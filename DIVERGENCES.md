# Divergences from the template

Every DELIBERATE difference between this repo and
dash-documentation-boilerplate, with its reason. This file is the
boundary between design and drift:

- Template syncs read this file FIRST and must not "restore" anything
  recorded here.
- A difference not recorded here is treated as drift and will be
  synced away.
- Record the divergence in the SAME commit that creates it — one
  line: what differs, why, and what the template would otherwise do.
- An empty list is a statement too: it means this repo intends to
  match the template exactly.

## This repo's divergences

### 1. This repo is the component AND its documentation site

The template is a documentation site. This repo is that site *plus* the
`dash-excalidraw` PyPI package it documents: `src/ts/`, `webpack.config.js`,
`package.json`, `tsconfig.json`, the tracked `dash_excalidraw/` package
(including the committed 7.7 MB JS bundle), `examples/`, `pyproject.toml`,
`MANIFEST.in`, `REBUILD.md`, `scripts/check_release.py` and the release
workflow all belong to that half and have no template counterpart.

**Why:** one component, one repo — the docs and the thing they document ship
from the same tree, so a prop added in `src/ts/` and the page describing it
cannot drift apart across a release.

**What a sync must not do:** treat those paths as drift, or "restore" a
docs-only file layout over them. `.dockerignore` excludes `node_modules/`
and the Dockerfile deliberately installs no Node — the bundle is committed,
so the production image is pure Python (template 1.6.x agrees).

### 2. `.claude/CLAUDE.md` above the contract sections is this repo's guide

The "Network role & the behavioral contract" and "Verification traps"
sections are **byte-verbatim** from the template and must stay that way.
Everything above them is this repo's own guide and documents both halves
(prop-surface philosophy, file externalization, the hooks/SSR guard, the
generator-vs-stub rule) alongside the docs-site customization points.

**Why:** the F1 pilots' correction, adopted in `sync/README.md` — a fork
whose CLAUDE.md is its own guide adapts everything above the contract.

### 3. `.claude/settings.json` carries more than the kit's keys, and its
seat-specific half lives in `settings.local.json`

The shipped file has the kit's three requirements (`"model": "opus"`,
`sandbox.network.allowedDomains` with this host + the hub,
`permissions.allow` with the matching `WebFetch` entries) plus this repo's
path-free permission defaults (`deny` on credential stores, `ask` on
publish-class commands, `sandbox.excludedCommands`).

Everything that names one machine's absolute paths — `additionalDirectories`,
`sandbox.filesystem.allowWrite`, `statusLine`, `enabledPlugins`,
`NPM_CONFIG_CACHE`, `effortLevel` — is in `.claude/settings.local.json`,
which stays ignored.

**Why:** this repo is public. A tracked `settings.json` containing
`allowWrite: ["/Users/pip/PycharmProjects/dash-excalidraw"]` gives every
other clone a sandbox that cannot write its own checkout, and publishes one
seat's directory layout for no benefit. The template's settings.json is
short enough that the question never came up there.

### 4. `DEPLOY-READINESS.md` stays tracked

The `.gitignore` session-document rule (`X402-SYNC-REPORT.md`,
`HANDOFF-*.md`, `KICKOFF-*.md`) is ported verbatim, but this repo also
carries `DEPLOY-READINESS.md` and keeps it in git.

**Why:** it is an owner deliverable, not a session document — the standing
checklist for this service's Render configuration. It names variable NAMES
and dashboard STEPS and no value of any kind (audited 2026-08-25). Losing it
to the convention would lose the only written record of what this deploy
still owes.

### 5. `cd.yml`'s verify gate is stricter than the template's

Template: `always() && needs.deploy.result != 'cancelled' && != 'skipped'`.
Here: `always() && needs.deploy.result == 'success'` — which excludes those
two **and** failure.

**Why:** when the build-match wait refuses because the site never served
this run's build, running the live battery anyway certifies whatever build
happens to be answering, and turns one cause into two red jobs. Measured on
this repo's first CD run (2026-08-21): six CI failures produced a seventh,
and the seventh was the most alarming and the least true.
`SYNC-1.6.10-1.6.16` item 4's detect ("excludes BOTH 'cancelled' AND
'skipped'") is satisfied by the stricter form. **A sync must not relax it.**

### 6. The Dockerfile `CMD` keeps gunicorn's worker/threads/timeout flags

Template: `gunicorn run:server -b 0.0.0.0:${PORT:-8550}`.
Here: `--workers "${WEB_CONCURRENCY:-2}" --threads 4 --timeout 120`, and the
port default is **8050**, this fork's number.

**Why the timeout:** `/ai-agent` and `/benchmark` call thinking models.
`lib/background.py` hands that work to a forked worker on Linux, but a
deployment running with `BACKGROUND_CALLBACKS=off` generates inside the
request — where gunicorn's 30s default kills it mid-flight and reports
nothing useful. **Why 8050:** `SYNC-1.6.10-1.6.16` item 5 states the
contract as the port defaulted at the point of use; 8550 is the template's
number, not the contract.

Both `CMD` and `HEALTHCHECK` use `${PORT:-8050}` — the default is at the
point of use because the `ENV` default covers *unset*, not *set-empty*.

### 7. `lib/gate_layouts.py` keeps "and the AI assistant" in the demo-branch
gate card

The template retired that phrase in 1.6.16 (`SYNC-1.6.10-1.6.16` item 9) on
the grounds that no fork wires an AI assistant, so the card was selling a
feature that did not exist.

