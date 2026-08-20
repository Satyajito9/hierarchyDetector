"""Hierarchy Detector & Validator — package root.

`__version__` is read from the `VERSION` file at the repo root (one directory
above this package), which is the single source of truth for the app's
version across the running app, the Docker image label, and releases.
"""

from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"


def _read_version() -> str:
    try:
        return _VERSION_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "0.0.0"


__version__ = _read_version()
