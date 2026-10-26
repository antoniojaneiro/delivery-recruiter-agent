"""The recruiter's summary card (D46). Built by code from the saved, validated data: it never repeats
the candidate's own words and never says anything about the person beyond the facts they gave."""
from screener.model import NO_CONSENT, EventType, Outcome
from screener.screening import Screening
from screener.spec import ScreeningSpec


def summarise(screening: Screening) -> str:
    spec = screening.spec
    texts = spec.recruiter
    decision = screening.decide()
    data = screening.extracted()
    consented = screening.consent is True
    head = [data.get(spec.title_field) or texts.no_name]
    if consented and spec.area_field and data.get(spec.area_field):
        head.append(data[spec.area_field])
    head.append(texts.outcome_labels[decision.outcome])
    lines = [" · ".join(head)]
    reasons = [_reason(spec, code) for code in decision.reasons]
    if reasons:
        lines.append(texts.reason_prefix + "; ".join(reasons))
    if consented:
        lines += [spec.field(key).card(data[key]) for key in spec.card_order if key in data]
        missing = [spec.field(f).label for f in screening.missing_fields()]
        if missing and decision.outcome not in (Outcome.DISQUALIFIED, Outcome.WITHDRAWN):
            lines.append(texts.missing_prefix + ", ".join(missing))
    lines += [texts.flags[flag] for flag in decision.flags if flag in texts.flags]
    lines.append(_chat_line(screening))
    lines.append(texts.footer)
    return "\n".join(lines)


def _reason(spec: ScreeningSpec, code: str) -> str:
    if code == NO_CONSENT:
        return spec.recruiter.no_consent
    if code.startswith("BLOCKED_ON_"):
        field = spec.field(code.removeprefix("BLOCKED_ON_").lower())
        return spec.recruiter.blocked_on + (field.not_provided or field.label)
    try:
        return spec.rule(code).summary
    except ValueError:
        return code


def _chat_line(screening: Screening) -> str:
    texts = screening.spec.recruiter
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
