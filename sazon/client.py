"""Grupo Sazón as a client of the engine (D63)."""
from sazon.areas import AREAS, COUNTRY_OF
from screener.client import Client
from sazon.spec import SAZON
from screener.slot_calendar import SlotCalendar

# Where each service area is, and the time zone of each country (D48).
SAZON_CALENDAR = SlotCalendar(
    timezones={"ES": "Europe/Madrid", "MX": "America/Mexico_City"},
    country_of=COUNTRY_OF,
)

SAZON_CLIENT = Client(spec=SAZON, areas=AREAS, calendar=SAZON_CALENDAR)
