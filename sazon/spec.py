"""What a client defines to use the screening engine (D63): its fields and the rules that end a screening.
Everything here is data and small functions; the engine owns the flow."""
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from operator import eq
from typing import Any, Callable

from sazon.extraction import build_model
from sazon.validators import Validation

MISSING = object()  # what a field's reader returns when the message says nothing about it


def read_attribute(name: str, empty_is_missing: bool = False) -> Callable[[Any, date, Any], object]:
    """A reader for a field that is one attribute of the model's reply."""
    def read(reply, today, base):
        value = getattr(reply, name)
        return MISSING if value is None or (empty_is_missing and not value) else value
    return read


@dataclass(frozen=True)
class FieldSpec:
    key: str
    validate: Callable[[Any, date], Validation] | None = None  # None: the engine's area matching decides
    same: Callable[[Any, Any], bool] = eq  # compares validated values, so the same answer is never a change
    rejects: Callable[[Any], bool] | None = None  # an answer that ends the screening once the candidate confirms it
    read: Callable[[Any, date, Any], object] | None = None  # (reply, today, base) -> a value or MISSING
    # base: what was kept of an earlier unclear answer, or the saved value when a change is being read
    partial: Callable[[Any], dict] | None = None  # what to keep of an unclear answer to combine with the next
    schema: dict[str, tuple] = field(default_factory=dict)  # the attributes this field adds to the model's reply
    prompt: str = ""  # the lines describing those attributes to the model
    decode_value: Callable[[Any], Any] | None = None  # a saved value read back from JSON
    decode_candidate: Callable[[Any], Any] | None = None  # a pending change read back from JSON


@dataclass(frozen=True)
class Rule:
    """A reason that disqualifies a candidate. `applies` reads the screening's saved answers."""
    reason: str
    applies: Callable[[Any], bool]


@dataclass(frozen=True)
class ScreeningSpec:
    fields: tuple[FieldSpec, ...]
    rules: tuple[Rule, ...] = ()
    role: str = "job"  # "delivery-driver" in "a delivery-driver screening chat"
    area_field: str | None = None  # the field matched against the client's service areas

    @cached_property
    def extraction_model(self):
        return build_model(self)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(f.key for f in self.fields)

    def field(self, key: str) -> FieldSpec:
        for spec in self.fields:
            if spec.key == key:
                return spec
        raise ValueError(f"unknown field: {key}")
