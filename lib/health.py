"""
``/healthz`` liveness probe for the Flask and Quart backends.

The 2plot.ai hub sweeps every satellite's ``/healthz`` once an hour and records
up/down + latency — that's the "Satellite health & reach" panel on ``/traffic``
(the traffic rollup this app POSTs supplies the other half). The FastAPI build
already declares a typed ``/healthz`` in ``lib/asgi_routes`` so it shows up in
Swagger; this module gives the other two backends the same endpoint, so the
probe result doesn't depend on which backend a deployment happens to run.

Keep it cheap: the hub measures the round trip, so any work done here is
reported back as this app being slow.
"""
from __future__ import annotations

import os

import dash


def health_payload(backend: str) -> dict:
    """The probe body. ``ok`` is what the battery gates on; ``app`` says
    WHO answered and ``build`` says WHICH artifact — the two fields that
    make a mis-deploy visible.

    THE ``app`` FIELD IS NOT DECORATION. Without it a probe cannot tell which
    satellite answered, only that *something* did — so a host serving another
    satellite's code looks perfectly healthy. That is exactly how the network's
    `flows` host went undetected while identifying itself as ``"email"``: every
    check was green because no check asked "green *as whom*?".

    It is read from ``satellite_reporter.app_key()`` — the same resolver the
    traffic rollup and the bulletin use — rather than written as a literal
    here. A literal would agree with the deployment only until someone set
    ``SATELLITE_APP_KEY`` and never updated it, which reintroduces the bug in
    the very field meant to catch it.
    """
    from lib.satellite_reporter import app_key

    payload = {
        "ok": True,
        "app": app_key(),
        "backend": backend,
        "dash_version": dash.__version__,
    }
    # Which commit the RUNNING instance was built from. This is what lets CD
    # verify the artifact it shipped rather than whichever build happens to
    # be serving: a Render service with a disk restarts with a blip instead
    # of overlapping instances, so a bare 200 proves nothing about WHICH
    # build answered (the muicharts finding, 2026-08-21 — its battery had
    # been verifying the previous release on every run, invisibly, until a
    # new surface made the race lose). Optional on purpose: omitted where
    # the platform variable does not exist, so the fleet's probe contract
    # is unchanged.
    build = os.environ.get("RENDER_GIT_COMMIT")
    if build:
        payload["build"] = build
    return payload


def register_health_route(app, backend: str) -> None:
    """Mount ``/healthz`` on Flask/Quart. No-op on FastAPI (already typed)."""
    if backend == "fastapi":
        return

    server = app.server
    payload = health_payload(backend)

    if backend == "quart":
        from quart import jsonify

        @server.get("/healthz")
        async def _healthz():  # pragma: no cover — quart runtime
            return jsonify(payload)
    else:
        from flask import jsonify

        @server.get("/healthz")
        def _healthz():
            return jsonify(payload)

    print(f"[boilerplate] /healthz registered ({backend}) — "
          "the 2plot.ai hourly health sweep probes this path.")
