"""Streamlit result viewer."""

import streamlit as st

from app.services.file_service import OUTPUT_DIR, ensure_data_dirs
from app.services.result_service import load_json


def render_result_viewer():
    ensure_data_dirs()
    files = sorted(OUTPUT_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        st.info("No results yet.")
        return
    latest = st.session_state.get("latest_result_path")
    index = files.index(latest) if latest in files else 0
    path = st.selectbox("Result file", files, index=index, format_func=lambda p: p.name)
    data = load_json(path)
    rows = _result_rows(data)

    st.caption(
        f"{data.get('document_name', path.name)} | "
        f"{data.get('total_keyword_groups', len(rows))} keyword group(s)"
    )

    if not rows:
        st.info("No keyword evidence found.")
        return

    st.dataframe(rows, use_container_width=True, hide_index=True)


def _result_rows(data):
    rows = []
    for group in data.get("keyword_groups", []):
        keyword = group.get("representative_keyword", "")
        if group.get("exact_text") or group.get("context_text"):
            rows.append(
                {
                    "Keyword": keyword,
                    "Page": _page_text(group.get("metadata", {}).get("page")),
                    "Text": group.get("exact_text") or group.get("context_text") or "",
                }
            )
            continue

        evidences = group.get("evidences") or []
        if not evidences:
            rows.append(
                {
                    "Keyword": keyword,
                    "Page": _page_text(group.get("metadata", {}).get("page")),
                    "Text": "",
                }
            )
            continue

        for evidence in evidences:
            rows.append(
                {
                    "Keyword": keyword,
                    "Page": _page_text(evidence.get("page")),
                    "Text": evidence.get("exact_text") or evidence.get("context_text") or "",
                }
            )
    return rows


def _page_text(page):
    if page is None:
        return ""
    return str(page)
