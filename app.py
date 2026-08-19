"""Streamlit app: detect and validate column hierarchies in uploaded CSV files."""

from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from hierarchy_engine import (
    BadRecordReason,
    ChainResult,
    ColumnProfile,
    ComplianceResult,
    DetectResult,
    LevelResult,
    ValidateResult,
    bad_record_reasons,
    detect_hierarchies,
    profile_columns,
    validate_hierarchy,
)

# Original-file row number shown to users (`row_num`): the CSV header line is
# counted as line 1, so the first data row (df index 0) is line 2.
HEADER_LINE_OFFSET = 2

st.set_page_config(page_title="Hierarchy Detector & Validator", layout="wide")

BOX_W = 170
BOX_H = 56  # baseline height used only for connector geometry; boxes themselves can grow taller
LINK_W = 40  # width of the horizontal bidirectional-arrow connector between parallel boxes
LINE_COLOR = "#7ea6e0"
LINK_COLOR = "#b98400"

HIER_CSS = f"""
<style>
.hier-row {{ display:flex; align-items:center; width:fit-content; margin:0 auto; }}
.hier-box {{ background:#eef4ff; border:1px solid {LINE_COLOR}; border-radius:8px;
            width:{BOX_W}px; min-height:{BOX_H}px; box-sizing:border-box; padding:6px 10px;
            text-align:center; display:flex; flex-direction:column; justify-content:center; }}
.hier-box-name {{ font-weight:600; font-size:0.85em; white-space:normal;
                  word-wrap:break-word; overflow-wrap:break-word; line-height:1.25em; }}
.hier-box-sub {{ font-size:0.72em; color:#4a5a75; margin-top:4px; }}
</style>
"""


def hier_box_html(col: str, distinct: int) -> str:
    return (
        f"<div class='hier-box'><div class='hier-box-name'>{col}</div>"
        f"<div class='hier-box-sub'>{distinct:,} distinct</div></div>"
    )


def bidirectional_link_svg(width: int = LINK_W, height: int = BOX_H) -> str:
    """Thin horizontal bidirectional arrow, used between same-level (1:1) boxes."""
    y = height / 2
    return (
        f'<svg width="{width}" height="{height}" style="display:block;">'
        f'<line x1="6" y1="{y}" x2="{width - 6}" y2="{y}" stroke="{LINK_COLOR}" stroke-width="1.5"/>'
        f'<polygon points="6,{y} 12,{y - 4} 12,{y + 4}" fill="{LINK_COLOR}"/>'
        f'<polygon points="{width - 6},{y} {width - 12},{y - 4} {width - 12},{y + 4}" fill="{LINK_COLOR}"/>'
        f"</svg>"
    )


def converge_connector_svg(n_boxes: int, box_w: int = BOX_W, link_w: int = LINK_W) -> str:
    """N vertical lines (one per box in the row above) converging into a single
    centered down-arrow pointing at the row below."""
    total_w = n_boxes * box_w + max(0, n_boxes - 1) * link_w
    centers = [i * (box_w + link_w) + box_w / 2 for i in range(n_boxes)]
    stub_h, tail_h, arrow_h = 12, 18, 8
    bus_y = stub_h
    tail_y2 = bus_y + tail_h
    mid_x = total_w / 2
    total_h = tail_y2 + arrow_h + 2

    parts = [f'<svg width="{total_w}" height="{total_h}" style="display:block;margin:0 auto;">']
    for cx in centers:
        parts.append(f'<line x1="{cx}" y1="0" x2="{cx}" y2="{bus_y}" stroke="{LINE_COLOR}" stroke-width="2"/>')
    if n_boxes > 1:
        parts.append(
            f'<line x1="{centers[0]}" y1="{bus_y}" x2="{centers[-1]}" y2="{bus_y}" '
            f'stroke="{LINE_COLOR}" stroke-width="2"/>'
        )
    parts.append(f'<line x1="{mid_x}" y1="{bus_y}" x2="{mid_x}" y2="{tail_y2}" stroke="{LINE_COLOR}" stroke-width="2"/>')
    parts.append(
        f'<polygon points="{mid_x - 6},{tail_y2} {mid_x + 6},{tail_y2} {mid_x},{tail_y2 + arrow_h}" fill="{LINE_COLOR}"/>'
    )
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Cached wrappers around the engine
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, max_entries=20, ttl=3600)
def load_csv(file_bytes: bytes, filename: str) -> pd.DataFrame:
    import io

    return pd.read_csv(io.BytesIO(file_bytes))


