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
    NEW = "new"  # no recruiter has decided anything: the system derives what is shown (`stage_of`)
    CONTACTED = "contacted"  # the conversation is going
    QUALIFIED = "qualified"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    HIRED = "hired"
    REJECTED = "rejected"
    UNREACHABLE = "unreachable"


# What "Estado" can show, in the order of a candidate's way through (D92); the recruiter's choices are these five.
STAGES = (RecruiterStatus.CONTACTED, RecruiterStatus.QUALIFIED, RecruiterStatus.INTERVIEW_SCHEDULED,
          RecruiterStatus.HIRED, RecruiterStatus.REJECTED)
# The steps only a recruiter takes, in order (D88, D92): hiring. Contacted, qualified and interview scheduled follow from
# what the candidate and the agent did.
RECRUITER_STEPS = (RecruiterStatus.HIRED,)
# The statuses with which a recruiter has closed a case: hired, or out of the process.
CLOSED_BY_RECRUITER = (RecruiterStatus.HIRED, RecruiterStatus.REJECTED, RecruiterStatus.UNREACHABLE)


def reached_by(step: RecruiterStatus) -> tuple[RecruiterStatus, ...]:
    """The statuses that mean this step was reached: itself and every later step."""
    return RECRUITER_STEPS[RECRUITER_STEPS.index(step):]


class Language(StrEnum):
    ES = "es"
    EN = "en"


def stage_of(outcome, status: RecruiterStatus, booked: bool) -> RecruiterStatus:
    """The one word shown as "Estado" (D92): what a recruiter decided, else what the system derives. The agent's outcome and a
    booked call move it on their own (a recruiter who sets the state the system would show leaves it automatic)."""
    status = RecruiterStatus(status)
    if status == RecruiterStatus.UNREACHABLE:
        return RecruiterStatus.REJECTED  # a state of an earlier version, shown as Rejected
    if status == RecruiterStatus.QUALIFIED and booked:
        return RecruiterStatus.INTERVIEW_SCHEDULED  # a recruiter's "qualified" moves on when the call is booked
    if status != RecruiterStatus.NEW:
        return status
    outcome = Outcome(outcome) if outcome else None
    if outcome in (Outcome.DISQUALIFIED, Outcome.ENDED_OFF_TOPIC):
        return RecruiterStatus.REJECTED
    if outcome == Outcome.QUALIFIED:
        return RecruiterStatus.INTERVIEW_SCHEDULED if booked else RecruiterStatus.QUALIFIED
    return RecruiterStatus.CONTACTED
