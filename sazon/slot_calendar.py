"""Time rules for call slots (D48, D63). A slot is a wall-clock time in its country's own zone, so a
candidate in that country sees exactly the time the recruiter typed and no conversion is needed.
The only conversion is the check that a slot is still far enough in the future."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class SlotCalendar:
    timezones: dict[str, str]  # country code -> time zone name
    country_of: dict[str, str]  # service area -> country code
    min_notice: timedelta = timedelta(hours=2)
    offer_size: int = 3  # how many free times a qualified candidate is offered

    def zone(self, country: str) -> ZoneInfo:
        return ZoneInfo(self.timezones[country])

    def wall_time_exists(self, country: str, wall: datetime) -> bool:
        """False for a time skipped when the clocks spring forward (02:30 does not exist in Madrid that night)."""
        aware = wall.replace(tzinfo=self.zone(country))
        return aware.astimezone(timezone.utc).astimezone(self.zone(country)).replace(tzinfo=None) == wall

    def has_enough_notice(self, country: str, wall: datetime, now: datetime) -> bool:
        """`now` may be aware, or naive meaning this machine's local time."""
        now = now if now.tzinfo else now.astimezone()
        return wall.replace(tzinfo=self.zone(country)) - now >= self.min_notice
