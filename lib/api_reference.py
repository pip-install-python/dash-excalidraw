"""Component prop tables from an installed Dash component package (1.6.38).

A Dash component package ships ``metadata.json`` next to its ``__init__``
(react-docgen output: one entry per component source file with
``displayName`` and ``props`` → ``{type, required, description,
defaultValue}``), and every generated component class carries the same
props in its docstring. ``metadata.json`` is the one machine-readable
source, so this reads it FIRST; the classes exist in the package namespace
and are used to confirm a component is exported. (The drop named
``_prop_names``; Dash 4 no longer sets it on generated classes — the
docstring and metadata.json are what remain.)

DOCSTRING FALLBACK (this fork, 2026-08-30, and filed upward). ``metadata.json``
is a BUILD ARTIFACT, and a component repo may legitimately not ship it:
here it is gitignored on purpose and ``scripts/check_release.py`` asserts it
is absent from the wheel, so it exists only on a machine that has run
``npm run build``. Reading it alone made /api document every prop on the
author's laptop and NOTHING in CI or in the production image — green
locally, an empty section on the wire. The generated stub
(``DashExcalidraw.py``) is tracked and IS in the wheel, and its docstring
carries the same catalogue in Dash's standard "Keyword arguments:" format,
so that is the fallback. Prefer metadata.json when present (richer types and
defaults); parse the docstring when it is not. A package that has neither
still returns [].
"""
from __future__ import annotations

import importlib
import json
import re
from pathlib import Path


def _type_name(t) -> str:
    if not isinstance(t, dict):
        return str(t or "")
    name = t.get("name") or ""
    if name == "enum" and isinstance(t.get("value"), list):
        vals = [str(v.get("value", v)) for v in t["value"]]
        return "one of " + ", ".join(vals[:8]) + (" …" if len(vals) > 8 else "")
    if name == "union" and isinstance(t.get("value"), list):
        return " | ".join(_type_name(v) for v in t["value"])
    if name == "arrayOf":
        return f"list of {_type_name(t.get('value'))}"
    if name in ("shape", "exact"):
        return "dict"
    return name or "any"


def _default(prop) -> str:
    d = prop.get("defaultValue")
    if isinstance(d, dict):
        return str(d.get("value", ""))
    return "" if d is None else str(d)


_DOC_PROP = re.compile(
    r"^- (?P<name>\w+) \((?P<type>.*?);\s*(?P<req>required|optional)\):\s*(?P<desc>.*)$"
)


def _props_from_docstring(doc: str) -> list[dict]:
    """Parse Dash's generated "Keyword arguments:" block.

    Each prop is `- name (type; optional): description`, the description
    continuing on following indented lines until the next `- ` entry. Nested
    shape members are indented further and are deliberately NOT hoisted into
    top-level props — they belong to their parent's type.
    """
    props, cur = [], None
    for raw in (doc or "").splitlines():
        line = raw.strip()
        m = _DOC_PROP.match(line)
        if m and not raw.startswith("    - "):
            cur = {
                "name": m.group("name"),
                "type": m.group("type").split(";")[0].strip(),
                "required": m.group("req") == "required",
                "default": "",
                "description": m.group("desc").strip(),
            }
            props.append(cur)
        elif cur is not None and line and not line.startswith("- "):
            cur["description"] = (cur["description"] + " " + line).strip()
        elif not line:
            cur = None
    for p in props:
        if p["name"] in ("setProps", "loading_state"):
            props.remove(p)
    props.sort(key=lambda p: (p["name"] != "id", p["name"]))
    return props


def _from_classes(mod) -> list[dict]:
    """Every exported Dash component class, from its generated docstring."""
    out = []
    for name in sorted(getattr(mod, "__all__", None) or dir(mod)):
        cls = getattr(mod, name, None)
        if not isinstance(cls, type) or not hasattr(cls, "_base_nodes"):
            continue
        doc = cls.__doc__ or ""
        props = _props_from_docstring(doc)
        if not props:
            continue
        head = doc.split("Keyword arguments:")[0].strip()
        out.append({"name": name, "description": head, "props": props})
    return out


def load_package(package: str) -> list[dict]:
    """``[{name, description, props: [{name, type, required, default, description}]}]``
    for every component the package exports, sorted by name. Raises
    ImportError if the package is not installed; returns [] if it ships no
    metadata.json (not a Dash component package)."""
    mod = importlib.import_module(package)
    meta_path = Path(mod.__file__).resolve().parent / "metadata.json"
    if not meta_path.is_file():
        # No build artifact — read the generated classes instead. This is the
        # normal state in CI and in the production image; see the module
        # docstring.
        return _from_classes(mod)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    out = []
    for entry in meta.values():
        name = entry.get("displayName") or ""
        if not name or not hasattr(mod, name):
            continue
        props = []
        for pname, p in (entry.get("props") or {}).items():
            if pname in ("setProps", "loading_state"):
                continue
            props.append({
                "name": pname,
                "type": _type_name(p.get("type") or p.get("flowType") or p.get("tsType")),
                "required": bool(p.get("required")),
                "default": _default(p),
                "description": (p.get("description") or "").strip(),
            })
        props.sort(key=lambda p: (p["name"] != "id", p["name"]))
        out.append({"name": name, "description": (entry.get("description") or "").strip(), "props": props})
    out.sort(key=lambda c: c["name"])
    return out


def load_packages(packages) -> list[dict]:
    """Every package's components, in declaration order; a missing package
    is reported as one entry with an ``error`` rather than raising — the
    page must render on a host whose extra is not installed."""
    out = []
    for pkg in packages:
        try:
            out.append({"package": pkg, "components": load_package(pkg)})
        except Exception as exc:  # noqa: BLE001
            out.append({"package": pkg, "components": [], "error": f"{type(exc).__name__}: {exc}"})
    return out


def as_markdown(packages) -> str:
    """The same tables as Markdown — the page's LLMS_DOC."""
    lines = ["# API reference", ""]
    for pkg in load_packages(packages):
        lines += [f"## {pkg['package']}", ""]
        if pkg.get("error"):
            lines += [f"_not installed: {pkg['error']}_", ""]
        for c in pkg["components"]:
            lines += [f"### {c['name']}", ""]
            if c["description"]:
                lines += [c["description"], ""]
            lines += ["| prop | type | default | description |", "|---|---|---|---|"]
            for p in c["props"]:
                desc = p["description"].replace("\n", " ").replace("|", "\\|")
                lines.append(f"| `{p['name']}`{' *' if p['required'] else ''} | {p['type']} | {p['default']} | {desc} |")
            lines.append("")
    return "\n".join(lines)
