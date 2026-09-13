import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {
    CaptureUpdateAction,
    Excalidraw,
    MainMenu,
    exportToBlob,
    exportToCanvas,
    exportToSvg,
    getSceneVersion,
    WelcomeScreen,
    restoreElements,
    serializeAsJSON,
} from '@excalidraw/excalidraw';
// Excalidraw 0.18 ships its stylesheet as a separate `exports` entry rather
// than inlining it into the JS artifact the way 0.17.x did. Without this
// import the canvas mounts but renders with no toolbar chrome at all.
// The style-loader chain in webpack.config.js (insertAtTop) inlines it into
// the bundle so Dash apps need no extra external_stylesheets entry.
import '@excalidraw/excalidraw/index.css';

import {DashComponentProps} from '../props';

/* =========================================================================
 *  Types
 *  The Excalidraw public types are permissive across 0.17/0.18 — we keep
 *  them loose intentionally so the Dash prop generator produces clean
 *  Python-side signatures without pulling Excalidraw's internal types.
 * ========================================================================= */

type ExcalidrawElement = Record<string, any>;
type AppState = Record<string, any>;
type BinaryFiles = Record<string, any>;
type LibraryItem = Record<string, any>;
type PointerCoords = {x: number; y: number};

type CanvasActionsOptions = {
    changeViewBackgroundColor?: boolean;
    clearCanvas?: boolean;
    export?: boolean | {saveFileToDisk?: boolean};
    loadScene?: boolean;
    saveToActiveFile?: boolean;
    toggleTheme?: boolean | null;
    saveAsImage?: boolean;
};

type UIOptionsShape = {
    canvasActions?: CanvasActionsOptions;
    tools?: {image?: boolean};
    dockedSidebarBreakpoint?: number;
    welcomeScreen?: boolean;
};

type InitialDataShape = {
    elements?: ExcalidrawElement[];
    appState?: Partial<AppState>;
    files?: BinaryFiles;
    libraryItems?: LibraryItem[];
    scrollToContent?: boolean;
};

type CommandType =
    | 'updateScene'
    | 'addFiles'
    | 'resetScene'
    | 'scrollToContent'
    | 'setActiveTool'
    | 'setToast'
    | 'toggleSidebar'
    | 'updateLibrary'
    | 'replaceFiles'
    | 'exportToSvg'
    | 'exportToBlob'
    | 'exportToCanvas';

type CommandShape = {
    id: string;
    type: CommandType;
    payload?: Record<string, any>;
};

/* -------------------------------------------------------------------------
 *  One-time deprecation notices. Module scope on purpose: a per-instance
 *  flag would re-warn for every canvas on a multi-canvas page, and a
 *  per-dispatch warn would flood the console on a collaborative session.
 * ------------------------------------------------------------------------- */
let warnedCommitToHistory = false;
let warnedBadCaptureUpdate = false;


type Props = {
    // ---- sizing ---------------------------------------------------------
    /**
     * CSS width of the canvas container.
     * @default "100%"
     */
    width?: string;

    /**
     * CSS height of the canvas container. Excalidraw fills its parent,
     * so this is the number to change when the canvas looks too short.
     * @default "600px"
     */
    height?: string;

    // ---- initial load ---------------------------------------------------
    /**
     * Initial scene contents passed to Excalidraw on mount. Shape:
     * `{elements, appState, files, libraryItems, scrollToContent}`.
     * Updating this prop after mount has no effect — use `command` with
     * `type="updateScene"` to change the scene imperatively.
     */
    initialData?: InitialDataShape;

    // ---- output state (setProps-only from Python's POV) -----------------
    /**
     * Current Excalidraw element array. Written via setProps on every
     * scene change — read-only from Python callbacks.
     */
    elements?: ReadonlyArray<ExcalidrawElement>;

    /**
     * Full serializable app state (view background, zoom, scroll, grid
     * mode, zen mode, theme, active tool, …). Read-only from Python.
     */
    appState?: Partial<AppState>;

    /**
     * Map of binary file entries (image id -> {dataURL, mimeType, ...}).
     * Read-only from Python.
     */
    files?: BinaryFiles;

    /**
     * JSON string of the canonical Excalidraw serialized envelope
     * `{type, version, source, elements, appState, files}`. Suitable to
     * pass to `dash.dcc.Store` and later restore via `initialData`.
     */
    serializedData?: string;

    /**
     * Same envelope as `serializedData`, but every `files[*].dataURL`
     * that still holds an inline `data:` URI is replaced with `null`.
     * External URLs (those dispatched via the `replaceFiles` command)
     * are retained as-is. Persist this variant to avoid paying the
     * base64 cost; inline bytes can be rehydrated later via
     * `dash_excalidraw.helpers.restore_inline_files`.
     */
    externalizedSerializedData?: string;

    /**
     * Show Excalidraw's welcome overlay on an empty canvas.
     *
     * REACTIVE, unlike `UIOptions.welcomeScreen`. The vendor reads that key
     * once while the canvas is mounting, so a switch wired to it appears to do
     * nothing — which is exactly how it read.
     *
     * This works by composing Excalidraw's `<WelcomeScreen>` as a CHILD, which
     * React mounts and unmounts with the prop. MEASURED, because the obvious
     * alternative looks right and is not: `appState.showWelcomeScreen` exists,
     * but `updateScene({appState: {showWelcomeScreen: false}})` leaves it
     * `true` — the vendor filters that key out of the merge, silently. Do not
     * "fix" this back to an appState push.
     */
    welcomeScreen?: boolean;

    /**
     * Words for the welcome overlay: `{title, subtitle}`. Either may be
     * omitted. Supplying neither keeps Excalidraw's own wording.
     *
     * Only the TEXT is yours — the overlay's menu hints stay the vendor's, so
     * they cannot drift out of step with the menu they describe.
     */
    welcomeScreenContent?: {title?: string; subtitle?: string};

    /**
     * A scene to open with when `initialData` is not given: `{elements,
     * appState, files}`, the same shape `initialData` and
     * `externalizedSerializedData` use, so a scene produced anywhere in this
     * library can be pasted straight in.
     *
     * MOUNT-ONLY, like `initialData` — Excalidraw owns the scene afterwards.
     * Dispatch `updateScene` to change it later.
     */
    welcomeScene?: Record<string, any>;

    /**
     * Monotonic scene version, from the package's `getSceneVersion(elements)`
     * export. Useful for change detection without diffing element arrays.
     *
     * It tracks ELEMENTS only. Registering a file, panning or zooming leaves
     * it unchanged, so a callback that must see those should take `files` or
     * `appState` as its Input rather than this.
     */
    sceneVersion?: number;

    /**
     * Fires when one or more new file ids appear in `files` with an
     * inline `data:` dataURL. Payload:
     *
     *   {
     *     timestamp,
     *     fileId, mimeType, dataURL, size,   # first new file (back-compat)
     *     files: [
     *       {fileId, mimeType, dataURL, size},
     *       ...                              # every new file in this change
     *     ],
     *   }
     *
     * Single-file callbacks can keep reading `event['fileId']`; batch
     * callbacks iterate `event['files']`. `size` is decoded byte count.
     */
    lastFileAdded?: Record<string, any>;

    /**
     * Fires when the wrapper's drop handler intercepts a drop that
     * Excalidraw itself doesn't accept (non-image files, or any multi-
     * file drop). Payload:
     *
     *   {
     *     timestamp,
     *     files: [{name, mimeType, dataURL, size}, ...],
     *     dropPoint: {x, y},                  # scene coords
     *     placeholderIds: [elemId, ...],      # one id per non-image file,
     *                                         # pointing at the rectangle we
     *                                         # placed on the canvas so you
     *                                         # can update its `link` after
     *                                         # upload.
     *   }
     */
    lastExternalDrop?: Record<string, any>;

    /**
     * When `true`, the wrapper calls `event.preventDefault()` on every
     * `lastLinkOpen` event so Python can handle the click itself
     * (typically by opening a `dmc.Drawer`). Default `false` — links
     * open in a new tab normally.
     */
    interceptLinkOpens?: boolean;

    /**
     * When `true` (default), the vendor's "Excalidraw links" group (GitHub /
     * Follow us / Discord) is not rendered. Set `false` to show it.
     *
     * This is a render condition on THIS canvas's menu, so it works in both
     * directions and each canvas on a page decides for itself.
     * @default true
     */
    hideExcalidrawLinks?: boolean;

    /**
     * URL for the wrapper's own documentation item in the main menu.
     * Rendered as its own group, independently of `hideExcalidrawLinks`.
     * Set to `""` or `None` to render no item at all.
     * @default "https://excalidraw.2plot.dev"
     */
    docsLinkUrl?: string;

    /**
     * Visible label for the `docsLinkUrl` item. Re-point the URL and you
     * should relabel: a menu entry that names one destination and opens
     * another is the failure this pair exists to avoid.
     * @default "dash-excalidraw docs"
     */
    docsLinkLabel?: string;

    // ---- editor config --------------------------------------------------
    /**
     * View-only mode: disables drawing tools; pan/zoom still available.
     * @default false
     */
    viewModeEnabled?: boolean;

    /**
     * Zen mode hides most of the chrome for a distraction-free canvas.
     * @default false
     */
    zenModeEnabled?: boolean;

    /**
     * Snap to grid and draw the grid background.
     * @default false
     */
    gridModeEnabled?: boolean;

    /**
     * Renders the "currently-editing" collaborator UI. You'll also need
     * to feed `appState.collaborators`; the wrapper does not bundle a
     * transport layer.
     * @default false
     */
    isCollaborating?: boolean;

    /**
     * Canvas color theme.
     * @default "light"
     */
    theme?: 'light' | 'dark';

    /**
     * Drawing name — appears in the top bar and in serialized export
     * filenames.
     */
    name?: string;

    /**
     * UI language code (e.g. `en`, `fr-FR`, `zh-CN`).
     * @default "en"
     */
    langCode?: string;

    /**
     * Optional URL appended to the "Browse Library" button in the
     * sidebar. When unset Excalidraw uses its own default.
     */
    libraryReturnUrl?: string;

    /**
     * Whether Excalidraw listens to wheel-scroll events on the canvas.
     * @default true
     */
    detectScroll?: boolean;

    /**
     * When true, keyboard shortcuts work even when the canvas is not
     * focused. Turn off if your Dash app has other inputs that might
     * conflict.
     * @default true
     */
    handleKeyboardGlobally?: boolean;

    /**
     * Focus the canvas on mount.
     * @default true
     */
    autoFocus?: boolean;

    // ---- UI options -----------------------------------------------------
    /**
     * Subset of Excalidraw `UIOptions` that is JSON-serializable. Use
     * this to toggle individual canvas actions, show/hide the welcome
     * screen, etc.
     */
    UIOptions?: UIOptionsShape;

    // ---- embeddable validation (serializable) ---------------------------
    /**
     * Controls which URLs may be embedded inside Excalidraw frames.
     * Pass `true` to allow all, `false` to deny all, or a list of
     * domain-glob strings (e.g. `["*.youtube.com", "excalidraw.com"]`)
     * which the wrapper compiles to case-insensitive RegExps.
     */
    validateEmbeddable?: boolean | string[];

    // ---- throttled event outputs ---------------------------------------
    /**
     * Snapshot of the last pointer-down event:
     * `{timestamp, activeTool, pointer: {x, y}}`.
     */
    lastPointerDown?: Record<string, any>;

    /**
     * Snapshot of the last pointer-up event:
     * `{timestamp, activeTool, pointer: {x, y}}`.
     */
    lastPointerUp?: Record<string, any>;

    /**
     * Throttled pointer-move snapshot `{timestamp, pointer, button,
     * pointersMap}`. Throttled by `pointerMoveThrottleMs` (default 50 ms).
     */
    lastPointerMove?: Record<string, any>;

    /**
     * Throttled scroll/zoom snapshot `{timestamp, scrollX, scrollY}`.
     */
    lastScrollChange?: Record<string, any>;

    /**
     * Snapshot of the last clipboard paste `{timestamp, data}`. The
     * wrapper cannot cancel the paste from Python; if you need to
     * intercept, clean up in a follow-up callback that modifies scene
     * state afterward.
     */
    lastPaste?: Record<string, any>;

    /**
     * Snapshot of the last library change `{timestamp, items}`.
     */
    lastLibraryChange?: Record<string, any>;

    /**
     * Snapshot of the last link-open event `{timestamp, elementId, url}`
     * — fired when a user Cmd/Ctrl-clicks an element with a hyperlink.
     */
    lastLinkOpen?: Record<string, any>;

    /**
     * Result of the most recent export command:
     * `{timestamp, id, type, result, error?}`. Match `id` against the
     * command you dispatched to correlate responses.
     */
    lastExport?: Record<string, any>;

    // ---- imperative command dispatch -----------------------------------
    /**
     * Write to this prop from a Python callback to dispatch an imperative
     * action into Excalidraw. Shape:
     *
     * ```python
     * {"id": "unique-string", "type": "updateScene", "payload": {...}}
     * ```
     *
     * Supported `type` values:
     *  - `updateScene` / `resetScene` / `addFiles`
     *  - `scrollToContent` / `setActiveTool` / `setToast` / `toggleSidebar`
     *  - `updateLibrary`
     *  - `exportToSvg` / `exportToBlob` / `exportToCanvas`
     *
     * Each dispatch is de-duplicated by `id`, and the component clears
     * the prop (sets it to `None`) once the action completes so React
     * re-renders do not re-fire.
     */
    command?: CommandShape | null;

    // ---- throttling knobs ----------------------------------------------
    /**
     * Debounce interval for `lastPointerMove` writes (milliseconds).
     * @default 50
     */
    pointerMoveThrottleMs?: number;

    /**
     * Debounce interval for `lastScrollChange` writes (milliseconds).
     * @default 100
     */
    scrollThrottleMs?: number;
} & DashComponentProps;

