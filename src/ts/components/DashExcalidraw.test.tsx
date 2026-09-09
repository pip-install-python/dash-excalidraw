/**
 * The two behaviours no Python test can reach.
 *
 * 1. The command dispatcher's handling of a canvas that is not ready yet.
 *    This is the ae82a0c regression: the effect claimed `command.id` BEFORE
 *    checking for the API handle, then returned on `!api` — and that early
 *    return happens before `run()`, so the `finally` that clears `command`
 *    never executed either. The command was lost, its id burned, and the
 *    guard rejected every retry. 470 Python tests could not see it, and the
 *    browser walk cannot either: every docs callback that writes `command`
 *    carries prevent_initial_call=True, so nothing dispatches on load.
 *
 * 2. The export correlation. Exports resolve out of order, so each result —
 *    and each catch-path payload — must name the command that produced it.
 *
 * Mutation check for suite 1: move `lastCommandIdRef.current = command.id`
 * back above the `if (!api) return;` in DashExcalidraw.tsx and the first two
 * tests fail. They are the ones that would have caught the original bug.
 */
import React from 'react';
import {act, render, waitFor} from '@testing-library/react';

import DashExcalidraw from './DashExcalidraw';
import {
    __apiRequested,
    __deliverApi,
    __reset,
    exportToBlob,
    exportToSvg,
    makeApi,
} from '@excalidraw/excalidraw';

const flush = async () => {
    // The component gates render on an isMounted effect, so <Excalidraw> —
    // and therefore the excalidrawAPI callback — only exists after a tick.
    await act(async () => {
        await Promise.resolve();
    });
};

beforeEach(() => {
    __reset();
});

describe('command dispatch: readiness and id claiming', () => {
    test('a command that arrives BEFORE the canvas is ready runs once it is', async () => {
        const setProps = jest.fn();
        const api = makeApi();

        render(
            <DashExcalidraw
                id="c"
                setProps={setProps}
                command={{id: 'cmd-early', type: 'setToast', payload: {message: 'hi'}}}
            />,
        );
        await flush();

        // The canvas has asked for its handle but has not been given one.
        expect(__apiRequested()).toBe(true);
        expect(api.setToast).not.toHaveBeenCalled();

        // Now the canvas becomes ready. The command must still run.
        await act(async () => {
            __deliverApi(api);
        });

        await waitFor(() => expect(api.setToast).toHaveBeenCalledTimes(1));
        expect(api.setToast).toHaveBeenCalledWith({message: 'hi'});
    });

    test('the id is NOT burned on the not-ready path', async () => {
        const setProps = jest.fn();
        const api = makeApi();
        const command = {id: 'cmd-same', type: 'resetScene', payload: {}};

        const {rerender} = render(
            <DashExcalidraw id="c" setProps={setProps} command={command} />,
        );
        await flush();
        expect(api.resetScene).not.toHaveBeenCalled();

        // A re-render while still not ready must not consume the id either.
        rerender(<DashExcalidraw id="c" setProps={setProps} command={command} />);
        await flush();

        await act(async () => {
            __deliverApi(api);
        });

        await waitFor(() => expect(api.resetScene).toHaveBeenCalledTimes(1));
    });

    test('re-dispatching a COMPLETED id is a no-op', async () => {
        const setProps = jest.fn();
        const api = makeApi();
        const command = {id: 'cmd-once', type: 'setToast', payload: {message: 'once'}};

        const {rerender} = render(
            <DashExcalidraw id="c" setProps={setProps} command={command} />,
        );
        await flush();
        await act(async () => {
            __deliverApi(api);
        });
        await waitFor(() => expect(api.setToast).toHaveBeenCalledTimes(1));

        // Same id again — documented as a no-op, and it must stay one.
        rerender(<DashExcalidraw id="c" setProps={setProps} command={command} />);
        await flush();
        expect(api.setToast).toHaveBeenCalledTimes(1);
    });

    test('a NEW id after a completed one still dispatches', async () => {
        const setProps = jest.fn();
        const api = makeApi();

        const {rerender} = render(
            <DashExcalidraw
                id="c"
                setProps={setProps}
                command={{id: 'cmd-a', type: 'setToast', payload: {message: 'a'}}}
            />,
        );
        await flush();
        await act(async () => {
            __deliverApi(api);
        });
        await waitFor(() => expect(api.setToast).toHaveBeenCalledTimes(1));

        rerender(
            <DashExcalidraw
                id="c"
                setProps={setProps}
                command={{id: 'cmd-b', type: 'setToast', payload: {message: 'b'}}}
            />,
        );
        await waitFor(() => expect(api.setToast).toHaveBeenCalledTimes(2));
        expect(api.setToast).toHaveBeenLastCalledWith({message: 'b'});
    });

    test('the command is cleared after it runs, so a re-render cannot re-fire it', async () => {
        const setProps = jest.fn();
        const api = makeApi();

        render(
            <DashExcalidraw
                id="c"
                setProps={setProps}
                command={{id: 'cmd-clear', type: 'resetScene', payload: {}}}
            />,
        );
        await flush();
        await act(async () => {
            __deliverApi(api);
        });

        await waitFor(() =>
            expect(
                setProps.mock.calls.some(
                    ([patch]) => patch && 'command' in patch && patch.command === null,
                ),
            ).toBe(true),
        );
    });
});

