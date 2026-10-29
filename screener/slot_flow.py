"""Offering and booking a call slot when a candidate qualifies (D7, D8, D48). The slots table is the
single source of truth for a booking: the screening only remembers which slots are on offer."""
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

from screener import conversation
from screener.channel import TEXT, Channel, effective
from screener.conversation import RETRY_ONCE, SKIP, Turn
from screener.client import Client
from screener.consent import is_stop_request, read_consent
from screener.model import Outcome
from screener.recruiter_rules import Verdict, can_schedule, closed_by_recruiter, may_choose
from screener.directive import LATER, Directive, Kind
from screener.phrasing import (fixed, slot_cancelled_message, slot_label, slot_scheduled_message, spoken_day, spoken_label,
                               spoken_time)
from screener.screening import Screening
from screener.slot_choice import NONE, read_slot_choice
from screener.spoken_when import Wish, nearest_day, nearest_time, read_day, read_time
from screener.store import Booking, ConflictError, InputError, Store

MAX_UNCLEAR_PICKS = 3  # re-offers of the same list before they are told to write again later


def after_close(store: Store, client: Client, screening: Screening, candidate_id: str, directive: Directive | None,
                now: datetime, channel: Channel = TEXT) -> Directive | None:
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
        return _closed_by_recruiter(screening)  # no offer: a recruiter has the case
    if channel.offer == "spoken":
        return _ask_day(store, client, screening, now)
    # Someone who left without booking gets the free times again when they write: no time was ever promised
    return _offer(store, client, screening, now, "first") or _give_up(screening)


def handle_pick(store: Store, client: Client, screening: Screening, candidate_id: str, message: str,
                now: datetime) -> Directive:
    """The candidate's reply to the numbered list. Read in plain code; nothing is sent to the model."""
    if is_stop_request(message):  # a withdrawal is a withdrawal, whatever question was open
        return screening.apply_stop_request()
    record = store.get(candidate_id)
    if record is None or not can_schedule(record):  # a recruiter closed their case since the times were offered
        return _closed_by_recruiter(screening)
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


def country_in(client: Client, values: dict) -> str | None:
    """The country of the place in a candidate's answers, which decides the clock and the recruiters they can be given."""
    area = client.spec.area_field
    return client.calendar.country_of.get(values.get(area)) if client.calendar and area else None


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
    return chosen, _already_booked(store, screening, candidate_id) or _take(store, client, screening, candidate_id, slot_id, now)


def _closed_by_recruiter(screening: Screening) -> Directive:
    """A recruiter closed this case (hired, rejected, unreachable): the offer of times ends, nothing new is offered, and
    the candidate is told, shortly, that the chat is closed and a recruiter has their case."""
    screening.resolve_slots()
    return Directive(Kind.CLOSE, repeat=True)


def _already_booked(store: Store, screening: Screening, candidate_id: str, spoken: bool = False) -> Directive | None:
    held = store.booking_of(candidate_id)
    if held:
        screening.resolve_slots()
        return Directive(Kind.ALREADY_BOOKED, label=(spoken_label if spoken else slot_label)(held.starts_at, screening.language))
    return None


def _take(store: Store, client: Client, screening: Screening, candidate_id: str, slot_id: int, now: datetime) -> Directive:
    """The one place a candidate's chosen time is booked, by number or by the picker: only a time in their own country, and
    a time that went meanwhile gets a fresh offer."""
    booking = _book(store, client, screening, candidate_id, slot_id, now)
    if booking is None:
        return _offer(store, client, screening, now, "taken") or _give_up(screening)
    screening.resolve_slots()
    return Directive(Kind.SLOT_BOOKED, label=slot_label(booking.starts_at, screening.language))


def _book(store: Store, client: Client, screening: Screening, candidate_id: str, slot_id: int, now: datetime):
    """Books the time for the candidate if it is in their own country and still free; None otherwise."""
    wanted = store.slot(slot_id)
    return (store.book_slot(slot_id, candidate_id, now, must_exist=True)
            if wanted and wanted.country == country_in(client, screening.values) else None)


# -- booking by voice (D93): which day, then which time ----------------------------------------------------------------

def _say(reason: str, label: str | None = None) -> Directive:
    return Directive(Kind.VOICE_BOOKING, reason=reason, label=label)


def _bookable_days(store: Store, client: Client, country: str, now: datetime) -> list[date]:
    """The days a candidate may book that still have a free time, soonest first."""
    first = client.calendar.today(country, now).replace(day=1)
    days: set[date] = set()
    for _ in range(3):  # four weeks reach at most the next month
        days |= set(store.free_days(country, first, now))
        first = (first + timedelta(days=32)).replace(day=1)
    return sorted(days)


def _ask_day(store: Store, client: Client, screening: Screening, now: datetime) -> Directive:
    country = country_in(client, screening.values)
    if not country or not _bookable_days(store, client, country, now):
        return _give_up(screening)  # nothing to book: they write again later
    screening.set_voice_booking(stage="day")
    return _say("ask_day")


def _ask_time(screening: Screening, day: date) -> Directive:
    screening.set_voice_booking(stage="time", day=day.isoformat())
    return _say("ask_time", spoken_day(day, screening.language))