/* =========================================================================
 *  Helpers
 * ========================================================================= */

function globToRegex(pattern: string): RegExp {
    const escaped = pattern
        .replace(/[.+?^${}()|[\]\\]/g, '\\$&')
        .replace(/\*/g, '.*');
    return new RegExp(`^${escaped}$`, 'i');
}

async function blobToBase64(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(blob);
    });
}

/**
 * Estimate the decoded byte size of a data URL. Base64 payloads decode
 * to roughly 3/4 of their character length (minus padding); percent-
 * encoded payloads are counted after decoding.
 */
function dataUrlByteSize(dataUrl: string): number {
    if (typeof dataUrl !== 'string') return 0;
    const commaIdx = dataUrl.indexOf(',');
    if (!dataUrl.startsWith('data:') || commaIdx < 0) return dataUrl.length;
    const meta = dataUrl.slice(5, commaIdx);
    const payload = dataUrl.slice(commaIdx + 1);
    if (meta.endsWith(';base64')) {
        const paddingMatch = payload.match(/=+$/);
        const padding = paddingMatch ? paddingMatch[0].length : 0;
        return Math.max(0, Math.floor((payload.length * 3) / 4) - padding);
    }
    try {
        return decodeURIComponent(payload).length;
    } catch (_err) {
        return payload.length;
    }
}

/** Read a File into a data URL. */
function fileToDataURL(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
    });
}

/** SHA-1 hex digest of an arbitrary string — matches the shape Excalidraw
 * uses for internal file ids. Stable across drops of the same bytes. */
async function hashString(input: string): Promise<string> {
    try {
        const bytes = new TextEncoder().encode(input);
        const buf = await window.crypto.subtle.digest('SHA-1', bytes);
        return Array.from(new Uint8Array(buf))
            .map((b) => b.toString(16).padStart(2, '0'))
            .join('');
    } catch (_err) {
        return (
            'fb-' +
            Math.random().toString(36).slice(2) +
            Date.now().toString(36)
        );
    }
}

/** Load an image dataURL and report naturalWidth/Height; defaults to
 * 320x240 on failure so the placement still makes visual sense. */
/** A GIF's size, read from its header — 10 bytes, no decode.
 *
 * `getImageDimensions` below works by setting `Image.src`, which DECODES the
 * file. On a 5 MB animated GIF that is the very main-thread stall this whole
 * interception exists to avoid, and reaching for it here reintroduced the
 * freeze inside the fix for it.
 *
 * The logical screen size lives at bytes 6..9 of every GIF87a/GIF89a, as two
 * little-endian uint16s, immediately after the 6-byte signature. Returns null
 * for anything that is not a GIF, so the caller can fall back.
 */
function gifSizeFromHeader(
    dataUrl: string,
): {width: number; height: number} | null {
    try {
        const comma = dataUrl.indexOf(',');
        if (comma === -1) return null;
        // Only the first 16 bytes are needed: 24 base64 chars cover them.
        const head = atob(dataUrl.slice(comma + 1, comma + 25));
        if (head.slice(0, 3) !== 'GIF') return null;
        const width = head.charCodeAt(6) | (head.charCodeAt(7) << 8);
        const height = head.charCodeAt(8) | (head.charCodeAt(9) << 8);
        if (!width || !height) return null;
        return {width, height};
    } catch (_err) {
        return null;
    }
}

function getImageDimensions(
    dataUrl: string,
): Promise<{width: number; height: number}> {
    return new Promise((resolve) => {
        const img = new Image();
        img.onload = () =>
            resolve({
                width: img.naturalWidth || 320,
                height: img.naturalHeight || 240,
            });
        img.onerror = () => resolve({width: 320, height: 240});
        img.src = dataUrl;
    });
}

