"""Separator selector: a single editable dropdown (`st.selectbox` with
`accept_new_options=True`) — pick a preset separator or type your own
character directly into the same field. Used inside the upload dialog."""

from __future__ import annotations

import streamlit as st

SEPARATOR_OPTIONS = [",", "|", ";", "~", ":", "*"]
# SEP_DISPLAYNAMES = {
#     ",": ", Comma",
#     "|": "| Pipe",
#     ";": "; Semicolon",
#     "~": "~ Tilde",
#     ":": ": Colon",
#     "*": "* Asterisk"
# }


def render_separator_select() -> str:
    return st.selectbox(
        "Separator",
        SEPARATOR_OPTIONS,
        index=0,
        # format_func=lambda x: SEP_DISPLAYNAMES.get(x, f"'{x}'" if len(x) == 1 else x),
        accept_new_options=True,
        help="Pick a common separator, or type your own character.",
        width=80,
    )
