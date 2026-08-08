import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {
    Excalidraw,
    exportToBlob,
    exportToCanvas,
    exportToSvg,
    restoreElements,
    serializeAsJSON,
} from '@excalidraw/excalidraw';
// NOTE: Excalidraw 0.17.x bundles its CSS into the JS artifact, so no
// explicit CSS import is needed. If you upgrade the pin to `^0.18.0`,
// re-enable the following line (the 0.18 ESM build exposes a standalone
// stylesheet that must be imported manually):
//     import '@excalidraw/excalidraw/index.css';

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
     * Monotonic scene version from `excalidrawAPI.getSceneVersion()`.
     * Useful for change detection without diffing element arrays.
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
     * When `true` (default), injects CSS that hides Excalidraw's built-in
     * "Excalidraw links" menu group (GitHub / Discord / Twitter). Set to
     * `false` if you actually want those links visible to users.
     */
    hideExcalidrawLinks?: boolean;

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
    } = props;

    const [isMounted, setIsMounted] = useState(false);
    const [api, setApi] = useState<any>(null);
    const apiRef = useRef<any>(null);
    const lastCommandIdRef = useRef<string | null>(null);
    const pointerMoveLastRef = useRef<number>(0);
    const scrollLastRef = useRef<number>(0);
    // Track file ids we've already emitted `lastFileAdded` for so the
    // event fires exactly once per new file, even across re-renders.
    const knownFileIdsRef = useRef<Set<string>>(new Set());

    useEffect(() => {
        setIsMounted(true);
    }, []);

    // Inject a global stylesheet (once) that hides Excalidraw's
    // "Excalidraw links" menu group. Opt-out via `hideExcalidrawLinks={false}`.
    useEffect(() => {
        if (!hideExcalidrawLinks || typeof document === 'undefined') return;
        const styleId = 'dash-excalidraw-hide-links';
        if (document.getElementById(styleId)) return;
        const el = document.createElement('style');
        el.id = styleId;
        el.textContent = `
            /* Hide the "Excalidraw links" menu group (GitHub / Discord / Twitter). */
            .dropdown-menu-group:has(a[href*="github.com/excalidraw/excalidraw"]),
            .dropdown-menu-group:has(a[href*="discord.gg/UexuTaE"]),
            .dropdown-menu-group:has(a[href*="twitter.com/excalidraw"]) {
                display: none !important;
            }
        `;
        document.head.appendChild(el);
        return () => {
            // keep the stylesheet around — multiple Dash components share it.
        };
    }, [hideExcalidrawLinks]);

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
            const sceneVersion =
                typeof apiRef.current?.getSceneVersion === 'function'
                    ? apiRef.current.getSceneVersion()
                    : undefined;

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
            const singleImage =
                files.length === 1 &&
                (files[0].type || '').startsWith('image/');
            if (singleImage) return; // let Excalidraw handle

            // We're taking the drop. Prevent native drop + stop Excalidraw.
            e.preventDefault();
            e.stopPropagation();

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
                files.map(async (f) => ({
                    file: f,
                    name: f.name,
                    mimeType: f.type || 'application/octet-stream',
                    size: f.size,
                    dataURL: await fileToDataURL(f),
                    isImage: (f.type || '').startsWith('image/'),
                })),
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
                    nonImagePayload.push({
                        name: item.name,
                        mimeType: item.mimeType,
                        dataURL: item.dataURL,
                        size: item.size,
                        placeholderId: placeholder.rectId,
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

    /* --------- command dispatch ------------------------------------------ */
    useEffect(() => {
        if (!command || !command.id) return;
        if (command.id === lastCommandIdRef.current) return;
        lastCommandIdRef.current = command.id;

        const api = apiRef.current;
        if (!api) return;

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
                        // Normalize any incoming elements through
                        // `restoreElements` so text baselines, autoResize,
                        // version ids, and other internals are populated.
                        // Without this, AI-generated text elements render
                        // invisibly until the user clicks / resizes them.
                        const scenePayload: Record<string, any> = {
                            ...(payload || {}),
                        };

                        // Excalidraw stores `appState.collaborators` as a
                        // `Map<string, Collaborator>`, but Python sends it
                        // as a plain JSON object. Converting prevents
                        // `Map.forEach` from blowing up during render.
                        const appStatePayload = scenePayload.appState;
                        if (
                            appStatePayload &&
                            appStatePayload.collaborators &&
                            !(appStatePayload.collaborators instanceof Map) &&
                            typeof appStatePayload.collaborators === 'object'
                        ) {
                            scenePayload.appState = {
                                ...appStatePayload,
                                collaborators: new Map(
                                    Object.entries(appStatePayload.collaborators),
                                ),
                            };
                        }

                        if (
                            Array.isArray(scenePayload.elements) &&
                            scenePayload.elements.length > 0
                        ) {
                            try {
                                scenePayload.elements = restoreElements(
                                    scenePayload.elements as any,
                                    null,
                                ) as any;
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
                        break;
                    case 'resetScene':
                        api.resetScene(payload || {});
                        break;
                    case 'scrollToContent':
                        api.scrollToContent(payload?.target, payload?.opts);
                        break;
                    case 'setActiveTool':
                        api.setActiveTool(payload || {type: 'selection'});
                        break;
                    case 'setToast':
                        api.setToast(payload ?? null);
                        break;
                    case 'toggleSidebar':
                        api.toggleSidebar(payload || {});
                        break;
                    case 'updateLibrary':
                        await api.updateLibrary(payload || {});
                        break;
                    case 'replaceFiles': {
                        // payload: { [fileId]: { dataURL: string, mimeType?: string } }
                        // `api.addFiles` with matching ids does an in-place
                        // overwrite, which makes the old base64 string
                        // unreferenced and collectible by the GC.
                        const entries = payload || {};
                        const replacement = Object.entries(entries)
                            .map(([fileId, info]: [string, any]) => {
                                if (!info || typeof info.dataURL !== 'string') {
                                    return null;
                                }
                                return {
                                    id: fileId,
                                    mimeType: info.mimeType || 'image/png',
                                    dataURL: info.dataURL,
                                    created: Date.now(),
                                };
                            })
                            .filter(Boolean) as any[];
                        if (replacement.length > 0) {
                            api.addFiles(replacement);
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
    }, [command, writeProps]);

    /* --------- render ---------------------------------------------------- */
    if (!isMounted) {
        return <div id={id} style={{width, height}} />;
    }

    return (
        <div
            id={id}
            style={{width, height, position: 'relative'}}
            onDragOver={handleDragOver}
            onDropCapture={handleDropCapture}
        >
            <Excalidraw
                excalidrawAPI={(a: any) => {
                    apiRef.current = a;
                    setApi(a);
                }}
                initialData={initialData as any}
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
            />
        </div>
    );
};

export default DashExcalidraw
