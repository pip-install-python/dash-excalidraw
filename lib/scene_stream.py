"""In-flight scene generations, so a page can watch one being drawn.

WHY A POLLED BUFFER AND NOT A PUSH SOCKET
The obvious shape for "show it as it arrives" is a websocket. This is a polled
buffer instead, for a reason that outranks elegance: the app is tested and
deployed on BOTH backends (ci.yml runs the whole suite against flask and
fastapi), and a socket transport would work on one of them. A generation
writes elements here as they parse; a `dcc.Interval` on the page collects
whatever is new. Moving to a real socket later means replacing the collector,
not the generator — `take()` is the seam.

WHY THE STATE IS SHARED AND NOT A MODULE-LEVEL DICT
This is the part that was wrong first time and is worth stating plainly,
because in development the broken version looks perfect. `python run.py` is
one process, so a dict in this module is visible to every poll. Production is
not one process — the Dockerfile ends:

    gunicorn run:server --workers "${WEB_CONCURRENCY:-2}" --threads 4

and render.yaml deliberately leaves WEB_CONCURRENCY unset, so it is two. The
producer thread lives in ONE of them; a poll load-balanced to the other finds
no such run and the page reports the generation vanished. Roughly half of
them would, at random, with no error anywhere — the failure a developer cannot
reproduce locally no matter how many times they try.

So the store is diskcache: the same on-disk cache Dash's own DiskcacheManager
uses, already a dependency (requirements.txt), and shared by every worker on
the instance. One element per key rather than one growing list per run, so an
append is a single write instead of a read-modify-write that gets quadratically
slower as the scene fills.

WHAT IT IS STILL NOT. Elements are not persisted beyond RUN_TTL, a run belongs
to whoever holds its id, and an instance restart drops everything in flight.
That is the right trade for a documentation demo and the wrong one for a
product, which is why it says so here rather than pretending otherwise.
"""

from __future__ import annotations

import atexit
import os
import tempfile
import threading
import time
import uuid
from typing import Any

import diskcache

from lib.scene_ai import stream_model

# A finished run stays readable for this long so the last poll can collect the
# tail, then it expires. Long enough to survive a slow browser, short enough
# that a busy day cannot grow the cache without bound. diskcache enforces it
# on read, so nothing has to sweep.
RUN_TTL = 300.0

# Every worker on the instance must open the SAME directory or the sharing
# does not happen — which is exactly the bug this module exists to avoid, in a
# quieter form. Configurable because a container may want it on a mounted
# volume; the default lands in the system temp dir, which on Render is local
# to the instance and shared by its workers.
CACHE_DIR = os.environ.get(
    "SCENE_STREAM_DIR", os.path.join(tempfile.gettempdir(), "excalidraw-scene-stream")
)

_cache: diskcache.Cache | None = None
_cache_lock = threading.Lock()


def cache() -> diskcache.Cache:
    """The shared store, opened once per process.

    Lazily, and never at import: opening a Cache creates the directory and an
    SQLite file, and doing that while Dash is registering pages would put disk
    I/O on the boot path for every deployment, including the ones that never
    generate a scene.
    """
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                _cache = diskcache.Cache(CACHE_DIR)
                atexit.register(_cache.close)
    return _cache


def _meta_key(run_id: str) -> str:
    return f"run:{run_id}:meta"


def _el_key(run_id: str, index: int) -> str:
    return f"run:{run_id}:el:{index}"


def start(**call_kwargs: Any) -> str:
    """Begin a generation in a worker thread; return its run id.

    A THREAD, not a background-callback worker. `lib/background.py` reports
    that its diskcache MANAGER is off on macOS because the forked child dies,
    and streaming needs the producer to stay alive for the whole call — a
    thread is what actually runs everywhere this app runs. The work is a
    network read, so the GIL is not the constraint. (Note the two uses of
    diskcache are unrelated: that one runs jobs, this one only stores bytes.)
    """
    run_id = uuid.uuid4().hex
    c = cache()
    c.set(
        _meta_key(run_id),
        {
            "count": 0,
            "done": False,
            "cancelled": False,
            "error": None,
            "meta": None,
            "started": time.time(),
        },
        expire=RUN_TTL,
    )

    def worker() -> None:
        error = None
        final_meta = None
        count = 0
        stopped = False
        # Held in a name rather than iterated inline, so `close()` below is a
        # deliberate act and not left to the garbage collector.
        stream = stream_model(**call_kwargs)
        try:
            for kind, payload in stream:
                if kind == "element":
                    c.set(_el_key(run_id, count), payload, expire=RUN_TTL)
                    count += 1
                else:
                    final_meta = payload
                # The element is written BEFORE the count that reveals it, so
                # a poll can never see a count it cannot read an element for.
                state = _touch(run_id, count=count, meta=final_meta)
                if state is None or state.get("cancelled"):
                    # None means the run was forgotten while in flight, which
                    # is a stop by another name. Either way: stop pulling
                    # tokens. Checked between elements rather than on a timer
                    # because that is where control returns to us.
                    stopped = True
                    break
        except Exception as exc:  # noqa: BLE001 - any provider error, verbatim
            # Verbatim because the page shows it: a truncated-budget message
            # or a refusal is the useful answer, not "generation failed".
            error = f"{type(exc).__name__}: {exc}"
        finally:
            # THIS is what stops the bill. Closing the generator raises
            # GeneratorExit at its suspended `yield`, which unwinds the
            # `with client.messages.stream(...)` block and closes the HTTP
            # response. The provider stops generating; billing stops at the
            # tokens already produced. Merely ending the poll would leave the
            # model running to its full budget with nobody reading it.
            stream.close()
            _touch(
                run_id, count=count, meta=final_meta, error=error, done=True,
                cancelled=stopped,
            )

    threading.Thread(target=worker, name=f"scene-{run_id[:8]}", daemon=True).start()
    return run_id


