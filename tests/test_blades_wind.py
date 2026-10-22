# SPDX-License-Identifier: GPL-3.0-or-later
"""SF_Blade, SF_Wind, SF_Effectors and SF_EffectorPoint, tested on fabricated points.

Each test builds a wrapper tree: grid -> points with the contract attributes ->
SF_Blade -> SF_Wind -> (Curve to Points -> Points to Vertices), so results can
be read back as a mesh on any supported Blender version.

Headless semantics: ``evaluated_depsgraph_get()`` in background mode is a
viewport depsgraph, so Is Viewport is True there and Mute in Viewport applies.
"""

from __future__ import annotations

import math

import bpy
import numpy as np
import pytest
from mathutils import Vector

from swayfield.core import compat, nodes, spec

CURVE = "_t_curve"
RADIUS = "_t_radius"

POINT_ATTRS = {
    spec.ATTR_ID: "INT",
    spec.ATTR_UP: "FLOAT_VECTOR",
    spec.ATTR_RANDOM: "FLOAT",
    spec.ATTR_CLUMP: "FLOAT",
    spec.ATTR_CLUMP_CENTER: "FLOAT_VECTOR",
    spec.ATTR_WISP: "BOOLEAN",
    spec.ATTR_LENGTH: "FLOAT",
    spec.ATTR_WIND_SCALE: "FLOAT",
    spec.ATTR_VARIATION: "FLOAT",
    spec.ATTR_DIST: "FLOAT",
    spec.ATTR_LOD: "INT",
    spec.ATTR_WIDTH: "FLOAT",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _evaluated(ob):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    return ob.evaluated_get(depsgraph)


def _set_inputs(node, values: dict) -> None:
    for key, value in values.items():
        item = spec.BY_KEY.get(key)
        node.inputs[item.name if item else key].default_value = value


def _fabricated_points(b, size, count, lod, clump_offset=(0.0, 0.0, 0.0)):
    """Grid -> points carrying every contract attribute Distribute and Cull would write."""
    grid = b.out("GeometryNodeMeshGrid", {"Size X": size[0], "Size Y": size[1],
                                          "Vertices X": count[0], "Vertices Y": count[1]})
    pts = b.out("GeometryNodeMeshToPoints", {"Mesh": grid})
    index = b.out("GeometryNodeInputIndex")
    lod_value = b.math("MODULO", index, 3.0) if lod == "cycle" else lod
    values = {
        spec.ATTR_ID: index,
        spec.ATTR_UP: (0.0, 0.0, 1.0),
        spec.ATTR_RANDOM: b.random_float(index, seed=1),
        spec.ATTR_CLUMP: b.random_float(index, seed=2),
        spec.ATTR_CLUMP_CENTER: b.vmath("ADD", b.out("GeometryNodeInputPosition"), clump_offset),
        spec.ATTR_WISP: False,
        spec.ATTR_LENGTH: 1.0,
        spec.ATTR_WIND_SCALE: 1.0,
        spec.ATTR_VARIATION: 0.3,
        spec.ATTR_DIST: 5.0,
        spec.ATTR_LOD: lod_value,
        spec.ATTR_WIDTH: 1.0,
    }
    for name, data_type in POINT_ATTRS.items():
        pts = b.store(pts, name, values[name], data_type=data_type)
    return pts


def _setup(name="SF_Test", *, size=(4.0, 4.0), count=(5, 5), lod=0, blade=None, wind=None,
           with_wind=True, as_mesh=True, clump_offset=(0.0, 0.0, 0.0)):
    """Object whose modifier runs fabricated points through Blade (and Wind)."""
    from swayfield.core.nodes import builder

    mesh = bpy.data.meshes.new(name)
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(ob)
    tree = bpy.data.node_groups.new(name, "GeometryNodeTree")
    builder.add_socket(tree, "Geometry", "GEOMETRY", "INPUT")
    builder.add_socket(tree, "Geometry", "GEOMETRY", "OUTPUT")
    b = builder.NodeBuilder(tree)
    pts = _fabricated_points(b, size, count, lod, clump_offset)
    blade_node = b.group(nodes.ensure("blade"), {"Points": pts}, forward=False)
    _set_inputs(blade_node, blade or {})
    geo = blade_node.outputs["Blades"]
    wind_node = None
    if with_wind:
        wind_node = b.group(nodes.ensure("wind"), {"Blades": geo}, forward=False)
        _set_inputs(wind_node, wind or {})
        geo = wind_node.outputs["Blades"]
    if as_mesh:
        geo = b.store(geo, CURVE, b.out("GeometryNodeCurveOfPoint"), data_type="INT")
        geo = b.store(geo, RADIUS, b.out("GeometryNodeInputRadius"))
        geo = b.out("GeometryNodeCurveToPoints", {"Curve": geo}, mode="EVALUATED")
        geo = b.out("GeometryNodePointsToVertices", {"Points": geo})
    b.output("Geometry", geo)
    ob.modifiers.new("Test", "NODES").node_group = tree
    return ob, blade_node, wind_node


def _read(ob, *names):
    """(positions (N, 3), {attribute: array}) of the evaluated mesh."""
    me = _evaluated(ob).data
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    out = {}
    for name in (CURVE, *names):
        attr = me.attributes[name]
        width = 3 if attr.data_type == "FLOAT_VECTOR" else 1
        prop = "vector" if width == 3 else "value"
        dtype = {"INT": np.int64, "BOOLEAN": bool}.get(attr.data_type, np.float64)
        arr = np.empty(n * width, dtype=dtype)
        attr.data.foreach_get(prop, arr)
        out[name] = arr.reshape(n, 3) if width == 3 else arr
    return co.reshape(n, 3), out


def _curve_starts(curve_index):
    return np.flatnonzero(np.r_[True, curve_index[1:] != curve_index[:-1]])


def _arc_lengths(co, curve_index):
    seg = np.linalg.norm(np.diff(co, axis=0), axis=1)
    seg[curve_index[1:] != curve_index[:-1]] = 0.0
    seg = np.r_[0.0, seg]
    return np.add.reduceat(seg, _curve_starts(curve_index))


def _tips(co, curve_index):
    ends = np.r_[_curve_starts(curve_index)[1:] - 1, len(co) - 1]
    return co[ends]


def _frame(frame: int) -> None:
    bpy.context.scene.frame_set(frame)


# ---------------------------------------------------------------------------
# Blades
# ---------------------------------------------------------------------------

def test_point_counts_follow_lod_bands(scene):
    ob, blade, _ = _setup(lod="cycle", with_wind=False, count=(6, 5))
    _, attrs = _read(ob, spec.ATTR_LOD)
    curves = attrs[CURVE]
    sizes = np.bincount(curves)
    lods = attrs[spec.ATTR_LOD][_curve_starts(curves)]
    assert len(sizes) == 30
    expected = {0: spec.get("blade_points").default, 1: spec.get("lod_mid_points").default,
                2: spec.get("lod_far_points").default}
    for lod, points in expected.items():
        assert set(sizes[lods == lod]) == {points}

    blade.inputs["Force Lite"].default_value = True
    _, attrs = _read(ob)
    assert set(np.bincount(attrs[CURVE])) == {3}


def test_blade_attributes_and_length(scene):
    ob, _, _ = _setup(with_wind=False, blade={"length_min": 0.7, "length_max": 0.7})
    co, attrs = _read(ob, spec.ATTR_FACTOR, spec.ATTR_ROOT, spec.ATTR_RANDOM, spec.ATTR_VARIATION,
                      spec.ATTR_CLUMP, spec.ATTR_DIST, spec.ATTR_WIND_SCALE, spec.ATTR_WISP, spec.ATTR_UP,
                      spec.ATTR_LOD, spec.ATTR_ID)
    curves = attrs[CURVE]
    starts = _curve_starts(curves)
    factor = attrs[spec.ATTR_FACTOR]
    assert np.allclose(factor[starts], 0.0)
    assert np.allclose(_tips(factor[:, None], curves)[:, 0], 1.0)
    # sf_root is the first point; every point of a blade shares the blade's values.
    assert np.allclose(attrs[spec.ATTR_ROOT][starts], co[starts], atol=1e-6)
    for name in (spec.ATTR_ROOT, spec.ATTR_RANDOM, spec.ATTR_ID):
        values = attrs[name]
        assert np.allclose(values, values[starts][curves], atol=1e-6), name
    assert np.allclose(attrs[spec.ATTR_VARIATION], 0.3)
    assert len(np.unique(attrs[spec.ATTR_ID])) == len(starts)
    # Lean, curl and tilt never change the length: the rest blade is an exact arc.
    lengths = _arc_lengths(co, curves)
    assert np.allclose(lengths, 0.7, rtol=0.01)
    # Grows upward, with some rest lean.
    tips = _tips(co, curves)
    assert np.all(tips[:, 2] > 0.5)


def test_curve_radius_tapers(scene):
    ob, _, _ = _setup(with_wind=False, blade={"root_width": 0.01, "tip_taper": 0.9})
    _, attrs = _read(ob, RADIUS, spec.ATTR_FACTOR)
    radius, factor = attrs[RADIUS], attrs[spec.ATTR_FACTOR]
    assert np.allclose(radius[factor == 0.0], 0.005, rtol=1e-4)
    assert np.allclose(radius[factor == 1.0], 0.0005, rtol=1e-3)


def _instance_matrices(ob):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    return [inst.matrix_world.copy() for inst in depsgraph.object_instances
            if inst.is_instance and inst.parent and inst.parent.original == ob]


def test_clump_pull_gathers_tips(scene):
    ob, blade, _ = _setup(with_wind=False, clump_offset=(-0.3, 0.0, 0.0),
                          blade={"length_min": 0.6, "length_max": 0.6, "rest_lean": 0.0, "random_tilt": 0.0})
    co, attrs = _read(ob)
    curves = attrs[CURVE]
    lean = _tips(co, curves) - co[_curve_starts(curves)]
    assert abs(lean[:, 0].mean()) < 0.1  # curl alone goes in random directions
    blade.inputs["Clump Pull"].default_value = 1.0
    co, attrs = _read(ob)
    lean = _tips(co, curves) - co[_curve_starts(curves)]
    assert np.all(lean[:, 0] < -0.1)
    assert np.allclose(_arc_lengths(co, curves), 0.6, rtol=0.01)


def test_instances_stay_instances(scene):
    coll = bpy.data.collections.new("Tufts")
    scene.collection.children.link(coll)
    cube = bpy.data.objects.new("Tuft", bpy.data.meshes.new("Tuft"))
    coll.objects.link(cube)
    source = spec.get("blade_source").item_index("INSTANCES")
    ob, _, wind = _setup(as_mesh=False, blade={"blade_source": source, "instance_collection": coll})
    wind.mute = True
    rest = _instance_matrices(ob)
    wind.mute = False
    swayed = _instance_matrices(ob)
    assert len(rest) == len(swayed) == 25
    ev = _evaluated(ob)
    assert len(ev.data.vertices) == 0  # nothing realised
    # Rigid sway turns instances about their own origin: they stay on the grid, but tilt.
    for a, b in zip(rest, swayed, strict=False):
        assert (a.translation - b.translation).length < 1e-5
    up = Vector((0.0, 0.0, 1.0))
    tilt = [(a.to_3x3() @ up).normalized().dot((b.to_3x3() @ up).normalized())
            for a, b in zip(rest, swayed, strict=False)]
    assert min(tilt) < math.cos(math.radians(20))
    if hasattr(ev, "evaluated_geometry"):  # Blender 4.4+
        geometry = ev.evaluated_geometry()  # keep it alive while the cloud is read
        cloud = geometry.instances_pointcloud()
        amount = np.array([d.value for d in cloud.attributes[spec.ATTR_WIND].data])
        assert len(amount) == 25 and amount.max() > 0.3


# ---------------------------------------------------------------------------
# Wind
# ---------------------------------------------------------------------------

def test_bending_preserves_length(scene):
    ob, _, wind = _setup(count=(8, 8), size=(10.0, 10.0))
    rest, attrs = _read(ob)
    wind.mute = True
    rest, attrs_rest = _read(ob)
    wind.mute = False
    bent, attrs = _read(ob, spec.ATTR_WIND)
    assert np.array_equal(attrs[CURVE], attrs_rest[CURVE])
    assert np.abs(bent - rest).max() > 0.1
    assert np.allclose(_arc_lengths(bent, attrs[CURVE]), _arc_lengths(rest, attrs[CURVE]), rtol=1e-4)
    assert 0.0 <= attrs[spec.ATTR_WIND].min() and attrs[spec.ATTR_WIND].max() <= 1.0


def test_direction_zero_blows_toward_plus_x(scene):
    ob, _, wind = _setup(count=(8, 8), size=(10.0, 10.0), wind={"direction": 0.0})
    wind.mute = True
    rest, attrs = _read(ob)
    wind.mute = False
    bent, _ = _read(ob)
    move = _tips(bent, attrs[CURVE]) - _tips(rest, attrs[CURVE])
    assert np.all(move[:, 0] > 0.05)
    assert move[:, 0].mean() > 5 * np.abs(move[:, 1]).mean()

    wind.inputs["Direction"].default_value = math.radians(90)
    turned, _ = _read(ob)
    move = _tips(turned, attrs[CURVE]) - _tips(rest, attrs[CURVE])
    assert move[:, 1].mean() > 5 * np.abs(move[:, 0]).mean()


def test_direction_object_sets_heading(scene):
    empty = bpy.data.objects.new("WindDir", None)
    scene.collection.objects.link(empty)
    empty.rotation_euler = (0.0, 0.0, math.radians(180))
    ob, _, wind = _setup(count=(6, 6), size=(8.0, 8.0), wind={"direction_object": empty})
    wind.mute = True
    rest, attrs = _read(ob)
    wind.mute = False
    bent, _ = _read(ob)
    move = _tips(bent, attrs[CURVE]) - _tips(rest, attrs[CURVE])
    assert np.all(move[:, 0] < -0.05)


def test_loop_is_exact(scene):
    ob, _, _ = _setup(count=(6, 6), size=(20.0, 20.0), wind={"loop_enable": True, "loop_frames": 24})
    _frame(1)
    first, _ = _read(ob, spec.ATTR_WIND)
    _frame(13)
    middle, _ = _read(ob)
    _frame(24)
    last, _ = _read(ob)
    _frame(25)
    again, _ = _read(ob)
    assert np.array_equal(first, again)
    assert np.abs(middle - first).max() > 1e-3
    # Seamless: the step from frame 24 to 25 is an ordinary one-frame step.
    _frame(2)
    second, _ = _read(ob)
    assert np.abs(again - last).max() < 3 * np.abs(second - first).max() + 1e-4


def test_freeze_holds_pose(scene):
    ob, _, wind = _setup(count=(5, 5), wind={"freeze": True, "time_offset": 3.0})
    _frame(1)
    a, _ = _read(ob)
    _frame(37)
    b, _ = _read(ob)
    assert np.array_equal(a, b)
    wind.mute = True
    rest, _ = _read(ob)
    assert np.abs(b - rest).max() > 0.1  # frozen, not switched off


def test_mute_viewport_gives_rest_pose(scene):
    ob, _, wind = _setup(count=(5, 5))
    wind.mute = True
    rest, _ = _read(ob)
    wind.mute = False
    wind.inputs["Mute in Viewport"].default_value = True
    muted, attrs = _read(ob, spec.ATTR_WIND)
    assert np.allclose(muted, rest)
    assert np.all(attrs[spec.ATTR_WIND] == 0.0)


def test_topology_constant_across_frames(scene):
    ob, _, _ = _setup(lod="cycle", count=(6, 6))
    reference = None
    for frame in (1, 10, 50, 51):
        _frame(frame)
        co, attrs = _read(ob, spec.ATTR_ID, spec.ATTR_FACTOR)
        key = (len(co), attrs[CURVE].tolist(), attrs[spec.ATTR_ID].tolist(), attrs[spec.ATTR_FACTOR].tolist())
        if reference is None:
            reference = key
        assert key == reference


def test_rigid_sway_keeps_shape(scene):
    ob, _, wind = _setup(count=(5, 5))
    wind.mute = True
    rest, attrs = _read(ob)
    wind.mute = False
    wind.inputs["Force Rigid"].default_value = True
    rigid, _ = _read(ob)
    curves = attrs[CURVE]
    roots = _curve_starts(curves)
    # Rigid rotation about the root keeps every distance to the root.
    d_rest = np.linalg.norm(rest - rest[roots][curves], axis=1)
    d_rigid = np.linalg.norm(rigid - rigid[roots][curves], axis=1)
    assert np.allclose(d_rest, d_rigid, atol=1e-5)
    assert np.abs(rigid - rest).max() > 0.05


def test_animation_lod_sways_far_blades_rigidly(scene):
    # Fabricated blades are 5 m from the camera: an LOD band ending at 1 m makes them all far.
    ob, _, wind = _setup(count=(5, 5), wind={"anim_lod_start": 0.0, "anim_lod_end": 1.0})
    wind.mute = True
    rest, attrs = _read(ob)
    wind.mute = False
    far, _ = _read(ob)
    roots = _curve_starts(attrs[CURVE])
    d_rest = np.linalg.norm(rest - rest[roots][attrs[CURVE]], axis=1)
    d_far = np.linalg.norm(far - far[roots][attrs[CURVE]], axis=1)
    assert np.allclose(d_rest, d_far, atol=1e-5)
    wind.inputs["Animation LOD"].default_value = False
    near, _ = _read(ob)
    d_near = np.linalg.norm(near - near[roots][attrs[CURVE]], axis=1)
    assert np.abs(d_near - d_rest).max() > 0.01  # bending changes root-to-point distances


def test_gusts_travel_at_gust_speed(scene):
    # One row of blades 1 m apart along the wind; gusts only (no lag, flutter, evolution).
    ob, _, _ = _setup(size=(60.0, 0.0), count=(61, 1), wind={
        "tip_lag": 0.0, "flutter_strength": 0.0, "gust_evolution": 0.0, "gust_speed": 4.0})
    fps = scene.render.fps / scene.render.fps_base
    _frame(1)
    co, attrs = _read(ob, spec.ATTR_WIND)
    starts = _curve_starts(attrs[CURVE])
    x0, w0 = np.round(co[starts, 0]).astype(int), attrs[spec.ATTR_WIND][starts]
    _frame(1 + int(fps))  # one second later
    _, attrs = _read(ob, spec.ATTR_WIND)
    w1 = attrs[spec.ATTR_WIND][starts]
    assert np.std(w0) > 0.02
    # The pattern at x one second later equals the pattern at x - 4 m now.
    order = np.argsort(x0)
    w0, w1 = w0[order], w1[order]
    assert np.allclose(w1[4:], w0[:-4], atol=1e-3)


def test_rolling_meadow_defaults(scene):
    ob, _, wind = _setup(size=(40.0, 40.0), count=(41, 41))
    wind.mute = True
    rest, attrs = _read(ob)
    wind.mute = False
    _frame(30)
    bent, attrs = _read(ob, spec.ATTR_WIND)
    curves = attrs[CURVE]
    move = _tips(bent, curves) - _tips(rest, curves)
    assert move[:, 0].mean() > 0.2  # strong crosswind toward +X
    # Tip direction (last segment) from vertical: nearly horizontal at the gust peaks.
    ends = np.r_[_curve_starts(curves)[1:] - 1, len(bent) - 1]
    tangent = bent[ends] - bent[ends - 1]
    tilt = np.degrees(np.arccos(tangent[:, 2] / np.linalg.norm(tangent, axis=1)))
    assert tilt.max() > 70.0


def test_sf_wind_reads_as_gust_streaks(scene):
    # sf_wind is flattening beyond the steady lean: mostly dark gaps, bright gust crests.
    ob, _, wind = _setup(size=(60.0, 60.0), count=(61, 61))
    for frame in (1, 60):
        _frame(frame)
        _, attrs = _read(ob, spec.ATTR_WIND)
        amount = attrs[spec.ATTR_WIND]
        assert 0.0 <= amount.min() and amount.max() <= 1.0
        p10, p50, p90 = np.percentile(amount, [10, 50, 90])
        assert p10 < 0.1 and p50 < 0.5 and p90 > 0.7
    # Steady lean alone (no gusts, waves or effectors) is not "flattened": sf_wind stays 0.
    wind.inputs["Gust Strength"].default_value = 0.0
    _, attrs = _read(ob, spec.ATTR_WIND)
    assert np.allclose(attrs[spec.ATTR_WIND], 0.0, atol=1e-6)


# ---------------------------------------------------------------------------
# Effectors
# ---------------------------------------------------------------------------

def _effector(name, kind, location=(0.0, 0.0, 0.0), radius=3.0, strength=1.0, falloff=0.5):
    coll = bpy.data.collections.get("SF_Effectors")
    if coll is None:
        coll = bpy.data.collections.new("SF_Effectors")
        bpy.context.scene.collection.children.link(coll)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(0.0, 0.0, 0.0)], [], [])
    ob = bpy.data.objects.new(name, mesh)
    ob.location = location
    coll.objects.link(ob)
    mod = ob.modifiers.new("Effector", "NODES")
    mod.node_group = nodes.ensure("effector_point")
    from swayfield.core.nodes import effector_point

    compat.set_input(mod, "Type", effector_point.TYPES.index(kind))
    compat.set_input(mod, "Radius", radius)
    compat.set_input(mod, "Strength", strength)
    compat.set_input(mod, "Falloff", falloff)
    return ob, coll


