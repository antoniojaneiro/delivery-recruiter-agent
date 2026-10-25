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


class Outcome(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    QUALIFIED = "QUALIFIED"
    DISQUALIFIED = "DISQUALIFIED"
    ENDED_OFF_TOPIC = "ENDED_OFF_TOPIC"
    WITHDRAWN = "WITHDRAWN"


class Status(StrEnum):
    OK = "ok"
    FOLLOW_UP = "follow_up"
    CONFIRM = "confirm"
    REVIEW = "review"


class EventType(StrEnum):
    OFF_TOPIC = "off_topic"
    HUMAN_REQUESTED = "human_requested"
    WITHDRAWN = "withdrawn"


class CityMatchStatus(StrEnum):
    MATCH = "match"
    CONFIRM = "confirm"
    OUT_OF_AREA = "out_of_area"
