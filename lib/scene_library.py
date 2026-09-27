"""A local library of AI-generated scenes, in SQLite.

LOCAL-ONLY BY DESIGN. /ai-agent only generates where provider keys exist,
which is a developer's machine, never the public site — so the library is
enabled on exactly the same condition (the page passes `ANY_KEY`). On the
deployed site the Save button stays disabled and nothing is ever written.

Each row keeps the elements IN DRAW ORDER (the order the stream delivered
them), which is what lets the page's timeline replay a saved scene shape by
shape, and every setting that produced it (provider, model, effort, budget,
seed, prompt), so a scene can be regenerated or compared later.

    AI_SCENES_DB=/path/to/file.sqlite   # default: <repo>/data/ai_scenes.sqlite
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scenes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created     TEXT    NOT NULL,
    title       TEXT    NOT NULL DEFAULT '',
    prompt      TEXT    NOT NULL DEFAULT '',
    provider    TEXT,
    model       TEXT,
    effort      TEXT,
    max_tokens  INTEGER,
    seed        INTEGER,
    n_elements  INTEGER NOT NULL,
    elements    TEXT    NOT NULL
)
"""


def db_path() -> Path:
    return Path(os.environ.get("AI_SCENES_DB") or (REPO / "data" / "ai_scenes.sqlite"))


def _conn() -> sqlite3.Connection:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p)
    c.row_factory = sqlite3.Row
    c.execute(_SCHEMA)
    return c


def _title(prompt: str) -> str:
    words = " ".join((prompt or "").split())
    return (words[:48] + "…") if len(words) > 48 else (words or "untitled")


def save(elements: list, *, prompt: str = "", provider: str | None = None, model: str | None = None,
         effort: str | None = None, max_tokens: int | None = None, seed: int | None = None) -> int:
    if not elements:
        raise ValueError("nothing to save — the scene has no elements")
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO scenes (created, title, prompt, provider, model, effort, max_tokens, seed,"
            " n_elements, elements) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (time.strftime("%Y-%m-%d %H:%M:%S"), _title(prompt), prompt or "", provider, model, effort,
             int(max_tokens) if max_tokens else None, int(seed) if seed else None,
             len(elements), json.dumps(elements)),
        )
        return int(cur.lastrowid)


def options(limit: int = 100) -> list[dict]:
    """Newest first, shaped for a dmc.Select."""
    with _conn() as c:
        rows = c.execute("SELECT id, created, title, n_elements, model FROM scenes ORDER BY id DESC LIMIT ?",
                         (limit,)).fetchall()
    return [{"value": str(r["id"]),
             "label": f"#{r['id']} · {r['title']} · {r['n_elements']} el · {r['created'][5:16]}"}
            for r in rows]


def get(scene_id) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM scenes WHERE id = ?", (int(scene_id),)).fetchone()
    if not r:
        return None
    out = dict(r)
    out["elements"] = json.loads(out["elements"])
    return out
