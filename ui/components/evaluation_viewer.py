"""Streamlit evaluation viewer."""

from pathlib import Path

import streamlit as st

from app.evaluation.evaluate_ground_truth import compare_keywords

GROUND_TRUTH_DIR = Path("data/ground_truth")


def render_evaluation_viewer():
    st.subheader("Compare with ground truth")

    result = st.text_input(
        "Result JSON path",
        value=str(st.session_state.get("latest_result_path", "")),
    )
    truth = render_ground_truth_input(key_prefix="evaluation")

    if result and truth and st.button("Compare"):
        st.json(compare_keywords(result, truth))


def render_ground_truth_input(
    key_prefix: str = "ground_truth",
    show_upload_label: bool = True,
    show_select_label: bool = True,
):
    uploaded = st.file_uploader(
        "Add ground truth JSON",
        type=["json"],
        key=f"{key_prefix}_ground_truth_upload",
        label_visibility="visible" if show_upload_label else "collapsed",
    )
    if uploaded:
        GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)
        path = GROUND_TRUTH_DIR / Path(uploaded.name).name
        path.write_bytes(uploaded.getvalue())
        st.session_state["ground_truth_path"] = path
        st.success(f"Added ground truth: {path}")

    ground_truth_files = sorted(GROUND_TRUTH_DIR.glob("*.json"))
    if ground_truth_files:
        current = st.session_state.get("ground_truth_path")
        index = _selected_index(ground_truth_files, current)
        selected = st.selectbox(
            "Ground truth JSON",
            ground_truth_files,
            index=index,
            format_func=lambda path: path.name,
            key=f"{key_prefix}_ground_truth_select",
            label_visibility="visible" if show_select_label else "collapsed",
        )
        st.session_state["ground_truth_path"] = selected
        return selected

    return st.session_state.get("ground_truth_path")


def _selected_index(paths, selected_path):
    if not selected_path:
        return 0
    selected = Path(selected_path)
    for index, path in enumerate(paths):
        if path == selected:
            return index
    return 0
