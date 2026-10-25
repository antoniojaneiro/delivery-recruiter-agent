from datetime import date, datetime

from sazon import session
from sazon.extraction import Extraction, extract
from sazon.llm import LLM, LLMError
from sazon.model import Field, Outcome, Status
from sazon.phrasing import Directive, Kind, consent_message, phrase
from sazon.screening import FIELD_ORDER, LIVE, Screening

_MISSING = object()
NOT_STORED = "[message not stored: no consent]"


def start(store, areas: dict[str, list[str]], candidate_id: str, now: datetime) -> str:
    screening = session.load(store, candidate_id, areas)
    text = consent_message()
    session.commit(store, candidate_id, screening, now, messages=[("agent", text)])
    return text


def wait_24h(llm: LLM, store, areas: dict[str, list[str]], candidate_id: str, now: datetime) -> str | None:
    """Simulates 24 hours of silence: first a reminder, then STALLED (D35)."""
    screening = session.load(store, candidate_id, areas)
    if screening.decide().outcome not in LIVE:
        return None
    if screening.reminder_sent:
        screening.mark_stalled()
        session.commit(store, candidate_id, screening, now)
        return None
    screening.send_reminder()
    reply = phrase(llm, Directive(Kind.REMINDER), screening.language)
    session.commit(store, candidate_id, screening, now, messages=[("agent", reply)])
    return reply


def handle_message(llm: LLM, store, areas: dict[str, list[str]], candidate_id: str, message: str,
                   now: datetime) -> str:
    screening = session.load(store, candidate_id, areas)
    screening.resume()
    history = store.messages(candidate_id)
    last_question = history[-1].text if history and history[-1].role == "agent" else None
    directive = _directive_for(llm, screening, message, now.date(), last_question)
    reply = consent_message() if directive is None else phrase(llm, directive, screening.language)
    kept = message if screening.consent else NOT_STORED
    session.commit(store, candidate_id, screening, now,
                   messages=[("candidate", kept), ("agent", reply)])
    return reply


def _extract_with_one_retry(llm: LLM, screening: Screening, message: str, asking: Field | None,
                            today: date, last_question: str | None) -> Extraction | None:
    for _ in range(2):
        result = extract(llm, message, asking, screening.awaiting_confirmation, today,
                         last_question, screening.previous_answer(asking),
                         awaiting_rejection=screening.awaiting_rejection)
        if result is not None:
            return result
    return None


def _close(screening: Screening) -> Directive:
    decision = screening.decide()
    return Directive(Kind.CLOSE, outcome=decision.outcome, reasons=decision.reasons)


def _directive_for(llm: LLM, screening: Screening, message: str, today: date,
                   last_question: str | None) -> Directive | None:
    """Applies the message to the screening and returns what to say next (None re-asks consent)."""
    if screening.decide().outcome not in LIVE:
        return _close(screening)
    asking = screening.next_field()
    try:
        extraction = _extract_with_one_retry(llm, screening, message, asking, today, last_question)
    except LLMError:
        screening.record_model_failure("unreachable")
        return Directive(Kind.TECHNICAL_ERROR)
    if extraction is None:
        screening.record_model_failure("unparseable")
        return Directive(Kind.TECHNICAL_ERROR)
    if extraction.language:
        screening.language = extraction.language
    if extraction.wants_human:
        screening.human_requested()
    if extraction.withdraw:
        screening.withdraw()
        return _close(screening)
    if screening.consent is None:
        if extraction.consent is None:
            if extraction.off_topic:
                screening.off_topic()
            return _close(screening) if screening.decide().outcome not in LIVE else None
        screening.record_consent(extraction.consent)
        if not extraction.consent:
            return _close(screening)
    unclear = _apply(screening, extraction, message, asking, today)
    if screening.decide().outcome not in LIVE:
        return _close(screening)
    if screening.awaiting_rejection:
        return Directive(Kind.CONFIRM_REJECTION, field=screening.awaiting_rejection,
                         suggestion=screening.rejection_subject)
    if screening.awaiting_confirmation:
        return Directive(Kind.CONFIRM_CITY, suggestion=screening.awaiting_confirmation)
    if screening.blocked_on:
        return Directive(Kind.BLOCKED, field=screening.blocked_on)
    if unclear:
        return Directive(Kind.FOLLOW_UP, field=unclear[0], reason=unclear[1])
    return Directive(Kind.ASK, field=screening.next_field())


def _apply(screening: Screening, ex: Extraction, message: str, asking: Field | None,
           today: date) -> tuple[Field, str] | None:
    unclear = None
    answered = False

    def note(field: Field, result) -> None:
        nonlocal unclear, answered
        answered = True
        if result.status == Status.FOLLOW_UP and unclear is None:
            unclear = (field, result.reason)

    if screening.awaiting_confirmation and ex.confirms_city is not None:
        note(Field.CITY, screening.confirm_city(ex.confirms_city))
    if screening.awaiting_rejection and ex.confirms_rejection is not None:
        note(screening.awaiting_rejection, screening.confirm_rejection(ex.confirms_rejection))
    for field in FIELD_ORDER:
        if field == Field.EXPERIENCE:
            experience = _experience(screening, ex)
            if experience is not _MISSING:
                result = screening.submit(field, experience, today, raw=message)
                if result.status == Status.FOLLOW_UP:
                    screening.partial[field] = {"years": experience[0], "platforms": experience[1]}
                note(field, result)
            continue
        value = _value(ex, field, today)
        if value is not _MISSING:
            note(field, screening.submit(field, value, today, raw=message))
    if not answered:
        if ex.off_topic:
            screening.off_topic()
        elif asking and asking != Field.CONSENT:
            note(asking, screening.submit(asking, None, today, raw=message))
    return unclear


def _experience(screening: Screening, ex: Extraction) -> object:
    if ex.experience_years is None and not ex.platforms:
        return _MISSING
    earlier = screening.partial.get(Field.EXPERIENCE, {})
    years = ex.experience_years if ex.experience_years is not None else earlier.get("years")
    platforms = ex.platforms or earlier.get("platforms", [])
    return (years, platforms)


def _value(ex: Extraction, field: Field, today: date) -> object:
    match field:
        case Field.NAME:
            return ex.name if ex.name is not None else _MISSING
        case Field.EXPERIENCE:
            return (ex.experience_years, ex.platforms) if ex.experience_years is not None else _MISSING
        case Field.AVAILABILITY:
            return ex.availability or _MISSING
        case Field.SCHEDULE:
            return ex.schedule if ex.schedule is not None else _MISSING
        case Field.START_DATE:
            return ex.start_date.resolve(today) if ex.start_date is not None else _MISSING
        case Field.CITY:
            return ex.city if ex.city is not None else _MISSING
        case Field.LICENSE:
            return ex.has_license if ex.has_license is not None else _MISSING
    return _MISSING
