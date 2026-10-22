# SPDX-License-Identifier: GPL-3.0-or-later
"""Blade counter and budget guard.

Panel code calls these on every redraw, so results are cached for a short time
per object, layer and frame, and nothing here evaluates more than the already
evaluated depsgraph.
"""

from __future__ import annotations

import time
from typing import NamedTuple

import bpy

from . import compat, layers

#: How long a counted value stays valid, in seconds.
_CACHE_SECONDS = 0.5

_object_cache: dict[tuple, tuple[float, int]] = {}
#: How long a measured area stays valid, in seconds. The key cannot see vertex edits.
_AREA_SECONDS = 2.0
_area_cache: dict[int, tuple[tuple, float, float]] = {}


class Totals(NamedTuple):
    viewport: int
    render: int


def invalidate() -> None:
    """Forget cached counts, e.g. after an operator changed density."""
    _object_cache.clear()
    _area_cache.clear()


# ---------------------------------------------------------------------------
# Counting evaluated geometry
# ---------------------------------------------------------------------------

def _geometry_blades(ob_eval: bpy.types.Object, ribbons: bool, blade_points: int, base_verts: int) -> int:
    """Blades in the evaluated geometry of ``ob_eval``.

    A blade is one curve (strands), one instance (custom instances) or one point
    (points display). Ribbons are mesh strips, so they are estimated from the
    vertices the surface gained.
    """
    geometry = ob_eval.evaluated_geometry()
    total = 0
    curves = geometry.curves
    if curves is not None:
        total += len(curves.curves)
    cloud = geometry.pointcloud
    if cloud is not None:
        total += len(cloud.points)
    try:
        instances = geometry.instances_pointcloud()
    except RuntimeError:
        instances = None
    if instances is not None:
        total += len(instances.points)
    if ribbons and geometry.mesh is not None:
        extra = max(0, len(geometry.mesh.vertices) - base_verts)
        total += extra // max(2 * blade_points, 1)
    return total


def _legacy_blades(ob: bpy.types.Object, depsgraph: bpy.types.Depsgraph) -> int:
    """Blender 4.2: count curve and point cloud components through the depsgraph instances."""
    total = 0
    for inst in depsgraph.object_instances:
        if not inst.is_instance or inst.parent is None or inst.parent.original != ob:
            continue
        data = inst.object.data
        if inst.object.type in {"CURVES", "CURVE"} and hasattr(data, "curves"):
            total += len(data.curves)
        elif inst.object.type == "POINTCLOUD" and hasattr(data, "points"):
            total += len(data.points)
    return total


def _grass_total(grass: bpy.types.Object, depsgraph: bpy.types.Depsgraph | None = None) -> int:
    """Blades in the evaluated viewport geometry of one grass object. Cached."""
    frame = bpy.context.scene.frame_current
    key = (grass.name_full, frame)
    now = time.monotonic()
    cached = _object_cache.get(key)
    if cached is not None and now - cached[0] < _CACHE_SECONDS:
        return cached[1]
    depsgraph = depsgraph or bpy.context.evaluated_depsgraph_get()
    grass_eval = grass.evaluated_get(depsgraph)
    ribbons = False
    blade_points = 8
    base_verts = 0
    for mod in layers.swayfield_modifiers(grass):
        try:
            ribbons = ribbons or compat.get_input(mod, "blade_source") == 1
            blade_points = int(compat.get_input(mod, "blade_points"))
            if compat.get_input(mod, "mask_preview"):
                surface = compat.get_input(mod, "surface")
                base_verts = len(surface.data.vertices) if surface is not None else 0
        except KeyError:
            pass
    try:
        if hasattr(grass_eval, "evaluated_geometry"):
            total = _geometry_blades(grass_eval, ribbons, blade_points, base_verts)
        else:
            total = _legacy_blades(grass, depsgraph)
    except (RuntimeError, ReferenceError, AttributeError):
        total = 0
    _object_cache[key] = (now, total)
    return total


