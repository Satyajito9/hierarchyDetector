"""Validate-mode view: lets the user tick columns and assign levels, then
evaluates and renders that user-specified hierarchy."""

from __future__ import annotations

from typing import List, Optional

import polars as pl
import streamlit as st

from ..core_polars import profile_columns
from .chain_view import render_chain_result
from .data_loading import cached_validate
from .formatting import chain_summary_label
from .timed_run import run_with_live_timer


def render_validate(file_key: str, df: pl.DataFrame) -> None:
    st.write(
        "Tick the columns that make up the hierarchy you want to check. Level (1 = leaf level) "
        "fills in automatically — each newly ticked column becomes the new "
        "top level, pushing previously ticked columns one level down — edit it yourself if "
        "you want a different order. Give two columns the **same** level number to treat "
        "them as parallel (1:1) columns at that level."
    )

    editor_key = f"validate_editor_{file_key}"
    source_key = f"{editor_key}_source"

    # `source_key` is a plain session_state entry we own outright — never the
    # same key as the widget itself, since data_editor forbids programmatically
    # assigning to st.session_state[<its own key>].
    if source_key not in st.session_state:
        st.session_state[source_key] = pl.DataFrame(
            {
                "Column": list(df.columns),
                "Include": [False] * len(df.columns),
                "Level": pl.Series("Level", [None] * len(df.columns), dtype=pl.Int64),
            }
        )

    edited = st.data_editor(
        st.session_state[source_key],
        column_config={
            "Column": st.column_config.TextColumn(disabled=True),
            "Include": st.column_config.CheckboxColumn(),
            "Level": st.column_config.NumberColumn(min_value=1, step=1),
        },
        hide_index=True,
        width='stretch',
        key=editor_key,
    )

    # Invariant enforced every run: unticked rows always show a blank Level;
    # a just-ticked row (Include=True, Level still blank) becomes the new top
    # level (1), and every already-assigned level shifts down to make room —
    # i.e. new columns are inserted upstream (as the new broadest level)
    # rather than appended downstream (as the new narrowest level).
    # data_editor round-trips the Level column as Float64 (its grid needs a
    # float dtype to represent blank numeric cells) — cast back to a
    # nullable Int64 before working with it, same reason the pandas version
    # needed `.astype("Int64")` here.
    edited = edited.with_columns(pl.col("Level").cast(pl.Int64, strict=False))
    include: List[bool] = edited["Include"].to_list()
    levels_raw: List[Optional[int]] = edited["Level"].to_list()
    levels = [lvl if inc else None for inc, lvl in zip(include, levels_raw)]

    new_positions = [i for i, (inc, lvl) in enumerate(zip(include, levels)) if inc and lvl is None]
    if new_positions:
        shift = len(new_positions)
        levels = [lvl + shift if (inc and lvl is not None) else lvl for inc, lvl in zip(include, levels)]
        for offset, pos in enumerate(new_positions, start=1):
            levels[pos] = offset

    updated = edited.with_columns(pl.Series("Level", levels, dtype=pl.Int64))

    if levels != levels_raw:
        st.session_state[source_key] = updated
        st.rerun()

    selected = updated.filter(pl.col("Include")).sort("Level", maintain_order=True)

    if selected.height < 2:
        st.info("Select at least 2 columns to validate a hierarchy.")
        return

    level_groups: List[List[str]] = [group["Column"].to_list() for _, group in selected.group_by("Level", maintain_order=True)]

    if len(level_groups) < 2:
        st.info("Select columns spanning at least 2 different level numbers to validate a hierarchy.")
        return

    result = run_with_live_timer(
        lambda: cached_validate(df, tuple(tuple(g) for g in level_groups)),
        label="Validating hierarchy...",
    )
    profile_map = {p.name: p for p in profile_columns(df)}

    st.markdown(f"#### Validating: {chain_summary_label(result.levels)}")
    render_chain_result(
        df,
        result.levels,
        profile_map,
        key_prefix=f"{file_key}_validate",
    )
