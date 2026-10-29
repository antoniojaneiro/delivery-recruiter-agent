"""Two small date calculations the engine and the pages share (D94)."""
from datetime import date, timedelta


def next_weekday(today: date, weekday: int) -> date:
    """The next day that is that weekday (Monday is 0), always after today: "el jueves" said on a Thursday is a week on."""
    return today + timedelta(days=(weekday - today.weekday()) % 7 or 7)


def minutes_of_day(moment) -> int:
    """Minutes since midnight of a time or a datetime."""
    return moment.hour * 60 + moment.minute
