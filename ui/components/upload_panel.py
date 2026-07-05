"""Streamlit upload panel."""

import streamlit as st

from app.services.file_service import save_bytes


def render_upload_panel():
    st.subheader("Upload contract")
    file = st.file_uploader(
        "Upload contract",
        type=["pdf", "txt"],
        label_visibility="collapsed",
    )
    if file:
        path = save_bytes(file.name, file.getvalue())
        st.session_state["uploaded_path"] = path
        st.success(f"Uploaded: {path}")

    path = st.session_state.get("uploaded_path")
    if path:
        st.info(f"Current file: {path}")

    return st.session_state.get("uploaded_path")
