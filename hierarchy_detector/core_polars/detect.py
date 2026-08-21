"""Automatic hierarchy detection (Polars backend) — mirrors
the pre-migration pandas core/detect.py's algorithm and public API exactly
(same union-find/graph-reduction/DFS control flow, same row-sampling
behavior for large files), operating on a pl.DataFrame instead of a
pd.DataFrame."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Dict, List, Set, Tuple

import polars as pl

from .compliance import ComplianceResult, _cardinalities_close, evaluate_chain, pairwise_symmetric_compliance
from .levels import LevelResult, build_level
from .profiling import ColumnProfile, profile_columns

__all__ = ["ChainResult", "DetectResult", "detect_hierarchies"]

_MAX_GENERATED_CHAINS = 50  # safety backstop against pathological branching, not a normal-use limit


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

# See the pre-migration pandas core/detect.py — identical row-sampling behavior.
_SEARCH_SAMPLE_CAP = 100_000
_SEARCH_SAMPLE_SEED = 0


def _recompute_chain_on_full_data(
    df: pl.DataFrame, chain: ChainResult, str_cache: Dict[str, pl.Series]
) -> ChainResult:
    """Rebuilds a chain's levels (same columns, same order) with
    ancestor_compliance/parallel_evidence recomputed against `df`, for a
    chain whose structure was found via a row sample (see
    _SEARCH_SAMPLE_CAP)."""
    chain_repr: List[str] = []
    new_levels: List[LevelResult] = []
    for level in chain.levels:
        representative = level.representative
        ancestor_compliance = (
            None if not chain_repr else evaluate_chain(df, chain_repr + [representative], str_cache)[-1]
        )
        extras = [extra for extra, _, _ in level.parallel_evidence]
        new_levels.append(build_level(df, [representative] + extras, ancestor_compliance, str_cache))
        chain_repr.append(representative)
    return ChainResult(levels=new_levels, near_misses=chain.near_misses)


def detect_hierarchies(df: pl.DataFrame, threshold: float = 95.0, max_hierarchies: int = 3) -> DetectResult:
    """See the pre-migration pandas core/detect.py:detect_hierarchies for the
    step-by-step algorithm description — identical here, just Polars-backed."""
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

    if df.height > _SEARCH_SAMPLE_CAP:
        search_df = df.sample(n=_SEARCH_SAMPLE_CAP, seed=_SEARCH_SAMPLE_SEED)
    else:
        search_df = df

    str_cache: Dict[str, pl.Series] = {c: search_df[c].cast(pl.Utf8) for c in eligible}

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
        fwd, rev = pairwise_symmetric_compliance(search_df, a, b, str_cache)
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
            compliance = evaluate_chain(search_df, [ra, rb], str_cache)[-1].compliance_pct
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
            result = evaluate_chain(search_df, chain_repr + [child_repr], str_cache)[-1]
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
            child_level = build_level(search_df, node_cols[child], result, str_cache)
            dfs(child, levels + [child_level], chain_repr + [node_repr(child)], near_misses + own_failures)

    for root in roots:
        if len(all_chains) >= _MAX_GENERATED_CHAINS:
            break
        root_level = build_level(search_df, node_cols[root], None, str_cache)
        dfs(root, [root_level], [node_repr(root)], [])

    used_cols = {c for chain in all_chains for lvl in chain.levels for c in lvl.columns}
    unused_columns = sorted((c for c in eligible if c not in used_cols), key=lambda c: order_index[c])

    all_chains.sort(key=lambda c: (-len(c.levels), -c.overall.compliance_pct))
    hierarchies = all_chains[:max_hierarchies]

    if search_df is not df:
        full_cols = {c for chain in hierarchies for lvl in chain.levels for c in lvl.columns}
        full_str_cache: Dict[str, pl.Series] = {c: df[c].cast(pl.Utf8) for c in full_cols}
        hierarchies = [_recompute_chain_on_full_data(df, chain, full_str_cache) for chain in hierarchies]

    return DetectResult(
        hierarchies=hierarchies,
        unused_columns=unused_columns,
        excluded_columns=excluded_columns,
        profiles=profiles,
    )
