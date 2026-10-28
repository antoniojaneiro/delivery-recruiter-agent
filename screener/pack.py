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
    scheduled: Text  # {label}: a recruiter booked the call for the candidate
    moved: Text  # {label}: a recruiter moved the booked call
    later: Text  # they chose none of the times, or went quiet: write again whenever they want to book


@dataclass(frozen=True)
class CvTexts:
    """Only for a client that lets a candidate upload a CV (D71)."""
    offer: Text  # said once after consent: the upload is optional and speeds things up
    notice: Text  # shown beside the uploader: what is kept, who sees it, that it can be erased
    read_back: Text  # {items}: what was taken from the CV, for the candidate to correct
    unreadable: Text  # the file was kept but nothing could be read from it
    invalid: Text  # not a PDF, or too big: nothing was kept
    not_now: Text  # a CV sent when none was being asked for


@dataclass(frozen=True)
class Pack:
    company: str
    default_language: Language
    consent: Text  # the disclosure and the consent question; its hash is stored with the answer
    closed: Text  # applications are closed
    error: Text
    reminder: Text
    unclear: Text  # said before asking the question again
    confirm_area: Text  # {suggestion}
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
    cv: CvTexts | None = None  # None: this client takes no CVs

    def pick(self, text: Text, language) -> str:
        return pick(text, language, self.default_language)
