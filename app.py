"""Entry point: wires the upload flow to the rendering layer. Holds no
business logic or rendering logic itself — see hierarchy_detector/core (pure
computation) and hierarchy_detector/ui (Streamlit rendering)."""

import streamlit as st

from hierarchy_detector.ui import (
    collect_uploaded_files,
    render_file_section,
    render_header_with_version,
    render_upload_trigger,
    get_uploaded_file_sep_pairs,
)

st.set_page_config(page_title="Hierarchy Detector & Validator", layout="wide")


def main() -> None:
    render_header_with_version("📊 Hierarchy Detector & Validator")
    st.markdown(
        "Click 'Upload CSV file(s)' below to check column-based hierarchies "
        "(e.g. *Country → State → City*). For each file you can:\n"
        "- 🔍 **Detect Hierarchy** — automatically finds likely parent/child column chains "
        "and scores how well the data complies with each one.\n"
        "- ✅ **Validate Hierarchy** — pick the exact columns and levels you have in mind "
        "and check how well the data actually follows that structure.\n"
        "- 🚩 Both modes give you a downloadable **exception report** pinpointing which rows "
        "break the hierarchy, and exactly which column/value differs and against which row.\n"
        "- ✉️ Questions or feedback? Contact us at plugincoe@o9solutions.com"
    )

    render_upload_trigger()

    file_sep_pairs = get_uploaded_file_sep_pairs()
    if not file_sep_pairs:
        st.info("Click 'Upload CSV file(s)' to get started.")
        return

    entries = collect_uploaded_files(file_sep_pairs)
    if not entries:
        return

    tabs = st.tabs([display_name for _, display_name, _ in entries])
    for tab, (file_key, display_name, df) in zip(tabs, entries):
        with tab:
            render_file_section(file_key, display_name, df)


if __name__ == "__main__":
    main()
