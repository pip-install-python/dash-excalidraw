# `dash-excalidraw` Rebuild Plan

> Target: a from-scratch rebuild that bumps `dash-excalidraw` to modern Dash 3+ and
> Excalidraw 0.18.x, fixes the props that never actually worked across the Python/JS
> boundary, and preserves the current public API wherever the change is gratuitous.

**Authored:** April 2026
**Target `dash-excalidraw` version on release:** `0.1.0` (breaks with `0.0.x`, by design)
**Minimum supported Dash:** `3.0.3`
**Minimum supported Python:** `3.9`
**Minimum supported React:** `18.3.1`
**Pinned Excalidraw:** `^0.18.0`

---

## 1. Goals and non-goals

### Goals

- Bring the underlying Excalidraw canvas up to `0.18.0` so users get elbow arrows,
  flowcharts, scene search, image cropping, element linking, and the command
  palette without monkey-patching.
- Make the Python/JS bridge honest — every prop documented in the README should
  actually work across the serialization boundary. Function props that cannot
  round-trip through JSON are either replaced with event-emitting output props
  or removed.
- Expose the imperative API (`updateScene`, `scrollToContent`, `resetScene`,
  `setActiveTool`, `addFiles`, `exportToSvg`, `exportToBlob`, …) as Dash-callable
  actions so apps can drive the canvas from Python callbacks.
- Modernize the build pipeline (ESM, CSS import, Dash 3 component generator,
  `pyproject.toml`).
- Ship with a test suite that verifies the bridge rather than just the render.

### Non-goals

- Rewriting the upstream Excalidraw library. This is a wrapper.
- Replacing the component with a Dash hook. Hooks are server-side Python plugins
  and cannot render a React canvas. See §3.
- Maintaining Dash 2 compatibility. Cleanly cut to Dash 3+.
- Re-implementing the Excalidraw collaboration server. The wrapper exposes
  collaboration *knobs* (`isCollaborating`, `collaborators` state) but does not
  bundle a backend.

---

## 2. Version pinning decisions

| Dependency | Current | Target | Rationale |
|---|---|---|---|
| `@excalidraw/excalidraw` | `^0.15.3` | `^0.18.0` | See §2.1. Caret, not tilde, so we pick up `0.18.x` patches automatically. |
| `react` / `react-dom` | `^18.2.0` | `^18.3.1` | Dash 3's default. `^19` is Excalidraw-supported but Dash 3 still defaults to 18, so we stay aligned with the renderer. |
| `prop-types` | `^15.8.1` | **removed** | Move to TypeScript; Dash 3's component generator handles typing directly. |
| `ramda` | `^0.26.1` | **removed** | Not actually used in `DashExcalidraw.react.js`. Dead dependency. |
| `webpack` | `^5.84.1` | `^5.97.0` | Patch-level only, but pull in ESM fixes. |
| `@babel/*` | `^7.22.x` | `^7.26.x` | Standard refresh. |
| `dash` (Python) | `>=2.0.0` | `>=3.0.3` | §6. Minimum needed for hooks entry-point and Dash 3 typing. |
| `dash-mantine-components` (demo only) | *pinned to old* | `>=2.6.0` | Demo-side only, for `usage.py`. |

### 2.1 Why `^0.18.0` and not `0.17.6` or `@next`

- **`0.15.3 → 0.17.x` is already a breaking change for us** (ref removed,
  `elementType` → `activeTool`, `ready` / `readyPromise` removed). The
  migration cost is paid once. Stopping at 0.17 would capture that cost
  without earning the 0.18 features.
- **`0.18.0` moved UMD → ESM.** Our webpack config needs updating regardless.
  Doing it once for 0.18 is cheaper than doing it at 0.17 and then again for
  0.19.