def _effector_motion(scene, kind, **kwargs):
    """Tip motion (wind minus rest) and root positions, with only the effector acting."""
    _, coll = _effector("Effector", kind, **kwargs)
    ob, _, wind = _setup(size=(5.0, 5.0), count=(11, 11), wind={"intensity": 0.0, "effector_collection": coll})
    wind.mute = True
    rest, attrs = _read(ob)
    wind.mute = False
    bent, _ = _read(ob)
    curves = attrs[CURVE]
    roots = rest[_curve_starts(curves)]
    return _tips(bent, curves) - _tips(rest, curves), roots


def test_effector_point_outputs_settings(scene):
    ob, _ = _effector("Probe", "TRAMPLE", location=(1.0, 2.0, 0.0), radius=2.0, strength=-1.5)
    ob.scale = (1.0, 3.0, 1.0)
    geometry = _evaluated(ob)
    if hasattr(geometry, "evaluated_geometry"):
        gs = geometry.evaluated_geometry()
        cloud = gs.pointcloud
        assert len(cloud.points) == 1
        assert cloud.attributes["sf_type"].data[0].value == 2
        assert cloud.attributes["sf_radius"].data[0].value == pytest.approx(6.0)
        assert cloud.attributes["sf_strength"].data[0].value == pytest.approx(-1.5)
        # The viewport circle is a separate mesh component (Is Viewport is True headless).
        assert gs.mesh is not None and len(gs.mesh.edges) > 0