**Why it stays here:** this fork wires one. `docs/ai-agent/ai-agent.md`
declares `endpoint: /ai-agent` and `tier: auth`, so an account genuinely
unlocks it. The item is ported as its CONTRACT — *the gate card promises
only what ships* — rather than as its string fix, and
`tests/test_gate_layouts.py::test_the_gate_card_promises_only_what_this_site_ships`
is what keeps the promise earned: open the page's tier or delete the page
and the test goes red.


### 8. `ci.yml` carries TWO Pythons, and only one of them is the fleet's

`SYNC-1.6.22-1.6.29` item 5 puts ONE Python everywhere it is encoded. This
repo encodes two, deliberately, because it is two things in one tree
(divergence 1):

- the **site lane** — `lint`, `test`, `docs-compat`, `docker`, `pip-audit`,
  `cd.yml`'s verify, and both `release.yml` singletons — is the fleet Python,
  3.14, sourced from the Dockerfile's `FROM` tag. That is the interpreter a
  visitor's request actually runs on.
- the **package lane** — `package-python-range` — is 3.9-3.13, and must NOT
  be the fleet Python. It installs the built wheel on every interpreter
  `pyproject.toml` advertises, which is the only thing that makes
  `requires-python = ">=3.9"` a measurement instead of a claim. Pinning it to
  a container base would fail the moment the image moved and would delete a
  promise this repo publishes on PyPI.

The line is drawn by what each number MEASURES: a singleton
`python-version:` literal measures nothing — it is a choice, and a divergent
choice is exactly the 3.11.8/3.12/3.12.0 drift the item exists to kill — so
every literal in all three workflows is the fleet Python, the wheel-build
jobs included (the wheel is `py3-none-any`). `package-python-range`'s matrix
is the one place a Python asserts something about the world, so
`tests/test_python_version.py` checks it against `pyproject.toml`'s
classifiers rather than against the image.

**Why the site window's floor moved 3.10 → 3.12:** the item holds the
compat window three wide around the fleet minor, and this fork's 3.10 leg
was documented as "the docs site's Python floor". Nothing was lost by
retiring it — the package's 3.9/3.10 support is still measured, by the job
whose whole purpose is measuring it.

**What a sync must not do:** read `3.9`-`3.13` in `ci.yml` as drift and
"restore" it to the fleet Python. Item 5's own contract anticipates this
fork's shape ("a fork adapting this file scopes the greps to its site-lane
jobs"); the scoping lives in `tests/test_python_version.py`'s
`PACKAGE_MEASURED_JOB`.

### 9. `scripts/network_smoke.py` carries an SSL context the template's does not

The fork's `fetch()` builds a certifi-backed `ssl.SSLContext` and passes it
to `urlopen`; template 1.6.29's copy of the same file does not, and calls
`urlopen(req, timeout=timeout)` naked.

**Why:** stdlib on macOS ships no OS trust-store integration, so a naked
`urlopen` dies in the TLS handshake, burns all three retry attempts on it,
and the battery reports a healthy production host as DOWN. `smoke_live.py`
has carried a context since flexlayout found this in the F1 kit adoption
(`154688e`); `network_smoke.py` is the fleet's OTHER live-host reader and
was still naked. `tests/test_network_smoke.py::
test_every_network_smoke_urlopen_passes_the_ssl_context` is the source pin.

**Status:** AHEAD of the template, not divergent from it by intent — filed
upward with this round's report as a template-class finding. A sync must not
restore the naked `urlopen`; when the template adopts the context, this entry
retires.

## Retired

*(none yet — retirements are marked here, not deleted, so that older
reports describing a divergence as live can be reconciled against it.)*

## Byte-owned paths

Paths this fork owns byte-for-byte. The F3b fan-out never overwrites
a path listed here; everything else in the spec's `sync-verbatim`
block is the template's to update mechanically. Prose above explains
divergences; this block is the machine answer.

Repo-relative paths, one per line, `#` comments, no `..`; exactly one
block. An EMPTY block means "the template owns every sync-verbatim
path here" — present so the absence is a statement. When the block
exists it is authoritative; a fork without it gets the conservative
mention heuristic (over-flags, never restores).

RE-AUDITED 2026-08-26 against all three live specs at template 1.6.29,
whose `sync-verbatim` union is now SIX paths — the four from the 1.6.23
audit plus `.github/dependabot.yml` (1.6.24) and `tests/test_auth_demos.py`
(1.6.26). Path by path:

- the three `.claude/skills/*/SKILL.md` and `tests/test_claude_kit.py`:
  byte-identical to template 1.6.23, which is where this fork took them.
  `report/SKILL.md` and `test_claude_kit.py` differ from template HEAD only
  because the TEMPLATE moved at 1.6.28 — this fork has not touched either
  byte, so both are the template's to update mechanically.
- `.github/dependabot.yml`: this fork carries the pre-1.6.24 template
  version, unmodified. It has NO npm block (the component half's
  `package.json` is not under dependabot here), so unlike leaflet there is
  nothing of this fork's to protect — the 1.6.24 rewrite is the fan-out's to
  deliver.
- `tests/test_auth_demos.py`: absent here, and its `# requires:`
  gate (`lib/auth_demos.py`) is satisfied, so the fan-out will deliver it.
  Its two fork-owned seams are in step — `DEMOS` is `endpoint -> {"module":
  ...}` and `conftest.py` exposes `app_module` — so it lands green rather
  than as interface drift.

Divergence 2 makes a byte-level claim on `.claude/CLAUDE.md`, which is not a
`sync-verbatim` path and therefore not an entry here; divergence 9's file is
not one either. The block is empty by decision, not by omission.

```yaml byte-owned
```
