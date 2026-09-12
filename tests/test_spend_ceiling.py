"""The daily spend ceiling.

THE PROPERTY THAT MATTERS MOST is that there is ONE budget, not one per worker.
The production image runs `gunicorn --workers 2`, so a counter held in a module
global would give each worker its own allowance: the real ceiling would be
twice the configured one, and would change if WEB_CONCURRENCY did. A safety
limit that silently depends on how many processes happen to be running is not
a limit, and it would look perfect in development, where there is one process.

`test_one_ceiling_across_two_handles` and
`test_one_ceiling_across_two_interpreters` are that property. The second is not
a stand-in for the first — it is the actual claim.

Nothing here makes a paid call. Money is recorded through `record`, and the
call paths are exercised with the provider client stubbed out.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import conftest
import diskcache
import pytest

from lib import spend

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(spend, "CACHE_DIR", str(tmp_path / "spend"))
    monkeypatch.setattr(spend, "_cache", None)
    monkeypatch.delenv(spend._CEILING_ENV, raising=False)
    yield
    if spend._cache is not None:
        spend._cache.close()


class TestOneBudgetNotOnePerWorker:
    def test_one_ceiling_across_two_handles(self):
        """Write through this process's handle, read through a fresh one."""
        spend.record(4.00)

        spend._cache.close()
        spend._cache = None  # the next call opens a new handle

        assert spend.spent_today() == pytest.approx(4.00), (
            "the spend was invisible to a second handle — each gunicorn worker "
            "would have had its own budget"
        )

    def test_a_handle_this_module_never_opened_sees_it(self):
        # Asserted against a Cache built here, so it cannot be satisfied by
        # any in-process state at all.
        spend.record(2.50)
        outsider = diskcache.Cache(spend.CACHE_DIR)
        try:
            key = spend._day_key()
            assert outsider.get(key) == 2_500_000  # micro-dollars
        finally:
            outsider.close()

    def test_one_ceiling_across_two_interpreters(self, tmp_path):
        """The real claim: two processes, like two gunicorn workers."""
        store = str(tmp_path / "xproc")
        env = {**os.environ, "AI_SPEND_DIR": store, "PYTHONPATH": str(REPO_ROOT)}

        spender = (
            "from lib import spend\n"
            "spend.record(3.25)\n"
            "print(spend.spent_today())\n"
        )
        first = subprocess.run(
            [sys.executable, "-c", spender], env=env, capture_output=True,
            text=True, timeout=60, check=True,
        ).stdout.strip().splitlines()[-1]
        assert float(first) == pytest.approx(3.25)

        reader = (
            "from lib import spend\n"
            "print(spend.spent_today())\n"
        )
        second = subprocess.run(
            [sys.executable, "-c", reader], env=env, capture_output=True,
            text=True, timeout=60, check=True,
        ).stdout.strip().splitlines()[-1]
        assert float(second) == pytest.approx(3.25), (
            "a second interpreter saw a different total — this is the "
            "per-worker-budget failure, reproduced"
        )


class TestAdmission:
    def test_under_the_ceiling_passes(self):
        spend.check(1.00)  # must not raise

    def test_at_the_ceiling_refuses(self, monkeypatch):
        monkeypatch.setattr(spend, "DAILY_CEILING_USD", 5.0)
        spend.record(5.0)
        with pytest.raises(spend.CeilingReached):
            spend.check()

    def test_a_run_that_would_cross_the_ceiling_refuses(self, monkeypatch):
        monkeypatch.setattr(spend, "DAILY_CEILING_USD", 5.0)
        spend.record(4.50)
        with pytest.raises(spend.CeilingReached, match=r"\$0\.50"):
            spend.check(2.00)

    def test_the_message_is_written_for_a_person(self, monkeypatch):
        # Someone hitting this needs to know it is a budget and that it ends —
        # a bare "limit reached" reads as a broken site.
        monkeypatch.setattr(spend, "DAILY_CEILING_USD", 1.0)
        spend.record(1.0)
        with pytest.raises(spend.CeilingReached) as exc:
            spend.check()
        message = str(exc.value)
        assert "midnight UTC" in message
        assert "not a fault with your prompt" in message


class TestTheDial:
    def test_the_constant_is_the_default(self, monkeypatch):
        monkeypatch.setattr(spend, "DAILY_CEILING_USD", 7.5)
        assert spend.ceiling() == 7.5

    def test_the_env_override_wins_when_valid(self, monkeypatch):
        monkeypatch.setattr(spend, "DAILY_CEILING_USD", 7.5)
        monkeypatch.setenv(spend._CEILING_ENV, "25")
        assert spend.ceiling() == 25.0

    @pytest.mark.parametrize("bad", ["", "   ", "abc", "10; DROP", "-3", "NaN!"])
    def test_a_bad_override_falls_back_rather_than_disabling_the_brake(
        self, monkeypatch, bad
    ):
        # The dangerous failure would be reading a typo as "no limit". The
        # other dangerous one is reading it as zero and taking the AI pages
        # down. Both are avoided by ignoring it.
        monkeypatch.setattr(spend, "DAILY_CEILING_USD", 7.5)
        monkeypatch.setenv(spend._CEILING_ENV, bad)
        assert spend.ceiling() == 7.5


