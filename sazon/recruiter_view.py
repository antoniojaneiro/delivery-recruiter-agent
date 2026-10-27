"""Grupo Sazón's recruiter view: its client and its text pack bound to the engine's `RecruiterView` (D63, D70)."""
from screener.model import Language
from screener.recruiter_view import RecruiterView
from sazon.client import SAZON_CLIENT
from sazon.ui_pack import PACK


def view_for(language=None) -> RecruiterView:
    """The recruiter screens' labels, cards and rows in `language` (Spanish, the default, or English)."""
    return RecruiterView(SAZON_CLIENT, PACK, Language(language) if language else None)
