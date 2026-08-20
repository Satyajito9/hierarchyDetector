"""Small formatting helpers shared across the detect/validate views."""

from __future__ import annotations

from typing import List

from ..core import BadRecordReason, LevelResult

# Original-file row number shown to users (`row_num`): the CSV header line is
# counted as line 1, so the first data row (df index 0) is line 2.
HEADER_LINE_OFFSET = 2


def format_bad_record_reason(reason: BadRecordReason) -> str:
    if reason.kind == "blank":
        return f"Blank {reason.detail}"
    example_row_num = reason.example_index + HEADER_LINE_OFFSET
    if not reason.diffs:
        return f"Different {reason.detail} than row {example_row_num}"
    pairs = ", ".join(f"{col}: {val}" for col, val in reason.diffs)
    return f"{pairs} in row {example_row_num}"


def chain_summary_label(levels: List[LevelResult]) -> str:
    return " → ".join(" ≡ ".join(lvl.columns) for lvl in levels)