class TestRecording:
    def test_amounts_accumulate(self):
        spend.record(1.10)
        spend.record(2.20)
        assert spend.spent_today() == pytest.approx(3.30)

    def test_many_small_amounts_do_not_drift(self):
        # Integer micro-dollars, not floats: a thousand additions of $0.001
        # under float accumulation would not land on $1.00 exactly.
        for _ in range(1000):
            spend.record(0.001)
        assert spend.spent_today() == pytest.approx(1.00, abs=1e-9)

    def test_zero_and_negative_are_ignored(self):
        spend.record(1.00)
        spend.record(0)
        spend.record(-5.00)
        assert spend.spent_today() == pytest.approx(1.00)

    def test_yesterday_does_not_count_against_today(self):
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        spend.cache().set(spend._day_key(yesterday), 99_000_000)
        assert spend.spent_today() == 0.0
        spend.check()  # and it does not block today


class TestTheCallPathsAreWired:
    """A ceiling nothing consults is decoration."""

    def _stub_claude(self, monkeypatch):
        import types
        stub = types.ModuleType("anthropic")
        stub.Anthropic = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("the provider was called despite the ceiling")
        )
        monkeypatch.setitem(sys.modules, "anthropic", stub)

    def test_a_blocking_claude_call_is_refused_before_the_client_is_built(
        self, monkeypatch
    ):
        from lib import scene_ai

        monkeypatch.setattr(spend, "DAILY_CEILING_USD", 0.01)
        spend.record(1.00)
        self._stub_claude(monkeypatch)
        with pytest.raises(spend.CeilingReached):
            scene_ai._call_claude("claude-opus-5", "draw", 24000, "low")

    def test_a_streamed_run_is_refused_once_per_run(self, monkeypatch):
        from lib import scene_ai

        monkeypatch.setattr(spend, "DAILY_CEILING_USD", 0.01)
        spend.record(1.00)
        stream = scene_ai.stream_model("claude-opus-5", "draw", 24000, "low")
        with pytest.raises(spend.CeilingReached):
            next(stream)

    def test_gemini_is_refused_too_even_though_it_cannot_be_priced(
        self, monkeypatch
    ):
        # It has no MODEL_PRICING entry, so it cannot be estimated or counted.
        # It is still a paid call and must not run on a blown budget.
        from lib import scene_ai

        monkeypatch.setattr(spend, "DAILY_CEILING_USD", 0.01)
        spend.record(1.00)
        with pytest.raises(spend.CeilingReached):
            scene_ai._call_gemini("gemini-2.5-flash", "draw")

    def test_settlement_records_the_actual_cost(self):
        from lib.scene_ai import MODEL_PRICING, settle

        meta = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
        charged = settle("claude-opus-5", meta)
        assert charged == pytest.approx(sum(MODEL_PRICING["claude-opus-5"]))
        assert spend.spent_today() == pytest.approx(charged)

    def test_settling_a_run_charges_once_not_once_per_element(self):
        # The trap this guards: `settle` in the element loop would bill a
        # forty-shape scene forty times and trip the ceiling on one drawing.
        from lib.scene_ai import settle

        meta = {"input_tokens": 1000, "output_tokens": 1000}
        first = settle("claude-opus-5", meta)
        after_one = spend.spent_today()
        assert after_one == pytest.approx(first)

    def test_an_unpriced_model_settles_at_zero_rather_than_raising(self):
        # Every model this app offers is priced now, Gemini included, so the
        # case needs an id from outside the tables — a model added to a
        # selector and forgotten in MODEL_PRICING. It must not raise on the
        # way out of a call that already succeeded and already cost money.
        from lib.scene_ai import MODEL_PRICING, settle

        unknown = "some-model-nobody-priced"
        assert unknown not in MODEL_PRICING
        assert settle(unknown, {"input_tokens": 10, "output_tokens": 10}) == 0.0
        assert spend.spent_today() == 0.0

    def test_no_meta_settles_at_zero(self):
        from lib.scene_ai import settle

        assert settle("claude-opus-5", None) == 0.0


