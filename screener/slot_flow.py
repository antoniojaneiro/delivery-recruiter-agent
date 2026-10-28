"""Offering and booking a call slot when a candidate qualifies (D7, D8, D48). The slots table is the
single source of truth for a booking: the screening only remembers which slots are on offer."""
from dataclasses import dataclass, replace
from datetime import datetime

from screener import conversation
from screener.conversation import RETRY_ONCE, SKIP, Turn
from screener.client import Client
from screener.consent import is_stop_request
from screener.model import Outcome
from screener.recruiter_rules import can_schedule
from screener.directive import LATER, Directive, Kind
from screener.phrasing import fixed, slot_cancelled_message, slot_label, slot_scheduled_message
from screener.screening import Screening
from screener.slot_choice import NONE, read_slot_choice
from screener.store import Booking, ConflictError, InputError, Store

MAX_UNCLEAR_PICKS = 3  # re-offers of the same list before they are told to write again later


def after_close(store: Store, client: Client, screening: Screening, candidate_id: str, directive: Directive | None,
                now: datetime) -> Directive | None:
    """When the chat closes as QUALIFIED: confirm an existing booking, or offer the next free slots."""
    if directive is None or directive.kind != Kind.CLOSE or directive.outcome != Outcome.QUALIFIED:
        return directive
    if screening.spec.pack.slots is None:
        return directive  # this client does not book calls
    booking = store.booking_of(candidate_id)
    if booking:
        return Directive(Kind.ALREADY_BOOKED, label=slot_label(booking.starts_at, screening.language))
    # Someone who left without booking gets the free times again when they write: no time was ever promised
    return _offer(store, client, screening, now, "first") or _give_up(screening)


def handle_pick(store: Store, client: Client, screening: Screening, candidate_id: str, message: str,
                now: datetime) -> Directive:
    """The candidate's reply to the numbered list. Read in plain code; nothing is sent to the model."""
    if is_stop_request(message):  # a withdrawal is a withdrawal, whatever question was open
        return screening.apply_stop_request()
    record = store.get(candidate_id)
    if record is None or not can_schedule(record):  # a recruiter closed their case since the times were offered
        screening.resolve_slots()
        return replace(screening.close_directive(), repeat=True)
    if held := _already_booked(store, screening, candidate_id):  # a retry after a turn that booked but was never saved
        return held
    offered = screening.slot_offer
    choice = read_slot_choice(message, len(offered))
    if choice is NONE:
        return _give_up(screening, later=True)
    if choice is None:
        if screening.note_unclear_pick() > MAX_UNCLEAR_PICKS:
            return _give_up(screening, later=True)
        return _offer(store, client, screening, now, "unclear") or _give_up(screening)
    return _take(store, client, screening, candidate_id, offered[choice - 1], now)


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
        raise InputError("not_schedulable", "only a candidate the agent qualified, and no recruiter has closed, gets a call")
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
        store.cancel_slot(call.slot_id, by, now.astimezone())
        notify_cancelled(store, client, call.candidate_id, now)
        released += 1
    return Resolved(moved, released)


def country_in(client: Client, values: dict) -> str | None:
    """The country of the place in a candidate's answers, which decides the clock and the recruiters they can be given."""
    area = client.spec.area_field
    return client.calendar.country_of.get(values.get(area)) if client.calendar and area else None


def may_choose_time(store: Store, client: Client, candidate_id: str) -> bool:
    """The one question every way of choosing a time asks (the chat's picker, the service's list of times, the reminder
    job): a candidate the agent qualified and no recruiter has closed, with no call yet, at a client that books calls."""
    record = store.get(candidate_id)
    return bool(record and client.calendar and client.spec.pack.slots and can_schedule(record)
                and store.booking_of(candidate_id) is None)


def country_of(store: Store, client: Client, candidate_id: str) -> str | None:
    record = store.get(candidate_id)
    return country_in(client, record.extracted) if record else None


