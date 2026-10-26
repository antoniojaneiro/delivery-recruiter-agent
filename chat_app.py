"""A browser chat for trying Grupo Sazón's agent (D66). Run with: streamlit run chat_app.py

It runs the same turn code as the terminal chat and the real model, but saves into a demo database (SAZON_DEMO_DB,
data/demo.db by default), never the recruiters' one. There is no login: it is meant to run on your own computer.
On the right, an inspector shows what the agent has understood, read from that database."""
import uuid
from datetime import datetime

import streamlit as st

from screener import gemini, turn
from screener.chat import log_error
from screener.inspector import inspect
from screener.llm import LLMError
from screener.store import Store

from sazon import config, ui
from sazon.client import SAZON_CLIENT
from sazon.recruiter_view import OUTCOME_COLOR, call_label, outcome_label
from sazon.ui import t

st.set_page_config(page_title=t("chat.page_title"), page_icon=":material/chat:", layout="wide")


@st.cache_resource
def open_demo_store(path: str) -> Store:
    return Store(path, calendar=SAZON_CLIENT.calendar)


store = open_demo_store(str(config.demo_db_path()))
language = ui.language()

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
    candidate_id = uuid.uuid4().hex[:12]
    while store.get(candidate_id) is not None:  # never merge two test candidates into one record
        candidate_id = uuid.uuid4().hex[:12]
    turn.start(store, SAZON_CLIENT, candidate_id, datetime.now())  # the disclosure, once per candidate
    st.session_state["chat_id"] = candidate_id
    st.session_state.pop("flash", None)


def wait_a_day() -> None:
    reply = turn.wait_24h(llm, store, SAZON_CLIENT, st.session_state["chat_id"], datetime.now())
    st.session_state["flash"] = None if reply else "chat.wait_nothing"


def deliver_queued() -> None:
    for entry in store.outbox_pending(st.session_state["chat_id"]):
        store.mark_delivered(entry.id, datetime.now())


if "chat_id" not in st.session_state:
    new_candidate()
candidate_id = st.session_state["chat_id"]

with st.sidebar:
    ui.language_switch()
    st.button(t("chat.new"), key="new_candidate", on_click=new_candidate, icon=":material/person_add:",
              width="stretch")
    st.button(t("chat.wait"), key="wait_24h", on_click=wait_a_day, icon=":material/schedule:", width="stretch",
              help=t("chat.wait_help"))
    st.caption(t("chat.candidate", id=candidate_id))
    st.caption(t("chat.rate_hint"))

st.title(t("chat.title"))
st.info(t("chat.notice"))
if st.session_state.get("flash"):
    st.warning(t(st.session_state["flash"]))

chat_side, inspector_side = st.columns([3, 2], gap="medium")

with chat_side:
    with st.container(border=True):
        for message in store.messages(candidate_id):
            with st.chat_message("assistant" if message.role == "agent" else "user"):
                st.text(message.text)  # candidate and model text is never rendered as Markdown or HTML
        prompt = st.chat_input(t("chat.input"), key="chat_message", submit_mode="disable")
    if prompt:
        with st.chat_message("user"):
            st.text(prompt)
        with st.spinner(t("chat.thinking")):
            try:
                turn.handle_message(llm, store, SAZON_CLIENT, candidate_id, prompt, datetime.now())
            except Exception as error:  # a database or network failure: say so, log it, never show internals
                st.error(t("chat.failed"))
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
                st.badge(outcome_label(found.outcome, language), color=OUTCOME_COLOR[found.outcome])
            if found.booking:
                st.success(t("inspector.booking", label=call_label(found.booking, language)))
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
