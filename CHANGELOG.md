# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/).

## [1.2.0] - 2026-08-20

### Changed
- `evaluate_chain`/`pairwise_symmetric_compliance` now accept a shared
  column -> `astype(str)` cache (`hierarchy_detector/core/compliance.py`,
  threaded through `detect.py`/`levels.py`/`validate.py`), so each eligible
  column's string conversion happens once per `detect_hierarchies`/
  `validate_hierarchy` call instead of once per pairwise/chain check that
  references it. Measured ~15% faster on synthetic benchmarks, no change
  in results. `detect_hierarchies`'s candidate-pair/edge scan is still
  O(columns^2) in the number of eligible columns, which dominates over row
  count for wide files (benchmarked: 8->48 columns at fixed rows was ~60x
  slower; 10k->1M rows at fixed columns was ~60x slower — comparable, but
  column count grows the cost per file far more easily in practice) — this
  fix reduces the constant factor, it doesn't change that scaling.

### Added
- `runtime.txt` pinning Python 3.11, so platforms that read it (e.g.
  Streamlit Community Cloud) use the same interpreter version as
  `Dockerfile` and local development, instead of their own default.

### Fixed
- A corrupted/unreadable uploaded file no longer surfaces its raw parse
  exception as a page-level error and no longer lingers in session state
  to be silently re-parsed (and re-reported) on every later rerun. It's
  now discarded immediately and reported once via a temporary toast
  (`hierarchy_detector/ui/upload.py`, `upload_dialog.discard_files`).

### Changed
- The upload flow moved into a modal dialog opened from an "Upload CSV
  file(s)" button, instead of a separator dropdown and file uploader
  sitting permanently on the page (`hierarchy_detector/ui/upload_dialog.py`,
  built on `st.dialog`). The dialog lays the file picker and the separator
  block out side by side, plus a Submit button; submitting closes the
  dialog. Each submission is appended to the session's list of uploads
  rather than replacing it, so re-opening the dialog to add more files no
  longer drops files (and their in-progress analysis) uploaded earlier in
  the same session.
- The separator control (`hierarchy_detector/ui/separator_picker.py`) is a
  single editable dropdown (`st.selectbox(accept_new_options=True)`) —
  comma/pipe/semicolon presets, or type a custom character into the same
  field. This filters the option list and shows an "Add new option" prompt
  while typing a character not already in the list — a known UX rough
  edge — but is kept over two alternatives that were tried and discarded:
  two independent widgets (dropdown + separate text field), and a custom
  HTML/JS component wrapping a native `<input list=...>` that didn't look
  right in the UI.

## [1.1.0] - 2026-08-20

### Added
- CSV separator picker: choose comma (default), pipe, semicolon, or a
  custom single character, before uploading file(s). A file that fails to
  parse with the chosen separator is reported and skipped rather than
  aborting the whole upload (`hierarchy_detector/ui/separator_picker.py`).

### Changed
- The running-version display moved from a page footer to a subscript next
  to the page title (`hierarchy_detector/ui/header.py`), since the earlier
  fixed-position footer/badge wasn't reliably visible.

## [1.0.0] - 2026-08-20

First tracked version. Introduces version tracking itself, alongside a
restructure of the codebase into a modular, deployable layout.

### Changed
- Restructured the codebase from two flat files (`app.py`, `hierarchy_engine.py`)
  into a `hierarchy_detector/` package:
  - `core/` — pure computation, split by concern: `profiling`, `compliance`,
    `bad_records`, `levels`, `detect`, `validate`.
  - `ui/` — Streamlit rendering, split by concern: diagram, reports,
    downloads, column profile, detect/validate views, file section, footer.
- `app.py` is now a thin orchestrator only (page config, file upload wiring,
  tab layout) — no business logic or rendering logic of its own.

### Added
- `VERSION` file as the single source of truth for the app version, read by
  `hierarchy_detector/__init__.py` (`__version__`).
- App footer showing the running version, so a deployed instance's version
  can be confirmed from the UI itself.
- `CHANGELOG.md` (this file) to track future releases.
- Docker image now takes an `APP_VERSION` build arg and sets it as the
  `org.opencontainers.image.version` OCI label, so `docker inspect` on a
  running container reveals which version it's running.

### Features Added
- Consolidated exceptions from all detected hierarchies in exception report
- Added summary and contact email for better user adaptability
- Download option now has 2 options, 1. download full data, 2. download exceptions only

### Bugs fixed
- Fixed %compaliance calculation; considers total rows including null rows as denominator now