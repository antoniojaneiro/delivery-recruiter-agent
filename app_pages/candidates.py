from datetime import datetime

import streamlit as st

from sazon import ui
from sazon.model import Outcome, RecruiterStatus
from sazon.recruiter_view import (OUTCOME_LABEL, STATUS_LABEL, call_label, filter_records, kpis, name_of,
                                  table_rows)

store = ui.store()
recruiter = ui.recruiter_name()

st.title("Candidatos")
if "erase_message" in st.session_state:
    kind, text = st.session_state.pop("erase_message")
    (st.success if kind == "success" else st.error)(text)

records = store.list_candidates()
if not records:
    st.info("No hay candidatos todavía. Aparecerán aquí cuando alguien hable con el asistente.")
    st.stop()

numbers = kpis(records)
cols = st.columns(5)
cols[0].metric("Candidatos", numbers["total"])
cols[1].metric("Cualificados por contactar", numbers["to_contact"])
cols[2].metric("Descartes por revisar", numbers["to_review"],
               help="Candidatos que el agente descartó (sin licencia, fuera de zona o fuera de tema) y que "
                    "ningún reclutador ha revisado todavía. Ponles un estado cuando los hayas mirado.")
cols[3].metric("Bloqueados", numbers["blocked"])
cols[4].metric("Sin respuesta", numbers["stalled"])

with st.container(horizontal=True, vertical_alignment="bottom"):
    outcomes = st.multiselect("Estado del agente", [o.value for o in Outcome], key="f_outcome",
                              format_func=lambda value: OUTCOME_LABEL[value])
    statuses = st.multiselect("Estado del reclutador", [s.value for s in RecruiterStatus], key="f_status",
                              format_func=lambda value: STATUS_LABEL[value])
    search = st.text_input("Buscar por nombre, ciudad o id", key="f_search")
    review_only = st.checkbox("Solo descartes por revisar", key="f_review")

shown = filter_records(records, outcomes, statuses, search, review_only)
if not shown:
    st.info("Ningún candidato coincide con los filtros.")
    st.stop()

st.dataframe(table_rows(shown), hide_index=True, width="stretch")

by_id = {r.candidate_id: r for r in shown}
if st.session_state.get("candidate") not in by_id:
    st.session_state["candidate"] = None  # e.g. the candidate was just erased
selected_id = st.selectbox(
    "Ver candidato", list(by_id), index=None, placeholder="Elige un candidato", key="candidate",
    bind="query-params",
    format_func=lambda cid: f"{name_of(by_id[cid])} · {by_id[cid].extracted.get('city', '')} ({cid})")
if selected_id is None:
    st.stop()

record = by_id[selected_id]
st.divider()
st.subheader(name_of(record))
left, right = st.columns([3, 2])

with left:
    st.markdown("**Resumen del agente**")
    st.text(record.summary or "Sin resumen todavía.")
    with st.expander("Datos validados (JSON)"):
        st.json(record.extracted)

with right:
    st.markdown("**Llamada**")
    if record.booking:
        caller = f" · llama {record.booking.recruiter}" if record.booking.recruiter else ""
        st.markdown(f"**Llamada:** {call_label(record.booking)}{caller}")
    else:
        hint = " Está cualificado: contáctalo." if record.outcome == Outcome.QUALIFIED else ""
        st.caption("Sin llamada reservada." + hint)

    st.markdown("**Gestión del reclutador**")
    if not recruiter:
        st.warning("Escribe tu nombre en la barra lateral para registrar acciones.")
    statuses_all = [s.value for s in RecruiterStatus]
    with st.form("status_form"):
        new_status = st.selectbox("Estado", statuses_all, index=statuses_all.index(record.status.value),
                                  format_func=lambda value: STATUS_LABEL[value], key="new_status")
        save_status = st.form_submit_button("Guardar estado", key="save_status")
    with st.form("assign_form"):
        assignee = st.text_input("Asignado a", value=record.assignee or "", key="assignee")
        save_assignee = st.form_submit_button("Guardar asignación", key="save_assignee")
    with st.form("note_form", clear_on_submit=True):
        note = st.text_area("Nota", key="note")
        save_note = st.form_submit_button("Añadir nota", key="save_note")

    if save_status or save_assignee or save_note:
        try:
            if not recruiter:
                raise ValueError("Escribe tu nombre en la barra lateral para registrar acciones.")
            now = datetime.now()
            if save_status:
                store.set_status(selected_id, RecruiterStatus(new_status), recruiter, now)
            if save_assignee:
                store.assign(selected_id, assignee, recruiter, now)
            if save_note:
                store.add_note(selected_id, note, recruiter, now)
        except ValueError as error:
            st.error(str(error) if "nombre" in str(error) else "Revisa lo que has escrito: no puede estar vacío.")
        else:
            st.rerun()

    for item in store.notes(selected_id):
        st.text(f"{item.author} · {item.at:%Y-%m-%d %H:%M}")
        st.text(item.text)


def erase_selected() -> None:
    """Runs before the page is redrawn, so the selection and the confirmation can be reset safely."""
    if not st.session_state.get("confirm_erase"):
        st.session_state["erase_message"] = ("error", "Marca la casilla de confirmación para borrar.")
        return
    store.erase_candidate(st.session_state["candidate"], f"recruiter:{recruiter}", datetime.now(), "request")
    st.session_state["candidate"] = None
    st.session_state["confirm_erase"] = False
    st.session_state["erase_message"] = ("success", "Datos borrados. Solo queda un registro anónimo de quién los borró.")


with st.expander("Borrar los datos de este candidato"):
    st.caption("Derecho de supresión: elimina sus respuestas, la conversación, las notas y la reserva. "
               "No se puede deshacer.")
    st.checkbox("Confirmo que quiero borrar todos los datos de este candidato", key="confirm_erase")
    st.button("Borrar datos", key="erase_candidate", on_click=erase_selected)

st.divider()
conversation, audit = st.tabs(["Conversación", "Auditoría"])
with conversation:
    messages = store.messages(selected_id)
    if not messages:
        st.caption("Sin mensajes.")
    for message in messages:
        with st.chat_message("assistant" if message.role == "agent" else "user"):
            st.text(message.text)  # candidate-written text is never rendered as Markdown or HTML
with audit:
    st.dataframe(
        [{"Cuándo": e.at.strftime("%Y-%m-%d %H:%M"), "Tipo": e.type, "Detalle": e.detail, "Actor": e.actor}
         for e in store.events(selected_id)],
        hide_index=True, width="stretch")
