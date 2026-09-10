"""The in-flight run buffer, and the reason it is not a dict.

THE BUG THIS FILE EXISTS FOR. The first version of `lib/scene_stream` kept
runs in a module-level dict. That is correct in development — `python run.py`
is one process — and broken in production, where the Dockerfile ends:

    gunicorn run:server --workers "${WEB_CONCURRENCY:-2}" --threads 4

and render.yaml deliberately leaves WEB_CONCURRENCY unset. The producer thread
lives in ONE worker; a poll balanced to the other finds no such run and the
page reports that the generation vanished. Roughly half of them would, at
random, with no error in any log — and no amount of local testing reproduces
it, because locally there is only ever one process.

Two tests carry that claim. `test_a_second_worker_can_read_the_run` drops this
process's cache handle and opens a fresh one — a good proxy, but still one
interpreter. `test_a_separate_interpreter_reads_the_run` spawns a real second
process, which is the actual claim rather than a stand-in for it. MEASURED
against the dict version, the second process reports `found: False` and an
empty scene; against the shared store it returns the whole run. That contrast
is the point of both tests.

Nothing here touches a network. `stream_model` is replaced by a generator that
ENDS — a mock that yields forever would hang the suite rather than fail it.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import diskcache
import pytest

from lib import scene_stream

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """A fresh cache directory per test, and no handle carried between them."""
    monkeypatch.setattr(scene_stream, "CACHE_DIR", str(tmp_path / "store"))
    monkeypatch.setattr(scene_stream, "_cache", None)
    yield
    cache = scene_stream._cache
    if cache is not None:
        cache.close()


def _stub_stream(elements, meta=None, error=None, delay=0.0):
    """A stream_model stand-in. Finite by construction."""

    def gen(**_kwargs):
        for element in elements:
            if delay:
                time.sleep(delay)
            yield ("element", element)
        if error:
            raise error
        yield ("done", meta or {"model": "stub", "output_tokens": 7})

    return gen


def _wait_done(run_id, timeout=5.0):
    """Poll until the worker finishes. Bounded, so a hang fails the test."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = scene_stream.take(run_id, 0)
        if state["done"]:
            return state
        time.sleep(0.01)
    pytest.fail(f"run {run_id} did not finish within {timeout}s")


EL = [{"id": "a", "type": "rectangle"}, {"id": "b", "type": "ellipse"}]


class TestItSharesAcrossWorkers:
    def test_a_second_worker_can_read_the_run(self, monkeypatch):
        """The whole reason this is not a dict."""
        monkeypatch.setattr(scene_stream, "stream_model", _stub_stream(EL))
        run_id = scene_stream.start(model="stub", user_prompt="x")
        _wait_done(run_id)

        # Drop this process's handle. A module-level dict would go with it;
        # anything read after this came off the shared store.
        scene_stream._cache.close()
        scene_stream._cache = None

        state = scene_stream.take(run_id, 0)
        assert state["found"] is True, (
            "the run was invisible to a fresh cache handle — this is the "
            "two-gunicorn-worker failure, reproduced"
        )
        assert [e["id"] for e in state["all"]] == ["a", "b"]

    def test_the_elements_are_really_on_disk(self, monkeypatch):
        # Asserted against a cache handle this module never created, so it
        # cannot be satisfied by any in-process state.
        monkeypatch.setattr(scene_stream, "stream_model", _stub_stream(EL))
        run_id = scene_stream.start(model="stub", user_prompt="x")
        _wait_done(run_id)

        outsider = diskcache.Cache(scene_stream.CACHE_DIR)
        try:
            meta = outsider.get(f"run:{run_id}:meta")
            assert meta is not None and meta["count"] == 2
            assert outsider.get(f"run:{run_id}:el:0")["id"] == "a"
        finally:
            outsider.close()


class TestItReallyCrossesAProcessBoundary:
    """Not a simulation — two interpreters, like two gunicorn workers.

    The handle-dropping test above is a good proxy, but a proxy: it still runs
    in one interpreter, and the thing being claimed is about separate ones.
    This spawns a real second process. Measured against the dict version it
    reports `found: False`, which IS the production bug; against the shared
    store it returns the whole run.
    """

    def test_a_separate_interpreter_reads_the_run(self, tmp_path):
        import json
        import subprocess
        import sys

        store = str(tmp_path / "xproc")
        env = {**os.environ, "SCENE_STREAM_DIR": store, "PYTHONPATH": str(REPO_ROOT)}

        produce = (
            "import time, sys\n"
            "from lib import scene_stream\n"
            "def stub(**kw):\n"
            "    for i in range(3):\n"
            "        yield ('element', {'id': 'e%d' % i, 'type': 'rectangle'})\n"
            "    yield ('done', {'model': 'stub'})\n"
            "scene_stream.stream_model = stub\n"
            "rid = scene_stream.start(model='stub', user_prompt='x')\n"
            "for _ in range(500):\n"
            "    if scene_stream.take(rid, 0)['done']: break\n"
            "    time.sleep(0.01)\n"
            "print(rid)\n"
        )
        run_id = subprocess.run(
            [sys.executable, "-c", produce], env=env, capture_output=True,
            text=True, timeout=60, check=True,
        ).stdout.strip().splitlines()[-1]

        consume = (
            "import json, sys\n"
            "from lib import scene_stream\n"
            "st = scene_stream.take(sys.argv[1], 0)\n"
            "print(json.dumps({'found': st['found'],\n"
            "                  'ids': [e['id'] for e in st['all']]}))\n"
        )
        out = subprocess.run(
            [sys.executable, "-c", consume, run_id], env=env, capture_output=True,
            text=True, timeout=60, check=True,
        ).stdout.strip().splitlines()[-1]
        seen = json.loads(out)

        assert seen["found"] is True, (
            "a second interpreter could not see the run — this is exactly what "
            "happens when a poll is balanced to the other gunicorn worker"
        )
        assert seen["ids"] == ["e0", "e1", "e2"]


