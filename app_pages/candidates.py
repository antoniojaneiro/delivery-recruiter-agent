from datetime import datetime

import streamlit as st

from sazon import ui
from sazon.ui import t
from screener.model import Outcome, RecruiterStatus
from screener.recruiter_view import PAGE_SIZE, escape_markdown, filter_records, page_of
from sazon.client import SAZON_CLIENT
from sazon.recruiter_view import (OUTCOME_COLOR, STATUS_COLOR, badge_columns, badge_rows, call_label, card_of,
                                  explain_error, name_of, outcome_label, status_label, table_rows)

store = ui.store()
recruiter = ui.recruiter_name()
language = ui.language()

st.title(t("cand.title"))
if "erase_message" in st.session_state:
    kind, key = st.session_state.pop("erase_message")
    (st.success if kind == "success" else st.error)(t(key))

records = ui.candidates()
if not records:
    st.info(t("cand.empty"))
    st.stop()

numbers = store.kpi_counts()
with st.container(horizontal=True):
    st.metric(t("kpi.total"), numbers["total"], border=True)
    st.metric(t("kpi.to_contact"), numbers["to_contact"], border=True)
    st.metric(t("kpi.to_review"), numbers["to_review"], border=True, help=t("kpi.to_review_help"))
    st.metric(t("kpi.blocked"), numbers["blocked"], border=True)
    st.metric(t("kpi.stalled"), numbers["stalled"], border=True)

with st.container(horizontal=True, vertical_alignment="bottom"):
    outcomes = st.multiselect(t("filter.outcome"), [o.value for o in Outcome], key="f_outcome",
                              format_func=lambda value: outcome_label(value, language))
    statuses = st.multiselect(t("filter.status"), [s.value for s in RecruiterStatus], key="f_status",
                              format_func=lambda value: status_label(value, language))
    search = st.text_input(t("filter.search"), key="f_search")
    review_only = st.checkbox(t("filter.review"), key="f_review")

shown = filter_records(records, outcomes, statuses, search, SAZON_CLIENT.spec, review_only)
if not shown:
    st.info(t("cand.none_match"))
    st.stop()

list_side, detail_side = st.columns([5, 4], gap="medium")

with list_side:
    page = st.number_input(t("cand.page"), min_value=1, step=1, value=1, key="page") if len(shown) > PAGE_SIZE else 1
    on_page, pages, page = page_of(shown, page)
    columns = {title: st.column_config.MultiselectColumn(title, options=options, color=colors)
               for title, (options, colors) in badge_columns(language).items()}
    picked = st.dataframe(badge_rows(table_rows(on_page, language), language), hide_index=True, width="stretch",
                          column_config=columns, on_select="rerun", selection_mode="single-row",
                          key="candidate_table", alt=t("cand.title"))
    if pages > 1:
        first = (page - 1) * PAGE_SIZE + 1
        st.caption(t("cand.showing", first=first, last=first + len(on_page) - 1, total=len(shown), page=page,
                     pages=pages))

    by_id = {r.candidate_id: r for r in shown}
    rows = picked.selection.rows
    clicked = on_page[rows[0]].candidate_id if rows and rows[0] < len(on_page) else None
    if clicked != st.session_state.get("_table_pick"):  # a click on the table chooses the candidate
        st.session_state["_table_pick"] = clicked
        if clicked:
            st.session_state["candidate"] = clicked
    if st.session_state.get("candidate") not in by_id:
        if st.session_state.get("candidate"):
            st.warning(t("cand.gone"))
        st.session_state["candidate"] = None
    selected_id = st.selectbox(
        t("cand.view"), list(by_id), index=None, placeholder=t("cand.pick"), key="candidate",
        bind="query-params",
        format_func=lambda cid: f"{name_of(by_id[cid], language)} · {by_id[cid].extracted.get('city', '')} ({cid})")

