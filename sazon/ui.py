"""Small helpers shared by the dashboard pages."""
import streamlit as st

from sazon import config
from sazon.client import SAZON_CLIENT
from sazon.ui_pack import PACK
from screener.model import Language
from screener.store import Store


@st.cache_resource
def _open_store(path: str) -> Store:
    return Store(path, calendar=SAZON_CLIENT.calendar)


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


def language() -> Language:
    """The language the recruiter picked for the screens (Spanish until they pick another)."""
    return Language(st.session_state.get("ui_language") or Language.ES)


def t(key: str, **values) -> str:
    return PACK.get(key, language(), **values)


def language_switch() -> None:
    """The Spanish/English switch. It keeps its value when the recruiter signs out."""
    st.segmented_control(t("language.label"), [Language.ES, Language.EN], default=Language.ES,
                         format_func=lambda value: {Language.ES: "Español", Language.EN: "English"}[value],
                         key="ui_language", label_visibility="collapsed")
