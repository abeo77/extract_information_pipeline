"""Streamlit result viewer."""

from html import escape

import streamlit as st

from app.services.file_service import OUTPUT_DIR, ensure_data_dirs
from app.services.result_service import load_json


TABLE_TITLE = "Contract Keyword Extraction Output"


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

    render_keyword_output_table(
        data,
        caption=(
            f"{data.get('document_name', path.name)} | "
            f"{data.get('total_keyword_groups', len(rows))} keyword group(s)"
        ),
    )


def render_keyword_output_table(data, caption: str | None = None):
    rows = _result_rows(data)

    if caption:
        st.caption(caption)

    if not rows:
        st.info("No keyword evidence found.")
        return

    st.markdown(_table_html(rows), unsafe_allow_html=True)


def _result_rows(data):
    rows = []
    for group in data.get("keyword_groups", []):
        representative = _clean_text(group.get("representative_keyword"))
        rows.append(
            {
                "Representative Keyword": representative,
                "Grouped Keywords": _grouped_keywords_text(
                    representative,
                    group.get("related_keywords", []),
                ),
                "Context Text": _clean_text(group.get("context_text")),
                "Exact Extracted Information": _clean_text(group.get("exact_text")),
            }
        )
    return rows


def _grouped_keywords_text(representative, related_keywords):
    keywords = []
    seen = set()
    for value in [representative, *list(related_keywords or [])]:
        text = _clean_text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            keywords.append(text)
    return ", ".join(keywords)


def _clean_text(value):
    return " ".join(str(value or "").split())


def _table_html(rows):
    header_cells = [
        "<th class=\"col-representative\">Representative<br>Keyword</th>",
        "<th class=\"col-grouped\">Grouped Keywords</th>",
        "<th class=\"col-context\">Context Text</th>",
        "<th class=\"col-exact\">Exact Extracted Information</th>",
    ]
    body_rows = "\n".join(_body_row(row) for row in rows)
    return f"""
<style>
    .contract-output-table-wrap {{
        background: #000;
        color: #fff;
        overflow-x: auto;
        padding: 0.25rem 0 1rem;
    }}
    .contract-output-table-wrap h2 {{
        color: #fff;
        font-size: 1.5rem;
        font-weight: 700;
        line-height: 1.2;
        margin: 0 0 0.75rem 0;
    }}
    .contract-output-table {{
        border-collapse: collapse;
        min-width: 980px;
        table-layout: fixed;
        width: 100%;
    }}
    .contract-output-table th,
    .contract-output-table td {{
        border-bottom: 1px solid #151515;
        color: #fff;
        overflow-wrap: anywhere;
        padding: 1rem 0.9rem;
        text-align: left;
        vertical-align: top;
        white-space: normal;
    }}
    .contract-output-table th {{
        border-bottom-color: #2b2b2b;
        font-size: 1rem;
        font-weight: 700;
        line-height: 1.25;
    }}
    .contract-output-table td {{
        font-size: 1rem;
        line-height: 1.6;
    }}
    .contract-output-table .col-representative {{
        width: 13%;
    }}
    .contract-output-table .col-grouped {{
        width: 18%;
    }}
    .contract-output-table .col-context {{
        width: 42%;
    }}
    .contract-output-table .col-exact {{
        width: 27%;
    }}
    .contract-output-table td:first-child,
    .contract-output-table td:last-child {{
        font-weight: 700;
    }}
</style>
<div class="contract-output-table-wrap">
    <h2>{escape(TABLE_TITLE)}</h2>
    <table class="contract-output-table">
        <thead>
            <tr>{"".join(header_cells)}</tr>
        </thead>
        <tbody>
            {body_rows}
        </tbody>
    </table>
</div>
"""


def _body_row(row):
    cells = [
        row["Representative Keyword"],
        row["Grouped Keywords"],
        row["Context Text"],
        row["Exact Extracted Information"],
    ]
    return "<tr>" + "".join(f"<td>{escape(value)}</td>" for value in cells) + "</tr>"
