# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/).

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