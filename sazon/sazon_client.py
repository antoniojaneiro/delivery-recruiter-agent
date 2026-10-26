"""Grupo Sazón as a client of the engine (D63)."""
from sazon import config
from sazon.client import Client
from sazon.sazon_spec import SAZON
from sazon.slot_calendar import SlotCalendar

# Where each service area is, and the time zone of each country (D48).
SAZON_CALENDAR = SlotCalendar(
    timezones={"ES": "Europe/Madrid", "MX": "America/Mexico_City"},
    country_of={"Madrid": "ES", "Barcelona": "ES", "Valencia": "ES",
                "Ciudad de México": "MX", "Guadalajara": "MX", "Monterrey": "MX"},
)

SAZON_CLIENT = Client(spec=SAZON, areas=config.AREAS, calendar=SAZON_CALENDAR)