class TestSummary:
    def test_it_reports_what_a_status_line_needs(self, monkeypatch):
        monkeypatch.setattr(spend, "DAILY_CEILING_USD", 10.0)
        spend.record(2.50)
        s = spend.summary()
        assert s["ceiling"] == 10.0
        assert s["spent"] == pytest.approx(2.50)
        assert s["remaining"] == pytest.approx(7.50)
        assert s["fraction"] == pytest.approx(0.25)
        assert s["overridden"] is False

    def test_it_flags_an_override(self, monkeypatch):
        monkeypatch.setenv(spend._CEILING_ENV, "50")
        assert spend.summary()["overridden"] is True


class TestThePagesRefuseUpFront:
    """A generator's body does not run until it is advanced.

    `stream_model` admits once per run, but `scene_stream.start` only CREATES
    the generator — the admission fires later, on the worker thread. Without a
    check in the page, a blown budget would surface as a red error on a run
    that had already been created, which reads as a fault rather than a
    limit. Each page therefore checks before it starts anything.
    """

    def test_benchmark_prices_the_whole_sweep_not_one_cell(self, monkeypatch):
        from docs.benchmark import benchmark

        # The suite runs keyless (conftest blanks every provider key), so the
        # page's own no-keys refusal fires before the ceiling is consulted.
        # This test is about the CEILING, so it puts the page in the posture a
        # developer with a `.env` has.
        monkeypatch.setattr(benchmark, "ANY_KEY", True)
        monkeypatch.setattr(spend, "DAILY_CEILING_USD", 1.0)
        started = []
        monkeypatch.setattr(
            benchmark.scene_stream, "start", lambda **kw: started.append(kw) or "rid"
        )
        # Six cells that each fit under $1 but together do not. Admitting them
        # one at a time would let every one of them through.
        _, tick_disabled, message, color, *_ = benchmark._run(
            1, "claude-opus-5", "budget", None,
            ["16000", "24000", "48000", "64000"], None, None, "low", "draw a cat",
        )
        assert started == [], "the sweep was started despite exceeding the budget"
        assert tick_disabled is True
        assert color == "yellow"
        assert "budget" in str(message).lower()

    def test_benchmark_runs_when_the_sweep_fits(self, monkeypatch):
        from docs.benchmark import benchmark

        monkeypatch.setattr(benchmark, "ANY_KEY", True)
        monkeypatch.setattr(spend, "DAILY_CEILING_USD", 1000.0)
        started = []
        monkeypatch.setattr(
            benchmark.scene_stream,
            "start",
            lambda **kw: started.append(kw) or f"rid{len(started)}",
        )
        cells, tick_disabled, *_ = benchmark._run(
            1, "claude-opus-5", "budget", None, ["4000", "8000"], None, None,
            "low", "draw a cat",
        )
        assert len(started) == 2, "a sweep inside the budget must still run"
        assert tick_disabled is False
        assert len(cells) == 2


class TestTheSuiteDoesNotSpendTheRealBudget:
    """The defect that made this file necessary a second time.

    MEASURED 2026-09-11: `lib.spend` resolves CACHE_DIR at import from
    AI_SPEND_DIR or a machine-global default under $TMPDIR. Only this file's
    own fixture isolated it, so every OTHER test that reached a paid call —
    the mocked OpenAI ones — admitted and SETTLED against the real ledger.
    Four suite runs on one machine consumed the whole $10 day and the fourth
    went red with CeilingReached, in tests that never touch a network. The
    real ledger held $6.08 of entirely fabricated spend when this was found.

    On a developer's machine the same thing drains the ledger their dev server
    reads, so `pytest` a few times and /ai-agent starts refusing real work.
    """

    def test_the_suite_ledger_is_not_the_machine_global_one(self):
        # `isolated_ledger` points this test at tmp_path; conftest points
        # everything ELSE at a per-run temp dir. Both must be off the default.
        assert os.environ.get("AI_SPEND_DIR")
        for root, _ in conftest.global_store_snapshot():
            assert root != os.environ["AI_SPEND_DIR"]

    def test_a_mocked_paid_call_does_not_touch_the_global_ledger(self, monkeypatch):
        """The negative control — and the instrument must not disturb it.

        The FIRST version of this test snapshotted by opening
        `diskcache.Cache(global_path)`. A diskcache open CREATES the directory
        and writes cache.db, so the control touched the very thing it asserted
        untouched, and passed anyway because it compared its own two opens to
        each other. Measured: a bare open of a non-existent path leaves a
        directory containing cache.db.

        `conftest.global_store_snapshot` hashes bytes off the filesystem and
        opens nothing. Content, not existence — on a machine where an earlier
        run already created the path, "it does not exist" is not a control.
        """
        import types

        before = conftest.global_store_snapshot()

        class _Rec:
            def __call__(self, *, api_key=None, **_):
                return self

            @property
            def responses(self):
                return self

            def create(self, **kwargs):
                return types.SimpleNamespace(
                    output_text="{}",
                    status="completed",
                    usage=types.SimpleNamespace(input_tokens=9_000, output_tokens=9_000),
                    incomplete_details=None,
                )

        from lib import scene_ai

        stub = types.ModuleType("openai")
        stub.OpenAI = _Rec()
        monkeypatch.setitem(sys.modules, "openai", stub)
        monkeypatch.setenv("CHATGPT_API_KEY", "sk-test")
        scene_ai._call_openai("gpt-6-astra", "draw", 24000, "low")

        # It really did record — against the isolated ledger. Without this the
        # test would pass by doing nothing at all.
        assert spend.spent_today() > 0

        assert conftest.global_store_snapshot() == before, (
            "a mocked test wrote into a machine-global store; on a developer's "
            "box this drains the budget their dev server reads"
        )

    def test_the_snapshot_would_notice_a_write(self, tmp_path, monkeypatch):
        """Non-vacuity: a control that cannot detect a change is not one."""
        root = tmp_path / "fake-global"
        monkeypatch.setattr(conftest, "GLOBAL_STORES", (str(root),))

        assert conftest.global_store_snapshot() == [(str(root), "absent")]

        root.mkdir()
        (root / "cache.db").write_bytes(b"x")
        created = conftest.global_store_snapshot()
        assert created != [(str(root), "absent")]

        (root / "cache.db").write_bytes(b"y")
        assert conftest.global_store_snapshot() != created, (
            "the snapshot compares existence only — a rewritten file would slip "
            "through, which is exactly how the diskcache-open version passed"
        )


