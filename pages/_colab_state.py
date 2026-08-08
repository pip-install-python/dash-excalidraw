"""In-memory state for the /ai-colab demo.

Single room, single worker. Production hardening (Redis pub/sub for
multi-worker, per-room isolation, auth) is noted in the page's docs but
deliberately out of scope for the demo — keeping the state loop inspectable
is worth more than scalability here.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional


# 6-slot palette used across the app. Indigo is reserved for the AI
# agent so human cursors cycle through the other five.
HUMAN_COLORS = ["#0ca678", "#e67700", "#e64980", "#ae3ec9", "#495057"]
AI_COLOR = "#4c6ef5"
AI_USER_ID = "claude-bot"
AI_DISPLAY_NAME = "Claude-bot"

ROOM_NAME = "ai-colab-main"


@dataclass
class User:
    user_id: str
    name: str
    color: str
    socket_id: Optional[str] = None  # None for the AI (no socket)
    is_ai: bool = False
    joined_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    # Most recent cursor in scene coordinates (what Excalidraw uses for
    # `appState.collaborators[*].pointer`). Absent until the user moves.
    cursor: Optional[Dict[str, float]] = None


class RoomState:
    """Thread-safe membership + scene state for the single demo room."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._users: Dict[str, User] = {}
        # serializedData string last broadcast by a user; server is the
        # source of truth for late joiners.
        self._scene: Optional[str] = None

    # ---- membership ----
    def add_user(self, user: User) -> None:
        with self._lock:
            self._users[user.user_id] = user

    def remove_by_socket(self, socket_id: str) -> Optional[User]:
        with self._lock:
            victim = next(
                (u for u in self._users.values() if u.socket_id == socket_id),
                None,
            )
            if victim is not None:
                self._users.pop(victim.user_id, None)
            return victim

    def remove_user(self, user_id: str) -> Optional[User]:
        with self._lock:
            return self._users.pop(user_id, None)

    def touch(self, user_id: str, cursor: Optional[Dict[str, float]] = None) -> None:
        with self._lock:
            u = self._users.get(user_id)
            if u is None:
                return
            u.last_seen = time.time()
            if cursor is not None:
                u.cursor = cursor

    def humans(self) -> list[User]:
        with self._lock:
            return [u for u in self._users.values() if not u.is_ai]

    def all_users(self) -> list[User]:
        with self._lock:
            return list(self._users.values())

    def get(self, user_id: str) -> Optional[User]:
        with self._lock:
            return self._users.get(user_id)

    def next_color(self) -> str:
        with self._lock:
            used = {u.color for u in self._users.values() if not u.is_ai}
            for c in HUMAN_COLORS:
                if c not in used:
                    return c
            return HUMAN_COLORS[len(used) % len(HUMAN_COLORS)]

    # ---- scene ----
    def set_scene(self, serialized: str) -> None:
        with self._lock:
            self._scene = serialized

    def get_scene(self) -> Optional[str]:
        with self._lock:
            return self._scene

    def presence_snapshot(self) -> list[dict]:
        """Light-weight view safe to send over the wire."""
        with self._lock:
            return [
                {
                    "userId": u.user_id,
                    "name": u.name,
                    "color": u.color,
                    "isAi": u.is_ai,
                    "joinedAt": u.joined_at,
                    "cursor": u.cursor,
                }
                for u in self._users.values()
            ]


# Module-level singleton — good enough for a single-process demo.
ROOM = RoomState()


def pick_random_name() -> str:
    """Generate a memorable two-word label like 'Teal Otter'."""
    import random

    adj = [
        "Teal",
        "Amber",
        "Rose",
        "Mint",
        "Slate",
        "Coral",
        "Indigo",
        "Olive",
        "Maple",
        "Jade",
    ]
    animals = [
        "Otter",
        "Fox",
        "Heron",
        "Hare",
        "Finch",
        "Sparrow",
        "Marten",
        "Newt",
        "Koi",
        "Kestrel",
    ]
    return f"{random.choice(adj)} {random.choice(animals)}"