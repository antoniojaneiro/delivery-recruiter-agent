"""One candidate message in, one reply out. The rules live in Screening; this module only does the
outside work: calling the model, loading and saving, and writing the reply."""
from dataclasses import replace
from datetime import date, datetime

from sazon import session, slot_flow
from sazon.consent import ConsentReading, is_stop_request, read_consent
from sazon.extraction import ControlFlags, extract
from sazon.llm import LLM, LLMError
from sazon.phrasing import Directive, Kind, closed_message, consent_message, phrase, technical_error_message
from sazon.screening import ExtractionContext, Screening
from sazon.spec import ScreeningSpec
from sazon.store import ConflictError

NOT_STORED = "[message not stored: no consent]"


def start(store, areas: dict[str, list[str]], candidate_id: str, now: datetime) -> str:
    if not store.accepting_applications():
        return closed_message()
    screening = session.load(store, candidate_id, areas)
    text = consent_message()
    try:
        session.commit(store, candidate_id, screening, now, messages=[("agent", text)])
    except ConflictError:
        return technical_error_message(screening.language)
    return text


def wait_24h(llm: LLM, store, areas: dict[str, list[str]], candidate_id: str, now: datetime) -> str | None:
    """Simulates 24 hours of silence: first a reminder, then STALLED (D35)."""
    if not store.accepting_applications():
        return None
    screening = session.load(store, candidate_id, areas)
    if not screening.is_open:
        return None
    directive = screening.on_silence()
    reply = phrase(llm, directive, screening.language) if directive else None
    try:
        session.commit(store, candidate_id, screening, now, messages=[("agent", reply)] if reply else [])
    except ConflictError:
        return None  # the record changed under us: skip this candidate for now
    return reply


def handle_message(llm: LLM, store, areas: dict[str, list[str]], candidate_id: str, message: str,
                   now: datetime) -> str:
    if not store.accepting_applications():
        return closed_message()  # nothing is read, stored or sent to the model while applications are closed
    if store.get(candidate_id) is None:  # never started, or erased: they see the disclosure before anything else
        return start(store, areas, candidate_id, now)
    for attempt in range(2):
        try:
            return _handle(llm, store, areas, candidate_id, message, now)
        except ConflictError:
            if store.get(candidate_id) is None:  # erased meanwhile: never bring the record back
                break
    return technical_error_message(session.load(store, candidate_id, areas).language)


def _handle(llm: LLM, store, areas: dict[str, list[str]], candidate_id: str, message: str, now: datetime) -> str:
    screening = session.load(store, candidate_id, areas)
    screening.resume()
    history = store.messages(candidate_id)
    last_question = history[-1].text if history and history[-1].role == "agent" else None
    if screening.awaiting_slot_choice:
        directive = slot_flow.handle_pick(store, screening, candidate_id, message, now)
    else:
        directive = _directive_for(llm, screening, message, now.date(), last_question)
        directive = slot_flow.after_close(store, screening, candidate_id, directive, now)
    reply = consent_message() if directive is None else phrase(llm, directive, screening.language)
    if directive is not None and directive.kind == Kind.CLOSE:
        short = phrase(llm, replace(directive, repeat=True), screening.language)
        if last_question in (reply, short):  # already said once: not the same close word for word
            reply = short
    kept = message if screening.consent else NOT_STORED
    session.commit(store, candidate_id, screening, now, messages=[("candidate", kept), ("agent", reply)])
    return reply


def _directive_for(llm: LLM, screening: Screening, message: str, today: date,
                   last_question: str | None) -> Directive | None:
    """What to say next. None means the consent question is asked again."""
    back = screening.returning(message)
    if back is not None:
        return back
    if not screening.is_open:
        return screening.close_directive()
    if screening.needs_consent:
        reading = read_consent(message)
        if reading.answer is None and is_stop_request(message):  # "me retiro" before consent closes it
            reading = ConsentReading(False, reading.language)
        return screening.apply_consent_reply(reading)
    if is_stop_request(message):
        return screening.apply_stop_request()
    if screening.awaiting_change:
        reading = read_consent(message)  # a yes or a no, read in plain code
        if reading.answer is not None:
            return screening.resolve_change(reading.answer, today)
        screening.drop_change()  # anything else: forget the question and read the message normally
    try:
        extraction = _extract_with_one_retry(llm, screening.spec, screening.extraction_context(), message, today,
                                             last_question)
    except LLMError as error:
        return screening.model_failed(f"unreachable:{error.kind}")
    if extraction is None:
        return screening.model_failed("unparseable")
    return screening.apply(extraction, message, today)


def _extract_with_one_retry(llm: LLM, spec: ScreeningSpec, context: ExtractionContext, message: str, today: date,
                            last_question: str | None) -> ControlFlags | None:
    for _ in range(2):
        result = extract(llm, spec, message, context.asking, context.awaiting_confirmation, today,
                         last_question, context.previous_answer,
                         awaiting_rejection=context.awaiting_rejection)
        if result is not None:
            return result
    return None
