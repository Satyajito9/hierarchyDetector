"""Exception-report rendering: the bad-record tables shown under a single
chain (detect/validate) and consolidated across every detected hierarchy."""

from __future__ import annotations

from typing import Dict, List

import polars as pl
import streamlit as st

from ..core_polars import ChainResult, ComplianceResult, bad_record_reasons
from .downloads import render_download_controls
from .formatting import HEADER_LINE_OFFSET, format_bad_record_reason


def _with_row_num_and_reason(df: pl.DataFrame, reason_text: Dict[int, str]) -> pl.DataFrame:
    """Returns a copy of `df` with a leading 'row_num' column (1-based file
    line number) and a trailing 'Bad Record Reason' column, populated from
    `reason_text` (keyed by 0-based row position; blank where absent)."""
    row_num = (pl.arange(0, df.height, eager=True) + HEADER_LINE_OFFSET).alias("row_num")
    reason = pl.Series("Bad Record Reason", [reason_text.get(i, "") for i in range(df.height)])
    return df.with_columns(row_num, reason).select(["row_num", *df.columns, "Bad Record Reason"])


def render_bad_record_table(df: pl.DataFrame, overall: ComplianceResult, key_prefix: str) -> None:
    """Exception view shared by Detect and Validate: one table with every bad
    record — rows that violate the chain, plus rows excluded for a blank
    chain column — each with all of the file's columns, a leading row_num,
    and a Bad Record Reason explaining why it's there. No violation-ranking
    sub-table."""
    bad_index = sorted(set(overall.violation_index) | set(overall.null_excluded_index))

    st.markdown("##### 🚩 Exception Report")
    if not bad_index:
        st.success("No violations — every evaluated row matches this hierarchy.")
        return

    with st.expander(f"Exception rows ({len(bad_index):,} rows that break this hierarchy)"):
        reasons = bad_record_reasons(df, overall)
        reason_text = {i: format_bad_record_reason(r) for i, r in reasons.items()}

        full_df = _with_row_num_and_reason(df, reason_text)
        exc_df = full_df[bad_index]

        popover_col, _ = st.columns([1, 5])
        with popover_col:
            with st.popover("Download"):
                render_download_controls(full_df, exc_df, key_prefix)

        st.dataframe(exc_df, hide_index=True, width='stretch', height=250)


def render_consolidated_bad_records(df: pl.DataFrame, hierarchies: List[ChainResult], key_prefix: str) -> None:
    """Consolidated exception view across every detected hierarchy: one row
    per bad record, with the reasons from each hierarchy it violates joined
    into a single comma-separated Bad Record Reason cell (prefixed 'H1:',
    'H2:', ... so the reasons stay attributable when a row breaks more than
    one hierarchy)."""
    per_row_reasons: Dict[int, List[str]] = {}
    for h_idx, chain in enumerate(hierarchies, start=1):
        reasons = bad_record_reasons(df, chain.overall)
        for i, r in reasons.items():
            per_row_reasons.setdefault(i, []).append(f"H{h_idx}: {format_bad_record_reason(r)}")

    bad_index = sorted(per_row_reasons.keys())

    st.markdown("##### 🚩 Exception Report (across all detected hierarchies)")
    if not bad_index:
        st.success("No violations — every evaluated row matches every detected hierarchy.")
        return

    with st.expander(f"Exception rows ({len(bad_index):,} rows that break at least one detected hierarchy)"):
        reason_text = {i: ", ".join(parts) for i, parts in per_row_reasons.items()}

        full_df = _with_row_num_and_reason(df, reason_text)
        exc_df = full_df[bad_index]

        popover_col, _ = st.columns([1, 5])
        with popover_col:
            with st.popover("Download"):
                render_download_controls(full_df, exc_df, key_prefix)

        st.dataframe(exc_df, hide_index=True, width='stretch', height=250)