- **`@next` is a moving target.** TS types have broken in pre-release commits
  (upstream issue #8503). A PyPI package can't reasonably track a rolling tag.
- **`0.19` does not exist at time of writing.** `0.18.0` shipped March 2025
  and there's been no stable release since. The upstream team is small and
  bootstrapped. `0.18.x` is effectively the latest stable and will remain so
  for the foreseeable near-term.

### 2.2 Escape hatch: `0.17.6`

If the ESM migration blows up in the Dash webpack config for reasons we can't
resolve in a reasonable timebox, `^0.17.6` is an acceptable fallback. We lose
elbow arrows, flowcharts, scene search, image cropping, element linking, and
the command palette — but we keep the `excalidrawAPI` cleanup that aligns us
with modern React. Treat this as plan B, not plan A.

---

## 3. Architecture: component package with an *optional* hooks companion

### 3.1 Why this stays a component package

Dash hooks (new in Dash 3.0) are a **Python server-side plugin mechanism**.
`@hooks.layout`, `@hooks.callback`, `@hooks.error`, `@hooks.setup`,
`@hooks.index`, `@hooks.route` all run on the Flask/FastAPI/Quart backend.
They do not ship JavaScript bundles. They cannot render React.

`dash-excalidraw` has to ship a JavaScript bundle (Excalidraw is React) and
has to register it through `_js_dist` / `_css_dist` so the Dash renderer
loads it in the browser. That registration is *exactly* what
`dash-generate-components` produces, and hooks can't replace it.

### 3.2 Where hooks *can* help: an optional companion

Split the project into two pip-installable packages that work independently:

```
dash-excalidraw/                 # the component, required
├── dash_excalidraw/
│   ├── __init__.py              # generated
│   ├── DashExcalidraw.py        # generated from TypeScript
│   └── dash_prop_typing.py      # custom type generator overrides
└── src/lib/components/DashExcalidraw.tsx

dash-excalidraw-hooks/           # optional, adds Python-side conveniences
└── dash_excalidraw_hooks/
    ├── __init__.py              # registers entry_point in pyproject.toml
    ├── autosave.py              # @hooks.callback to persist scene to dcc.Store
    ├── error_banner.py          # @hooks.error to display scene-load failures
    └── analytics.py             # @hooks.index to inject an analytics tag

# pyproject.toml in the hooks package
[project.entry-points."dash_hooks"]
dash_excalidraw_hooks = "dash_excalidraw_hooks"
```

The hooks package depends on the component package but not the reverse. An
app that does `pip install dash-excalidraw` gets just the canvas. An app
that also wants autosave/telemetry/error banners does
`pip install dash-excalidraw-hooks` and the behavior lights up without any
code change in the app itself.

This keeps the core small and gives people a reason to try the new hooks
system without entangling it with the component's critical path.

---

## 4. Prop surface redesign

The hard constraint: **Dash props are JSON-serialized over the Python/JS
boundary.** Functions, RegExp instances, and class instances cannot round-trip.
The current wrapper has several props declared as `PropTypes.func`
(`onPointerUpdate`, `renderTopRightUI`, `onPaste`, …) that Python can never
set and Python can never read. They're dead code in the Dash context.

The fix is to replace them with two kinds of Dash-friendly props:

- **Event output props** — the JS side watches the Excalidraw callback, and
  when it fires, calls `setProps({ lastPointerUp: {...} })`. Python reads the
  resulting state via `Input('excalidraw', 'lastPointerUp')`.
- **Action dispatch props** — Python writes an object like
  `{ id, type, payload }` into a prop (e.g. `command`), and the JS side
  watches for changes to that prop and dispatches into the imperative API.
  The `id` field is how we guarantee the same command isn't dispatched twice.

### 4.1 Proposed full prop list

```ts
type DashExcalidrawProps = DashComponentProps & {
  // ---- sizing ----
  width?: string;                     // default "100%"
  height?: string;                    // default "600px" (was "400px" — too small)

  // ---- initial load ----
  initialData?: {
    elements?: ExcalidrawElement[];
    appState?: Partial<AppState>;
    files?: BinaryFiles;
    libraryItems?: LibraryItems;
  };

  // ---- controlled-ish output state (written by JS via setProps) ----
  elements?: readonly ExcalidrawElement[];       // output-only from Python's POV
  appState?: Partial<AppState>;                  // output-only; FULL appState now, not just {gridSize, viewBackgroundColor}
  files?: BinaryFiles;                           // output-only
  serializedData?: string;                       // output-only, backward-compat shape
  sceneVersion?: number;                         // output-only, from getSceneVersion()

  // ---- editor config (declarative) ----
  viewModeEnabled?: boolean;                     // default false
  zenModeEnabled?: boolean;                      // default false
  gridModeEnabled?: boolean;                     // default false
  isCollaborating?: boolean;                     // default FALSE (was true — surprising)
  theme?: "light" | "dark";                      // default "light"
  name?: string;                                 // drawing name
  langCode?: string;                             // default "en"
  libraryReturnUrl?: string;
  detectScroll?: boolean;                        // default true
  handleKeyboardGlobally?: boolean;              // default true
  autoFocus?: boolean;                           // default true

  // ---- UI options (serializable subset) ----
  UIOptions?: {
    canvasActions?: {
      changeViewBackgroundColor?: boolean;
      clearCanvas?: boolean;
      export?: boolean | { saveFileToDisk?: boolean };
      loadScene?: boolean;
      saveToActiveFile?: boolean;
      toggleTheme?: boolean | null;
      saveAsImage?: boolean;
    };
    tools?: { image?: boolean };
    dockedSidebarBreakpoint?: number;
    welcomeScreen?: boolean;
  };

  // ---- embeddable validation (string allowlist instead of RegExp[]) ----
  validateEmbeddable?: boolean | string[];      // string[] is domain allowlist
                                                // (JS side compiles to RegExp[])

  // ---- throttled event outputs (NEW) ----
  // All written via setProps, never read from Python. Each one carries
  // { timestamp, ... } so Python can dedupe.
  lastPointerDown?: { timestamp, activeTool, pointer };
  lastPointerUp?:   { timestamp, activeTool, pointer };
  lastPointerMove?: { timestamp, pointer };      // throttled to ~50ms
  lastScrollChange?: { timestamp, scrollX, scrollY };
  lastPaste?:       { timestamp, data };
  lastLibraryChange?: { timestamp, items };
  lastLinkOpen?:    { timestamp, elementId, url };
  lastExport?:      { timestamp, id, type, result };  // see 4.2

  // ---- imperative command dispatch (NEW) ----
  // Python writes here, JS dispatches, then clears with setProps({command: null}).
  // Every command MUST carry a unique id so we don't double-dispatch on remount.
  command?: null | {
    id: string;
    type:
      | "updateScene"
      | "addFiles"
      | "resetScene"
      | "scrollToContent"
      | "setActiveTool"
      | "setToast"
      | "toggleSidebar"
      | "updateLibrary"
      | "exportToSvg"
      | "exportToBlob"
      | "exportToCanvas";
    payload?: any;                            // shape depends on type
  };
};
```

### 4.2 Exports: the "command + event" round trip

The export utilities (`exportToSvg`, `exportToBlob`) return Promises, not
direct values. For a Dash-friendly flow:

1. Python dispatches `command = { id: "x", type: "exportToSvg", payload: {...} }`
2. JS side sees the prop change, awaits the export, then writes
   `setProps({ lastExport: { id: "x", type: "exportToSvg", result: <base64 or SVG string> } })`
3. Python reads `Input('excalidraw', 'lastExport')`, matches on `id`, and
   has the result.
4. JS clears `command` by calling `setProps({ command: null })` to avoid
   re-dispatching if React re-renders the prop.

This keeps everything async-safe and JSON-serializable.

### 4.3 Props removed from the public API

These were dead code in the Dash context (`PropTypes.func` but unreachable
from Python):

- `excalidrawAPI` — replaced by the command/event pair above
- `onPointerUpdate` — replaced by `lastPointerMove`
- `onPointerDown` — replaced by `lastPointerDown`
- `onScrollChange` — replaced by `lastScrollChange`
- `onPaste` — replaced by `lastPaste` (note: cannot `return false` to block
  paste from Python's async side; if users need paste interception they
  should use a separate Dash callback that modifies scene state afterward)
- `onLibraryChange` — replaced by `lastLibraryChange`
- `onLinkOpen` — replaced by `lastLinkOpen`
- `renderTopRightUI` / `renderCustomStats` / `renderEmbeddable` — these
  require *React children*. Not representable as JSON. Document as
  out-of-scope for the Python API. Users who need them must fork the
  wrapper.
- `generateIdForFile` — functions don't cross the bridge; the JS side uses
  a default UUID generator.

### 4.4 Breaking-change table for existing apps

| Old prop | New behavior | Migration |
|---|---|---|
| `isCollaborating` default `true` | default `false` | Apps that relied on collaboration UI must set `isCollaborating=True` explicitly. |
| `height` default `"400px"` | default `"600px"` | Apps get a slightly taller canvas by default. Cosmetic. |
| `appState` written to Python only contained `gridSize`, `viewBackgroundColor` | Full serializable appState | Callbacks that pattern-matched on the old narrow shape will still work; it's strictly additive. |
| `onPointerUpdate` et al. | removed, replaced by `lastPointerMove` et al. | Python code that read these props never got anything useful, so no real breakage. |
| `excalidrawAPI` callback prop | removed, replaced by `command` + event props | See §4.2. |
| `validateEmbeddable: RegExp[]` | `validateEmbeddable: string[]` | Pass domain strings; the JS side compiles them. |

---

## 5. Build pipeline changes (0.18 ESM + Dash 3 generator)

### 5.1 Switch to the TypeScript component template

Regenerate the project skeleton from
`cookiecutter gh:plotly/dash-typescript-component-template`. This gets us:

- TypeScript component sources (`src/ts/DashExcalidraw.tsx`)
- Dash 3 component generator that emits typed `__init__` signatures
- `proptypes.js` auto-generation registered in `_js_dist`
- `pyproject.toml` instead of `setup.py`
- A pre-configured webpack setup that includes `ts-loader`

Carry over from the old repo:

- The README (updated)
- The demo `usage.py` (rewritten for Dash 3)
- The existing asset/animation pipeline if anything's there (there isn't
  much — mostly a thumbnail image)

