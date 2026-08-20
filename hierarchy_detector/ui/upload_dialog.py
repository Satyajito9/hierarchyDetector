"""Upload flow: a button that opens a modal dialog with a file picker, a
separator selector, and a Submit button — instead of those controls sitting
permanently on the page."""

from __future__ import annotations

from typing import Any, List, Tuple

import streamlit as st

from .separator_picker import render_separator_select

_BATCHES_KEY = "_upload_dialog_batches"  # list of (uploaded_files, sep), one per Submit


@st.dialog("Upload CSV file(s)")
def _render_upload_dialog() -> None:
    files_col, sep_col = st.columns([2, 1])
    with files_col:
        files = st.file_uploader("Choose files", type=["csv"], accept_multiple_files=True)
    with sep_col:
        sep = render_separator_select()

    if st.button("Submit", type="primary"):
        if not files:
            st.warning("Choose at least one file before submitting.")
        elif not sep:
            st.warning("Choose or enter a separator before submitting.")
        else:
            # Append rather than overwrite: files uploaded in an earlier
            # dialog submission stay in the session alongside new ones.
            st.session_state.setdefault(_BATCHES_KEY, []).append((files, sep))
            st.rerun()


def render_upload_trigger() -> None:
    if st.button("📁 Upload CSV file(s)"):
        _render_upload_dialog()


def get_uploaded_file_sep_pairs() -> List[Tuple[Any, str]]:
    """Every (uploaded_file, sep) pair submitted so far this session, across
    every upload-dialog submission, in submission order."""
    batches = st.session_state.get(_BATCHES_KEY, [])
    return [(uf, sep) for files, sep in batches for uf in files]


def discard_files(bad_files: List[Any]) -> None:
    """Remove specific uploaded files (e.g. ones that failed to parse) from
    every stored batch, so they're dropped from session state instead of
    being reprocessed and re-reported on every future rerun."""
    bad_ids = {id(f) for f in bad_files}
    batches = st.session_state.get(_BATCHES_KEY, [])
    st.session_state[_BATCHES_KEY] = [
        (kept, sep)
        for files, sep in batches
        if (kept := [f for f in files if id(f) not in bad_ids])
    ]
