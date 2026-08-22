# Changelog

All notable changes to `dash-excalidraw` are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Site — gate-wave pass (2026-08-21)

The 2plot network's gate/reporter/SEO sync, from
dash-documentation-boilerplate 1.6.4, plus the deployment groundwork this
host had never had. **The documentation site is not affected in anything a
visitor can see: it ships DARK** (`PAGE_DEFAULT_TIER=public`), which means
the gate plumbing goes live and changes nothing. Everything here is the site
under `run.py`; the `dash_excalidraw` package is untouched apart from one
metadata fix.

#### Fixed — mobile

- **The header wordmark overflowed the row on phones.** `dash-excalidraw` is
  a long mark to sit beside a burger, a 36px logo, a search control and the
  theme toggle. It is now `visibleFrom="xs"` — hidden below 576px (36em),
  which covers every phone in portrait. Measured at the boundary: hidden at
  360/414/575px, shown from 576px. `visibleFrom` renders a CSS class rather
  than dropping the component, so the element stays in the DOM: the site's
  name is still in the accessibility tree via the logo's `alt`, and
  `assets/text_animation.js` still finds `#dash-docs-title` to type into.

#### Fixed — the first CI run (round 2)

The first run of the rewritten workflows lost nine checks. Every one was in
the CI configuration; none was in the site. The four pytest legs, lint, and
the Docker build-boot-battery job all passed first time.

- **`scripts/smoke_test.py` did not exist** — six `docs-compat` legs called
  it. Same class as `check_release.py`: the job and its script were both
  leaflet's. Ported; it node-syntax-checks all 23 inline clientside callbacks
  and all four asset JS files, which no pytest can reach.
- **The wheel's packaging-leak check was fooled by its own working
  directory.** `importlib.util.find_spec("lib")` ran in a heredoc whose cwd
  was the repo root, and Python puts the cwd on `sys.path` for a stdin
  script — so it found the repo's own directories and failed on a clean
  wheel. Now a `zipfile` scan of the artifact, plus a clean-venv import run
  from `/tmp`.
- **The docs-compat matrix tested Dash 4.1.0, which this site cannot run
  on.** `run.py` passes `backend=` to the Dash constructor and 4.1.0 rejects
  it during construction. Measured: 4.1.0 cannot boot; 4.2.0, 4.3.0 and
  4.4.1 each pass 48/48. The floor is 4.2.0 and the matrix now says so.
- **`requirements.txt` never carried the `# COMPAT-MATRIX: dash` marker** the
  matrix strips, so the pin was silently reinstated on every leg — a green
  matrix testing one Dash version three times.
- **A failed CI run produced a misleading production failure.** With `deploy`
  skipped, `verify the live site` still ran and failed against production.
  Now gated on the deploy having actually succeeded.

`tests/test_config.py` gains three tests for the class rather than the
instances: every script a workflow runs must exist, no workflow may name
another repo's artifacts in live YAML, and the dash pin must keep its
matrix marker.

#### Fixed — things that would have broken the first deploy

- **The site was on a branch Render does not deploy.** `main` held the
  initial component commit and nothing else; the entire documentation site
  lived on `feat/excalidraw-0.18.1`. `main` is now fast-forwarded onto it —
  no commit rewritten, squashed or dropped.
- **`.github/workflows/cd.yml` deployed and smoke-tested
  `leaflet.2plot.dev`.** It was a copy of that repo's file and had never
  run. Rewritten from the template, which also carries the fix for CD
  verifying the *previous* release whenever the deploy hook is unset — the
  fleet's default configuration.
- **`.github/workflows/ci.yml` and `release.yml` were also leaflet's**:
  package jobs importing `dash_leaflet2`, an image tagged
  `dash-leaflet2-docs`, flake8 pointed at a `usage.py` this repo lacks, a
  missing `scripts/check_release.py`, and `dash-leaflet2` as the PyPI
  trusted-publishing target.
- **The Dockerfile bound a hardcoded port 8550**, which Render (which
  assigns `$PORT`) cannot health-check, and installed nodejs + npm to build
  a bundle that is committed. Rewritten to the fleet shape: python 3.12-slim,
  binds `$PORT`, `WEB_CONCURRENCY`, a 120s timeout for the model calls, no
  Node.
- **`.env.example` documented `CLERK_SATELLITE_DOMAIN=excalidraw.2plot.dev`.**
  Every `*.2plot.dev` docs host is an allowed *subdomain* of the one
  `2plot.dev` satellite; the per-host spelling resolves to NXDOMAIN and hangs
  sign-in with no error.

#### Fixed — SEO and identity regressions

- `twitter:card` had been deleted from `templates/index.html`. Dash declares
  it with `property=` and Twitter's parser reads only `name=`, so no scraper
  could see a card type at all. Restored.
- Three icon links (96/192/512) had been dropped from the head, so it could
  not agree with the crawler head. Restored.
- `msapplication-TileColor` still carried the template's teal against a
  violet `theme-color`.
- The noscript block advertised `/getting-started/llms.txt`, a template page
  this site does not have.

#### Added

