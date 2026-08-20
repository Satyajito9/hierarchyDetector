"""Rendering of a single evaluated chain (used by both detect and validate):
metrics, the hierarchy diagram, fan-out captions, near-misses and the
exception report."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from ..core import ColumnProfile, LevelResult
from .diagram import render_hierarchy_diagram
from .reports import render_bad_record_table


def render_chain_result(
    df: pd.DataFrame,
    levels: List[LevelResult],
    profile_map: Dict[str, ColumnProfile],
    key_prefix: str,
    near_misses: Optional[List[Tuple[str, float, float, str]]] = None,
    show_bad_records: bool = True,
) -> None:
    overall = levels[-1].ancestor_compliance

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Compliance", f"{overall.overall_compliance_pct:.1f}%")
    m2.metric("Compliant rows", f"{overall.compliant_rows:,} / {overall.total_rows:,}")
    m3.metric("Rows with missing values", f"{overall.null_excluded_rows:,}")
    m4.metric("Levels", f"{len(levels)}")

    st.markdown("##### Hierarchy structure")
    render_hierarchy_diagram(levels, profile_map)

    chain_repr = [lvl.representative for lvl in levels]
    cardinalities = [profile_map[c].distinct_count for c in chain_repr]
    fan_out_bits = []
    for i in range(len(cardinalities) - 1):
        if cardinalities[i]:
            ratio = round(cardinalities[i + 1] / cardinalities[i], 2)
            fan_out_bits.append(f"{chain_repr[i]} → {chain_repr[i + 1]}: {ratio}x")
    if fan_out_bits:
        st.caption("Avg. children per parent (fan-out): " + " | ".join(fan_out_bits))

    if near_misses:
        with st.expander(f"Columns considered but excluded from this hierarchy ({len(near_misses)})"):
            nm_df = pd.DataFrame(
                near_misses, columns=["Column", "Best compliance %", "Avg rows/value", "Reason excluded"]
            )
            nm_df["Best compliance %"] = nm_df["Best compliance %"].round(1)
            nm_df["Avg rows/value"] = nm_df["Avg rows/value"].round(1)
            nm_df = nm_df.sort_values("Best compliance %", ascending=False)
            st.dataframe(nm_df, hide_index=True, width='stretch')

    if show_bad_records:
        render_bad_record_table(df, overall, key_prefix)
