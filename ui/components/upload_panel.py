"""Streamlit upload panel."""

import streamlit as st

from app.services.file_service import save_bytes
from ui.components.evaluation_viewer import render_ground_truth_input


def render_upload_panel():
    contract_col, truth_col = st.columns(2, gap="large")

    with contract_col:
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

    with truth_col:
        st.subheader("Ground truth")
        render_ground_truth_input(
            key_prefix="top",
            show_upload_label=False,
            show_select_label=False,
        )

    return st.session_state.get("uploaded_path")
