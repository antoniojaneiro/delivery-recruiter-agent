"""The fixed wording a client gives the engine (D63). Everything the candidate reads that is not written by the
model lives here, in every language the client supports; a missing text is a missing argument, not a runtime error."""
from dataclasses import dataclass

from screener.language import pick
from screener.model import Language, Outcome

Text = dict[Language, str]  # language -> wording; {placeholders} are filled in by the engine


@dataclass(frozen=True)
class SlotTexts:
    """Only for a client whose agent books a call when a candidate qualifies."""
    offer: dict[str, Text]  # first, taken, unclear, reminder: the line above the numbered list
    offer_end: Text
    booked: Text  # {label}
    already_booked: Text  # {label}
    cancelled: Text


@dataclass(frozen=True)
class Pack:
    company: str
    default_language: Language
    consent: Text  # the disclosure and the consent question; its hash is stored with the answer
    closed: Text  # applications are closed
    error: Text
    reminder: Text
    unclear: Text  # said before asking the question again
    confirm_city: Text  # {suggestion}
    confirm_change: Text  # {old}, {new}
    blocked: Text  # {what}
    close: dict[Outcome, Text]  # QUALIFIED, ENDED_OFF_TOPIC, WITHDRAWN
    close_other: Text
    close_no_consent: Text
    close_repeat: dict[Outcome, Text]  # a close already sent once, said shortly
    close_repeat_withdrawn: Text
    close_repeat_other: Text
    notices: dict[str, Text]  # human, pay, changed, kept, offtopic
    slots: SlotTexts | None = None

    def pick(self, text: Text, language) -> str:
        return pick(text, language, self.default_language)
