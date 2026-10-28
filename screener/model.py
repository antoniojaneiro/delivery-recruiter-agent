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
    CV_UPLOADED = "cv_uploaded"
    CV_PREFILLED = "cv_prefilled"
    CV_SKIPPED = "cv_skipped"
    CV_UNREADABLE = "cv_unreadable"


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


# The recruiter's steps in order; a later status means the earlier steps were reached too (D88).
RECRUITER_STEPS = (RecruiterStatus.CONTACTED, RecruiterStatus.INTERVIEW_SCHEDULED, RecruiterStatus.HIRED)
# The statuses with which a recruiter has closed a case: hired, or out of the process.
CLOSED_BY_RECRUITER = (RecruiterStatus.HIRED, RecruiterStatus.REJECTED, RecruiterStatus.UNREACHABLE)


def reached_by(step: RecruiterStatus) -> tuple[RecruiterStatus, ...]:
    """The statuses that mean this step was reached: itself and every later step."""
    return RECRUITER_STEPS[RECRUITER_STEPS.index(step):]


class Language(StrEnum):
    ES = "es"
    EN = "en"