with detail_side:
    if selected_id is None:
        st.info(t("detail.pick_hint"))
        st.stop()
    record = by_id[selected_id]
    with st.container(border=True):
        st.subheader(escape_markdown(name_of(record, language)))
        with st.container(horizontal=True):
            if record.outcome:
                st.badge(outcome_label(record.outcome, language), color=OUTCOME_COLOR[record.outcome])
            st.badge(status_label(record.status, language), color=STATUS_COLOR[record.status])
        st.markdown(f"**{t('detail.summary')}**")
        st.text(card_of(record, language) or t("detail.no_summary"))
        with st.expander(t("detail.json")):
            st.json(record.extracted)

        st.markdown(f"**{t('detail.call')}**")
        if record.booking:
            caller = t("detail.caller", name=record.booking.recruiter) if record.booking.recruiter else ""
            st.markdown(t("detail.call_line", label=call_label(record.booking, language), caller=caller))
        else:
            waiting = record.outcome == Outcome.QUALIFIED and record.status == RecruiterStatus.NEW
            hint = t("detail.qualified_hint") if waiting else ""
            st.caption(t("detail.no_call") + hint)

    with st.container(border=True):
        st.markdown(f"**{t('detail.manage')}**")
        if not recruiter:
            st.warning(t("common.need_name"))
        statuses_all = [s.value for s in RecruiterStatus]
        if st.session_state.get("_forms_for") != selected_id:
            # Widget keys keep their value when another candidate is chosen: start the forms from this one's data.
            st.session_state.update(new_status=record.status.value, assignee=record.assignee or "", note="",
                                    confirm_erase=False, _forms_for=selected_id)
        with st.form("status_form"):
            new_status = st.selectbox(t("form.status"), statuses_all, index=statuses_all.index(record.status.value),
                                      format_func=lambda value: status_label(value, language), key="new_status")
            save_status = st.form_submit_button(t("form.save_status"), key="save_status")
        with st.form("assign_form"):
            assignee = st.text_input(t("form.assignee"), value=record.assignee or "", key="assignee")
            save_assignee = st.form_submit_button(t("form.save_assignee"), key="save_assignee")
        with st.form("note_form", clear_on_submit=True):
            note = st.text_area(t("form.note"), key="note")
            save_note = st.form_submit_button(t("form.save_note"), key="save_note")

        if save_status or save_assignee or save_note:
            try:
                if not recruiter:
                    raise ValueError(t("common.need_name"))
                now = datetime.now()
                if save_status:
                    store.set_status(selected_id, RecruiterStatus(new_status), recruiter, now)
                if save_assignee:
                    store.assign(selected_id, assignee, recruiter, now)
                if save_note:
                    store.add_note(selected_id, note, recruiter, now)
            except (ValueError, LookupError) as error:
                st.error(explain_error(error, language))
            else:
                st.rerun()

        for item in store.notes(selected_id):
            st.text(f"{item.author} · {item.at:%Y-%m-%d %H:%M}")
            st.text(item.text)

    def erase_selected() -> None:
        """Runs before the page is redrawn, so the selection and the confirmation can be reset safely."""
        if not st.session_state.get("confirm_erase"):
            st.session_state["erase_message"] = ("error", "erase.need_check")
            return
        store.erase_candidate(st.session_state["candidate"], f"recruiter:{recruiter}", datetime.now(), "request")
        st.session_state["candidate"] = None
        st.session_state["confirm_erase"] = False
        st.session_state["erase_message"] = ("success", "erase.done")

    with st.expander(t("erase.title")):
        st.caption(t("erase.caption"))
        st.checkbox(t("erase.confirm"), key="confirm_erase")
        st.button(t("erase.button"), key="erase_candidate", on_click=erase_selected)

    conversation, audit = st.tabs([t("tab.conversation"), t("tab.audit")])
    with conversation:
        messages = store.messages(selected_id)
        if not messages:
            st.caption(t("detail.no_messages"))
        for message in messages:
            with st.chat_message("assistant" if message.role == "agent" else "user"):
                st.text(message.text)  # candidate-written text is never rendered as Markdown or HTML
    with audit:
        st.dataframe(
            [{t("audit.when"): e.at.strftime("%Y-%m-%d %H:%M"), t("audit.type"): e.type, t("audit.detail"): e.detail,
              t("audit.actor"): e.actor} for e in store.events(selected_id)],
            hide_index=True, width="stretch", alt=t("tab.audit"))