def test_no_effectors_means_no_force(scene):
    coll = bpy.data.collections.new("Empty")
    ob, _, wind = _setup(count=(5, 5), wind={"intensity": 0.0, "effector_collection": coll})
    wind.mute = True
    rest, _ = _read(ob)
    wind.mute = False
    bent, attrs = _read(ob, spec.ATTR_WIND)
    assert np.allclose(bent, rest, atol=1e-6)
    assert np.allclose(attrs[spec.ATTR_WIND], 0.0)


def test_vortex_swirls_counter_clockwise(scene):
    move, roots = _effector_motion(scene, "VORTEX")
    r = np.linalg.norm(roots[:, :2], axis=1)
    inside = (r > 0.3) & (r < 2.0)
    radial = roots[inside, :2] / r[inside, None]
    tangent = np.stack([-radial[:, 1], radial[:, 0]], axis=1)
    along = np.sum(move[inside, :2] * tangent, axis=1)
    across = np.sum(move[inside, :2] * radial, axis=1)
    assert np.all(along > 0.05)
    assert np.abs(across).max() < 0.25 * along.min() + 1e-3
    # Outside the radius nothing moves.
    assert np.abs(move[r > 3.2]).max() < 1e-5


def test_radial_blast_pushes_outward(scene):
    move, roots = _effector_motion(scene, "RADIAL_BLAST", location=(0.5, 0.0, 0.0))
    offset = roots[:, :2] - np.array([0.5, 0.0])
    r = np.linalg.norm(offset, axis=1)
    inside = (r > 0.3) & (r < 2.0)
    outward = np.sum(move[inside, :2] * offset[inside] / r[inside, None], axis=1)
    assert np.all(outward > 0.05)


