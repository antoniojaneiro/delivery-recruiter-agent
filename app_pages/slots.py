from datetime import datetime, time

import streamlit as st

from sazon import ui
from sazon.model import Language
from sazon.phrasing import slot_label
from sazon.recruiter_view import COUNTRY_LABEL, name_of, slot_state

store = ui.store()
recruiter = ui.recruiter_name()
NEEDS_NAME = "Escribe tu nombre en la barra lateral para registrar acciones."

st.title("Horarios para llamadas")
st.caption("El agente ofrece a cada candidato cualificado los tres próximos horarios libres de su país. "
           "La hora es la del reloj del país: un candidato en México ve la hora de México.")


def explain(error: ValueError) -> str:
    text = str(error)
    if "does not exist" in text:
        return "Esa hora no existe: ese día cambia la hora y se salta de las 02:00 a las 03:00. Elige otra."
    if "past or too soon" in text:
        return "Ese horario ya ha pasado o falta menos de dos horas. Elige uno más adelante."
    return NEEDS_NAME


with st.form("slot_form"):
    country = st.selectbox("País", list(COUNTRY_LABEL), format_func=COUNTRY_LABEL.get, key="slot_country")
    day = st.date_input("Día", key="slot_date")
    hour = st.time_input("Hora", value=time(10, 0), step=900, key="slot_time")
    caller = st.text_input("Quién llama (opcional)", key="slot_recruiter")
    save = st.form_submit_button("Añadir horario", key="save_slot")

if save:
    try:
        if not recruiter:
            raise ValueError(NEEDS_NAME)
        store.add_slot(country, datetime.combine(day, hour), caller, recruiter, datetime.now().astimezone())
    except ValueError as error:
        st.error(explain(error))
    else:
        st.success("Horario añadido.")

now = datetime.now().astimezone()
slots = store.slots(now)

if slots:
    def describe(slot_id: int) -> str:
        slot = next(s for s in slots if s.id == slot_id)
        return f"{COUNTRY_LABEL[slot.country]} · {slot_label(slot.starts_at, Language.ES)}"

    with st.container(horizontal=True, vertical_alignment="bottom"):
        to_cancel = st.selectbox("Cancelar un horario", [s.id for s in slots], format_func=describe,
                                 key="cancel_slot")
        cancel = st.button("Cancelar horario", key="confirm_cancel")
    if cancel:
        if not recruiter:
            st.error(NEEDS_NAME)
        else:
            booked_by = store.cancel_slot(to_cancel, recruiter, now)
            if booked_by:
                booked = store.get(booked_by)
                who = f"{name_of(booked)} ({booked_by})" if booked else booked_by
                st.warning(f"Ese horario estaba reservado por {who}. Avisa al candidato: el asistente no puede "
                           "escribirle. Se quedó sin llamada reservada.")
            else:
                st.success("Horario cancelado.")
        slots = store.slots(now)

if not slots:
    st.info("No hay horarios próximos. Añade alguno para que el asistente pueda ofrecerlos.")
else:
    def state(slot) -> str:
        booked = store.get(slot.candidate_id) if slot.candidate_id else None
        return slot_state(slot, name_of(booked) if booked else None, now)

    st.dataframe(
        [{"Id": s.id, "País": COUNTRY_LABEL[s.country], "Día y hora": slot_label(s.starts_at, Language.ES),
          "Llama": s.recruiter or "", "Estado": state(s)} for s in slots],
        hide_index=True, width="stretch")