def viewport_fraction(mod: bpy.types.Modifier) -> float:
    """Share of blades the viewport shows compared to a render (1.0 = all of them)."""
    fraction = 1.0
    try:
        if compat.get_input(mod, "optimised"):
            fraction = float(compat.get_input(mod, "viewport_density")) / 100.0
        fraction *= float(compat.get_input(mod, "simplify"))
    except KeyError:
        pass
    return min(max(fraction, 0.0), 1.0)


def count_blades(ob: bpy.types.Object, mod: bpy.types.Modifier) -> int:
    """Blades the viewport currently shows for the layer ``mod``.

    Counted from the evaluated geometry of the layer's own grass object, so layers
    are counted separately. ``ob`` (the surface) is accepted for call-site symmetry.
    """
    if not mod.show_viewport:
        return 0
    grass = mod.id_data
    if grass.hide_viewport:
        return 0
    return _grass_total(grass)


def estimate_render_count(ob: bpy.types.Object, mod: bpy.types.Modifier) -> int:
    """Expected blades in a final render: the viewport count divided by the viewport fraction."""
    if not mod.show_render:
        return 0
    fraction = viewport_fraction(mod)
    viewport = count_blades(ob, mod) if mod.show_viewport else 0
    if fraction > 0.0 and viewport > 0:
        return int(round(viewport / fraction))
    try:
        surface = compat.get_input(mod, "surface") or ob
        return int(estimate_from_area(surface, float(compat.get_input(mod, "density"))))
    except KeyError:
        return 0


# ---------------------------------------------------------------------------
# Estimating before evaluation
# ---------------------------------------------------------------------------

def surface_area(ob: bpy.types.Object) -> float:
    """World-space area of the base mesh in square metres."""
    import numpy as np

    me = ob.data
    n_verts = len(me.vertices)
    if n_verts == 0 or len(me.polygons) == 0:
        return 0.0
    matrix = ob.matrix_world
    key = (n_verts, len(me.polygons), tuple(round(v, 6) for row in matrix for v in row))
    now = time.monotonic()
    cached = _area_cache.get(me.session_uid)
    if cached is not None and cached[0] == key and now - cached[2] < _AREA_SECONDS:
        return cached[1]

    me.calc_loop_triangles()
    tris = me.loop_triangles
    co = np.empty(n_verts * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    world = co.reshape(-1, 3) @ np.array(matrix, dtype=np.float32)[:3, :3].T
    idx = np.empty(len(tris) * 3, dtype=np.int32)
    tris.foreach_get("vertices", idx)
    idx = idx.reshape(-1, 3)
    a, b, c = world[idx[:, 0]], world[idx[:, 1]], world[idx[:, 2]]
    area = float(np.linalg.norm(np.cross(b - a, c - a), axis=1).sum() * 0.5)
    if len(_area_cache) > 64:
        _area_cache.clear()
    _area_cache[me.session_uid] = (key, area, now)
    return area


def estimate_from_area(ob: bpy.types.Object, density: float) -> int:
    """Blades ``ob`` would grow at ``density`` per square metre, before anything is evaluated."""
    return int(surface_area(ob) * max(density, 0.0))


# ---------------------------------------------------------------------------
# Scene totals and the budget guard
# ---------------------------------------------------------------------------

def scene_totals(context: bpy.types.Context) -> Totals:
    """Viewport and estimated render blades across every Swayfield layer in the scene."""
    viewport = render = 0
    for ob in context.scene.objects:
        if ob.type != "CURVES" or not layers.is_grass_object(ob):
            continue
        for mod in layers.swayfield_modifiers(ob):
            surface = ob.parent
            viewport += count_blades(surface, mod)
            render += estimate_render_count(surface, mod)
    return Totals(viewport, render)


def budget_limit(context: bpy.types.Context) -> int:
    return int(context.scene.swayfield.budget)


def would_exceed_budget(context: bpy.types.Context, extra: int = 0) -> bool:
    """True when the viewport count plus ``extra`` more blades is over the scene's budget."""
    return scene_totals(context).viewport + max(int(extra), 0) > budget_limit(context)
