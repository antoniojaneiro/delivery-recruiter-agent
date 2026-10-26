"""Small helpers shared by the dashboard pages."""
import streamlit as st

from sazon import config
from sazon.sazon_client import SAZON_CALENDAR
from sazon.store import Store


@st.cache_resource
def _open_store(path: str) -> Store:
    return Store(path, calendar=SAZON_CALENDAR)


def store() -> Store:
    return _open_store(str(config.db_path()))


@st.cache_resource(max_entries=2)
def _candidates(path: str, revision: int) -> list:
    return _open_store(path).list_candidates()


def candidates() -> list:
    """Every candidate, read again only when something changed in the database (see Store.revision)."""
    return _candidates(str(config.db_path()), store().revision())


def recruiter_name() -> str:
    """The name typed in the sidebar; every recruiter action is saved with it."""
    return str(st.session_state.get("recruiter", "")).strip()
