# Changelog

All notable changes to `dash-excalidraw` are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
