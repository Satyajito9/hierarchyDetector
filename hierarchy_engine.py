"""
Core hierarchy detection / validation logic.

Hierarchy semantics used throughout this module:
    A chain of columns [C0, C1, ..., Ck] represents a top-down hierarchy
    (C0 = broadest / top level, Ck = most granular / leaf level), e.g.
    Country -> State -> City.

    A row "satisfies" the hierarchy if, for the leaf value in that row, the
    combination of all its ancestor values matches the single most common
    ("dominant") ancestor combination observed for that leaf value across the
    whole file. This checks the full ancestor path at once (not just the
    immediate parent), which is what makes a rollup hierarchy valid end to
    end.

    Rows with a null in any column that participates in the chain being
    evaluated are excluded from both the numerator and denominator of the
    compliance percentage, and reported separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd

# Class to store the details/profile of each column in the DataFrame
# It's used in the report to show the characteristics of each column to the user in both the UI (generate and validate)
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


# ---------------------------------------------------------------------------
# Compliance calculation
# ---------------------------------------------------------------------------

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


def evaluate_chain(df: pd.DataFrame, ordered_cols: Sequence[str]) -> List[ComplianceResult]:
    """Evaluate a top->bottom column chain level by level.

    Returns one ComplianceResult per level (from the 2nd column onward),
    where each result's compliance covers *all* ancestor columns seen so
    far, not just the immediate parent.
    """
    if len(ordered_cols) < 2:
        raise ValueError("A hierarchy chain needs at least 2 columns")

    results: List[ComplianceResult] = []
    str_cache = {c: df[c].astype(str) for c in ordered_cols}

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


def pairwise_symmetric_compliance(df: pd.DataFrame, col_a: str, col_b: str) -> Tuple[ComplianceResult, ComplianceResult]:
    """Check both directions of a potential 1:1 (same-level) relationship between two columns."""
    forward = evaluate_chain(df, [col_a, col_b])[-1]  # col_a -> col_b
    reverse = evaluate_chain(df, [col_b, col_a])[-1]  # col_b -> col_a
    return forward, reverse


# ---------------------------------------------------------------------------
# Shared level representation
# ---------------------------------------------------------------------------

@dataclass
class LevelResult:
    """One level of a hierarchy. Usually a single column, but can hold several
    columns that are mutually 1:1 (parallel / same-level) with each other."""

    columns: List[str]
    ancestor_compliance: Optional[ComplianceResult]  # roll-up compliance from prior levels; None for the top level
    parallel_evidence: List[Tuple[str, ComplianceResult, ComplianceResult]] = field(default_factory=list)
    # (extra_column, forward_result, reverse_result) for each column beyond columns[0]

    @property
    def representative(self) -> str:
        return self.columns[0]

    @property
    def is_parallel_group(self) -> bool:
        return len(self.columns) > 1


# ---------------------------------------------------------------------------
# Hierarchy detection (exhaustive: every valid chain, not just one greedy pick)
# ---------------------------------------------------------------------------

@dataclass
class ChainResult:
    levels: List[LevelResult]
    near_misses: List[Tuple[str, float, float, str]]  # (column, compliance_pct, avg_group_size, reason)

    @property
    def overall(self) -> ComplianceResult:
        return self.levels[-1].ancestor_compliance

    @property
    def flat_columns(self) -> List[str]:
        return [c for lvl in self.levels for c in lvl.columns]


@dataclass
class DetectResult:
    hierarchies: List[ChainResult]
    unused_columns: List[str]
    excluded_columns: List[Tuple[str, str]]  # (column, reason)
    profiles: List[ColumnProfile]


_MAX_GENERATED_CHAINS = 50  # safety backstop against pathological branching, not a normal-use limit


def _build_level(df: pd.DataFrame, node_cols_for_node: List[str], ancestor_compliance: Optional[ComplianceResult]) -> LevelResult:
    representative = node_cols_for_node[0]
    level = LevelResult(columns=[representative], ancestor_compliance=ancestor_compliance)
    for extra in node_cols_for_node[1:]:
        fwd, rev = pairwise_symmetric_compliance(df, representative, extra)
        level.columns.append(extra)
        level.parallel_evidence.append((extra, fwd, rev))
    return level


def detect_hierarchies(df: pd.DataFrame, threshold: float = 95.0, max_hierarchies: int = 3) -> DetectResult:
    """Exhaustively enumerate every valid top->bottom column chain, rather than
    committing to a single greedy pick. Steps:
      1. Merge columns that are mutually 1:1 into same-level groups.
      2. Test every remaining pair (broad -> narrow, by ascending cardinality)
         for an ancestor relationship, and transitive-reduce the resulting
         graph so only immediate parent/child edges remain (dropping
         redundant skip-edges like Category->Item when Category->Subcategory
         ->Brand->Item already holds).
      3. Walk every root->leaf path in that graph, re-validating the *full*
         cumulative ancestor path (not just the adjacent pair) at each step,
         since that check only gets stricter as more ancestors are added.
    """
    profiles = profile_columns(df)
    profile_map = {p.name: p for p in profiles}
    order_index = {c: i for i, c in enumerate(df.columns)}

    excluded_columns: List[Tuple[str, str]] = []
    eligible: List[str] = []
    for p in profiles:
        if p.non_null_count == 0:
            excluded_columns.append((p.name, "entirely empty (no non-null values)"))
        elif p.is_constant:
            excluded_columns.append((p.name, "constant (only one distinct value)"))
        else:
            eligible.append(p.name)

    if len(eligible) < 2:
        return DetectResult(hierarchies=[], unused_columns=eligible, excluded_columns=excluded_columns, profiles=profiles)

    # --- Step 1: merge columns that are mutually 1:1 into same-level groups ---
    parent = {c: c for c in eligible}

    def find(c: str) -> str:
        while parent[c] != c:
            c = parent[c]
        return c

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a, b in combinations(eligible, 2):
        if not _cardinalities_close(profile_map[a].distinct_count, profile_map[b].distinct_count):
            continue
        fwd, rev = pairwise_symmetric_compliance(df, a, b)
        if fwd.compliance_pct >= threshold and rev.compliance_pct >= threshold:
            union(a, b)

    groups: Dict[str, List[str]] = {}
    for c in eligible:
        groups.setdefault(find(c), []).append(c)

    node_cols: Dict[str, List[str]] = {
        root: sorted(cols, key=lambda c: (profile_map[c].distinct_count, order_index[c]))
        for root, cols in groups.items()
    }

    def node_repr(node: str) -> str:
        return node_cols[node][0]

    # --- Step 2: broad -> narrow candidate edges between groups, then reduce ---
    nodes_sorted = sorted(
        node_cols.keys(), key=lambda n: (profile_map[node_repr(n)].distinct_count, order_index[node_repr(n)])
    )

    direct_edges: Dict[str, List[str]] = {n: [] for n in nodes_sorted}
    for i, na in enumerate(nodes_sorted):
        ra = node_repr(na)
        for nb in nodes_sorted[i + 1:]:
            rb = node_repr(nb)
            if profile_map[ra].distinct_count > profile_map[rb].distinct_count:
                continue
            compliance = evaluate_chain(df, [ra, rb])[-1].compliance_pct
            if compliance >= threshold:
                direct_edges[na].append(nb)

    reach: Dict[str, Set[str]] = {n: set() for n in nodes_sorted}
    for na in reversed(nodes_sorted):
        for nb in direct_edges[na]:
            reach[na].add(nb)
            reach[na].update(reach[nb])

    reduced_edges: Dict[str, List[str]] = {n: [] for n in nodes_sorted}
    for na in nodes_sorted:
        children = direct_edges[na]
        for nb in children:
            redundant = any(nb in reach[nc] for nc in children if nc != nb)
            if not redundant:
                reduced_edges[na].append(nb)

    incoming = {n: 0 for n in nodes_sorted}
    for na in nodes_sorted:
        for nb in reduced_edges[na]:
            incoming[nb] += 1
    roots = [n for n in nodes_sorted if incoming[n] == 0]

    # --- Step 3: walk every root->leaf path, re-validating the full chain ---
    all_chains: List[ChainResult] = []

    def dfs(
        node: str,
        levels: List[LevelResult],
        chain_repr: List[str],
        near_misses: List[Tuple[str, float, float, str]],
    ) -> None:
        if len(all_chains) >= _MAX_GENERATED_CHAINS:
            return

        successful_children: List[Tuple[str, ComplianceResult]] = []
        own_failures: List[Tuple[str, float, float, str]] = []
        for child in reduced_edges[node]:
            child_repr = node_repr(child)
            result = evaluate_chain(df, chain_repr + [child_repr])[-1]
            if result.compliance_pct >= threshold:
                successful_children.append((child, result))
            else:
                own_failures.append((child_repr, result.compliance_pct, result.avg_group_size, "below compliance threshold"))

        if not successful_children:
            if len(levels) >= 2:
                all_chains.append(ChainResult(levels=levels, near_misses=near_misses + own_failures))
            return

        for child, result in successful_children:
            if len(all_chains) >= _MAX_GENERATED_CHAINS:
                break
            child_level = _build_level(df, node_cols[child], result)
            dfs(child, levels + [child_level], chain_repr + [node_repr(child)], near_misses + own_failures)

    for root in roots:
        if len(all_chains) >= _MAX_GENERATED_CHAINS:
            break
        root_level = _build_level(df, node_cols[root], None)
        dfs(root, [root_level], [node_repr(root)], [])

    used_cols = {c for chain in all_chains for lvl in chain.levels for c in lvl.columns}
    unused_columns = sorted((c for c in eligible if c not in used_cols), key=lambda c: order_index[c])

    all_chains.sort(key=lambda c: (-len(c.levels), -c.overall.compliance_pct))
    hierarchies = all_chains[:max_hierarchies]

    return DetectResult(
        hierarchies=hierarchies,
        unused_columns=unused_columns,
        excluded_columns=excluded_columns,
        profiles=profiles,
    )


# ---------------------------------------------------------------------------
# Hierarchy validation (user-specified levels, no threshold gating)
# ---------------------------------------------------------------------------

@dataclass
class ValidateResult:
    levels: List[LevelResult]

    @property
    def overall(self) -> ComplianceResult:
        return self.levels[-1].ancestor_compliance

    @property
    def flat_columns(self) -> List[str]:
        return [c for lvl in self.levels for c in lvl.columns]


def validate_hierarchy(df: pd.DataFrame, level_groups: Sequence[Sequence[str]]) -> ValidateResult:
    """Evaluate a user-specified hierarchy. `level_groups` is ordered top->bottom;
    each element is a list of one or more columns considered the same level
    (columns sharing a level are checked pairwise for a 1:1 relationship, but that
    isn't enforced — the caller decided they belong together)."""
    groups = [list(g) for g in level_groups]
    if len(groups) < 2:
        raise ValueError("A hierarchy needs at least 2 levels")

    levels: List[LevelResult] = []
    chain_repr: List[str] = []

    for i, group in enumerate(groups):
        representative = group[0]
        if i == 0:
            level = LevelResult(columns=[representative], ancestor_compliance=None)
        else:
            trial = chain_repr + [representative]
            result = evaluate_chain(df, trial)[-1]
            level = LevelResult(columns=[representative], ancestor_compliance=result)

        for extra in group[1:]:
            fwd, rev = pairwise_symmetric_compliance(df, representative, extra)
            level.columns.append(extra)
            level.parallel_evidence.append((extra, fwd, rev))

        levels.append(level)
        chain_repr.append(representative)

    return ValidateResult(levels=levels)
