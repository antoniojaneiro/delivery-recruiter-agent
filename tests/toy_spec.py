"""A second client, used only by the tests (D63): warehouse pickers, English only, no service areas.
If a Sazón detail leaks back into the engine, the tests built on this spec fail."""
from sazon.spec import FieldSpec, Rule, ScreeningSpec
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
        FieldSpec("name", validate=lambda value, today: validate_name(value)),
        FieldSpec("shift", validate=_validate_shift),
        FieldSpec("can_lift", validate=_validate_can_lift, rejects=lambda value: value is False),
    ),
    rules=(Rule("CANNOT_LIFT", applies=lambda screening: screening.values.get("can_lift") is False),),
)
