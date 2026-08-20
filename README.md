# hierarchyDetector
Detects and validates hierarchy in raw files.

## Run locally

```
pip install -r requirements.txt
streamlit run app.py
```

## Run with Docker

```
docker build --build-arg APP_VERSION=$(cat VERSION) -t hierarchydetector:$(cat VERSION) .
docker run -p 8501:8501 hierarchydetector:$(cat VERSION)
```

## Code layout

- `app.py` — thin entry point / orchestrator only.
- `hierarchy_detector/core/` — pure hierarchy detection & validation logic.
- `hierarchy_detector/ui/` — Streamlit rendering layer.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full breakdown, deployment
notes, and versioning/release process. See [CHANGELOG.md](CHANGELOG.md) for
release history.
