"""Grupo Sazón's screening: delivery drivers in Spain and Mexico (D63)."""
from sazon import validators
from sazon.model import Field, Reason
from sazon.spec import FieldSpec, Rule, ScreeningSpec

SAZON = ScreeningSpec(
    fields=(
        FieldSpec(Field.NAME, validate=lambda value, today: validators.validate_name(value),
                  same=lambda old, new: validators.fold(old) == validators.fold(new)),
        FieldSpec(Field.EXPERIENCE, validate=lambda value, today: _experience(value),
                  same=lambda old, new: old["years"] == new["years"] and set(old["platforms"]) == set(new["platforms"])),
        FieldSpec(Field.AVAILABILITY, validate=lambda value, today: validators.validate_availability(value),
                  same=lambda old, new: set(old) == set(new)),
        FieldSpec(Field.SCHEDULE, validate=lambda value, today: validators.validate_schedule(value)),
        FieldSpec(Field.START_DATE, validate=validators.validate_start_date),
        FieldSpec(Field.CITY),
        FieldSpec(Field.LICENSE, validate=lambda value, today: validators.validate_license(value),
                  rejects=lambda value: value is False),
    ),
    rules=(
        Rule(Reason.NO_LICENSE, applies=lambda screening: screening.values.get(Field.LICENSE) is False),
        Rule(Reason.OUT_OF_AREA, applies=lambda screening: screening.out_of_area),
    ),
    area_field=Field.CITY,
)


def _experience(value):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return validators.Validation(False, reason="need years and platform")
    return validators.validate_experience(*value)
