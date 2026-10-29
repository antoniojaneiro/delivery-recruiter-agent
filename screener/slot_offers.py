"""Offering and booking a call slot when a candidate qualifies, in writing (D7, D8, D48). The slots table is the single source
of truth for a booking: the screening only remembers which slots are on offer. The helpers that take a time, say a case is
closed or give up are shared with the spoken booking (spoken_booking.py) and the recruiters' workflows (recruiter_calls.py)."""
from dataclasses import replace
from datetime import datetime
from typing import Callable

from screener.channel import TEXT, Channel, effective
from screener.client import Client
from screener.consent import is_stop_request
from screener.directive import LATER, Directive, Kind
from screener.model import Outcome
from screener.phrasing import slot_label
from screener.recruiter_rules import Verdict, can_schedule, closed_by_recruiter, may_choose
from screener.screening import Screening
from screener.slot_choice import NONE, read_slot_choice
from screener.store import Store

MAX_UNCLEAR_PICKS = 3  # re-offers of the same list before they are told to write again later


def after_close(store: Store, client: Client, screening: Screening, candidate_id: str, directive: Directive | None,
                now: datetime, channel: Channel = TEXT,
                ask_day: Callable | None = None) -> Directive | None:
    """When the chat closes as QUALIFIED: confirm an existing booking, or offer the next free slots (by voice: ask which
    day). `channel` is the effective one for this client."""
    if directive is None or directive.kind != Kind.CLOSE or directive.outcome != Outcome.QUALIFIED:
        return directive
    if screening.spec.pack.slots is None:
        return directive  # this client does not book calls
    booking = store.booking_of(candidate_id)
    if booking:
        return Directive(Kind.ALREADY_BOOKED, label=channel.label(booking.starts_at, screening.language))
    record = store.get(candidate_id)
    if record is not None and closed_by_recruiter(record):
        return case_closed(screening)  # no offer: a recruiter has the case
    if channel.offer == "spoken" and ask_day:
        return ask_day(store, client, screening, now)
    # Someone who left without booking gets the free times again when they write: no time was ever promised
    return offer(store, client, screening, now, "first") or give_up(screening)


def handle_pick(store: Store, client: Client, screening: Screening, candidate_id: str, message: str,
                now: datetime) -> Directive:
    """The candidate's reply to the numbered list. Read in plain code; nothing is sent to the model."""
    if is_stop_request(message):  # a withdrawal is a withdrawal, whatever question was open
        return screening.apply_stop_request()
    record = store.get(candidate_id)
    if record is None or not can_schedule(record):  # a recruiter closed their case since the times were offered
        return case_closed(screening)
    if held := already_booked(store, screening, candidate_id):  # a retry after a turn that booked but was never saved
        return held
    offered = screening.slot_offer
    choice = read_slot_choice(message, len(offered))
    if choice is NONE:
        return give_up(screening, later=True)
    if choice is None:
        if screening.note_unclear_pick() > MAX_UNCLEAR_PICKS:
            return give_up(screening, later=True)
        return offer(store, client, screening, now, "unclear") or give_up(screening)
    return take(store, client, screening, candidate_id, offered[choice - 1], now)


def country_in(client: Client, values: dict) -> str | None:
    """The country of the place in a candidate's answers, which decides the clock and the recruiters they can be given."""
    area = client.spec.area_field
    return client.calendar.country_of.get(values.get(area)) if client.calendar and area else None


def choice_verdict(store: Store, client: Client, candidate_id: str) -> Verdict:
    """May this candidate choose a time now, and if not, why (D94)."""
    return may_choose(store.get(candidate_id), books_calls=bool(client.calendar and client.spec.pack.slots),
                      holds_call=store.booking_of(candidate_id) is not None)


def may_choose_time(store: Store, client: Client, candidate_id: str) -> bool:
    """The one question every way of choosing a time asks (the chat's picker, the service's list of times, the reminder job)."""
    return choice_verdict(store, client, candidate_id).allowed


def country_of(store: Store, client: Client, candidate_id: str) -> str | None:
    record = store.get(candidate_id)
    return country_in(client, record.extracted) if record else None


def pick_slot(store: Store, client: Client, screening: Screening, candidate_id: str, slot_id: int,
              now: datetime) -> tuple[str, Directive]:
    """The candidate chose a time in the picker instead of typing a number: the same booking and the same answers.
    Returns what the transcript shows they chose, and what the agent says."""
    wanted = store.slot(slot_id)
    chosen = slot_label(wanted.starts_at, screening.language) if wanted else ""
    return chosen, already_booked(store, screening, candidate_id) or take(store, client, screening, candidate_id, slot_id, now)


def case_closed(screening: Screening) -> Directive:
    """A recruiter closed this case (hired, rejected, unreachable): the offer of times ends, nothing new is offered, and
    the candidate is told, shortly, that the chat is closed and a recruiter has their case."""
    screening.resolve_slots()
    return Directive(Kind.CLOSE, repeat=True)


def already_booked(store: Store, screening: Screening, candidate_id: str, channel: Channel = TEXT) -> Directive | None:
    held = store.booking_of(candidate_id)
    if held:
        screening.resolve_slots()
        return Directive(Kind.ALREADY_BOOKED, label=channel.label(held.starts_at, screening.language))
    return None


def take(store: Store, client: Client, screening: Screening, candidate_id: str, slot_id: int, now: datetime) -> Directive:
    """The one place a candidate's chosen time is booked, by number or by the picker: only a time in their own country, and
    a time that went meanwhile gets a fresh offer."""
    booking = book(store, client, screening, candidate_id, slot_id, now)
    if booking is None:
        return offer(store, client, screening, now, "taken") or give_up(screening)
    screening.resolve_slots()
    return Directive(Kind.SLOT_BOOKED, label=slot_label(booking.starts_at, screening.language))


def book(store: Store, client: Client, screening: Screening, candidate_id: str, slot_id: int, now: datetime):
    """Books the time for the candidate if it is in their own country and still free; None otherwise."""
    wanted = store.slot(slot_id)
    return (store.book_slot(slot_id, candidate_id, now, must_exist=True)
            if wanted and wanted.country == country_in(client, screening.values) else None)


def on_idle(store: Store, client: Client, screening: Screening, now: datetime) -> tuple[str, Directive]:
    """24 hours without an answer to the slot list: remind once with the free slots, then give up (D58)."""
    if screening.reminder_sent:
        return "gave_up_offer", give_up(screening, later=True)
    screening.send_reminder()
    return "reminder", offer(store, client, screening, now, "reminder") or give_up(screening)


def offer(store: Store, client: Client, screening: Screening, now: datetime, reason: str) -> Directive | None:
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
                     reason=reason, buttons=effective(screening.usual_channel, client).offer == "button")


def give_up(screening: Screening, later: bool = False) -> Directive:
    """No slot to offer (`later` False: no time is free), or they took none (`later`): either way they are told to
    write again to book, and nothing is promised."""
    screening.resolve_slots()
    directive = screening.close_directive()
    return replace(directive, reason=LATER) if later else directive

