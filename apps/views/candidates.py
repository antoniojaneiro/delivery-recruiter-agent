from datetime import datetime

import streamlit as st

from sazon import ui
from sazon.ui import t
from screener.model import STAGES, Outcome, RecruiterStatus
from screener.recruiter_rules import TO_CONTACT
from screener.recruiter_view import (OUTCOME_COLOR, PAGE_SIZE, STATUS_COLOR, escape_markdown, filter_records, page_of,
                                     table_height)
from sazon.client import SAZON_CLIENT

store = ui.store()
recruiter = ui.recruiter_name()
view = ui.view()

st.title(t("cand.title"))
if "erase_message" in st.session_state:
    kind, key = st.session_state.pop("erase_message")
    (st.success if kind == "success" else st.error)(t(key))

records = ui.candidates()
ui.watch_for_changes()
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

stage_values = [s.value for s in STAGES]
st.session_state["f_status"] = [v for v in st.session_state.get("f_status", []) if v in stage_values]  # a tab open since the states changed
with st.container(horizontal=True, vertical_alignment="bottom"):
    outcomes = st.multiselect(t("filter.outcome"), [o.value for o in Outcome], key="f_outcome", placeholder=t("filter.choose"),
                              format_func=lambda value: view.outcome_label(value))
    statuses = st.multiselect(t("filter.status"), stage_values, key="f_status", placeholder=t("filter.choose"),
                              format_func=lambda value: view.status_label(value))
    search = st.text_input(t("filter.search"), key="f_search")
    review_only = st.checkbox(t("filter.review"), key="f_review")

shown = filter_records(records, outcomes, statuses, search, SAZON_CLIENT.spec, review_only)
if not shown:
    st.info(t("cand.none_match"))
    st.stop()


page = st.number_input(t("cand.page"), min_value=1, step=1, value=1, key="page",
                       width=160) if len(shown) > PAGE_SIZE else 1
on_page, pages, page = page_of(shown, page)
columns = {title: st.column_config.MultiselectColumn(title, options=options, color=colors)
           for title, (options, colors) in view.badge_columns().items()}
picked = st.dataframe(view.badge_rows(view.table_rows(on_page, {r.email: r.name for r in store.recruiters()})), hide_index=True, width="stretch",
                      height=table_height(len(on_page)),  # as tall as its rows up to a limit, then it scrolls inside
                      column_config=columns, on_select="rerun", selection_mode="single-row",
                      key="candidate_table", alt=t("cand.title"))
if pages > 1:
    first = (page - 1) * PAGE_SIZE + 1
    st.caption(t("cand.showing", first=first, last=first + len(on_page) - 1, total=len(shown), page=page,
                 pages=pages))

by_id = {r.candidate_id: r for r in shown}
clicked_rows = tuple(picked.selection.rows)
if clicked_rows != st.session_state.get("_table_rows", ()):  # only a new click on the table chooses a candidate
    st.session_state["_table_rows"] = clicked_rows
    if clicked_rows and clicked_rows[0] < len(on_page):
        st.session_state["candidate"] = on_page[clicked_rows[0]].candidate_id
if st.session_state.get("candidate") not in by_id:
    if st.session_state.get("candidate"):
        st.warning(t("cand.gone"))
    st.session_state["candidate"] = None
pickable = [r.candidate_id for r in on_page]  # this page only: the browser is not sent every candidate each time
for named in (st.session_state.get("candidate"), st.query_params.get("candidate")):
    if named in by_id and named not in pickable:
        pickable.append(named)  # one named by a link or chosen on an earlier page stays selected
selected_id = st.selectbox(
    t("cand.view"), pickable, index=None, placeholder=t("cand.pick"), key="candidate",
    bind="query-params",
    format_func=lambda cid: f"{view.name_of(by_id[cid])} · {by_id[cid].extracted.get(SAZON_CLIENT.spec.area_field, '')} ({cid})")

if selected_id is None:
    st.caption(t("detail.pick_hint"))
    st.stop()
record = by_id[selected_id]
st.subheader(escape_markdown(view.name_of(record)))
with st.container(horizontal=True):
    if record.outcome:
        st.badge(view.outcome_label(record.outcome), color=OUTCOME_COLOR[record.outcome])
    st.badge(view.status_label(record.stage), color=STATUS_COLOR[record.stage])
info_side, manage_side = st.columns(2, gap="medium")

with info_side:
    with st.container(border=True):
        st.markdown(f"**{t('detail.summary')}**")
        st.text(view.card(record) or t("detail.no_summary"))
        with st.expander(t("detail.json")):
            st.json(record.extracted)
        cv = store.cv(selected_id)
        if cv is not None:  # the file is never drawn on the page: a recruiter downloads and opens it
            st.download_button(t("detail.cv_download", size=max(1, cv.size // 1024)), data=cv.data,
                               file_name=f"cv-{selected_id}.pdf", mime="application/pdf", icon=":material/description:",
                               key="download_cv")

        st.markdown(f"**{t('detail.call')}**")
        if record.booking:
            holder = store.get_recruiter(record.booking.recruiter) if record.booking.recruiter else None
            caller = t("detail.caller", name=holder.name if holder else record.booking.recruiter) if record.booking.recruiter else ""
            st.markdown(t("detail.call_line", label=view.call_label(record.booking), caller=caller))
        else:
            hint = t("detail.qualified_hint") if TO_CONTACT.matches(record) else ""
            st.caption(t("detail.no_call") + hint)

with manage_side:
    with st.container(border=True):
        st.markdown(f"**{t('detail.manage')}**")
        if not recruiter:
            st.warning(t("common.need_name"))
        statuses_all = stage_values
        if st.session_state.get("_forms_for") != selected_id:
            # Widget keys keep their value when another candidate is chosen: start the forms from this one's data.
            st.session_state.update(new_status=record.stage.value, note="", confirm_erase=False, _forms_for=selected_id)
        with st.form("status_form"):
            new_status = st.selectbox(t("form.status"), statuses_all, index=statuses_all.index(record.stage.value),
                                      format_func=lambda value: view.status_label(value), key="new_status")
            save_status = st.form_submit_button(t("form.save_status"), key="save_status")
        with st.form("note_form", clear_on_submit=True):
            note = st.text_area(t("form.note"), key="note")
            save_note = st.form_submit_button(t("form.save_note"), key="save_note")

        if save_status or save_note:
            try:
                if not recruiter:
                    raise ValueError(t("common.need_name"))
                now = datetime.now()
                if save_status:
                    store.set_stage(selected_id, RecruiterStatus(new_status), recruiter, now)
                if save_note:
                    store.add_note(selected_id, note, recruiter, now)
            except (ValueError, LookupError) as error:
                st.error(view.explain_error(error))
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
