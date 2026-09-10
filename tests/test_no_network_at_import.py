"""No page may ask a provider anything while it is being imported.

MEASURED at 46a1694, in this app's own boot log:

    INFO:pages.markdown:Loading docs/ai-agent/ai-agent.md..
    INFO:httpx:HTTP Request: GET https://api.anthropic.com/v1/models?limit=100

`docs/ai-agent/ai_agent.py` called `available_models(CLAUDE_MODELS)` at module
level. Dash imports page modules while registering pages, so that put an
outbound request on the BOOT path: every start of the app blocked on a third
party being reachable, and the answer was then frozen for the life of the
process — a model that became available later never appeared, and a check that
failed during a deploy left the page permanently marked unverified.

The fix is that the control ships empty and a callback fills it. This file is
the guard on that, because the failure is silent: the page looks right, the
list is simply older than it should be, and nothing goes red.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Functions that reach a provider. A module-level call to any of these runs at
# import — which for a page module means at boot.
NETWORK_AT_IMPORT = {"available_models", "_reported_claude_models"}

PAGE_FILES = sorted(
    p
    for p in list((REPO_ROOT / "docs").rglob("*.py")) + list((REPO_ROOT / "pages").glob("*.py"))
    if not p.name.startswith("_")
)


def _module_level_calls(tree: ast.Module) -> set[str]:
    """Names called from a top-level statement, decorators and defs excluded.

    Walks only the statements that actually execute on import — the body of a
    `def` or `class` does not, which is the whole distinction being tested.
    """
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                fn = sub.func
                name = getattr(fn, "id", None) or getattr(fn, "attr", None)
                if name:
                    found.add(name)
    return found


class TestTheDetectorWorks:
    """A guard that cannot fail is not a guard."""

    def test_the_corpus_is_not_empty(self):
        assert len(PAGE_FILES) > 10, (
            f"only {len(PAGE_FILES)} page modules found — every assertion "
            f"below would be vacuous"
        )

    def test_it_catches_a_module_level_call(self):
        tree = ast.parse("from lib.scene_ai import available_models\n"
                         "OFFERED = available_models([])\n")
        assert "available_models" in _module_level_calls(tree)

    def test_it_ignores_a_call_inside_a_function(self):
        # This is the shape the fix takes, so the detector must not flag it.
        tree = ast.parse("def offered():\n    return available_models([])\n")
        assert "available_models" not in _module_level_calls(tree)


class TestNoPageAsksAProviderAtImport:
    @pytest.mark.parametrize("path", PAGE_FILES, ids=lambda p: p.name)
    def test_page_module(self, path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offending = _module_level_calls(tree) & NETWORK_AT_IMPORT
        assert not offending, (
            f"{path.relative_to(REPO_ROOT)} calls {sorted(offending)} at module "
            f"level. Dash imports page modules during page registration, so "
            f"this runs on the boot path and freezes its answer for the life "
            f"of the process. Move it into a callback."
        )