@st.cache_data(show_spinner="Detecting hierarchies...", max_entries=20, ttl=3600)
def cached_detect(df: pd.DataFrame, threshold: float, max_hierarchies: int) -> DetectResult:
    return detect_hierarchies(df, threshold=threshold, max_hierarchies=max_hierarchies)


@st.cache_data(show_spinner="Validating hierarchy...", max_entries=20, ttl=3600)
def cached_validate(df: pd.DataFrame, level_groups: Tuple[Tuple[str, ...], ...]) -> ValidateResult:
    return validate_hierarchy(df, level_groups)


# ---------------------------------------------------------------------------
# Shared rendering helpers
# ---------------------------------------------------------------------------

def render_column_profile(df: pd.DataFrame) -> None:
    profiles = profile_columns(df)
    rows = [
        {
            "Column": p.name,
            "Type": p.dtype,
            "Distinct values": p.distinct_count,
            "Distinct %": round(p.distinct_pct, 1),
            "Nulls": p.null_count,
            "Null %": round(p.null_pct, 1),
            "Constant": p.is_constant,
            "Unique key": p.is_unique_key,
        }
        for p in profiles
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')


def format_bad_record_reason(reason: BadRecordReason) -> str:
    if reason.kind == "blank":
        return f"Blank {reason.detail}"
    example_row_num = reason.example_index + HEADER_LINE_OFFSET
    if not reason.diffs:
        return f"Different {reason.detail} than row {example_row_num}"
    pairs = ", ".join(f"{col}: {val}" for col, val in reason.diffs)
    return f"{pairs} in row {example_row_num}"


def render_hierarchy_diagram(
    levels: List[LevelResult],
    profile_map: Dict[str, ColumnProfile],
) -> None:
    st.markdown(HIER_CSS, unsafe_allow_html=True)

    for i, level in enumerate(levels):
        row_parts = [hier_box_html(level.representative, profile_map[level.representative].distinct_count)]
        for extra, _fwd, _rev in level.parallel_evidence:
            row_parts.append(bidirectional_link_svg())
            row_parts.append(hier_box_html(extra, profile_map[extra].distinct_count))
        st.markdown(f"<div class='hier-row'>{''.join(row_parts)}</div>", unsafe_allow_html=True)

        if i < len(levels) - 1:
            st.markdown(converge_connector_svg(len(level.columns)), unsafe_allow_html=True)


def render_download_controls(full_df: pd.DataFrame, exc_df: pd.DataFrame, key_prefix: str) -> None:
    """Shared download controls: an 'include reason' toggle plus two download
    buttons — full data (every row) or exception rows only — both honoring
    that toggle. Both frames must already carry a 'Bad Record Reason' column."""
    include_reason = st.checkbox(
        "Include bad record reason",
        value=True,
        key=f"{key_prefix}_dl_include_reason",
        help="On: include the Bad Record Reason column in the download. Off: drop it.",
    )
    full_export = full_df if include_reason else full_df.drop(columns=["Bad Record Reason"])
    exc_export = exc_df if include_reason else exc_df.drop(columns=["Bad Record Reason"])

    st.caption(f"{len(full_df):,} rows total · {len(exc_df):,} exception rows")
    # Stacked (not side-by-side columns) so both buttons span the same full
    # width regardless of label length — side-by-side columns kept coming out
    # different sizes because the longer label wrapped inside its half-width
    # column while the shorter one didn't.
    st.download_button(
        "Full data",
        full_export.to_csv(index=False).encode("utf-8"),
        file_name=f"{key_prefix}_full_data.csv",
        mime="text/csv",
        icon="📄",
        key=f"{key_prefix}_dl_full_btn",
        width='stretch',
    )
    st.download_button(
        "Exceptions only",
        exc_export.to_csv(index=False).encode("utf-8"),
        file_name=f"{key_prefix}_exceptions.csv",
        mime="text/csv",
        icon="⚠️",
        key=f"{key_prefix}_dl_exc_btn",
        width='stretch',
    )


def render_bad_record_table(df: pd.DataFrame, overall: ComplianceResult, key_prefix: str) -> None:
    """Exception view shared by Detect and Validate: one table with every bad
    record — rows that violate the chain, plus rows excluded for a blank
    chain column — each with all of the file's columns, a leading row_num,
    and a Bad Record Reason explaining why it's there. No violation-ranking
    sub-table."""
    bad_index = sorted(set(overall.violation_index) | set(overall.null_excluded_index))

    st.markdown("##### 🚩 Exception Report")
    if not bad_index:
        st.success("No violations — every evaluated row matches this hierarchy.")
        return

    with st.expander(f"Exception rows ({len(bad_index):,} rows that break this hierarchy)"):
        reasons = bad_record_reasons(df, overall)
        reason_text = {i: format_bad_record_reason(r) for i, r in reasons.items()}

        full_df = df.copy()
        full_df.insert(0, "row_num", [i + HEADER_LINE_OFFSET for i in df.index])
        full_df["Bad Record Reason"] = [reason_text.get(i, "") for i in df.index]
        exc_df = full_df.loc[bad_index]

        popover_col, _ = st.columns([1, 5])
        with popover_col:
            with st.popover("Download"):
                render_download_controls(full_df, exc_df, key_prefix)

        st.dataframe(exc_df, hide_index=True, width='stretch', height=250)


def render_consolidated_bad_records(df: pd.DataFrame, hierarchies: List[ChainResult], key_prefix: str) -> None:
    """Consolidated exception view across every detected hierarchy: one row
    per bad record, with the reasons from each hierarchy it violates joined
    into a single comma-separated Bad Record Reason cell (prefixed 'H1:',
    'H2:', ... so the reasons stay attributable when a row breaks more than
    one hierarchy)."""
    per_row_reasons: Dict[object, List[str]] = {}
    for h_idx, chain in enumerate(hierarchies, start=1):
        reasons = bad_record_reasons(df, chain.overall)
        for i, r in reasons.items():
            per_row_reasons.setdefault(i, []).append(f"H{h_idx}: {format_bad_record_reason(r)}")

    bad_index = sorted(per_row_reasons.keys())

    st.markdown("##### 🚩 Exception Report (across all detected hierarchies)")
    if not bad_index:
        st.success("No violations — every evaluated row matches every detected hierarchy.")
        return

    with st.expander(f"Exception rows ({len(bad_index):,} rows that break at least one detected hierarchy)"):
        reason_text = {i: ", ".join(parts) for i, parts in per_row_reasons.items()}

        full_df = df.copy()
        full_df.insert(0, "row_num", [i + HEADER_LINE_OFFSET for i in df.index])
        full_df["Bad Record Reason"] = [reason_text.get(i, "") for i in df.index]
        exc_df = full_df.loc[bad_index]

        popover_col, _ = st.columns([1, 5])
        with popover_col:
            with st.popover("Download"):
                render_download_controls(full_df, exc_df, key_prefix)

        st.dataframe(exc_df, hide_index=True, width='stretch', height=250)


def render_chain_result(
    df: pd.DataFrame,
    levels: List[LevelResult],
    profile_map: Dict[str, ColumnProfile],
    key_prefix: str,
    near_misses: Optional[List[Tuple[str, float, float, str]]] = None,
    show_bad_records: bool = True,
) -> None:
    overall = levels[-1].ancestor_compliance

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Compliance", f"{overall.overall_compliance_pct:.1f}%")
    m2.metric("Compliant rows", f"{overall.compliant_rows:,} / {overall.total_rows:,}")
    m3.metric("Rows with missing values", f"{overall.null_excluded_rows:,}")
    m4.metric("Levels", f"{len(levels)}")

    st.markdown("##### Hierarchy structure")
    render_hierarchy_diagram(levels, profile_map)

    chain_repr = [lvl.representative for lvl in levels]
    cardinalities = [profile_map[c].distinct_count for c in chain_repr]
    fan_out_bits = []
    for i in range(len(cardinalities) - 1):
        if cardinalities[i]:
            ratio = round(cardinalities[i + 1] / cardinalities[i], 2)
            fan_out_bits.append(f"{chain_repr[i]} → {chain_repr[i + 1]}: {ratio}x")
    if fan_out_bits:
        st.caption("Avg. children per parent (fan-out): " + " | ".join(fan_out_bits))

    if near_misses:
        with st.expander(f"Columns considered but excluded from this hierarchy ({len(near_misses)})"):
            nm_df = pd.DataFrame(
                near_misses, columns=["Column", "Best compliance %", "Avg rows/value", "Reason excluded"]
            )
            nm_df["Best compliance %"] = nm_df["Best compliance %"].round(1)
            nm_df["Avg rows/value"] = nm_df["Avg rows/value"].round(1)
            nm_df = nm_df.sort_values("Best compliance %", ascending=False)
            st.dataframe(nm_df, hide_index=True, width='stretch')

    if show_bad_records:
        render_bad_record_table(df, overall, key_prefix)


def chain_summary_label(levels: List[LevelResult]) -> str:
    return " → ".join(" ≡ ".join(lvl.columns) for lvl in levels)


# ---------------------------------------------------------------------------
# Detect mode
# ---------------------------------------------------------------------------

MAX_HIERARCHIES_TO_FIND = 8

# Fixed internally; not exposed in the UI. Used only to decide which chains
# qualify as a detected hierarchy — the displayed Compliance % (see
# ComplianceResult.overall_compliance_pct) is unaffected by this value.
DETECT_COMPLIANCE_THRESHOLD = 98.0


def render_detect(file_key: str, df: pd.DataFrame) -> None:
    result = cached_detect(df, DETECT_COMPLIANCE_THRESHOLD, MAX_HIERARCHIES_TO_FIND)
    profile_map = {p.name: p for p in result.profiles}

    if not result.hierarchies:
        st.warning(
            "No column chain met the compliance threshold. Try Validate Hierarchy "
            "to inspect a specific combination of columns instead."
        )
    else:
        tab_labels = [f"Hierarchy {idx + 1}" for idx in range(len(result.hierarchies))]
        tabs = st.tabs(tab_labels)
        for idx, (tab, chain_result) in enumerate(zip(tabs, result.hierarchies)):
            with tab:
                st.caption(chain_summary_label(chain_result.levels))
                render_chain_result(
                    df,
                    chain_result.levels,
                    profile_map,
                    key_prefix=f"{file_key}_h{idx + 1}",
                    near_misses=chain_result.near_misses,
                    show_bad_records=False,
                )

        render_consolidated_bad_records(df, result.hierarchies, key_prefix=f"{file_key}_detect")

    if result.unused_columns:
        st.markdown("##### Columns not part of any detected hierarchy")
        st.write(", ".join(result.unused_columns))

    if result.excluded_columns:
        with st.expander("Columns excluded from analysis (constant or empty)"):
            st.dataframe(
                pd.DataFrame(result.excluded_columns, columns=["Column", "Reason"]),
                hide_index=True,
                width='stretch',
            )


# ---------------------------------------------------------------------------
# Validate mode
# ---------------------------------------------------------------------------

def render_validate(file_key: str, df: pd.DataFrame) -> None:
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
        st.session_state[source_key] = pd.DataFrame(
            {
                "Column": list(df.columns),
                "Include": False,
                "Level": pd.array([pd.NA] * len(df.columns), dtype="Int64"),
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
    levels = edited["Level"].astype("Int64")
    include = edited["Include"]
    levels = levels.where(include, other=pd.NA)

    needs_level = include & levels.isna()
    if needs_level.any():
        new_idx = list(levels.index[needs_level])
        already_assigned_idx = levels.index[include & ~levels.isna()]
        levels.loc[already_assigned_idx] = levels.loc[already_assigned_idx] + len(new_idx)
        for offset, idx in enumerate(new_idx, start=1):
            levels.loc[idx] = offset

    updated = edited.copy()
    updated["Level"] = levels

    if not updated["Level"].equals(edited["Level"]):
        st.session_state[source_key] = updated
        st.rerun()

    selected = updated[updated["Include"]].sort_values("Level", kind="stable")

    if len(selected) < 2:
        st.info("Select at least 2 columns to validate a hierarchy.")
        return

    level_groups: List[List[str]] = [
        group_df["Column"].tolist() for _, group_df in selected.groupby("Level", sort=True)
    ]

    if len(level_groups) < 2:
        st.info("Select columns spanning at least 2 different level numbers to validate a hierarchy.")
        return

    result = cached_validate(df, tuple(tuple(g) for g in level_groups))
    profile_map = {p.name: p for p in profile_columns(df)}

    st.markdown(f"#### Validating: {chain_summary_label(result.levels)}")
    render_chain_result(
        df,
        result.levels,
        profile_map,
        key_prefix=f"{file_key}_validate",
    )


# ---------------------------------------------------------------------------
# Per-file section + app entry point
# ---------------------------------------------------------------------------

def render_file_section(file_key: str, filename: str, df: pd.DataFrame) -> None:
    st.caption(f"{df.shape[0]:,} rows × {df.shape[1]} columns")

    with st.expander("Preview data (first 20 rows)"):
        st.dataframe(df.head(20), width='stretch')

    with st.expander("Column profile"):
        render_column_profile(df)

    mode = st.radio(
        "What do you want to do?",
        ["🔍 Detect Hierarchy", "✅ Validate Hierarchy"],
        key=f"mode_{file_key}",
        horizontal=True,
    )

    if mode == "🔍 Detect Hierarchy":
        render_detect(file_key, df)
    else:
        render_validate(file_key, df)


def main() -> None:
    st.title("📊 Hierarchy Detector & Validator")
    st.markdown(
        "Upload one or more CSV files below to check column-based hierarchies "
        "(e.g. *Country → State → City*). For each file you can:\n"
        "- 🔍 **Detect Hierarchy** — automatically finds likely parent/child column chains "
        "and scores how well the data complies with each one.\n"
        "- ✅ **Validate Hierarchy** — pick the exact columns and levels you have in mind "
        "and check how well the data actually follows that structure.\n"
        "- 🚩 Both modes give you a downloadable **exception report** pinpointing which rows "
        "break the hierarchy, and exactly which column/value differs and against which row."
    )

    uploaded_files = st.file_uploader(
        "📁 Upload CSV file(s)", type=["csv"], accept_multiple_files=True
    )

    if not uploaded_files:
        st.info("Upload at least one CSV file to get started.")
        return

    # De-duplicate display names in case two uploaded files share a filename.
    name_counts: Dict[str, int] = {}
    entries: List[Tuple[str, str, pd.DataFrame]] = []
    for uf in uploaded_files:
        df = load_csv(uf.getvalue(), uf.name)
        count = name_counts.get(uf.name, 0)
        name_counts[uf.name] = count + 1
        display_name = uf.name if count == 0 else f"{uf.name} ({count + 1})"
        file_key = f"file{len(entries)}_{uf.name}"
        entries.append((file_key, display_name, df))

    tabs = st.tabs([display_name for _, display_name, _ in entries])
    for tab, (file_key, display_name, df) in zip(tabs, entries):
        with tab:
            render_file_section(file_key, display_name, df)


if __name__ == "__main__":
    main()
