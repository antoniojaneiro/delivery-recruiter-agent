"""D48: which call slots were offered to a qualified candidate, and whether the offer is over."""
from sazon.model import EventType, Outcome


class SlotOffer:
    """Part of Screening; uses its `_slot_offer`, `_slots_done`, `_unclear_picks`, `events` and `decide`."""

    @property
    def slot_offer(self) -> list[int]:
        return list(self._slot_offer)

    @property
    def slots_resolved(self) -> bool:
        return self._slots_done

    @property
    def awaiting_slot_choice(self) -> bool:
        return bool(self._slot_offer) and not self._slots_done and self.decide().outcome == Outcome.QUALIFIED

    def offer_slots(self, slot_ids: list[int]) -> None:
        self._slot_offer = list(slot_ids)
        self.events.append((EventType.SLOTS_OFFERED, ",".join(str(i) for i in slot_ids)))

    def note_unclear_pick(self) -> int:
        """Counts a reply to the slot list that could not be read; returns how many so far."""
        self._unclear_picks += 1
        return self._unclear_picks

    def resolve_slots(self) -> None:
        """The offer is over: booked, declined, or nothing to offer."""
        self._slot_offer = []
        self._slots_done = True
