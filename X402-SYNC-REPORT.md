# x402 / network sync report — excalidraw

This repo had no report file before this pass; it had never run a network
sync, and it had never deployed.

## gate-wave

date: 2026-08-21
repo: dash-excalidraw (excalidraw.2plot.dev)
matrix_row: "Batch 1 — dash-excalidraw | Clerk env block; hub
  redirect-allowlist gap" — with EXTENDED SCOPE, because this host has
  never deployed.
source_template: dash-documentation-boilerplate 1.6.4 (6d1e0bd)
head_sha: (this commit, on main)
posture: DARK (PAGE_DEFAULT_TIER=public). NOT flipped, and not deployable
  from here — the owner-side steps are DEPLOY-READINESS.md.

### STEP 0 — repo state found, and what was kept

The 2026-08-16 fleet survey recorded "excalidraw: the site on a branch
Render does not deploy". Confirmed exactly, and worse than it sounds:

  found:
    main: 2 commits — the initial 0.1.0 component rebuild and one
      CHANGELOG commit. NO documentation site at all.
    feat/excalidraw-0.18.1: 12 further commits carrying the entire site
      (the boilerplate restructure, brand assets, the AI agent page, the
      benchmark page, the background-callback work).
    uncommitted: requirements.txt edited to vendor dash_clerk_auth 1.0.2
      + the two security floors; vendor/1.0.0.tar.gz deleted from the
      worktree; vendor/1.0.2.tar.gz untracked.
    relationship: main was a strict ANCESTOR of the branch — no
      divergence, so no merge decision to make.
  kept:
    everything. `git merge --ff-only` fast-forwarded main onto the
    branch. No commit was rewritten, squashed or dropped.
  discarded:
    only the in-flight 1.0.2 vendoring, which the handbook supersedes:
    the floor is 1.0.5. The requirements edit's SECURITY half was
    re-applied verbatim (it was already correct) and the tarball went
    straight to 1.0.5.
  reconciled_to: a clean, committed main. `git status` is empty.
  still_owner_side: main is 14 commits AHEAD of origin/main. Pushing is
    outside a checkout's authority and is checklist item 0.

### Acceptance

  satellite_reporter_shasum:
    boilerplate: a4ebbf26d8dd1ed9f45e3d81f95982d83e639348b722c2602c755be095b6ff2d
    excalidraw:  a4ebbf26d8dd1ed9f45e3d81f95982d83e639348b722c2602c755be095b6ff2d
    verdict: MATCH (byte-identical)
  vendored_clerk:
    file: vendor/dash_clerk_auth-1.0.5.tar.gz, from the hook repo's dist/
    sha256: a2f9062e15a69fc79deeaf76fcf1380907a961978db558b2aa227572cb2b74f3
    verdict: MATCH the handbook's required hash. Verified BEFORE the copy,
      and the copy refused on mismatch. vendor/1.0.0.tar.gz was git rm'd —
      the directory holds exactly one tarball.
  security_floors: clerk-backend-api>=7.0.0,<8 and cryptography>=50.0.0,
    resolved live (7.0.0 + 50.0.0 install together cleanly) and MEASURED:
    pip-audit now reports zero advisories against either package. The four
    that motivated the floor (GHSA-537c-gmf6-5ccf, PYSEC-2026-3552/3553/
    3554) are closed.
  tests: 328 passed (was 226 at the start of the pass)
  flake8: clean over lib components pages tests scripts run.py docs
  boot_guards (production-shaped local boot, DASH_BACKEND=flask):
    interactive_gate_line: PRESENT —
      "[boilerplate/excalidraw] interactive gate: default tier 'public',
       2 non-public page(s), machine surfaces open by default
       (LLMS_PUBLIC_DEFAULT), access wiring ON, control board at
       /admin/control-board (0 live override(s))."
    visibility_warning: ABSENT
    auth_warning: ABSENT
    guards_proven_live: all three states were forced and all three fired —
      [visibility] with PAGE_VISIBILITY_FILE unset; [auth] with satellite
      mode and CLERK_SATELLITE_SIGN_IN_REDIRECT unset; [auth] again with
      it set to the non-URL `true`. The absences above are a pass, not a
      dead check.
  clerk_wiring (booted with satellite Clerk configured):
    _dash-layout carries clerk-user-avatar / clerk-login-button /
    clerk-logout-menu-item, exactly one avatar id; the served index
    carries both index-hook delegates, data-clerk-publishable-key and
    buildSatelliteRedirect; /api/agent-key answers 204 anonymous.

