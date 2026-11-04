from __future__ import annotations

import streamlit as st

from src.auth import require_user
from src.ui.styles import apply_styles
from src.ui.pages import dashboard, upload, search, compare, documents, users, settings

st.set_page_config(
    page_title="TalentSeek AI",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_styles()
user = require_user()

with st.sidebar:
    st.markdown("# TalentSeek AI")
    st.caption("CV Recruitment & Evidence Search")
    st.divider()
    st.write(f"Signed in as **{user.get('display_name') or user['email']}**")
    st.caption(f"Role: {user['role'].title()}")
    if st.button("Sign out", use_container_width=True):
        st.session_state.pop("current_user", None)
        st.rerun()

workspace_pages = [
    st.Page(dashboard.render, title="Dashboard", url_path="dashboard", icon=":material/dashboard:", default=True),
    st.Page(upload.render, title="Upload CVs", url_path="upload-cvs", icon=":material/upload_file:"),
    st.Page(search.render, title="Candidate Search", url_path="candidate-search", icon=":material/search:"),
    st.Page(compare.render, title="Compare Candidates", url_path="compare-candidates", icon=":material/groups:"),
    st.Page(documents.render, title="CV Documents", url_path="cv-documents", icon=":material/folder_open:"),
    st.Page(settings.render, title="Settings", url_path="settings", icon=":material/settings:"),
]
admin_pages = [
    st.Page(
        users.render,
        title="User Management",
        url_path="user-management",
        icon=":material/manage_accounts:",
    )
]

navigation = {"Workspace": workspace_pages}
if user.get("role") == "admin":
    navigation["Administration"] = admin_pages

selected_page = st.navigation(navigation)
selected_page.run()
