"""Fills an empty database with a working hiring pipeline, so the dashboard has something to show (D95):

    python -m sazon.demo.seed            # into the recruiters' database (data/sazon.db); refuses one that has candidates
    python -m sazon.demo.seed --reset    # deletes that database first

Every candidate is fictional and goes through the real engine with scripted answers: no model, no network, the same result each
time. The candidates are spread over the last three weeks, in both countries and both languages, and end every way a screening
can: a call booked, qualified and still choosing, no time taken, no licence, outside the service area, withdrawn, and
unfinished. Recruiters then set their hiring status and leave notes. One candidate is erased, so the audit log has an entry."""
import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta

from sazon import config
from sazon.client import SAZON_CLIENT
from screener import turn
from screener.call_times import Recruiter
from screener.llm import LLMError
from screener.model import RecruiterStatus as S
from screener.store import Store

PASSWORD = "demo-sazon-2026"
MANAGER = "manager@sazon.test"

RECRUITERS = (("ana@sazon.test", "Ana Beltrán", "ES"), ("miguel@sazon.test", "Miguel Soto", "ES"),
              ("lucia@sazon.test", "Lucía Herrera", "MX"), ("roberto@sazon.test", "Roberto Campos", "MX"))
BY_COUNTRY = {"ES": "Ana Beltrán", "MX": "Lucía Herrera"}


class SeedError(Exception):
    pass


class Scripted:
    """The model, played: it reads the message as what the script says it contains, and words nothing (the engine then uses its
    fixed texts), so the same conversation gives the same result every time."""

    def __init__(self, extraction: dict):
        self.extraction = extraction

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        if not json_mode:
            raise LLMError("no wording: the fixed texts are used")
        return json.dumps(self.extraction)


@dataclass(frozen=True)
class Person:
    name: str
    city: str
    days_ago: int
    end: str  # booked | open | declined | no_license | outside | withdrawn | stopped | erased
    language: str = "es"
    years: int = 1
    platform: str = "Glovo"
    availability: str = "full_time"
    schedule: str = "morning"
    start: tuple = ("now", True)
    pick: int = 1
    stage: S | None = None  # what a recruiter then sets
    note: str | None = None


PEOPLE = (
    Person("Carlos Ruiz Mora", "Madrid", 19, "booked", years=3, stage=S.HIRED, note="Buena entrevista, empieza el lunes. Moto propia."),
    Person("José Luis Hernández Cruz", "Ciudad de México", 20, "booked", years=4, platform="Rappi", stage=S.HIRED, pick=2),
    Person("Lucía Fernández Gil", "Barcelona", 15, "booked", years=2, platform="Uber Eats", availability="part_time", schedule="evening",
           stage=S.HIRED, pick=2, note="Prefiere noches; encaja con la zona del puerto."),
    Person("Irene Castillo Vega", "Madrid", 12, "booked", years=0, platform="", stage=S.REJECTED, note="No se presentó a la entrevista dos veces."),
    Person("Daniela Gómez Pineda", "Ciudad de México", 16, "booked", years=1, platform="DiDi Food", stage=S.REJECTED,
           note="Disponibilidad real distinta de la declarada."),
    Person("Emilio Cárdenas Ibarra", "Guadalajara", 14, "booked", years=2, platform="Rappi", availability="weekends", schedule="flexible",
           stage=S.UNREACHABLE, note="Tres llamadas sin respuesta; se le escribió por el chat."),
    Person("Sergio Navarro Pons", "Hospitalet", 7, "booked", years=2, stage=S.CONTACTED, start=("in_weeks", 1)),
    Person("Diego Ramírez Salas", "Monterrey", 7, "booked", years=5, platform="Uber Eats", stage=S.CONTACTED, note="Llamar por la tarde, trabaja de mañana."),
    Person("Javier Romero Díaz", "Madrid", 4, "booked", years=3, availability="part_time", schedule="afternoon", pick=3),
    Person("María Fernanda López Ruiz", "Zapopan", 4, "booked", years=2, platform="Rappi", note="Pregunta si hay uniforme."),
    Person("Marta Sánchez Ortega", "Valencia", 2, "booked", years=1, platform="Just Eat", start=("weekday", 0)),
    Person("Oliver Grant", "Barcelona", 3, "booked", language="en", years=2, platform="Uber Eats", availability="part_time",
           schedule="afternoon", note="English speaker, lives near Sants."),
    Person("Hannah Brooks", "Monterrey", 2, "booked", language="en", years=1, platform="Uber Eats", availability="weekends", schedule="flexible"),
    Person("Paola Mendoza Ríos", "Ciudad de México", 1, "booked", years=3, platform="DiDi Food", pick=2),
    Person("Elena Vidal Marín", "Getafe", 1, "open", years=2),
    Person("Ximena Torres Beltrán", "CDMX", 1, "open", years=0, platform="", availability="part_time", schedule="evening"),
    Person("Sophie Turner", "Madrid", 0, "open", language="en", years=1, platform="Just Eat"),
    Person("Pablo Herrero Ríos", "Paterna", 6, "declined", years=4, note="Prefiere esperar a que le llamemos."),
    Person("Andrés Castañeda Luna", "Apodaca", 10, "declined", years=2, platform="Rappi"),
    Person("Álvaro Peña Lozano", "Barcelona", 9, "no_license", years=2),
    Person("Valeria Ortiz Ponce", "Guadalajara", 11, "no_license", years=1, platform="Rappi"),
    Person("Nuria Campos Soler", "Sevilla", 8, "outside", years=3),
    Person("Fernando Aguilar Mora", "Puebla", 13, "outside", years=2, platform="Rappi"),
    Person("Hugo Prieto Alonso", "Madrid", 5, "withdrawn"),
    Person("Camila Reyes Navarro", "Ciudad de México", 6, "withdrawn"),
    Person("Raquel Molina Ferrer", "Valencia", 0, "stopped"),
    Person("Ricardo Salinas Vega", "Monterrey", 0, "stopped"),
    Person("Tomás Delgado Vera", "Madrid", 17, "erased", years=2),
)