- The interactive gate, **dark**: `lib/gate_layouts.py`, `lib/access.py`'s
  two-axis resolution, `lib/page_visibility.py` and the `/admin/control-board`
  page, `lib/agent_key.py` (`/api/agent-key`), `assets/auth_gate.*`.
- `configure_seo` with this site's own seven-icon set, social card and
  publisher/`sameAs`; `SoftwareApplication` on the home page; and truthful
  `lastmod` on all fourteen docs, taken from each file's real last-commit
  date via `git log` — never invented, never from a file mtime.
- `lib/versions.py`, so prose can write `{{VERSION:<dist>}}` instead of a
  number that goes stale.
- `scripts/check_release.py` and `scripts/make_favicons.py`.
- `DEPLOY-READINESS.md` (the owner-side deploy checklist) and
  `X402-SYNC-REPORT.md` (what this pass did, measured).

#### Changed

- **Vendored `dash-clerk-auth` 1.0.0 → 1.0.5**, from the hook repo's `dist/`
  and admitted only on sha256
  `a2f9062e…b74f3`. 1.0.5 is the release that reconciles the *return trip*:
  landing back on a gated page after signing in on the primary used to show
  the gate card until a manual refresh.
- **Security floors**: `clerk-backend-api>=7.0.0,<8` and
  `cryptography>=50.0.0`. The old SDK cap held `cryptography` below the fixes
  for GHSA-537c-gmf6-5ccf and PYSEC-2026-3552/3553/3554; all four now audit
  clean.
- Floors raised: `dash-improve-my-llms[flask]>=2.6.0` (honest sitemap
  `lastmod`, icon autodiscovery), `dash-mantine-components>=2.8.0` (below it
  the mobile drawer renders as a floating card), `plotly>=6.9.0`.
- `lib/satellite_reporter.py` is now **byte-identical** to the template's —
  which is why `run.py` claims `SATELLITE_APP_KEY=excalidraw` via
  `os.environ.setdefault` before any hub-facing import. Without that, an
  unset variable would file this site's traffic under the template's row.
- `/healthz` reports `build` (the running instance's commit) alongside the
  existing `app`, so CD can verify the artifact it shipped.
- `render.yaml` fully authored for Docker + the 1 GB `/var/data` disk, and
  deliberately declares **no** env-group-owned variable — a service-level
  copy would shadow the group and mask future edits.
- `dash_excalidraw/package-info.json` advertised
  `@excalidraw/excalidraw ^0.17.6` while the bundle is built from 0.18.1.


### Security

- **Repository history starts clean.** The project had never been committed to
  any git repository. Before the first commit, the live `ANTHROPIC_API_KEY` and
  `GEMINI_API_KEY` that lived in the untracked `.env` were rotated at their
  providers, `.env.example` was authored with names only, and the first commit
  was gated on three checks: `.env` absent from the staged set, a secret-pattern
  scan over every staged file, and a review of the staged tree for build
  directories. No key has ever entered this history.

- **`dash_excalidraw/dash_excalidraw.js` contains a `AIzaSy…` string, and that
  is expected.** Secret scanners pattern-match it as a Google API key. It starts
  `AIzaSyAd15pYlMci_` (truncated here on purpose, so this file does not itself
  become a second scanner finding) and appears three times inside the
  `VITE_APP_FIREBASE_CONFIG` literal that upstream Excalidraw bakes into its own
  published `dist/` (`authDomain: excalidraw-room-persistence.firebaseapp.com`).
  It belongs to the Excalidraw project, not to this one, and a Firebase **Web**
  API key is a public client-side identifier by design — access is enforced by
  Firebase Security Rules, not by keeping the key secret. It is bundled verbatim
  by webpack from `node_modules/@excalidraw/excalidraw/dist/`, so any finding
  against it is **dismissed deliberately** as a third-party public identifier.
  **Do not re-litigate this**, and do not "fix" it by stripping the string —
  that would fork upstream's bundle. Note that upstream's *development* builds
  carry a second such key (`AIzaSyCMkxA60XIW8Kbq…`); webpack's production build
  does not include it.

  Measured on the first push (2026-08-08): GitHub push protection did **not**
  block it. Treat that as unverified rather than as proof the string is
  ignorable — enable Secret scanning + Push protection under Settings →
  Advanced Security, dismiss the resulting alert as a false positive, and expect
  a future bundle-touching push to need an explicit bypass.

### Changed

- `.gitignore`: `.claude/` and `.idea/` are now ignored wholesale; the built bundle
  `dash_excalidraw/dash_excalidraw.js` is now **tracked** rather than ignored
  (the release gate reads its commit timestamp, and tracking keeps
  `pip install git+…` working without npm); `dash_excalidraw/metadata.json`,
  a `dash-generate-components` byproduct that must not ship in the wheel, is
  now ignored.

### Added

- `.env.example` documenting `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` and the
  `GOOGLE_API_KEY` fallback, read out of `pages/ai_agent.py` rather than out of
  `.env`. Nothing in the showcase requires a key; every AI provider degrades to
  a disabled state when its key is absent.

## [0.1.0] — unreleased

Ground-up TypeScript rebuild of the component. See `REBUILD.md`.