### File set delivered

  new: lib/agent_key.py, lib/auth_demos.py, lib/gate_layouts.py,
    lib/page_visibility.py, lib/versions.py, pages/control_board.py,
    assets/auth_gate.js, assets/auth_gate.css, scripts/make_favicons.py,
    scripts/check_release.py, and tests test_agent_key_route /
    test_control_board / test_gate_layouts / test_network_directory /
    test_satellite_presence / test_seo_icons / test_traffic_rollup
  byte_copied: lib/satellite_reporter.py, lib/network_directory.py,
    lib/auth.py, lib/access.py, lib/page_tiers.py, lib/traffic_rollup.py,
    pages/markdown.py, assets/llms_copy.js, tests/conftest.py,
    tests/test_social_card.py, scripts/smoke_live.py (now byte-identical
    to the template's again)
  merged_not_copied: run.py, components/header.py, components/navbar.py,
    lib/constants.py, lib/ad_client.py, lib/health.py, assets/main.css,
    templates/index.html, render.yaml, Dockerfile, .env.example,
    requirements.txt, tests/test_access.py, tests/test_bulletin.py,
    tests/test_site_identity.py — each carries per-site identity or
    per-site tests a byte-copy would have destroyed.
  left_alone_because_this_repo_is_AHEAD: lib/hub_client.py ("excalidraw"
    key), lib/asgi_routes.py, and the whole component/wheel tree.

### The six read-first additions — all six landed

  1. control board + lib/page_visibility.py + the conftest tmp-store line
     (conftest was byte-copied; the template's /admin exclusion in the
     `pages` fixture came with it, which is what four failing sweeps were
     asking for).
  2. network-standard mobile drawer — ALREADY PRESENT and correct
     (create_mobile_content, create_navbar_drawer, HEADER_HEIGHT, the
     mobile-select→url and State-based burger callbacks). Only the section
     ORDER was synced (own-work above third-party; Resources last).
  3. aria-labels on every icon-only control; create_link now REQUIRES a
     label. `title=` audit: 8 call sites, all `dmc.Alert(title=)` or
     `dmc.Drawer(title=)` — real props on those components, not the HTML
     attribute. No ActionIcon/Anchor takes one. Not a boot-killer here.
  4. ad image aspectRatio box reservation.
  5. lib/auth.py's `_install_signout_delegation` + both redirect boot
     guards (arrived with the byte-copy; verified firing).
  6. lib/auth_demos.py.

### FORK POINT

  run.py claims `os.environ.setdefault("SATELLITE_APP_KEY", "excalidraw")`
  before any hub-facing import, and three tests pin it: the line exists,
  it precedes the first-party imports, and render.yaml still declares
  `value: excalidraw`. The byte-copied reporter keeps its "boilerplate"
  fallback, which is the whole point.

### Identity — NOT blocked on art (the caveat did not hold)

  The brief said: no `<app>.png` on the CDN, repo never favicon-audited,
  so BLOCK ON ART unless the repo has its own mark.

  It has its own mark. `assets/excalidraw-mark.png` (32218 B) and
  `assets/excalidraw-mark-144.png`, generated by this repo's own
  `scripts/make_brand_assets.py`, plus a full 8-file favicon set derived
  from it. All nine files were byte-compared against the template's and
  all nine DIFFER. `site.webmanifest` names this app in all three fields.
  So the identity half was NOT blocked and did not need to be deferred.

  ordering_rule: SATISFIED WITHOUT A SWAP — the pixels were verified
    distinct from the template's BEFORE the dimll floor moved to 2.6.0, so
    2.6's icon autodiscovery cannot cement the wrong mark here.
  root_icon_trap: N/A. The one `apple-touch-icon.png` reference
    (templates/index.html) already points at /assets/favicon/, and no root
    assets/apple-touch-icon.png exists.
  added: configure_seo (the seven-icon block + social card +
    publisher/same_as), PUBLISHER + SAME_AS in lib/constants.py,
    schema_type="SoftwareApplication" on the home page, and `lastmod` on
    all 14 docs taken from each file's REAL last-commit date via
    `git log -1 --date=short` — never invented, never from mtime.
  UNVERIFIABLE FROM HERE: the og-card object at
    cdn.2plot.ai/github_assets/excalidraw.2plot.dev.png. No network
    egress during this pass. Checklist item 9.

### Defects found and fixed that were NOT in the brief

  1. **cd.yml deployed and smoke-tested the WRONG HOST.** It was leaflet's
     file: `SITE_URL` defaulted to `https://leaflet.2plot.dev` and the
     production environment URL said the same. Rewritten from the
     template, which also brings the muicharts build-match fix (the old
     shape gated its wait on the deploy hook, so with the hook unset —
     which is the fleet default — it verified the PREVIOUS release,
     invisibly, on every run).
  2. **ci.yml was leaflet's too, and had never run.** Package jobs
     imported `dash_leaflet2` and built Leaflet layouts; the image was
     tagged `dash-leaflet2-docs`; flake8 targeted a `usage.py` this repo
     does not have; `scripts/check_release.py` was referenced and did not
     exist. All rewritten for this repo, and check_release.py written.
  3. **release.yml named `dash-leaflet2`** as the PyPI trusted-publishing
     project and environment URL.
  4. **The Dockerfile could not serve on Render.** It hardcoded
     `-b 0.0.0.0:8550` and Render assigns `$PORT`. It also installed
     nodejs + npm and ran `npm install` — the whole Excalidraw/webpack/
     TypeScript toolchain baked into a production image that never runs a
     line of it, since the bundle is committed. Rewritten to the fleet
     shape (python:3.12-slim, binds $PORT, WEB_CONCURRENCY, 120s timeout
     for the model calls, no Node).
  5. **`twitter:card` had been deleted from templates/index.html.** Dash
     declares it with `property=` and Twitter's parser only reads
     `name=`, so with the static tag gone no scraper could see a card
     type at all. Restored, with the template's rationale.
  6. **Three icon links had been dropped from the head** (96/192/512), so
     the browser head could not have been set-equal to the configure_seo
     list this pass added. Restored.
  7. **`msapplication-TileColor` still said the template's teal** while
     `theme-color` had been changed to violet.
  8. **The noscript block advertised `/getting-started/llms.txt`** — a
     template page that does not exist here. Repointed at `/basic`.
  9. **`.env.example` set `CLERK_SATELLITE_DOMAIN=excalidraw.2plot.dev`.**
     That is the mistake render.yaml's comment exists to prevent:
     `clerk.excalidraw.2plot.dev` is NXDOMAIN and sign-in hangs with no
     error. Corrected to `2plot.dev`, along with `CLERK_SIGN_IN_URL`
     (`2plot.ai` → `accounts.2plot.ai`).
  10. **`dash_excalidraw/package-info.json` advertised
      `@excalidraw/excalidraw ^0.17.6`** while package.json builds 0.18.1
      — i.e. the SHIPPED package named the pre-upgrade version. Found by
      the new check_release.py on its first run; aligned.
  11. **`/benchmark` was missing from test_pages.py's REQUIRED_PATHS** —
      the page postdates the test.
  12. **Five flake8 findings** in files CI had never linted
      (lib/background.py, lib/scene_ai.py, tests/test_llms_routes.py,
      tests/test_usage.py).

### Deviations

  1. Gate boot line is prefixed `[boilerplate/excalidraw]`, matching the
     handbook's literal acceptance string and pannellum's precedent,
     rather than this repo's other prints which say `[boilerplate]`.
  2. `tests/test_bulletin.py`'s identity assertions were rewritten to
     pannellum's shape: the byte-copied reporter genuinely defaults to
     "boilerplate", so "all four agree with the env unset" became false.
     Rather than weaken the guard or edit a file whose shasum is an
     acceptance check, the guarantee moved to run.py's setdefault and
     three tests pin it.
  3. `tests/test_network_directory.py::test_this_app_is_not_its_own_peer`
     was made conditional. The canonical PEERS list deliberately omits
     this host until it deploys, so the template's "the self-filter
     removed exactly one" assertion cannot hold. The invariant (a site is
     never its own peer) still holds unconditionally, the spelling check
     switches on automatically once the entry lands, and a companion test
     `test_this_host_is_queued_for_registration` makes the absence a
     recorded decision rather than an oversight — it fails the moment the
     entry is added, which is the reminder to delete it.
  4. `lib/health.py` was MERGED, not copied. This repo's payload carries
     an `app` field the template's lacks (it answers "green as whom?");
     the template's 1.6.4 adds `build` for the CD artifact match. Both
     kept.
  5. Two copied tests carried template-only page paths and were repointed
     at this site's pages: test_access.py `PUBLIC_PAGE` "/backends" →
     "/commands", and test_network_directory.py "/networks/llms.txt" →
     "/basic/llms.txt". A 404 emits no canonical tag, so the key-leak
     assertions would have passed vacuously.
  6. `scripts/check_release.py` was written for this repo rather than
     ported from leaflet's — the two repos have different version-source
     layouts (no root package-info.json here), and it gained an
     Excalidraw-pin check that immediately found defect #10.
  7. pip-audit stays ADVISORY, against the handbook's "flip it once the
     baseline is quiet". The baseline is NOT quiet and the reason is
     recorded in ci.yml: `diskcache` 5.6.3 carries PYSEC-2026-2447 with
     NO fix version published, so gating today means a permanently red
     required check. The floors this pass added did work — cryptography
     and clerk-backend-api audit clean.

