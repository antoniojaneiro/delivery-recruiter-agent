import os
from pathlib import Path

# Sample service areas (D13). Replace with the client's real list before any pilot.
AREAS = {
    "Madrid": [],
    "Barcelona": [],
    "Valencia": [],
    "Ciudad de México": ["CDMX", "DF", "Mexico City"],
    "Guadalajara": [],
    "Monterrey": [],
}

# Where each service area is, and the time zone of each country (D48).
COUNTRY_OF = {
    "Madrid": "ES", "Barcelona": "ES", "Valencia": "ES",
    "Ciudad de México": "MX", "Guadalajara": "MX", "Monterrey": "MX",
}
COUNTRY_TZ = {"ES": "Europe/Madrid", "MX": "America/Mexico_City"}

DB_PATH = Path("data/sazon.db")

LOG_PATH = Path("data/sazon.log")


def db_path() -> Path:
    """The SQLite file. SAZON_DB overrides it (used by tests and to point the dashboard elsewhere)."""
    return Path(os.environ.get("SAZON_DB") or DB_PATH)