def _touch(run_id: str, **fields: Any) -> dict | None:
    """Merge fields into a run's metadata, refreshing its TTL.

    Under diskcache's own transaction so two threads in one process cannot
    interleave a read-modify-write. Cross-PROCESS the only writer is the
    worker thread that owns the run, so this is sufficient — a poll never
    writes.
    """
    c = cache()
    key = _meta_key(run_id)
    with c.transact():
        current = c.get(key)
        if current is None:
            # Expired mid-run, or someone called forget(). Do not resurrect
            # it: a run nobody is watching should stay gone.
            return None
        # A plain update, and the caller decides what to send: mid-stream it
        # passes only `count` and `meta`, so `error` and `done` keep whatever
        # they held. Filtering by truthiness here would silently refuse to
        # write count=0 or done=False.
        current.update(fields)
        c.set(key, current, expire=RUN_TTL)
        # Returned so the caller can read `cancelled` without a second round
        # trip — the worker checks it after every element.
        return current


def take(run_id: str, cursor: int) -> dict:
    """Everything known about a run, plus the elements after `cursor`.

    The cursor is an index into the element sequence rather than a timestamp,
    so a poll that arrives late, twice, or on a different worker cannot skip
    or duplicate a shape — the page's own `cursor` is the only state the
    browser has to keep.
    """
    c = cache()
    info = c.get(_meta_key(run_id))
    if info is None:
        # Unknown or expired. `done` True so a polling page stops rather than
        # asking forever about a run that will never answer.
        return {
            "found": False,
            "elements": [],
            "all": [],
            "cursor": cursor,
            "done": True,
            "cancelled": False,
            "error": None,
            "meta": None,
            "elapsed": 0.0,
        }

    count = info.get("count", 0)
    everything = []
    for i in range(count):
        element = c.get(_el_key(run_id, i))
        if element is not None:
            everything.append(element)

    return {
        "found": True,
        # New since the last poll, for a caller that wants a delta...
        "elements": everything[cursor:],
        # ...and everything so far, because Excalidraw's updateScene REPLACES
        # the scene rather than appending to it. Sending only the delta would
        # leave one shape on the canvas at a time.
        "all": everything,
        "cursor": len(everything),
        "done": bool(info.get("done")),
        "cancelled": bool(info.get("cancelled")),
        "error": info.get("error"),
        "meta": info.get("meta"),
        "elapsed": max(0.0, time.time() - info.get("started", time.time())),
    }


def cancel(run_id: str) -> bool:
    """Ask a run to stop pulling tokens. Returns whether there was one.

    Sets a flag the producer checks after every element; the producer is the
    only thing that touches the provider, so this is cooperative rather than a
    kill. In practice that means the stop lands within one element — the gap
    between two `yield`s — not instantly mid-token.

    IT WORKS ACROSS PROCESSES, which is the whole reason the flag lives in the
    shared store: with `gunicorn --workers 2` the click that presses the brake
    is very likely handled by the worker that is NOT running the generation. A
    threading.Event here would have looked correct in development and stopped
    nothing in production half the time.
    """
    state = _touch(run_id, cancelled=True)
    return state is not None


def cancel_all() -> int:
    """Stop every run this instance knows about. Returns how many.

    The panic button. `cancel` needs a run id, which is no use when the thing
    that has gone wrong is "something is spending money and I am not sure
    what". Iterates the shared store, so it reaches runs started by any worker
    on this instance — not only this one.
    """
    stopped = 0
    c = cache()
    for key in list(c):
        if isinstance(key, str) and key.startswith("run:") and key.endswith(":meta"):
            info = c.get(key)
            if info is not None and not info.get("done"):
                info["cancelled"] = True
                c.set(key, info, expire=RUN_TTL)
                stopped += 1
    return stopped


def forget(run_id: str) -> None:
    """Drop a run early — a Clear button should not wait for the TTL."""
    c = cache()
    info = c.get(_meta_key(run_id))
    count = info.get("count", 0) if info else 0
    for i in range(count):
        c.delete(_el_key(run_id, i))
    c.delete(_meta_key(run_id))