def _unclear(screening: Screening, state: dict, reason: str, label: str | None = None) -> Directive:
    """An answer that could not be read: ask again, and after a few tell them to write when they want to book."""
    if state["unclear"] + 1 > MAX_UNCLEAR_PICKS:
        return _give_up(screening, later=True)
    screening.set_voice_booking(**{**state, "unclear": state["unclear"] + 1})
    return _say(reason, label)


def _propose_time(store: Store, screening: Screening, country: str, day: date, wish: Wish,
                  now: datetime) -> Directive | None:
    """The closest free time of that day to what was asked, proposed (None when the day has nothing left)."""
    free = store.free_slots_on(country, day, now)
    by_minutes = {s.starts_at.hour * 60 + s.starts_at.minute: s for s in free}
    chosen = nearest_time(list(by_minutes), wish)
    if chosen is None:
        return None
    screening.set_voice_booking(stage="confirm_time", day=day.isoformat(), slot=by_minutes[chosen].id)
    return _say("propose_time", spoken_time(chosen, screening.language))


def _book_spoken(store: Store, client: Client, screening: Screening, candidate_id: str, slot_id: int, now: datetime):
    booking = _book(store, client, screening, candidate_id, slot_id, now)
    if booking is None:
        return None
    screening.resolve_slots()
    return Directive(Kind.SLOT_BOOKED, label=spoken_label(booking.starts_at, screening.language))


def handle_spoken(store: Store, client: Client, screening: Screening, candidate_id: str, message: str,
                  now: datetime) -> Directive:
    """One turn of the spoken booking: ask the day, then the time; a day or time that is free is taken, one that is not gets
    the closest offered and a yes books it. Read in plain code; nothing is sent to the model."""
    if is_stop_request(message):
        return screening.apply_stop_request()
    if held := _already_booked(store, screening, candidate_id, spoken=True):
        return held
    record = store.get(candidate_id)
    if record is None or not can_schedule(record):
        return _closed_by_recruiter(screening)
    state = screening.voice_booking
    if state is None:
        return _ask_day(store, client, screening, now)
    country = country_in(client, screening.values)
    days = _bookable_days(store, client, country, now) if country else []
    if not days:
        return _give_up(screening)
    language, today, stage = screening.language, client.calendar.today(country, now), state["stage"]
    if stage in ("day", "time") and read_slot_choice(message, 0) is NONE:
        return _give_up(screening, later=True)
    if stage == "confirm_day":
        answer = read_consent(message).answer
        if answer is True:
            return _ask_time(screening, date.fromisoformat(state["day"]))
        if answer is False:
            screening.set_voice_booking(stage="day")
            return _say("other_day")
        if read_day(message, today) is None:
            return _unclear(screening, state, "propose_day", spoken_day(date.fromisoformat(state["day"]), language))
        stage = "day"
    elif stage == "confirm_time":
        answer = read_consent(message).answer
        if answer is True:
            done = _book_spoken(store, client, screening, candidate_id, state["slot"], now)
            if done is not None:
                return done
            taken = store.slot(state["slot"])  # went to someone else meanwhile: the closest of what is left
            wish = Wish(taken.starts_at.hour, taken.starts_at.minute) if taken else Wish(period="morning")
            return (_propose_time(store, screening, country, date.fromisoformat(state["day"]), wish, now)
                    or _ask_day(store, client, screening, now))
        if answer is False:
            screening.set_voice_booking(stage="time", day=state["day"])
            return _say("other_time")
        if read_time(message) is None:
            slot = store.slot(state["slot"])
            label = spoken_time(slot.starts_at.hour * 60 + slot.starts_at.minute, language) if slot else None
            return _unclear(screening, state, "propose_time", label)
        stage = "time"
    if stage == "day":
        day = read_day(message, today)
        if day is None:
            return _unclear(screening, state, "ask_day_again")
        if day in days:
            return _ask_time(screening, day)
        near = nearest_day(days, day)
        screening.set_voice_booking(stage="confirm_day", day=near.isoformat())
        return _say("propose_day", spoken_day(near, language))
    day = date.fromisoformat(state["day"])
    wish = read_time(message)
    if wish is None:
        return _unclear(screening, state, "ask_time_again")
    exact = next((s for s in store.free_slots_on(country, day, now)
                  if wish.minutes is not None and s.starts_at.hour * 60 + s.starts_at.minute == wish.minutes), None)
    if exact is not None:
        done = _book_spoken(store, client, screening, candidate_id, exact.id, now)
        if done is not None:
            return done
    return _propose_time(store, screening, country, day, wish, now) or _ask_day(store, client, screening, now)


def notify_cancelled(store: Store, client: Client, candidate_id: str, now: datetime) -> bool:
    """Queues the fixed 'your call is no longer available' message for a candidate whose booked time was taken away,
    followed by the free times so they can pick again (or, with none free, that they can write to book later).
    False when there is nobody to tell (erased) or the record changed meanwhile."""
    record = store.get(candidate_id)
    if record is None or not can_schedule(record):  # erased, or a recruiter has closed their case: nothing to offer
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
                     reason=reason, buttons=effective(screening.usual_channel, client).offer == "button")


def _give_up(screening: Screening, later: bool = False) -> Directive:
    """No slot to offer (`later` False: no time is free), or they took none (`later`): either way they are told to
    write again to book, and nothing is promised."""
    screening.resolve_slots()
    directive = screening.close_directive()
    return replace(directive, reason=LATER) if later else directive
