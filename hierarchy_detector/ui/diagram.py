"""Rendering of the hierarchy structure diagram — boxes per level, plus
connectors between parallel (1:1) boxes and between levels."""

from __future__ import annotations

from typing import Dict, List

import streamlit as st

from ..core import ColumnProfile, LevelResult
from .styles import BOX_H, BOX_W, HIER_CSS, LINE_COLOR, LINK_COLOR, LINK_W


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
