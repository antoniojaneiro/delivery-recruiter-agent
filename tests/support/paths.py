"""Where things are in the repo, for the tests that start an app or read a repo file."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DASHBOARD = ROOT / "apps" / "dashboard.py"
CHAT_APP = ROOT / "apps" / "chat_app.py"
VIEWS = ROOT / "apps" / "views"