def test_trample_parts_and_flattens(scene):
    move, roots = _effector_motion(scene, "TRAMPLE", location=(0.0, 0.0, 0.0), radius=2.0)
    r = np.linalg.norm(roots[:, :2], axis=1)
    inside = (r > 0.3) & (r < 1.0)
    outward = np.sum(move[inside, :2] * roots[inside, :2] / r[inside, None], axis=1)
    assert np.all(outward > 0.1)


def test_shelter_calms_wind(scene):
    _, coll = _effector("Shelter", "SHELTER", radius=1.5, strength=1.0, falloff=0.2)
    ob, _, wind = _setup(size=(8.0, 8.0), count=(9, 9), wind={"effector_collection": coll})
    wind.mute = True
    rest, attrs = _read(ob)
    wind.mute = False
    bent, attrs = _read(ob, spec.ATTR_WIND)
    curves = attrs[CURVE]
    starts = _curve_starts(curves)
    r = np.linalg.norm(rest[starts, :2], axis=1)
    move = np.linalg.norm(_tips(bent, curves) - _tips(rest, curves), axis=1)
    assert move[r < 0.5].max() < 0.02
    assert move[r > 2.0].min() > 0.1
    assert attrs[spec.ATTR_WIND][starts][r < 0.5].max() < 0.05


def test_effector_flattening_shows_in_sf_wind(scene):
    # With no steady wind, a vortex's push is all "beyond the steady lean".
    move, roots = _effector_motion(scene, "VORTEX")
    ob = bpy.data.objects["SF_Test"]
    _, attrs = _read(ob, spec.ATTR_WIND)
    root_amount = attrs[spec.ATTR_WIND][_curve_starts(attrs[CURVE])]
    r = np.linalg.norm(roots[:, :2], axis=1)
    assert root_amount[(r > 0.3) & (r < 1.0)].min() > 0.5
    assert root_amount[r > 3.2].max() < 1e-6
