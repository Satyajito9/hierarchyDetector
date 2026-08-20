"""App-version footer — lets anyone looking at a deployed instance confirm
which version is actually running."""

from __future__ import annotations

import streamlit as st

from .. import __version__


def render_version_footer() -> None:
    st.caption(f"Hierarchy Detector & Validator · v{__version__}")
