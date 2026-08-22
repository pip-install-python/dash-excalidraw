# DEPLOY-READINESS — excalidraw.2plot.dev

**This host has never deployed.** The repo half of the gate-wave pass is
complete (see `X402-SYNC-REPORT.md`); everything below is owner-side and
cannot be done from a checkout. Work top to bottom — the ordering is
load-bearing in three places, each flagged.

Nothing here is optional-but-nice. Every unchecked box is a failure mode the
fleet has already hit on some other host.

---

## 0. Before the service exists

- [ ] **Push `main`.** The site lived on `feat/excalidraw-0.18.1` and `main`
      held only the initial commit — the branch Render deploys had no site on
      it. `main` is now fast-forwarded and is 14 commits ahead of
      `origin/main`. Nothing reaches Render until this is pushed.
- [ ] **Confirm CI is green on that push.** `.github/workflows/ci.yml` had
      never run (it triggers on pull requests only, and the site was never
      PR'd to `main`). It was still leaflet's file: the package jobs imported
      `dash_leaflet2`, the image was tagged `dash-leaflet2-docs`, and flake8
      was pointed at a `usage.py` this repo does not have. All fixed, none of
      it exercised. **The first CI run is the first proof.**

## 1. Create the Render service

- [ ] New → Blueprint → this repo. `render.yaml` declares everything:
      `runtime: docker`, `plan: starter`, `branch: main`, `autoDeploy: true`,
      `healthCheckPath: /healthz`, the custom domain, and the 1 GB disk.
- [ ] **Verify the disk actually attached** — Dashboard → the service →
      Disks. *A declared disk attaches nothing.* leaflet ran for weeks with
      the declaration and no disk: the app `mkdir`'d `/var/data` on the
      container filesystem and every deploy silently wiped both the analytics
      ledger and the control-board store. The boot guard is the other check —
      see §5.

## 2. Env groups — **Step ZERO, and it comes before any delete**

Link all three to this service. Between them they supply the shared secret,
the reporting cadence, both `/var/data` paths, and the whole Clerk block.

- [ ] `2plot-network-shared` (group A)
- [ ] `2plot-satellite-reporting` (group B)
- [ ] `2plot-clerk-satellite` (group C) — only when turning Clerk on here

> **Ordering rule.** Link the group *before* deleting any service-level copy
> of one of its variables. Doing it the other way round is an outage, and it
> happened for real: service-level Clerk vars were removed while group C was
> not yet supplying them, `clerk_enabled()` went `False` on boilerplate and
> leaflet, and the sign-in avatar simply vanished with nothing in the logs.

`render.yaml` deliberately does **not** declare any group-owned variable. A
service-level variable overrides the group value, so a declared copy would
become a shadow on the next blueprint sync and silently mask future group
edits — recreating the drift class the groups exist to end.

## 3. Per-service identity variables

These are never grouped. `render.yaml` declares them, but **blueprint
`envVars` apply on a blueprint SYNC, not on a git-push autodeploy** — so
confirm each one on the service itself:

- [ ] `APP_BASE_URL=https://excalidraw.2plot.dev` — drives canonical,
      sitemap, og:url and every absolute llms.txt URL. The app refuses to
      boot on Render without it, and refuses a `*.onrender.com` value.
- [ ] `SATELLITE_APP_KEY=excalidraw`
- [ ] `AD_APP_ID=excalidraw`
- [ ] `SESSION_SECRET` — **unique**, generated, never shared or grouped.
- [ ] `DASH_BACKEND=flask`, `DASH_MCP_ENABLED=0`
- [ ] `PAGE_DEFAULT_TIER=public`, `LLMS_SMALL_TIER=public`,
      `LLMS_FULL_TIER=public` — the dark-launch trio, set explicitly so the
      declared-vs-live diff flags their absence and the eventual flip is a
      value edit rather than a variable add.
- [ ] `LLMS_PUBLIC_DEFAULT` stays **absent**. Its first appearance on any
      host *is* the phase-4 agent flip.

## 4. DNS and the certificate

- [ ] Point `excalidraw.2plot.dev` at the service (CNAME to the Render
      hostname). Until it resolves the site is only reachable on
      `*.onrender.com` — while already advertising `excalidraw.2plot.dev` as
      canonical, which is intentional: link equity consolidates onto the
      custom domain instead of competing with it.

## 5. Read the first deploy log — three absences and one presence

This is the acceptance check for §1–§3, and every part of it was proven to
have teeth locally (each guard was deliberately broken and each one fired).

- [ ] **PRESENT:** `[boilerplate/excalidraw] interactive gate: default tier
      'public', 2 non-public page(s), machine surfaces open by default
      (LLMS_PUBLIC_DEFAULT), access wiring ON, control board at
      /admin/control-board (…)`
- [ ] **ABSENT:** any `[visibility]` WARNING. Its presence names exactly
      which half of the disk contract is missing.
- [ ] **ABSENT:** any `[auth]` WARNING (only meaningful once Clerk is on).
- [ ] **ABSENT:** `[satellite-traffic] disabled` — its presence means
      `CROSS_APP_WEBHOOK_SECRET` did not arrive from group A.

## 6. Declared-vs-live env diff

- [ ] Diff `render.yaml`'s `envVars` against the service's actual env. **No
      test can see this class of defect and the diff can:** leaflet measured
      seven declared variables absent from the live service — including
      `PAGE_VISIBILITY_FILE`, which meant every control-board toggle reset on
      every deploy — plus two dead Gen-1 variables still set.

## 7. Register the host with the network — *currently unregistered by design*

`lib/network_directory.py` is a verbatim copy of the canonical list, and that
list **deliberately omits `excalidraw.2plot.dev`** ("only list hosts that are
actually live"). That is correct today and wrong the moment this deploys.
`tests/test_network_directory.py::test_this_host_is_queued_for_registration`
exists so the absence is a recorded decision rather than an oversight, and it
fails once the entry is added — delete it in that change.

- [ ] Add `excalidraw.2plot.dev` to the boilerplate's canonical `PEERS`, then
      re-copy `lib/network_directory.py` to every satellite (the list drifted
      into seven versions across nine repos once already).
- [ ] Add the hub health probe: `PULSE_POLL_TARGETS` on 2plot.ai +=
      `excalidraw=https://excalidraw.2plot.dev/healthz`
- [ ] Register the app key with the hub so its rollups land on a named row
      rather than an unknown one.

## 8. Before Clerk is turned on here — flip blockers

- [ ] **`CLERK_ALLOWED_REDIRECT_ORIGINS` on the 2plot.ai hub must include
      `https://excalidraw.2plot.dev`.** Re-verified against origin/main
      `2ebbed4`: this host is *not* among the listed origins. The env var
      REPLACES the code default, so every new host must be appended, and it
      needs no hub deploy. A host missing from it signs users in and strands
      them on 2plot.ai.
- [ ] **Add `excalidraw.2plot.dev` to the Clerk dashboard's allowed
      subdomains.** Missing from either list produces the same silent
      stranding.
- [ ] Link group C, then confirm `_dash-layout` carries the clerk components
      (`clerk-user-avatar`, `clerk-login-button`) — that grep is the external
      probe for `clerk_enabled()` having gone False.
- [ ] One real sign-in round trip: card → onboarding → back, still signed in.

## 9. After the first deploy

- [ ] `python scripts/smoke_live.py https://excalidraw.2plot.dev` — the same
      battery CD runs, including the crawler/browser identity-parity block.
- [ ] **Verify the social card exists.** `lib/constants.OG_IMAGE_URL` points
      at `https://cdn.2plot.ai/github_assets/excalidraw.2plot.dev.png`. That
      object was **not verifiable from the repo** (no network egress during
      this pass). If it 404s, every share of this site renders a blank card —
      build one with `scripts/make_social_card.py` and upload it to the
      Cloudflare bucket by hand; there is no automated path.
- [ ] Confirm the hub board shows this host `● live` within ~100s of a real
      visit (the presence beacon from group B).

## 10. Only then: the gate flip

- [ ] `PAGE_DEFAULT_TIER=auth`, after §8 passes. Rollback is setting it back
      — env only, no code revert. Record the flip date in
      `X402-SYNC-REPORT.md`.

---

## Not blockers, but queued

- **PyPI.** `lib/constants.SAME_AS` and `.github/workflows/release.yml`
  both point at `https://pypi.org/project/dash-excalidraw/`. If the project
  is not published yet, the JSON-LD `sameAs` names a 404 and the trusted
  publisher must still be configured (PyPI → Publishing → pending publisher:
  owner `pip-install-python`, repo `dash-excalidraw`, workflow `release.yml`,
  environment `pypi`).
- **pip-audit is advisory, deliberately.** The floors this pass added did
  their job — `cryptography` and `clerk-backend-api` now audit clean — but
  `diskcache` 5.6.3 carries PYSEC-2026-2447 with no fix published, so gating
  today would mean a permanently red check nobody can clear. Flip
  `continue-on-error` off in the change that raises the remaining pins.
- **`render.yaml` could declare the group links** via `fromGroup:` instead of
  describing them in comments. No host in the fleet does this yet, so it was
  not introduced here unilaterally — but it would turn §2 from a manual step
  into a declared one.
