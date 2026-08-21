"""Shared LevelResult representation (Polars backend) — mirrors
the pre-migration pandas core/levels.py's public API, operating on a
pl.DataFrame."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import polars as pl

from .compliance import ComplianceResult, pairwise_symmetric_compliance

__all__ = ["LevelResult", "build_level"]


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


def build_level(
    df: pl.DataFrame,
    node_cols_for_node: List[str],
    ancestor_compliance: Optional[ComplianceResult],
    str_cache: Optional[Dict[str, pl.Series]] = None,
) -> LevelResult:
    representative = node_cols_for_node[0]
    level = LevelResult(columns=[representative], ancestor_compliance=ancestor_compliance)
    for extra in node_cols_for_node[1:]:
        fwd, rev = pairwise_symmetric_compliance(df, representative, extra, str_cache)
        level.columns.append(extra)
        level.parallel_evidence.append((extra, fwd, rev))
    return level
