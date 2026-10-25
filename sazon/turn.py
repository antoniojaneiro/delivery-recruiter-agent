"""One candidate message in, one reply out. The rules live in Screening; this module only does the
outside work: calling the model, loading and saving, and writing the reply."""
from datetime import date, datetime

from sazon import session
from sazon.consent import read_consent
from sazon.extraction import Extraction, extract
from sazon.llm import LLM, LLMError
from sazon.phrasing import Directive, consent_message, phrase
from sazon.screening import ExtractionContext, Screening

NOT_STORED = "[message not stored: no consent]"


def start(store, areas: dict[str, list[str]], candidate_id: str, now: datetime) -> str:
    screening = session.load(store, candidate_id, areas)
    text = consent_message()
    session.commit(store, candidate_id, screening, now, messages=[("agent", text)])
    return text


def wait_24h(llm: LLM, store, areas: dict[str, list[str]], candidate_id: str, now: datetime) -> str | None:
    """Simulates 24 hours of silence: first a reminder, then STALLED (D35)."""
    screening = session.load(store, candidate_id, areas)
    if not screening.is_open:
        return None
    directive = screening.on_silence()
    reply = phrase(llm, directive, screening.language) if directive else None
    session.commit(store, candidate_id, screening, now, messages=[("agent", reply)] if reply else [])
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


def _directive_for(llm: LLM, screening: Screening, message: str, today: date,
                   last_question: str | None) -> Directive | None:
    """What to say next. None means the consent question is asked again."""
    if not screening.is_open:
        return screening.close_directive()
    if screening.needs_consent:
        return screening.apply_consent_reply(read_consent(message))
    try:
        extraction = _extract_with_one_retry(llm, screening.extraction_context(), message, today, last_question)
    except LLMError:
        return screening.model_failed("unreachable")
    if extraction is None:
        return screening.model_failed("unparseable")
    return screening.apply(extraction, message, today)


def _extract_with_one_retry(llm: LLM, context: ExtractionContext, message: str, today: date,
                            last_question: str | None) -> Extraction | None:
    for _ in range(2):
        result = extract(llm, message, context.asking, context.awaiting_confirmation, today,
                         last_question, context.previous_answer,
                         awaiting_rejection=context.awaiting_rejection)
        if result is not None:
            return result
    return None
