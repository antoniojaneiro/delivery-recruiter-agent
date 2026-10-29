"""Reading a day and a time from what a candidate says by voice, in Spanish and English (D93). Booking a call by voice has
no list or button, so the agent asks "which day?" and then "what time?"; this reads the answers in plain code, the way
`slot_choice` reads a typed number. Anything it is not sure of is None and the agent asks again. It also finds the closest
day or time when the one asked for is taken."""
import re
from dataclasses import dataclass
from datetime import date, timedelta

from screener.language import fold, plain

_WEEKDAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6,
             "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
_MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
           "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
           "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
           "september": 9, "october": 10, "november": 11, "december": 12}
_MORNING = ("por la manana", "en la manana", "de la manana", "a la manana", "in the morning")
_AFTERNOON = ("por la tarde", "en la tarde", "de la tarde", "a la tarde", "in the afternoon")
_EVENING = ("por la noche", "en la noche", "de la noche", "a la noche", "in the evening", "at night", "tonight")
_TIME_MARKER = re.compile(r"\b(?:a las?|at|las)\b")  # what comes before this is the day, what comes after is the time
_NUMBER_WORDS = {"uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
                 "nueve": 9, "diez": 10, "once": 11, "doce": 12,
                 "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                 "ten": 10, "eleven": 11, "twelve": 12}
_MINUTE_WORDS = {"thirty": 30, "fifteen": 15, "forty five": 45, "fortyfive": 45, "fifty": 50, "twenty": 20, "ten": 10}
_PERIOD_BOUNDS = {"morning": (0, 12 * 60), "afternoon": (12 * 60, 18 * 60), "evening": (18 * 60, 24 * 60)}


@dataclass(frozen=True)
class Wish:
    """A time asked for: an exact one (hour and minute) or a part of the day."""
    hour: int | None = None
    minute: int = 0
    period: str | None = None  # "morning", "afternoon" or "evening" when no exact time was said

    @property
    def minutes(self) -> int | None:
        return None if self.hour is None else self.hour * 60 + self.minute


def _without(text: str, phrases: tuple[str, ...]) -> str:
    for phrase in phrases:
        text = text.replace(phrase, " ")
    return " ".join(text.split())


def read_day(text: str, today: date) -> date | None:
    """The day said, or None. Weekday names mean the next such day after today; a number alone, the next such day of a
    month from today on."""
    said = " ".join(plain(text).split())
    said = _without(said, _MORNING + _AFTERNOON + _EVENING)
    said = _TIME_MARKER.split(said)[0].strip()  # "el 30 a las 10": only "el 30" is the day
    words = said.split()
    if not words:
        return None
    month = next((_MONTHS[w] for w in words if w in _MONTHS), None)
    number = next((int(re.sub(r"(?:st|nd|rd|th)$", "", w)) for w in words if re.fullmatch(r"\d{1,2}(?:st|nd|rd|th)?", w)), None)
    if number is not None and 1 <= number <= 31:
        return _from_number(number, month, today)
    if "pasado manana" in said or "day after tomorrow" in said:
        return today + timedelta(days=2)
    if "hoy" in words or "today" in words:
        return today
    if "manana" in words or "tomorrow" in words:
        return today + timedelta(days=1)
    weekday = next((_WEEKDAYS[w] for w in words if w in _WEEKDAYS), None)
    if weekday is not None:
        return today + timedelta(days=(weekday - today.weekday()) % 7 or 7)
    return None


def _from_number(number: int, month: int | None, today: date) -> date | None:
    if month is not None:
        for year in (today.year, today.year + 1):
            try:
                found = date(year, month, number)
            except ValueError:
                return None
            if found >= today:
                return found
        return None
    year, mon = today.year, today.month
    for _ in range(14):
        try:
            found = date(year, mon, number)
        except ValueError:
            found = None
        if found and found >= today:
            return found
        year, mon = (year + 1, 1) if mon == 12 else (year, mon + 1)
    return None


def read_time(text: str) -> Wish | None:
    """The time said (an exact one, or a part of the day), or None. With no am or pm, 1 to 7 are the afternoon: a call is
    never at one in the morning."""
    said = fold(text)
    said = re.sub(r"\b([ap])\.\s?m\.?", r"\1m", said)
    morning, afternoon, evening = (any(p in said for p in group) for group in (_MORNING, _AFTERNOON, _EVENING))
    afternoon_words = afternoon or evening or bool(re.search(r"\bpm\b", said))
    morning_words = morning or bool(re.search(r"\bam\b", said))
    said = _without(said, _MORNING + _AFTERNOON + _EVENING)
    hour = minute = None
    if re.search(r"\b(?:mediodia|noon|midday)\b", said):
        hour, minute = 12, 0
    elif found := re.search(r"\b(\d{1,2}):(\d{2})\b", said):
        hour, minute = int(found[1]), int(found[2])
    else:
        hour, minute = _spoken_time(said)
    if hour is None:
        period = "morning" if morning else "afternoon" if afternoon else "evening" if evening else None
        if period is None and re.search(r"\b(?:morning|afternoon|evening)\b", said):
            period = re.search(r"\b(morning|afternoon|evening)\b", said)[1]
        return Wish(period=period) if period else None
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    if afternoon_words and 1 <= hour <= 11:
        hour += 12
    elif not (morning_words or ":" in text or hour == 0) and 1 <= hour <= 7:
        hour += 12
    return Wish(hour, minute)


def _hour_of(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    return _NUMBER_WORDS.get(token)


def _spoken_time(said: str) -> tuple[int | None, int | None]:
    hour_word = r"(\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")"
    patterns = (
        (rf"\b{hour_word} y media\b", 30, 0), (rf"\b{hour_word} y cuarto\b", 15, 0), (rf"\b{hour_word} menos cuarto\b", 45, -1),
        (rf"\bhalf past {hour_word}\b", 30, 0), (rf"\bquarter past {hour_word}\b", 15, 0),
        (rf"\bquarter to {hour_word}\b", 45, -1), (rf"\b{hour_word} and a half\b", 30, 0))
    for pattern, minute, shift in patterns:
        if found := re.search(pattern, said):
            hour = _hour_of(found[1])
            return (None, None) if hour is None else (hour + shift, minute)
    minute_words = "|".join(sorted(_MINUTE_WORDS, key=len, reverse=True))
    if found := re.search(rf"\b{hour_word} ({minute_words})\b", said):
        hour = _hour_of(found[1])
        if hour is not None:
            return hour, _MINUTE_WORDS[found[2]]
    if found := re.search(r"\b(\d{1,2})\b", said):
        return int(found[1]), 0
    for token in said.split():
        if token in _NUMBER_WORDS and (token not in ("una", "uno", "one") or re.search(r"\b(?:las?|at)\b", said)):
            return _NUMBER_WORDS[token], 0
    return None, None


def nearest_day(days: list[date], wanted: date) -> date | None:
    """The day with free times closest to the one asked for; two equally close, the earlier one."""
    return min(days, key=lambda d: (abs((d - wanted).days), d), default=None)


def nearest_time(minutes: list[int], wish: Wish) -> int | None:
    """The free time (minutes since midnight) closest to what was asked: the exact one if free, otherwise the closest, and
    two equally close the earlier. For a part of the day, its earliest free time, or the closest to it."""
    if not minutes:
        return None
    if wish.period:
        start, end = _PERIOD_BOUNDS[wish.period]
        inside = [m for m in minutes if start <= m < end]
        if inside:
            return min(inside)
        return min(minutes, key=lambda m: (abs(m - start), m))
    return min(minutes, key=lambda m: (abs(m - wish.minutes), m))
