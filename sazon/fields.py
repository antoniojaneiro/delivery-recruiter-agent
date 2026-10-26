"""The names Grupo Sazón uses for its fields and its disqualifying reasons (D63)."""
from enum import StrEnum


class Field(StrEnum):
    NAME = "name"
    EXPERIENCE = "experience"
    AVAILABILITY = "availability"
    SCHEDULE = "schedule"
    START_DATE = "start_date"
    CITY = "city"
    LICENSE = "license"
    CONSENT = "consent"


class Reason(StrEnum):
    NO_CONSENT = "NO_CONSENT"
    NO_LICENSE = "NO_LICENSE"
    OUT_OF_AREA = "OUT_OF_AREA"
