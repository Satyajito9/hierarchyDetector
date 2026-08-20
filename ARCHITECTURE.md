# Hierarchy Detector & Validator — Architecture & Deployment Notes

## What it is

A single-page internal web tool (Streamlit) for exploring CSV files: it either
**detects** likely top-to-bottom column hierarchies in an uploaded file
automatically (e.g. `Category -> Subcategory -> Item`), or lets a user
**validate** a specific hierarchy they define by hand against the data,
reporting compliance % and the exact rows that break it.

There is no database, no persistent storage, and no calls out to any other
internal or external service. It is a pure compute-and-display tool: a file
goes in over HTTP, pandas crunches it in memory, results render in the
browser. Nothing is written to disk and nothing survives past the browser
session / container restart.

## Tech stack

- Python 3.11
- [Streamlit](https://streamlit.io/) (`>=1.45,<2.0`) — the web framework;
  handles the HTTP/WebSocket server, UI widgets, and browser rendering. The
  `1.45` floor is required for `st.selectbox(accept_new_options=True)`,
  used by the separator control below.
- pandas (`>=2.0,<3.0`) — all data processing
- No database, no message queue, no external API calls, no secrets/env vars
  required at runtime

## Code layout

The app is a `hierarchy_detector/` package plus a thin `app.py` entry point —
no business logic or rendering logic lives in `app.py` itself.

| Path | Role |
|---|---|
| `app.py` | Entry point / orchestrator only: page config, file-upload wiring, tab layout. Delegates everything else to `hierarchy_detector`. |
| `hierarchy_detector/__init__.py` | Exposes `__version__`, read from the repo-root `VERSION` file. |
| `hierarchy_detector/core/` | Pure computation layer — no Streamlit or I/O dependency; independently testable. Split by concern: `profiling.py` (column stats), `compliance.py` (chain compliance calculation), `bad_records.py` (per-row violation reasons), `levels.py` (shared level representation), `detect.py` (automatic hierarchy detection), `validate.py` (user-specified hierarchy validation). |
| `hierarchy_detector/ui/` | Streamlit rendering layer, one concern per module: `styles.py`/`diagram.py` (hierarchy diagram), `upload_dialog.py` (upload button + modal dialog, file picker and separator block laid out side by side), `separator_picker.py` (single editable-dropdown separator field), `data_loading.py` (cached wrappers around `core`), `upload.py` (upload-to-DataFrame wiring), `formatting.py`, `downloads.py`, `reports.py` (exception reports), `profile_view.py`, `chain_view.py`, `detect_view.py`, `validate_view.py`, `file_section.py`, `header.py` (page title with version subscript). |
| `VERSION` | Single source of truth for the app version — read by `hierarchy_detector/__init__.py`, shown as a subscript next to the page title, and baked into the Docker image label. |
| `CHANGELOG.md` | Keep-a-Changelog-style history, updated alongside `VERSION` bumps. |
| `Dockerfile` | Single-stage build (`python:3.11-slim`), installs `requirements.txt`, copies `VERSION`, `hierarchy_detector/`, and `app.py`, exposes port 8501. Takes an `APP_VERSION` build arg set as an OCI image-version label. |
| `azure-pipelines.yml` | CI/CD scaffold written for an **Azure App Service** target (build → push to ACR → deploy). Placeholders for the ACR name / service connections / app name are still unfilled — this pipeline is Azure-App-Service-specific and would need to be replaced, not reused as-is, if the target hosting mechanism is different (e.g. Kubernetes). Note: this file is referenced here but is not currently present in the repo. |

## Data flow / statelessness

1. User clicks "Upload CSV file(s)", which opens a modal dialog
   (`upload_dialog.py`, backed by `st.dialog`) with a file picker and a
   separator block laid out side by side, plus a Submit button. The
   separator block (`separator_picker.py`) is a single editable dropdown
   (`st.selectbox(accept_new_options=True)`, options comma/pipe/semicolon,
   comma default) — pick a preset or type a custom character into the same
   field. Note: typing a character that isn't already in the option list
   makes this widget show its filtered option list plus an "Add new
   option" prompt before the typed value is accepted — a known, reported
   UX rough edge, kept for now because the two alternatives tried in its
   place (two independent widgets; a custom HTML/JS component) were each
   rejected for other reasons. Submitting appends the
   files and resolved separator as a new batch in `session_state` (rather
   than overwriting the previous submission) and closes the dialog — so
   re-opening the dialog and uploading more files keeps every file, and its
   analysis state, from earlier submissions in the same session.
2. The bytes are parsed into a pandas DataFrame **in memory** (`io.BytesIO`,
   no temp files written to disk) using the chosen separator. A file that
   fails to parse with it (corrupted/unreadable) is discarded from session
   state and reported with a temporary toast ("'<name>' is corrupted —
   please retry the upload") instead of a page-level error — so it doesn't
   linger in the tab list or get silently re-parsed (and re-reported) on
   every later rerun, and isn't fatal to the rest of the batch.
3. Results are computed in-process and cached in memory only, keyed by a hash
   of the inputs (`st.cache_data`, bounded to 20 entries / 1 hour TTL per
   cached function — added specifically so memory can't grow unbounded under
   sustained multi-user traffic).
4. Nothing is persisted anywhere. Restarting the process/container clears
   all state. Two different containers never need to share data, a disk
   volume, or a cache store.

## Authentication — currently none in the app

`app.py` has no login/access-control logic. As it
stands today, **anyone who can reach the deployed URL can use the app** —
access control, if required, currently has to come from the hosting layer
(see "Access" below), not the app itself.

## Health check

The container's `HEALTHCHECK` and any orchestrator's liveness/readiness
probes should point at Streamlit's built-in endpoint:

```
GET /_stcore/health   → 200 OK
```

## Runtime characteristics relevant to a hosting decision

- **CPU-bound, not I/O-bound.** Hierarchy detection is an exhaustive
  pandas-driven search; cost scales with file size and column count. There
  is currently no server-side cap on upload size beyond Streamlit's default
  200 MB limit.
- **Single process per container, no internal worker pool.** Unlike a
  typical WSGI app (gunicorn with N workers), one `streamlit run` process
  handles all connected sessions for that container via threads. Concurrent
  heavy computations from different users on the *same* container will
  contend for CPU (Python GIL) — this is a reason to run multiple replicas,
  not a bug to fix in code.
- **Stateful per-browser-tab WebSocket connection.** Streamlit keeps a live
  WebSocket per open browser tab plus an in-memory `session_state` for that
  tab, both tied to whichever specific container instance first served it.
  This has a direct consequence for the load-balancer question below.

---

## Running in multiple containers behind a load balancer

This works, but one thing must be configured correctly or the app will
misbehave: **the load balancer needs session affinity (sticky sessions),
not plain round-robin.**

Why: each browser tab opens one long-lived WebSocket to whichever container
served it first, and that container is the only one holding that tab's
`session_state` (uploaded file, widget state, etc.) in memory. If a
load balancer round-robins a reconnect or a follow-up request to a
*different* container, that container has no idea about the user's
in-progress session — the user sees the app reset, get disconnected, or
have to re-upload their file.

What to configure, depending on the hosting mechanism chosen:

- **Azure App Service**: ARR affinity (cookie-based session affinity) —
  usually on by default, just confirm it isn't disabled.
- **Kubernetes + ingress-nginx**: set
  `nginx.ingress.kubernetes.io/affinity: cookie` on the Ingress resource.
- **Generic load balancer (HAProxy, AWS ALB, etc.)**: enable cookie-based
  sticky sessions.
- If the internal hosting mechanism has no way to do sticky sessions, this
  app will not behave correctly behind it with more than one replica — this
  is a hard requirement, not a tuning knob.

Other things that fall out of the architecture, for scaling:

- **No shared volume or shared cache needed between replicas** — nothing is
  written to disk, and each container's `st.cache_data` cache is local to
  it (a cache miss on one replica just means it recomputes; there's no
  correctness risk from replicas not sharing a cache, just a lower
  effective hit rate as replica count grows).
- **Size replicas/CPU by expected concurrent active users doing detection
  at the same time**, not by raw request rate — since the workload is
  CPU-bound, CPU-based autoscaling is more representative than
  request-count-based autoscaling.
- Use `/_stcore/health` for both liveness and readiness probes.

---

## How someone accesses the app once deployed

It's a normal web page — open a browser to whatever URL the hosting
platform assigns or routes to it (e.g. `https://<app-name>.azurewebsites.net`
for App Service, or an internal hostname if hosted on an internal
platform). No client install, no special protocol beyond HTTPS/WebSocket.

Two things worth deciding explicitly with ops, since the app itself has no
access control today:

1. **Network exposure**: if the internal hosting platform places this
   behind a corporate VPN / internal-only load balancer / private network,
   access is naturally restricted to whoever can reach that network — that
   policy lives entirely at the infra layer.
2. **Per-user login / domain restriction**: if that's required beyond
   network-level restriction, it needs to be added either (a) in-app, by
   finishing and wiring in something like the `test.py` prototype
   (Streamlit's `st.login()` OIDC support, needs an identity provider
   configured in `.streamlit/secrets.toml`), or (b) at the platform/
   reverse-proxy layer in front of the container (e.g. Azure App Service
   Easy Auth, an API gateway doing OIDC) — the latter is usually simpler
   and keeps auth out of the app entirely. Worth asking the ops team which
   of these their internal hosting mechanism already provides.

---

## Support / contact

The app's landing page includes a static line — "Questions or feedback?
Contact us at plugincoe@o9solutions.com" — as the one support channel
surfaced in-app. It's plain markdown in `app.py`, meant as a contact point
for usage/feature/bug queries — not an access-control mechanism. See
"Authentication" above for how access itself is (not) controlled.

---

## Versioning and releases

The app uses [Semantic Versioning](https://semver.org/). To cut a release:

1. Bump the version string in the repo-root `VERSION` file.
2. Add an entry to `CHANGELOG.md` describing what changed, under that version.
3. Build the Docker image with the version baked in:
   ```
   docker build --build-arg APP_VERSION=$(cat VERSION) -t hierarchydetector:$(cat VERSION) .
   ```
4. Optionally tag the commit `git tag vX.Y.Z` to tie the image back to an exact commit.

The running version is visible in two places without needing repo access:
a subscript next to the page title, and `docker inspect` on the running
container (`org.opencontainers.image.version` label).

---

## Known open items (not yet resolved)

- `azure-pipelines.yml` has unfilled placeholders (ACR name, service
  connection names, App Service name) and assumes an Azure App Service
  target specifically — if the internal hosting mechanism is different,
  this file should be treated as a reference example, not reused directly.
- No authentication is currently wired into the app (see above).
- No server-side upload size limit beyond Streamlit's default.
