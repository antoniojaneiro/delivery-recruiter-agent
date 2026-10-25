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
    STALLED = "STALLED"


class Status(StrEnum):
    OK = "ok"
    FOLLOW_UP = "follow_up"
    CONFIRM = "confirm"
    REVIEW = "review"


class EventType(StrEnum):
    OFF_TOPIC = "off_topic"
    HUMAN_REQUESTED = "human_requested"
    WITHDRAWN = "withdrawn"
    REMINDER_SENT = "reminder_sent"
    RESUMED = "resumed"
    CONSENT_GIVEN = "consent_given"
    CONSENT_DECLINED = "consent_declined"
    FIELD_ACCEPTED = "field_accepted"
    FOLLOW_UP = "follow_up"
    REVIEW = "review"
    MODEL_FAILURE = "model_failure"


class CityMatchStatus(StrEnum):
    MATCH = "match"
    CONFIRM = "confirm"
    OUT_OF_AREA = "out_of_area"
