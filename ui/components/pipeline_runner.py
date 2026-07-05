"""Streamlit pipeline runner."""

import json

import streamlit as st
from dotenv import load_dotenv

from app.pipeline import run_pipeline
from app.services.file_service import output_path
from app.services.pipeline_service import build_config
from app.services.result_service import load_json
from ui.components.result_viewer import render_keyword_output_table

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
    llm_events = []
    progress_placeholder = st.empty()
    llm_trace_placeholder = st.empty()
    result_placeholder = st.empty()

    def on_step(step):
        steps.append(step)
        _render_progress(progress_placeholder, steps)

    def on_llm_event(event):
        llm_events.append(event)
        _render_llm_trace(llm_trace_placeholder, llm_events)

    _render_progress(progress_placeholder, steps)
    _render_llm_trace(llm_trace_placeholder, llm_events)
    config = build_config()
    with st.spinner("System running..."):
        result = run_pipeline(
            path,
            out,
            config,
            on_step=on_step,
            on_llm_event=on_llm_event,
        )

    st.session_state["latest_result_path"] = out
    st.success(
        f"Done: {len(result.keyword_groups)} keyword groups "
        f"in {result.processing_time_seconds:.2f}s"
    )
    with result_placeholder.container():
        render_keyword_output_table(
            load_json(out),
            caption=f"{path.name} | {len(result.keyword_groups)} keyword group(s)",
        )


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


def _render_llm_trace(placeholder, events):
    with placeholder.container():
        st.subheader("LLM Processing Trace")
        st.caption(
            "Shows prompts, responses, parsed JSON, and an output summary for each LLM batch. "
            "Private model chain-of-thought is not available from the API."
        )

        if not events:
            st.info("LLM trace will appear here after each LLM batch finishes.")
            return

        for index, event in enumerate(events, start=1):
            label = (
                f"{index}. {event.get('stage')} batch "
                f"{event.get('batch_index')}/{event.get('batch_total')} | "
                f"{event.get('provider')}/{event.get('model')} | "
                f"{event.get('seconds', 0):.2f}s"
            )
            with st.expander(label, expanded=index == len(events)):
                st.write(event.get("summary", ""))
                cols = st.columns(2)
                cols[0].metric("Input items", event.get("input_count", 0))
                cols[1].metric("Output groups", event.get("output_count", 0))

                st.markdown("**Prompt sent to LLM**")
                st.code(event.get("prompt", ""), language="text")

                st.markdown("**Raw LLM response**")
                st.code(event.get("raw_response", ""), language="json")

                st.markdown("**Parsed JSON**")
                st.code(
                    json.dumps(
                        event.get("parsed_payload", {}),
                        indent=2,
                        ensure_ascii=False,
                    ),
                    language="json",
                )


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
