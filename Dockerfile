# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# dash-excalidraw documentation site (run.py) — production image for
# https://excalidraw.2plot.dev.
#
# The component bundle (dash_excalidraw/dash_excalidraw.js, 7.7 MB) is
# COMMITTED, so no Node/webpack build happens here: this is a pure-Python
# image serving the pre-built Dash app with gunicorn. node_modules/ is
# excluded via .dockerignore.
#
# It used to install nodejs + npm and run `npm install` — pulling the whole
# Excalidraw/webpack/TypeScript dev toolchain into a production image that
# never runs a line of it, on every build. Removed 2026-08-21 with the
# gate-wave pass; if a future change needs a build step, it belongs in CI
# producing a committed artifact, not in the runtime image.
# ---------------------------------------------------------------------------
FROM python:3.12-slim

# PYTHONUNBUFFERED        -> stream logs straight to stdout, so Render shows
#                            them live. Learned on email.2plot.dev: without it
#                            Python block-buffers stdout when it is a pipe and
#                            gunicorn never flushes, so every boot diagnostic
#                            this app prints — the backend it resolved, whether
#                            the bulletin is wired, the [visibility] and [auth]
#                            guards the wave verifies against — is swallowed.
#                            The line that would have explained an outage was
#                            the line that got lost.
# PYTHONDONTWRITEBYTECODE -> no .pyc clutter in the image
# DASH_BACKEND=flask      -> WSGI backend served by gunicorn (not fastapi/quart)
# PORT                    -> local default; Render overrides it at runtime, and
#                            the CMD below binds whatever it is told
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DASH_BACKEND=flask \
    PORT=8050

# curl only — the HEALTHCHECK below uses it. Deliberately NO nodejs/npm:
# this image used to apt-install both and `npm install` a package.json whose
# toolchain is the COMPONENT's build (webpack, TypeScript, the Excalidraw
# dev tree) and which nothing in the running site touches — the bundle is
# committed. A docs site is a Python app; a fork that genuinely builds JS in
# its image adds that toolchain knowingly rather than by inheritance.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CACHE SEMANTICS — read this before shipping a dependency upgrade. The pip
# layer below re-runs ONLY when vendor/ or requirements.txt BYTES change. A
# `>=` floor can NEVER pull a newer release through a cache hit: a code-only
# commit rebuilds the app layers underneath while pip silently keeps whatever
# version the image was first built with. That has bitten the fleet twice —
# at 2.6.1 and again at 2.7.1 — and both times the site looked fine, because
# a stale package degrades quietly rather than failing.
#
# So ship every dependency upgrade as a floor bump in requirements.txt, and
# grep the NUMBER rather than the file: it also lives in run.py's
# LLMS_PKG_FLOOR and in ci.yml's two asserts. The bump IS the cache bust, and
# the boot floor turns a stale image from a silent downgrade into a loud
# refusal to start.
#
# Python deps first so this layer caches across app-code changes.
# vendor/ must come along: requirements.txt installs dash-clerk-auth 1.0.5
# from a local tarball there (vendored across the 2plot network, not on PyPI).
COPY requirements.txt ./
COPY vendor/ ./vendor/
RUN pip install --no-cache-dir -r requirements.txt
# markdown2dash 0.1.2 pins gunicorn<22, against the CVE-driven gunicorn>=23
# floor in requirements.txt (CVE-2024-6827, CVE-2024-1135 — request
# smuggling). Its real dependencies are all in requirements.txt already, so it
# installs without its dependency graph. Same pair in .github/workflows/ci.yml
# and render.yaml; CI asserts the resolved gunicorn version inside this image,
# which is what keeps the dodge honest.
RUN pip install --no-cache-dir --no-deps markdown2dash==0.1.2

# Copy the application. run.py resolves templates/, dash_excalidraw/, docs/,
# assets/, components/, lib/ and pages/ relative to the working directory, so
# it must run from /app (the repo root) — which it does under this WORKDIR.
COPY . .

# Documentation only; the process binds to $PORT (below).
EXPOSE 8050

# The 2plot.ai hub's hourly sweep probes /healthz; give the container the same
# check so an unhealthy process is visible to the orchestrator too. Shell form
# so the variable expands at runtime, and DEFAULTED AT THE POINT OF USE:
# `${PORT}` bare reads as the empty string when the platform sets the variable
# to nothing, and `http://localhost:/healthz` is not a URL — the probe fails
# forever against a perfectly healthy app. The ENV default above covers unset,
# not set-empty; these two are the only places the number is used, so they
# carry it. 8050 is THIS fork's port (the template's number is 8550).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT:-8050}/healthz" || exit 1

# run:server is the Flask WSGI callable (run.py: `server = app.server`).
#
# Shell form so ${PORT} and ${WEB_CONCURRENCY} expand when the container
# starts rather than when it is built, with the port defaulted at the point of
# use for the same set-empty reason the HEALTHCHECK above spells out — a bare
# ${PORT} collapses the bind to "0.0.0.0:" and gunicorn dies on the address.
# The 120s timeout is not decoration:
# /ai-agent and /benchmark call thinking models, and while background
# callbacks (lib/background.py) hand that work to a forked worker on Linux, a
# deployment that turns them off with BACKGROUND_CALLBACKS=off runs the
# generation inside the request — where gunicorn's 30s default would kill it
# mid-flight and report nothing useful.
CMD gunicorn run:server --bind "0.0.0.0:${PORT:-8050}" --workers "${WEB_CONCURRENCY:-2}" --threads 4 --timeout 120 --access-logfile - --error-logfile -
