"""A second client, used only by the tests (D63): warehouse pickers, English only, no service areas.
If a Sazón detail leaks back into the engine, the tests built on this spec fail."""
from typing import Literal

from sazon.spec import FieldSpec, Rule, ScreeningSpec, read_attribute
from sazon.validators import Validation, validate_name

SHIFTS = ("day", "night")


def _validate_shift(value, today) -> Validation:
    if value not in SHIFTS:
        return Validation(False, reason="pick day or night")
    return Validation(True, value)


def _validate_can_lift(value, today) -> Validation:
    if not isinstance(value, bool):
        return Validation(False, reason="need a clear yes or no")
    return Validation(True, value)


TOY = ScreeningSpec(
    fields=(
        FieldSpec("name", validate=lambda value, today: validate_name(value), read=read_attribute("name"),
                  schema={"name": (str | None, None)}, prompt="- name: full name as written"),
        FieldSpec("shift", validate=_validate_shift, read=read_attribute("shift"),
                  schema={"shift": (Literal["day", "night"] | None, None)}, prompt='- shift: "day" or "night"'),
        FieldSpec("can_lift", validate=_validate_can_lift, rejects=lambda value: value is False,
                  read=read_attribute("can_lift"), schema={"can_lift": (bool | None, None)},
                  prompt="- can_lift: true/false only if they clearly state they can lift 20 kg"),
    ),
    role="warehouse-picker",
    rules=(Rule("CANNOT_LIFT", applies=lambda screening: screening.values.get("can_lift") is False),),
)
