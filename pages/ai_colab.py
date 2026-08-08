"""/ai-colab — multiplayer canvas with a resident AI buddy.

Phase 1 (this file): SocketIO plumbing + presence. Open two tabs and
they see each other join / leave. No cursor sync, no AI behavior yet —
those arrive in Phase 2+.

Architecture recap (see PLAN notes in chat for detail):
- `dash-socketio` 1.1.1 is a listen-only client component: `connected`,
  `socketId`, `data-<eventName>` props. All client → server messages go
  through Dash callbacks that emit from Python.
- Single shared room. Server-authoritative presence list. AI is just an
  entry in that list, pinned while any human is connected.
"""

from __future__ import annotations

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, clientside_callback, dcc, html, no_update

from dash_excalidraw import DashExcalidraw
from pages._shared import canvas_frame, page_header, sync_canvas_theme

try:
    from dash_socketio import DashSocketIO

    from pages._colab_ai import get_agent
    from pages._colab_server import handle_cursor, handle_join, handle_scene

    _HAS_DASH_SOCKETIO = True
except ImportError:  # pragma: no cover
    DashSocketIO = None  # type: ignore[assignment]
    handle_join = None  # type: ignore[assignment]
    handle_cursor = None  # type: ignore[assignment]
    handle_scene = None  # type: ignore[assignment]
    get_agent = None  # type: ignore[assignment]
    _HAS_DASH_SOCKETIO = False

dash.register_page(
    __name__,
    path="/ai-colab",
    name="AI collab",
    description="Multiplayer canvas + persistent AI buddy (Phase 3: Claude-bot is live)",
    order=14,
)

AI_USER_ID = "claude-bot"
AI_COLOR = "#4c6ef5"

sync_canvas_theme("colab-canvas")


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def _install_banner() -> dmc.Alert:
    return dmc.Alert(
        color="red",
        variant="light",
        title="dash-socketio is not installed",
        children=dmc.Stack(
            gap="xs",
            children=[
                dmc.Text(
                    "This page needs the optional [colab] extra. Install with:",
                    size="sm",
                ),
                dmc.Code(
                    "pip install -e '.[colab]'",
                    block=True,
                ),
                dmc.Text(
                    "Then restart `python app.py` — the server will pick up "
                    "the socketio handlers on boot.",
                    size="xs",
                    c="dimmed",
                ),
            ],
        ),
    )


