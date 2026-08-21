"""Validation of a user-specified hierarchy (Polars backend) — mirrors
the pre-migration pandas core/validate.py's public API and semantics, operating
on a pl.DataFrame."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

import polars as pl

from .compliance import ComplianceResult, evaluate_chain, pairwise_symmetric_compliance
from .levels import LevelResult

__all__ = ["ValidateResult", "validate_hierarchy"]


@dataclass
class ValidateResult:
    levels: List[LevelResult]

    @property
    def overall(self) -> ComplianceResult:
        return self.levels[-1].ancestor_compliance

    @property
    def flat_columns(self) -> List[str]:
        return [c for lvl in self.levels for c in lvl.columns]


def validate_hierarchy(df: pl.DataFrame, level_groups: Sequence[Sequence[str]]) -> ValidateResult:
    """See the pre-migration pandas core/validate.py:validate_hierarchy for the
    semantics — identical here, just Polars-backed."""
    groups = [list(g) for g in level_groups]
    if len(groups) < 2:
        raise ValueError("A hierarchy needs at least 2 levels")

    str_cache: Dict[str, pl.Series] = {c: df[c].cast(pl.Utf8) for g in groups for c in g}

    levels: List[LevelResult] = []
    chain_repr: List[str] = []

    for i, group in enumerate(groups):
        representative = group[0]
        if i == 0:
            level = LevelResult(columns=[representative], ancestor_compliance=None)
        else:
            trial = chain_repr + [representative]
            result = evaluate_chain(df, trial, str_cache)[-1]
            level = LevelResult(columns=[representative], ancestor_compliance=result)

        for extra in group[1:]:
            fwd, rev = pairwise_symmetric_compliance(df, representative, extra, str_cache)
            level.columns.append(extra)
            level.parallel_evidence.append((extra, fwd, rev))

        levels.append(level)
        chain_repr.append(representative)

    return ValidateResult(levels=levels)
