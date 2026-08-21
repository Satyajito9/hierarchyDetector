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

    active_mode_key = f"active_mode_{file_key}"

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 Detect Hierarchy", key=f"detect_btn_{file_key}", width="stretch"):
            st.session_state[active_mode_key] = "detect"
    with col2:
        if st.button("✅ Validate Hierarchy", key=f"validate_btn_{file_key}", width="stretch"):
            st.session_state[active_mode_key] = "validate"

    active_mode = st.session_state.get(active_mode_key)
    if active_mode == "detect":
        render_detect(file_key, df)
    elif active_mode == "validate":
        render_validate(file_key, df)