### 5.2 Webpack config for ESM Excalidraw

Excalidraw 0.18's distribution is ESM-only. The webpack config needs:

```js
// webpack.config.js (excerpt)
module.exports = {
  // …
  resolve: {
    extensions: ['.ts', '.tsx', '.js', '.jsx'],
    // Ensure package.json "exports" field is respected for @excalidraw/*
    conditionNames: ['import', 'module', 'default'],
  },
  experiments: {
    outputModule: false,  // Dash still loads the bundle via <script>, not <script type=module>
  },
  module: {
    rules: [
      {
        test: /\.m?js/,
        resolve: { fullySpecified: false },  // Excalidraw's ESM imports are not fully specified
      },
      {
        test: /\.tsx?$/,
        use: 'ts-loader',
        exclude: /node_modules/,
      },
      {
        test: /\.css$/,
        use: ['style-loader', 'css-loader'],
      },
    ],
  },
};
```

### 5.3 CSS import

0.18 requires an explicit CSS import:

```ts
import '@excalidraw/excalidraw/index.css';
```

The webpack `style-loader` + `css-loader` chain will inline it into the
bundle. Alternatively, register it as a separate CSS asset in
`_css_dist` so Dash serves it as a `<link rel="stylesheet">`. The inline
approach is simpler for a Python package — one `.js` file to ship.

