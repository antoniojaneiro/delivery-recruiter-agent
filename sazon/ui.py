"""Small helpers shared by the dashboard pages."""
import streamlit as st

from sazon import config
from sazon.store import Store


@st.cache_resource
def _open_store(path: str) -> Store:
    return Store(path)


def store() -> Store:
    return _open_store(str(config.db_path()))


def recruiter_name() -> str:
    """The name typed in the sidebar; every recruiter action is saved with it."""
    return str(st.session_state.get("recruiter", "")).strip()
