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
- [Streamlit](https://streamlit.io/) (`>=1.38,<2.0`) — the web framework;
  handles the HTTP/WebSocket server, UI widgets, and browser rendering
- pandas (`>=2.0,<3.0`) — all data processing
- No database, no message queue, no external API calls, no secrets/env vars
  required at runtime

## Code layout

| File | Role |
|---|---|
| `app.py` | UI layer — file upload, mode selection, rendering tables/diagrams, CSV export. All Streamlit-specific code lives here. |
| `hierarchy_engine.py` | Pure computation layer — column profiling, the exhaustive hierarchy-detection algorithm, compliance validation, bad-record-reason generation. No Streamlit or I/O dependency; independently testable. |
| `Dockerfile` | Single-stage build (`python:3.11-slim`), installs `requirements.txt`, copies the two files above, exposes port 8501. |
| `azure-pipelines.yml` | CI/CD scaffold written for an **Azure App Service** target (build → push to ACR → deploy). Placeholders for the ACR name / service connections / app name are still unfilled — this pipeline is Azure-App-Service-specific and would need to be replaced, not reused as-is, if the target hosting mechanism is different (e.g. Kubernetes). |

## Data flow / statelessness

1. User uploads a CSV via the browser (`st.file_uploader`).
2. The bytes are parsed into a pandas DataFrame **in memory** (`io.BytesIO`,
   no temp files written to disk).
3. Results are computed in-process and cached in memory only, keyed by a hash
   of the inputs (`st.cache_data`, bounded to 20 entries / 1 hour TTL per
   cached function — added specifically so memory can't grow unbounded under
   sustained multi-user traffic).
4. Nothing is persisted anywhere. Restarting the process/container clears
   all state. Two different containers never need to share data, a disk
   volume, or a cache store.

## Authentication — currently none in the app

`app.py` has no login/access-control logic. There's an unused prototype
(`test.py`, not imported by `app.py`) sketching a Streamlit
`st.login()` + domain-allowlist pattern, but it isn't wired in. As it
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

## Known open items (not yet resolved)

- `azure-pipelines.yml` has unfilled placeholders (ACR name, service
  connection names, App Service name) and assumes an Azure App Service
  target specifically — if the internal hosting mechanism is different,
  this file should be treated as a reference example, not reused directly.
- No authentication is currently wired into the app (see above).
- No server-side upload size limit beyond Streamlit's default.
