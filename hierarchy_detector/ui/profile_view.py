"""Column-profile table rendering."""

from __future__ import annotations

import polars as pl
import streamlit as st

from ..core_polars import profile_columns


def render_column_profile(df: pl.DataFrame) -> None:
    profiles = profile_columns(df)
    rows = [
        {
            "Column": p.name,
            "Type": p.dtype,
            "Distinct values": p.distinct_count,
            "Distinct %": round(p.distinct_pct, 1),
            "Nulls": p.null_count,
            "Null %": round(p.null_pct, 1),
            "Constant": p.is_constant,
            "Unique key": p.is_unique_key,
        }
        for p in profiles
    ]
    st.dataframe(pl.DataFrame(rows), hide_index=True, width='stretch')
