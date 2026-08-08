"""Flask-SocketIO handlers + helpers for the /ai-colab demo.

`dash-socketio` 1.1.1 doesn't expose a client-side `send` prop — all
outgoing messages go through server-side code. The page module reacts
to `connected=True` via a Dash callback and calls `handle_join(...)`
below, which does the actual room bookkeeping + emits. The in-browser
`DashSocketIO` component is a pure listener.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, Optional

from flask_socketio import SocketIO

from pages._colab_state import (
    AI_COLOR,
    AI_DISPLAY_NAME,
    AI_USER_ID,
    ROOM,
    ROOM_NAME,
    User,
    pick_random_name,
)


# Populated by `register_socketio_handlers()` so `handle_join` can emit.
_socketio: Optional[SocketIO] = None

# Per-user throttles for high-frequency broadcasts. `_broadcast_lock`
# guards both dicts because Dash callbacks from multiple requests can
# land concurrently on the threaded server.
_CURSOR_THROTTLE_MS = 80
_SCENE_THROTTLE_MS = 400
_broadcast_lock = threading.Lock()
_last_cursor_broadcast: Dict[str, float] = {}
_last_scene_broadcast: Dict[str, float] = {}


def register_socketio_handlers(socketio: SocketIO) -> None:
    """Call once from app.py after SocketIO instantiation."""
    global _socketio
    _socketio = socketio

    # Spin up the Claude-bot background thread. Safe-to-call-multiple-times;
    # only the first invocation creates + starts the thread.
    from pages._colab_ai import start_agent

    start_agent(socketio)

    @socketio.on("disconnect", namespace="/")
    def _on_disconnect() -> None:
        from flask import request

        victim = ROOM.remove_by_socket(request.sid)  # type: ignore[attr-defined]
        if victim is None:
            return
        # Remove the AI too if the room is now empty of humans.
        if not ROOM.humans():
            ROOM.remove_user(AI_USER_ID)
        _broadcast_presence()
        socketio.emit(
            "colab_left",
            {"userId": victim.user_id, "name": victim.name},
            to=ROOM_NAME,
            namespace="/",
        )


# ---------------------------------------------------------------------------
# Public API used by pages/ai_colab.py Dash callbacks.
# ---------------------------------------------------------------------------


def handle_join(socket_id: str, identity_hint: Optional[Dict[str, Any]]) -> None:
    """Put `socket_id` into the room and welcome it.

    Idempotent — if the same socket_id is already in the room we just
    re-emit the welcome (useful after a quick reconnect).
    """
    if _socketio is None:
        return

    hint = identity_hint or {}
    existing = next(
        (u for u in ROOM.all_users() if u.socket_id == socket_id),
        None,
    )

    if existing is None:
        user_id = hint.get("userId") or f"user-{uuid.uuid4().hex[:8]}"
        name = hint.get("name") or pick_random_name()
        color = hint.get("color") or ROOM.next_color()
        user = User(
            user_id=user_id,
            name=name,
            color=color,
            socket_id=socket_id,
        )
        ROOM.add_user(user)
    else:
        user = existing

    # Ensure the AI is always present while any human is in the room.
    _ensure_ai_present()

    # Join the SocketIO room so broadcasts reach this socket. Done from
    # outside a socket event handler → use the raw `.server.enter_room`.
    _socketio.server.enter_room(socket_id, ROOM_NAME, namespace="/")

    # Welcome this socket personally with the resolved identity + current state.
    _socketio.emit(
        "colab_welcome",
        {
            "userId": user.user_id,
            "name": user.name,
            "color": user.color,
            "scene": ROOM.get_scene(),
            "presence": ROOM.presence_snapshot(),
            "aiUserId": AI_USER_ID,
        },
        to=socket_id,
        namespace="/",
    )

    # Tell the rest of the room someone showed up.
    _broadcast_presence()
    _socketio.emit(
        "colab_joined",
        {"userId": user.user_id, "name": user.name, "color": user.color},
        to=ROOM_NAME,
        namespace="/",
    )

    # Catch the newcomer up on Claude-bot's current state: replay the
    # most recent intent (if any) and nudge the agent to run a fresh
    # tick now so the bot doesn't look frozen while the newcomer waits.
    from pages._colab_ai import get_agent

    agent = get_agent()
    if agent is not None:
        last_intent = agent.last_intent()
        if last_intent is not None:
            _socketio.emit(
                "ai_intent",
                last_intent,
                to=socket_id,
                namespace="/",
            )
        # Regardless of whether an intent existed, nudge the loop so the
        # bot acknowledges the new arrival within ~1 tick instead of 4.
        agent.poke()


def handle_cursor(
    user_id: str,
    x: float,
    y: float,
    button: Optional[str] = None,
    tool: Optional[str] = None,
) -> None:
    """Broadcast a user's cursor to the room (throttled per user).

    Called from the Dash callback bound to `lastPointerMove` on the
    client canvas. The TSX-level `pointerMoveThrottleMs` already caps
    emits at ~50 ms per user; the server-side throttle here just
    guarantees the fan-out stays capped even if that ever slips.
    """
    if _socketio is None:
        return
    now_ms = time.time() * 1000.0
    with _broadcast_lock:
        last = _last_cursor_broadcast.get(user_id, 0.0)
        if now_ms - last < _CURSOR_THROTTLE_MS:
            return
        _last_cursor_broadcast[user_id] = now_ms
    ROOM.touch(user_id, cursor={"x": float(x), "y": float(y)})
    _socketio.emit(
        "colab_cursor",
        {
            "userId": user_id,
            "x": float(x),
            "y": float(y),
            "button": button,
            "tool": tool,
        },
        to=ROOM_NAME,
        namespace="/",
    )


def handle_scene(user_id: str, serialized: str) -> None:
    """Broadcast a user's serialized scene to the room (throttled)."""
    if _socketio is None:
        return
    if not serialized:
        return
    now_ms = time.time() * 1000.0
    with _broadcast_lock:
        last = _last_scene_broadcast.get(user_id, 0.0)
        if now_ms - last < _SCENE_THROTTLE_MS:
            return
        _last_scene_broadcast[user_id] = now_ms
    ROOM.set_scene(serialized)
    ROOM.touch(user_id)
    _socketio.emit(
        "colab_scene",
        {"userId": user_id, "serializedData": serialized},
        to=ROOM_NAME,
        namespace="/",
    )
    # Feed the scene to Claude-bot's rule engine. It'll dedupe echoes from
    # its own recent actions and respect per-rule cooldowns.
    from pages._colab_ai import get_agent

    agent = get_agent()
    if agent is not None:
        agent.observe_scene(serialized)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _broadcast_presence() -> None:
    if _socketio is None:
        return
    _socketio.emit(
        "colab_presence",
        {"presence": ROOM.presence_snapshot()},
        to=ROOM_NAME,
        namespace="/",
    )


def _ensure_ai_present() -> None:
    if ROOM.get(AI_USER_ID) is not None:
        return
    ROOM.add_user(
        User(
            user_id=AI_USER_ID,
            name=AI_DISPLAY_NAME,
            color=AI_COLOR,
            socket_id=None,
            is_ai=True,
        )
    )