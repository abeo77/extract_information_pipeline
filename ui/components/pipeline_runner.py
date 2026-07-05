"""Streamlit pipeline runner."""

import streamlit as st
from dotenv import load_dotenv

from app.pipeline import run_pipeline
from app.services.file_service import output_path
from app.services.pipeline_service import build_config
from app.services.result_service import load_json

load_dotenv()


def render_pipeline_runner(path):
    st.subheader("Run")
    if not path:
        st.info("Upload a PDF or TXT file first.")
        return

    out = output_path(path.name)
    st.caption(f"Output: {out}")

    if not st.button("RUN", type="primary"):
        return

    steps = []
    progress_placeholder = st.empty()
    result_placeholder = st.empty()

    def on_step(step):
        steps.append(step)
        _render_progress(progress_placeholder, steps)

    _render_progress(progress_placeholder, steps)
    config = build_config()
    with st.spinner("System running..."):
        result = run_pipeline(path, out, config, on_step=on_step)

    st.session_state["latest_result_path"] = out
    st.success(
        f"Done: {len(result.keyword_groups)} keyword groups "
        f"in {result.processing_time_seconds:.2f}s"
    )
    result_placeholder.json(load_json(out))


def _render_progress(placeholder, steps):
    if not steps:
        placeholder.info("System running will show each processing step here.")
        return

    rows = [
        {
            "Step": step["label"],
            "Time": f"{step['seconds']:.2f}s",
            "Details": _step_details(step),
        }
        for step in steps
    ]
    placeholder.table(rows)


def _step_details(step):
    details = []
    if "pages" in step:
        details.append(f"{step['pages']} page(s)")
    if "segments" in step:
        details.append(f"{step['segments']} segment(s)")
    if "keyword_groups" in step:
        details.append(f"{step['keyword_groups']} keyword group(s)")
    if "batches" in step:
        details.append(f"{step['batches']} batch(es)")
    return ", ".join(details)