describe('export correlation', () => {
    const lastExportPayloads = (setProps: jest.Mock) =>
        setProps.mock.calls
            .map(([patch]) => patch && patch.lastExport)
            .filter(Boolean);

    /**
     * Mount with NO command and hand over the API first, so these tests
     * exercise correlation on a canvas that is already ready.
     *
     * This matters for what the mutation check can tell you. An earlier draft
     * dispatched before delivering the API here too, which meant reverting the
     * dispatcher fix failed all eight tests — a signal that says "something
     * broke" and nothing more. Isolated, the five dispatcher tests fail and
     * these three keep passing, so the mutation check localises the damage.
     */
    const mountReady = async () => {
        const setProps = jest.fn();
        const api = makeApi();
        const {rerender} = render(<DashExcalidraw id="c" setProps={setProps} />);
        await flush();
        await act(async () => {
            __deliverApi(api);
        });
        return {setProps, api, rerender};
    };

    test('an export result carries the id that was dispatched', async () => {
        (exportToSvg as jest.Mock).mockResolvedValue({outerHTML: '<svg id="s"/>'});
        const {setProps, rerender} = await mountReady();

        rerender(
            <DashExcalidraw
                id="c"
                setProps={setProps}
                command={{id: 'e1', type: 'exportToSvg', payload: {}}}
            />,
        );

        await waitFor(() => expect(lastExportPayloads(setProps).length).toBeGreaterThan(0));
        const payload = lastExportPayloads(setProps)[0];
        expect(payload.id).toBe('e1');
        expect(payload.type).toBe('exportToSvg');
        expect(payload.result).toBe('<svg id="s"/>');
    });

    test('two exports resolving OUT OF ORDER each keep their own id', async () => {
        let resolveFirst: (v: any) => void = () => undefined;
        (exportToSvg as jest.Mock).mockReturnValue(
            new Promise((res) => {
                resolveFirst = res;
            }),
        );
        (exportToBlob as jest.Mock).mockResolvedValue(new Blob(['x']));

        const {setProps, rerender} = await mountReady();

        rerender(
            <DashExcalidraw
                id="c"
                setProps={setProps}
                command={{id: 'slow-svg', type: 'exportToSvg', payload: {}}}
            />,
        );

        // Second export dispatched while the first is still pending, and
        // allowed to finish first.
        rerender(
            <DashExcalidraw
                id="c"
                setProps={setProps}
                command={{id: 'fast-blob', type: 'exportToBlob', payload: {}}}
            />,
        );
        await waitFor(() =>
            expect(lastExportPayloads(setProps).some((p) => p.id === 'fast-blob')).toBe(true),
        );

        await act(async () => {
            resolveFirst({outerHTML: '<svg/>'});
        });
        await waitFor(() =>
            expect(lastExportPayloads(setProps).some((p) => p.id === 'slow-svg')).toBe(true),
        );

        const byId = Object.fromEntries(
            lastExportPayloads(setProps).map((p) => [p.id, p.type]),
        );
        // The blob landed first and the svg second; neither wears the other's id.
        expect(byId['fast-blob']).toBe('exportToBlob');
        expect(byId['slow-svg']).toBe('exportToSvg');
    });

    test('a FAILING export reports the error on the id that asked for it', async () => {
        (exportToSvg as jest.Mock).mockRejectedValue(new Error('boom'));
        const {setProps, rerender} = await mountReady();

        rerender(
            <DashExcalidraw
                id="c"
                setProps={setProps}
                command={{id: 'e-fail', type: 'exportToSvg', payload: {}}}
            />,
        );

        await waitFor(() => expect(lastExportPayloads(setProps).length).toBeGreaterThan(0));
        const payload = lastExportPayloads(setProps)[0];
        expect(payload.id).toBe('e-fail');
        expect(payload.result).toBeNull();
        expect(String(payload.error)).toContain('boom');
    });
});
