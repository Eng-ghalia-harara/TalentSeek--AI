from __future__ import annotations

from typing import Any

import streamlit as st

from src.config import ADMIN_PASSWORD, RECRUITER_PASSWORD
from src.database import get_active_user, get_or_create_role_user
from src.passwords import verify_role_password


def require_user() -> dict[str, Any]:
    """Require credentials for an active account with the selected database role."""
    session_user = st.session_state.get("current_user")
    if session_user:
        try:
            user = get_active_user(int(session_user["id"]))
        except Exception as exc:
            st.error(f"Could not verify the active account: {exc}")
            st.stop()
        if user is not None:
            st.session_state["current_user"] = user
            return user
        st.session_state.pop("current_user", None)
        st.error("This account is no longer active. Sign in with an active account.")

    st.title("TalentSeek AI")
    st.subheader("Sign in to the recruitment workspace")
    with st.form("login_form"):
        role = st.selectbox(
            "Role",
            ["admin", "recruiter"],
            format_func=lambda value: "Admin" if value == "admin" else "Recruiter",
        )
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")

    if submitted:
        if role not in {"admin", "recruiter"}:
            st.error("Select a valid role.")
        elif not (ADMIN_PASSWORD if role == "admin" else RECRUITER_PASSWORD):
            st.error(f"The {role.title()} password is not configured in the project .env file.")
        elif not verify_role_password(role, password, ADMIN_PASSWORD, RECRUITER_PASSWORD):
            st.error("The password is incorrect.")
        else:
            try:
                user = get_or_create_role_user(role)
            except Exception as exc:
                st.error(f"Sign-in could not be completed: {exc}")
                st.stop()
            st.session_state["current_user"] = user
            st.rerun()

    st.stop()


def current_user() -> dict[str, Any]:
    return st.session_state.get("current_user", {})


def require_admin() -> dict[str, Any]:
    user = current_user()
    if user.get("role") != "admin":
        st.error("This page is available to administrators only.")
        st.stop()
    return user
