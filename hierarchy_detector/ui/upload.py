"""Turns the raw list of Streamlit `UploadedFile` objects into de-duplicated
(file_key, display_name, DataFrame) entries ready for rendering."""

from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd

from .data_loading import load_csv


def collect_uploaded_files(uploaded_files) -> List[Tuple[str, str, pd.DataFrame]]:
    """De-duplicate display names in case two uploaded files share a filename."""
    name_counts: Dict[str, int] = {}
    entries: List[Tuple[str, str, pd.DataFrame]] = []
    for uf in uploaded_files:
        df = load_csv(uf.getvalue(), uf.name)
        count = name_counts.get(uf.name, 0)
        name_counts[uf.name] = count + 1
        display_name = uf.name if count == 0 else f"{uf.name} ({count + 1})"
        file_key = f"file{len(entries)}_{uf.name}"
        entries.append((file_key, display_name, df))
    return entries
