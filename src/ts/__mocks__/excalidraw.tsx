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
    return React.createElement('div', {'data-testid': 'excalidraw-canvas'});
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
    exportToSvg.mockReset();
    exportToBlob.mockReset();
    exportToCanvas.mockReset();
    restoreElements.mockReset();
    restoreElements.mockImplementation((els: any) => els);
    serializeAsJSON.mockReset();
    serializeAsJSON.mockImplementation(() => '{}');
}
