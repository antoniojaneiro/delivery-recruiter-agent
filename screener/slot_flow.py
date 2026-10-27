"""Offering and booking a call slot when a candidate qualifies (D7, D8, D48). The slots table is the
single source of truth for a booking: the screening only remembers which slots are on offer."""
from datetime import datetime

from screener import conversation
from screener.conversation import SKIP, Turn
from screener.client import Client
from screener.consent import is_stop_request
from screener.model import Outcome
from screener.phrasing import Directive, Kind, slot_cancelled_message, slot_label
from screener.screening import Screening
from screener.slot_choice import NONE, read_slot_choice
from screener.store import Store

MAX_UNCLEAR_PICKS = 3  # re-offers of the same list before the 48-hour promise applies


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
    if screening.slots_resolved:
        return directive
    return _offer(store, client, screening, now, "first") or _give_up(screening)


def handle_pick(store: Store, client: Client, screening: Screening, candidate_id: str, message: str,
                now: datetime) -> Directive:
    """The candidate's reply to the numbered list. Read in plain code; nothing is sent to the model."""
    if is_stop_request(message):  # a withdrawal is a withdrawal, whatever question was open
        return screening.apply_stop_request()
    held = store.booking_of(candidate_id)
    if held:  # a retry after a turn that booked but was never saved
        screening.resolve_slots()
        return Directive(Kind.ALREADY_BOOKED, label=slot_label(held.starts_at, screening.language))
    offered = screening.slot_offer
    choice = read_slot_choice(message, len(offered))
    if choice is NONE:
        return _give_up(screening)
    if choice is None:
        if screening.note_unclear_pick() > MAX_UNCLEAR_PICKS:
            return _give_up(screening)
        return _offer(store, client, screening, now, "unclear") or _give_up(screening)
    booking = store.book_slot(offered[choice - 1], candidate_id, now, must_exist=True)
    if booking is None:
        return _offer(store, client, screening, now, "taken") or _give_up(screening)
    screening.resolve_slots()
    return Directive(Kind.SLOT_BOOKED, label=slot_label(booking.starts_at, screening.language))


def notify_cancelled(store: Store, client: Client, candidate_id: str, now: datetime) -> bool:
    """Queues the fixed 'your call was cancelled' message for a candidate whose booked slot a recruiter cancelled.
    False when there is nobody to tell (erased) or the record changed meanwhile."""
    if store.get(candidate_id) is None:
        return False

    def work(screening: Screening) -> Turn:
        text = slot_cancelled_message(client.spec, screening.language)
        return Turn(True, messages=[("agent", text)], outbox=[text])

    return conversation.run(store, client, candidate_id, now, work, on_conflict=SKIP, default=False)


def on_idle(store: Store, client: Client, screening: Screening, now: datetime) -> tuple[str, Directive]:
    """24 hours without an answer to the slot list: remind once with the free slots, then give up (D58)."""
    if screening.reminder_sent:
        return "gave_up_offer", _give_up(screening)
    screening.send_reminder()
    return "reminder", _offer(store, client, screening, now, "reminder") or _give_up(screening)


def _offer(store: Store, client: Client, screening: Screening, now: datetime, reason: str) -> Directive | None:
    calendar, area = client.calendar, screening.spec.area_field
    country = calendar.country_of.get(screening.values.get(area)) if calendar and area else None
    free = store.free_slots(country, now, calendar.offer_size) if country else []
    if not free:
        return None
    previous = screening.slot_offer
    ids = [slot.id for slot in free]
    if reason == "unclear" and previous and ids != previous:
        reason = "taken"  # some of the earlier options went in the meantime
    screening.offer_slots(ids)
    return Directive(Kind.OFFER_SLOTS, options=[slot_label(s.starts_at, screening.language) for s in free],
                     reason=reason)


def _give_up(screening: Screening) -> Directive:
    """No slot to offer, or none suits: the 48-hour promise, and a recruiter takes over."""
    screening.resolve_slots()
    return screening.close_directive()
