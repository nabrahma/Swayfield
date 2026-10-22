# SPDX-License-Identifier: GPL-3.0-or-later
"""Operator registration.

Modules written by other parts of the add-on (``presets``, ``materials``) are
optional: a missing module never breaks registration. A module may expose
``classes`` or its own ``register``/``unregister``.
"""

from __future__ import annotations

import importlib

import bpy

from ..core import drivers

_OWN = ("add_grass", "layers", "paint", "bake", "effectors", "scene")
_OPTIONAL = ("presets", "materials")

#: Modules registered by register(), so unregister() undoes exactly that.
_registered: list = []


def _load(name: str, *, optional: bool):
    try:
        return importlib.import_module(f".{name}", __name__)
    except ModuleNotFoundError as err:
        if optional and err.name == f"{__name__}.{name}":
            return None
        raise


def _register_module(module) -> None:
    if hasattr(module, "register"):
        module.register()
    else:
        for cls in module.classes:
            bpy.utils.register_class(cls)
    _registered.append(module)


def _unregister_module(module) -> None:
    if hasattr(module, "unregister"):
        module.unregister()
    else:
        for cls in reversed(module.classes):
            bpy.utils.unregister_class(cls)


def register() -> None:
    modules = [_load(name, optional=False) for name in _OWN]
    modules += [m for m in (_load(name, optional=True) for name in _OPTIONAL) if m is not None]
    for module in modules:
        _register_module(module)
    drivers.start_camera_watch()


def unregister() -> None:
    drivers.stop_camera_watch()
    while _registered:
        _unregister_module(_registered.pop())