layout = dmc.Stack(
    gap="md",
    children=[
        page_header(
            "AI collab (Phase 3)",
            "Multiplayer canvas with a resident AI buddy. Claude-bot cycles "
            "between following a human, observing the cursor's last spot, "
            "and resting — it also runs an event-rule engine against every "
            "scene change, and tidies the canvas when the alignment rule "
            "fires. Draw a few ungridded shapes and watch it snap them into "
            "place (rule cooldown: 2 min).",
        ),
        dmc.Alert(
            color="blue",
            variant="light",
            title="What Claude-bot does",
            children=dmc.List(
                size="sm",
                children=[
                    dmc.ListItem(
                        "Every ~4 s it picks a new high-level `ai_intent` — "
                        "follow / observe / rest. The cursor animates to the "
                        "new target via Excalidraw's own collaborator rendering."
                    ),
                    dmc.ListItem(
                        "Watches every scene change through a small rule "
                        "engine (misalignment active by default; overlap, "
                        "typography, colors, orphan scaffolded + disabled)."
                    ),
                    dmc.ListItem(
                        "When a rule fires, emits an `ai_action` and "
                        "broadcasts a corrected scene — global 4 s lockout "
                        "prevents the bot from talking over itself."
                    ),
                    dmc.ListItem(
                        "Fully local rule evaluation this round — no Claude "
                        "/ Gemini calls yet. Phase 4 opens up the model-"
                        "assisted tidies behind the typography and colors "
                        "rules."
                    ),
                ],
            ),
        ),
        *([] if _HAS_DASH_SOCKETIO else [_install_banner()]),
        # Client-local identity store (persisted across tab reloads via
        # sessionStorage). Hydrated by the clientside callback below.
        dcc.Store(id="colab-identity", storage_type="session"),
        # Authoritative presence list as broadcast by the server.
        dcc.Store(id="colab-presence", data=[]),
        # Latest server-held scene snapshot; used by late joiners.
        dcc.Store(id="colab-server-scene"),
        # Map of peer cursors, keyed by userId. Fed by incoming
        # colab_cursor events; drives the collaborators-Map dispatch.
        dcc.Store(id="colab-peers-cursors", data={}),
        # Latest `ai_intent` from the server. Drives the AI buddy's
        # rendered position; swaps out every few seconds.
        dcc.Store(id="colab-ai-intent"),
        # Bounded log of AI actions shown in the sidebar panel.
        dcc.Store(id="colab-ai-actions", data=[]),
        # "Ready to broadcast" flag. Flips True once `colab_welcome` has
        # landed, suppressing mount-time empty-scene broadcasts that
        # would otherwise wipe every peer's canvas on page refresh.
        dcc.Store(id="colab-ready", data=False),
        # Pointer-is-down flag. Set True on `lastPointerDown`, False on
        # `lastPointerUp`. Used to suppress:
        #   - outgoing cursor broadcasts (~20 Hz during drag overloads Werkzeug)
        #   - collaborator-map `updateScene` dispatches (clobbers Excalidraw's
        #     draft-element state and forces the drag to commit early)
        #   - incoming peer scene `updateScene` dispatches (same reason; we
        #     queue the latest and apply it on pointer-up)
        dcc.Store(id="colab-pointer-down", data=False),
        # Dedicated sink stores for each side-effect callback. Sharing a
        # single `colab-noop` across multiple callbacks mixed with and
        # without `allow_duplicate=True` was tripping Dash's callback-
        # graph dispatcher after hot-reload and producing the
        # `IndexError: list index out of range` 500s. Giving each
        # side-effect its own output is explicit + reload-stable.
        dcc.Store(id="colab-noop-join"),
        dcc.Store(id="colab-noop-cursor"),
        dcc.Store(id="colab-noop-scene"),
        dcc.Store(id="colab-noop-tidy"),
        *(
            [
                DashSocketIO(
                    id="colab-socket",
                    eventNames=[
                        "colab_welcome",
                        "colab_presence",
                        "colab_joined",
                        "colab_left",
                        "colab_cursor",
                        "colab_scene",
                        "ai_intent",
                        "ai_action",
                    ],
                )
            ]
            if _HAS_DASH_SOCKETIO
            else []
        ),
        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(
                    span={"base": 12, "md": 8},
                    children=canvas_frame(
                        DashExcalidraw(
                            id="colab-canvas",
                            height="640px",
                            isCollaborating=True,
                        ),
                        min_height=640,
                    ),
                ),
                dmc.GridCol(
                    span={"base": 12, "md": 4},
                    children=dmc.Stack(
                        gap="md",
                        children=[
                            dmc.Paper(
                                withBorder=True,
                                p="md",
                                children=dmc.Stack(
                                    gap="xs",
                                    children=[
                                        dmc.Group(
                                            justify="space-between",
                                            children=[
                                                dmc.Text("You", fw=600, size="sm"),
                                                dmc.Badge(
                                                    id="colab-conn-badge",
                                                    children="connecting…",
                                                    color="gray",
                                                    variant="light",
                                                    size="sm",
                                                ),
                                            ],
                                        ),
                                        html.Div(id="colab-self-row"),
                                    ],
                                ),
                            ),
                            dmc.Paper(
                                withBorder=True,
                                p="md",
                                children=dmc.Stack(
                                    gap="xs",
                                    children=[
                                        dmc.Group(
                                            justify="space-between",
                                            children=[
                                                dmc.Text("Room", fw=600, size="sm"),
                                                dmc.Badge(
                                                    id="colab-roster-count",
                                                    children="0 connected",
                                                    variant="light",
                                                    color="gray",
                                                    size="sm",
                                                ),
                                            ],
                                        ),
                                        html.Div(id="colab-roster"),
                                    ],
                                ),
                            ),
                            dmc.Paper(
                                withBorder=True,
                                p="md",
                                children=dmc.Stack(
                                    gap="xs",
                                    children=[
                                        dmc.Group(
                                            justify="space-between",
                                            children=[
                                                dmc.Text(
                                                    "Claude-bot",
                                                    fw=600,
                                                    size="sm",
                                                ),
                                                dmc.Badge(
                                                    id="colab-ai-state",
                                                    children="idle",
                                                    color="indigo",
                                                    variant="light",
                                                    size="sm",
                                                ),
                                            ],
                                        ),
                                        dmc.Text(
                                            id="colab-ai-target",
                                            children="(no target)",
                                            size="xs",
                                            c="dimmed",
                                        ),
                                        dmc.Button(
                                            "✨ Tidy canvas now",
                                            id="colab-tidy-btn",
                                            variant="light",
                                            color="indigo",
                                            size="compact-sm",
                                            fullWidth=True,
                                        ),
                                        dmc.Divider(my=4),
                                        dmc.Text(
                                            "Recent actions",
                                            size="xs",
                                            c="dimmed",
                                            fw=500,
                                        ),
                                        html.Div(
                                            id="colab-ai-action-log",
                                            style={"maxHeight": 180, "overflowY": "auto"},
                                        ),
                                    ],
                                ),
                            ),
                            dmc.Paper(
                                withBorder=True,
                                p="md",
                                children=dmc.Stack(
                                    gap="xs",
                                    children=[
                                        dmc.Text("Invite", fw=600, size="sm"),
                                        dmc.Text(
                                            "Share this URL — or just open the "
                                            "same page in another browser tab — "
                                            "and watch the roster update live.",
                                            size="xs",
                                            c="dimmed",
                                        ),
                                    ],
                                ),
                            ),
                        ],
                    ),
                ),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

if _HAS_DASH_SOCKETIO:
    # Step 1 (clientside): ensure we have a stable userId before the join
    # callback fires. Runs once per socket-connect transition.
    clientside_callback(
        """
        function(connected, stored) {
            if (!connected) return window.dash_clientside.no_update;
            if (stored && stored.userId) return stored;
            return {
                userId: 'user-' + (crypto?.randomUUID?.()?.slice(0, 8) ||
                                    Math.random().toString(36).slice(2, 10)),
            };
        }
        """,
        Output("colab-identity", "data"),
        Input("colab-socket", "connected"),
        State("colab-identity", "data"),
    )

    # Step 2 (serverside): when socket connects AND we have identity,
    # tell the server to join us. The server emits `colab_welcome` back,
    # which flows through the clientside listener below.
    @callback(
        Output("colab-noop-join", "data"),
        Input("colab-socket", "connected"),
        Input("colab-identity", "data"),
        State("colab-socket", "socketId"),
        prevent_initial_call=True,
    )
    def _join_on_connect(connected, identity, socket_id):
        if not connected or not socket_id or not identity or not identity.get("userId"):
            return no_update
        handle_join(socket_id, identity)
        return no_update

    # Step 3 (clientside): server acks join with a welcome containing
    # resolved identity + presence + scene. Persist the identity so
    # reloads reuse it.
    clientside_callback(
        """
        function(welcome) {
            if (!welcome) return [window.dash_clientside.no_update,
                                   window.dash_clientside.no_update,
                                   window.dash_clientside.no_update];
            const identity = {
                userId: welcome.userId,
                name: welcome.name,
                color: welcome.color,
            };
            return [identity, welcome.presence || [], welcome.scene || null];
        }
        """,
        Output("colab-identity", "data", allow_duplicate=True),
        Output("colab-presence", "data", allow_duplicate=True),
        Output("colab-server-scene", "data"),
        Input("colab-socket", "data-colab_welcome"),
        prevent_initial_call=True,
    )

    # Ongoing presence broadcasts.
    clientside_callback(
        """
        function(payload) {
            if (!payload || !payload.presence) return window.dash_clientside.no_update;
            return payload.presence;
        }
        """,
        Output("colab-presence", "data", allow_duplicate=True),
        Input("colab-socket", "data-colab_presence"),
        prevent_initial_call=True,
    )

    # Roster panel render — self row + peer list + count badge.
    clientside_callback(
        """
        function(presence, identity) {
            if (!Array.isArray(presence)) presence = [];
            const selfId = identity?.userId;
            function makeRow(entry, isSelf) {
                const color = entry.color || '#adb5bd';
                const isAi = !!entry.isAi;
                return {
                    namespace: 'dash_mantine_components',
                    type: 'Group',
                    props: {
                        gap: 'sm',
                        wrap: 'nowrap',
                        children: [
                            {
                                namespace: 'dash_mantine_components',
                                type: 'Box',
                                props: {style: {
                                    width: 10, height: 10, borderRadius: '50%',
                                    background: color,
                                    boxShadow: '0 0 0 2px ' + color + '22',
                                    flexShrink: 0,
                                }},
                            },
                            {
                                namespace: 'dash_mantine_components',
                                type: 'Text',
                                props: {
                                    children: (entry.name || entry.userId || '…') +
                                              (isSelf ? ' (you)' : ''),
                                    size: 'sm',
                                    fw: isAi ? 600 : 500,
                                    style: {
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        whiteSpace: 'nowrap',
                                    },
                                },
                            },
                            {
                                namespace: 'dash_mantine_components',
                                type: 'Badge',
                                props: {
                                    children: isAi ? 'AI' : 'Human',
                                    size: 'xs',
                                    variant: 'light',
                                    color: isAi ? 'indigo' : 'gray',
                                },
                            },
                        ],
                    },
                };
            }
            const selfEntry = presence.find(p => p.userId === selfId);
            const others = presence.filter(p => p.userId !== selfId);
            others.sort((a, b) => (b.isAi ? 1 : 0) - (a.isAi ? 1 : 0));
            const selfRow = selfEntry
                ? makeRow(selfEntry, true)
                : {
                    namespace: 'dash_mantine_components',
                    type: 'Text',
                    props: {children: '(waiting for welcome…)',
                            size: 'sm', c: 'dimmed'},
                };
            const roster = {
                namespace: 'dash_mantine_components',
                type: 'Stack',
                props: {
                    gap: 'xs',
                    children: others.length
                        ? others.map(e => makeRow(e, false))
                        : [{
                            namespace: 'dash_mantine_components',
                            type: 'Text',
                            props: {
                                children: 'No peers yet — open this page in another tab.',
                                size: 'xs', c: 'dimmed',
                            },
                        }],
                },
            };
            const humans = presence.filter(p => !p.isAi).length;
            const hasAi = presence.some(p => p.isAi);
            const count = humans + ' connected' + (hasAi ? ' + AI' : '');
            return [selfRow, roster, count];
        }
        """,
        Output("colab-self-row", "children"),
        Output("colab-roster", "children"),
        Output("colab-roster-count", "children"),
        Input("colab-presence", "data"),
        Input("colab-identity", "data"),
    )

    # Connection badge.
    clientside_callback(
        """
        function(connected) {
            if (connected) return ['connected', 'green'];
            return ['connecting…', 'gray'];
        }
        """,
        Output("colab-conn-badge", "children"),
        Output("colab-conn-badge", "color"),
        Input("colab-socket", "connected"),
    )

    # -----------------------------------------------------------------
    # Phase 2 — cursor + scene sync
    # -----------------------------------------------------------------

    # Ready flag flips true as soon as colab_welcome arrives. Until then
    # the broadcast callbacks below no-op — this prevents Excalidraw's
    # mount-time empty-scene `onChange` from wiping the shared state
    # before hydration has applied the server's copy of the scene.
    clientside_callback(
        """
        function(welcome) {
            if (!welcome) return window.dash_clientside.no_update;
            return true;
        }
        """,
        Output("colab-ready", "data"),
        Input("colab-socket", "data-colab_welcome"),
    )

    # Pointer-is-down tracking. Drives the drag-safety gates below.
    clientside_callback(
        """
        function(down, up) {
            // Both inputs fire into the same callback. Whichever event
            // has the newer timestamp wins. This handles out-of-order
            // arrival on fast gestures.
            const dt = (down && down.timestamp) || 0;
            const ut = (up && up.timestamp) || 0;
            if (!dt && !ut) return window.dash_clientside.no_update;
            return dt > ut;
        }
        """,
        Output("colab-pointer-down", "data"),
        Input("colab-canvas", "lastPointerDown"),
        Input("colab-canvas", "lastPointerUp"),
    )

    # Outgoing cursor. Server-side so it can call socketio.emit(...).
    # Suppressed during local drag — at ~20 Hz Werkzeug's dev server
    # struggles to keep up AND peers don't really need every sub-gesture
    # sample from a mid-draw user.
    @callback(
        Output("colab-noop-cursor", "data"),
        Input("colab-canvas", "lastPointerMove"),
        State("colab-identity", "data"),
        State("colab-ready", "data"),
        State("colab-pointer-down", "data"),
        prevent_initial_call=True,
    )
    def _broadcast_cursor(move, identity, ready, pointer_down):
        if not ready or pointer_down:
            return no_update
        if not move or not identity or not identity.get("userId"):
            return no_update
        pointer = move.get("pointer") or {}
        x = pointer.get("x")
        y = pointer.get("y")
        if x is None or y is None:
            return no_update
        handle_cursor(
            identity["userId"],
            x,
            y,
            button=move.get("button"),
            tool=(move.get("activeTool") or {}).get("type")
            if isinstance(move.get("activeTool"), dict)
            else None,
        )
        return no_update

    # Outgoing scene. We use the full `serializedData` (not the
    # externalized one) so peers see images too — for a multiplayer
    # demo full fidelity beats minimal wire size.
    @callback(
        Output("colab-noop-scene", "data"),
        Input("colab-canvas", "serializedData"),
        State("colab-identity", "data"),
        State("colab-ready", "data"),
        prevent_initial_call=True,
    )
    def _broadcast_scene(serialized, identity, ready):
        # CRITICAL gate: don't broadcast anything until the server has
        # welcomed us. On refresh, Excalidraw fires an empty-scene
        # onChange at mount which, without this guard, races the welcome
        # flow and clobbers `ROOM.scene` before hydration can restore it.
        if not ready:
            return no_update
        if not serialized or not identity or not identity.get("userId"):
            return no_update
        handle_scene(identity["userId"], serialized)
        return no_update

    # Incoming cursor: merge into peers map.
    clientside_callback(
        """
        function(cursor, prev) {
            if (!cursor || !cursor.userId) return window.dash_clientside.no_update;
            const next = {...(prev || {})};
            next[cursor.userId] = {
                x: cursor.x,
                y: cursor.y,
                button: cursor.button || 'up',
                tool: cursor.tool || null,
                lastSeen: Date.now(),
            };
            return next;
        }
        """,
        Output("colab-peers-cursors", "data"),
        Input("colab-socket", "data-colab_cursor"),
        State("colab-peers-cursors", "data"),
    )

    # Peer left → drop their cursor from the map so Excalidraw stops
    # rendering a stale pin.
    clientside_callback(
        """
        function(left, prev) {
            if (!left || !left.userId || !prev) return window.dash_clientside.no_update;
            if (!(left.userId in prev)) return window.dash_clientside.no_update;
            const next = {...prev};
            delete next[left.userId];
            return next;
        }
        """,
        Output("colab-peers-cursors", "data", allow_duplicate=True),
        Input("colab-socket", "data-colab_left"),
        State("colab-peers-cursors", "data"),
        prevent_initial_call=True,
    )

    # Peers cursors + AI intent → command: updateScene with
    # appState.collaborators. We do NOT send `elements` or top-level
    # `files` here so this callback never stomps on user drawings. The
    # TSX dispatcher converts the plain-object collaborators to a Map.
    #
    # Claude-bot is synthesized from the latest `ai_intent`:
    #   - follow → stick to target's cursor + safeDistance offset
    #   - observe → park at the intent's (x, y) for dwellMs
    #   - rest → park at the intent's (x, y) plus a tiny time-based
    #            orbit so it doesn't look frozen
    #
    # Gated on pointer-down: dispatching `updateScene` mid-drag will
    # commit Excalidraw's draft element and close out the gesture,
    # which is exactly the "my square stops mid-drag" bug.
    clientside_callback(
        """
        function(cursors, presence, intent, identity, pointerDown) {
            if (pointerDown) return window.dash_clientside.no_update;
            if (!identity || !identity.userId) return window.dash_clientside.no_update;
            const AI_ID = 'claude-bot';
            const AI_COLOR = '#4c6ef5';
            const presMap = {};
            (presence || []).forEach(p => { presMap[p.userId] = p; });
            const collaborators = {};

            // Human peers.
            Object.entries(cursors || {}).forEach(([uid, c]) => {
                if (!c) return;
                if (uid === identity.userId) return;   // skip self
                if (uid === AI_ID) return;             // never render AI from peers map
                const p = presMap[uid];
                if (!p) return;
                collaborators[uid] = {
                    id: uid,
                    username: p.name || uid,
                    color: {background: p.color, stroke: p.color},
                    pointer: {x: c.x, y: c.y, tool: c.tool || 'pointer'},
                    button: c.button === 'down' ? 'down' : 'up',
                    userState: 'active',
                };
            });

            // Claude-bot.
            const hasHuman = (presence || []).some(p => !p.isAi && p.userId !== identity.userId);
            const humanPresent = (presence || []).some(p => !p.isAi);
            if (intent && humanPresent) {
                let x = 120, y = 120;
                if (intent.type === 'follow' && intent.targetUserId) {
                    const t = cursors && cursors[intent.targetUserId];
                    if (t) {
                        x = t.x + (intent.safeDistance || 110);
                        y = t.y - 20;
                    }
                } else if (intent.type === 'observe') {
                    x = intent.x ?? 120;
                    y = intent.y ?? 120;
                } else if (intent.type === 'rest') {
                    // Micro-orbit for personality.
                    const tt = Date.now() / 1000;
                    x = (intent.x ?? 120) + Math.sin(tt * 1.5) * 4;
                    y = (intent.y ?? 120) + Math.cos(tt * 1.5) * 4;
                }
                collaborators[AI_ID] = {
                    id: AI_ID,
                    username: '🤖 Claude-bot',
                    color: {background: AI_COLOR, stroke: AI_COLOR},
                    pointer: {x, y, tool: 'pointer'},
                    button: 'up',
                    userState: 'active',
                };
            }

            return {
                id: 'cursors-' + Date.now(),
                type: 'updateScene',
                payload: {appState: {collaborators}},
            };
        }
        """,
        Output("colab-canvas", "command"),
        Input("colab-peers-cursors", "data"),
        Input("colab-presence", "data"),
        Input("colab-ai-intent", "data"),
        State("colab-identity", "data"),
        State("colab-pointer-down", "data"),
    )

    # AI intent → store. Just captures the latest for the cursor callback
    # above; history isn't needed.
    clientside_callback(
        """
        function(intent) {
            if (!intent) return window.dash_clientside.no_update;
            return intent;
        }
        """,
        Output("colab-ai-intent", "data"),
        Input("colab-socket", "data-ai_intent"),
    )

    # AI action → prepend to bounded log, render the log list.
    clientside_callback(
        """
        function(action, prev) {
            if (!action) return window.dash_clientside.no_update;
            const next = [action, ...(prev || [])].slice(0, 20);
            return next;
        }
        """,
        Output("colab-ai-actions", "data"),
        Input("colab-socket", "data-ai_action"),
        State("colab-ai-actions", "data"),
    )

    # Render action log in the sidebar.
    clientside_callback(
        """
        function(actions) {
            actions = actions || [];
            if (!actions.length) {
                return {
                    namespace: 'dash_mantine_components',
                    type: 'Text',
                    props: {
                        children: '(no actions yet)',
                        size: 'xs',
                        c: 'dimmed',
                    },
                };
            }
            return {
                namespace: 'dash_mantine_components',
                type: 'Stack',
                props: {
                    gap: 4,
                    children: actions.map((a, i) => {
                        const ts = a.timestamp ? new Date(a.timestamp * 1000) : new Date();
                        const hh = String(ts.getHours()).padStart(2, '0');
                        const mm = String(ts.getMinutes()).padStart(2, '0');
                        const ss = String(ts.getSeconds()).padStart(2, '0');
                        return {
                            namespace: 'dash_mantine_components',
                            type: 'Group',
                            props: {
                                gap: 'xs',
                                wrap: 'nowrap',
                                children: [
                                    {
                                        namespace: 'dash_mantine_components',
                                        type: 'Text',
                                        props: {
                                            children: hh + ':' + mm + ':' + ss,
                                            size: 'xs',
                                            c: 'dimmed',
                                            style: {fontVariantNumeric: 'tabular-nums', minWidth: 56},
                                        },
                                    },
                                    {
                                        namespace: 'dash_mantine_components',
                                        type: 'Text',
                                        props: {
                                            children: a.message || a.type || 'action',
                                            size: 'xs',
                                            style: {
                                                overflow: 'hidden',
                                                textOverflow: 'ellipsis',
                                                whiteSpace: 'nowrap',
                                            },
                                        },
                                    },
                                ],
                            },
                        };
                    }),
                },
            };
        }
        """,
        Output("colab-ai-action-log", "children"),
        Input("colab-ai-actions", "data"),
    )

    # AI state badge + target line in the sidebar.
    clientside_callback(
        """
        function(intent, presence) {
            if (!intent) return ['idle', 'gray', '(waiting for humans…)'];
            const color = intent.type === 'follow' ? 'indigo'
                        : intent.type === 'observe' ? 'teal'
                        : intent.type === 'rest' ? 'gray' : 'indigo';
            let label = intent.type;
            if (intent.hint === 'orbiting-element') label = 'orbit';
            let target = '';
            if (intent.type === 'follow' && intent.targetUserId) {
                const p = (presence || []).find(x => x.userId === intent.targetUserId);
                target = 'following ' + (p ? p.name : intent.targetUserId);
            } else if (intent.type === 'observe' && intent.hint === 'orbiting-element') {
                target = 'examining an element';
            } else if (intent.type === 'observe') {
                target = 'observing (' + Math.round(intent.x) + ', ' + Math.round(intent.y) + ')';
            } else if (intent.type === 'rest') {
                target = 'resting';
            } else {
                target = intent.type;
            }
            return [label, color, target];
        }
        """,
        Output("colab-ai-state", "children"),
        Output("colab-ai-state", "color"),
        Output("colab-ai-target", "children"),
        Input("colab-ai-intent", "data"),
        Input("colab-presence", "data"),
    )

    # Manual "Tidy canvas now" → call force_tidy on the agent.
    @callback(
        Output("colab-noop-tidy", "data"),
        Input("colab-tidy-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def _manual_tidy(n_clicks):
        if not n_clicks:
            return no_update
        agent = get_agent() if get_agent is not None else None
        if agent is None:
            return no_update
        agent.force_tidy()
        return no_update

    # Incoming scene from a peer → dispatch updateScene with just
    # `elements` + `files`. We deliberately skip `appState` so the
    # receiver keeps their own zoom, scroll, theme, and collaborator
    # cursors unchanged.
    #
    # If the local user is mid-drag, we stash the scene on `window`
    # and apply it when the drag releases (see the pointer-up flush
    # callback below). Otherwise Excalidraw's in-flight draft element
    # gets clobbered.
    clientside_callback(
        """
        function(payload, identity, pointerDown) {
            if (!payload || !identity) return window.dash_clientside.no_update;
            if (payload.userId === identity.userId) return window.dash_clientside.no_update;
            if (pointerDown) {
                // Defer; the newest deferred scene wins.
                window._colabPendingPeerScene = payload;
                return window.dash_clientside.no_update;
            }
            try {
                const parsed = JSON.parse(payload.serializedData);
                return {
                    id: 'peer-scene-' + Date.now(),
                    type: 'updateScene',
                    payload: {
                        elements: parsed.elements || [],
                        files: parsed.files || {},
                    },
                };
            } catch (err) {
                return window.dash_clientside.no_update;
            }
        }
        """,
        Output("colab-canvas", "command", allow_duplicate=True),
        Input("colab-socket", "data-colab_scene"),
        State("colab-identity", "data"),
        State("colab-pointer-down", "data"),
        prevent_initial_call=True,
    )

    # When the local drag ends, flush any peer scene we deferred.
    clientside_callback(
        """
        function(up) {
            if (!up) return window.dash_clientside.no_update;
            const pending = window._colabPendingPeerScene;
            if (!pending) return window.dash_clientside.no_update;
            window._colabPendingPeerScene = null;
            try {
                const parsed = JSON.parse(pending.serializedData);
                return {
                    id: 'peer-scene-flush-' + Date.now(),
                    type: 'updateScene',
                    payload: {
                        elements: parsed.elements || [],
                        files: parsed.files || {},
                    },
                };
            } catch (err) {
                return window.dash_clientside.no_update;
            }
        }
        """,
        Output("colab-canvas", "command", allow_duplicate=True),
        Input("colab-canvas", "lastPointerUp"),
        prevent_initial_call=True,
    )

    # Late-join scene hydration — on welcome, if the server sent a
    # non-null scene, apply it once.
    clientside_callback(
        """
        function(scene) {
            if (!scene) return window.dash_clientside.no_update;
            try {
                const parsed = JSON.parse(scene);
                return {
                    id: 'join-scene-' + Date.now(),
                    type: 'updateScene',
                    payload: {
                        elements: parsed.elements || [],
                        files: parsed.files || {},
                    },
                };
            } catch (err) {
                return window.dash_clientside.no_update;
            }
        }
        """,
        Output("colab-canvas", "command", allow_duplicate=True),
        Input("colab-server-scene", "data"),
        prevent_initial_call=True,
    )