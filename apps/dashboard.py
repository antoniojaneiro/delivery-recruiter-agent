"""Recruiter dashboard for Grupo Sazón (D4, D42, D47, D48, D57, D66). Run with: streamlit run apps/dashboard.py

Reads the same SQLite file as the chat. The agent's data and the recruiter's data are separate:
nothing here can overwrite what the agent stored (D42). Recruiters sign in with their own account. The login page also has a tab to create one, open to anyone who
can reach the page (D74), so keep the dashboard on your own computer. (`python -m sazon.accounts add NAME` works too.) This is a
prototype login: a real deployment should use the company's single sign-on. Every text comes from
`sazon/ui_pack.py`, in the language chosen with the switch."""
from datetime import datetime

import streamlit as st

from screener import accounts

from sazon import accounts as sazon_accounts
from sazon import config, ui
from sazon.ui import t

st.set_page_config(page_title=t("app.page_title"), page_icon=":material/groups:", layout="wide")

if not st.session_state.get("recruiter"):  # only a successful login below ever sets this
    ui.language_switch()
    st.title(t("login.title"))
    if st.session_state.get("account_flash"):
        st.success(st.session_state.pop("account_flash"))
    sign_in, sign_up = st.tabs([t("login.tab_sign_in"), t("login.tab_sign_up")])
    with sign_in, st.form("login"):
        name = st.text_input(t("login.name"), key="login_name")
        password = st.text_input(t("login.password"), type="password", key="login_password")
        submitted = st.form_submit_button(t("login.submit"), key="login_submit")
    with sign_up, st.form("signup"):
        new_name = st.text_input(t("login.name"), key="signup_name")
        new_password = st.text_input(t("login.password"), type="password", key="signup_password")
        new_confirm = st.text_input(t("account.confirm"), type="password", key="signup_confirm")
        created = st.form_submit_button(t("login.signup_submit"), key="signup_submit")
    if submitted:
        try:
            verified = accounts.verify(sazon_accounts.accounts_path(), name, password)
        except accounts.TooManyAttempts:
            st.error(t("login.too_many"))
            st.stop()
        if verified is None:
            st.error(t("login.wrong"))
        else:
            st.session_state["recruiter"] = verified
            st.rerun()
    if created:  # open to anyone who can reach this page (D74); the new person still has to sign in
        try:
            if new_password != new_confirm:
                raise accounts.AccountError("mismatch", "")
            registered = accounts.add_account(sazon_accounts.accounts_path(), new_name, new_password)
        except accounts.AccountError as error:
            st.error(t(f"account.err.{error.code}", n=accounts.MIN_PASSWORD_LENGTH))
        except accounts.DamagedAccounts:
            st.error(t("account.err.damaged"))
        else:
            ui.store().log_admin("signup", "account_created", registered, datetime.now())
            st.session_state["account_flash"] = t("account.created", name=registered)
            st.rerun()
    st.stop()

store = ui.store()
with st.sidebar:
    st.header(t("sidebar.header"))
    st.write(t("sidebar.session", name=st.session_state["recruiter"]))
    ui.language_switch()
    if st.button(t("sidebar.logout"), key="logout"):
        for key in list(st.session_state):  # filters, the open candidate, messages: nothing is left for the next person
            if key != "ui_language":
                del st.session_state[key]
        st.rerun()
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
st.navigation(pages).run()
