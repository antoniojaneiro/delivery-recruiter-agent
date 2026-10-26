"""Grupo Sazón's screening: delivery drivers in Spain and Mexico (D63)."""
from datetime import date
from typing import Literal

from sazon import validators
from sazon.extraction import StartDate, build_system_prompt
from sazon.model import Field, Reason
from sazon.spec import MISSING, FieldSpec, Rule, ScreeningSpec, read_attribute


def _experience(value):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return validators.Validation(False, reason="need years and platform")
    return validators.validate_experience(*value)


def _read_experience(reply, today, base):
    if reply.experience_years is None and not reply.platforms:
        return MISSING
    base = base or {}
    years = reply.experience_years if reply.experience_years is not None else base.get("years")
    return (years, reply.platforms or base.get("platforms", []))


def _read_start_date(reply, today, base):
    return reply.start_date.resolve(today) if reply.start_date is not None else MISSING


def _date_from_json(value):
    return date.fromisoformat(value) if isinstance(value, str) else value


SAZON = ScreeningSpec(
    role="delivery-driver",
    fields=(
        FieldSpec(Field.NAME, validate=lambda value, today: validators.validate_name(value),
                  same=lambda old, new: validators.fold(old) == validators.fold(new),
                  read=read_attribute("name"), schema={"name": (str | None, None)},
                  prompt="- name: full name as written"),
        FieldSpec(Field.EXPERIENCE, validate=lambda value, today: _experience(value),
                  same=lambda old, new: old["years"] == new["years"] and set(old["platforms"]) == set(new["platforms"]),
                  read=_read_experience, partial=lambda value: {"years": value[0], "platforms": value[1]},
                  decode_candidate=tuple,
                  schema={"experience_years": (float | None, None), "platforms": (list[str], [])},
                  prompt="- experience_years: number of years of delivery experience (0 if none)\n"
                         "- platforms: delivery platforms mentioned, as written (e.g. Glovo, Uber Eats)"),
        FieldSpec(Field.AVAILABILITY, validate=lambda value, today: validators.validate_availability(value),
                  same=lambda old, new: set(old) == set(new),
                  read=read_attribute("availability", empty_is_missing=True),
                  schema={"availability": (list[Literal["full_time", "part_time", "weekends"]], [])},
                  prompt='- availability: any of "full_time", "part_time", "weekends"'),
        FieldSpec(Field.SCHEDULE, validate=lambda value, today: validators.validate_schedule(value),
                  read=read_attribute("schedule"),
                  schema={"schedule": (Literal["morning", "afternoon", "evening", "flexible"] | None, None)},
                  prompt='- schedule: one of "morning", "afternoon", "evening", "flexible"'),
        FieldSpec(Field.START_DATE, validate=validators.validate_start_date, read=_read_start_date,
                  decode_value=_date_from_json, decode_candidate=_date_from_json,
                  schema={"start_date": (StartDate | None, None)},
                  prompt='- start_date: {"iso": "YYYY-MM-DD"} for an exact date, else {"now": true}, {"in_days": n} or '
                         '{"in_weeks": n}, {"in_months": n}, or {"weekday": 0-6} (Monday=0) for "next Monday" or '
                         '"el lunes". Never do date arithmetic yourself.'),
        FieldSpec(Field.CITY, read=read_attribute("city"), schema={"city": (str | None, None)},
                  prompt="- city: the city or zone exactly as written, never mapped or corrected"),
        FieldSpec(Field.LICENSE, validate=lambda value, today: validators.validate_license(value),
                  rejects=lambda value: value is False, read=read_attribute("has_license"),
                  schema={"has_license": (bool | None, None)},
                  prompt="- has_license: true/false only if they clearly state whether they hold a driver's license. "
                         "A license is not a car,\n  motorbike, bike or any vehicle: not owning a vehicle says nothing "
                         "about the license (leave it null)"),
    ),
    rules=(
        Rule(Reason.NO_LICENSE, applies=lambda screening: screening.values.get(Field.LICENSE) is False),
        Rule(Reason.OUT_OF_AREA, applies=lambda screening: screening.out_of_area),
    ),
    area_field=Field.CITY,
)

Extraction = SAZON.extraction_model
SYSTEM = build_system_prompt(SAZON)