### Not done here — owner steps, see DEPLOY-READINESS.md

  - Push main (14 commits ahead of origin/main).
  - Create the Render service; verify the disk ATTACHED, not just declared.
  - Link env groups A/B/C, then set the per-service identity vars.
  - The declared-vs-live env diff.
  - DIRECTORY + HUB REGISTRATION, flagged as the brief asked: this host is
    deliberately absent from the canonical network directory, absent from
    the hub's PULSE_POLL_TARGETS, and absent from
    `CLERK_ALLOWED_REDIRECT_ORIGINS` on 2plot.ai (re-verified against
    origin/main 2ebbed4). The last of those is a hard flip blocker — a
    host missing from it signs users in and strands them on 2plot.ai —
    and so is the Clerk dashboard's allowed-subdomain list.
  - One real sign-in round trip.
  - The PAGE_DEFAULT_TIER=auth flip.

### Open questions

  - The og-card CDN object could not be fetched (no egress). If it is
    absent, every share renders blank; scripts/make_social_card.py builds
    one and the upload is manual.
  - `lib/constants.SAME_AS` and release.yml both assume
    pypi.org/project/dash-excalidraw exists. If the package is not
    published, the JSON-LD `sameAs` names a 404.
  - CI has never executed on this repo. Everything above is locally
    verified; the first CI run is the first independent proof.
