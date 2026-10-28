"""Where a candidate is in the whole process, and whether they are still in it (D78). The process is the agent's screening
(consent, each answer, qualified, a call when the client books calls) and then the recruiter's steps (contacted,
interview, hired). Pure code over a saved screening, the agent's outcome, the recruiter's status and their history;
the screens only draw it."""
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from screener.model import Language, Outcome, RecruiterStatus
from screener.screening import Screening
from screener.spec import ScreeningSpec

CONSENT, QUALIFIED_STEP, BOOKED_STEP = "consent", "qualified", "booked"
# The recruiter's steps in order, each with the status that means it was reached (a later status means it too).
RECRUITER_STEPS = (RecruiterStatus.CONTACTED, RecruiterStatus.INTERVIEW_SCHEDULED, RecruiterStatus.HIRED)
_RANK = {status: number for number, status in enumerate(RECRUITER_STEPS, start=1)}


class Mark(StrEnum):
    IN_PROCESS = "in_process"  # the next step can still happen
    PAUSED = "paused"  # stalled or blocked: they can come back by writing again
    OUT = "out"  # closed by the agent, withdrawn, rejected or unreachable
    HIRED = "hired"


class StepState(StrEnum):
    DONE = "done"
    CURRENT = "current"  # where an active candidate is now
    STOPPED = "stopped"  # where a candidate who is out stopped
    LEFT = "left"  # still ahead
    SKIPPED = "skipped"  # a recruiter took over before the agent finished this one


@dataclass(frozen=True)
class Step:
    key: str
    label: str
    state: StepState


@dataclass(frozen=True)
class Path:
    mark: Mark
    steps: list[Step]
    why: tuple[str, ...]  # the agent's reasons, for a candidate who is out or paused


_BY_OUTCOME = {
    Outcome.STALLED: Mark.PAUSED, Outcome.BLOCKED: Mark.PAUSED,
    Outcome.DISQUALIFIED: Mark.OUT, Outcome.ENDED_OFF_TOPIC: Mark.OUT, Outcome.WITHDRAWN: Mark.OUT,
}


def mark_of(outcome: str | None, status: RecruiterStatus) -> Mark:
    """A recruiter's status overrules the agent's outcome (D42): contacted or an interview keeps a candidate in the
    process even if the agent closed the chat, and rejected or unreachable ends it. `new` leaves it to the agent.
    A withdrawn candidate is out, though they can resume by writing "continuar" (D56): the mark is read live."""
    status = RecruiterStatus(status)
    if status == RecruiterStatus.HIRED:
        return Mark.HIRED
    if status in (RecruiterStatus.REJECTED, RecruiterStatus.UNREACHABLE):
        return Mark.OUT
    if status in (RecruiterStatus.CONTACTED, RecruiterStatus.INTERVIEW_SCHEDULED):
        return Mark.IN_PROCESS
    return _BY_OUTCOME.get(Outcome(outcome), Mark.IN_PROCESS) if outcome else Mark.IN_PROCESS


def count_marks(records: Iterable) -> dict[Mark, int]:
    counts = {mark: 0 for mark in Mark}
    for record in records:
        counts[mark_of(record.outcome, record.status)] += 1
    return counts


def reached_rank(status: RecruiterStatus, history: Iterable[RecruiterStatus]) -> int:
    """How far into the recruiter's steps the candidate ever got: 0 none, 1 contacted, 2 interview, 3 hired. A later
    rejection does not undo it, and a candidate set straight to hired has passed the steps before it."""
    return max((_RANK.get(RecruiterStatus(s), 0) for s in (*history, status)), default=0)


def path_of(screening: Screening, *, outcome: str | None, status: RecruiterStatus, reasons: list[str], booked: bool,
            history: Iterable[RecruiterStatus], with_calls: bool, spec: ScreeningSpec, language: Language | None,
            labels: dict[str, str]) -> Path:
    """The steps of one candidate, in order, each done, current, stopped, left or skipped. `labels` names the steps that
    are not questions (started, consent, qualified, booked and the recruiter's); a question is named by the client's spec."""
    rank = reached_rank(status, history)
    mark = mark_of(outcome, status)
    agent = [("started", True), (CONSENT, screening.consent is True)]
    agent += [(key, key in screening.values) for key in spec.keys]
    agent += [(QUALIFIED_STEP, outcome == Outcome.QUALIFIED)]
    if with_calls:
        agent += [(BOOKED_STEP, booked)]
    steps = [(key, done, True) for key, done in agent]
    steps += [(RECRUITER_STEPS[i].value, rank > i, False) for i in range(len(RECRUITER_STEPS))]

    def label(key: str) -> str:
        return spec.say(spec.field(key).label, language) if key in spec.keys else labels[key]

    result, marked_pending = [], False
    for key, done, by_agent in steps:
        if done:
            state = StepState.DONE
        elif rank >= 1 and by_agent:
            state = StepState.SKIPPED
        elif marked_pending or mark == Mark.HIRED:
            state = StepState.LEFT
        else:
            marked_pending = True
            state = StepState.STOPPED if mark == Mark.OUT else StepState.CURRENT
        result.append(Step(key, label(key), state))
    why = tuple(spec.reason_text(code, language) for code in reasons) if mark in (Mark.OUT, Mark.PAUSED) else ()
    return Path(mark, result, why)
