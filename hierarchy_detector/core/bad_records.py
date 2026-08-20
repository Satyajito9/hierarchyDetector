"""Per-row "why is this a bad record" explanations, derived from a chain's
ComplianceResult — used to build the exception reports shown in the UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .compliance import ComplianceResult


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
        is the original-df index of a row that does show the dominant
        combination, for the caller to cite)."""

    kind: str  # "blank" | "different_parent"
    detail: str
    example_index: Optional[object] = None
    diffs: List[Tuple[str, object]] = field(default_factory=list)


def bad_record_reasons(df: pd.DataFrame, result: ComplianceResult) -> Dict[object, BadRecordReason]:
    """Per-row reason a record is a bad record for `result.ancestors -> result.leaf`,
    keyed by original df index. Covers exactly `result.null_excluded_index` and
    `result.violation_index` (not compliant rows)."""
    reasons: Dict[object, BadRecordReason] = {}

    check_cols = list(result.ancestors) + [result.leaf]
    for idx in result.null_excluded_index:
        blanks = [c for c in check_cols if pd.isna(df.at[idx, c])]
        reasons[idx] = BadRecordReason(kind="blank", detail=", ".join(blanks))

    if len(result.violation_index) == 0:
        return reasons

    ancestor_key = df[result.ancestors[0]].astype(str)
    for col in result.ancestors[1:]:
        ancestor_key = ancestor_key.str.cat(df[col].astype(str), sep="||")

    valid_mask = ~df.index.isin(result.null_excluded_index)
    tmp = pd.DataFrame(
        {"leaf": df.loc[valid_mask, result.leaf].values, "anc": ancestor_key[valid_mask].values},
        index=df.index[valid_mask],
    )
    pair_counts = tmp.groupby(["leaf", "anc"], sort=False).size().reset_index(name="n")
    top_idx = pair_counts.groupby("leaf", sort=False)["n"].idxmax()
    dominant = pair_counts.loc[top_idx].set_index("leaf")["anc"]

    tmp["is_dominant"] = tmp["anc"].values == tmp["leaf"].map(dominant).values
    dominant_rows = tmp[tmp["is_dominant"]].copy()
    dominant_rows["_row_index"] = dominant_rows.index
    example_row_by_leaf = dominant_rows.groupby("leaf", sort=False)["_row_index"].min()

    ancestor_label = " / ".join(result.ancestors)
    for idx in result.violation_index:
        leaf_val = df.at[idx, result.leaf]
        example_idx = example_row_by_leaf.get(leaf_val)
        diffs = [
            (col, df.at[example_idx, col])
            for col in result.ancestors
            if df.at[idx, col] != df.at[example_idx, col]
        ] if example_idx is not None else []
        reasons[idx] = BadRecordReason(
            kind="different_parent",
            detail=ancestor_label,
            example_index=example_idx,
            diffs=diffs,
        )

    return reasons