class TestTheCursor:
    def test_a_poll_returns_only_what_is_new(self, monkeypatch):
        monkeypatch.setattr(scene_stream, "stream_model", _stub_stream(EL))
        run_id = scene_stream.start(model="stub", user_prompt="x")
        _wait_done(run_id)

        first = scene_stream.take(run_id, 0)
        assert len(first["elements"]) == 2
        assert first["cursor"] == 2

        second = scene_stream.take(run_id, first["cursor"])
        assert second["elements"] == [], "a repeat poll re-sent shapes"

    def test_all_always_carries_the_whole_scene(self, monkeypatch):
        # updateScene REPLACES the scene, so a caller that sent only the delta
        # would leave one shape on the canvas at a time.
        monkeypatch.setattr(scene_stream, "stream_model", _stub_stream(EL))
        run_id = scene_stream.start(model="stub", user_prompt="x")
        _wait_done(run_id)
        late = scene_stream.take(run_id, 2)
        assert late["elements"] == []
        assert len(late["all"]) == 2

    def test_a_duplicated_poll_cannot_skip_a_shape(self, monkeypatch):
        monkeypatch.setattr(scene_stream, "stream_model", _stub_stream(EL))
        run_id = scene_stream.start(model="stub", user_prompt="x")
        _wait_done(run_id)
        a = scene_stream.take(run_id, 0)
        b = scene_stream.take(run_id, 0)
        assert [e["id"] for e in a["elements"]] == [e["id"] for e in b["elements"]]


class TestFailure:
    def test_a_provider_error_is_reported_verbatim(self, monkeypatch):
        # The page shows this string. "Generation failed" would throw away the
        # useful part — a truncated budget, or a refusal.
        boom = ValueError("Truncated: hit the 24,000-token budget mid-response")
        monkeypatch.setattr(scene_stream, "stream_model", _stub_stream(EL, error=boom))
        run_id = scene_stream.start(model="stub", user_prompt="x")
        state = _wait_done(run_id)
        assert "24,000-token budget" in state["error"]
        assert state["error"].startswith("ValueError:")

    def test_elements_before_the_error_are_kept(self, monkeypatch):
        boom = RuntimeError("connection reset")
        monkeypatch.setattr(scene_stream, "stream_model", _stub_stream(EL, error=boom))
        run_id = scene_stream.start(model="stub", user_prompt="x")
        state = _wait_done(run_id)
        assert len(state["all"]) == 2

    def test_an_unknown_run_says_done_rather_than_hanging(self):
        # A polling page must stop, not ask forever about a run that will
        # never answer — an expired TTL or an instance restart looks like this.
        state = scene_stream.take("no-such-run", 0)
        assert state["found"] is False
        assert state["done"] is True
        assert state["all"] == []


class TestForget:
    def test_it_removes_the_run_and_its_elements(self, monkeypatch):
        monkeypatch.setattr(scene_stream, "stream_model", _stub_stream(EL))
        run_id = scene_stream.start(model="stub", user_prompt="x")
        _wait_done(run_id)
        scene_stream.forget(run_id)

        assert scene_stream.take(run_id, 0)["found"] is False
        outsider = diskcache.Cache(scene_stream.CACHE_DIR)
        try:
            # Leaving the element keys behind would leak the whole scene for
            # RUN_TTL after a Clear that claimed to drop it.
            assert outsider.get(f"run:{run_id}:el:0") is None
        finally:
            outsider.close()


class TestProgressIsVisibleBeforeTheEnd:
    def test_elements_appear_while_the_run_is_still_going(self, monkeypatch):
        many = [{"id": str(i), "type": "rectangle"} for i in range(6)]
        monkeypatch.setattr(
            scene_stream, "stream_model", _stub_stream(many, delay=0.05)
        )
        run_id = scene_stream.start(model="stub", user_prompt="x")

        # Catch it mid-flight. If elements only became visible at the end,
        # the page would be a spinner with extra steps.
        deadline = time.monotonic() + 5.0
        saw_partial = False
        while time.monotonic() < deadline:
            state = scene_stream.take(run_id, 0)
            if state["all"] and not state["done"]:
                saw_partial = True
                break
            if state["done"]:
                break
            time.sleep(0.01)
        _wait_done(run_id)
        assert saw_partial, "no element was readable before the run finished"

    def test_a_never_polled_run_still_completes(self, monkeypatch):
        monkeypatch.setattr(scene_stream, "stream_model", _stub_stream(EL))
        run_id = scene_stream.start(model="stub", user_prompt="x")
        state = _wait_done(run_id)
        assert state["done"] and state["meta"]["model"] == "stub"
