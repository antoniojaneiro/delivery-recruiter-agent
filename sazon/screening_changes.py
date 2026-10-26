"""D54: a changed answer is confirmed with the candidate before it replaces the saved one."""
from dataclasses import replace
from datetime import date

from sazon import validators
from sazon.model import EventType, Field, Status
from sazon.phrasing import Directive, Kind, describe_value


class ChangeConfirmation:
    """Part of Screening; uses its `values`, `events`, `language`, `submit` and `_directive_now`."""

    @property
    def awaiting_change(self) -> bool:
        return self._pending_change is not None

    def drop_change(self) -> None:
        self._pending_change = None

    def resolve_change(self, yes: bool, today: date) -> Directive:
        """The candidate's yes or no to "Antes me dijiste X. ¿Lo cambio a Y?" (D54)."""
        field, candidate, _, _ = self._pending_change
        self._pending_change = None
        notice = "kept"
        if yes:
            self.events.append((EventType.FIELD_CHANGED, str(field)))
            result = self.submit(field, candidate, today)  # the usual flows (typo, outside the area, no license) still apply
            notice = "changed" if result.status == Status.OK else None  # else another question follows
        directive = self._directive_now(None)
        return replace(directive, notice=notice) if directive.kind != Kind.CLOSE else directive

    def _consider_change(self, field: Field, candidate: object, today: date) -> None:
        if self._pending_change is not None:
            return  # one question at a time
        old = self.values[field]
        if field == self.spec.area_field:
            if not isinstance(candidate, str):
                return
            match = validators.match_city(candidate, self.areas, self.spec.place_qualifiers)
            if match.city == old:
                return  # the same city, however it is spelled (an outside-the-area city has no match)
            shown = match.city or " ".join(candidate.split())[:40]
        else:
            result = self._validate(field, candidate, today)
            if not result.ok or self.spec.field(field).same(old, result.value):
                return
            shown = result.value
        self._pending_change = (field, candidate, describe_value(self.spec, field, old, self.language),
                                describe_value(self.spec, field, shown, self.language))
