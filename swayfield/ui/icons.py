# SPDX-License-Identifier: GPL-3.0-or-later
"""Preview icons for preset thumbnails, and the Blender icon names the panels use."""

from __future__ import annotations

import importlib
import os

import bpy
import bpy.utils.previews

#: Blender built-in icon names used by the panels (validated by tests).
ICON_ADD = "ADD"
ICON_DUPLICATE = "DUPLICATE"
ICON_REMOVE = "REMOVE"
ICON_UP = "TRIA_UP"
ICON_DOWN = "TRIA_DOWN"
ICON_EYE_ON = "HIDE_OFF"
ICON_EYE_OFF = "HIDE_ON"
ICON_RENDER_ON = "RESTRICT_RENDER_OFF"
ICON_RENDER_OFF = "RESTRICT_RENDER_ON"
ICON_SOLO = "SOLO_OFF"
ICON_PAINT = "BRUSH_DATA"
ICON_DONE = "CHECKMARK"
ICON_WARNING = "ERROR"
ICON_UPGRADE = "FILE_REFRESH"
ICON_SYNC = "LINKED"
ICON_SELECT = "RESTRICT_SELECT_OFF"
ICON_CAMERA = "CAMERA_DATA"
ICON_IMAGE = "IMAGE_DATA"
ICON_EMPTY = "EMPTY_AXIS"
ICON_BAKE = "PACKAGE"
ICON_FREE = "TRASH"
ICON_VORTEX = "FORCE_VORTEX"
ICON_BLAST = "FORCE_FORCE"
ICON_TRAMPLE = "MOD_PHYSICS"
ICON_SHELTER = "MOD_SOLIDIFY"
ICON_EXCLUDE = "CANCEL"
ICON_SUBDIVIDE = "MOD_SUBSURF"
ICON_WIND = "FORCE_WIND"
ICON_DROPDOWN = "DOWNARROW_HLT"
ICON_COUNTER = "POINTCLOUD_DATA"

ALL_ICONS = tuple(v for k, v in sorted(globals().items()) if k.startswith("ICON_"))

_pcoll = None


def _presets() -> list[dict]:
    try:
        module = importlib.import_module("swayfield.core.presets")
        return list(module.list_grass_presets())
    except Exception:
        return []


def load() -> None:
    """Create the preview collection and load every preset thumbnail."""
    global _pcoll
    free()
    _pcoll = bpy.utils.previews.new()
    for preset in _presets():
        thumb = preset.get("thumbnail")
        if thumb and os.path.isfile(str(thumb)):
            try:
                _pcoll.load(str(preset["id"]), str(thumb), "IMAGE")
            except Exception:
                continue


def free() -> None:
    """Release the preview collection."""
    global _pcoll
    if _pcoll is not None:
        bpy.utils.previews.remove(_pcoll)
        _pcoll = None


def is_loaded() -> bool:
    return _pcoll is not None


def icon_id(key: str) -> int:
    """Icon id for a preset thumbnail, or 0 when there is none."""
    if _pcoll is not None and key in _pcoll:
        return _pcoll[key].icon_id
    return 0


def has_thumbnails() -> bool:
    return _pcoll is not None and len(_pcoll) > 0
