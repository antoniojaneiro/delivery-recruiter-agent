"""Recruiter dashboard for Grupo Sazón (D4, D42, D47, D48, D66, D80). Run with: streamlit run apps/dashboard.py

Reads the same SQLite file as the chat. The agent's data and the recruiter's data are separate: nothing here can
overwrite what the agent stored (D42). People sign in with their email and password. The hiring manager's email and
password come from `.env` (HIRING_MANAGER_EMAIL, HIRING_MANAGER_PASSWORD) and only that person creates and deletes
recruiters, on the Recruiters page. There is no sign-up. This is a prototype login: a real deployment should use the
company's single sign-on. Every text comes from `sazon/ui_pack.py`, in the language chosen with the switch."""
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

from screener.login import sign_in
from screener.recruiters import TooManyAttempts
from screener.store import InputError

from sazon import config, ui
from sazon.ui import t

load_dotenv()  # the hiring manager's email and password
st.set_page_config(page_title=t("app.page_title"), page_icon=":material/groups:", layout="wide")
store = ui.store()

if not st.session_state.get("recruiter"):  # only a successful sign-in below ever sets this
    ui.language_switch()
    st.title(t("login.title"))
    manager = config.manager_credentials()
    if manager is None and not store.recruiters():
        st.warning(t("login.setup_needed"))
    with st.form("login"):
        email = st.text_input(t("login.email"), key="login_email")
        password = st.text_input(t("login.password"), type="password", key="login_password")
        submitted = st.form_submit_button(t("login.submit"), key="login_submit")
    if submitted:
        try:
            who = sign_in(store, email, password, manager, datetime.now())
        except TooManyAttempts:
            st.error(t("login.too_many"))
            st.stop()
        if who is None:
            st.error(t("login.wrong"))
        else:
            st.session_state.update(recruiter=who.email, recruiter_name=who.name, role=who.role, country=who.country)
            st.rerun()
    st.stop()

with st.sidebar:
    st.header(t("sidebar.header"))
    st.write(t("sidebar.session", name=ui.signed_in_name()))
    if ui.is_manager():
        st.caption(t("sidebar.manager"))
    ui.language_switch()
    if st.button(t("sidebar.logout"), key="logout"):
        for key in list(st.session_state):  # filters, the open candidate, messages: nothing is left for the next person
            if key != "ui_language":
                del st.session_state[key]
        st.rerun()
    if not ui.is_manager():  # the manager's password is in .env; a recruiter changes their own here
        with st.expander(t("account.change_title")):
            with st.form("password_form", clear_on_submit=True):
                old = st.text_input(t("account.old"), type="password", key="old_password")
                new = st.text_input(t("account.new"), type="password", key="new_password")
                again = st.text_input(t("account.confirm"), type="password", key="new_password_again")
                change = st.form_submit_button(t("account.change_button"), key="change_password")
            if change:
                try:
                    if new != again:
                        st.error(t("account.mismatch"))
                    else:
                        store.change_password(st.session_state["recruiter"], old, new, datetime.now())
                        st.success(t("account.changed"))
                except TooManyAttempts:
                    st.error(t("login.too_many"))
                except InputError as error:
                    st.error(ui.view().explain_error(error))
    st.link_button(t("link.chat"), config.chat_url(), icon=":material/open_in_new:", width="stretch")
    accepting = store.accepting_applications()
    st.caption(t("sidebar.open") if accepting else t("sidebar.closed"))
    if st.button(t("sidebar.close_button") if accepting else t("sidebar.open_button"), key="toggle_applications",
                 help=t("sidebar.toggle_help")):
        store.set_accepting(not accepting, st.session_state["recruiter"], datetime.now())
        st.rerun()

pages = [
    st.Page("views/candidates.py", title=t("nav.candidates"), icon=":material/groups:", default=True),
    st.Page("views/slots.py", title=t("nav.slots"), icon=":material/calendar_month:"),
    st.Page("views/funnel.py", title=t("nav.funnel"), icon=":material/monitoring:"),
]
if ui.is_manager():  # only the hiring manager creates and deletes recruiters
    pages.append(st.Page("views/recruiters.py", title=t("nav.recruiters"), icon=":material/manage_accounts:"))
st.navigation(pages).run()
