"""What recruiters do to booked calls (D8, D84, D86): book or move one, make a time for a candidate, deal with the calls of a
recruiter who leaves or changes their hours, tell a candidate their call is gone. The candidate's chat is told in a fixed text."""
from dataclasses import dataclass
from datetime import date, datetime

from screener import conversation
from screener.conversation import RETRY_ONCE, SKIP, Turn
from screener.client import Client
from screener.phrasing import fixed, slot_cancelled_message, slot_label, slot_scheduled_message
from screener.recruiter_rules import can_schedule
from screener.screening import Screening
from screener.slot_offers import country_in, offer
from screener.store import Booking, ConflictError, InputError, Store

@dataclass(frozen=True)
class Scheduled:
    booking: Booking
    before: Booking | None  # the call they had, when this moved it
    told: bool  # the candidate's chat got the fixed notice (False: it could not be saved, so tell them yourself)


def schedule_by_recruiter(store: Store, client: Client, candidate_id: str, slot_id: int, recruiter: str,
                          now: datetime) -> Scheduled:
    """A recruiter books or moves a candidate's call (the calendar). The booking is one atomic step in the store, and
    only a time in the candidate's own country is accepted (D8). Then the chat is told in a fixed text, in the language
    of the chat, and any open offer of times is closed, so a late "2" gets the booked time and the reminder job does
    not ask them to pick one. Raises InputError when the booking is refused; then nothing is sent."""
    if client.spec.pack.slots is None or client.calendar is None:
        raise InputError("no_calendar", "this client does not book calls")
    record = store.get(candidate_id)
    if record is None:
        raise LookupError(f"no candidate {candidate_id}")
    if not can_schedule(record):
        raise InputError("not_schedulable", "only a candidate shown as qualified or with an interview gets a call")
    booking, before = store.move_booking(candidate_id, slot_id, recruiter, now.astimezone(),
                                         country=country_in(client, record.extracted))
    if before is not None and before.slot_id == booking.slot_id:
        return Scheduled(booking, before, True)  # nothing changed, so there is nothing to tell

    def work(screening: Screening) -> Turn:
        screening.resolve_slots()
        text = slot_scheduled_message(client.spec, screening.language, slot_label(booking.starts_at, screening.language),
                                      moved=before is not None)
        return Turn(True, messages=[("agent", text)], outbox=[text])

    try:
        told = conversation.run(store, client, candidate_id, now, work, on_conflict=RETRY_ONCE, default=False)
    except ConflictError:  # the booking stands; only the notice could not be saved (the candidate wrote, or was erased)
        told = False
    return Scheduled(booking, before, bool(told))


@dataclass(frozen=True)
class Resolved:
    moved: int  # calls given to another recruiter free at the same time
    released: int  # calls with nobody else free: the candidate was told and can pick again


def resolve_calls(store: Store, client: Client, calls, by: str, now: datetime) -> Resolved:
    """What to do with booked calls whose recruiter can no longer take them (a day off, a new week, leaving): another
    recruiter free at the same time takes it over and the candidate hears nothing; otherwise the call is released and the
    candidate is told and shown the free times."""
    moved = released = 0
    for call in calls:
        if store.reassign_call(call.slot_id, now.astimezone()) is not None:
            moved += 1
            continue
        notify_cancelled(store, client, call.candidate_id, now)  # told first: a failure leaves the call booked, so a repeat finds it
        store.cancel_slot(call.slot_id, by, now.astimezone())
        released += 1
    return Resolved(moved, released)


def schedule_new_time(store: Store, client: Client, candidate_id: str, country: str, starts_at: datetime, owner: str,
                      recruiter: str, now: datetime) -> Scheduled:
    """A recruiter makes a time for a candidate (the owner's, in the candidate's own country) and books it in one go.
    A booking that is refused leaves no new time behind, and so does one the least busy recruiter took instead."""
    slot_id = store.add_slot(country, starts_at, owner, recruiter, now.astimezone())
    try:
        done = schedule_by_recruiter(store, client, candidate_id, slot_id, recruiter, now)
    except Exception:
        store.cancel_slot(slot_id, recruiter, now.astimezone())
        raise
    if done.booking.slot_id != slot_id:
        store.cancel_slot(slot_id, recruiter, now.astimezone())
    return done


def remove_recruiter(store: Store, client: Client, email: str, by: str, now: datetime) -> Resolved:
    """A recruiter leaves (D86): the account goes first, so nobody can book their times again, and each call they held goes
    to another recruiter free then or is released with the candidate told (D84). Not one transaction (telling a candidate
    is not part of the database), but it can be run again: a failure part-way is finished by the same call, because the
    calls are found by the email, not by the account."""
    calls = store.future_calls(email, now.astimezone())
    if not store.remove_recruiter(email, by, now) and not calls:
        raise LookupError(f"no recruiter {email}")
    return resolve_calls(store, client, calls, by, now)


def save_week(store: Store, client: Client, email: str, picks: list, by: str, now: datetime) -> Resolved:
    """A recruiter's new weekly hours; the calls that no longer fit are dealt with (D84)."""
    return resolve_calls(store, client, store.set_weekly(email, picks, by, now), by, now)


def reset_week(store: Store, client: Client, email: str, by: str, now: datetime) -> Resolved:
    return resolve_calls(store, client, store.reset_weekly(email, by, now), by, now)


def set_day_off(store: Store, client: Client, email: str, day: date, off: bool, by: str, now: datetime) -> Resolved:
    return resolve_calls(store, client, store.set_day_off(email, day, off, by, now), by, now)


def notify_cancelled(store: Store, client: Client, candidate_id: str, now: datetime) -> bool:
    """Queues the fixed 'your call is no longer available' message for a candidate whose booked time was taken away,
    followed by the free times so they can pick again (or, with none free, that they can write to book later).
    False when there is nobody to tell (erased) or the record changed meanwhile."""
    record = store.get(candidate_id)
    if record is None or not can_schedule(record):  # erased, or a recruiter has closed their case: nothing to offer
        return False

    def work(screening: Screening) -> Turn:
        screening.reopen_slots()
        times = offer(store, client, screening, now, "reminder")
        if times is None:
            screening.resolve_slots()
        text = slot_cancelled_message(client.spec, screening.language)
        more = fixed(client.spec, times, screening.language) if times else client.spec.pack.pick(
            client.spec.pack.slots.later, screening.language)
        text = f"{text}\n{more}" if times else f"{text} {more}"
        return Turn(True, messages=[("agent", text)], outbox=[text])

    return conversation.run(store, client, candidate_id, now, work, on_conflict=SKIP, default=False)
