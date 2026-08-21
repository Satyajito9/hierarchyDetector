"""Per-column profiling (Polars backend) — mirrors
the pre-migration pandas core/profiling.py's public API exactly, operating on a
pl.DataFrame instead of a pd.DataFrame."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import polars as pl


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


def profile_columns(df: pl.DataFrame) -> List[ColumnProfile]:
    n_rows = df.height
    profiles = []
    for col in df.columns:
        series = df[col]
        null_count = int(series.null_count())
        non_null = n_rows - null_count
        distinct_count = int(series.drop_nulls().n_unique())
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
