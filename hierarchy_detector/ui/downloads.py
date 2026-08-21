"""Shared download controls (full data / exceptions-only CSV export) used by
both the detect and validate exception reports."""

from __future__ import annotations

import polars as pl
import streamlit as st


def render_download_controls(full_df: pl.DataFrame, exc_df: pl.DataFrame, key_prefix: str) -> None:
    """Shared download controls: an 'include reason' toggle plus two download
    buttons — full data (every row) or exception rows only — both honoring
    that toggle. Both frames must already carry a 'Bad Record Reason' column."""
    include_reason = st.checkbox(
        "Include bad record reason",
        value=True,
        key=f"{key_prefix}_dl_include_reason",
        help="On: include the Bad Record Reason column in the download. Off: drop it.",
    )
    full_export = full_df if include_reason else full_df.drop("Bad Record Reason")
    exc_export = exc_df if include_reason else exc_df.drop("Bad Record Reason")

    st.caption(f"{len(full_df):,} rows total · {len(exc_df):,} exception rows")
    # Stacked (not side-by-side columns) so both buttons span the same full
    # width regardless of label length — side-by-side columns kept coming out
    # different sizes because the longer label wrapped inside its half-width
    # column while the shorter one didn't.
    st.download_button(
        "Full data",
        full_export.write_csv().encode("utf-8"),
        file_name=f"{key_prefix}_full_data.csv",
        mime="text/csv",
        icon="📄",
        key=f"{key_prefix}_dl_full_btn",
        width='stretch',
    )
    st.download_button(
        "Exceptions only",
        exc_export.write_csv().encode("utf-8"),
        file_name=f"{key_prefix}_exceptions.csv",
        mime="text/csv",
        icon="⚠️",
        key=f"{key_prefix}_dl_exc_btn",
        width='stretch',
    )
