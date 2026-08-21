"""Chain compliance calculation (Polars backend) — mirrors
the pre-migration pandas core/compliance.py's public API and semantics, operating
on a pl.DataFrame instead of a pd.DataFrame.

`ComplianceResult.violation_index`/`null_excluded_index` are plain 0-based
row-position lists (List[int]) rather than a pd.Index, since Polars has no
persistent row index — they're only valid against the same pl.DataFrame
they were computed from."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import polars as pl

__all__ = [
    "ComplianceResult",
    "evaluate_chain",
    "pairwise_symmetric_compliance",
    "top_violations",
    "_cardinalities_close",
]

LOW_SAMPLE_AVG_GROUP_SIZE = 2.0


@dataclass
class ComplianceResult:
    ancestors: Tuple[str, ...]
    leaf: str
    total_rows: int
    valid_rows: int
    null_excluded_rows: int
    compliant_rows: int
    violating_rows: int
    compliance_pct: float
    distinct_leaf_values: int
    violation_index: List[int] = field(repr=False)
    null_excluded_index: List[int] = field(repr=False)

    @property
    def is_degenerate(self) -> bool:
        return self.valid_rows == 0

    @property
    def overall_compliance_pct(self) -> float:
        if self.total_rows == 0:
            return 0.0
        return 100.0 * self.compliant_rows / self.total_rows

    @property
    def avg_group_size(self) -> float:
        if self.distinct_leaf_values == 0:
            return 0.0
        return self.valid_rows / self.distinct_leaf_values

    @property
    def low_sample_warning(self) -> bool:
        return not self.is_degenerate and self.avg_group_size < LOW_SAMPLE_AVG_GROUP_SIZE


def _compliance_from_key(
    df: pl.DataFrame,
    ancestor_key: pl.Series,
    ancestor_null_mask: pl.Series,
    ancestors: Tuple[str, ...],
    leaf_col: str,
) -> ComplianceResult:
    total_rows = df.height
    leaf_null_mask = df[leaf_col].is_null()
    valid_mask = ~(ancestor_null_mask | leaf_null_mask)
    valid_rows = int(valid_mask.sum())
    row_idx = pl.arange(0, total_rows, eager=True)
    null_excluded_index = row_idx.filter(~valid_mask).to_list()

    if valid_rows == 0:
        return ComplianceResult(
            ancestors=ancestors,
            leaf=leaf_col,
            total_rows=total_rows,
            valid_rows=0,
            null_excluded_rows=total_rows,
            compliant_rows=0,
            violating_rows=0,
            compliance_pct=0.0,
            distinct_leaf_values=0,
            violation_index=[],
            null_excluded_index=null_excluded_index,
        )

    leaf_valid = df[leaf_col].filter(valid_mask)
    anc_valid = ancestor_key.filter(valid_mask)
    idx_valid = row_idx.filter(valid_mask)

    tmp = pl.DataFrame({"leaf": leaf_valid, "anc": anc_valid, "_idx": idx_valid})

    # Vectorized mode-per-group: count (leaf, anc) pairs, then take the
    # highest-count anc per leaf (sort by count desc, then first per leaf
    # group) — the Polars equivalent of pandas' groupby+idxmax.
    pair_counts = tmp.group_by(["leaf", "anc"]).len()
    dominant = (
        pair_counts.sort("len", descending=True)
        .group_by("leaf", maintain_order=True)
        .first()
        .select(["leaf", pl.col("anc").alias("expected")])
    )
    tmp = tmp.join(dominant, on="leaf", how="left")
    compliant_mask = tmp["anc"] == tmp["expected"]

    compliant_rows = int(compliant_mask.sum())
    violating_rows = valid_rows - compliant_rows
    violation_index = tmp["_idx"].filter(~compliant_mask).to_list()
    compliance_pct = 100.0 * compliant_rows / valid_rows

    return ComplianceResult(
        ancestors=ancestors,
        leaf=leaf_col,
        total_rows=total_rows,
        valid_rows=valid_rows,
        null_excluded_rows=total_rows - valid_rows,
        compliant_rows=compliant_rows,
        violating_rows=violating_rows,
        compliance_pct=compliance_pct,
        distinct_leaf_values=int(tmp["leaf"].n_unique()),
        violation_index=violation_index,
        null_excluded_index=null_excluded_index,
    )


def evaluate_chain(
    df: pl.DataFrame,
    ordered_cols: Sequence[str],
    str_cache: Optional[Dict[str, pl.Series]] = None,
) -> List[ComplianceResult]:
    """Evaluate a top->bottom column chain level by level. See
    the pre-migration pandas core/compliance.py:evaluate_chain for the semantics
    (identical here, just Polars-backed)."""
    if len(ordered_cols) < 2:
        raise ValueError("A hierarchy chain needs at least 2 columns")

    results: List[ComplianceResult] = []
    if str_cache is None:
        str_cache = {c: df[c].cast(pl.Utf8) for c in ordered_cols}
    else:
        for c in ordered_cols:
            if c not in str_cache:
                str_cache[c] = df[c].cast(pl.Utf8)

    cumulative_key = str_cache[ordered_cols[0]]
    cumulative_null_mask = df[ordered_cols[0]].is_null()

    for i in range(1, len(ordered_cols)):
        leaf = ordered_cols[i]
        ancestors = tuple(ordered_cols[:i])
        result = _compliance_from_key(df, cumulative_key, cumulative_null_mask, ancestors, leaf)
        results.append(result)

        # Extend the composite ancestor key for the next level.
        cumulative_key = cumulative_key + "||" + str_cache[leaf]
        cumulative_null_mask = cumulative_null_mask | df[leaf].is_null()

    return results


def top_violations(df: pl.DataFrame, leaf_col: str, violation_index: List[int], top_n: int = 10) -> pl.DataFrame:
    """Which leaf values account for the most violating rows."""
    if len(violation_index) == 0:
        return pl.DataFrame({leaf_col: [], "violating_rows": []})
    counts = df[leaf_col].gather(violation_index).value_counts().sort("count", descending=True).head(top_n)
    return counts.rename({"count": "violating_rows"})


def _cardinalities_close(a: int, b: int, tolerance: float = 0.9) -> bool:
    """Whether two distinct-value counts are close enough to even consider a
    1:1 (same-level) relationship. A true 1:1 pair (e.g. two ID columns for the
    same entity) has essentially equal cardinality; a real parent/child pair
    (e.g. 8 groups vs. 12 subgroups) does not, even if one child value happens
    to dominate each parent bucket by row count."""
    if a == 0 or b == 0:
        return a == b
    lo, hi = min(a, b), max(a, b)
    return (lo / hi) >= tolerance


def pairwise_symmetric_compliance(
    df: pl.DataFrame,
    col_a: str,
    col_b: str,
    str_cache: Optional[Dict[str, pl.Series]] = None,
) -> Tuple[ComplianceResult, ComplianceResult]:
    """Check both directions of a potential 1:1 (same-level) relationship between two columns."""
    forward = evaluate_chain(df, [col_a, col_b], str_cache)[-1]
    reverse = evaluate_chain(df, [col_b, col_a], str_cache)[-1]
    return forward, reverse
