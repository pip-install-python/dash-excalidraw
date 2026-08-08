"""The Claude-bot AI agent for /ai-colab.

Server-side background thread that:
  - Every `_TICK_SECS`, picks a human to follow / observe and emits an
    `ai_intent` event. Client renders it as a collaborator cursor with
    smooth motion via Excalidraw's own interpolation.
  - On every scene change (observed through `observe_scene`), runs a
    small event-rule engine and emits an `ai_action` event when a
    rule fires. Per-rule cooldowns + a global action lockout keep the
    bot from spamming.

Scope guardrails for the demo:
  - One rule active by default: misalignment detection (cheap, no API).
  - Orphan / overlap / typography / color rules are scaffolded but
    disabled behind a feature flag — enable by flipping `ENABLED_RULES`.
  - No Claude/Gemini calls in Phase 3. Phase 4 will add the
    model-assisted tidies behind the `colors` and `typography` rules.
"""

from __future__ import annotations

import json
import math
import random
import threading
import time
from typing import Any, Dict, List, Optional

from flask_socketio import SocketIO

from pages._colab_state import (
    AI_COLOR,
    AI_DISPLAY_NAME,
    AI_USER_ID,
    ROOM,
    ROOM_NAME,
)

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------

_TICK_SECS = 4.0
_ACTION_LOCKOUT_S = 4.0  # no two AI actions within this window
_ECHO_WINDOW_S = 2.5  # ignore scenes that echo back right after an AI action

# Per-rule cooldowns (seconds). Lower = more active buddy, higher = more chill.
_RULE_COOLDOWN = {
    "misalignment": 120.0,
    # Additional rules are scaffolded but disabled for Phase 3. Enable them
    # by adding to ENABLED_RULES and implementing the corresponding check.
    "overlap": 90.0,
    "typography": 180.0,
    "colors": 180.0,
    "orphan": 300.0,
}

ENABLED_RULES = {"misalignment"}

# Grid snap size for the misalignment rule.
_GRID = 20

