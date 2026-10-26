"""What a client defines to use the screening engine (D63): its fields and the rules that end a screening.
Everything here is data and small functions; the engine owns the flow."""
from dataclasses import dataclass
from datetime import date
from operator import eq
from typing import Any, Callable

from sazon.validators import Validation


@dataclass(frozen=True)
class FieldSpec:
    key: str
    validate: Callable[[Any, date], Validation] | None = None  # None: the engine's area matching decides
    same: Callable[[Any, Any], bool] = eq  # compares validated values, so the same answer is never a change
    rejects: Callable[[Any], bool] | None = None  # an answer that ends the screening once the candidate confirms it


@dataclass(frozen=True)
class Rule:
    """A reason that disqualifies a candidate. `applies` reads the screening's saved answers."""
    reason: str
    applies: Callable[[Any], bool]


@dataclass(frozen=True)
class ScreeningSpec:
    fields: tuple[FieldSpec, ...]
    rules: tuple[Rule, ...] = ()
    area_field: str | None = None  # the field matched against the client's service areas

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(f.key for f in self.fields)

    def field(self, key: str) -> FieldSpec:
        for spec in self.fields:
            if spec.key == key:
                return spec
        raise ValueError(f"unknown field: {key}")
