"""One client's deployment of the screening engine (D63): what it screens for and where it operates."""
from dataclasses import dataclass

from sazon.spec import ScreeningSpec


@dataclass(frozen=True)
class Client:
    spec: ScreeningSpec
    areas: dict[str, list[str]]  # service area -> nearby places that count as the same area
