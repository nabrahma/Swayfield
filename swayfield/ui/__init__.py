# SPDX-License-Identifier: GPL-3.0-or-later
"""Swayfield user interface: sidebar tab, layer list and preview icons."""

from __future__ import annotations

import bpy

from . import icons, lists, panels

_enum_items: list = []


def _preset_items(self, context):
    """Dynamic items of the grass preset picker (kept alive in a module list)."""
    global _enum_items
    if not icons.is_loaded():
        icons.load()
    items = []
    try:
        from ..core import presets

        for index, preset in enumerate(presets.list_grass_presets()):
            pid = str(preset["id"])
            items.append((pid, str(preset.get("name", pid)), str(preset.get("description", "")),
                          icons.icon_id(pid), index))
    except Exception:
        items = []
    if not items:
        items = [("NONE", "Default", "Default grass", 0, 0)]
    _enum_items = items
    return _enum_items


_CLASSES = (*lists.CLASSES, *panels.CLASSES)
_registered = False


def register() -> None:
    """Register panels, the layer list and the preset picker property."""
    global _registered
    if _registered:
        return
    icons.load()
    bpy.types.WindowManager.swayfield_preset = bpy.props.EnumProperty(
        name="Grass Preset", description="Grass preset used by Add Grass", items=_preset_items)
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    _registered = True


def unregister() -> None:
    """Remove everything registered by :func:`register`."""
    global _registered
    if not _registered:
        return
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    if hasattr(bpy.types.WindowManager, "swayfield_preset"):
        del bpy.types.WindowManager.swayfield_preset
    icons.free()
    _registered = False
