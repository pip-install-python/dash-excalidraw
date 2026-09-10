"""Every provider key is blanked before the suite can spend money.

THE HOLE THIS CLOSES, measured at 46a1694: `tests/conftest.py` blanked a
hand-kept `SECRET_ENV_KEYS` tuple that named Clerk, the session secrets and
the databases — and not one provider key. `CHATGPT_API_KEY` reached
`lib/scene_ai.py` in E2 and never reached that tuple. On any machine holding
that key in its shell or `.env`, `available_models` would have called the live
endpoint on every run. It is a GET, so nothing would have been billed; the
POST that costs money sits behind the same absent fence.

So the fence is no longer hand-kept. conftest imports the names from the
module that reads them, and the test below asserts the two agree — which is
what makes forgetting the NEXT provider a red test rather than a live call.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from lib.scene_ai import PROVIDER_KEY_VARS

MODULE = Path(__file__).resolve().parent.parent / "lib" / "scene_ai.py"

# `os.environ.get("NAME")` / `os.environ["NAME"]` for anything that looks like
# a credential. Deliberately not every env read — RENDER and APP_ENV are
# posture flags, not keys, and blanking them would change what is tested.
_READS = re.compile(r"""os\.environ(?:\.get)?[(\[]\s*["']([A-Z0-9_]+)["']""")
_CREDENTIAL = re.compile(r"(_KEY|_TOKEN|_SECRET)$")


def _keys_the_module_reads() -> set[str]:
    src = MODULE.read_text(encoding="utf-8")
    return {n for n in _READS.findall(src) if _CREDENTIAL.search(n)}


class TestTheFenceIsDerivedNotHandKept:
    def test_the_module_reads_at_least_one_key(self):
        # Non-vacuity. If the regex stopped matching, every assertion below
        # would pass against an empty set and the fence would be gone.
        found = _keys_the_module_reads()
        assert found, "no credential env reads found — the detector is broken"

    def test_every_key_the_module_reads_is_declared(self):
        undeclared = _keys_the_module_reads() - set(PROVIDER_KEY_VARS)
        assert not undeclared, (
            f"lib/scene_ai.py reads {sorted(undeclared)} but PROVIDER_KEY_VARS "
            f"does not declare them, so conftest never blanks them and the "
            f"suite can reach a live provider."
        )

    def test_the_declared_extras_are_deliberate(self):
        # PROVIDER_KEY_VARS may legitimately be a SUPERSET: the Anthropic SDK
        # reads ANTHROPIC_AUTH_TOKEN itself, without this module ever naming
        # it, and blanking only ANTHROPIC_API_KEY would still leave a
        # configured client. Anything else extra is a stale entry.
        extra = set(PROVIDER_KEY_VARS) - _keys_the_module_reads()
        assert extra <= {"ANTHROPIC_AUTH_TOKEN"}, (
            f"PROVIDER_KEY_VARS declares {sorted(extra)} which nothing reads"
        )


class TestTheyAreActuallyBlankDuringTheSuite:
    """The list being right is worthless if conftest does not apply it."""

    @pytest.mark.parametrize("name", PROVIDER_KEY_VARS)
    def test_each_one_is_falsy(self, name):
        # "" not absent: `load_dotenv()` never overrides an existing key, so
        # pinning to empty neutralises a developer's .env without deleting it.
        assert not os.environ.get(name), (
            f"{name} is set during the test suite — a real provider call is "
            f"one code path away"
        )

    def test_a_configured_client_cannot_be_built(self):
        # The end the fence exists for, asserted directly rather than inferred
        # from the variables: the availability check must report "unknown"
        # instead of reaching the network.
        from lib import scene_ai

        scene_ai._AVAILABILITY_CACHE.clear()
        try:
            assert scene_ai._reported_claude_models() is None
        finally:
            scene_ai._AVAILABILITY_CACHE.clear()
