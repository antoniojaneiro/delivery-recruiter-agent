"""One client's deployment of the screening engine (D63): what it screens for and where it operates."""
from dataclasses import dataclass
from datetime import timedelta

from sazon.spec import ScreeningSpec


@dataclass(frozen=True)
class Client:
    spec: ScreeningSpec
    areas: dict[str, list[str]]  # service area -> nearby places that count as the same area
    remind_after: timedelta = timedelta(hours=24)  # silence before the one reminder, and again before STALLED
