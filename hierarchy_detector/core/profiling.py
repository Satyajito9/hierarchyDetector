"""Per-column profiling: distinct/null counts and simple column classification
(constant, unique key) shown in the column-profile report and used to decide
which columns are eligible for hierarchy detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd


@dataclass
class ColumnProfile:
    name: str
    dtype: str
    non_null_count: int
    null_count: int
    null_pct: float
    distinct_count: int
    distinct_pct: float
    is_constant: bool
    is_unique_key: bool


def profile_columns(df: pd.DataFrame) -> List[ColumnProfile]:
    n_rows = len(df)
    profiles = []
    for col in df.columns:
        series = df[col]
        non_null = int(series.notna().sum())
        null_count = n_rows - non_null
        distinct_count = int(series.nunique(dropna=True))
        profiles.append(
            ColumnProfile(
                name=col,
                dtype=str(series.dtype),
                non_null_count=non_null,
                null_count=null_count,
                null_pct=(null_count / n_rows * 100.0) if n_rows else 0.0,
                distinct_count=distinct_count,
                distinct_pct=(distinct_count / n_rows * 100.0) if n_rows else 0.0,
                is_constant=distinct_count <= 1,
                is_unique_key=(distinct_count == non_null and non_null > 0),
            )
        )
    return profiles
