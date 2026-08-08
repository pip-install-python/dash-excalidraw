# AUTO GENERATED FILE - DO NOT EDIT

import typing  # noqa: F401
from typing_extensions import TypedDict, NotRequired, Literal # noqa: F401
from dash.development.base_component import Component, _explicitize_args

import typing
from typing import Any, Dict, List, Optional, Union


ComponentSingleType = typing.Union[str, int, float, Component, None]
ComponentType = typing.Union[
    ComponentSingleType,
    typing.Sequence[ComponentSingleType],
]

NumberType = typing.Union[
    typing.SupportsFloat, typing.SupportsInt, typing.SupportsComplex
]


class DashExcalidraw(Component):
    """A DashExcalidraw component.
DashExcalidraw is an Excalidraw drawing canvas bound to Dash via a
JSON-safe prop surface. See the per-prop docs above for the full
catalog; see the README for the command/event round-trip pattern used
for imperative actions like exports.

Keyword arguments:

- id (string; optional):
    Unique ID to identify this component in Dash callbacks.

- UIOptions (dict; optional):
    Subset of Excalidraw `UIOptions` that is JSON-serializable. Use
    this to toggle individual canvas actions, show/hide the welcome
    screen, etc.

    `UIOptions` is a dict with keys:

    - canvasActions (dict; optional)

        `canvasActions` is a dict with keys:

        - changeViewBackgroundColor (boolean; optional)

        - clearCanvas (boolean; optional)

        - export (dict; optional)

            `export` is a boolean

          Or dict with keys:

    - saveFileToDisk (boolean; optional)

        - loadScene (boolean; optional)

        - saveToActiveFile (boolean; optional)

        - toggleTheme (boolean; optional)

        - saveAsImage (boolean; optional)

    - tools (dict; optional)

        `tools` is a dict with keys:

        - image (boolean; optional)

    - dockedSidebarBreakpoint (number; optional)

    - welcomeScreen (boolean; optional)

- appState (dict with strings as keys and values of type boolean | number | string | dict | list; optional):
    Full serializable app state (view background, zoom, scroll, grid
    mode, zen mode, theme, active tool, …). Read-only from Python.

- autoFocus (boolean; optional):
    Focus the canvas on mount. @,default,True.

- command (dict; optional):
    Write to this prop from a Python callback to dispatch an
    imperative action into Excalidraw. Shape:  ```python {\"id\":
    \"unique-string\", \"type\": \"updateScene\", \"payload\": {...}}
    ```  Supported `type` values:  - `updateScene` / `resetScene` /
    `addFiles`  - `scrollToContent` / `setActiveTool` / `setToast` /
    `toggleSidebar`  - `updateLibrary`  - `exportToSvg` /
    `exportToBlob` / `exportToCanvas`  Each dispatch is de-duplicated
    by `id`, and the component clears the prop (sets it to `None`)
    once the action completes so React re-renders do not re-fire.

    `command` is a dict with keys:

    - id (string; required)

    - type (a value equal to: 'updateScene', 'addFiles', 'resetScene', 'scrollToContent', 'setActiveTool', 'setToast', 'toggleSidebar', 'updateLibrary', 'replaceFiles', 'exportToSvg', 'exportToBlob', 'exportToCanvas'; required)

    - payload (dict with strings as keys and values of type boolean | number | string | dict | list; optional)

- detectScroll (boolean; optional):
    Whether Excalidraw listens to wheel-scroll events on the canvas.
    @,default,True.

- elements (list of dicts with strings as keys and values of type boolean | number | string | dict | list; optional):
    Current Excalidraw element array. Written via setProps on every
    scene change — read-only from Python callbacks.

- externalizedSerializedData (string; optional):
    Same envelope as `serializedData`, but every `files[*].dataURL`
    that still holds an inline `data:` URI is replaced with `None`.
    External URLs (those dispatched via the `replaceFiles` command)
    are retained as-is. Persist this variant to avoid paying the
    base64 cost; inline bytes can be rehydrated later via
    `dash_excalidraw.helpers.restore_inline_files`.

- files (dict with strings as keys and values of type boolean | number | string | dict | list; optional):
    Map of binary file entries (image id -> {dataURL, mimeType, ...}).
    Read-only from Python.

- gridModeEnabled (boolean; optional):
    Snap to grid and draw the grid background. @,default,False.

- handleKeyboardGlobally (boolean; optional):
    When True, keyboard shortcuts work even when the canvas is not
    focused. Turn off if your Dash app has other inputs that might
    conflict. @,default,True.

- height (string; optional):
    CSS height of the canvas container. Excalidraw fills its parent,
    so this is the number to change when the canvas looks too short.
    @,default,\"600px\".

- hideExcalidrawLinks (boolean; optional):
    When `True` (default), injects CSS that hides Excalidraw's
    built-in \"Excalidraw links\" menu group (GitHub / Discord /
    Twitter). Set to `False` if you actually want those links visible
    to users.

- initialData (dict; optional):
    Initial scene contents passed to Excalidraw on mount. Shape:
    `{elements, appState, files, libraryItems, scrollToContent}`.
    Updating this prop after mount has no effect — use `command` with
    `type=\"updateScene\"` to change the scene imperatively.

    `initialData` is a dict with keys:

    - elements (list of dicts with strings as keys and values of type boolean | number | string | dict | list; optional)

    - appState (dict with strings as keys and values of type boolean | number | string | dict | list; optional)

    - files (dict with strings as keys and values of type boolean | number | string | dict | list; optional)

    - libraryItems (list of dicts with strings as keys and values of type boolean | number | string | dict | list; optional)

    - scrollToContent (boolean; optional)

- interceptLinkOpens (boolean; optional):
    When `True`, the wrapper calls `event.preventDefault()` on every
    `lastLinkOpen` event so Python can handle the click itself
    (typically by opening a `dmc.Drawer`). Default `False` — links
    open in a new tab normally.

- isCollaborating (boolean; optional):
    Renders the \"currently-editing\" collaborator UI. You'll also
    need to feed `appState.collaborators`; the wrapper does not bundle
    a transport layer. @,default,False.

- langCode (string; optional):
    UI language code (e.g. `en`, `fr-FR`, `zh-CN`). @,default,\"en\".

- lastExport (dict with strings as keys and values of type boolean | number | string | dict | list; optional):
    Result of the most recent export command: `{timestamp, id, type,
    result, error?}`. Match `id` against the command you dispatched to
    correlate responses.

- lastExternalDrop (dict with strings as keys and values of type boolean | number | string | dict | list; optional):
    Fires when the wrapper's drop handler intercepts a drop that
    Excalidraw itself doesn't accept (non-image files, or any multi-
    file drop). Payload:    {     timestamp,     files: [{name,
    mimeType, dataURL, size}, ...],     dropPoint: {x, y},
    # scene coords     placeholderIds: [elemId, ...],      # one id
    per non-image file,                                         #
    pointing at the rectangle we
    # placed on the canvas so you
    # can update its `link` after
    # upload.   }.

- lastFileAdded (dict with strings as keys and values of type boolean | number | string | dict | list; optional):
    Fires when one or more new file ids appear in `files` with an
    inline `data:` dataURL. Payload:    {     timestamp,     fileId,
    mimeType, dataURL, size,   # first new file (back-compat)
    files: [       {fileId, mimeType, dataURL, size},       ...
    # every new file in this change     ],   }  Single-file callbacks
    can keep reading `event['fileId']`; batch callbacks iterate
    `event['files']`. `size` is decoded byte count.

- lastLibraryChange (dict with strings as keys and values of type boolean | number | string | dict | list; optional):
    Snapshot of the last library change `{timestamp, items}`.

- lastLinkOpen (dict with strings as keys and values of type boolean | number | string | dict | list; optional):
    Snapshot of the last link-open event `{timestamp, elementId, url}`
    — fired when a user Cmd/Ctrl-clicks an element with a hyperlink.

- lastPaste (dict with strings as keys and values of type boolean | number | string | dict | list; optional):
    Snapshot of the last clipboard paste `{timestamp, data}`. The
    wrapper cannot cancel the paste from Python; if you need to
    intercept, clean up in a follow-up callback that modifies scene
    state afterward.

- lastPointerDown (dict with strings as keys and values of type boolean | number | string | dict | list; optional):
    Snapshot of the last pointer-down event: `{timestamp, activeTool,
    pointer: {x, y}}`.

- lastPointerMove (dict with strings as keys and values of type boolean | number | string | dict | list; optional):
    Throttled pointer-move snapshot `{timestamp, pointer, button,
    pointersMap}`. Throttled by `pointerMoveThrottleMs` (default 50
    ms).

- lastPointerUp (dict with strings as keys and values of type boolean | number | string | dict | list; optional):
    Snapshot of the last pointer-up event: `{timestamp, activeTool,
    pointer: {x, y}}`.

- lastScrollChange (dict with strings as keys and values of type boolean | number | string | dict | list; optional):
    Throttled scroll/zoom snapshot `{timestamp, scrollX, scrollY}`.

- libraryReturnUrl (string; optional):
    Optional URL appended to the \"Browse Library\" button in the
    sidebar. When unset Excalidraw uses its own default.

- name (string; optional):
    Drawing name — appears in the top bar and in serialized export
    filenames.

- pointerMoveThrottleMs (number; optional):
    Debounce interval for `lastPointerMove` writes (milliseconds).
    @,default,50.

- sceneVersion (number; optional):
    Monotonic scene version from `excalidrawAPI.getSceneVersion()`.
    Useful for change detection without diffing element arrays.

- scrollThrottleMs (number; optional):
    Debounce interval for `lastScrollChange` writes (milliseconds).
    @,default,100.

- serializedData (string; optional):
    JSON string of the canonical Excalidraw serialized envelope
    `{type, version, source, elements, appState, files}`. Suitable to
    pass to `dash.dcc.Store` and later restore via `initialData`.

- theme (a value equal to: 'light', 'dark'; optional):
    Canvas color theme. @,default,\"light\".

- validateEmbeddable (boolean | list of strings; optional):
    Controls which URLs may be embedded inside Excalidraw frames. Pass
    `True` to allow all, `False` to deny all, or a list of domain-glob
    strings (e.g. `[\"*.youtube.com\", \"excalidraw.com\"]`) which the
    wrapper compiles to case-insensitive RegExps.

- viewModeEnabled (boolean; optional):
    View-only mode: disables drawing tools; pan/zoom still available.
    @,default,False.

- width (string; optional):
    CSS width of the canvas container. @,default,\"100%\".

- zenModeEnabled (boolean; optional):
    Zen mode hides most of the chrome for a distraction-free canvas.
    @,default,False."""
    _children_props: typing.List[str] = []
    _base_nodes = ['children']
    _namespace = 'dash_excalidraw'
    _type = 'DashExcalidraw'


    def __init__(
        self,
        width: typing.Optional[str] = None,
        height: typing.Optional[str] = None,
        initialData: typing.Optional[typing.Optional[typing.Dict[str, typing.Any]]] = None,
        elements: typing.Optional[typing.Optional[typing.List[typing.Any]]] = None,
        appState: typing.Optional[typing.Optional[typing.Dict[str, typing.Any]]] = None,
        files: typing.Optional[typing.Optional[typing.Dict[str, typing.Any]]] = None,
        serializedData: typing.Optional[str] = None,
        externalizedSerializedData: typing.Optional[str] = None,
        sceneVersion: typing.Optional[NumberType] = None,
        lastFileAdded: typing.Optional[typing.Optional[typing.Dict[str, typing.Any]]] = None,
        lastExternalDrop: typing.Optional[typing.Optional[typing.Dict[str, typing.Any]]] = None,
        interceptLinkOpens: typing.Optional[bool] = None,
        hideExcalidrawLinks: typing.Optional[bool] = None,
        viewModeEnabled: typing.Optional[bool] = None,
        zenModeEnabled: typing.Optional[bool] = None,
        gridModeEnabled: typing.Optional[bool] = None,
        isCollaborating: typing.Optional[bool] = None,
        theme: typing.Optional[Literal["light", "dark"]] = None,
        name: typing.Optional[str] = None,
        langCode: typing.Optional[str] = None,
        libraryReturnUrl: typing.Optional[str] = None,
        detectScroll: typing.Optional[bool] = None,
        handleKeyboardGlobally: typing.Optional[bool] = None,
        autoFocus: typing.Optional[bool] = None,
        UIOptions: typing.Optional[typing.Optional[typing.Dict[str, typing.Any]]] = None,
        validateEmbeddable: typing.Optional[typing.Optional[typing.Union[bool, typing.List[str]]]] = None,
        lastPointerDown: typing.Optional[typing.Optional[typing.Dict[str, typing.Any]]] = None,
        lastPointerUp: typing.Optional[typing.Optional[typing.Dict[str, typing.Any]]] = None,
        lastPointerMove: typing.Optional[typing.Optional[typing.Dict[str, typing.Any]]] = None,
        lastScrollChange: typing.Optional[typing.Optional[typing.Dict[str, typing.Any]]] = None,
        lastPaste: typing.Optional[typing.Optional[typing.Dict[str, typing.Any]]] = None,
        lastLibraryChange: typing.Optional[typing.Optional[typing.Dict[str, typing.Any]]] = None,
        lastLinkOpen: typing.Optional[typing.Optional[typing.Dict[str, typing.Any]]] = None,
        lastExport: typing.Optional[typing.Optional[typing.Dict[str, typing.Any]]] = None,
        command: typing.Optional[typing.Optional[typing.Dict[str, typing.Any]]] = None,
        pointerMoveThrottleMs: typing.Optional[NumberType] = None,
        scrollThrottleMs: typing.Optional[NumberType] = None,
        id: typing.Optional[typing.Union[str, dict]] = None,
        **kwargs
    ):
        self._prop_names = ['id', 'UIOptions', 'appState', 'autoFocus', 'command', 'detectScroll', 'elements', 'externalizedSerializedData', 'files', 'gridModeEnabled', 'handleKeyboardGlobally', 'height', 'hideExcalidrawLinks', 'initialData', 'interceptLinkOpens', 'isCollaborating', 'langCode', 'lastExport', 'lastExternalDrop', 'lastFileAdded', 'lastLibraryChange', 'lastLinkOpen', 'lastPaste', 'lastPointerDown', 'lastPointerMove', 'lastPointerUp', 'lastScrollChange', 'libraryReturnUrl', 'name', 'pointerMoveThrottleMs', 'sceneVersion', 'scrollThrottleMs', 'serializedData', 'theme', 'validateEmbeddable', 'viewModeEnabled', 'width', 'zenModeEnabled']
        self._valid_wildcard_attributes =            []
        self.available_properties = ['id', 'UIOptions', 'appState', 'autoFocus', 'command', 'detectScroll', 'elements', 'externalizedSerializedData', 'files', 'gridModeEnabled', 'handleKeyboardGlobally', 'height', 'hideExcalidrawLinks', 'initialData', 'interceptLinkOpens', 'isCollaborating', 'langCode', 'lastExport', 'lastExternalDrop', 'lastFileAdded', 'lastLibraryChange', 'lastLinkOpen', 'lastPaste', 'lastPointerDown', 'lastPointerMove', 'lastPointerUp', 'lastScrollChange', 'libraryReturnUrl', 'name', 'pointerMoveThrottleMs', 'sceneVersion', 'scrollThrottleMs', 'serializedData', 'theme', 'validateEmbeddable', 'viewModeEnabled', 'width', 'zenModeEnabled']
        self.available_wildcard_properties =            []
        _explicit_args = kwargs.pop('_explicit_args')
        _locals = locals()
        _locals.update(kwargs)  # For wildcard attrs and excess named props
        args = {k: _locals[k] for k in _explicit_args}

        super(DashExcalidraw, self).__init__(**args)

setattr(DashExcalidraw, "__init__", _explicitize_args(DashExcalidraw.__init__))
