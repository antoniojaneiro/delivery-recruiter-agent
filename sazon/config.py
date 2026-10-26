import os
from pathlib import Path

# Sample service areas (D13). Replace with the client's real list before any pilot.
# Nearby towns and districts are samples too: they let "Zapopan" or "Chamberí" count as their service area.
AREAS = {
    "Madrid": ["Chamberí", "Getafe", "Alcalá de Henares", "Leganés", "Alcorcón"],
    "Barcelona": ["L'Hospitalet de Llobregat", "Hospitalet", "Badalona"],
    "Valencia": ["Paterna", "Torrent"],
    "Ciudad de México": ["CDMX", "DF", "Mexico City", "Coyoacán", "Iztapalapa", "Tlalpan"],
    "Guadalajara": ["Zapopan", "Tlaquepaque", "Tonalá"],
    "Monterrey": ["San Pedro Garza García", "San Nicolás de los Garza", "Apodaca"],
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "sazon.db"

LOG_PATH = PROJECT_ROOT / "data" / "sazon.log"


def db_path() -> Path:
    """The SQLite file. SAZON_DB overrides it (used by tests and to point the dashboard elsewhere)."""
    return Path(os.environ.get("SAZON_DB") or DB_PATH)
