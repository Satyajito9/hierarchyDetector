"""Chain compliance calculation — the core statistic behind both detection
and validation: for a top->bottom column chain, what fraction of rows have
the leaf value's dominant ancestor combination."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

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
    violation_index: pd.Index = field(repr=False)
    null_excluded_index: pd.Index = field(repr=False)

    @property
    def is_degenerate(self) -> bool:
        return self.valid_rows == 0

    @property
    def overall_compliance_pct(self) -> float:
        """Compliance against *every* evaluated row, including the ones excluded
        for a blank chain column (those count as non-compliant here). This is
        the percentage shown to the user. `compliance_pct` (valid-rows-only,
        i.e. nulls excluded from both numerator and denominator) remains the
        internal metric used to decide whether a hierarchy chain qualifies
        during detection — changing that would make detection threshold
        gating sensitive to how much null data a chain happens to have."""
        if self.total_rows == 0:
            return 0.0
        return 100.0 * self.compliant_rows / self.total_rows

    @property
    def avg_group_size(self) -> float:
        if self.distinct_leaf_values == 0:
            return 0.0
        return self.valid_rows / self.distinct_leaf_values

    # Might have to remove this, redundant
    @property
    def low_sample_warning(self) -> bool:
        """True when most leaf values appear ~once, so there's not enough
        repetition to actually test consistency — a high (or low) compliance
        score at this level should not be trusted at face value."""
        return not self.is_degenerate and self.avg_group_size < LOW_SAMPLE_AVG_GROUP_SIZE


def _compliance_from_key(
    df: pd.DataFrame,
    ancestor_key: pd.Series,
    ancestor_null_mask: pd.Series,
    ancestors: Tuple[str, ...],
    leaf_col: str,
) -> ComplianceResult:
    total_rows = len(df)
    leaf_null_mask = df[leaf_col].isna()
    valid_mask = ~(ancestor_null_mask | leaf_null_mask)
    valid_rows = int(valid_mask.sum())
    null_excluded_index = df.index[~valid_mask]

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
            violation_index=pd.Index([]),
            null_excluded_index=null_excluded_index,
        )

    leaf_valid = df.loc[valid_mask, leaf_col]
    anc_valid = ancestor_key[valid_mask]
    tmp = pd.DataFrame({"leaf": leaf_valid.values, "anc": anc_valid.values}, index=leaf_valid.index)

    # Vectorized mode-per-group: count (leaf, anc) pairs, then take the
    # highest-count anc per leaf. Avoids slow groupby-apply with a lambda.
    pair_counts = tmp.groupby(["leaf", "anc"], sort=False).size().reset_index(name="n")
    top_idx = pair_counts.groupby("leaf", sort=False)["n"].idxmax()
    mode_df = pair_counts.loc[top_idx, ["leaf", "anc"]].rename(columns={"anc": "expected"})

    tmp = tmp.merge(mode_df, on="leaf", how="left")
    tmp.index = leaf_valid.index
    compliant_mask = tmp["anc"] == tmp["expected"]

    compliant_rows = int(compliant_mask.sum())
    violating_rows = valid_rows - compliant_rows
    violation_index = tmp.index[~compliant_mask]
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
        distinct_leaf_values=int(tmp["leaf"].nunique()),
        violation_index=violation_index,
        null_excluded_index=null_excluded_index,
    )


def evaluate_chain(
    df: pd.DataFrame,
    ordered_cols: Sequence[str],
    str_cache: Optional[Dict[str, pd.Series]] = None,
) -> List[ComplianceResult]:
    """Evaluate a top->bottom column chain level by level.

    Returns one ComplianceResult per level (from the 2nd column onward),
    where each result's compliance covers *all* ancestor columns seen so
    far, not just the immediate parent.

    `str_cache` is an optional column-name -> `df[column].astype(str)` map,
    shared across many `evaluate_chain` calls against the same `df` (e.g.
    the O(columns^2) candidate-pair scan in `detect_hierarchies`) so each
    column's string conversion happens once instead of once per call it
    appears in. Callers that don't pass one get the old per-call behavior.
    """
    if len(ordered_cols) < 2:
        raise ValueError("A hierarchy chain needs at least 2 columns")

    results: List[ComplianceResult] = []
    if str_cache is None:
        str_cache = {c: df[c].astype(str) for c in ordered_cols}
    else:
        for c in ordered_cols:
            if c not in str_cache:
                str_cache[c] = df[c].astype(str)

    cumulative_key = str_cache[ordered_cols[0]]
    cumulative_null_mask = df[ordered_cols[0]].isna()

    for i in range(1, len(ordered_cols)):
        leaf = ordered_cols[i]
        ancestors = tuple(ordered_cols[:i])
        result = _compliance_from_key(df, cumulative_key, cumulative_null_mask, ancestors, leaf)
        results.append(result)

        # Extend the composite ancestor key for the next level.
        cumulative_key = cumulative_key.str.cat(str_cache[leaf], sep="||")
        cumulative_null_mask = cumulative_null_mask | df[leaf].isna()

    return results


def top_violations(df: pd.DataFrame, leaf_col: str, violation_index: pd.Index, top_n: int = 10) -> pd.DataFrame:
    """Which leaf values account for the most violating rows."""
    if len(violation_index) == 0:
        return pd.DataFrame(columns=[leaf_col, "violating_rows"])
    counts = df.loc[violation_index, leaf_col].value_counts().head(top_n)
    return counts.rename_axis(leaf_col).reset_index(name="violating_rows")


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
    df: pd.DataFrame,
    col_a: str,
    col_b: str,
    str_cache: Optional[Dict[str, pd.Series]] = None,
) -> Tuple[ComplianceResult, ComplianceResult]:
    """Check both directions of a potential 1:1 (same-level) relationship between two columns."""
    forward = evaluate_chain(df, [col_a, col_b], str_cache)[-1]  # col_a -> col_b
    reverse = evaluate_chain(df, [col_b, col_a], str_cache)[-1]  # col_b -> col_a
    return forward, reverse