/** Build an Excalidraw-compatible image element at a given scene position. */
function makeImageElement(
    fileId: string,
    x: number,
    y: number,
    width: number,
    height: number,
): Record<string, any> {
    const now = Date.now();
    return {
        id: `img-${fileId.slice(0, 10)}-${now}`,
        type: 'image',
        x,
        y,
        width,
        height,
        angle: 0,
        strokeColor: 'transparent',
        backgroundColor: 'transparent',
        fillStyle: 'solid',
        strokeWidth: 1,
        strokeStyle: 'solid',
        roughness: 1,
        opacity: 100,
        seed: Math.floor(Math.random() * 1_000_000),
        version: 1,
        versionNonce: Math.floor(Math.random() * 1_000_000),
        isDeleted: false,
        groupIds: [],
        frameId: null,
        boundElements: [],
        updated: now,
        link: null,
        locked: false,
        status: 'saved',
        fileId,
        scale: [1, 1],
        roundness: null,
    };
}

/** Pick an emoji icon for a non-image file based on mime type / extension. */
function fileIconFor(mimeType: string, fileName: string): string {
    const m = (mimeType || '').toLowerCase();
    const n = (fileName || '').toLowerCase();
    if (m.includes('pdf') || n.endsWith('.pdf')) return '📕';
    if (m.includes('csv') || n.endsWith('.csv')) return '📊';
    if (
        m.includes('spreadsheet') ||
        m.includes('excel') ||
        /\.xlsx?$/.test(n)
    )
        return '📊';
    if (
        m.includes('presentation') ||
        m.includes('powerpoint') ||
        /\.pptx?$/.test(n)
    )
        return '🎞️';
    if (m.includes('msword') || m.includes('officedocument') || /\.docx?$/.test(n))
        return '📘';
    if (m.includes('json') || m.includes('yaml') || /\.(json|ya?ml|toml)$/.test(n))
        return '🗂️';
    if (m.startsWith('audio/')) return '🎵';
    if (m.startsWith('video/')) return '🎬';
    if (m.startsWith('image/')) return '🖼️';
    if (
        m.includes('zip') ||
        m.includes('tar') ||
        m.includes('gzip') ||
        m.includes('compressed') ||
        /\.(zip|tar|gz|7z|rar)$/.test(n)
    )
        return '🗜️';
    if (
        m.startsWith('text/') ||
        m.includes('javascript') ||
        m.includes('typescript') ||
        m.includes('python') ||
        /\.(txt|md|py|js|ts|tsx|jsx|css|html|rb|go|rs|java|c|cpp|h|sh|log)$/.test(n)
    )
        return '📝';
    return '📎';
}

/** Short human-friendly type label, e.g. "CSV", "PDF", "PNG". */
function typeLabelFor(mimeType: string, fileName: string): string {
    if (mimeType && mimeType !== 'application/octet-stream') {
        const tail = mimeType.split('/').pop() || mimeType;
        const compact = tail
            .replace(/^vnd\..*?-/, '')
            .replace(/^x-/, '')
            .replace('officedocument.', '')
            .replace(/;.*/, '');
        return compact.toUpperCase().slice(0, 24);
    }
    const ext = fileName.match(/\.([^.]+)$/)?.[1];
    return (ext || 'FILE').toUpperCase().slice(0, 8);
}

/** Build a grouped file-card placeholder: background rectangle + icon + name
 * + type label. Returns the elements plus the rectangle id (the link target). */
function makePlaceholderElements(
    fileName: string,
    mimeType: string,
    x: number,
    y: number,
): {elements: Record<string, any>[]; rectId: string; width: number; height: number} {
    const now = Date.now();
    const rand = () => Math.random().toString(36).slice(2, 10);
    const groupId = `g-${rand()}-${now}`;
    const rectId = `ph-r-${rand()}-${now}`;
    const iconId = `ph-i-${rand()}-${now}`;
    const nameId = `ph-n-${rand()}-${now}`;
    const metaId = `ph-m-${rand()}-${now}`;
    const badgeId = `ph-b-${rand()}-${now}`;

    const width = 280;
    const height = 200;
    const displayName =
        fileName.length > 26 ? fileName.slice(0, 23) + '…' : fileName;
    const typeLabel = typeLabelFor(mimeType, fileName);
    const icon = fileIconFor(mimeType, fileName);

    const common = {
        angle: 0,
        strokeStyle: 'solid',
        fillStyle: 'solid',
        strokeWidth: 1,
        roughness: 0,
        opacity: 100,
        isDeleted: false,
        frameId: null,
        link: null,
        locked: false,
        updated: now,
        groupIds: [groupId],
        boundElements: [],
        version: 1,
    };
    const seed = () => Math.floor(Math.random() * 1_000_000);

    // Background card
    const rect: Record<string, any> = {
        ...common,
        id: rectId,
        type: 'rectangle',
        x,
        y,
        width,
        height,
        strokeColor: '#4c6ef5',
        backgroundColor: '#edf2ff',
        seed: seed(),
        versionNonce: seed(),
        roundness: {type: 3},
    };

    // Emoji icon — big, top-center
    const iconFontSize = 64;
    const iconW = 100;
    const iconH = iconFontSize * 1.25;
    const iconEl: Record<string, any> = {
        ...common,
        id: iconId,
        type: 'text',
        x: x + (width - iconW) / 2,
        y: y + 18,
        width: iconW,
        height: iconH,
        strokeColor: '#1e3a8a',
        backgroundColor: 'transparent',
        seed: seed(),
        versionNonce: seed(),
        fontSize: iconFontSize,
        fontFamily: 2,
        text: icon,
        textAlign: 'center',
        verticalAlign: 'top',
        containerId: null,
        originalText: icon,
        lineHeight: 1.25,
    };

    // Filename — middle band
    const nameFontSize = 16;
    const nameH = nameFontSize * 1.5;
    const nameEl: Record<string, any> = {
        ...common,
        id: nameId,
        type: 'text',
        x: x + 12,
        y: y + 18 + iconH + 6,
        width: width - 24,
        height: nameH,
        strokeColor: '#1e3a8a',
        backgroundColor: 'transparent',
        seed: seed(),
        versionNonce: seed(),
        fontSize: nameFontSize,
        fontFamily: 2,
        text: displayName,
        textAlign: 'center',
        verticalAlign: 'top',
        containerId: null,
        originalText: displayName,
        lineHeight: 1.25,
    };

    // Small badge-style type label behind the type text for contrast
    const badgeW = Math.min(width - 40, 10 + typeLabel.length * 8 + 10);
    const badgeH = 22;
    const badge: Record<string, any> = {
        ...common,
        id: badgeId,
        type: 'rectangle',
        x: x + (width - badgeW) / 2,
        y: y + 18 + iconH + 6 + nameH + 6,
        width: badgeW,
        height: badgeH,
        strokeColor: '#4c6ef5',
        backgroundColor: '#dbe4ff',
        seed: seed(),
        versionNonce: seed(),
        roundness: {type: 3},
    };

    // Type label inside the badge
    const metaFontSize = 11;
    const metaEl: Record<string, any> = {
        ...common,
        id: metaId,
        type: 'text',
        x: x + (width - badgeW) / 2 + 6,
        y: y + 18 + iconH + 6 + nameH + 6 + 4,
        width: badgeW - 12,
        height: metaFontSize * 1.25,
        strokeColor: '#364fc7',
        backgroundColor: 'transparent',
        seed: seed(),
        versionNonce: seed(),
        fontSize: metaFontSize,
        fontFamily: 3,
        text: typeLabel,
        textAlign: 'center',
        verticalAlign: 'top',
        containerId: null,
        originalText: typeLabel,
        lineHeight: 1.25,
    };

    return {
        elements: [rect, iconEl, nameEl, badge, metaEl],
        rectId,
        width,
        height,
    };
}

/**
 * Produce a variant of a serialized Excalidraw envelope where every
 * `files[*].dataURL` that is still an inline `data:` URI is replaced
 * with `null`. External URLs survive unchanged.
 */
function stripInlineFileUrls(jsonStr: string | undefined): string | undefined {
    if (!jsonStr) return jsonStr;
    try {
        const parsed = JSON.parse(jsonStr);
        if (!parsed || typeof parsed !== 'object') return jsonStr;
        const files = parsed.files;
        if (!files || typeof files !== 'object') return jsonStr;
        const nextFiles: Record<string, any> = {};
        for (const [id, file] of Object.entries(files)) {
            const f = file as any;
            if (
                f &&
                typeof f.dataURL === 'string' &&
                f.dataURL.startsWith('data:')
            ) {
                nextFiles[id] = {...f, dataURL: null};
            } else {
                nextFiles[id] = f;
            }
        }
        return JSON.stringify({...parsed, files: nextFiles});
    } catch (_err) {
        return jsonStr;
    }
}

/**
 * DashExcalidraw is an Excalidraw drawing canvas bound to Dash via a
 * JSON-safe prop surface. See the per-prop docs above for the full
 * catalog; see the README for the command/event round-trip pattern used
 * for imperative actions like exports.
 */