def pick_slot(store: Store, client: Client, screening: Screening, candidate_id: str, slot_id: int,
              now: datetime) -> tuple[str, Directive]:
    """The candidate chose a time in the picker instead of typing a number: the same booking and the same answers.
    Returns what the transcript shows they chose, and what the agent says."""
    wanted = store.slot(slot_id)
    chosen = slot_label(wanted.starts_at, screening.language) if wanted else ""
    return chosen, _already_booked(store, screening, candidate_id) or _take(store, client, screening, candidate_id, slot_id, now)


def _already_booked(store: Store, screening: Screening, candidate_id: str) -> Directive | None:
    held = store.booking_of(candidate_id)
    if held:
        screening.resolve_slots()
        return Directive(Kind.ALREADY_BOOKED, label=slot_label(held.starts_at, screening.language))
    return None


def _take(store: Store, client: Client, screening: Screening, candidate_id: str, slot_id: int, now: datetime) -> Directive:
    """The one place a candidate's chosen time is booked, by number or by the picker: only a time in their own country, and
    a time that went meanwhile gets a fresh offer."""
    wanted = store.slot(slot_id)
    booking = (store.book_slot(slot_id, candidate_id, now, must_exist=True)
               if wanted and wanted.country == country_in(client, screening.values) else None)
    if booking is None:
        return _offer(store, client, screening, now, "taken") or _give_up(screening)
    screening.resolve_slots()
    return Directive(Kind.SLOT_BOOKED, label=slot_label(booking.starts_at, screening.language))


def notify_cancelled(store: Store, client: Client, candidate_id: str, now: datetime) -> bool:
    """Queues the fixed 'your call is no longer available' message for a candidate whose booked time was taken away,
    followed by the free times so they can pick again (or, with none free, that they can write to book later).
    False when there is nobody to tell (erased) or the record changed meanwhile."""
    if store.get(candidate_id) is None:
        return False

    def work(screening: Screening) -> Turn:
        screening.reopen_slots()
        offer = _offer(store, client, screening, now, "reminder")
        if offer is None:
            screening.resolve_slots()
        text = slot_cancelled_message(client.spec, screening.language)
        more = fixed(client.spec, offer, screening.language) if offer else client.spec.pack.pick(
            client.spec.pack.slots.later, screening.language)
        text = f"{text}\n{more}" if offer else f"{text} {more}"
        return Turn(True, messages=[("agent", text)], outbox=[text])

    return conversation.run(store, client, candidate_id, now, work, on_conflict=SKIP, default=False)


def on_idle(store: Store, client: Client, screening: Screening, now: datetime) -> tuple[str, Directive]:
    """24 hours without an answer to the slot list: remind once with the free slots, then give up (D58)."""
    if screening.reminder_sent:
        return "gave_up_offer", _give_up(screening, later=True)
    screening.send_reminder()
    return "reminder", _offer(store, client, screening, now, "reminder") or _give_up(screening)


def _offer(store: Store, client: Client, screening: Screening, now: datetime, reason: str) -> Directive | None:
    country = country_in(client, screening.values)
    free = store.free_slots(country, now, client.calendar.offer_size) if country else []
    if not free:
        return None
    previous = screening.slot_offer
    ids = [slot.id for slot in free]
    if reason == "unclear" and previous and ids != previous:
        reason = "taken"  # some of the earlier options went in the meantime
    screening.offer_slots(ids)
    return Directive(Kind.OFFER_SLOTS, options=[slot_label(s.starts_at, screening.language) for s in free],
                     reason=reason)


def _give_up(screening: Screening, later: bool = False) -> Directive:
    """No slot to offer (`later` False: no time is free), or they took none (`later`): either way they are told to
    write again to book, and nothing is promised."""
    screening.resolve_slots()
    directive = screening.close_directive()
    return replace(directive, reason=LATER) if later else directive
