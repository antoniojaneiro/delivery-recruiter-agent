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
DEMO_DIR = PROJECT_ROOT / "data" / "demo"  # everything the demos write: the chat app's database, the transcripts


def db_path() -> Path:
    """The SQLite file. SAZON_DB overrides it (used by tests and to point the dashboard elsewhere)."""
    return Path(os.environ.get("SAZON_DB") or DB_PATH)


def demo_db_path() -> Path:
    """The database of the browser chat for trying the agent. It is never the recruiters' file: SAZON_DB does not
    move it, only SAZON_DEMO_DB does."""
    return Path(os.environ.get("SAZON_DEMO_DB") or DEMO_DIR / "chat.db")
