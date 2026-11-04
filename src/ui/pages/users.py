import streamlit as st

from src.auth import require_admin
from src.config import ADMIN_PASSWORD, RECRUITER_PASSWORD


def render() -> None:
    require_admin()
    st.title("Role Passwords")
    st.caption("There is one shared password per role. Passwords are read from the project .env file.")
    st.write({
        "Admin password": "Configured" if ADMIN_PASSWORD else "Not configured",
        "Recruiter password": "Configured" if RECRUITER_PASSWORD else "Not configured",
    })
    st.info("To change a role password, update ADMIN_PASSWORD or RECRUITER_PASSWORD in .env, then restart the app. Password values are never displayed here.")
