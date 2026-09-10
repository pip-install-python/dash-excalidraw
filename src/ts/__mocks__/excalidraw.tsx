/**
 * Stand-in for `@excalidraw/excalidraw`, wired in through jest.config.js's
 * moduleNameMapper rather than `jest.mock`.
 *
 * Mapping rather than mocking is deliberate: Excalidraw 0.18 reaches its
 * entry points only through the package `exports` map, which jest's CommonJS
 * resolver does not read (the same constraint tsconfig documents for
 * `moduleResolution`). Mapping the specifier sidesteps resolution entirely.
 *
 * The important capability here is `__deliverApi`. The real component receives
 * its API handle from Excalidraw's `excalidrawAPI` callback at some point
 * AFTER mount, and the bug this harness exists for lives in that gap — a
 * command that arrives while the handle is still null. Holding the callback
 * and firing it on demand is what makes the gap testable at all.
 */
import React from 'react';

let apiCallback: ((api: any) => void) | null = null;

export const exportToSvg = jest.fn();
export const exportToBlob = jest.fn();
export const exportToCanvas = jest.fn();
export const restoreElements = jest.fn((els: any) => els);
export const serializeAsJSON = jest.fn(() => '{}');

export const CaptureUpdateAction = {
    IMMEDIATELY: 'immediately',
    NEVER: 'never',
    EVENTUALLY: 'eventually',
};

export const Excalidraw = (props: any) => {
    // Capture, do not call. The test decides when the canvas is "ready".
    apiCallback = props.excalidrawAPI || null;
    // Children matter: the wrapper passes its composed <MainMenu> this way,
    // and a stub that dropped them would report an empty menu for every
    // state — a test that cannot fail rather than one that passes.
    return React.createElement(
        'div',
        {'data-testid': 'excalidraw-canvas'},
        props.children,
    );
};

/** Build a scene API whose every method is observable. */
export function makeApi() {
    return {
        updateScene: jest.fn(),
        addFiles: jest.fn(),
        resetScene: jest.fn(),
        scrollToContent: jest.fn(),
        setActiveTool: jest.fn(),
        setToast: jest.fn(),
        toggleSidebar: jest.fn(),
        updateLibrary: jest.fn().mockResolvedValue(undefined),
        getSceneElements: jest.fn(() => []),
        getAppState: jest.fn(() => ({})),
        getFiles: jest.fn(() => ({})),
        getSceneVersion: jest.fn(() => 1),
    };
}

/** Hand the component its API handle — i.e. "the canvas is ready now". */
export function __deliverApi(api: any) {
    if (!apiCallback) {
        throw new Error(
            '__deliverApi called before <Excalidraw> rendered — the component ' +
                'gates render on an isMounted effect, so flush effects first.',
        );
    }
    apiCallback(api);
}

export function __apiRequested(): boolean {
    return apiCallback !== null;
}

export function __reset() {
    apiCallback = null;
    menuLog = [];
    exportToSvg.mockReset();
    exportToBlob.mockReset();
    exportToCanvas.mockReset();
    restoreElements.mockReset();
    restoreElements.mockImplementation((els: any) => els);
    serializeAsJSON.mockReset();
    serializeAsJSON.mockImplementation(() => '{}');
}

/* -------------------------------------------------------------------------
 *  MainMenu, recorded rather than rendered.
 *
 *  The component composes its own menu (mirroring the vendor's
 *  DefaultMainMenu), so the harness needs to see WHAT was composed, in order.
 *  Each stub logs itself and renders nothing; assertions read the log.
 * ------------------------------------------------------------------------- */
type MenuEntry = {kind: string; title?: string; href?: string; label?: any; rel?: string};

let menuLog: MenuEntry[] = [];

const recordItem = (name: string) => {
    const C: any = () => {
        menuLog.push({kind: name});
        return null;
    };
    C.displayName = name;
    return C;
};

const DEFAULT_ITEM_NAMES = [
    'LoadScene',
    'SaveToActiveFile',
    'SaveAsImage',
    'CommandPalette',
    'SearchMenu',
    'Help',
    'ClearCanvas',
    'ToggleTheme',
    'ChangeCanvasBackground',
    'Export',
    'Socials',
    'LiveCollaborationTrigger',
];

export const MainMenu: any = ({children}: any) =>
    React.createElement('div', {'data-testid': 'main-menu'}, children);

MainMenu.DefaultItems = DEFAULT_ITEM_NAMES.reduce((acc: any, name) => {
    acc[name] = recordItem(name);
    return acc;
}, {});

MainMenu.Separator = recordItem('Separator');

MainMenu.Group = ({title, children}: any) => {
    menuLog.push({kind: 'Group', title});
    return React.createElement('div', null, children);
};

MainMenu.ItemLink = ({href, children, rel}: any) => {
    menuLog.push({kind: 'ItemLink', href, label: children, rel});
    return null;
};

/** Everything the menu rendered, in order. */
export function __menuLog(): MenuEntry[] {
    return menuLog;
}

/** Just the vendor DefaultItems names that rendered. */
export function __renderedDefaultItems(): string[] {
    return menuLog.filter((e) => DEFAULT_ITEM_NAMES.includes(e.kind)).map((e) => e.kind);
}

export function __resetMenuLog() {
    menuLog = [];
}
