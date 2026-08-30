# dash-excalidraw — Claude Code Project Guide

## Project overview

This repo is **two things in one tree**, and most confusion here comes from
forgetting which half you are in:

1. **The component.** `dash-excalidraw` wraps the
   [Excalidraw](https://excalidraw.com/) React canvas as a
   [Dash](https://dash.plotly.com/) component, published to PyPI as a wheel
   shipping `dash_excalidraw/dash_excalidraw.js` (webpack) and
   `DashExcalidraw.py` (`dash-generate-components`). See
   [`REBUILD.md`](../REBUILD.md) for the rationale behind the prop surface.
2. **The documentation site.** `run.py` serves
   <https://excalidraw.2plot.dev>, a satellite of the 2plot network forked
   from `dash-documentation-boilerplate`. Docs live in `docs/`, the shell in
   `components/` + `pages/`, the network machinery in `lib/`.

The two halves share a repo and almost nothing else. A change to `src/ts/`
needs an `npm run build` and a wheel; a change to `docs/` needs a deploy.
Versions and dependency floors are deliberately not restated here — they go
stale. Read `requirements.txt`, `package.json` and `CHANGELOG.md`.

## Project structure

```
dash-excalidraw/
├── .claude/                     # this kit (see "Network role" below)
│
│   # ── the component ────────────────────────────────────────────────
├── dash_excalidraw/             # Python package shipped to PyPI
│   ├── DashExcalidraw.py        # GENERATED — do not hand-edit
│   ├── dash_excalidraw.js       # webpack output; TRACKED, not ignored
│   ├── helpers.py               # decode_data_url / strip_inline_files / …
│   ├── dash_prop_typing.py      # type overrides for the generator
│   └── package-info.json        # metadata read by __init__.py
├── src/ts/components/DashExcalidraw.tsx   # the only component
├── webpack.config.js            # ESM-friendly for Excalidraw 0.18
├── examples/                    # standalone runnable examples (ai_colab)
│
│   # ── the documentation site ───────────────────────────────────────
├── run.py                       # app entry: fork point, floors, SEO, gate
├── docs/<page>/<page>.md        # one folder per page + its example modules
├── pages/                       # home.py, markdown.py, control_board.py
├── components/                  # appshell, header, navbar, backend_badge
├── lib/                         # health, access, page_visibility, …
├── templates/index.html         # meta tags, JSON-LD, noscript lane
├── scripts/                     # smoke_live, network_smoke, check_release …
├── Dockerfile, render.yaml      # production image + Render blueprint
│
├── tests/                       # pytest — both halves
├── DIVERGENCES.md               # deliberate differences from the template
└── DEPLOY-READINESS.md          # owner-side deployment checklist
```

## The component half

### Prop surface philosophy

- **Every prop must be JSON-serializable.** Functions, RegExps and class
  instances cannot cross the Python/JS bridge. If you are tempted to add a
  `func` prop, stop and reach for one of the two patterns below.
- **Events → snapshot props.** Anything Excalidraw emits as a callback
  (`onPaste`, `onPointerUpdate`, `onScrollChange`, …) becomes a
  `last<Event>` prop written via `setProps`. Each snapshot carries a
  `timestamp` so Python-side code can dedupe.
- **Imperative actions → command dispatch.** A `command` prop accepts
  `{id, type, payload}`. The TS side dispatches once per unique `id`, then
  calls `setProps({command: null})` to clear it. Responses for async actions
  (exports) flow back via `lastExport`, keyed by the same `id` the caller
  dispatched.

### File externalization (images)

Excalidraw's `files` map holds every pasted/dropped image as a base64
`dataURL`. Leaving them inline bloats `serializedData` by orders of
magnitude. Reach for these three before considering a fork:

- **`lastFileAdded`** (output) — fires once per new inline file:
  `{timestamp, fileId, mimeType, dataURL, size}`. Push the bytes to storage
  from a callback here.
- **`replaceFiles`** (command) — payload `{[fileId]: {dataURL, mimeType?}}`,
  calls `api.addFiles` with matching ids so Excalidraw's copy is overwritten
  in place and the old base64 is GC'd.
- **`externalizedSerializedData`** (output) — `serializedData` with every
  remaining `data:` URI stripped to `null`. **Persist this one.**

Python helpers live in `dash_excalidraw/helpers.py` (`decode_data_url`,
`strip_inline_files`, `restore_inline_files`) — pure-Python, dependency-free,
re-exported from the top-level module. The reference demo is
`docs/file-uploads/`.

Intentional non-goals: the component never makes the network call, there is
no `lastFileRemoved`, no automatic resize/recompress, and CORS is the user's
problem when serving from another origin.

### Rule of hooks / SSR guard

Excalidraw requires `window`. The component gates render with a mounted flag:

```tsx
const [isMounted, setIsMounted] = useState(false);
useEffect(() => { setIsMounted(true); }, []);
if (!isMounted) return <div id={id} style={{width, height}} />;
```

Never early-return before the hooks — React 18.3 warns loudly in dev.

### Python stub vs. generator

`dash_excalidraw/DashExcalidraw.py` is hand-written *and* regenerated by
`dash-generate-components`. When you edit the TSX prop signature: update the
TS `Props` type, run `npm run build:backends` (or `npm run build` for the
full chain), and commit both. The hand-written stub exists so the app imports
before you have run the JS build — don't let it drift from the generator's
output.

### Component gotchas

- **`initialData` is mount-only.** Excalidraw owns the scene after mount —
  use `command: updateScene` or `command: resetScene`, never "set
  initialData from a callback".
- **Commands need unique ids.** The same `{id, type}` twice is a no-op on the
  second dispatch. Use `uuid.uuid4()` or a counter.
- **`lastExport` carries the id you dispatched.** Async exports can arrive
  out of order — match on the id, don't assume the latest is yours.
- **`validateEmbeddable` accepts strings only from Python.** The TS side
  compiles them to case-insensitive RegExps. Write `"*.youtube.com"`, not a
  full regex.
- `webpack.config.js` sets `resolve.conditionNames` and the `.m?js` rule
  specifically for Excalidraw 0.18's ESM exports. "Cannot find module
  '@excalidraw/excalidraw'" at build time — check those first.

## The documentation-site half

| File | Purpose |
|------|---------|
| `lib/constants.py` | Brand, description, `BASE_URL` — the identity source |
| `run.py` | Fork point (`SATELLITE_APP_KEY`), dependency floors, SEO, gate |
| `assets/main.css` | Custom CSS. Never style through hashed `.m_*` classes |
| `templates/index.html` | Meta tags, JSON-LD, the noscript machine lane |
| `components/navbar.py` | Navigation order + the full-height mobile drawer |
| `pages/control_board.py` | `/admin/control-board` — per-page tier + llms toggles |
| `lib/page_visibility.py` | The board's override store; beats frontmatter |
| `lib/auth_demos.py` | The live teaser rendered inside sign-in gate cards |

### Adding a documentation page

Create `docs/my-thing/my-thing.md` with frontmatter (`name`, `description`,
`endpoint`, `icon`, optional `tier: auth`, `lastmod`), then reference example
modules with `.. exec::docs.my-thing.example`. The page auto-registers.
Directives: `.. toc::`, `.. exec::`, `.. source::`, `.. kwargs::`,
`.. llms_copy::`.

### Setup and running

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev,demo]' && pip install -r requirements.txt
npm install                     # only if you are touching src/ts/
npm run build                   # webpack + dash-generate-components
python run.py                   # the docs site on :8050
pytest tests/ -v && flake8
```

## Agent reference

| Agent | Purpose |
|---|---|
| `debugger` | JS build errors, Dash callback errors |
| `architect` | Design decisions — consult before extending the prop surface |
| `reviewer` | Code review against the conventions above |
| `tester` | pytest + Jest |
| `housekeeper` | Self-maintenance of `.claude/` after a dev session |

Skills live in `.claude/skills/`. The three network skills below ship with
this kit; `/doc`, `/review`, `/status` and `/test` are this repo's own.

---

## Network role & the behavioral contract

This repo is a member of the 2plot network — either the template
itself (dash-documentation-boilerplate) or a fork of it serving one
component's documentation. **Identity derives from the repo, never
from this file**: the app key comes from `SATELLITE_APP_KEY` and
run.py's fork point, the host from `lib/constants.py`'s `BASE_URL`,
the deliberate differences from the template from `DIVERGENCES.md`
at the repo root. If those disagree with anything written here,
they win.

### The contract — every session, every prompt

1. **Check the prompt against this tree before executing.** Prompts
   are written from the template's perspective and your fork may
   legitimately differ — floors, backends, payload shapes, page
   sets. A prompt step that doesn't fit this repo is a finding to
   return, not an instruction to force.
2. **Corrections are your job, not scope creep.** If a prompt's
   reference list doesn't match its steps, if its assumed state is
   wrong, or if executing it as written would produce a
   green-but-vacuous result, say so and propose the corrected
   version before running it.
3. **Verify your own deploy on the wire before reporting.** A push
   is not a result. Run `/wire-verify` (or its manual equivalent)
   against production and paste what came back. If your sandbox
   cannot reach your own domain, say exactly that — an unverified
   claim marked as unverified is honest; the same claim unmarked is
   not.
4. **Report observed versus expected, with evidence.** Paste the
   JSON, the status code, the test count. "Should work" and summary
   claims without artifacts are not reports.
5. **Divergence is legitimate when written down.** Before syncing
   template changes, read `DIVERGENCES.md`; never let a sync
   "restore" a recorded deliberate difference. When you deliberately
   diverge, record it there in the same commit — an unrecorded
   divergence is indistinguishable from drift and will be treated
   as drift.
6. **Never touch**: environment variable VALUES, hosting dashboards,
   secrets, other repos' trees, or anything the prompt didn't put in
   scope. Enumerate what you cannot do (closing PRs, dashboard
   steps) for the owner instead of claiming it done.

### Verification traps (fleet-learned, keep them)

- A `>=` floor can never pull a new release through a Docker cache
  hit — the requirements line changing IS the cache bust, and floors
  live in several encodings (requirements, run.py's boot floor,
  tests, CI): grep the number, move every one.
- `/healthz` build == HEAD is the deploy proof; a missing geo block
  on dimll ≥2.7 means the cache trap fired (unless DIVERGENCES.md
  says this host's healthz is deliberately minimal).
- Probe with GET, not HEAD — HEAD responses omit the Link headers.
- Run-watchers keyed on a commit sha can match Dependabot's runs on
  the same sha — key on the workflow path (cd.yml) instead.
- The browser lane and the machine lane are different documents;
  a fix proven on one is unproven on the other.
- There is ONE classifier: `dash_improve_my_llms.classify()`. Never
  add a User-Agent list to this app — the tracker had one for a year
  (`lib/analytics_tracker.py`, until 1.6.34), it filed ClaudeBot as
  *search* (it is Anthropic's training crawler; the package's registry
  and this repo's own `run.py` comment both said so six lines from
  where the list ignored them), it still named the retired
  `anthropic-ai` / `claude-web` tokens, and it counted every UA-less or
  library client as a human. Every host in the fleet reported those
  numbers. A token the registry lacks is a pushback to the package
  seat, not a list here; `tests/test_analytics_classifier.py` greps the
  module for the old tokens and goes red if one comes back.
- `build == HEAD` on `/healthz` means HEAD of **`release`**, not main
  (1.6.35). Render deploys `release`; only cd.yml's `deploy` job writes
  it, fast-forward, after the CI matrix is green. `main` ahead of
  `release` is an uncertified push pending — its CD run is red or still
  running — never "drift" and never a reason to deploy by hand or to
  write `release` yourself (a non-fast-forward push fails the next run
  on purpose). Compare the wire against `git rev-parse origin/release`;
  the one measurement behind this: 2026-08-29 14:12Z, de0bcff pushed
  to main on the template, built by Render inside the minute, red in CD
  at 14:13Z, served for ~6 minutes. A host whose DIVERGENCES.md posture
  fence has no `deploy:` key still watches main — there the trap is the
  old one.
