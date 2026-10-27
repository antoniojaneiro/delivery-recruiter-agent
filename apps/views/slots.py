from datetime import datetime, time

import streamlit as st

from screener import slot_flow

from sazon import ui
from sazon.ui import t
from sazon.client import SAZON_CLIENT
from screener.phrasing import slot_label
from screener.recruiter_view import escape_markdown

store = ui.store()
recruiter = ui.recruiter_name()
language = ui.language()
view = ui.view()

st.title(t("slots.title"))
st.caption(t("slots.caption"))

with st.form("slot_form"):
    countries = list(store.calendar.timezones)
    country = st.selectbox(t("slots.country"), countries, format_func=lambda code: view.country_label(code),
                           key="slot_country")
    day = st.date_input(t("slots.day"), key="slot_date")
    hour = st.time_input(t("slots.hour"), value=time(10, 0), step=900, key="slot_time")
    caller = st.text_input(t("slots.caller"), key="slot_recruiter")
    save = st.form_submit_button(t("slots.add"), key="save_slot")

if save:
    try:
        if not recruiter:
            raise ValueError(t("common.need_name"))
        store.add_slot(country, datetime.combine(day, hour), caller, recruiter, datetime.now().astimezone())
    except (ValueError, LookupError) as error:
        st.error(view.explain_error(error))
    else:
        st.success(t("slots.added"))

now = datetime.now().astimezone()
slots = store.slots(now)

if slots:
    def describe(slot_id: int) -> str:
        slot = next(s for s in slots if s.id == slot_id)
        return f"{view.country_label(slot.country)} · {slot_label(slot.starts_at, language)}"

    with st.container(horizontal=True, vertical_alignment="bottom"):
        to_cancel = st.selectbox(t("slots.cancel_pick"), [s.id for s in slots], format_func=describe,
                                 key="cancel_slot")
        cancel = st.button(t("slots.cancel_button"), key="confirm_cancel")
    if cancel:
        if not recruiter:
            st.error(t("common.need_name"))
        else:
            try:
                booked_by = store.cancel_slot(to_cancel, recruiter, now)
            except (ValueError, LookupError) as error:
                st.error(view.explain_error(error))
                st.stop()
            if booked_by:
                booked = store.get(booked_by)
                who = f"{escape_markdown(view.name_of(booked))} ({booked_by})" if booked else booked_by
                told = slot_flow.notify_cancelled(store, SAZON_CLIENT, booked_by, now.replace(tzinfo=None))
                st.warning(t("slots.booked_warning", who=who,
                             notice=t("slots.notice_left") if told else t("slots.notice_failed")))
            else:
                st.success(t("slots.cancelled"))
        slots = store.slots(now)

if not slots:
    st.info(t("slots.none"))
else:
    def state(slot) -> str:
        booked = store.get(slot.candidate_id) if slot.candidate_id else None
        return view.slot_state(slot, view.name_of(booked) if booked else None, now)

    st.dataframe(
        [{t("col.id"): s.id, t("slots.country"): view.country_label(s.country),
          t("slots.col_when"): slot_label(s.starts_at, language), t("slots.col_caller"): s.recruiter or "",
          t("slots.col_state"): state(s)} for s in slots],
        hide_index=True, width="stretch")
