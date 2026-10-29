"""One candidate message in, one reply out. The rules live in Screening; this module only does the
outside work: calling the model, loading and saving, and writing the reply."""
import hashlib
from dataclasses import replace
from datetime import date, datetime

from screener import conversation, session, slot_flow
from screener.conversation import RETRY_ONCE, Turn
from screener.client import Client
from screener.consent import ConsentReading, is_stop_request, read_consent
from screener.cv import CvProblem, extract_cv, read_pdf
from screener.extraction import ControlFlags, extract
from screener.llm import LLM, NO_MODEL, LLMError
from screener.model import Outcome
from screener.directive import Directive, Kind
from screener.phrasing import closed_message, consent_message, fixed, phrase, technical_error_message
from screener.recruiter_rules import can_schedule
from screener.screening import ExtractionContext, Screening
from screener.spec import ScreeningSpec
from screener.store import ConflictError

NOT_STORED = "[message not stored: no consent]"
CV_MARK = "[CV uploaded]"  # what the transcript shows of an upload; the file itself is kept apart


def start(store, client: Client, candidate_id: str, now: datetime, buttons: bool = False) -> str:
    """A new candidate and the disclosure they are shown first. `buttons`: the channel has a button to choose a time, so
    the offer of times names it instead of numbering them (D90); it is saved with the candidate."""
    if not store.accepting_applications():
        return closed_message(client.spec)
    text = consent_message(client.spec)

    def work(screening: Screening) -> Turn:
        screening.buttons = buttons
        return Turn(text, messages=[("agent", text)])

    try:
        return conversation.run(store, client, candidate_id, now, work)
    except ConflictError:
        return technical_error_message(client.spec, client.spec.pack.default_language)


def handle_message(llm: LLM, store, client: Client, candidate_id: str, message: str,
                   now: datetime, voice: bool = False) -> str:
    """`voice`: the message was spoken and the reply will be spoken (D93): no CV upload, and a call is booked by saying a day
    and then a time, with no list and no button. The channel is per message: the same candidate can write the next one."""
    if not store.accepting_applications():
        return closed_message(client.spec)  # nothing is read, stored or sent to the model while applications are closed
    if store.get(candidate_id) is None:  # never started, or erased: they see the disclosure before anything else
        return start(store, client, candidate_id, now)
    try:  # a lost race is retried once with a fresh copy; an erased candidate is never brought back
        return conversation.run(store, client, candidate_id, now,
                                lambda screening: _handle(llm, store, client, candidate_id, message, now, screening, voice),
                                on_conflict=RETRY_ONCE)
    except ConflictError:
        return technical_error_message(client.spec, session.load(store, candidate_id, client).language)


def voice_opening(store, client: Client, candidate_id: str, now: datetime) -> tuple[str, str | None]:
    """The first words of a call, and the language to speak them in (None when it is not known yet) (D93). It is what the engine
    would say now on the voice channel: the disclosure for someone who has not answered the consent question (already shown in
    the text chat, so not saved again), the way back to the open question for someone midway, the day question for someone
    qualified who has no call, the call they have, or the closing. It is saved as the agent's message, so the transcript shows
    what was heard, and the consent question is never asked twice."""
    if not store.accepting_applications():
        return closed_message(client.spec), None
    record = store.get(candidate_id)
    if record is None:
        return consent_message(client.spec), None

    def work(screening: Screening) -> Turn:
        language = screening.language
        if screening.needs_consent:
            return Turn((consent_message(client.spec), None), save=False)
        if screening.decide().outcome == Outcome.QUALIFIED:
            directive = slot_flow.after_close(store, client, screening, candidate_id, screening.close_directive(), now, voice=True)
            text = phrase(NO_MODEL, client.spec, directive, language)
        elif not screening.is_open:
            text = phrase(NO_MODEL, client.spec, replace(screening.close_directive(), repeat=True), language)
        else:
            screening.withhold_cv_offer()
            slots = client.spec.pack.slots
            lead = client.spec.pack.pick(slots.voice["resume"], language) + " " if slots and "resume" in slots.voice else ""
            text = lead + phrase(NO_MODEL, client.spec, screening.current_directive(), language)
        history = store.messages(candidate_id)
        said_already = bool(history) and history[-1].role == "agent" and history[-1].text == text
        return Turn((text, language.value), messages=[] if said_already else [("agent", text)])

    try:
        return conversation.run(store, client, candidate_id, now, work, on_conflict=RETRY_ONCE)
    except ConflictError:
        return technical_error_message(client.spec, client.spec.pack.default_language), None


