"""Cached wrappers around the core engine and CSV loading. Kept separate from
the core engine itself, since caching (`st.cache_data`) is a Streamlit/UI
concern, not a computation concern."""

from __future__ import annotations

import io
from typing import Tuple

import pandas as pd
import streamlit as st

from ..core import DetectResult, ValidateResult, detect_hierarchies, validate_hierarchy


@st.cache_data(show_spinner=False, max_entries=20, ttl=3600)
def load_csv(file_bytes: bytes, filename: str) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(file_bytes))


@st.cache_data(show_spinner="Detecting hierarchies...", max_entries=20, ttl=3600)
def cached_detect(df: pd.DataFrame, threshold: float, max_hierarchies: int) -> DetectResult:
    return detect_hierarchies(df, threshold=threshold, max_hierarchies=max_hierarchies)


@st.cache_data(show_spinner="Validating hierarchy...", max_entries=20, ttl=3600)
def cached_validate(df: pd.DataFrame, level_groups: Tuple[Tuple[str, ...], ...]) -> ValidateResult:
    return validate_hierarchy(df, level_groups)
