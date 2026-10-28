"""A fictional recruiting team for the browser chat's test database (D86), so a person trying the chat can book a call at
once. Never put in the recruiters' own database, and nobody can sign in as them (their passwords are thrown away)."""
import secrets
from datetime import datetime

DEMO_TEAM = (("demo-es@demo.test", "Demo recruiter (Spain)", "ES"), ("demo-mx@demo.test", "Demo recruiter (Mexico)", "MX"))


def ensure_demo_team(store, now: datetime) -> None:
    """Adds the team when the database has no recruiters at all; each has the default week."""
    if store.recruiters():
        return
    for email, name, country in DEMO_TEAM:
        store.add_recruiter(email, name, country, secrets.token_urlsafe(24), "demo", now)
