import streamlit as st

from sazon import ui
from sazon.ui import t
from screener.funnel import build_funnel
from sazon.client import SAZON_CLIENT
from sazon.recruiter_view import outcome_label

store = ui.store()
language = ui.language()
spec = SAZON_CLIENT.spec
funnel = build_funnel(store, spec, language)

st.title(t("funnel.title"))
st.caption(t("funnel.caption"))

if not funnel.total:
    st.info(t("funnel.none"))
    st.stop()

texts = spec.recruiter_texts(language)
cols = st.columns(4)
cols[0].metric(texts.started, funnel.total)
cols[1].metric(texts.consented, funnel.consented, f"{funnel.rates['consent']:.0%}", delta_color="off")
cols[2].metric(texts.qualified, funnel.qualified, f"{funnel.rates['qualified']:.0%}", delta_color="off")
cols[3].metric(texts.booked, funnel.booked, t("funnel.booked_rate", rate=f"{funnel.rates['booked_of_qualified']:.0%}"),
               delta_color="off")
st.caption(t("funnel.closed_by_agent", rate=f"{funnel.rates['closed_by_agent']:.0%}"))

st.subheader(t("funnel.how_far"))
st.dataframe([{t("funnel.stage"): name, t("funnel.candidates"): count} for name, count in funnel.stages],
             hide_index=True, width="stretch")
st.bar_chart({name: count for name, count in funnel.stages}, horizontal=True)

left, right = st.columns(2)
with left:
    st.subheader(t("funnel.ends"))
    st.dataframe([{t("funnel.result"): outcome_label(o, language), t("funnel.candidates"): n}
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
