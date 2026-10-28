import altair as alt
import streamlit as st

from sazon import ui
from sazon.ui import t
from screener.funnel import build_funnel
from sazon.client import SAZON_CLIENT

store = ui.store()
language = ui.language()
view = ui.view()
spec = SAZON_CLIENT.spec
funnel = build_funnel(store, spec, language)

st.title(t("funnel.title"))
st.caption(t("funnel.caption"))

if not funnel.total:
    st.info(t("funnel.none"))
    st.stop()

texts = spec.recruiter_texts(language)
with st.container(horizontal=True):
    st.metric(texts.started, funnel.total, border=True)
    st.metric(texts.consented, funnel.consented, f"{funnel.rates['consent']:.0%}", delta_color="off", border=True)
    st.metric(texts.qualified, funnel.qualified, f"{funnel.rates['qualified']:.0%}", delta_color="off", border=True)
    st.metric(texts.booked, funnel.booked, t("funnel.booked_rate", rate=f"{funnel.rates['booked_of_qualified']:.0%}"),
              delta_color="off", border=True)
st.caption(t("funnel.closed_by_agent", rate=f"{funnel.rates['closed_by_agent']:.0%}"))

stage_rows = [{"stage": name, "count": count} for name, count in funnel.stages]
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
        st.dataframe([{t("funnel.stage"): name, t("funnel.candidates"): count} for name, count in funnel.stages],
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
