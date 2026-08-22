"""The PACKAGE's own surface — `pip install dash-excalidraw`.

Everything else in tests/ is about the documentation SITE. This file is about
the wheel, and specifically about the promises the wheel makes to someone who
has never seen this repo: it depends on Dash and nothing else, it exports one
component and three helpers, and every prop on that component survives the
Python->JS bridge.

Those promises are asserted in CI too, against a built wheel installed into a
clean venv. They are ALSO asserted here because CI is where they are hardest
to iterate on — the wheel job's dependency check shipped twice with a bug
(once cwd-dependent, once blind to optional-dependency markers) and both
round trips cost a full CI run to discover. A local test is the cheap half of
the same guard.
"""

from __future__ import annotations

import importlib.metadata as md

import pytest

import dash_excalidraw as dex


def test_the_package_depends_on_dash_and_nothing_else():
    """`pip install dash-excalidraw` must not drag in the docs site.

    BASE requirements only. `md.requires()` also returns every optional
    dependency with its `extra == "..."` marker attached — anthropic,
    pytest, flask-socketio — and a plain install pulls none of them.
    """
    reqs = md.requires("dash-excalidraw") or []
    base = [r for r in reqs if "extra ==" not in r]
    names = {r.split(";")[0].split("[")[0].strip().lower()
             .split(">")[0].split("<")[0].split("=")[0].strip()
             for r in base}
    assert names == {"dash"}, (
        f"the wheel gained a runtime dependency: {names}. The docs site's "
        "dependencies belong in requirements.txt, never in pyproject.toml."
    )
    assert base, "the wheel declares no runtime dependency at all"


def test_the_public_surface_is_the_component_and_the_helpers():
    """One component, three pure-Python helpers. `__all__` is the contract."""
    assert set(dex.__all__) == {
        "DashExcalidraw",
        "decode_data_url",
        "strip_inline_files",
        "restore_inline_files",
    }
    for name in dex.__all__:
        assert hasattr(dex, name), f"__all__ promises {name} and it is absent"


def test_every_prop_survives_the_python_to_js_bridge():
    """The design constraint the whole component is built around.

    REBUILD.md's rule: every prop must be JSON-serializable — no functions,
    no RegExps, no class instances. `to_json` is Dash's own encoder, so this
    is the same serialisation a real page performs.
    """
    from dash import Dash, html
    from dash._utils import to_json

    app = Dash(__name__)
    app.layout = html.Div([
        dex.DashExcalidraw(
            id="canvas",
            width="100%",
            height="600px",
            theme="dark",
            initialData={"elements": [],
                         "appState": {"viewBackgroundColor": "#ffffff"}},
            UIOptions={"canvasActions": {"saveToActiveFile": False}},
            # Compiled to case-insensitive RegExps on the TS side; strings
            # are the only thing that can cross the bridge.
            validateEmbeddable=["*.youtube.com"],
            command={"id": "abc", "type": "updateScene", "payload": {}},
        ),
    ])
    payload = to_json(app.layout)
    assert "validateEmbeddable" in payload
    assert "updateScene" in payload


def test_decode_data_url_round_trips():
    mime, blob = dex.decode_data_url("data:image/png;base64,iVBORw0KGgo=")
    assert mime == "image/png"
    assert blob.startswith(b"\x89PNG")


def test_decode_data_url_rejects_what_is_not_one():
    """A boundary helper: it is fed whatever the browser pasted."""
    for bad in ("https://example.com/x.png", "", "data:", None):
        with pytest.raises(ValueError):
            dex.decode_data_url(bad)


def test_strip_and_restore_are_inverses():
    """The file-externalization pair documented on /file-uploads.

    `strip_inline_files` is what makes `externalizedSerializedData` safe to
    persist; `restore_inline_files` is what puts the bytes back.
    """
    import json

    scene = {
        "elements": [{"type": "image", "fileId": "f1"}],
        "files": {"f1": {"mimeType": "image/png",
                         "dataURL": "data:image/png;base64,iVBORw0KGgo="}},
    }
    stripped, extracted = dex.strip_inline_files(json.dumps(scene))
    assert "iVBORw0KGgo" not in stripped, "inline bytes survived the strip"
    assert "f1" in extracted

    restored = dex.restore_inline_files(stripped, extracted)
    assert "iVBORw0KGgo" in restored
