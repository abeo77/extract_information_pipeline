"""Streamlit UI for the contract keyword pipeline."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.components.pipeline_runner import render_pipeline_runner
from ui.components.result_viewer import render_result_viewer
from ui.components.segment_viewer import render_segment_viewer
from ui.components.upload_panel import render_upload_panel

st.set_page_config(page_title="Contract Keyword Pipeline", layout="wide")
st.title("Contract Keyword Pipeline")

uploaded_path = render_upload_panel()
tabs = st.tabs(["Segments", "RUN", "Results"])

with tabs[0]:
    render_segment_viewer(uploaded_path)
with tabs[1]:
    render_pipeline_runner(uploaded_path)
with tabs[2]:
    render_result_viewer()
