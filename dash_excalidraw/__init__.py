from __future__ import print_function as _

import json
import os as _os
import sys as _sys

import dash as _dash

# noinspection PyUnresolvedReferences
from ._imports_ import *  # noqa: F401,F403
from ._imports_ import __all__ as _component_all
from .helpers import decode_data_url, restore_inline_files, strip_inline_files

__all__ = list(_component_all) + [
    "decode_data_url",
    "restore_inline_files",
    "strip_inline_files",
]

if not hasattr(_dash, "__plotly_dash") and not hasattr(_dash, "development"):
    print(
        "Dash was not successfully imported. "
        'Make sure you don\'t have a file named \n"dash.py" in your current directory.',
        file=_sys.stderr,
    )
    _sys.exit(1)

_basepath = _os.path.dirname(__file__)
_filepath = _os.path.abspath(_os.path.join(_basepath, "package-info.json"))
with open(_filepath) as f:
    package = json.load(f)

package_name = package["name"].replace(" ", "_").replace("-", "_")
__version__ = package["version"]

_current_path = _os.path.dirname(_os.path.abspath(__file__))

_this_module = _sys.modules[__name__]

_js_dist = [
    {
        "relative_package_path": "dash_excalidraw.js",
        "external_url": "https://unpkg.com/{0}@{2}/{1}/{1}.js".format(
            package_name, "dash_excalidraw", __version__
        ),
        "namespace": package_name,
    },
    {
        "relative_package_path": "dash_excalidraw.js.map",
        "external_url": "https://unpkg.com/{0}@{2}/{1}/{1}.js.map".format(
            package_name, "dash_excalidraw", __version__
        ),
        "namespace": package_name,
        "dynamic": True,
    },
]

_js_dist.append(
    dict(
        dev_package_path="proptypes.js",
        dev_only=True,
        namespace="dash_excalidraw",
    )
)

_css_dist = []


for _component in _component_all:
    setattr(locals()[_component], "_js_dist", _js_dist)
    setattr(locals()[_component], "_css_dist", _css_dist)