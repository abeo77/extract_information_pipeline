"""Streamlit segment debug viewer."""

import streamlit as st

from app.loaders.document_loader import load_document
from app.preprocessing.normalizer import normalize_documents
from app.segmentation.contract_segmenter import segment_documents


def render_segment_viewer(path):
    if not path or not st.button("Preview segments"):
        return
    segments = segment_documents(normalize_documents(load_document(path)))
    st.write(f"{len(segments)} segments")
    for segment in segments:
        with st.expander(f"{segment.segment_id} | page {segment.page} | {segment.title or '-'}"):
            st.code(segment.text)
