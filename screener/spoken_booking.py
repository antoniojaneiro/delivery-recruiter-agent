"""Booking a call by voice (D93): which day, then which time. A day or time that is free is taken; one that is not gets the
closest offered and a yes books it. Read in plain code (spoken_when.py); nothing is sent to the model. The dialogue's state
lives in the screening (`voice_booking`)."""
from datetime import date, datetime, timedelta

from screener.channel import VOICE
from screener.client import Client
from screener.consent import is_stop_request, read_consent
from screener.directive import Directive, Kind
from screener.phrasing import spoken_day, spoken_label, spoken_time
from screener.recruiter_rules import can_schedule
from screener.screening import Screening
from screener.slot_choice import NONE, read_slot_choice
from screener.slot_offers import MAX_UNCLEAR_PICKS, already_booked, book, case_closed, country_in, give_up
from screener.spoken_when import Wish, nearest_day, nearest_time, read_day, read_time
from screener.store import Store

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


def ask_day(store: Store, client: Client, screening: Screening, now: datetime) -> Directive:
    country = country_in(client, screening.values)
    if not country or not _bookable_days(store, client, country, now):
        return give_up(screening)  # nothing to book: they write again later
    screening.set_voice_booking(stage="day")
    return _say("ask_day")


def _ask_time(screening: Screening, day: date) -> Directive:
    screening.set_voice_booking(stage="time", day=day.isoformat())
    return _say("ask_time", spoken_day(day, screening.language))


def _unclear(screening: Screening, state: dict, reason: str, label: str | None = None) -> Directive:
    """An answer that could not be read: ask again, and after a few tell them to write when they want to book."""
    if state["unclear"] + 1 > MAX_UNCLEAR_PICKS:
        return give_up(screening, later=True)
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
    booking = book(store, client, screening, candidate_id, slot_id, now)
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
    if held := already_booked(store, screening, candidate_id, VOICE):
        return held
    record = store.get(candidate_id)
    if record is None or not can_schedule(record):
        return case_closed(screening)
    state = screening.voice_booking
    if state is None:
        return ask_day(store, client, screening, now)
    country = country_in(client, screening.values)
    days = _bookable_days(store, client, country, now) if country else []
    if not days:
        return give_up(screening)
    language, today, stage = screening.language, client.calendar.today(country, now), state["stage"]
    if stage in ("day", "time") and read_slot_choice(message, 0) is NONE:
        return give_up(screening, later=True)
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
                    or ask_day(store, client, screening, now))
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
    return _propose_time(store, screening, country, day, wish, now) or ask_day(store, client, screening, now)