/* ---------------------------------------------------------------------------
 *  The scene a canvas opens with when nobody supplies one.
 * ---------------------------------------------------------------------------
 *
 * DELIBERATELY EMPTY. A default that draws something would put shapes into
 * every canvas in every app that mounts this component without `initialData`,
 * and the first thing each of those authors would have to do is work out how
 * to remove them. "Nothing" is the only default that is never wrong.
 *
 * It exists as a NAMED constant rather than as `undefined` because it is the
 * override point: pass `welcomeScene={...}` — any `{elements, appState,
 * files}` object, including one copied straight out of
 * `externalizedSerializedData` — and that becomes the opening scene instead.
 * /trace-image will hand you one of those as JSON, which is the intended way
 * to author a welcome scene: draw it, or have a model trace it, then paste.
 */
const DEFAULT_WELCOME_SCENE: Record<string, any> | undefined = undefined;

const DashExcalidraw = (props: Props) => {
    const {
        id,
        setProps,
        width = '100%',
        height = '600px',
        initialData,
        viewModeEnabled = false,
        zenModeEnabled = false,
        gridModeEnabled = false,
        isCollaborating = false,
        theme = 'light',
        name,
        welcomeScreen,
        welcomeScreenContent,
        welcomeScene,
        langCode = 'en',
        libraryReturnUrl,
        detectScroll = true,
        handleKeyboardGlobally = true,
        autoFocus = true,
        UIOptions,
        validateEmbeddable,
        command,
        pointerMoveThrottleMs = 50,
        scrollThrottleMs = 100,
        interceptLinkOpens = false,
        hideExcalidrawLinks = true,
        docsLinkUrl = 'https://excalidraw.2plot.dev',
        docsLinkLabel = 'dash-excalidraw docs',
    } = props;

    const [isMounted, setIsMounted] = useState(false);
    const [api, setApi] = useState<any>(null);
    const apiRef = useRef<any>(null);
    // The wrapper element, so a file chosen through the toolbar picker can be
    // re-dispatched onto it as a drop — see the "insert image" effect below.
    const containerRef = useRef<HTMLDivElement | null>(null);
    const lastCommandIdRef = useRef<string | null>(null);
    const pointerMoveLastRef = useRef<number>(0);
    const scrollLastRef = useRef<number>(0);
    // Track file ids we've already emitted `lastFileAdded` for so the
    // event fires exactly once per new file, even across re-renders.
    const knownFileIdsRef = useRef<Set<string>>(new Set());

    useEffect(() => {
        setIsMounted(true);
    }, []);

    const writeProps = useCallback(
        (patch: Record<string, any>) => {
            if (setProps) setProps(patch);
        },
        [setProps],
    );

    /* --------- validateEmbeddable: compile string allowlist to RegExp[] --- */
    const validateEmbeddableResolved = useMemo(() => {
        if (validateEmbeddable === undefined) return undefined;
        if (typeof validateEmbeddable === 'boolean') return validateEmbeddable;
        if (Array.isArray(validateEmbeddable)) {
            return validateEmbeddable.map(globToRegex);
        }
        return undefined;
    }, [validateEmbeddable]);

    /* --------- the scene the canvas opens with ---------------------------
     * `initialData` wins; then `welcomeScene`; then the shipped default. All
     * three are MOUNT-ONLY, which is Excalidraw's rule and not ours: it owns
     * the scene once it has one. Computed once so a re-render cannot hand the
     * canvas a different opening scene halfway through its life.
     */
    const openingScene = useMemo(
        () => initialData ?? welcomeScene ?? DEFAULT_WELCOME_SCENE,
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [],
    );

    /* --------- name: keep appState in step with the prop ------------------
     * Excalidraw seeds `appState.name` from the `name` prop while mounting
     * and then stops looking, so changing it later moved the prop and left
     * the scene still called by its old name — including in the export
     * dialog's filename, which is the one place the name is visible.
     * MEASURED: prop "renamed-scene" against appState.name "coverage-scene".
     */
    useEffect(() => {
        if (name === undefined) return;
        const api = apiRef.current;
        if (!api) return;
        const current = api.getAppState?.();
        if (current && current.name === name) return;
        api.updateScene({
            appState: {name},
            captureUpdate: CaptureUpdateAction.NEVER,
        } as any);
    }, [name, api]);

    /* --------- effective UIOptions: welcomeScreen defaults to false ------- */
    const resolvedUIOptions = useMemo<UIOptionsShape>(() => {
        const base = UIOptions || {};
        const {canvasActions, ...rest} = base;
        // Excalidraw 0.17.6 tries to set `saveFileToDisk` on
        // `canvasActions.export` directly, which throws when `export === true`
        // (you can't set properties on a primitive). Normalize a bare boolean
        // `true` to the object form it expects.
        const normalizedExport =
            canvasActions?.export === true
                ? {saveFileToDisk: true}
                : canvasActions?.export;
        const normalizedCanvasActions =
            canvasActions === undefined
                ? undefined
                : {
                      ...canvasActions,
                      ...(normalizedExport !== undefined
                          ? {export: normalizedExport}
                          : {}),
                  };
        return {
            welcomeScreen: false,
            ...rest,
            ...(normalizedCanvasActions !== undefined
                ? {canvasActions: normalizedCanvasActions}
                : {}),
        };
    }, [UIOptions]);

    /* --------- the two menu gates the vendor applies at the call site ----
     * Most default menu items decide for themselves and return null when
     * their action is off. `Export` and `SaveAsImage` do not: the vendor
     * gates them where it composes the menu, so composing our own means
     * replicating exactly these two — otherwise /ui-options' `export` and
     * `saveAsImage` switches would go quiet without anything failing.
     * `undefined` means "not set", which is Excalidraw's own default of on;
     * only an explicit `false` hides the item. `export` may have been
     * normalised to `{saveFileToDisk: true}` above, which is still on.
     */
    const showExportItem = resolvedUIOptions?.canvasActions?.export !== false;
    const showSaveAsImageItem =
        resolvedUIOptions?.canvasActions?.saveAsImage !== false;

    /* --------- onChange: elements / appState / files / serialized / ver --- */
    const handleChange = useCallback(
        (
            elements: ReadonlyArray<ExcalidrawElement>,
            nextAppState: AppState,
            nextFiles: BinaryFiles,
        ) => {
            let serialized: string | undefined;
            try {
                serialized = serializeAsJSON(
                    elements as any,
                    nextAppState as any,
                    nextFiles as any,
                    'local' as any,
                );
            } catch (_err) {
                serialized = undefined;
            }
            const externalized = stripInlineFileUrls(serialized);
            /* `getSceneVersion` is a STANDALONE EXPORT of the package that
             * takes the elements — it is NOT a method on the imperative API.
             * This read used to be `apiRef.current?.getSceneVersion()` behind a
             * `typeof === 'function'` guard, so it was always undefined and the
             * guard made that silent: `sceneVersion` never once reached Python,
             * and any callback with it as an Input never fired. /coverage's
             * whole read-only panel is such a callback, which is why its
             * appState, its file ids and its scene version all sat at null
             * however much you drew — three symptoms, this one cause. */
            let sceneVersion: number | undefined;
            try {
                sceneVersion = getSceneVersion(elements as any);
            } catch (_err) {
                sceneVersion = undefined;
            }

            // Detect new files with inline base64 that still need uploading.
            // Only the first such file becomes `lastFileAdded` per change;
            // callers who need batch visibility watch `files` directly.
            const patch: Record<string, any> = {
                elements,
                appState: nextAppState,
                files: nextFiles,
                serializedData: serialized,
                externalizedSerializedData: externalized,
                sceneVersion,
            };
            const currentIds = new Set(Object.keys(nextFiles || {}));
            const newEntries: Array<{
                fileId: string;
                mimeType: string;
                dataURL: string;
                size: number;
            }> = [];
            for (const id of currentIds) {
                if (knownFileIdsRef.current.has(id)) continue;
                const fileData = (nextFiles as any)?.[id];
                const url = fileData?.dataURL;
                if (typeof url === 'string' && url.startsWith('data:')) {
                    newEntries.push({
                        fileId: id,
                        mimeType: fileData.mimeType,
                        dataURL: url,
                        size: dataUrlByteSize(url),
                    });
                }
            }
            knownFileIdsRef.current = currentIds;
            if (newEntries.length > 0) {
                const first = newEntries[0];
                patch.lastFileAdded = {
                    timestamp: Date.now(),
                    fileId: first.fileId,
                    mimeType: first.mimeType,
                    dataURL: first.dataURL,
                    size: first.size,
                    files: newEntries,
                };
            }
            writeProps(patch);
        },
        [writeProps],
    );

    /* --------- pointer events -------------------------------------------- */
    const handlePointerDown = useCallback(
        (activeTool: any, pointerDownState: any) => {
            writeProps({
                lastPointerDown: {
                    timestamp: Date.now(),
                    activeTool,
                    pointer: pointerDownState?.origin ?? null,
                },
            });
        },
        [writeProps],
    );

    // pointerUp is exposed as an API subscriber (not a component prop)
    // in Excalidraw 0.17+. Subscribe once the api becomes available.
    useEffect(() => {
        if (!api || typeof api.onPointerUp !== 'function') return;
        const unsubscribe = api.onPointerUp(
            (activeTool: any, pointerDownState: any) => {
                writeProps({
                    lastPointerUp: {
                        timestamp: Date.now(),
                        activeTool,
                        pointer: pointerDownState?.origin ?? null,
                    },
                });
            },
        );
        return () => {
            if (typeof unsubscribe === 'function') unsubscribe();
        };
    }, [api, writeProps]);

    const handlePointerUpdate = useCallback(
        (payload: {pointer: PointerCoords; button: string; pointersMap: any}) => {
            const now = Date.now();
            if (now - pointerMoveLastRef.current < pointerMoveThrottleMs) return;
            pointerMoveLastRef.current = now;
            writeProps({
                lastPointerMove: {
                    timestamp: now,
                    pointer: payload?.pointer,
                    button: payload?.button,
                },
            });
        },
        [writeProps, pointerMoveThrottleMs],
    );

    const handleScrollChange = useCallback(
        (scrollX: number, scrollY: number) => {
            const now = Date.now();
            if (now - scrollLastRef.current < scrollThrottleMs) return;
            scrollLastRef.current = now;
            writeProps({
                lastScrollChange: {timestamp: now, scrollX, scrollY},
            });
        },
        [writeProps, scrollThrottleMs],
    );

    const handlePaste = useCallback(
        (data: any, _event: ClipboardEvent | null) => {
            writeProps({
                lastPaste: {timestamp: Date.now(), data},
            });
            return true;
        },
        [writeProps],
    );

    const handleLibraryChange = useCallback(
        (items: LibraryItem[]) => {
            writeProps({
                lastLibraryChange: {timestamp: Date.now(), items},
            });
        },
        [writeProps],
    );

    const handleLinkOpen = useCallback(
        (element: any, event: any) => {
            if (interceptLinkOpens && event && typeof event.preventDefault === 'function') {
                event.preventDefault();
            }
            writeProps({
                lastLinkOpen: {
                    timestamp: Date.now(),
                    elementId: element?.id,
                    url: element?.link,
                },
            });
        },
        [writeProps, interceptLinkOpens],
    );

    /* --------- wrapper-level drop handler --------------------------------
       Excalidraw 0.17.6's native onDrop only consumes the first image of a
       drop and silently ignores non-image files. We intercept at the
       capture phase for:
        - multi-file drops (any count > 1)
        - single non-image drops
       Single-image drops pass through to Excalidraw for the native UX. */
    const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
        if (e.dataTransfer?.types?.includes?.('Files')) {
            e.preventDefault();
        }
    }, []);

    const handleDropCapture = useCallback(
        async (e: React.DragEvent<HTMLDivElement>) => {
            const fileList = e.dataTransfer?.files;
            if (!fileList || fileList.length === 0) return;
            const files = Array.from(fileList);
            /* ANIMATED GIFs ARE NOT "just an image" HERE.
             *
             * Excalidraw rasterises a dropped GIF to a single still frame
             * before anything downstream can see it. MEASURED: a 123,069-byte
             * GIF89a of 12 frames arrives at `lastFileAdded` as a 2,820-byte
             * PNG with none. So an app that uploads what it is given and
             * frames it in an iframe is framing a still — the animation was
             * lost at the drop, not at the embed, and no storage or embed
             * change can recover it.
             *
             * The rasterisation is also what freezes the tab: a 5.17 MB
             * 600x600x20 GIF left the renderer unable to answer a debugger
             * evaluation at all, twice, while the server sat idle at 32
             * callbacks and logged nothing. It is decode work on the main
             * thread, not I/O. (Timer sampling is useless for this — a
             * backgrounded tab is throttled to ~1s and an idle page reports
             * the same lag as a wedged one.)
             *
             * So a GIF is taken down the SAME path as a .txt or a .pdf: the
             * original bytes reach Python verbatim on `lastExternalDrop`, and
             * the app decides what to put on the canvas — an embeddable
             * pointing at storage, in /file-uploads' case. Excalidraw never
             * sees it as an image and never decodes it.
             */
            /* Type OR extension. A drag from a file manager usually sets
             * `type`, but a drag out of another browser window, some Linux
             * desktops, and anything re-wrapped by an OS share sheet can hand
             * over an empty string — and a GIF that misses this check goes
             * straight back to Excalidraw to be rasterised, which is the
             * failure this is guarding. The magic bytes are checked later,
             * where they are already in hand. */
            const isAnimatable = (f: File) =>
                (f.type || '').toLowerCase() === 'image/gif' ||
                /\.gif$/i.test(f.name || '');
            const singleImage =
                files.length === 1 &&
                (files[0].type || '').startsWith('image/') &&
                !isAnimatable(files[0]);
            if (singleImage) return; // let Excalidraw handle

            // We're taking the drop. Prevent native drop + stop Excalidraw.
            e.preventDefault();
            e.stopPropagation();

            if (files.some(isAnimatable)) {
                // Visible confirmation that the GIF path is live. Without it,
                // "the fix is not working" and "the browser is running an old
                // bundle" look identical from the outside.
                // eslint-disable-next-line no-console
                console.info(
                    '[dash-excalidraw] GIF drop intercepted — original bytes ' +
                    'kept, Excalidraw will not rasterise it.',
                );
            }

            const currentApi = apiRef.current;
            if (!currentApi) return;

            // Translate client coords into scene coords.
            const rect = (
                e.currentTarget as HTMLDivElement
            ).getBoundingClientRect();
            const appStateSnap = currentApi.getAppState?.() || {};
            const zoom = appStateSnap.zoom?.value ?? 1;
            const scrollX = appStateSnap.scrollX ?? 0;
            const scrollY = appStateSnap.scrollY ?? 0;
            const dropX = (e.clientX - rect.left) / zoom - scrollX;
            const dropY = (e.clientY - rect.top) / zoom - scrollY;

            // Read all files in parallel.
            const loaded = await Promise.all(
                files.map(async (f) => {
                    const dataURL = await fileToDataURL(f);
                    /* SNIFF, DO NOT TRUST. A drag can arrive with `type`
                     * empty — measured: a GIF dropped that way was stored as
                     * `.bin` with mime application/octet-stream, so Python
                     * could not tell it was a GIF and never made the embed.
                     * The magic bytes are already in hand here, and they are
                     * the only thing that actually knows.
                     *
                     * The dataURL's own prefix is rewritten too, because
                     * Python reads the mime back out of it. */
                    const gifSize = gifSizeFromHeader(dataURL);
                    const sniffed = gifSize ? 'image/gif' : '';
                    const mimeType =
                        sniffed || f.type || 'application/octet-stream';
                    const corrected = sniffed
                        ? `data:${sniffed};base64,${dataURL.slice(
                              dataURL.indexOf(',') + 1,
                          )}`
                        : dataURL;
                    return {
                        file: f,
                        name: f.name,
                        mimeType,
                        size: f.size,
                        dataURL: corrected,
                        naturalSize: gifSize,
                        // A GIF is deliberately NOT an "image" for placement:
                        // it goes down the payload path so its bytes survive.
                        isImage:
                            (f.type || '').startsWith('image/') &&
                            !isAnimatable(f) &&
                            !gifSize,
                        isAnimatable: isAnimatable(f) || Boolean(gifSize),
                    };
                }),
            );

            const newFileEntries: any[] = [];
            const newElements: any[] = [];
            const placeholderIds: string[] = [];
            const nonImagePayload: any[] = [];

            let cursorX = dropX;
            let cursorY = dropY;
            const gap = 20;
            let rowMaxHeight = 0;

            for (const item of loaded) {
                if (item.isImage) {
                    const dims = await getImageDimensions(item.dataURL);
                    const maxSide = 400;
                    const scale = Math.min(
                        1,
                        maxSide / Math.max(dims.width, dims.height),
                    );
                    const w = dims.width * scale;
                    const h = dims.height * scale;
                    const fileId = await hashString(item.dataURL);
                    newFileEntries.push({
                        id: fileId,
                        mimeType: item.mimeType,
                        dataURL: item.dataURL,
                        created: Date.now(),
                    });
                    newElements.push(
                        makeImageElement(fileId, cursorX, cursorY, w, h),
                    );
                    cursorX += w + gap;
                    rowMaxHeight = Math.max(rowMaxHeight, h);
                } else {
                    const placeholder = makePlaceholderElements(
                        item.name,
                        item.mimeType,
                        cursorX,
                        cursorY,
                    );
                    newElements.push(...placeholder.elements);
                    placeholderIds.push(placeholder.rectId);
                    /* A GIF's real dimensions travel with it. The app puts an
                     * embeddable where the placeholder was, and an iframe at
                     * the placeholder's size would letterbox the animation. */
                    // Read from the header when the bytes were sniffed,
                    // never via getImageDimensions: that sets Image.src and
                    // decodes the whole animation.
                    const naturalSize = item.naturalSize;
                    nonImagePayload.push({
                        name: item.name,
                        mimeType: item.mimeType,
                        dataURL: item.dataURL,
                        size: item.size,
                        placeholderId: placeholder.rectId,
                        ...(naturalSize ? {naturalSize} : {}),
                    });
                    cursorX += placeholder.width + gap;
                    rowMaxHeight = Math.max(rowMaxHeight, placeholder.height);
                }
                // Wrap every ~1200 px so rows don't shoot off-screen.
                if (cursorX - dropX > 1200) {
                    cursorX = dropX;
                    cursorY += rowMaxHeight + gap;
                    rowMaxHeight = 0;
                }
            }

            if (newFileEntries.length > 0) currentApi.addFiles(newFileEntries);
            if (newElements.length > 0) {
                const existing = currentApi.getSceneElements?.() || [];
                // Run the new partial elements through Excalidraw's own
                // normalizer so text `baseline`, `autoResize`, version ids
                // and other internals are populated. Without this, custom
                // text elements render empty until the user interacts with
                // them (click + resize triggers Excalidraw's re-measure).
                let restored: any[] = newElements;
                try {
                    restored = restoreElements(newElements as any, null) as any[];
                } catch (_err) {
                    // Fallback: use as-is if restoreElements isn't available
                    // or rejects our partial shape. Better a degraded render
                    // than a crash.
                }
                currentApi.updateScene({
                    elements: [...existing, ...restored],
                });
            }

            if (nonImagePayload.length > 0) {
                writeProps({
                    lastExternalDrop: {
                        timestamp: Date.now(),
                        files: nonImagePayload.map(
                            ({placeholderId, ...rest}) => rest,
                        ),
                        dropPoint: {x: dropX, y: dropY},
                        placeholderIds,
                    },
                });
            }
        },
        [writeProps],
    );

    /* --------- the toolbar's "insert image" button -------------------------
     *
     * A GIF DROPPED on the canvas takes the interception above and keeps its
     * frames. The same GIF chosen through the toolbar's image tool did not,
     * and that is not a second bug — it is a second DOOR. Excalidraw opens
     * the picker with `fileOpen` from browser-fs-access, which uses
     * `window.showOpenFilePicker` where it exists (Chrome) and falls back to
     * a hidden `<input type="file">` elsewhere. Neither passes through the
     * drop handler.
     *
     * So both doors are covered, and both lead to the same room: the chosen
     * GIF is re-dispatched as a synthetic drop on this container, which runs
     * the path that is already proven, rather than a second copy of it that
     * could drift.
     *
     * Excalidraw is then told the user picked nothing — an AbortError is
     * exactly what a cancelled picker throws, so it takes that quietly. Any
     * non-GIF selection is passed straight through untouched.
     */
    useEffect(() => {
        const isGif = (f: {name?: string; type?: string} | null | undefined) =>
            Boolean(
                f &&
                    ((f.type || '').toLowerCase() === 'image/gif' ||
                        /\.gif$/i.test(f.name || '')),
            );

        const redispatchAsDrop = (gifs: File[]) => {
            const host = containerRef.current;
            if (!host || gifs.length === 0) return;
            const transfer = new DataTransfer();
            for (const f of gifs) transfer.items.add(f);
            const rect = host.getBoundingClientRect();
            host.dispatchEvent(
                new DragEvent('drop', {
                    bubbles: true,
                    cancelable: true,
                    clientX: rect.left + rect.width / 2,
                    clientY: rect.top + rect.height / 2,
                    dataTransfer: transfer,
                }),
            );
        };

        // --- door 1: the File System Access API (Chrome) ---
        const realPicker = (window as any).showOpenFilePicker;
        if (typeof realPicker === 'function') {
            (window as any).showOpenFilePicker = async (...args: any[]) => {
                const handles = await realPicker.apply(window, args);
                let files: File[] = [];
                try {
                    files = await Promise.all(
                        handles.map((h: any) => h.getFile()),
                    );
                } catch (_err) {
                    return handles; // cannot inspect them; do not interfere
                }
                const gifs = files.filter(isGif);
                if (gifs.length === 0) return handles;
                redispatchAsDrop(gifs);
                const rest = handles.filter(
                    (_h: any, i: number) => !isGif(files[i]),
                );
                if (rest.length === 0) {
                    throw new DOMException('aborted', 'AbortError');
                }
                return rest;
            };
        }

        // --- door 2: the <input type="file"> fallback ---
        const onChange = (event: Event) => {
            const input = event.target as HTMLInputElement | null;
            if (!input || input.type !== 'file' || !input.files) return;
            const chosen = Array.from(input.files);
            const gifs = chosen.filter(isGif);
            if (gifs.length === 0) return;
            // Capture phase: this runs before the library's own handler, so
            // stopping it here is what prevents the rasterisation.
            event.stopPropagation();
            event.preventDefault();
            input.value = '';
            redispatchAsDrop(gifs);
        };
        document.addEventListener('change', onChange, true);

        return () => {
            if (typeof realPicker === 'function') {
                (window as any).showOpenFilePicker = realPicker;
            }
            document.removeEventListener('change', onChange, true);
        };
    }, []);

    /* --------- command dispatch ------------------------------------------ */
    useEffect(() => {
        if (!command || !command.id) return;
        if (command.id === lastCommandIdRef.current) return;

        const api = apiRef.current;
        // Claim the id only once the canvas can actually service the command.
        // Marking it consumed first — as this did — dropped any command
        // dispatched before Excalidraw's `excalidrawAPI` callback had fired:
        // the `finally` that clears `command` lives inside `run()`, which this
        // early return never reaches, so `command` stayed set while its id was
        // already burned, and the id guard above then rejected every retry.
        // A callback that dispatches on page load hits exactly that window.
        // `api` (the state set alongside `apiRef`) is in the dependency list
        // so this effect re-runs the moment the canvas is ready.
        if (!api) return;

        lastCommandIdRef.current = command.id;

        const {id: commandId, type, payload} = command;

        const sceneExportArgs = () => {
            const els = api.getSceneElements();
            const state = api.getAppState();
            const f = api.getFiles();
            return {elements: els, appState: state, files: f};
        };

        const run = async () => {
            try {
                switch (type) {
                    case 'updateScene': {
                        const scenePayload: Record<string, any> = {
                            ...(payload || {}),
                        };

                        /* ---- embeddable links must be ABSOLUTE ----------
                         * An `embeddable` carries its src in `link`, and
                         * Excalidraw parses that as a full URL. A Dash app
                         * naturally produces app-relative ones — Flask's
                         * url_for, a route prefix, `/excalidraw-files/<id>` —
                         * and a relative link is DROPPED on restore: the
                         * element survives, `link` does not, and the canvas
                         * shows an empty box with no iframe and no error.
                         * MEASURED on /file-uploads' GIF auto-embed, whose
                         * whole point is that iframe.
                         *
                         * Resolved against the page's own origin, which is
                         * where such a path was always going to point.
                         *
                         * KNOWN AND NOT FIXABLE HERE: an embeddable always
                         * draws above every ordinary element, whatever the
                         * scene order says. Measured in the DOM —
                         * `.excalidraw__canvas.static` (every shape, image and
                         * text, painted into ONE bitmap) is z-index 1, and
                         * `.excalidraw__embeddable-container` (the iframes) is
                         * z-index 2. Scene order decides painting WITHIN the
                         * bitmap; it cannot lift part of it above a DOM
                         * sibling in a higher layer. "Bring to front" on a
                         * shape therefore does nothing against an embed.
                         */
                        if (Array.isArray(scenePayload.elements)) {
                            scenePayload.elements = scenePayload.elements.map(
                                (el: any) => {
                                    if (
                                        !el ||
                                        el.type !== 'embeddable' ||
                                        typeof el.link !== 'string' ||
                                        !el.link.startsWith('/')
                                    ) {
                                        return el;
                                    }
                                    return {
                                        ...el,
                                        link: new URL(
                                            el.link,
                                            window.location.origin,
                                        ).href,
                                    };
                                },
                            );
                        }

                        /* ---- history semantics -------------------------
                         * 0.17 left history untouched when no flag was
                         * given. 0.18 defaults to EVENTUALLY, which folds
                         * the update into the NEXT captured action — so a
                         * user's first undo after a Python-dispatched push
                         * would also roll back their own prior edit.
                         * Nothing errors and nothing warns; the behaviour
                         * just changes. We default to IMMEDIATELY: a
                         * dispatched scene push is a deliberate edit and
                         * should undo as one discrete step.
                         */
                        if ('commitToHistory' in scenePayload) {
                            if (!warnedCommitToHistory) {
                                warnedCommitToHistory = true;
                                console.warn(
                                    '[DashExcalidraw] `commitToHistory` was removed in ' +
                                        'Excalidraw 0.18 and is being translated to ' +
                                        '`captureUpdate`. Pass captureUpdate as ' +
                                        '"IMMEDIATELY", "NEVER" or "EVENTUALLY" instead.',
                                );
                            }
                            if (scenePayload.captureUpdate === undefined) {
                                scenePayload.captureUpdate = scenePayload
                                    .commitToHistory
                                    ? 'IMMEDIATELY'
                                    : 'NEVER';
                            }
                            delete scenePayload.commitToHistory;
                        }

                        const requestedCapture = scenePayload.captureUpdate;
                        // Explicit allowlist rather than an object index:
                        // `CaptureUpdateAction[x]` with an attacker- or
                        // typo-supplied `x` such as "constructor" returns a
                        // truthy function, which would sail through the
                        // fallback check below and reach Excalidraw.
                        const CAPTURE_VALUES: Record<string, string> = {
                            IMMEDIATELY: CaptureUpdateAction.IMMEDIATELY,
                            NEVER: CaptureUpdateAction.NEVER,
                            EVENTUALLY: CaptureUpdateAction.EVENTUALLY,
                        };
                        const resolvedCapture =
                            requestedCapture === undefined
                                ? CaptureUpdateAction.IMMEDIATELY
                                : Object.prototype.hasOwnProperty.call(
                                      CAPTURE_VALUES,
                                      requestedCapture,
                                  )
                                ? CAPTURE_VALUES[requestedCapture]
                                : undefined;

                        if (requestedCapture !== undefined && !resolvedCapture) {
                            // Do not silently accept a typo — it would look
                            // like the caller's history choice took effect.
                            if (!warnedBadCaptureUpdate) {
                                warnedBadCaptureUpdate = true;
                                console.warn(
                                    `[DashExcalidraw] Unknown captureUpdate ` +
                                        `"${requestedCapture}". Expected "IMMEDIATELY", ` +
                                        `"NEVER" or "EVENTUALLY". Falling back to ` +
                                        `"IMMEDIATELY".`,
                                );
                            }
                        }
                        scenePayload.captureUpdate =
                            resolvedCapture || CaptureUpdateAction.IMMEDIATELY;

                        /* ---- collaborators ----------------------------
                         * A TOP-LEVEL SceneData field in 0.18; 0.17 read it
                         * off appState. Accept either spelling from Python
                         * and normalise to a top-level Map — Excalidraw
                         * iterates it during render, so a plain JSON object
                         * makes `Map.forEach` throw.
                         */
                        const rawCollaborators =
                            scenePayload.collaborators ??
                            scenePayload.appState?.collaborators;

                        if (rawCollaborators) {
                            scenePayload.collaborators =
                                rawCollaborators instanceof Map
                                    ? rawCollaborators
                                    : new Map(Object.entries(rawCollaborators));
                        }
                        if (
                            scenePayload.appState &&
                            'collaborators' in scenePayload.appState
                        ) {
                            const {
                                collaborators: _movedToTopLevel,
                                ...restAppState
                            } = scenePayload.appState;
                            scenePayload.appState = restAppState;
                        }

                        // Normalize any incoming elements through
                        // `restoreElements` so text baselines, autoResize,
                        // version ids, and other internals are populated.
                        // Without this, AI-generated text elements render
                        // invisibly until the user clicks / resizes them.
                        if (
                            Array.isArray(scenePayload.elements) &&
                            scenePayload.elements.length > 0
                        ) {
                            try {
                                /* `restoreElements` DISCARDS the `link` of an
                                 * embeddable. It has no access to this
                                 * component's `validateEmbeddable` prop, so it
                                 * cannot know the URL is allowed and drops it
                                 * — the element survives, its src does not,
                                 * and the canvas draws an empty box with no
                                 * iframe and nothing logged. MEASURED on
                                 * /file-uploads: the scene kept a
                                 * `type: "embeddable"` element with no `link`
                                 * key at all.
                                 *
                                 * The restore is still wanted (text baselines,
                                 * autoResize, version ids — without it
                                 * generated text renders invisibly), so put
                                 * the links back rather than skip it. */
                                const linksById = new Map<string, string>();
                                for (const el of scenePayload.elements as any[]) {
                                    if (
                                        el &&
                                        el.type === 'embeddable' &&
                                        typeof el.link === 'string' &&
                                        el.link
                                    ) {
                                        linksById.set(el.id, el.link);
                                    }
                                }
                                scenePayload.elements = (
                                    restoreElements(
                                        scenePayload.elements as any,
                                        null,
                                    ) as any[]
                                ).map((el: any) => {
                                    const link = linksById.get(el?.id);
                                    return link && !el.link ? {...el, link} : el;
                                }) as any;
                            } catch (_err) {
                                // Fall through with raw elements if the
                                // restorer refuses — better a degraded
                                // render than a crash.
                            }
                        }
                        api.updateScene(scenePayload);
                        break;
                    }
                    case 'addFiles':
                        api.addFiles(payload || []);
                        /* `addFiles` registers bytes WITHOUT touching any
                         * element, so Excalidraw fires no onChange for it and
                         * the `files` prop would never mention the file that
                         * was just added. The command worked and Python could
                         * not tell — which is indistinguishable from it having
                         * failed, and is exactly how it was read. Push the
                         * store ourselves so a caller can see the result of
                         * the thing it just dispatched. */
                        writeProps({files: api.getFiles()});
                        break;
                    case 'resetScene': {
                        api.resetScene(payload || {});
                        /* `resetScene` restores Excalidraw's DEFAULT appState,
                         * which silently discards every mode this component
                         * controls. MEASURED on a `viewModeEnabled` canvas: 1
                         * toolbar button before, 17 after — the canvas became
                         * editable with nothing said, and then snapped back to
                         * view-only on the next React re-render, stranding
                         * whatever had been drawn in the meantime. /trace-image
                         * resets the scene at the start of every trace, so this
                         * happened on the ordinary path, not an edge case.
                         *
                         * Re-assert what the props say. Excalidraw is the owner
                         * of the scene, but these flags are ours. */
                        api.updateScene({
                            appState: {
                                viewModeEnabled,
                                zenModeEnabled,
                                gridModeEnabled,
                                ...(name !== undefined ? {name} : {}),
                                ...(theme !== undefined ? {theme} : {}),
                            },
                            captureUpdate: CaptureUpdateAction.NEVER,
                        } as any);
                        break;
                    }
                    case 'scrollToContent':
                        api.scrollToContent(payload?.target, payload?.opts);
                        break;
                    case 'setActiveTool':
                        api.setActiveTool(payload || {type: 'selection'});
                        break;
                    case 'setToast':
                        api.setToast(payload ?? null);
                        break;
                    case 'toggleSidebar': {
                        /* Returns FALSE when the named sidebar does not
                         * exist, and that silence is how this bit two of our
                         * own pages: `name` is the SIDEBAR ("default" for the
                         * built-in one) while "library" and "search" are TABS
                         * inside it, so `{name: "library"}` addressed nothing
                         * and reported nothing. Say so rather than let a
                         * dispatched command vanish. */
                        const opened = api.toggleSidebar(payload || {});
                        if (opened === false) {
                            // eslint-disable-next-line no-console
                            console.warn(
                                '[dash-excalidraw] toggleSidebar did nothing: no sidebar named',
                                JSON.stringify((payload || {}).name),
                                '— the built-in sidebar is "default"; "library" and "search" are tabs',
                                'within it, so pass {name: "default", tab: "library"}.',
                            );
                        }
                        break;
                    }
                    case 'updateLibrary':
                        await api.updateLibrary(payload || {});
                        break;
                    case 'replaceFiles': {
                        /* payload: { [fileId]: { dataURL, mimeType? } }
                         *
                         * MEASURED IN THE BROWSER, because the obvious
                         * implementation is a silent no-op: `api.addFiles`
                         * with an id the store ALREADY holds does nothing at
                         * all. Add id `x` with an inline dataURL, add `x`
                         * again with an external URL, read `getFiles()` — it
                         * is still the inline one. There is no removeFiles,
                         * and `updateScene({files})` is ignored too; the whole
                         * imperative surface for files is addFiles/getFiles.
                         *
                         * So in-place replacement is not available, and this
                         * command used to claim it: /file-uploads uploaded
                         * every drop, dispatched replaceFiles, and the canvas
                         * kept the base64 — which is why its GIF auto-embed
                         * never fired. The page watches for a file whose
                         * dataURL has become an external URL and there never
                         * was one.
                         *
                         * What works: store the new bytes under a NEW id and
                         * repoint the elements at it. The element ends up
                         * referencing an entry whose dataURL is the external
                         * URL, which is what every consumer actually wants.
                         * The orphaned inline entry cannot be deleted (no
                         * API), but nothing references it and
                         * `externalizedSerializedData` strips it regardless.
                         */
                        const entries = payload || {};
                        const remap: Record<string, string> = {};
                        const additions: any[] = [];
                        const stamp = Date.now();
                        for (const [oldId, info] of Object.entries(
                            entries as Record<string, any>,
                        )) {
                            if (!info || typeof info.dataURL !== 'string') {
                                continue;
                            }
                            const newId = `${oldId}-ext-${stamp.toString(36)}`;
                            remap[oldId] = newId;
                            additions.push({
                                id: newId,
                                mimeType: info.mimeType || 'image/png',
                                dataURL: info.dataURL,
                                created: stamp,
                            });
                        }
                        if (additions.length > 0) {
                            api.addFiles(additions);
                            const repointed = (api.getSceneElements() || []).map(
                                (el: any) =>
                                    el &&
                                    el.type === 'image' &&
                                    el.fileId &&
                                    remap[el.fileId]
                                        ? {...el, fileId: remap[el.fileId]}
                                        : el,
                            );
                            api.updateScene({
                                elements: repointed,
                                captureUpdate: CaptureUpdateAction.NEVER,
                            } as any);
                            /* Report the store: swapping bytes touches no
                             * element in a way Excalidraw reports, so without
                             * this the `files` prop never mentions the new
                             * entry and any callback watching it never runs. */
                            writeProps({files: api.getFiles()});
                        }
                        break;
                    }
                    case 'exportToSvg': {
                        const svg = await exportToSvg({
                            ...sceneExportArgs(),
                            ...(payload || {}),
                        } as any);
                        writeProps({
                            lastExport: {
                                timestamp: Date.now(),
                                id: commandId,
                                type,
                                result: svg?.outerHTML ?? null,
                            },
                        });
                        break;
                    }
                    case 'exportToBlob': {
                        const blob = await exportToBlob({
                            ...sceneExportArgs(),
                            ...(payload || {}),
                        } as any);
                        const base64 = await blobToBase64(blob);
                        writeProps({
                            lastExport: {
                                timestamp: Date.now(),
                                id: commandId,
                                type,
                                result: base64,
                                mimeType: payload?.mimeType || 'image/png',
                            },
                        });
                        break;
                    }
                    case 'exportToCanvas': {
                        const canvas = await exportToCanvas({
                            ...sceneExportArgs(),
                            ...(payload || {}),
                        } as any);
                        const dataUrl = canvas.toDataURL(payload?.mimeType || 'image/png');
                        writeProps({
                            lastExport: {
                                timestamp: Date.now(),
                                id: commandId,
                                type,
                                result: dataUrl,
                            },
                        });
                        break;
                    }
                    default:
                        // Unknown command types are ignored silently; log for devs.
                        // eslint-disable-next-line no-console
                        console.warn('[dash-excalidraw] unknown command.type:', type);
                }
            } catch (err) {
                writeProps({
                    lastExport: {
                        timestamp: Date.now(),
                        id: commandId,
                        type,
                        result: null,
                        error: String(err),
                    },
                });
            } finally {
                // Clear the command so React re-renders do not re-fire.
                writeProps({command: null});
            }
        };

        void run();
        // `api` is the state written beside `apiRef` in the `excalidrawAPI`
        // callback. It is here, not read here, on purpose: it turns "the
        // canvas became ready" into a re-run so a command that arrived early
        // is dispatched instead of dropped. Inside the body `api` is the ref
        // read, which is what the async `run()` must use to avoid a stale
        // closure; the dependency list resolves to the state in the scope above.
    }, [command, api, writeProps]);

    /* --------- render ---------------------------------------------------- */
    if (!isMounted) {
        return <div id={id} style={{width, height}} />;
    }

    return (
        <div
            id={id}
            ref={containerRef}
            style={{width, height, position: 'relative'}}
            onDragOver={handleDragOver}
            onDropCapture={handleDropCapture}
        >
            <Excalidraw
                excalidrawAPI={(a: any) => {
                    apiRef.current = a;
                    setApi(a);
                }}
                initialData={openingScene as any}
                viewModeEnabled={viewModeEnabled}
                zenModeEnabled={zenModeEnabled}
                gridModeEnabled={gridModeEnabled}
                isCollaborating={isCollaborating}
                theme={theme as any}
                name={name}
                langCode={langCode}
                libraryReturnUrl={libraryReturnUrl}
                detectScroll={detectScroll}
                handleKeyboardGlobally={handleKeyboardGlobally}
                autoFocus={autoFocus}
                UIOptions={resolvedUIOptions as any}
                validateEmbeddable={validateEmbeddableResolved as any}
                onChange={handleChange}
                onPointerDown={handlePointerDown}
                onPointerUpdate={handlePointerUpdate as any}
                onScrollChange={handleScrollChange as any}
                onPaste={handlePaste as any}
                onLibraryChange={handleLibraryChange as any}
                onLinkOpen={handleLinkOpen as any}
            >
                {/*
                 * OUR OWN MAIN MENU, mirroring the vendor's `DefaultMainMenu`
                 * verbatim — same items, same order, same gates. See
                 * node_modules/@excalidraw/excalidraw/dist/dev/index.js,
                 * `var DefaultMainMenu` (0.18.1: lines 21056-21071, in
                 * components/LayerUI.tsx).
                 *
                 * Supplying MainMenu children REPLACES the vendor's default,
                 * which is the only supported way to control the links group:
                 * `Socials` is a DefaultItems entry composed at that one site,
                 * and no UIOptions key reaches it. The alternative considered
                 * and rejected was rewriting the rendered anchors' hrefs — the
                 * group is three links labelled GitHub, Follow us and Discord,
                 * so re-pointing them at one destination ships a menu entry
                 * that names one place and opens another.
                 *
                 * The cost of owning the menu is the two gates the vendor
                 * applies HERE rather than inside the item: Export and
                 * SaveAsImage. The other five default items return null on
                 * their own; SearchMenu and Help have no gate. Keep this list
                 * in step with the vendor — the drift test in
                 * DashExcalidraw.test.tsx reads that block and fails if the
                 * set of default items changes under a version bump.
                 */}
                {welcomeScreen && (
                    <WelcomeScreen>
                        <WelcomeScreen.Center>
                            {(welcomeScreenContent?.title ||
                                welcomeScreenContent?.subtitle) && (
                                <WelcomeScreen.Center.Heading>
                                    {welcomeScreenContent?.title ||
                                        welcomeScreenContent?.subtitle}
                                </WelcomeScreen.Center.Heading>
                            )}
                            {welcomeScreenContent?.title &&
                                welcomeScreenContent?.subtitle && (
                                    <WelcomeScreen.Center.Heading>
                                        {welcomeScreenContent.subtitle}
                                    </WelcomeScreen.Center.Heading>
                                )}
                            <WelcomeScreen.Center.Menu>
                                <WelcomeScreen.Center.MenuItemLoadScene />
                                <WelcomeScreen.Center.MenuItemHelp />
                            </WelcomeScreen.Center.Menu>
                        </WelcomeScreen.Center>
                    </WelcomeScreen>
                )}
                <MainMenu>
                    <MainMenu.DefaultItems.LoadScene />
                    <MainMenu.DefaultItems.SaveToActiveFile />
                    {showExportItem && <MainMenu.DefaultItems.Export />}
                    {showSaveAsImageItem && <MainMenu.DefaultItems.SaveAsImage />}
                    <MainMenu.DefaultItems.SearchMenu />
                    <MainMenu.DefaultItems.Help />
                    <MainMenu.DefaultItems.ClearCanvas />
                    <MainMenu.Separator />
                    {!hideExcalidrawLinks && (
                        <MainMenu.Group title="Excalidraw links">
                            <MainMenu.DefaultItems.Socials />
                        </MainMenu.Group>
                    )}
                    {Boolean(docsLinkUrl) && (
                        <MainMenu.Group>
                            <MainMenu.ItemLink
                                href={docsLinkUrl as string}
                                rel="noopener noreferrer"
                            >
                                {docsLinkLabel}
                            </MainMenu.ItemLink>
                        </MainMenu.Group>
                    )}
                    {/*
                     * The vendor brackets its links group with a Separator on
                     * each side. When BOTH groups are absent the trailing one
                     * would sit against the leading one, so it is dropped —
                     * one break, never two, in all three states.
                     */}
                    {(!hideExcalidrawLinks || Boolean(docsLinkUrl)) && (
                        <MainMenu.Separator />
                    )}
                    <MainMenu.DefaultItems.ToggleTheme />
                    <MainMenu.DefaultItems.ChangeCanvasBackground />
                </MainMenu>
            </Excalidraw>
        </div>
    );
};

export default DashExcalidraw
