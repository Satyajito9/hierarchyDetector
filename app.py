"""Entry point: wires the upload flow to the rendering layer. Holds no
business logic or rendering logic itself — see hierarchy_detector/core (pure
computation) and hierarchy_detector/ui (Streamlit rendering)."""

import streamlit as st

from hierarchy_detector.ui import collect_uploaded_files, render_file_section, render_version_footer

st.set_page_config(page_title="Hierarchy Detector & Validator", layout="wide")


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
        "break the hierarchy, and exactly which column/value differs and against which row.\n"
        "- ✉️ Questions or feedback? Contact us at plugincoe@o9solutions.com"
    )

    uploaded_files = st.file_uploader(
        "📁 Upload CSV file(s)", type=["csv"], accept_multiple_files=True
    )

    if not uploaded_files:
        st.info("Upload at least one CSV file to get started.")
        render_version_footer()
        return

    entries = collect_uploaded_files(uploaded_files)

    tabs = st.tabs([display_name for _, display_name, _ in entries])
    for tab, (file_key, display_name, df) in zip(tabs, entries):
        with tab:
            render_file_section(file_key, display_name, df)

    render_version_footer()


if __name__ == "__main__":
    main()
