"""Custom type overrides for `dash-generate-components`.

Run:
    dash-generate-components ./src/ts/components dash_excalidraw \\
        -p package-info.json -t dash_excalidraw.dash_prop_typing

The overrides below narrow the otherwise permissive `Record<string, any>`
shapes into typed dicts on the Python side, so IDE autocomplete and
runtime validation line up with what the component actually accepts.
"""

custom_imports = {
    "DashExcalidraw": [
        "import typing",
        "from typing import Any, Dict, List, Optional, Union",
    ],
}


def _optional_dict_any(*_):
    return "typing.Optional[typing.Dict[str, typing.Any]]"


def _optional_list_of_any(*_):
    return "typing.Optional[typing.List[typing.Any]]"


def _validate_embeddable(*_):
    return "typing.Optional[typing.Union[bool, typing.List[str]]]"


def _command(*_):
    return "typing.Optional[typing.Dict[str, typing.Any]]"


custom_props = {
    "DashExcalidraw": {
        "initialData": _optional_dict_any,
        "appState": _optional_dict_any,
        "files": _optional_dict_any,
        "elements": _optional_list_of_any,
        "UIOptions": _optional_dict_any,
        "validateEmbeddable": _validate_embeddable,
        "lastPointerDown": _optional_dict_any,
        "lastPointerUp": _optional_dict_any,
        "lastPointerMove": _optional_dict_any,
        "lastScrollChange": _optional_dict_any,
        "lastPaste": _optional_dict_any,
        "lastLibraryChange": _optional_dict_any,
        "lastLinkOpen": _optional_dict_any,
        "lastExport": _optional_dict_any,
        "lastFileAdded": _optional_dict_any,
        "lastExternalDrop": _optional_dict_any,
        "command": _command,
    },
}