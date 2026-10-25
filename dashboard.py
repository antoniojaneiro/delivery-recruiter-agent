"""Recruiter dashboard for Grupo Sazón (D4, D42, D47, D48). Run with: streamlit run dashboard.py

Reads the same SQLite file as the chat. The agent's data and the recruiter's data are separate:
nothing here can overwrite what the agent stored (D42). There is no login in the prototype, so run
it only on a trusted machine."""
import streamlit as st

st.set_page_config(page_title="Candidatos · Grupo Sazón", page_icon=":material/groups:", layout="wide")

with st.sidebar:
    st.header("Reclutador")
    st.text_input("Tu nombre", key="recruiter", help="Se guarda con cada acción que hagas.")
    st.caption("Sin inicio de sesión: usa la aplicación solo en un equipo de confianza.")

pages = [
    st.Page("app_pages/candidates.py", title="Candidatos", icon=":material/groups:", default=True),
    st.Page("app_pages/slots.py", title="Horarios", icon=":material/calendar_month:"),
]
st.navigation(pages).run()
