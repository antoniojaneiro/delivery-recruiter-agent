"""The hiring manager's page: create and delete recruiters, and reset a forgotten password (D80)."""
from datetime import datetime

import streamlit as st

from screener import slot_flow

from sazon import ui
from sazon.client import SAZON_CLIENT
from sazon.ui import t
from screener.store import InputError

store = ui.store()
view = ui.view()
actor = ui.recruiter_name()

st.title(t("recruiters.title"))
if not ui.is_manager():  # the page is not even listed for a recruiter; this is the second lock
    st.stop()
st.caption(t("recruiters.caption"))

if flash := st.session_state.pop("_recruiter_flash", None):
    st.success(flash)
recruiters = store.recruiters()
countries = list(SAZON_CLIENT.calendar.timezones)

if recruiters:
    st.dataframe([{t("recruiters.col_email"): r.email, t("recruiters.col_name"): r.name,
                   t("recruiters.col_country"): view.country_label(r.country),
                   t("recruiters.col_since"): f"{r.created_at:%Y-%m-%d}"} for r in recruiters],
                 hide_index=True, width="stretch", alt=t("recruiters.title"))
else:
    st.info(t("recruiters.none"))

with st.container(border=True):
    st.subheader(t("recruiters.add_title"))
    with st.form("recruiter_form", clear_on_submit=False):
        email = st.text_input(t("recruiters.email"), key="rec_email")
        name = st.text_input(t("recruiters.name"), key="rec_name")
        country = st.selectbox(t("recruiters.country"), countries, key="rec_country",
                               format_func=lambda code: view.country_label(code))
        password = st.text_input(t("recruiters.password"), type="password", key="rec_password")
        again = st.text_input(t("recruiters.password_again"), type="password", key="rec_password_again")
        create = st.form_submit_button(t("recruiters.create"), key="rec_create")
    if create:
        try:
            if password != again:
                st.error(t("account.mismatch"))
            else:
                made = store.add_recruiter(email, name, country, password, actor, datetime.now())
                st.success(t("recruiters.created", name=made.name))
                recruiters = store.recruiters()
        except InputError as error:
            st.error(view.explain_error(error))

if recruiters:
    emails = [r.email for r in recruiters]
    by_email = {r.email: r for r in recruiters}
    with st.container(border=True):
        st.subheader(t("recruiters.reset_title"))
        with st.form("reset_form", clear_on_submit=True):
            who = st.selectbox(t("recruiters.delete_pick"), emails, key="reset_who",
                               format_func=lambda e: f"{by_email[e].name} ({e})")
            new = st.text_input(t("recruiters.reset_new"), type="password", key="reset_password")
            reset = st.form_submit_button(t("recruiters.reset_button"), key="reset_submit")
        if reset:
            try:
                store.reset_password(who, new, actor, datetime.now())
                st.success(t("recruiters.reset_done"))
            except (InputError, LookupError) as error:
                st.error(view.explain_error(error))
    with st.container(border=True):
        st.subheader(t("recruiters.delete_title"))
        gone = st.selectbox(t("recruiters.delete_pick"), emails, key="delete_who",
                            format_func=lambda e: f"{by_email[e].name} ({e})")
        calls = store.future_calls(gone, datetime.now().astimezone())
        st.caption(t("recruiters.delete_calls", n=len(calls)))  # what leaving would affect
        sure = st.checkbox(t("recruiters.delete_confirm"), key="delete_sure")
        if st.button(t("recruiters.delete_button"), key="delete_submit"):
            if not sure:
                st.error(t("recruiters.delete_need_check"))
            else:  # each future call goes to another recruiter free then, or the candidate is told and can pick again
                done = slot_flow.remove_recruiter(store, SAZON_CLIENT, gone, actor, datetime.now())
                st.session_state["_recruiter_flash"] = t("recruiters.deleted") + (
                    " " + t("avail.effect", moved=done.moved, released=done.released) if calls else "")
                st.rerun()
