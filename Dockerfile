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

WORKDIR /app

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

# run:server is the Flask WSGI callable (run.py: `server = app.server`).
#
# Shell form so ${PORT} and ${WEB_CONCURRENCY} expand when the container
# starts rather than when it is built. The 120s timeout is not decoration:
# /ai-agent and /benchmark call thinking models, and while background
# callbacks (lib/background.py) hand that work to a forked worker on Linux, a
# deployment that turns them off with BACKGROUND_CALLBACKS=off runs the
# generation inside the request — where gunicorn's 30s default would kill it
# mid-flight and report nothing useful.
CMD gunicorn run:server --bind "0.0.0.0:${PORT}" --workers "${WEB_CONCURRENCY:-2}" --threads 4 --timeout 120 --access-logfile - --error-logfile -
