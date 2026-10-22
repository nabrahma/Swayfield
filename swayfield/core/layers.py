# SPDX-License-Identifier: GPL-3.0-or-later
"""Find grass layers and their modifiers, and answer small questions about them."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterator

import bpy

from . import compat

MAIN_PREFIX = "SF_Main"
CUSTOM = "CUSTOM"

#: Panel text cache lifetime in seconds. Draw code calls these on every redraw.
_CACHE_SECONDS = 0.5


def is_swayfield_modifier(mod: bpy.types.Modifier) -> bool:
    """True for a Geometry Nodes modifier that uses a Swayfield main group."""
    return mod.type == "NODES" and mod.node_group is not None and mod.node_group.name.startswith(MAIN_PREFIX)


def swayfield_modifiers(ob: bpy.types.Object) -> list[bpy.types.Modifier]:
    return [m for m in ob.modifiers if is_swayfield_modifier(m)]


def iter_layers(ob: bpy.types.Object) -> Iterator:
    """Yield the ``SF_Layer`` entries of ``ob`` (nothing for objects without any)."""
    settings = getattr(ob, "swayfield", None)
    if settings is not None:
        yield from settings.layers


def active_layer(ob: bpy.types.Object):
    """The layer selected in the layer list, or None."""
    settings = getattr(ob, "swayfield", None)
    if settings is None or not settings.layers:
        return None
    index = min(max(settings.active_layer_index, 0), len(settings.layers) - 1)
    return settings.layers[index]


def is_grass_object(ob: bpy.types.Object | None) -> bool:
    """True for a Swayfield layer object (a hair Curves object carrying the modifier)."""
    return ob is not None and (bool(ob.get("sf_grass")) or any(is_swayfield_modifier(m) for m in ob.modifiers))


def surface_of(ob: bpy.types.Object | None) -> bpy.types.Object | None:
    """The surface whose layer list applies to ``ob``.

    ``ob`` itself when it has layers, its surface when ``ob`` is a Swayfield grass
    object, otherwise None. Use it wherever the active object is read, so the
    panel and operators work with either object active.
    """
    if ob is None:
        return None
    if ob.type == "MESH" and len(ob.swayfield.layers):
        return ob
    if is_grass_object(ob):
        parent = ob.parent
        if parent is not None and parent.type == "MESH":
            return parent
        for mod in swayfield_modifiers(ob):
            try:
                surface = compat.get_input(mod, "surface")
            except KeyError:
                continue
            if surface is not None:
                return surface
    return None


def target_mesh(context: bpy.types.Context) -> bpy.types.Object | None:
    """The mesh an operator should work on: the active surface, or a plain active mesh."""
    ob = context.active_object
    surface = surface_of(ob)
    if surface is not None:
        return surface
    if ob is not None and ob.type == "MESH" and not is_grass_object(ob):
        return ob
    return None


def active_target(context: bpy.types.Context):
    """``(surface, layer, modifier)`` for the active layer of the active object's surface, or None.

    The modifier lives on the layer's grass object.
    """
    surface = surface_of(context.active_object)
    if surface is None:
        return None
    layer = active_layer(surface)
    mod = get_modifier(surface, layer)
    if mod is None:
        return None
    return surface, layer, mod


def layer_index(ob: bpy.types.Object, layer) -> int:
    for i, other in enumerate(iter_layers(ob)):
        if other.as_pointer() == layer.as_pointer():
            return i
    return -1


def get_modifier(ob: bpy.types.Object, layer) -> bpy.types.Modifier | None:
    """The modifier on the layer's grass object, or None when the object or modifier is gone.

    ``ob`` is the surface; it is kept so call sites read the same as before.
    """
    if layer is None:
        return None
    grass = layer.grass_object
    if grass is None:
        return None
    mod = grass.modifiers.get(layer.modifier_name)
    if mod is not None and is_swayfield_modifier(mod):
        return mod
    return None


def layer_for_modifier(ob: bpy.types.Object, mod: bpy.types.Modifier):
    for layer in iter_layers(ob):
        if layer.grass_object == mod.id_data and layer.modifier_name == mod.name:
            return layer
    return None


def layer_material(ob: bpy.types.Object, layer) -> bpy.types.Material | None:
    mod = get_modifier(ob, layer)
    if mod is None:
        return None
    try:
        return compat.get_input(mod, "material")
    except KeyError:
        return None


def unique_layer_name(ob: bpy.types.Object, base: str) -> str:
    """``base``, or ``base 2``, ``base 3`` ... when the name is taken on ``ob``."""
    base = base.strip() or "Grass"
    taken = {layer.name for layer in iter_layers(ob)}
    if base not in taken:
        return base
    n = 2
    while f"{base} {n}" in taken:
        n += 1
    return f"{base} {n}"


# ---------------------------------------------------------------------------
# Surface resolution
# ---------------------------------------------------------------------------

#: Painting needs about one vertex per 25 cm.
MAX_EDGE_LENGTH = 0.25

#: How long a measured edge length stays valid, in seconds. The key cannot see vertex edits.
_COARSE_SECONDS = 2.0
_coarse_cache: dict[int, tuple[tuple, float, float]] = {}


def mean_edge_length(ob: bpy.types.Object) -> float:
    """Average world-space edge length of the base mesh in metres (0 when it has no edges)."""
    import numpy as np

    me = ob.data
    n_verts, n_edges = len(me.vertices), len(me.edges)
    if n_verts == 0 or n_edges == 0:
        return 0.0
    matrix = ob.matrix_world
    key = (n_verts, n_edges, tuple(round(v, 6) for row in matrix for v in row))
    now = time.monotonic()
    cached = _coarse_cache.get(me.session_uid)
    if cached is not None and cached[0] == key and now - cached[2] < _COARSE_SECONDS:
        return cached[1]

    co = np.empty(n_verts * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    ends = np.empty(n_edges * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", ends)
    ends = ends.reshape(-1, 2)
    m = np.array(matrix, dtype=np.float32)
    world = co @ m[:3, :3].T
    length = float(np.linalg.norm(world[ends[:, 0]] - world[ends[:, 1]], axis=1).mean())
    if len(_coarse_cache) > 64:
        _coarse_cache.clear()
    _coarse_cache[me.session_uid] = (key, length, now)
    return length


def surface_too_coarse(ob: bpy.types.Object) -> bool:
    """True when the surface has fewer than about 1 vertex per 25 cm, too few to paint cleanly."""
    if ob.type != "MESH":
        return False
    return mean_edge_length(ob) > MAX_EDGE_LENGTH


# ---------------------------------------------------------------------------
# Presets: "Custom" detection
# ---------------------------------------------------------------------------

_label_cache: dict[tuple[str, str], tuple[float, str, str]] = {}
_names_cache: dict[str, str] = {}


def settings_hash(mod: bpy.types.Modifier) -> str:
    """Fingerprint of the preset-controlled settings of ``mod``.

    Uses ``presets.snapshot_hash`` so it matches what the preset operators store.
    """
    try:
        from . import presets
        return presets.snapshot_hash(mod)
    except (ImportError, AttributeError):
        from . import spec
        values = {i.key: repr(compat.get_input(mod, i.key)) for i in spec.INPUTS
                  if i.panel != "Internal" and not i.hidden and i.type in {"FLOAT", "INT", "BOOLEAN"}
                  and compat.has_input(mod, i.name)}
        return hashlib.sha1(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def mark_preset(ob: bpy.types.Object, layer, preset_id: str) -> None:
    """Remember that ``layer`` now matches ``preset_id``. Call right after applying a preset."""
    mod = get_modifier(ob, layer)
    layer.preset = preset_id
    layer.preset_hash = settings_hash(mod) if mod is not None else ""
    _label_cache.pop((ob.name_full, layer.name), None)


def _preset_name(preset_id: str) -> str:
    name = _names_cache.get(preset_id)
    if name is None:
        try:
            from . import presets
            _names_cache.update({p["id"]: p["name"] for p in presets.list_grass_presets()})
        except (ImportError, AttributeError, OSError):
            pass
        name = _names_cache.get(preset_id) or preset_id.replace("_", " ").title()
    return name


def preset_label(ob: bpy.types.Object, layer) -> str:
    """Preset name for the panel, or "Custom" once any setting was changed (AN-01)."""
    if layer.preset in {"", CUSTOM} or not layer.preset_hash:
        return "Custom"
    key = (ob.name_full, layer.name)
    now = time.monotonic()
    cached = _label_cache.get(key)
    if cached is not None and now - cached[0] < _CACHE_SECONDS and cached[2] == layer.preset_hash:
        return cached[1]
    mod = get_modifier(ob, layer)
    if mod is None:
        label = "Custom"
    else:
        label = _preset_name(layer.preset) if settings_hash(mod) == layer.preset_hash else "Custom"
    _label_cache[key] = (now, label, layer.preset_hash)
    return label


def clear_caches() -> None:
    _label_cache.clear()
    _coarse_cache.clear()
