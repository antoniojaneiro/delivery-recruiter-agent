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


# A second toy client that books calls: UK warehouses, service areas, its own clock.
from dataclasses import replace  # noqa: E402
from datetime import timedelta  # noqa: E402


from sazon.pack import SlotTexts  # noqa: E402
from sazon.slot_calendar import SlotCalendar  # noqa: E402

SLOTS = SlotTexts(
    offer={"first": say("You are through! Pick a time for a call:"), "taken": say("That time went. Pick another:"),
           "unclear": say("Pick one of these:"), "reminder": say("Times still free:")},
    offer_end=say("Reply with the number, or 'none'."),
    booked=say("Booked: {label}."), already_booked=say("Already booked: {label}."),
    cancelled=say("Your call was cancelled."),
)
_TOWN = FieldSpec("town", ask=say("Which town do you live in?"), what=say("your town"), label="town",
                  read=read_attribute("town"), schema={"town": (str | None, None)},
                  prompt="- town: the town as written, never corrected",
                  confirm_rejection=say("Just to confirm: you live in {city}?"))
TOY_UK_SPEC = replace(
    TOY,
    pack=replace(PACK, slots=SLOTS),
    fields=(TOY.fields[0], _TOWN, TOY.fields[2]),
    area_field="town",
    place_qualifiers=("england", "united kingdom"),
    card_order=("can_lift",),
    rules=(*TOY.rules, Rule("OUT_OF_AREA", applies=lambda screening: screening.out_of_area,
                            close=say("We do not hire in your town yet."), summary="outside the hiring towns")),
)
UK_CALENDAR = SlotCalendar(timezones={"GB": "Europe/London"}, country_of={"Leeds": "GB", "London": "GB"},
                           min_notice=timedelta(hours=4), offer_size=2)
TOY_UK = Client(spec=TOY_UK_SPEC, areas={"Leeds": ["Headingley"], "London": []}, calendar=UK_CALENDAR)