TEXT = {
    "es": {"consent": "Sí, de acuerdo", "name": "Me llamo {}", "experience": "Tengo {} {} con {}", "year": ("año", "años"), "none": "No tengo experiencia",
           "availability": {"full_time": "Tiempo completo", "part_time": "Medio tiempo", "weekends": "Solo fines de semana"},
           "schedule": {"morning": "Por las mañanas", "afternoon": "Por las tardes", "evening": "Por las noches", "flexible": "Soy flexible"},
           "start": {"now": "Ya mismo", "in_weeks": "La semana que viene", "weekday": "El lunes"}, "city": "Vivo en {}",
           "license": "Sí, tengo carnet de conducir", "no_license": "No tengo carnet", "confirm": "Sí, correcto",
           "withdraw": "Mejor lo dejo, me retiro", "none_of_them": "Ninguna, gracias"},
    "en": {"consent": "Yes, that's fine", "name": "My name is {}", "experience": "{} {} with {}", "year": ("year", "years"), "none": "I have no experience",
           "availability": {"full_time": "Full time", "part_time": "Part time", "weekends": "Weekends only"},
           "schedule": {"morning": "Mornings", "afternoon": "Afternoons", "evening": "Evenings", "flexible": "I'm flexible"},
           "start": {"now": "Right away", "in_weeks": "Next week", "weekday": "Next Monday"}, "city": "I live in {}",
           "license": "Yes, I have a driving license", "no_license": "I don't have a license", "confirm": "Yes, that's right",
           "withdraw": "I'd rather stop, I withdraw", "none_of_them": "None of them, thanks"},
}


def _start(person: Person) -> dict:
    kind, value = person.start
    return {kind: value}


def _steps(person: Person) -> list[tuple[str, dict]]:
    """What the candidate says, each with what the model would have read from it."""
    words = TEXT[person.language]
    steps = [(words["consent"], {"consent": True, "language": person.language}), (words["name"].format(person.name), {"name": person.name})]
    if person.end == "withdrawn":
        return steps + [(words["withdraw"], {"withdraw": True})]
    experience = ({"experience_years": person.years, "platforms": [person.platform] if person.platform else []})
    steps.append((words["experience"].format(person.years, words["year"][person.years != 1], person.platform) if person.years else words["none"], experience))
    if person.end == "stopped":
        return steps
    steps.append((words["availability"][person.availability], {"availability": [person.availability]}))
    if person.availability != "full_time":
        steps.append((words["schedule"][person.schedule], {"schedule": person.schedule}))
    steps.append((words["start"][person.start[0]], {"start_date": _start(person)}))
    steps.append((words["city"].format(person.city), {"city": person.city}))
    if person.end == "outside":
        return steps + [(words["confirm"], {"confirms_rejection": True})]
    if person.end == "no_license":
        return steps + [(words["no_license"], {"has_license": False}), (words["confirm"], {"confirms_rejection": True})]
    steps.append((words["license"], {"has_license": True}))
    if person.end == "declined":
        steps.append((words["none_of_them"], {}))
    if person.end == "booked":
        steps.append((str(person.pick), {}))
    return steps


def _talk(store: Store, person: Person, cid: str, base: datetime) -> None:
    now = base - timedelta(days=person.days_ago)
    turn.start(store, SAZON_CLIENT, cid, now)
    for minute, (message, extraction) in enumerate(_steps(person), start=1):
        turn.handle_message(Scripted(extraction), store, SAZON_CLIENT, cid, message, now + timedelta(minutes=minute))


@dataclass
class Summary:
    recruiters: list[Recruiter]
    candidates: int


def seed(store: Store, now: datetime) -> Summary:
    if store.count() or store.recruiters():
        raise SeedError("the database already has candidates or recruiters: use --reset to start again")
    first = now - timedelta(days=max(p.days_ago for p in PEOPLE) + 2)
    recruiters = [store.add_recruiter(email, name, country, PASSWORD, MANAGER, first) for email, name, country in RECRUITERS]
    for index, person in enumerate(PEOPLE, start=1):
        cid = f"demo-{index:02d}"
        _talk(store, person, cid, now)
        after = now - timedelta(days=person.days_ago) + timedelta(hours=3)
        record = store.get(cid)
        by = BY_COUNTRY["MX" if SAZON_CLIENT.calendar.country_of.get(record.extracted.get("city")) == "MX" else "ES"]
        if person.stage:
            store.set_stage(cid, person.stage, by, after)
        if person.note:
            store.add_note(cid, person.note, by, after + timedelta(minutes=5))
        if person.end == "erased":
            store.erase_candidate(cid, MANAGER, after, "request of the candidate")
    return Summary(recruiters, store.count())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill the recruiters' database with fictional demo candidates.")
    parser.add_argument("--reset", action="store_true", help="delete the database first")
    args = parser.parse_args(argv)
    path = config.db_path()
    if args.reset:
        for leftover in path.parent.glob(path.name + "*"):
            leftover.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    store = Store(path, calendar=SAZON_CLIENT.calendar)
    try:
        summary = seed(store, datetime.now().replace(second=0, microsecond=0))
    except SeedError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"{summary.candidates} fictional candidates in {path}")
    print(f"Recruiters (password {PASSWORD}): " + ", ".join(f"{r.email} ({r.country})" for r in summary.recruiters))
    return 0


if __name__ == "__main__":
    sys.exit(main())
