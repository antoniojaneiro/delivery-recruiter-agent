"""The recruiter's summary card (D46). Built by code from the saved, validated data: it never repeats
the candidate's own words and never says anything about the person beyond the facts they gave.
The card is in the language the recruiter reads (D66); the one saved with the candidate is in the pack's default."""
from screener.model import EventType, Language, Outcome
from screener.screening import Screening


def summarise(screening: Screening, language: Language | None = None) -> str:
    spec = screening.spec
    language = language or spec.pack.default_language
    texts = spec.recruiter_texts(language)
    decision = screening.decide()
    data = screening.extracted()
    consented = screening.consent is True
    head = [data.get(spec.title_field) or texts.no_name]
    if consented and spec.area_field and data.get(spec.area_field):
        head.append(data[spec.area_field])
    head.append(texts.outcome_labels[decision.outcome])
    lines = [" · ".join(head)]
    reasons = [spec.reason_text(code, language) for code in decision.reasons]
    if reasons:
        lines.append(texts.reason_prefix + "; ".join(reasons))
    if consented:
        lines += [spec.field(key).card(data[key], language) for key in spec.card_order if key in data]
        missing = [spec.say(spec.field(f).label, language) for f in screening.missing_fields()]
        if missing and decision.outcome not in (Outcome.DISQUALIFIED, Outcome.WITHDRAWN):
            lines.append(texts.missing_prefix + ", ".join(missing))
    lines += [texts.flags[flag] for flag in decision.flags if flag in texts.flags]
    lines.append(_chat_line(screening, language))
    lines.append(texts.footer)
    return "\n".join(lines)


def _chat_line(screening: Screening, language: Language) -> str:
    texts = screening.spec.recruiter_texts(language)
    kinds = [kind for kind, _ in screening.events]
    parts = [f"{texts.language_word} {texts.language_names[screening.language]}"]
    clarifications = kinds.count(EventType.FOLLOW_UP)
    if clarifications:
        parts.append(f"{clarifications} {texts.clarification[0] if clarifications == 1 else texts.clarification[1]}")
    if EventType.HUMAN_REQUESTED in kinds:
        parts.append(texts.asked_for_person)
    if screening.reminder_sent:
        parts.append(texts.reminder_sent)
    return texts.chat_prefix + " · ".join(parts)


def card_for(record, client, language: Language | None = None) -> str:
    """The card in `language`, rebuilt from the saved state (a read, never a write). The card saved with the
    candidate stays the audit snapshot. A record with no state (erased) shows what was saved."""
    if not record.state:
        return record.summary or ""
    return summarise(Screening.from_state(client.areas, record.state, client.spec), language)
