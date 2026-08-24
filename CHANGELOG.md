# Changelog

All notable changes to `dash-excalidraw` are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Site — floor round (2026-08-23)

Moves to `dash-improve-my-llms >= 2.7.1` and syncs four template fixes from
dash-documentation-boilerplate 1.6.9-1.6.13.

#### Changed

- **dimll floor 2.6.1 → 2.7.1**, in all six places it is encoded:
  requirements.txt (the pin and the three commented backend extras), run.py's
  `LLMS_PKG_FLOOR` and its boot message, and ci.yml's extras install plus both
  version asserts. 2.7.0 dedups the prerender H1 and the home footer's doubled
  `/llms.txt` link, and hardens the idempotency probe so a page that merely
  MENTIONS the marker keeps its prerender; 2.7.1 adds the llms.txt v2
  discovery relations and Link headers, the `Accept: text/plain` ramp, and the
  representation digest. **Editing the requirements line is the Docker cache
  bust** — that layer re-runs only on a byte change, so a `>=` floor can never
  pull a newer release through a cache hit.
- **`/healthz` is built per request, from one payload, on every backend.** It
  was a snapshot closed over at registration — harmless while every field was
  static and wrong the moment one is not. FastAPI built its own payload
  *without* `build`, which is the exact field cd.yml's build-match wait polls
  for, so a FastAPI deploy would have verified whichever release happened to
  be serving. The payload gains `app` (`SATELLITE_APP_KEY`, else `"unknown"`)
  and, on dimll >= 2.7.0, `geo` `{configured, denied, resolved}` — counts and
  flags only, never the denylist's country codes, and omitted rather than
  error-flagged on older packages.
- **`_expand_source_directives` is fence-aware.** A `.. source::` inside a
  fenced block is documentation showing the syntax, not a directive; expanding
  it injected a fence inside the open fence, closed it early, and rendered the
  inlined Python as markdown — every `# comment` becoming an `<h1>`. Latent
  here (no doc teaches the directive yet) and fixed before it could bite.
- **Dependabot pip version-updates restricted** to `dash*` / `plotly*` /
  `markdown2dash`. Without the allow-list it proposes floor-raises for every
  requirement, and those floors encode minimum-compatibility knowledge — the
  gunicorn floor *is* the CVE fact. Security updates are unaffected; they
  arrive through a separate channel.

#### Fixed

- **The noscript block carried an `<h1>`, so every page served two.** Crawlers
  run no JavaScript but do parse `noscript`, making it a second site-wide h1
  competing with each page's own. Found by the every-page structure pin the
  moment it was ported. The block now starts at h2.

#### Added

- The every-page structure pin: every non-admin page serves exactly one `<h1>`
  to a generic client (comments stripped first), no duplicate llms.txt links
  in the prerender footer, and home carries the root link exactly once.
- Four healthz contract tests, the fence-awareness test, and the noscript pin.
- The Dockerfile's cache-semantics block, plus `curl` and a `$PORT`-aware
  HEALTHCHECK.

### Site — round-2 pass (2026-08-22)

Follow-ups from the gate-wave review, an outside SEO audit, and the
dash-improve-my-llms 2.6.1 pickup.

#### Fixed

- **The home link had no accessible name on phones.** Below 576px the
  wordmark is `display: none` (that is what `visibleFrom` compiles to), and a
  display:none subtree is removed from the accessibility tree entirely — so
  with a decorative logo beside it the branded header link announced as just
  "link", with nothing saying where it goes. The gate-wave report claimed
  `visibleFrom` "stays in the accessibility tree"; **that was wrong**, and the
  report has been corrected. The anchor now carries a permanent `aria-label`
  and the logo is explicitly decorative (`alt=""`) so the two do not compete
  for the accessible name — template 1.6.6's pattern.
- **The meta description was 270 characters.** Google truncates around
  155-160 and, for a description it judges unrepresentative, rewrites the
  snippet from page text — so an over-long one forfeits the snippet rather
  than shortening it. Now 153, in `lib/constants.SITE_DESCRIPTION`, with
  index.html's JSON-LD copy kept in step.
- **The meta keywords still described the template.** The tag shipped naming
  Dash Mantine Components, markdown docs and developer tools — the one tag
  that states outright what a site is about never once mentioned Excalidraw.
  Replaced with terms for the component.

#### Changed

- **`lib/network_directory.py` re-copied verbatim from the boilerplate.**
  Template 1.6.5 added `excalidraw.2plot.dev` and `modelviewer.2plot.dev` to
  the canonical list now that both are live. `test_this_host_is_queued_for_registration`
  fired on the re-copy exactly as it was designed to, and is replaced by two
  tests that pin the steady state: the self-filter removes exactly one row
  (which proves the spelling), and this host's row exists at the source
  (which a healthy self-filter would otherwise hide).
- **dimll floor 2.6.0 → 2.6.1**, in requirements (including the commented
  backend extras), `run.py`'s boot floor and its message, and CI's two
  version fingerprints. 2.6.1 makes the universal prerender visible to non-JS
  consumers: below it the injected block carries a literal `hidden`
  attribute, so every visibility-respecting reader saw "Loading..." and
  nothing else. A `>=2.6.0` build resolves 2.6.1 today, but that is
  resolution luck rather than a guarantee — the floor is stated where the
  guarantee is. Verified by downgrading: on 2.6.0 the new generic-lane test
  fails on the `hidden` attribute and the boot floor refuses to start.

### Site — gate-wave pass (2026-08-21)

The 2plot network's gate/reporter/SEO sync, from
dash-documentation-boilerplate 1.6.4, plus the deployment groundwork this
host had never had. **The documentation site is not affected in anything a
visitor can see: it ships DARK** (`PAGE_DEFAULT_TIER=public`), which means
the gate plumbing goes live and changes nothing. Everything here is the site
under `run.py`; the `dash_excalidraw` package is untouched apart from one
metadata fix.

#### Fixed — mobile

- **The home page scrolled sideways on phones.** The prop-mapping table is
  min-content sized, so with `overflow: visible` it burst out of its column
  and dragged the document with it: measured at 414px, the table rendered
  471px inside a 318px container and the page scrolled 105px horizontally, so
  every paragraph could be swiped off-screen. Markdown tables now scroll
  inside their own box (`display:block` + `width:max-content` +
  `max-width:100%` + `overflow-x:auto`) — a no-op above the container width,
  so desktop is unchanged. `dmc.Table` (which /file-uploads renders, and
  which has its own scroll container) is explicitly excluded.
- **/ui-options scrolled sideways too**, by 15px: a Switch labelled
  `canvasActions.changeViewBackgroundColor` — a dotted identifier with no
  break opportunity — rendered 309px wide in a 250px box. Control labels in
  the docs bodies now use `overflow-wrap: anywhere`.
- **All fifteen pages now measure zero horizontal overflow at 414px.**
- **Three stylesheet rules targeted Mantine's internal hashed class names**
  (`.m_46b77525`, `.m_5caae85b`, `.m_9cdde9a`). Those hashes are private,
  version-unstable build artifacts. Audited against DMC 2.8: `.m_5caae85b`
  had already gone dead (zero occurrences in the bundle), and `.m_9cdde9a`
  was putting a stray `margin-top: 15px` on the AppShell aside while
  re-declaring width, transform and z-index that Mantine already sets. The
  header-Select rule was rewritten against a stable selector; the other two
  are gone. This is the failure 2plot_leaflet recorded after a `.m_b8a05bbd`
  rule — the Drawer content — silently overrode its drawer's docking styles
  and left that host's mobile navigation floating. A test now fails on any
  `.m_*` selector in any stylesheet.


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
