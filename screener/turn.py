"""One candidate message in, one reply out. The rules live in Screening; this module only does the
outside work: calling the model, loading and saving, and writing the reply."""
from dataclasses import replace
from datetime import date, datetime

from screener import conversation, session, slot_flow
from screener.conversation import RETRY_ONCE, SKIP, Turn
from screener.client import Client
from screener.consent import ConsentReading, is_stop_request, read_consent
from screener.extraction import ControlFlags, extract
from screener.llm import LLM, LLMError
from screener.directive import Directive, Kind
from screener.phrasing import closed_message, consent_message, phrase, technical_error_message
from screener.screening import ExtractionContext, Screening
from screener.spec import ScreeningSpec
from screener.store import ConflictError

NOT_STORED = "[message not stored: no consent]"


def start(store, client: Client, candidate_id: str, now: datetime) -> str:
    if not store.accepting_applications():
        return closed_message(client.spec)
    text = consent_message(client.spec)
    try:
        return conversation.run(store, client, candidate_id, now,
                                lambda screening: Turn(text, messages=[("agent", text)]))
    except ConflictError:
        return technical_error_message(client.spec, client.spec.pack.default_language)


def wait_24h(llm: LLM, store, client: Client, candidate_id: str, now: datetime) -> str | None:
    """Simulates 24 hours of silence: first a reminder, then STALLED (D35)."""
    if not store.accepting_applications():
        return None
    def work(screening: Screening) -> Turn:
        if not screening.is_open:
            return Turn(None, save=False)
        directive = screening.on_silence()
        reply = phrase(llm, client.spec, directive, screening.language) if directive else None
        return Turn(reply, messages=[("agent", reply)] if reply else [])

    # the record changed under us: skip this candidate for now
    return conversation.run(store, client, candidate_id, now, work, on_conflict=SKIP)


def handle_message(llm: LLM, store, client: Client, candidate_id: str, message: str,
                   now: datetime) -> str:
    if not store.accepting_applications():
        return closed_message(client.spec)  # nothing is read, stored or sent to the model while applications are closed
    if store.get(candidate_id) is None:  # never started, or erased: they see the disclosure before anything else
        return start(store, client, candidate_id, now)
    try:  # a lost race is retried once with a fresh copy; an erased candidate is never brought back
        return conversation.run(store, client, candidate_id, now,
                                lambda screening: _handle(llm, store, client, candidate_id, message, now, screening),
                                on_conflict=RETRY_ONCE)
    except ConflictError:
        return technical_error_message(client.spec, session.load(store, candidate_id, client).language)


def _handle(llm: LLM, store, client: Client, candidate_id: str, message: str, now: datetime,
            screening: Screening) -> Turn:
    screening.resume()
    consented_before = screening.consent is True  # the turn that answers the consent question shares nothing
    history = store.messages(candidate_id)
    last_question = history[-1].text if history and history[-1].role == "agent" else None
    if screening.awaiting_slot_choice:
        directive = slot_flow.handle_pick(store, client, screening, candidate_id, message, now)
    else:
        directive = _directive_for(llm, screening, message, now.date(), last_question)
        directive = slot_flow.after_close(store, client, screening, candidate_id, directive, now)
    # what the model may see when it words a message: the saved conversation and this message, only after consent
    context = [(m.role, m.text) for m in history] + [("candidate", message)] if consented_before else []
    reply = (consent_message(client.spec) if directive is None
             else phrase(llm, client.spec, directive, screening.language, history=context))
    if directive is not None and directive.kind == Kind.CLOSE:
        short = phrase(llm, client.spec, replace(directive, repeat=True), screening.language)
        if last_question in (reply, short):  # already said once: not the same close word for word
            reply = short
    kept = message if screening.consent else NOT_STORED
    return Turn(reply, messages=[("candidate", kept), ("agent", reply)])


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
