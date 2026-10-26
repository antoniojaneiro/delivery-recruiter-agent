"""A second client, used only by the tests (D63): warehouse pickers, English only, no service areas, no call booking.
If a Sazón detail leaks back into the engine, the tests built on this spec fail."""
from typing import Literal

from sazon.client import Client
from sazon.model import Language, Outcome
from sazon.pack import Pack
from sazon.spec import FieldSpec, RecruiterTexts, Rule, ScreeningSpec, read_attribute
from sazon.validators import Validation, validate_name

EN = Language.EN
SHIFTS = ("day", "night")


def say(text: str) -> dict:
    return {EN: text}


def _validate_shift(value, today) -> Validation:
    if value not in SHIFTS:
        return Validation(False, reason="pick day or night")
    return Validation(True, value)


def _validate_can_lift(value, today) -> Validation:
    if not isinstance(value, bool):
        return Validation(False, reason="need a clear yes or no")
    return Validation(True, value)


PACK = Pack(
    company="Acme Logistics",
    default_language=EN,
    consent=say("Hi, I'm Acme Logistics' virtual assistant (an AI). I'll ask three questions about your picker "
                "application. A recruiter reviews every answer. May I save your answers?"),
    closed=say("We are not hiring right now."),
    error=say("Something went wrong. Could you say that again?"),
    reminder=say("Still interested in the picker job?"),
    unclear=say("Sorry, I need that to continue. "),
    confirm_city=say("Do you mean {suggestion}?"),
    confirm_change=say("You said {old} before. Change it to {new}?"),
    blocked=say("I can't go on until you tell me {what}."),
    close={
        Outcome.QUALIFIED: say("Thanks, you are through. Our team will call you within 5 days."),
        Outcome.ENDED_OFF_TOPIC: say("That is off topic, so I am stopping here."),
        Outcome.WITHDRAWN: say("OK, stopping. Write 'continue' to start again."),
    },
    close_other=say("Thanks for your time."),
    close_no_consent=say("Without your consent I cannot go on. Write 'yes' to start."),
    close_repeat={Outcome.QUALIFIED: say("You are through already; the team will call you.")},
    close_repeat_withdrawn=say("You stopped. Write 'continue' to start again."),
    close_repeat_other=say("This chat is closed."),
    notices={
        "human": say("I am an assistant; a recruiter reads everything."),
        "pay": say("A recruiter will talk about pay."),
        "changed": say("Changed."),
        "kept": say("Kept as it was."),
        "offtopic": say("Let's stay on the application."),
    },
)

RECRUITER = RecruiterTexts(
    outcome_labels={
        Outcome.IN_PROGRESS: "In progress", Outcome.QUALIFIED: "Qualified", Outcome.DISQUALIFIED: "Rejected by agent",
        Outcome.BLOCKED: "Blocked", Outcome.STALLED: "No reply", Outcome.ENDED_OFF_TOPIC: "Ended off topic",
        Outcome.WITHDRAWN: "Withdrew",
    },
    no_name="Unnamed candidate", reason_prefix="Reason: ", missing_prefix="Missing: ",
    no_consent="did not consent", blocked_on="has not said ", flags={},
    footer="Automatic summary: the recruiter decides.",
    chat_prefix="Chat: ", language_word="language", language_names={EN: "English"},
    clarification=("clarification", "clarifications"), asked_for_person="asked for a person",
    reminder_sent="reminder sent",
    started="Started", consented="Consented", answered="Answered: {label}", qualified="Qualified",
    booked="Booked a call", consent_stage="consent",
)

TOY = ScreeningSpec(
    role="warehouse-picker",
    pack=PACK,
    recruiter=RECRUITER,
    title_field="name",
    card_order=("shift", "can_lift"),
    fields=(
        FieldSpec("name", ask=say("What's your full name?"), what=say("your full name"), label="name",
                  validate=lambda value, today: validate_name(value), read=read_attribute("name"),
                  schema={"name": (str | None, None)}, prompt="- name: full name as written"),
        FieldSpec("shift", ask=say("Do you prefer day or night shifts?"), what=say("your preferred shift"),
                  label="shift", validate=_validate_shift, read=read_attribute("shift"),
                  card=lambda value: f"Shift: {value}",
                  schema={"shift": (Literal["day", "night"] | None, None)}, prompt='- shift: "day" or "night"'),
        FieldSpec("can_lift", ask=say("Can you lift 20 kg?"), what=say("whether you can lift 20 kg"),
                  label="lifting", validate=_validate_can_lift, rejects=lambda value: value is False,
                  read=read_attribute("can_lift"), schema={"can_lift": (bool | None, None)},
                  card=lambda value: "Can lift 20 kg: " + ("yes" if value else "no"),
                  confirm_rejection=say("Just to confirm: you cannot lift 20 kg?"),
                  prompt="- can_lift: true/false only if they clearly state they can lift 20 kg"),
    ),
    rules=(Rule("CANNOT_LIFT", applies=lambda screening: screening.values.get("can_lift") is False,
                close=say("We need someone who can lift 20 kg, so I can't go on. A recruiter can review your case."),
                summary="cannot lift 20 kg"),),
)

TOY_CLIENT = Client(spec=TOY, areas={})