def handle_slot(store, client: Client, candidate_id: str, slot_id: int, now: datetime) -> str:
    """A time chosen in the picker. Only a candidate the agent qualified can choose; for anyone else nothing happens
    and nothing is said. The answer is the one typing a number would have given."""
    if not store.accepting_applications() or store.get(candidate_id) is None:
        return ""

    def work(screening: Screening) -> Turn:
        if (screening.decide().outcome != Outcome.QUALIFIED or screening.spec.pack.slots is None
                or not can_schedule(store.get(candidate_id))):
            return Turn("", save=False)
        chosen, directive = slot_flow.pick_slot(store, client, screening, candidate_id, slot_id, now)
        reply = fixed(client.spec, directive, screening.language)
        return Turn(reply, messages=[("candidate", chosen), ("agent", reply)])

    try:
        return conversation.run(store, client, candidate_id, now, work, on_conflict=RETRY_ONCE)
    except ConflictError:
        return technical_error_message(client.spec, session.load(store, candidate_id, client).language)


def handle_cv(llm: LLM, store, client: Client, candidate_id: str, data: bytes, now: datetime) -> str:
    """A PDF uploaded while the CV is on offer (D71). It is kept for the recruiter; the clear answers in it are taken
    for the fields the client allows, and the candidate is told what was taken so they can correct it."""
    texts = client.spec.pack.cv
    if texts is None:
        raise ValueError("this client takes no CVs")
    if not store.accepting_applications():
        return closed_message(client.spec)
    if store.get(candidate_id) is None:
        return start(store, client, candidate_id, now)
    peek = session.load(store, candidate_id, client)
    pick = client.spec.pack.pick
    if peek.needs_consent:
        return consent_message(client.spec)
    if not peek.cv_offered:
        return pick(texts.not_now, peek.language)
    cv = read_pdf(data)
    if cv.problem in (CvProblem.NOT_A_PDF, CvProblem.TOO_BIG):
        return pick(texts.invalid, peek.language)
    digest = hashlib.sha256(data).hexdigest()[:12]
    extraction, failure = None, None
    if cv.problem is None:
        try:
            extraction = extract_cv(llm, client.spec, cv.text, now.date())
        except LLMError as error:
            failure = f"unreachable:{error.kind}"
        failure = failure or (None if extraction is not None else "unparseable")

    def work(screening: Screening) -> Turn:
        screening.resume()
        if not (screening.cv_offered and screening.is_open):  # answered by hand while the file was being read
            return Turn(pick(texts.not_now, screening.language), save=False)
        taken: list[str] = []
        if extraction is None:
            if failure:
                screening.record_model_failure(failure)
            directive = screening.cv_unreadable(len(data), digest)
        else:
            taken, directive = screening.apply_cv(extraction, now.date(), len(data), digest)
        lead = (phrase(llm, client.spec, Directive(Kind.CV_READ, options=taken), screening.language) if taken
                else pick(texts.unreadable, screening.language))
        reply = lead + " " + fixed(client.spec, directive, screening.language)  # no model right after a CV
        return Turn(reply, messages=[("candidate", CV_MARK), ("agent", reply)], cv=data)

    try:
        return conversation.run(store, client, candidate_id, now, work, on_conflict=RETRY_ONCE)
    except ConflictError:
        return technical_error_message(client.spec, session.load(store, candidate_id, client).language)


def _handle(llm: LLM, store, client: Client, candidate_id: str, message: str, now: datetime,
            screening: Screening, voice: bool = False) -> Turn:
    screening.resume()
    consented_before = screening.consent is True  # the turn that answers the consent question shares nothing
    history = store.messages(candidate_id)
    last_question = history[-1].text if history and history[-1].role == "agent" else None
    spoken = voice and slot_flow.can_speak(client)
    if spoken and screening.awaiting_slot_choice:
        directive = slot_flow.handle_spoken(store, client, screening, candidate_id, message, now)
    elif screening.slot_offer and screening.awaiting_slot_choice:
        directive = slot_flow.handle_pick(store, client, screening, candidate_id, message, now)
    else:
        screening.end_voice_booking()  # a spoken booking left open when they write instead
        directive = _directive_for(llm, screening, message, now.date(), last_question)
        if voice and directive is not None and directive.kind == Kind.CV_OFFER:  # a file cannot be sent by voice
            screening.withhold_cv_offer()
            directive = Directive(Kind.ASK, field=screening.next_field())
        directive = slot_flow.after_close(store, client, screening, candidate_id, directive, now, voice=spoken)
    # what the model may see when it words a message: the saved conversation and this message, only after consent
    context = [(m.role, m.text) for m in history] + [("candidate", message)] if consented_before else []
    wording = NO_MODEL if voice else llm  # speech has no time for a second model call: the fixed words (and the free model's rate)
    reply = (consent_message(client.spec) if directive is None
             else phrase(wording, client.spec, directive, screening.language, history=context))
    if directive is not None and directive.kind == Kind.CV_OFFER:  # the offer, then the first question
        ask = Directive(Kind.ASK, field=screening.next_field())
        reply = reply + " " + fixed(client.spec, ask, screening.language)  # nothing was said to acknowledge
    if directive is not None and directive.kind == Kind.CLOSE:
        short = phrase(wording, client.spec, replace(directive, repeat=True), screening.language)
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
    screening.skip_cv()  # whatever was typed instead of uploading ends the offer; the message is read as usual
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
