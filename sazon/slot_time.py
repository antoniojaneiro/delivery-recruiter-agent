"""Time rules for call slots (D48). A slot is a wall-clock time in its country's own zone, so a
candidate in that country sees exactly the time the recruiter typed and no conversion is needed.
The only conversion is the check that a slot is still far enough in the future."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sazon import config

MIN_NOTICE = timedelta(hours=2)


def zone(country: str) -> ZoneInfo:
    return ZoneInfo(config.COUNTRY_TZ[country])


def wall_time_exists(country: str, wall: datetime) -> bool:
    """False for a time skipped when the clocks spring forward (02:30 does not exist in Madrid that night)."""
    aware = wall.replace(tzinfo=zone(country))
    return aware.astimezone(timezone.utc).astimezone(zone(country)).replace(tzinfo=None) == wall


def has_enough_notice(country: str, wall: datetime, now: datetime) -> bool:
    """`now` may be aware, or naive meaning this machine's local time."""
    now = now if now.tzinfo else now.astimezone()
    return wall.replace(tzinfo=zone(country)) - now >= MIN_NOTICE