class TestGeminiCountsNow:
    """The hole E3 shipped with, closed.

    Refusing Gemini once the ceiling is reached was never the difficulty —
    COUNTING it was, and without a price it could not be counted. A day of
    nothing but Gemini could therefore pass the cap without tripping it.
    """

    def test_both_models_are_priced(self):
        from lib.scene_ai import GEMINI_MODELS, MODEL_PRICING

        assert GEMINI_MODELS, "corpus empty — the loop below would be vacuous"
        for entry in GEMINI_MODELS:
            assert entry["value"] in MODEL_PRICING
            inp, out = MODEL_PRICING[entry["value"]]
            assert inp > 0 and out > inp, "output should not be cheaper than input"

    def test_a_gemini_call_is_recorded(self):
        from lib.scene_ai import MODEL_PRICING, settle

        charged = settle(
            "gemini-2.5-pro", {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
        )
        assert charged == pytest.approx(sum(MODEL_PRICING["gemini-2.5-pro"]))
        assert spend.spent_today() == pytest.approx(charged)

    def test_gemini_stays_out_of_the_comparison_axis(self):
        # Priceable and comparable are different questions: /benchmark needs a
        # budget and an effort control, and `_call_gemini` has neither.
        from lib.scene_ai import COMPARABLE_MODELS, GEMINI_MODELS

        comparable = {m["value"] for m in COMPARABLE_MODELS}
        for entry in GEMINI_MODELS:
            assert entry["value"] not in comparable


class TestTheGuardWatchesWhatTheCodeUses:
    """A guard that computes the path itself can drift from the code.

    It did. `lib/spend` resolved its default from `os.environ["TMPDIR"]` while
    `lib/scene_stream` and the suite's guard used `tempfile.gettempdir()`.
    Those agree in a shell that exports TMPDIR and disagree in one that does
    not — so in the pytest process the guard watched
    /var/folders/.../excalidraw-ai-spend while the module wrote to
    $TMPDIR/excalidraw-ai-spend, and reported a clean result for a directory
    nothing had touched. Two spellings of "the temp directory" in one codebase
    is a defect waiting for a machine that distinguishes them.
    """

    def test_the_guard_watches_the_modules_own_defaults(self):
        from lib import scene_stream

        watched = {root for root, _ in conftest.global_store_snapshot()}
        assert spend.DEFAULT_CACHE_DIR in watched
        assert scene_stream.DEFAULT_CACHE_DIR in watched

    def test_both_modules_spell_the_temp_directory_the_same_way(self):
        import tempfile

        from lib import scene_stream

        base = tempfile.gettempdir()
        assert spend.DEFAULT_CACHE_DIR.startswith(base)
        assert scene_stream.DEFAULT_CACHE_DIR.startswith(base)

    def test_the_env_override_still_wins(self, monkeypatch):
        # The default is only a default; AI_SPEND_DIR is what the suite and a
        # persistent-disk deployment both rely on.
        assert os.environ["AI_SPEND_DIR"] != spend.DEFAULT_CACHE_DIR
