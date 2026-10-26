import streamlit as st

from sazon import ui
from screener.funnel import build_funnel
from sazon.client import SAZON_CLIENT
from sazon.recruiter_view import OUTCOME_LABEL

store = ui.store()
funnel = build_funnel(ui.candidates(), SAZON_CLIENT.spec)

st.title("Embudo de candidatos")
st.caption("Cuenta lo que el asistente ya guarda: hasta dónde llega cada persona y cuántas llegan a un reclutador.")

if not funnel.total:
    st.info("Todavía no hay candidatos.")
    st.stop()

cols = st.columns(4)
cols[0].metric("Empezaron", funnel.total)
cols[1].metric("Dieron su consentimiento", funnel.consented, f"{funnel.rates['consent']:.0%}", delta_color="off")
cols[2].metric("Cualificaron", funnel.qualified, f"{funnel.rates['qualified']:.0%}", delta_color="off")
cols[3].metric("Reservaron una llamada", funnel.booked, f"{funnel.rates['booked_of_qualified']:.0%} de los cualificados",
               delta_color="off")
st.caption(f"El agente cerró por su cuenta (sin licencia, fuera de zona o fuera de tema) al "
           f"{funnel.rates['closed_by_agent']:.0%} de los candidatos. Los que ningún reclutador ha revisado "
           "siguen en «Descartes por revisar».")

st.subheader("Hasta dónde llegan")
st.dataframe([{"Etapa": name, "Candidatos": count} for name, count in funnel.stages], hide_index=True, width="stretch")
st.bar_chart({name: count for name, count in funnel.stages}, horizontal=True)

left, right = st.columns(2)
with left:
    st.subheader("Cómo terminan")
    st.dataframe([{"Resultado": OUTCOME_LABEL.get(o, o), "Candidatos": n} for o, n in sorted(funnel.outcomes.items())],
                 hide_index=True, width="stretch")
    if funnel.reasons:
        st.subheader("Motivos")
        st.dataframe([{"Motivo": code, "Candidatos": n} for code, n in sorted(funnel.reasons.items())],
                     hide_index=True, width="stretch")
with right:
    st.subheader("Dónde se quedaron los que siguen abiertos")
    if funnel.stopped_at:
        st.dataframe([{"Falta": what, "Candidatos": n} for what, n in sorted(funnel.stopped_at.items())],
                     hide_index=True, width="stretch")
    else:
        st.caption("Nadie sin terminar.")