### 5.4 Font handling

Excalidraw 0.18 loads fonts from `esm.run` CDN by default. Two choices:

**Option A (default, recommended for 0.1.0):** Leave the CDN loading on.
Simpler, fonts load lazily, no asset-copy step in the Python packaging.
Downside: requires internet access at runtime. Documented as a known
limitation.

**Option B (self-hosted):** Copy
`node_modules/@excalidraw/excalidraw/dist/prod/fonts/` into the Python
package's asset directory at build time, set
`window.EXCALIDRAW_ASSET_PATH` on mount. Adds ~10 MB to the wheel. Do
this in 0.2.0 as a follow-up if users request offline support.

### 5.5 SSR guard fix

Current code:

```js
if (typeof window === "undefined") { return null; }    // ⚠ before useRef
const excalidrawRef = useRef(null);                    // Rules-of-Hooks violation
```

Replace with:

```tsx
const [isMounted, setIsMounted] = useState(false);
useEffect(() => { setIsMounted(true); }, []);
// …later in render:
if (!isMounted) return <div style={{width, height}} />;
```

Dash actually has no SSR path today, but React 18.3's dev mode enforces
Rules of Hooks strictly and the current code will warn. The effect-gated
flag is the canonical pattern.

---

## 6. Dash 3+ compatibility

