"""Streamlit rendering layer. Each module owns one rendering concern; `app.py`
only wires these together and holds no rendering or business logic itself."""

from .file_section import render_file_section
from .header import render_header_with_version
from .upload import collect_uploaded_files
from .upload_dialog import get_uploaded_file_sep_pairs, render_upload_trigger

__all__ = [
    "render_file_section",
    "render_header_with_version",
    "collect_uploaded_files",
    "render_upload_trigger",
    "get_uploaded_file_sep_pairs",
]
