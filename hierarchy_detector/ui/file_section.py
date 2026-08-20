"""Per-uploaded-file section: preview, column profile, and the
detect/validate mode switch."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .detect_view import render_detect
from .profile_view import render_column_profile
from .validate_view import render_validate


def render_file_section(file_key: str, filename: str, df: pd.DataFrame) -> None:
    st.caption(f"{df.shape[0]:,} rows × {df.shape[1]} columns")

    with st.expander("Preview data (first 20 rows)"):
        st.dataframe(df.head(20), width='stretch')

    with st.expander("Column profile"):
        render_column_profile(df)

    mode = st.radio(
        "What do you want to do?",
        ["🔍 Detect Hierarchy", "✅ Validate Hierarchy"],
        key=f"mode_{file_key}",
        horizontal=True,
    )

    if mode == "🔍 Detect Hierarchy":
        render_detect(file_key, df)
    else:
        render_validate(file_key, df)
