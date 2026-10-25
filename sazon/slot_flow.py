"""Offering and booking a call slot when a candidate qualifies (D7, D8, D48). The slots table is the
single source of truth for a booking: the screening only remembers which slots are on offer."""
from datetime import datetime

from sazon import config
from sazon.model import Field, Outcome
from sazon.phrasing import Directive, Kind, slot_label
from sazon.screening import Screening
from sazon.slot_choice import NONE, read_slot_choice
from sazon.store import Store

OFFER_SIZE = 3


def after_close(store: Store, screening: Screening, candidate_id: str, directive: Directive | None,
                now: datetime) -> Directive | None:
    """When the chat closes as QUALIFIED: confirm an existing booking, or offer the next free slots."""
    if directive is None or directive.kind != Kind.CLOSE or directive.outcome != Outcome.QUALIFIED:
        return directive
    booking = store.booking_of(candidate_id)
    if booking:
        return Directive(Kind.ALREADY_BOOKED, label=slot_label(booking.starts_at, screening.language))
    if screening.slots_resolved:
        return directive
    return _offer(store, screening, now, "first") or _give_up(screening)


def handle_pick(store: Store, screening: Screening, candidate_id: str, message: str,
                now: datetime) -> Directive:
    """The candidate's reply to the numbered list. Read in plain code; nothing is sent to the model."""
    held = store.booking_of(candidate_id)
    if held:  # a retry after a turn that booked but was never saved
        screening.resolve_slots()
        return Directive(Kind.ALREADY_BOOKED, label=slot_label(held.starts_at, screening.language))
    offered = screening.slot_offer
    choice = read_slot_choice(message, len(offered))
    if choice is NONE:
        return _give_up(screening)
    if choice is None:
        return _offer(store, screening, now, "unclear") or _give_up(screening)
    booking = store.book_slot(offered[choice - 1], candidate_id, now)
    if booking is None:
        return _offer(store, screening, now, "taken") or _give_up(screening)
    screening.resolve_slots()
    return Directive(Kind.SLOT_BOOKED, label=slot_label(booking.starts_at, screening.language))


def _offer(store: Store, screening: Screening, now: datetime, reason: str) -> Directive | None:
    country = config.COUNTRY_OF.get(screening.values.get(Field.CITY))
    free = store.free_slots(country, now, OFFER_SIZE) if country else []
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
