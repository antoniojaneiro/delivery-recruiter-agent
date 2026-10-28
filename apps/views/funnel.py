import altair as alt
import streamlit as st

from sazon import ui
from sazon.ui import t
from screener.funnel import build_funnel
from screener.model import RecruiterStatus
from screener.model import RECRUITER_STEPS
from screener.pipeline import Mark, StepState, count_marks, path_for
from screener.recruiter_view import escape_markdown, filter_records
from sazon.client import SAZON_CLIENT

PATH_CHOICES = 20  # candidates offered to pick from; a search narrows them (the full list would be thousands)
MARK_COLOR = {Mark.IN_PROCESS: "blue", Mark.PAUSED: "orange", Mark.OUT: "red", Mark.HIRED: "green"}
STATE_ICON = {StepState.DONE: ":green[:material/check_circle:]", StepState.CURRENT: ":blue[:material/pending:]",
              StepState.STOPPED: ":red[:material/cancel:]", StepState.LEFT: ":gray[:material/radio_button_unchecked:]",
              StepState.SKIPPED: ":orange[:material/redo:]"}
STATE_WORD = {StepState.CURRENT: "funnel.now", StepState.STOPPED: "funnel.stopped_here", StepState.SKIPPED: "funnel.skipped"}

store = ui.store()
language = ui.language()
view = ui.view()
spec = SAZON_CLIENT.spec
recruiter_labels = {step.value: view.status_label(step) for step in RECRUITER_STEPS}
funnel = build_funnel(store, spec, language, recruiter_labels)

st.title(t("funnel.title"))
st.caption(t("funnel.caption"))

if not funnel.total:
    st.info(t("funnel.none"))
    st.stop()

records = ui.candidates()
marks = count_marks(records)
texts = spec.recruiter_texts(language)
with st.container(horizontal=True):
    st.metric(texts.started, funnel.total, border=True)
    st.metric(texts.consented, funnel.consented, f"{funnel.rates['consent']:.0%}", delta_color="off", border=True)
    st.metric(texts.qualified, funnel.qualified, f"{funnel.rates['qualified']:.0%}", delta_color="off", border=True)
    st.metric(texts.booked, funnel.booked, t("funnel.booked_rate", rate=f"{funnel.rates['booked_of_qualified']:.0%}"),
              delta_color="off", border=True)
st.caption(t("funnel.closed_by_agent", rate=f"{funnel.rates['closed_by_agent']:.0%}"))

st.subheader(t("funnel.marks_title"))
with st.container(horizontal=True):
    for mark in (Mark.IN_PROCESS, Mark.PAUSED, Mark.OUT):
        st.metric(t(f"mark.{mark.value}"), marks[mark], border=True)
    st.metric(t("funnel.whole"), funnel.recruiter_stages[-1][1], border=True,  # the chart's last bar: ever hired
              help=t("funnel.whole_help"))

all_stages = funnel.stages + funnel.recruiter_stages
stage_rows = [{"stage": name, "count": count} for name, count in all_stages]
with st.container(border=True):
    st.subheader(t("funnel.how_far"))
    # one series, so it takes the theme's first colour and needs no legend
    bars = alt.Chart(alt.Data(values=stage_rows)).mark_bar(cornerRadiusEnd=4, size=18).encode(
        y=alt.Y("stage:N", sort=None, title=None, axis=alt.Axis(labelLimit=260)),
        x=alt.X("count:Q", title=None, axis=alt.Axis(tickMinStep=1)),
        tooltip=[alt.Tooltip("stage:N", title=t("funnel.stage")), alt.Tooltip("count:Q", title=t("funnel.candidates"))])
    numbers = bars.mark_text(align="left", dx=4).encode(text="count:Q")
    st.altair_chart(bars + numbers, width="stretch", alt=t("funnel.how_far"))
    with st.expander(t("funnel.table")):
        st.dataframe([{t("funnel.stage"): name, t("funnel.candidates"): count} for name, count in all_stages],
                     hide_index=True, width="stretch", alt=t("funnel.how_far"))

left, right = st.columns(2)
with left:
    st.subheader(t("funnel.ends"))
    st.dataframe([{t("funnel.result"): view.outcome_label(o), t("funnel.candidates"): n}
                  for o, n in sorted(funnel.outcomes.items())], hide_index=True, width="stretch")
    if funnel.reasons:
        st.subheader(t("funnel.reasons"))
        st.dataframe([{t("funnel.reason"): spec.reason_text(code, language), t("funnel.candidates"): n}
                      for code, n in sorted(funnel.reasons.items())], hide_index=True, width="stretch")
with right:
    st.subheader(t("funnel.stopped"))
    if funnel.stopped_at:
        st.dataframe([{t("funnel.missing"): what, t("funnel.candidates"): n}
                      for what, n in sorted(funnel.stopped_at.items())], hide_index=True, width="stretch")
    else:
        st.caption(t("funnel.nobody"))

st.subheader(t("funnel.path_title"))
st.caption(t("funnel.path_hint"))
by_id = {r.candidate_id: r for r in records}
with st.container(horizontal=True, vertical_alignment="bottom"):
    search = st.text_input(t("funnel.path_search"), key="path_search")
    choices = [r.candidate_id for r in filter_records(records, [], [], search, spec, False)[:PATH_CHOICES]]
    if st.session_state.get("path_candidate") in by_id and st.session_state["path_candidate"] not in choices:
        choices.append(st.session_state["path_candidate"])  # a chosen candidate stays chosen while the search changes
    if st.session_state.get("path_candidate") not in by_id:
        st.session_state["path_candidate"] = None  # erased since the last time
    chosen = st.selectbox(t("funnel.path_pick"), choices, index=None, placeholder=t("funnel.path_pick_placeholder"),
                          key="path_candidate",
                          format_func=lambda cid: f"{view.name_of(by_id[cid])} · {by_id[cid].extracted.get(spec.area_field, '')} ({cid})")

if chosen is None:
    if search and not choices:
        st.caption(t("funnel.path_none"))
    st.stop()

record = by_id[chosen]
history = [RecruiterStatus(e.detail) for e in store.events(chosen) if e.type == "recruiter_status"]
labels = {key: t(f"funnel.step.{key}") for key in ("started", "consent", "qualified", "booked")} | recruiter_labels
path = path_for(record, history, client=SAZON_CLIENT, language=language, labels=labels)
with st.container(border=True):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader(escape_markdown(view.name_of(record)))
        st.badge(t(f"mark.{path.mark.value}"), color=MARK_COLOR[path.mark])
    if path.why:
        st.caption(t("funnel.why", reasons="; ".join(path.why)))
    agent_side, recruiter_side = st.columns(2)
    recruiter_keys = {step.value for step in RECRUITER_STEPS}
    for side, wanted in ((agent_side, False), (recruiter_side, True)):
        with side:
            lines = []
            for step in path.steps:
                if (step.key in recruiter_keys) != wanted:
                    continue
                word = f" — {t(STATE_WORD[step.state])}" if step.state in STATE_WORD else ""
                label = escape_markdown(step.label[:1].upper() + step.label[1:])  # the client's labels are lower case
                text = f"{STATE_ICON[step.state]} {label}{word}"
                lines.append(f"**{text}**" if step.state in (StepState.CURRENT, StepState.STOPPED) else text)
            st.markdown("  \n".join(lines))  # one tight block per column
    st.caption(t("funnel.legend"))
