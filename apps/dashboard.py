"""Recruiter dashboard for Grupo Sazón (D4, D42, D47, D48, D57, D66). Run with: streamlit run apps/dashboard.py

Reads the same SQLite file as the chat. The agent's data and the recruiter's data are separate:
nothing here can overwrite what the agent stored (D42). Recruiters sign in with their own account.
With no accounts yet the login page creates the first one; after that only a signed-in recruiter can add more (D73).
(`python -m sazon.accounts add NAME` still works.) This is a
prototype login: a real deployment should use the company's single sign-on. Every text comes from
`sazon/ui_pack.py`, in the language chosen with the switch."""
from datetime import datetime

import streamlit as st

from screener import accounts

from sazon import accounts as sazon_accounts
from sazon import ui
from sazon.ui import t

st.set_page_config(page_title=t("app.page_title"), page_icon=":material/groups:", layout="wide")

if not st.session_state.get("recruiter"):  # only a successful login below ever sets this
    ui.language_switch()
    st.title(t("login.title"))
    if not accounts.has_accounts(sazon_accounts.accounts_path()):
        # An install with no accounts: the first one is created here. Once one exists this form is never shown again.
        st.info(t("setup.intro"))
        with st.form("setup"):
            name = st.text_input(t("login.name"), key="setup_name")
            password = st.text_input(t("login.password"), type="password", key="setup_password")
            confirm = st.text_input(t("account.confirm"), type="password", key="setup_confirm")
            created = st.form_submit_button(t("setup.submit"), key="setup_submit")
        if created:
            try:
                if password != confirm:
                    raise accounts.AccountError("mismatch", "")
                registered = accounts.create_first(sazon_accounts.accounts_path(), name, password)
            except accounts.AccountError as error:
                st.error(t(f"account.err.{error.code}", n=accounts.MIN_PASSWORD_LENGTH))
            except accounts.DamagedAccounts:
                st.error(t("account.err.damaged"))
            else:
                ui.store().log_admin("setup", "account_created", registered, datetime.now())
                st.session_state["recruiter"] = registered
                st.rerun()
        st.stop()
    with st.form("login"):
        name = st.text_input(t("login.name"), key="login_name")
        password = st.text_input(t("login.password"), type="password", key="login_password")
        submitted = st.form_submit_button(t("login.submit"), key="login_submit")
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
    st.divider()

    def add_recruiter_account() -> None:
        """Runs before the page is redrawn, so the boxes can be emptied once the account exists."""
        state = st.session_state
        try:
            if state["new_account_password"] != state["new_account_confirm"]:
                raise accounts.AccountError("mismatch", "")
            registered = accounts.add_account(sazon_accounts.accounts_path(), state["new_account_name"],
                                              state["new_account_password"])
        except accounts.AccountError as error:
            state["account_flash"] = ("error", t(f"account.err.{error.code}", n=accounts.MIN_PASSWORD_LENGTH))
        except accounts.DamagedAccounts:
            state["account_flash"] = ("error", t("account.err.damaged"))
        else:
            store.log_admin(f"recruiter:{state['recruiter']}", "account_created", registered, datetime.now())
            for key in ("new_account_name", "new_account_password", "new_account_confirm"):
                state[key] = ""
            state["account_flash"] = ("success", t("account.created", name=registered))

    with st.expander(t("account.add_title")):
        st.text_input(t("login.name"), key="new_account_name")
        st.text_input(t("login.password"), type="password", key="new_account_password")
        st.text_input(t("account.confirm"), type="password", key="new_account_confirm")
        st.button(t("account.add_button"), key="new_account_submit", on_click=add_recruiter_account)
        if st.session_state.get("account_flash"):
            kind, message = st.session_state.pop("account_flash")
            (st.success if kind == "success" else st.error)(message)
    st.divider()
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
