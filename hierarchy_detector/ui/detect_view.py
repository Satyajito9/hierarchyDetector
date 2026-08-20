"""Detect-mode view: runs automatic detection and renders one tab per
discovered hierarchy plus a consolidated exception report."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .chain_view import render_chain_result
from .data_loading import cached_detect
from .formatting import chain_summary_label
from .reports import render_consolidated_bad_records

MAX_HIERARCHIES_TO_FIND = 8

# Fixed internally; not exposed in the UI. Used only to decide which chains
# qualify as a detected hierarchy — the displayed Compliance % (see
# ComplianceResult.overall_compliance_pct) is unaffected by this value.
DETECT_COMPLIANCE_THRESHOLD = 98.0


def render_detect(file_key: str, df: pd.DataFrame) -> None:
    result = cached_detect(df, DETECT_COMPLIANCE_THRESHOLD, MAX_HIERARCHIES_TO_FIND)
    profile_map = {p.name: p for p in result.profiles}

    if not result.hierarchies:
        st.warning(
            "No column chain met the compliance threshold. Try Validate Hierarchy "
            "to inspect a specific combination of columns instead."
        )
    else:
        tab_labels = [f"Hierarchy {idx + 1}" for idx in range(len(result.hierarchies))]
        tabs = st.tabs(tab_labels)
        for idx, (tab, chain_result) in enumerate(zip(tabs, result.hierarchies)):
            with tab:
                st.caption(chain_summary_label(chain_result.levels))
                render_chain_result(
                    df,
                    chain_result.levels,
                    profile_map,
                    key_prefix=f"{file_key}_h{idx + 1}",
                    near_misses=chain_result.near_misses,
                    show_bad_records=False,
                )

        render_consolidated_bad_records(df, result.hierarchies, key_prefix=f"{file_key}_detect")

    if result.unused_columns:
        st.markdown("##### Columns not part of any detected hierarchy")
        st.write(", ".join(result.unused_columns))

    if result.excluded_columns:
        with st.expander("Columns excluded from analysis (constant or empty)"):
            st.dataframe(
                pd.DataFrame(result.excluded_columns, columns=["Column", "Reason"]),
                hide_index=True,
                width='stretch',
            )
