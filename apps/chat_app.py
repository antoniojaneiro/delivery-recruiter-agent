"""A browser chat for trying Grupo Sazón's agent (D66). Run with: streamlit run apps/chat_app.py

It runs the same turn code as the terminal chat and the real model. It saves into a demo database (SAZON_DEMO_DB,
data/demo/chat.db by default), unless the switch in the sidebar sends new candidates to the recruiters' database
(SAZON_DB) so they appear in the dashboard (D73). There is no login: it is meant to run on your own computer.
On the right, an inspector shows what the agent has understood, read from that database."""
import calendar
from datetime import date, datetime, timedelta

import streamlit as st

from screener import dialog, gemini, reminders, slot_flow, turn
from screener.chat import log_error
from screener.inspector import inspect
from screener.language import language_of
from screener.llm import LLMError
from screener.model import Language
from screener.recruiter_view import OUTCOME_COLOR
from screener.store import Store

from sazon import config, ui
from sazon.client import SAZON_CLIENT
from sazon.demo.team import ensure_demo_team
from sazon.ui import open_store, t
from sazon.ui_pack import PACK

st.set_page_config(page_title=t("chat.page_title"), page_icon=":material/chat:", layout="wide")


def active_store() -> Store:
    """The test database, or the recruiters' one while the sidebar switch is on."""
    shared = st.session_state.get("share_with_dashboard")
    return open_store(str(config.db_path() if shared else config.demo_db_path()))


store = active_store()
if not st.session_state.get("share_with_dashboard"):  # the test database gets a fictional team; the real one never does
    ensure_demo_team(store, datetime.now())
language = ui.language()
view = ui.view()

if "llm" not in st.session_state:  # one model client per browser session, created once
    try:
        st.session_state["llm"] = gemini.from_env()
    except LLMError:
        with st.sidebar:
            ui.language_switch()
        st.title(t("chat.title"))
        st.error(t("chat.no_key"))
        st.stop()
llm = st.session_state["llm"]


def new_candidate() -> None:
    """Also runs when the switch changes, so one chat never splits across two databases."""
    candidate_id, _ = dialog.new_candidate(active_store(), SAZON_CLIENT, datetime.now())  # the disclosure, once per candidate
    st.session_state["chat_id"] = candidate_id
    st.session_state.pop("flash", None)


def wait_a_day() -> None:
    reply = reminders.wait_a_day(active_store(), SAZON_CLIENT, st.session_state["chat_id"], datetime.now())
    st.session_state["flash"] = None if reply else "chat.wait_nothing"


def deliver_queued() -> None:
    dialog.deliver_queued(active_store(), st.session_state["chat_id"], datetime.now())


if "chat_id" not in st.session_state:
    new_candidate()
candidate_id = st.session_state["chat_id"]

with st.sidebar:
    ui.language_switch()
    st.toggle(t("chat.share"), key="share_with_dashboard", on_change=new_candidate, help=t("chat.share_help"))
    st.button(t("chat.new"), key="new_candidate", on_click=new_candidate, icon=":material/person_add:",
              width="stretch")
    st.button(t("chat.wait"), key="wait_24h", on_click=wait_a_day, icon=":material/schedule:", width="stretch",
              help=t("chat.wait_help"))
    st.caption(t("chat.candidate", id=candidate_id))
    st.caption(t("chat.rate_hint"))
    st.link_button(t("link.dashboard"), config.dashboard_url(), icon=":material/open_in_new:", width="stretch")

st.title(t("chat.title"))
if st.session_state.get("share_with_dashboard"):
    st.warning(t("chat.shared_warning"))
else:
    st.caption(t("chat.notice"))
if st.session_state.get("flash"):
    st.warning(t(st.session_state["flash"]))

record = store.get(candidate_id)
chat_language = Language((record.state or {}).get("language") or language) if record else language


def tc(key: str, **values) -> str:
    """A text for the candidate's side of the screen: it follows the language the candidate writes in."""
    return PACK.get(key, chat_language, **values)


chat_side, inspector_side = st.columns([3, 2], gap="medium")

