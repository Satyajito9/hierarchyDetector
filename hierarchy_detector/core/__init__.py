"""
Core hierarchy detection / validation logic. Pure computation — no Streamlit
or I/O dependency; independently testable.

Hierarchy semantics used throughout this package:
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

Submodules, one concern each:
    profiling    — per-column profiling (distinct/null counts, etc.)
    compliance   — chain compliance calculation (the core statistic)
    bad_records  — per-row "why is this a bad record" explanations
    levels       — shared LevelResult representation used by detect & validate
    detect       — automatic hierarchy detection (exhaustive chain search)
    validate     — validation of a user-specified hierarchy
"""

from .bad_records import BadRecordReason, bad_record_reasons
from .compliance import (
    ComplianceResult,
    evaluate_chain,
    pairwise_symmetric_compliance,
    top_violations,
)
from .detect import ChainResult, DetectResult, detect_hierarchies
from .levels import LevelResult
from .profiling import ColumnProfile, profile_columns
from .validate import ValidateResult, validate_hierarchy

__all__ = [
    "BadRecordReason",
    "bad_record_reasons",
    "ComplianceResult",
    "evaluate_chain",
    "pairwise_symmetric_compliance",
    "top_violations",
    "ChainResult",
    "DetectResult",
    "detect_hierarchies",
    "LevelResult",
    "ColumnProfile",
    "profile_columns",
    "ValidateResult",
    "validate_hierarchy",
]
