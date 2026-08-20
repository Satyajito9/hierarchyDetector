"""Page header: the app title with the running version rendered as a
subscript next to it, so anyone looking at a deployed instance can confirm
which version is actually running."""

from __future__ import annotations

import streamlit as st

from .. import __version__


def render_header_with_version(title: str) -> None:
    st.markdown(
        f"# {title} <sub style='font-size:0.3em; font-weight:400; color:#6b7280;'>"
        f"v{__version__}</sub>",
        unsafe_allow_html=True,
    )
