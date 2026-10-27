from enum import StrEnum


CONSENT = "consent"  # the question every screening starts with, before any field of the client's
NO_CONSENT = "NO_CONSENT"  # the one disqualifying reason the engine owns


class Outcome(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    QUALIFIED = "QUALIFIED"
    DISQUALIFIED = "DISQUALIFIED"
    ENDED_OFF_TOPIC = "ENDED_OFF_TOPIC"
    WITHDRAWN = "WITHDRAWN"
    STALLED = "STALLED"
    BLOCKED = "BLOCKED"


class Status(StrEnum):
    OK = "ok"
    FOLLOW_UP = "follow_up"
    CONFIRM = "confirm"
    BLOCKED = "blocked"
    CONFIRM_REJECT = "confirm_reject"


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
    BLOCKED = "blocked"
    MODEL_FAILURE = "model_failure"
    SLOTS_OFFERED = "slots_offered"
    PAY_QUESTION = "pay_question"
    FIELD_CHANGED = "field_changed"


class AreaMatchStatus(StrEnum):
    MATCH = "match"
    CONFIRM = "confirm"
    OUT_OF_AREA = "out_of_area"


class RecruiterStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    HIRED = "hired"
    REJECTED = "rejected"
    UNREACHABLE = "unreachable"


class Language(StrEnum):
    ES = "es"
    EN = "en"
