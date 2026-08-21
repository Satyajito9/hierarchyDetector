"""Turns the raw list of Streamlit `UploadedFile` objects into de-duplicated
(file_key, display_name, DataFrame) entries ready for rendering."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import polars as pl
import streamlit as st

from .data_loading import load_csv
from .upload_dialog import discard_files


def collect_uploaded_files(file_sep_pairs) -> List[Tuple[str, str, pl.DataFrame]]:
    """Turns a flat list of (uploaded_file, sep) pairs — potentially spanning
    several upload-dialog submissions, each with its own separator — into
    de-duplicated (file_key, display_name, DataFrame) entries. De-duplicates
    display names across the *whole* list (not just within one submission),
    so re-opening the dialog and uploading more files never drops or
    renumbers files uploaded earlier in the session. Files that fail to
    parse with their chosen separator are corrupted/unreadable — they're
    discarded from session state and reported with a temporary toast rather
    than a page-level error, so they don't linger or get reprocessed on
    every future rerun."""
    name_counts: Dict[str, int] = {}
    entries: List[Tuple[str, str, pl.DataFrame]] = []
    corrupted: List[Any] = []
    for uf, sep in file_sep_pairs:
        count = name_counts.get(uf.name, 0)
        name_counts[uf.name] = count + 1
        display_name = uf.name if count == 0 else f"{uf.name} ({count + 1})"

        try:
            df = load_csv(uf.getvalue(), uf.name, sep)
        except Exception:
            corrupted.append(uf)
            continue

        file_key = f"file{len(entries)}_{uf.name}"
        entries.append((file_key, display_name, df))

    if corrupted:
        st.markdown(
            """
            <style>
            div[data-testid="stToastContainer"] {
                position: fixed !important;
                top: 50% !important;
                left: 50% !important;
                right: auto !important;
                bottom: auto !important;
                transform: translate(-50%, -50%) !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        for uf in corrupted:
            st.toast(f"'{uf.name}' is corrupted — please fix and retry.", icon="⚠️", duration="short")
        discard_files(corrupted)

    return entries
