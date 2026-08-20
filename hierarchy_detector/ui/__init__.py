"""Streamlit rendering layer. Each module owns one rendering concern; `app.py`
only wires these together and holds no rendering or business logic itself."""

from .file_section import render_file_section
from .footer import render_version_footer
from .upload import collect_uploaded_files

__all__ = [
    "render_file_section",
    "render_version_footer",
    "collect_uploaded_files",
]
