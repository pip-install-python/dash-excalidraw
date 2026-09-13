"""The component's prop surface, and two mistakes that were silent.

Both bugs behind this file shared a shape: a call that did nothing and said
nothing. `getSceneVersion` was read as a method that does not exist, behind a
`typeof === "function"` guard that turned "broken" into "empty"; and
`toggleSidebar` was handed a TAB name where it wanted a SIDEBAR name, which it
answers with `false` and no other sign. Neither raised, neither logged, and
both looked exactly like a feature nobody had wired up yet.

These tests are cheap and they pin the parts that a future edit could quietly
undo: that the props exist at all on the Python side, and that the pages call
the sidebar by a name Excalidraw actually has.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dash_excalidraw import DashExcalidraw

REPO_ROOT = Path(__file__).resolve().parent.parent


def _tsx_code() -> str:
    """The TSX with comments stripped.

    Every assertion here is about what the component DOES, and this file's own
    explanations quote the broken forms verbatim — `apiRef.current?.
    getSceneVersion()` appears in the comment that exists to stop anyone
    writing it again. Matching raw text would fail on the documentation of the
    fix, which is the same mistake as grepping a page for a string its own
    source listing prints.
    """
    src = (REPO_ROOT / "src/ts/components/DashExcalidraw.tsx").read_text(
        encoding="utf-8"
    )
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _py_code(rel: str) -> str:
    """Python source with `#` comments stripped, for the same reason."""
    src = (REPO_ROOT / rel).read_text(encoding="utf-8")
    return "\n".join(line.split("#", 1)[0] for line in src.splitlines())


class TestTheWelcomeScreenProps:
    """A prop that is not in the generated stub cannot be set from Python."""

    @pytest.mark.parametrize(
        "prop", ["welcomeScreen", "welcomeScreenContent", "welcomeScene"]
    )
    def test_the_stub_declares_it(self, prop):
        assert prop in DashExcalidraw().available_properties, (
            f"{prop} is missing from the generated stub — `npm run "
            f"build:backends` was not re-run after the TSX changed, and Dash "
            f"will reject it as an unknown prop"
        )

    def test_the_overlay_is_composed_as_a_child_not_pushed_through_appstate(self):
        """MEASURED, and the obvious alternative is wrong.

        `appState.showWelcomeScreen` exists, so pushing it through
        `updateScene` looks like the natural mechanism. It silently does
        nothing — the vendor filters that key out of the merge, and the flag
        stays `true` however it is set. The overlay is therefore controlled by
        mounting and unmounting Excalidraw's `<WelcomeScreen>` child, which
        React does with the prop.

        This asserts the finding is written down where the next person will
        look, because the code that would "fix" it back is a two-line effect
        that reads perfectly well.
        """
        tsx = _tsx_code()
        assert "<WelcomeScreen>" in tsx, "the overlay is no longer composed"
        # And it must NOT be driven through appState, which is silently
        # ignored — asserted against the code, not the note that explains it.
        assert "showWelcomeScreen" not in tsx, (
            "something pushes appState.showWelcomeScreen again; measured, the "
            "vendor filters that key out of updateScene and the flag never moves"
        )
        raw = (REPO_ROOT / "src/ts/components/DashExcalidraw.tsx").read_text(
            encoding="utf-8"
        )
        assert "showWelcomeScreen" in raw, (
            "the note explaining why appState is NOT the mechanism has gone; "
            "without it the next reader will try the push and find it silent"
        )

    def test_name_is_kept_in_step_with_appstate(self):
        # The mirror image: `name` IS accepted by updateScene, while
        # showWelcomeScreen is not. Excalidraw seeds appState.name at mount
        # and then stops looking, so without this the prop moved and the
        # scene kept its old name in the export dialog.
        tsx = _tsx_code()
        assert "appState: {name}" in tsx


class TestTheSidebarIsCalledByANameExcalidrawHas:
    """`toggleSidebar` answers False for an unknown sidebar and does nothing.

    Excalidraw's built-in sidebar is named "default"; "library" and "search"
    are TABS inside it. Two pages passed the tab name as the sidebar name, so
    both buttons were inert while the canvas's own library button opened the
    very same panel.
    """

    PAGES = ("docs/library/library.py", "docs/commands/commands.py")

    @pytest.mark.parametrize("rel", PAGES)
    def test_the_page_names_the_sidebar_not_the_tab(self, rel):
        src = _py_code(rel)
        payloads = re.findall(r'toggleSidebar"[^)]*?\{([^}]*)\}', src, re.S)
        if not payloads:
            payloads = re.findall(r'"toggleSidebar",\s*\{([^}]*)\}', src, re.S)
        assert payloads, f"{rel} no longer dispatches toggleSidebar — corpus empty"
        for payload in payloads:
            assert '"name": "default"' in payload, (
                f'{rel} passes {payload.strip()!r}; "library" is a tab, not a '
                f'sidebar, and Excalidraw silently ignores an unknown one'
            )

    def test_the_component_warns_instead_of_swallowing_a_miss(self):
        tsx = _tsx_code()
        assert "toggleSidebar did nothing" in tsx, (
            "the warning is gone; a dispatched command that evaporates with no "
            "sign is how this survived in two pages at once"
        )


class TestSceneVersionComesFromThePackage:
    def test_it_is_not_read_as_a_method_on_the_api(self):
        """The original bug, pinned.

        `getSceneVersion` is a standalone export that takes the elements.
        Called as `api.getSceneVersion()` it is `undefined` forever, and the
        `typeof === "function"` guard that wrapped it made the failure look
        like an empty value rather than a broken call.
        """
        tsx = _tsx_code()
        assert "getSceneVersion(elements" in tsx, "the package export is not used"
        assert "apiRef.current?.getSceneVersion" not in tsx
        assert "current.getSceneVersion()" not in tsx

    def test_addfiles_reports_the_file_store(self):
        # Registering a file touches no element, so Excalidraw fires no
        # onChange and `files` would never mention it. The command reports the
        # store itself, or Python cannot tell success from failure.
        tsx = _tsx_code()
        assert "writeProps({files: api.getFiles()})" in tsx