with chat_side:
    with st.container(border=True):
        for message in store.messages(candidate_id):
            with st.chat_message("assistant" if message.role == "agent" else "user"):
                st.text(message.text)  # candidate and model text is never rendered as Markdown or HTML
        prompt = st.chat_input(tc("chat.input"), key="chat_message", submit_mode="disable")
    offered = record is not None and (record.state or {}).get("cv") == "offered"
    if offered:
        st.caption(SAZON_CLIENT.spec.pack.pick(SAZON_CLIENT.spec.pack.cv.notice, chat_language))
        upload = st.file_uploader(tc("chat.cv_label"), type=["pdf"], key=f"cv_{candidate_id}", max_upload_size=2)
        if st.session_state.get("_cv_refused"):
            st.warning(st.session_state.pop("_cv_refused"))
        if upload is not None and st.session_state.get("_cv_seen") != upload.file_id:
            st.session_state["_cv_seen"] = upload.file_id  # an unusable file is answered once, not on every rerun
            saved_before = len(store.messages(candidate_id))
            with st.spinner(tc("chat.thinking")):
                try:
                    reply = turn.handle_cv(llm, store, SAZON_CLIENT, candidate_id, upload.getvalue(), datetime.now())
                except Exception as error:  # a database or network failure: say so, log it, never show internals
                    st.error(tc("chat.failed"))
                    st.caption(log_error(error, datetime.now(), config.LOG_PATH))
                    st.stop()
            if len(store.messages(candidate_id)) == saved_before:  # refused: the reply is not part of the chat
                st.session_state["_cv_refused"] = reply
            st.rerun()
    if slot_flow.may_choose_time(store, SAZON_CLIENT, candidate_id):  # the button, then a month of days that have free times, then that day's 15-minute times
        country = slot_flow.country_of(store, SAZON_CLIENT, candidate_id)

        def open_picker() -> None:
            st.session_state.update(picker_open=True, picker_month=(date.today() + timedelta(days=1)).replace(day=1), picker_day=None)

        def move_month(step: int) -> None:
            month = st.session_state["picker_month"]
            st.session_state.update(picker_month=(month + timedelta(days=32 if step > 0 else -1)).replace(day=1), picker_day=None)

        def book(time_id: int) -> None:
            try:
                turn.handle_slot(store, SAZON_CLIENT, candidate_id, time_id, datetime.now())
            except Exception as error:  # a database or network failure: say so, log it, never show internals
                st.session_state["flash"] = "chat.failed"
                log_error(error, datetime.now(), config.LOG_PATH)
            st.session_state.update(picker_open=False, picker_day=None)

        st.button(tc("picker.open"), key="pick_open", icon=":material/event:", type="primary", on_click=open_picker)
        if st.session_state.get("picker_open") and country:
            month = st.session_state["picker_month"]
            free_days = store.free_days(country, month, datetime.now())
            with st.container(border=True):
                with st.container(horizontal=True, vertical_alignment="center"):
                    st.button(tc("picker.prev"), key="pick_prev", icon=":material/chevron_left:", on_click=move_month, args=(-1,))
                    st.markdown(f"**{tc(f'month.{month.month}')} {month.year}**")
                    st.button(tc("picker.next"), key="pick_next", icon=":material/chevron_right:", on_click=move_month, args=(1,))
                head = st.columns(7)
                for column, weekday in zip(head, range(7)):
                    column.caption(tc(f"cal.day.{weekday}"))
                for week in calendar.monthcalendar(month.year, month.month):
                    for column, number in zip(st.columns(7), week):
                        if number:
                            day = date(month.year, month.month, number)
                            column.button(str(number), key=f"pick_day_{day.isoformat()}", disabled=day not in free_days,
                                          width="stretch", on_click=lambda d=day: st.session_state.update(picker_day=d))
                if not free_days:
                    st.caption(tc("picker.none"))
                chosen_day = st.session_state.get("picker_day")
                if chosen_day and chosen_day in free_days:
                    st.markdown(f"**{tc('picker.times', day=f'{chosen_day:%d/%m}')}**")
                    free_times = store.free_slots_on(country, chosen_day, datetime.now())
                    for row in range(0, len(free_times), 6):
                        for column, found in zip(st.columns(6), free_times[row:row + 6]):
                            column.button(f"{found.starts_at:%H:%M}", key=f"pick_time_{found.id}", width="stretch",
                                          on_click=book, args=(found.id,))
    if prompt:
        with st.chat_message("user"):
            st.text(prompt)
        now_in = language_of(prompt, None, chat_language)  # the message itself: nothing is saved yet on the first one
        with st.spinner(PACK.get("chat.thinking", now_in)):
            try:
                turn.handle_message(llm, store, SAZON_CLIENT, candidate_id, prompt, datetime.now())
            except Exception as error:  # a database or network failure: say so, log it, never show internals
                st.error(PACK.get("chat.failed", now_in))
                st.caption(log_error(error, datetime.now(), config.LOG_PATH))
                st.stop()
        st.rerun()

with inspector_side:
    found = inspect(store, SAZON_CLIENT, candidate_id, language)
    with st.container(border=True):
        st.subheader(t("inspector.title"))
        if found is not None:
            st.markdown(f"**{t('inspector.outcome')}**")
            if found.outcome:
                st.badge(view.outcome_label(found.outcome), color=OUTCOME_COLOR[found.outcome])
            if found.booking:
                st.success(t("inspector.booking", label=view.call_label(found.booking)))
            st.markdown(f"**{t('inspector.data')}**")
            st.json(found.extracted)
            st.markdown(f"**{t('inspector.card')}**")
            st.text(found.card)
            st.markdown(f"**{t('inspector.queued')}**")
            if found.queued:
                for entry in found.queued:
                    st.text(entry.text)
                st.button(t("inspector.deliver"), key="deliver_queued", on_click=deliver_queued)
            else:
                st.caption(t("inspector.queued_none"))
