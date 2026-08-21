"""Per-row 'why is this a bad record' explanations (Polars backend) —
mirrors the pre-migration pandas core/bad_records.py's public API and semantics,
operating on a pl.DataFrame."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import polars as pl

from .compliance import ComplianceResult

__all__ = ["BadRecordReason", "bad_record_reasons"]


@dataclass
class BadRecordReason:
    """Why one row is a 'bad record' for a given chain. Two cases:
      - "blank": one of the chain's columns is null on this row (`detail` is
        a comma-joined list of the blank column names).
      - "different_parent": the row's ancestor combination isn't the leaf
        value's dominant one elsewhere in the file (`detail` is the ancestor
        column(s) involved, kept for backward-compat/logging; `diffs` holds
        only the ancestor column(s) whose value actually differs from the
        example row, as (column, example_row_value) pairs; `example_index`
        is the row position (0-based, within the same df) of a row that
        does show the dominant combination, for the caller to cite)."""

    kind: str  # "blank" | "different_parent"
    detail: str
    example_index: Optional[int] = None
    diffs: List[Tuple[str, object]] = field(default_factory=list)


def bad_record_reasons(df: pl.DataFrame, result: ComplianceResult) -> Dict[int, BadRecordReason]:
    """Per-row reason a record is a bad record for `result.ancestors ->
    result.leaf`, keyed by 0-based row position (valid only against this
    same `df`). Covers exactly `result.null_excluded_index` and
    `result.violation_index` (not compliant rows)."""
    reasons: Dict[int, BadRecordReason] = {}

    check_cols = list(result.ancestors) + [result.leaf]
    if result.null_excluded_index:
        blank_rows = df[check_cols][result.null_excluded_index]
        for idx, row in zip(result.null_excluded_index, blank_rows.iter_rows(named=True)):
            blanks = [c for c in check_cols if row[c] is None]
            reasons[idx] = BadRecordReason(kind="blank", detail=", ".join(blanks))

    if not result.violation_index:
        return reasons

    total_rows = df.height
    row_idx = pl.arange(0, total_rows, eager=True)
    valid_mask = ~row_idx.is_in(result.null_excluded_index)

    ancestor_key = df[result.ancestors[0]].cast(pl.Utf8)
    for col in result.ancestors[1:]:
        ancestor_key = ancestor_key + "||" + df[col].cast(pl.Utf8)

    tmp = pl.DataFrame(
        {
            "leaf": df[result.leaf].filter(valid_mask),
            "anc": ancestor_key.filter(valid_mask),
            "_idx": row_idx.filter(valid_mask),
        }
    )
    pair_counts = tmp.group_by(["leaf", "anc"]).len()
    dominant = (
        pair_counts.sort("len", descending=True)
        .group_by("leaf", maintain_order=True)
        .first()
        .select(["leaf", pl.col("anc").alias("expected")])
    )
    tmp = tmp.join(dominant, on="leaf", how="left")
    example_row_by_leaf = (
        tmp.filter(pl.col("anc") == pl.col("expected"))
        .group_by("leaf", maintain_order=True)
        .agg(pl.col("_idx").min().alias("example_idx"))
    )
    example_idx_by_leaf = dict(zip(example_row_by_leaf["leaf"].to_list(), example_row_by_leaf["example_idx"].to_list()))

    ancestor_label = " / ".join(result.ancestors)
    ancestor_cols = list(result.ancestors)
    violation_rows = df[check_cols][result.violation_index]
    example_indices = [example_idx_by_leaf.get(row[result.leaf]) for row in violation_rows.iter_rows(named=True)]
    unique_example_indices = sorted({i for i in example_indices if i is not None})
    example_rows_by_idx: Dict[int, dict] = {}
    if unique_example_indices:
        gathered = df[ancestor_cols][unique_example_indices]
        example_rows_by_idx = dict(zip(unique_example_indices, gathered.iter_rows(named=True)))

    for idx, row, example_idx in zip(result.violation_index, violation_rows.iter_rows(named=True), example_indices):
        example_row = example_rows_by_idx.get(example_idx) if example_idx is not None else None
        diffs = (
            [(col, example_row[col]) for col in result.ancestors if row[col] != example_row[col]]
            if example_row is not None
            else []
        )
        reasons[idx] = BadRecordReason(
            kind="different_parent",
            detail=ancestor_label,
            example_index=example_idx,
            diffs=diffs,
        )

    return reasons
