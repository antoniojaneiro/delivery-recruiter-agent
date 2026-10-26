"""Recruiter dashboard for Grupo Sazón (D4, D42, D47, D48, D57). Run with: streamlit run dashboard.py

Reads the same SQLite file as the chat. The agent's data and the recruiter's data are separate:
nothing here can overwrite what the agent stored (D42). Recruiters sign in with their own account
(create one with `python -m sazon.accounts add NAME`); without accounts nobody gets in. This is a
prototype login: a real deployment should use the company's single sign-on."""
from datetime import datetime

import streamlit as st

from screener import accounts

from sazon import accounts as sazon_accounts
from sazon import ui

st.set_page_config(page_title="Candidatos · Grupo Sazón", page_icon=":material/groups:", layout="wide")

if not st.session_state.get("recruiter"):  # only a successful login below ever sets this
    st.title("Grupo Sazón · Reclutamiento")
    if not accounts.has_accounts(sazon_accounts.accounts_path()):
        st.error("No hay cuentas de reclutador, así que nadie puede entrar. "
                 "Crea una con: python -m sazon.accounts add NOMBRE")
        st.stop()
    with st.form("login"):
        name = st.text_input("Nombre", key="login_name")
        password = st.text_input("Contraseña", type="password", key="login_password")
        submitted = st.form_submit_button("Entrar", key="login_submit")
    if submitted:
        try:
            verified = accounts.verify(sazon_accounts.accounts_path(), name, password)
        except accounts.TooManyAttempts:
            st.error("Demasiados intentos con ese nombre. Espera 10 minutos e inténtalo de nuevo.")
            st.stop()
        if verified is None:
            st.error("Nombre o contraseña incorrectos.")
        else:
            st.session_state["recruiter"] = verified
            st.rerun()
    st.stop()

store = ui.store()
with st.sidebar:
    st.header("Reclutador")
    st.write(f"Sesión: **{st.session_state['recruiter']}**")
    if st.button("Cerrar sesión", key="logout"):
        for key in list(st.session_state):  # filters, the open candidate, messages: nothing is left for the next person
            del st.session_state[key]
        st.rerun()
    st.divider()
    accepting = store.accepting_applications()
    st.caption("Candidaturas: abiertas" if accepting else "Candidaturas: CERRADAS")
    if st.button("Cerrar candidaturas" if accepting else "Abrir candidaturas", key="toggle_applications",
                 help="Cerradas, el asistente responde a todos que no se aceptan solicitudes."):
        store.set_accepting(not accepting, st.session_state["recruiter"], datetime.now())
        st.rerun()

pages = [
    st.Page("app_pages/candidates.py", title="Candidatos", icon=":material/groups:", default=True),
    st.Page("app_pages/slots.py", title="Horarios", icon=":material/calendar_month:"),
    st.Page("app_pages/funnel.py", title="Embudo", icon=":material/monitoring:"),
]
st.navigation(pages).run()