# Safe-distance (scene px) the buddy keeps from the user it's following.
# Tuned up from the original 110 so the cursor doesn't block the user's
# active editing area.
_FOLLOW_DISTANCE_MIN = 210
_FOLLOW_DISTANCE_MAX = 270


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class AIAgent:
    def __init__(self, socketio: SocketIO) -> None:
        self.socketio = socketio
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Action-cadence gates
        self._last_action_ts = 0.0
        self._rule_last_fired: Dict[str, float] = {}
        # Fingerprint of the last scene WE emitted so we don't react to
        # our own echo. Plain string comparison — scenes are big JSON
        # blobs and exact byte-equality is effectively a free dedupe.
        self._last_emitted_scene: Optional[str] = None

        # Action log exposed for the sidebar (bounded ring buffer).
        self._action_log: List[Dict[str, Any]] = []
        self._action_log_max = 24

        # Cache the last emitted intent so late-joining browsers can be
        # welcomed with the bot's current state instead of sitting blank
        # for up to `_TICK_SECS` seconds.
        self._last_intent: Optional[Dict[str, Any]] = None
        # Event used to kick off an immediate tick when a new human joins.
        self._kick_event = threading.Event()

    # ---- lifecycle ----

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(
                target=self._loop,
                name="ai-colab-agent",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False

    # ---- background loop ----

    def _loop(self) -> None:
        while True:
            with self._lock:
                if not self._running:
                    return
            try:
                self._tick()
            except Exception as exc:  # noqa: BLE001 - never kill the loop
                # Keep the loop alive even if one tick throws.
                print(f"[ai-colab] tick error: {exc}")
            # Wait up to _TICK_SECS, but wake early if poke() is called.
            woken = self._kick_event.wait(timeout=_TICK_SECS)
            if woken:
                self._kick_event.clear()

    def poke(self) -> None:
        """Ask the loop to run a tick immediately (e.g. on user join)."""
        self._kick_event.set()

    def _tick(self) -> None:
        humans = ROOM.humans()
        if not humans:
            return

        # Toned-down distribution per user feedback: fewer follow ticks,
        # more object-orbit + rest so the cursor stays out of the editing
        # area most of the time.
        #   20% follow a human (with a wide safe distance)
        #   35% orbit a random scene element (the "examining" behavior)
        #   20% observe near a user's last cursor (one beat, then moves on)
        #   25% rest at a corner
        roll = random.random()
        if roll < 0.20:
            self._intent_follow(humans)
        elif roll < 0.55:
            self._intent_orbit_element()
        elif roll < 0.75:
            self._intent_observe(humans)
        else:
            self._intent_rest()

    # ---- intent emission ----

    def _intent_follow(self, humans: list) -> None:
        target = random.choice(humans)
        self._emit_intent(
            {
                "type": "follow",
                "targetUserId": target.user_id,
                "safeDistance": random.uniform(
                    _FOLLOW_DISTANCE_MIN, _FOLLOW_DISTANCE_MAX
                ),
            }
        )

    def _intent_observe(self, humans: list) -> None:
        target = random.choice(humans)
        cursor = target.cursor
        if not cursor:
            # Fall back to resting if we don't know where they are yet —
            # observing an unknown point is worse than sitting still.
            self._intent_rest()
            return
        # Offset well clear of the actual cursor so the bot isn't
        # hovering over the user's pointer.
        offset_radius = 140 + random.uniform(0, 80)
        angle = random.uniform(0, 2 * math.pi)
        self._emit_intent(
            {
                "type": "observe",
                "x": cursor["x"] + math.cos(angle) * offset_radius,
                "y": cursor["y"] + math.sin(angle) * offset_radius,
                "dwellMs": 1500 + random.randint(0, 1500),
            }
        )

    def _intent_orbit_element(self) -> None:
        """Park near a random existing scene element — an "examining" pose.

        Keeps the bot engaged with actual content (not hovering over
        the user's active cursor) and naturally moves it around the
        canvas as the scene changes.
        """
        scene_str = ROOM.get_scene()
        if not scene_str:
            self._intent_rest()
            return
        try:
            scene = json.loads(scene_str)
        except (TypeError, ValueError):
            self._intent_rest()
            return
        elements = [
            el
            for el in (scene.get("elements") or [])
            if isinstance(el, dict) and not el.get("isDeleted")
        ]
        if not elements:
            self._intent_rest()
            return
        target_el = random.choice(elements)
        cx = float(target_el.get("x", 0)) + float(target_el.get("width", 100)) / 2
        cy = float(target_el.get("y", 0)) + float(target_el.get("height", 50)) / 2
        # Offset outside the element's bounding box in a random direction.
        angle = random.uniform(0, 2 * math.pi)
        half_diag = math.hypot(
            float(target_el.get("width", 100)) / 2,
            float(target_el.get("height", 50)) / 2,
        )
        offset = half_diag + 60 + random.uniform(0, 40)
        self._emit_intent(
            {
                "type": "observe",
                "x": cx + math.cos(angle) * offset,
                "y": cy + math.sin(angle) * offset,
                "dwellMs": 2500 + random.randint(0, 1500),
                # Metadata so the client can label the bot's state nicely.
                "hint": "orbiting-element",
            }
        )

    def _intent_rest(self) -> None:
        # Drift to a corner; clients add micro-jitter for personality.
        self._emit_intent(
            {
                "type": "rest",
                "x": random.choice([80, 920]),
                "y": random.choice([80, 520]),
            }
        )

    def _emit_intent(self, intent: Dict[str, Any]) -> None:
        self._last_intent = intent
        self.socketio.emit(
            "ai_intent",
            intent,
            to=ROOM_NAME,
            namespace="/",
        )

    # Public getter for `handle_join` so late arrivals can be caught up.
    def last_intent(self) -> Optional[Dict[str, Any]]:
        return self._last_intent

    # ---- scene observation → rule engine ----

    def observe_scene(self, serialized: str) -> None:
        """Called by `handle_scene` for every broadcast from any human."""
        if not serialized:
            return
        # Skip our own echo — if we just emitted a scene, the clients'
        # next scene_change is the same bytes coming back.
        if serialized == self._last_emitted_scene:
            return
        if time.time() - self._last_action_ts < _ECHO_WINDOW_S:
            return

        try:
            scene = json.loads(serialized)
        except (TypeError, ValueError):
            return
        elements = scene.get("elements") or []
        if not elements:
            return

        for rule in ENABLED_RULES:
            if rule == "misalignment":
                self._try_misalignment(scene, elements)

    def _try_misalignment(self, scene: dict, elements: list) -> None:
        if not self._rule_ready("misalignment"):
            return
        if not self._action_ready():
            return
        if len(elements) < 5:
            return
        aligned = sum(
            1
            for el in elements
            if isinstance(el, dict)
            and _is_on_grid(el.get("x"), _GRID)
            and _is_on_grid(el.get("y"), _GRID)
        )
        if aligned / max(1, len(elements)) >= 0.5:
            return  # already tidy enough

        # Snap every element to the grid.
        new_elements = [_snap_to_grid(el, _GRID) for el in elements]
        self._emit_tidy(scene, new_elements, message="✨ aligned to grid")
        self._rule_last_fired["misalignment"] = time.time()

    # ---- action emission ----

    def _emit_tidy(
        self,
        scene: dict,
        new_elements: list,
        message: str,
    ) -> None:
        self._last_action_ts = time.time()
        # Broadcast a new scene as if the AI were a collaborator.
        new_scene = {
            **scene,
            "elements": new_elements,
            "source": "ai-colab-bot",
        }
        serialized = json.dumps(new_scene)
        self._last_emitted_scene = serialized
        ROOM.set_scene(serialized)
        self.socketio.emit(
            "colab_scene",
            {"userId": AI_USER_ID, "serializedData": serialized},
            to=ROOM_NAME,
            namespace="/",
        )
        # Announce it in the action log.
        action = {
            "type": "tidy",
            "message": message,
            "timestamp": time.time(),
            "elementCount": len(new_elements),
        }
        self._push_action(action)
        self.socketio.emit(
            "ai_action",
            action,
            to=ROOM_NAME,
            namespace="/",
        )

    def _push_action(self, action: Dict[str, Any]) -> None:
        with self._lock:
            self._action_log.append(action)
            if len(self._action_log) > self._action_log_max:
                self._action_log.pop(0)

    # ---- gates ----

    def _action_ready(self) -> bool:
        return (time.time() - self._last_action_ts) >= _ACTION_LOCKOUT_S

    def _rule_ready(self, rule: str) -> bool:
        cooldown = _RULE_COOLDOWN.get(rule, 60.0)
        last = self._rule_last_fired.get(rule, 0.0)
        return (time.time() - last) >= cooldown

    def snapshot_log(self) -> list:
        """Read-only snapshot of the action log for diagnostics."""
        with self._lock:
            return list(self._action_log)

    def force_tidy(self) -> Dict[str, Any]:
        """Manual-trigger tidy: clears cooldowns and runs every enabled rule.

        Unlike `observe_scene`, this does not skip early when alignment is
        already acceptable — the user pressed the button expecting something
        to happen. We still do the actual snap-to-grid work (which may be
        a no-op visually if elements are already on the grid), and we emit
        the action so the sidebar log shows a confirmation either way.
        """
        scene_str = ROOM.get_scene()
        if not scene_str:
            return {"ok": False, "reason": "no scene"}
        try:
            scene = json.loads(scene_str)
        except (TypeError, ValueError):
            return {"ok": False, "reason": "bad scene json"}
        elements = scene.get("elements") or []
        if not elements:
            return {"ok": False, "reason": "empty canvas"}

        # Clear cooldowns so the rule runs unconditionally.
        self._rule_last_fired = {}
        self._last_action_ts = 0.0

        new_elements = [_snap_to_grid(el, _GRID) for el in elements]
        # How many moved? Cosmetic counter for the log message.
        moved = sum(
            1
            for before, after in zip(elements, new_elements)
            if (before.get("x"), before.get("y")) != (after.get("x"), after.get("y"))
        )
        message = (
            f"✨ tidied on request ({moved} moved)"
            if moved
            else "✨ canvas already tidy"
        )
        self._emit_tidy(scene, new_elements, message=message)
        return {"ok": True, "moved": moved}


# ---------------------------------------------------------------------------
# Pure helpers (used by rules — also fine to unit-test directly).
# ---------------------------------------------------------------------------


def _is_on_grid(value: Any, grid: int) -> bool:
    if value is None:
        return False
    try:
        return abs(float(value) - round(float(value) / grid) * grid) < 0.5
    except (TypeError, ValueError):
        return False


def _snap_to_grid(el: dict, grid: int) -> dict:
    if not isinstance(el, dict):
        return el
    new = dict(el)
    for key in ("x", "y"):
        v = el.get(key)
        if v is not None:
            try:
                new[key] = round(float(v) / grid) * grid
            except (TypeError, ValueError):
                pass
    return new


# ---------------------------------------------------------------------------
# Module-level singleton wiring.
# ---------------------------------------------------------------------------

_agent: Optional[AIAgent] = None


def start_agent(socketio: SocketIO) -> AIAgent:
    global _agent
    if _agent is None:
        _agent = AIAgent(socketio)
    _agent.start()
    return _agent


def get_agent() -> Optional[AIAgent]:
    return _agent