### 6.1 Drop `defaultProps` on function components

React 18.3 deprecates `defaultProps` on function components. Convert:

```jsx
// old
DashExcalidraw.defaultProps = { width: '100%', height: '400px', … };

// new
const DashExcalidraw = ({
  width = '100%',
  height = '600px',
  theme = 'light',
  isCollaborating = false,
  viewModeEnabled = false,
  // …
}: DashExcalidrawProps) => { … };
```

For persistence props, use `Component.dashPersistence` (Dash 3-only) with
a runtime-feature-detect fallback if we ever want Dash 2 compat back (we
don't).

### 6.2 Update `usage.py`

```python
# was
if __name__ == '__main__':
    app.run_server(debug=True, port=8023)

# now
if __name__ == '__main__':
    app.run(debug=True, port=8023)
```

Drop `_dash_renderer._set_react_version("18.2.0")` entirely — Dash 3
manages React version itself and the API is gone.

### 6.3 Type-generator overrides

Add `dash_excalidraw/dash_prop_typing.py`:

```python
# Tell dash-generate-components to emit good types for initialData
custom_imports = {
    "DashExcalidraw": [
        "from typing import TypedDict, List, Any, Dict",
    ],
}

def _initial_data_type(*_):
    return "typing.Optional[typing.Dict[str, typing.Any]]"

custom_props = {
    "DashExcalidraw": {
        "initialData": _initial_data_type,
    },
}
```

Run `dash-generate-components -t dash_prop_typing`.

### 6.4 `loading_state` is gone

We never depended on it, so this is zero-effort. Note for future: if we
want to react to loading, use
`window.dash_component_api.useDashContext().useLoading()`.

---

## 7. Packaging and distribution

### 7.1 Move to `pyproject.toml`

Replace `setup.py` with PEP 621 metadata:

```toml
[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "dash-excalidraw"
version = "0.1.0"
description = "Excalidraw drawing component for Dash"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.9"
authors = [{ name = "Pip Install Python" }]
dependencies = [
  "dash>=3.0.3",
]
classifiers = [
  "Framework :: Dash",
  "License :: OSI Approved :: MIT License",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3 :: Only",
]

[project.urls]
Homepage = "https://pip-install-python.com/pip/dash_excalidraw"
Source = "https://github.com/pip-install-python/dash_excalidraw"

[tool.setuptools.packages.find]
include = ["dash_excalidraw*"]

[tool.setuptools.package-data]
dash_excalidraw = ["*.js", "*.js.map", "*.json", "fonts/**/*"]
```

### 7.2 Trusted Publishing on PyPI

Move off API tokens. PyPI's Trusted Publishing with GitHub Actions removes
the need to store a token in repo secrets. See PyPI docs for the OIDC
workflow.

### 7.3 Semver on the Python package

This rebuild warrants a jump to `0.1.0`:

- `0.0.4 → 0.1.0` signals a breaking change to downstream consumers
- Future bug-fix-only releases go `0.1.1`, `0.1.2`, …
- Future minor features that don't break the API go `0.2.0`, `0.3.0`, …
- `1.0.0` is reserved for the first release where we commit to a stable
  Python API surface

---

## 8. Testing plan

Current tests (`tests/test_usage.py`) are a placeholder from the
cookiecutter — they test an input box that doesn't exist. They need to
be deleted and replaced.

### 8.1 Unit tests (JS side)

Use Jest + React Testing Library (already available in the TS
boilerplate):

- `DashExcalidraw` renders without crashing with no props.
- `initialData` is forwarded to the underlying `<Excalidraw>`.
- `theme="dark"` causes the dark-mode class to appear.
- `viewModeEnabled` / `zenModeEnabled` / `gridModeEnabled` booleans
  propagate.
- The `onChange` handler writes to `setProps` with the expected keys
  (`elements`, `appState`, `files`, `serializedData`, `sceneVersion`).
- A `command = { id, type: 'updateScene', payload }` causes
  `excalidrawAPI.updateScene` to be invoked with `payload`, exactly once
  per `id` (dispatching the same `id` twice is a no-op).
- `command = { id, type: 'exportToSvg', payload }` results in a
  `lastExport` prop write carrying the same `id`.

### 8.2 Integration tests (Python side)

Use `dash[testing]` + `dash_duo`:

- An app with `dash_excalidraw.DashExcalidraw(id='x')` and a
  `html.Div(id='out')` updating on `Input('x', 'elements')` — simulate a
  canvas drag via Selenium, confirm `elements` updates in the Div.
- A Python callback that writes to `Output('x', 'command')` triggers
  a scene update and fires `lastExport`.
- `theme` can be flipped from a `dcc.Switch` and the canvas rerenders.

### 8.3 CI

GitHub Actions matrix:

- Python 3.9, 3.10, 3.11, 3.12, 3.13
- Dash 3.0.3 (minimum), 3.1, 3.2, 3.3, 4.0, 4.1 (latest stable)
- Node 20 LTS (the current stable for Dash 3 tooling)
- Chrome headless for the Selenium step

---

## 9. README and docs

### 9.1 README restructure

The current README claims a lot of things that don't quite work
(`renderTopRightUI`, etc.). The new README should:

- Lead with a working minimal example (the existing one is fine).
- Document every prop with a Python-level code example.
- Document the command/event pattern for imperative actions, with a
  copy-pasteable "export to SVG" example.
- Include a "what's different from Excalidraw upstream" section that
  honestly lists what's exposed and what isn't (e.g. custom React UI
  children are not exposed).
- Include a "migration from 0.0.x" section that enumerates every
  breaking change from §4.4.

### 9.2 Examples directory

Add `examples/`:

- `01_basic/` — the README example.
- `02_persistence/` — save/restore scene to a `dcc.Store`.
- `03_export/` — Python-driven SVG export with a download link.
- `04_collaboration_stub/` — `isCollaborating=True` with a Python-only
  collaboration pointer relay (no backend required).
- `05_themed_app/` — integration with a `dash-mantine-components`
  color-scheme toggle.

---

## 10. Rollout plan

### Phase 1 — scaffold (week 1)

- New repo skeleton from TS template
- Copy README, LICENSE, asset
- `pyproject.toml` written
- CI wired (lint only, no tests yet)

### Phase 2 — bridge (weeks 2-3)

- TS component with the new prop surface (§4)
- `onChange` wiring with full appState serialization
- Command/event dispatch plumbing
- Jest unit tests green

### Phase 3 — parity (week 4)

- All export actions wired (`exportToSvg`, `exportToBlob`,
  `exportToCanvas`)
- Library update API wired
- `setActiveTool` wired
- Integration tests green

### Phase 4 — docs & publish (week 5)

- README rewrite
- Five examples
- Migration guide
- Publish `0.1.0-rc1` to TestPyPI
- Feedback cycle of ~2 weeks
- Publish `0.1.0` to PyPI

### Phase 5 — optional hooks companion (week 6+, can slip)

- `dash-excalidraw-hooks` with autosave, error banner, analytics
- Publish `0.1.0` to PyPI as a separate package

---

## 11. Risks and open questions

### Confirmed risks

- **ESM in Dash's webpack.** The `conditionNames` and `fullySpecified: false`
  config works in principle, but Dash's component build pipeline pre-dates
  the ESM transition. If `dash-generate-components` chokes on ESM imports,
  fall back to 0.17.6 per §2.2.
- **Slow upstream pace.** Excalidraw has not shipped a stable since March
  2025. If a bug surfaces in 0.18.0 that needs an upstream fix, we may be
  waiting a while. Mitigation: if we hit a specific blocker, consider
  pinning to a known-good `0.18.0-<sha>` pre-release commit that's fixed.
- **CDN font loading.** Environments without outbound internet (corporate
  firewalls, air-gapped) will see fallback fonts. Flag as a known
  limitation for 0.1.0; address in 0.2.0 with self-hosted fonts.

### Open questions

- Do we want to expose Mermaid-to-Excalidraw conversion? It's a separate
  npm package (`@excalidraw/mermaid-to-excalidraw`) and would be a nice
  value-add for Dash users who want to pipe Mermaid source into the
  canvas. Low priority but worth a line item.
- Should `UIOptions.welcomeScreen` default to `false` for Dash users?
  Most Dash apps embed the canvas in a larger UI where the welcome
  screen is visually noisy. Tentatively yes, but opt-out via prop.
- Should the demo use FastAPI (Dash 4+)? FastAPI unlocks async callbacks
  which could be nice for the export round-trip. Leave for 0.2.0.
- Do we want TypeScript types published for Python? PEP 561 stubs are
  free once we've done the `dash_prop_typing` work — the Dash 3
  generator produces them automatically.

---

## 12. What is explicitly NOT changing

To keep scope honest, these parts of the current wrapper are correct and
carry forward unchanged:

- The core `initialData` shape (`{ elements, appState }` with optional
  `files` and `libraryItems`).
- `width` / `height` as string props.
- `theme`, `langCode`, `name`, `libraryReturnUrl`, `zenModeEnabled`,
  `gridModeEnabled`, `viewModeEnabled` — all declaratively fine.
- The `serializedData` output prop shape — it was well-designed and
  apps depend on it. We keep the `{ type, version, source, elements,
  appState, files }` envelope.
- The top-level `<div id={id}>` wrapper so Dash `id` targeting works.

---

## Appendix A: Excalidraw changelog digest (0.15.3 → 0.18.0)

Abbreviated, covering only what affects integrators:

### v0.16 (minor)
- `validateEmbeddable` prop added
- Sidebar tabs API, `<DefaultSidebar>` exposed
- `scrollToContent` gains `fitToViewport` / `viewportZoomFactor` opts
- `useI18n()` hook exposed for rendering Excalidraw children
- `restoreElements` / `restore` gain `opts` param

### v0.17 (BREAKING)
- **`ref` removed**, replaced by `excalidrawAPI` prop callback
- **`ready` / `readyPromise` removed**
- `onChange` / `onPointerDown` / `onPointerUp` API subscribers added
- `setActiveTool` gains `locked` and `insertOnCanvasDirectly`
- Frames API added
- `getCommonBounds`, `elementsOverlappingBBox`,
  `isElementInsideBBox`, `elementPartiallyOverlapsWithOrContainsBBox`
  exported
- Preact supported via `process.env.IS_PREACT = "true"`
- `useDevice` hook return value split into editor / viewport breakpoints

### v0.17.1 - v0.17.6 (patches)
- UMD build restored (was breaking in 0.17.0)
- `customData` preserved across restore
- Bundle size / perf fixes

### v0.18.0 (BREAKING + headline features)
- Command palette (Cmd/Ctrl+/)
- Multiplayer undo / redo
- Editable element stats panel
- Text element wrapping
- Font picker, Excalifont, CJK font
- SVG export font subsetting
- **Elbow arrows**
- **Flowchart shortcuts** (Cmd/Ctrl+Arrow)
- **Scene search** (Cmd/Ctrl+F)
- **Image cropping** (Enter / double-click image)
- **Element linking** (Cmd/Ctrl+K)
- Crowfoot arrowheads
- **UMD → ESM** bundle transition
- `excalidraw-assets` folder deprecated; locales transpiled to JS
- Fonts from `esm.run` CDN by default
- CSS now imported from `@excalidraw/excalidraw/index.css`
- Public types available at `@excalidraw/excalidraw/types`

### (post-0.18, `@next` only — do NOT pin to these)
- `onMount` / `onInitialize` / `onUnmount` lifecycle props
- `<ExcalidrawAPIProvider>` and `useExcalidrawAPI()`
- `useAppStateValue()` / `useOnExcalidrawStateChange()` hooks
- `api.onEvent(...)` unified subscriber API
