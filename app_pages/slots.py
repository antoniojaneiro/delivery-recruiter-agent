from datetime import datetime, time

import streamlit as st

from sazon import slot_flow, ui
from sazon.sazon_client import SAZON_CLIENT
from sazon.model import Language
from sazon.phrasing import slot_label
from sazon.recruiter_view import COUNTRY_LABEL, escape_markdown, explain_error, name_of, slot_state

store = ui.store()
recruiter = ui.recruiter_name()
NEEDS_NAME = "Escribe tu nombre en la barra lateral para registrar acciones."

st.title("Horarios para llamadas")
st.caption("El agente ofrece a cada candidato cualificado los tres próximos horarios libres de su país. "
           "La hora es la del reloj del país: un candidato en México ve la hora de México.")



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
    except (ValueError, LookupError) as error:
        st.error(explain_error(error))
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
            try:
                booked_by = store.cancel_slot(to_cancel, recruiter, now)
            except (ValueError, LookupError) as error:
                st.error(explain_error(error))
                st.stop()
            if booked_by:
                booked = store.get(booked_by)
                who = f"{escape_markdown(name_of(booked))} ({booked_by})" if booked else booked_by
                told = slot_flow.notify_cancelled(store, SAZON_CLIENT, booked_by, now.replace(tzinfo=None))
                st.warning(f"Ese horario estaba reservado por {who}. "
                           + ("El asistente le dejará un aviso en su chat. " if told else "No se pudo dejar el aviso: escríbele tú. ")
                           + "Se quedó sin llamada reservada.")
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
