# SPDX-License-Identifier: GPL-3.0-or-later
"""SF_Masks, SF_Distribute and SF_Cull, run through a small wrapper group.

The wrapper does what SF_Main does around these stages: surface to world
space, Masks, Distribute, Cull, back to object space. It ends with Points to
Vertices so the evaluated object is a mesh whose attributes Python can read.

Background evaluation (``blender -b``) uses a viewport depsgraph, so Is
Viewport is true there. The render branch is reached by rendering a tiny
Cycles frame and reading the RENDER depsgraph passed to ``frame_change_post``.
"""

from __future__ import annotations

import math

import bpy
import mathutils
import numpy as np
import pytest

from swayfield.core import compat, nodes, spec
from swayfield.core.nodes import builder, cull, distribute, masks

KEYS = tuple(dict.fromkeys(masks.INPUT_KEYS + distribute.INPUT_KEYS + cull.INPUT_KEYS))
FAST = {"density": 100.0, "density_ceiling": 200.0, "min_distance": 0.01}


def _transform(b: builder.NodeBuilder, geometry, matrix):
    node = b.node("GeometryNodeTransform", {"Geometry": geometry})
    if "Mode" in {s.name for s in node.inputs}:
        node.inputs["Mode"].default_value = "Matrix"  # 5.x: menu socket
    else:
        node.mode = "MATRIX"
    b.link(matrix, builder.find_socket(node.inputs, "Transform"))
    return node.outputs[0]


def _wrapper(with_cull: bool = True, raw: bool = False):
    """Masks, Distribute and Cull between world-space transforms.

    ``raw=True`` feeds Cull from a plain Distribute Points on Faces node
    instead, like a scatter baked at full density.
    """
    tree = bpy.data.node_groups.new("SF_TestScatter", "GeometryNodeTree")
    builder.add_socket(tree, "Geometry", "GEOMETRY", "INPUT")
    builder.add_spec_inputs(tree, KEYS)
    builder.add_socket(tree, "Geometry", "GEOMETRY", "OUTPUT")
    b = builder.NodeBuilder(tree)
    info = b.node("GeometryNodeObjectInfo", {"Object": b.out("GeometryNodeSelfObject")}, transform_space="ORIGINAL")
    geo = _transform(b, b.inp("Geometry"), info.outputs["Transform"])
    if raw:
        geo = b.out("GeometryNodeDistributePointsOnFaces", {"Mesh": geo, "Density Max": b.inp("density")},
                    distribute_method="POISSON")
    else:
        geo = b.group(nodes.ensure("masks", rebuild=True), {"Surface": geo}).outputs["Surface"]
        geo = b.group(nodes.ensure("distribute", rebuild=True), {"Surface": geo}).outputs["Points"]
    if with_cull:
        geo = b.group(nodes.ensure("cull", rebuild=True), {"Points": geo}).outputs["Points"]
    inverse = b.out("FunctionNodeInvertMatrix", {"Matrix": info.outputs["Transform"]}, output="Matrix")
    geo = _transform(b, geo, inverse)
    b.output("Geometry", b.out("GeometryNodePointsToVertices", {"Points": geo}))
    b.arrange()
    return tree


def _scatter(ob, with_cull: bool = True, raw: bool = False, **values):
    mod = ob.modifiers.new("Swayfield", "NODES")
    mod.node_group = _wrapper(with_cull, raw)
    _set(ob, **{**FAST, **values})
    return mod


def _set(ob, **values) -> None:
    mod = ob.modifiers["Swayfield"]
    for key, value in values.items():
        compat.set_input(mod, key, value)
    # Writing 5.x modifier inputs from Python does not tag the object.
    ob.update_tag()


def _points(ob) -> dict:
    """Evaluated points in object space: ``co`` (N×3) and every attribute of the result."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    return _read(ob.evaluated_get(depsgraph).data)


def _render_points(ob) -> dict:
    """Points as evaluated for a final render (Is Viewport false).

    Renders 8×8 px with Cycles on the CPU and reads the render depsgraph that
    ``frame_change_post`` receives.
    """
    found = {}

    def grab(scene, depsgraph=None):
        if depsgraph is not None and depsgraph.mode == "RENDER" and "pts" not in found:
            found["pts"] = _read(ob.evaluated_get(depsgraph).data)

    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 1
    sc.render.resolution_x = sc.render.resolution_y = 8
    bpy.app.handlers.frame_change_post.append(grab)
    try:
        bpy.ops.render.render()
    finally:
        bpy.app.handlers.frame_change_post.remove(grab)
    if "pts" not in found:
        pytest.skip("no render depsgraph reached frame_change_post")
    return found["pts"]


def _read(me) -> dict:
    n = len(me.vertices)
    out = {"co": np.zeros(n * 3, dtype=np.float32)}
    me.vertices.foreach_get("co", out["co"])
    out["co"] = out["co"].reshape(n, 3)
    for attr in me.attributes:
        if attr.name.startswith(".") or attr.name == "position" or attr.domain != "POINT":
            continue
        if attr.data_type == "FLOAT_VECTOR":
            arr = np.zeros(n * 3, dtype=np.float32)
            attr.data.foreach_get("vector", arr)
            arr = arr.reshape(n, 3)
        elif attr.data_type in {"FLOAT", "INT", "BOOLEAN"}:
            arr = np.zeros(n, dtype={"FLOAT": np.float32, "INT": np.int32, "BOOLEAN": bool}[attr.data_type])
            attr.data.foreach_get("value", arr)
        else:
            continue
        out[attr.name] = arr
    return out


def _by_id(pts) -> dict:
    return {int(i): tuple(np.round(c, 5)) for i, c in zip(pts["id"], pts["co"])}


def _collection(name: str, *objects):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    for ob in objects:
        coll.objects.link(ob)
    return coll


def _box(name: str, size: float, location):
    bpy.ops.mesh.primitive_cube_add(size=size, location=location)
    ob = bpy.context.active_object
    ob.name = name
    bpy.context.scene.collection.objects.unlink(ob)
    return ob


# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stage, geo_in, geo_out", [
    ("masks", "Surface", "Surface"), ("distribute", "Surface", "Points"), ("cull", "Points", "Points")])
def test_stage_interface_uses_spec_names(scene, stage, geo_in, geo_out):
    tree = nodes.ensure(stage, rebuild=True)
    module = {"masks": masks, "distribute": distribute, "cull": cull}[stage]
    inputs = [i for i in tree.interface.items_tree if i.item_type == "SOCKET" and i.in_out == "INPUT"]
    outputs = [i.name for i in tree.interface.items_tree if i.item_type == "SOCKET" and i.in_out == "OUTPUT"]
    assert inputs[0].name == geo_in and outputs == [geo_out]
    assert [i.name for i in inputs[1:]] == [spec.get(k).name for k in spec.BY_KEY if k in module.INPUT_KEYS]
    assert not [n for n in tree.nodes if n.bl_idname == "NodeUndefined"]


def test_points_carry_the_attribute_contract(plane, camera):
    plane.select_set(False)
    _scatter(plane)
    pts = _points(plane)
    assert len(pts["co"]) > 1000
    for name in (spec.ATTR_ID, spec.ATTR_UP, spec.ATTR_RANDOM, spec.ATTR_CLUMP, spec.ATTR_CLUMP_CENTER,
                 spec.ATTR_WISP, spec.ATTR_LENGTH, spec.ATTR_WIND_SCALE, spec.ATTR_VARIATION,
                 spec.ATTR_DIST, spec.ATTR_LOD, spec.ATTR_WIDTH):
        assert name in pts, name
    assert spec.ATTR_MASK not in pts
    assert pts["id"].dtype == np.int32 and len(np.unique(pts["id"])) == len(pts["id"])
    assert np.allclose(np.linalg.norm(pts[spec.ATTR_UP], axis=1), 1.0, atol=1e-4)
    assert np.allclose(pts[spec.ATTR_UP], (0, 0, 1), atol=1e-4)  # flat ground
    assert 0.4 < pts[spec.ATTR_RANDOM].mean() < 0.6
    assert np.allclose(pts[spec.ATTR_LENGTH], 1.0) and np.allclose(pts[spec.ATTR_WIND_SCALE], 1.0)
    assert np.allclose(pts[spec.ATTR_VARIATION], 0.0)
    cam = np.array(camera.matrix_world.translation)
    assert np.allclose(pts[spec.ATTR_DIST], np.linalg.norm(pts["co"] - cam, axis=1), atol=1e-3)


# ---------------------------------------------------------------------------
# Distribution
# ---------------------------------------------------------------------------

def test_density_is_per_world_square_metre(plane):
    _scatter(plane)
    small = len(_points(plane)["co"])
    assert 0.85 * 100 * 100 < small <= 1.02 * 100 * 100  # 100 m² at 100 blades/m²
    plane.scale = (2.0, 2.0, 2.0)
    plane.update_tag()
    big = len(_points(plane)["co"])
    assert 3.7 < big / small < 4.3


def test_lowering_density_keeps_surviving_blades(plane):
    _scatter(plane)
    full = _by_id(_points(plane))
    _set(plane, density=40.0)
    thin = _by_id(_points(plane))
    assert 0.3 < len(thin) / len(full) < 0.5
    assert all(full.get(i) == co for i, co in thin.items())  # same id, same position


def test_density_paint_thins_without_moving_blades(plane):
    group = plane.vertex_groups.new(name="SF_Base_density")
    every = list(range(len(plane.data.vertices)))
    group.add(every, 1.0, "REPLACE")
    _scatter(plane, density_group=group.name)
    full = _by_id(_points(plane))

    group.add(every, 0.5, "REPLACE")
    plane.data.update()
    half = _by_id(_points(plane))
    assert 0.4 < len(half) / len(full) < 0.6
    assert all(full.get(i) == co for i, co in half.items())

    group.add(every, 0.0, "REPLACE")
    plane.data.update()
    assert len(_points(plane)["co"]) == 0
    _set(plane, density_invert=True)  # WP-05
    assert len(_points(plane)["co"]) == len(full)


def test_paint_threshold_and_missing_group(plane):
    group = plane.vertex_groups.new(name="SF_Base_density")
    group.add(list(range(len(plane.data.vertices))), 0.5, "REPLACE")
    _scatter(plane, density_group=group.name, density_threshold=0.6)
    assert len(_points(plane)["co"]) == 0
    _set(plane, density_threshold=0.0, density_contrast=10.0)  # 0.5 stays 0.5 around the pivot
    half = len(_points(plane)["co"])
    _set(plane, density_group="NoSuchGroup", density_invert=True)  # missing map is neutral
    assert 1.7 < len(_points(plane)["co"]) / half < 2.3


def test_length_map_and_falloff(plane):
    group = plane.vertex_groups.new(name="SF_Base_length")
    group.add(list(range(len(plane.data.vertices))), 0.25, "REPLACE")
    _scatter(plane, length_group=group.name)
    assert np.allclose(_points(plane)[spec.ATTR_LENGTH], 0.25, atol=1e-4)
    # WP-08: half density at full falloff halves the length.
    dgroup = plane.vertex_groups.new(name="SF_Base_density")
    dgroup.add(list(range(len(plane.data.vertices))), 0.5, "REPLACE")
    _set(plane, length_group="", density_group=dgroup.name, length_falloff=1.0)
    assert np.allclose(_points(plane)[spec.ATTR_LENGTH], 0.5, atol=1e-4)


def test_seed_offset_changes_layout(plane):
    _scatter(plane)
    a = _points(plane)["co"]
    _set(plane, seed_offset=7)
    b = _points(plane)["co"]
    assert abs(len(a) - len(b)) < 0.05 * len(a)
    shared = {tuple(np.round(c, 5)) for c in a} & {tuple(np.round(c, 5)) for c in b}
    assert len(shared) < 0.01 * len(a)


def test_orientation_follows_normal_blend(plane):
    plane.rotation_euler = (math.radians(30), 0.0, 0.0)
    _scatter(plane, orient_normal=0.0)
    # sf_up stays in world space; the wrapper only transforms positions back.
    assert np.allclose(_points(plane)[spec.ATTR_UP], (0, 0, 1), atol=1e-4)
    _set(plane, orient_normal=1.0)
    normal = np.array(plane.matrix_world.to_3x3() @ mathutils.Vector((0, 0, 1)))
    assert np.allclose(_points(plane)[spec.ATTR_UP], normal, atol=1e-3)
    _set(plane, orient_normal=0.5)
    half = (normal + (0, 0, 1)) / np.linalg.norm(normal + (0, 0, 1))
    assert np.allclose(_points(plane)[spec.ATTR_UP], half, atol=1e-3)


def test_clumps_and_wisps(plane):
    _scatter(plane, clump_density=4.0, clump_radius=0.3, wisp_percent=10.0)
    pts = _points(plane)
    co_world = pts["co"]  # identity transform
    offset = np.linalg.norm(pts[spec.ATTR_CLUMP_CENTER] - co_world, axis=1)
    assert offset.max() <= 0.3 + 1e-4
    assert (offset > 0).mean() > 0.5  # most blades joined a clump
    assert 0.07 < pts[spec.ATTR_WISP].mean() < 0.13
    _set(plane, clump_density=0.0)
    pts = _points(plane)
    assert np.allclose(pts[spec.ATTR_CLUMP_CENTER], pts["co"], atol=1e-5)
    assert np.allclose(pts[spec.ATTR_CLUMP], pts[spec.ATTR_RANDOM])


# ---------------------------------------------------------------------------
# Masks
# ---------------------------------------------------------------------------

def test_slope_mask_uses_world_normal(plane):
    _scatter(plane, slope_enable=True, slope_min=0.0, slope_max=math.radians(35), slope_smooth=math.radians(2))
    full = len(_points(plane)["co"])
    assert full > 1000
    plane.rotation_euler = (math.radians(60), 0.0, 0.0)
    plane.update_tag()
    assert len(_points(plane)["co"]) == 0
    _set(plane, slope_blend=spec.get("slope_blend").item_index("ADD"))
    assert len(_points(plane)["co"]) == full


def test_altitude_mask(plane):
    _scatter(plane, altitude_enable=True, altitude_min=-1.0, altitude_max=1.0, altitude_smooth=0.0)
    assert len(_points(plane)["co"]) > 1000
    plane.location.z = 5.0
    plane.update_tag()
    assert len(_points(plane)["co"]) == 0


@pytest.mark.parametrize("coverage, low, high", [(0.0, 0.0, 0.0), (0.5, 0.3, 0.7), (1.0, 1.0, 1.0)])
def test_noise_mask_coverage(plane, coverage, low, high):
    _scatter(plane)
    full = len(_points(plane)["co"])
    _set(plane, noise_enable=True, noise_coverage=coverage, noise_contrast=20.0, noise_scale=0.5)
    share = len(_points(plane)["co"]) / full
    assert low - 1e-6 <= share <= high + 1e-6


def test_image_mask_reads_uvs(plane):
    image = bpy.data.images.new("Mask", 8, 8)
    pixels = np.ones((8, 8, 4), dtype=np.float32)
    pixels[:, :4, :3] = 0.0  # left half (u < 0.5) black
    image.pixels.foreach_set(pixels.ravel())
    _scatter(plane)
    full = len(_points(plane)["co"])
    _set(plane, image_enable=True)
    assert len(_points(plane)["co"]) == full  # no image is neutral
    _set(plane, image_mask=image)
    co = _points(plane)["co"]
    assert 0.4 < len(co) / full < 0.6
    assert co[:, 0].min() > -1.0  # U runs along X; 8 px are blurred by linear filtering


def test_proximity_mask(plane):
    target = bpy.data.objects.new("Target", None)
    target.location = (3.0, 3.0, 0.0)
    coll = _collection("Near", target)
    _scatter(plane)
    full = len(_points(plane)["co"])
    _set(plane, proximity_enable=True, proximity_distance=1.5, proximity_smooth=0.0)
    assert len(_points(plane)["co"]) == full  # unset collection is neutral
    _set(plane, proximity_collection=coll)
    pts = _points(plane)["co"]
    d = np.linalg.norm(pts[:, :2] - (3.0, 3.0), axis=1)
    assert len(pts) > 0 and d.max() < 1.5 + 0.4
    _set(plane, proximity_invert=True)
    pts = _points(plane)["co"]
    assert np.linalg.norm(pts[:, :2] - (3.0, 3.0), axis=1).min() > 1.5 - 0.4
    assert len(pts) < full


def test_exclusion_removes_blades_near_objects(plane):
    box = _box("Rock", 2.0, (0.0, 0.0, 0.0))
    marker = bpy.data.objects.new("Marker", None)
    marker.location = (3.0, 3.0, 0.0)
    coll = _collection("Exclude", box, marker)
    _scatter(plane)
    full = _points(plane)
    _set(plane, exclusion_collection=coll, exclusion_distance=0.5, exclusion_falloff=1.0)
    pts = _points(plane)
    co = pts["co"]
    # Vertex masks blur by about one grid cell (0.25 m) when interpolated.
    box_dist = np.max(np.abs(co[:, :2]), axis=1) - 1.0
    assert box_dist.min() > 0.5 - 0.3
    assert np.linalg.norm(co[:, :2] - (3.0, 3.0), axis=1).min() > 0.2
    # Shorter grass across the falloff band, full length beyond it.
    length = pts[spec.ATTR_LENGTH]
    band = (box_dist > 0.6) & (box_dist < 1.2) & (np.linalg.norm(co[:, :2] - (3.0, 3.0), axis=1) > 2.0)
    assert length[band].mean() < 0.9
    far = (box_dist > 2.0) & (np.linalg.norm(co[:, :2] - (3.0, 3.0), axis=1) > 2.0)
    assert np.allclose(length[far], 1.0, atol=1e-4)
    assert len(co) < len(full["co"])


def test_camera_distance_mask(plane, camera):
    _scatter(plane, camdist_enable=True, camdist_min=0.0, camdist_max=6.0, camdist_smooth=0.0)
    co = _points(plane)["co"]
    assert len(co) > 0
    assert np.linalg.norm(co - np.array(camera.location), axis=1).max() < 6.0 + 0.4


def test_camera_masks_are_neutral_without_camera(plane):
    _scatter(plane, optimised=True, viewport_density=100.0)
    full = len(_points(plane)["co"])
    _set(plane, camdist_enable=True, camdist_max=1.0, frustum_cull=True, lod_far=1.0)
    pts = _points(plane)
    assert len(pts["co"]) == full
    assert np.all(pts[spec.ATTR_DIST] == 0.0) and np.all(pts[spec.ATTR_LOD] == 0)


# ---------------------------------------------------------------------------
# Culling
# ---------------------------------------------------------------------------

def test_viewport_density_reduces_the_distribution(plane):
    _scatter(plane)
    full = len(_points(plane)["co"])
    _set(plane, optimised=True, viewport_density=25.0)
    pts = _points(plane)
    assert 0.2 < len(pts["co"]) / full < 0.3  # thinned once, not again in Cull
    assert np.allclose(pts[spec.ATTR_WIDTH], 2.0, atol=1e-4)
    assert distribute.ATTR_SHARE not in pts
    # Simplify also applies outside Optimised Mode.
    _set(plane, optimised=False, simplify=0.5)
    pts = _points(plane)
    assert 0.45 < len(pts["co"]) / full < 0.55
    assert np.allclose(pts[spec.ATTR_WIDTH], math.sqrt(2.0), atol=1e-4)
    _set(plane, viewport_density=1.0, optimised=True, simplify=1.0)
    assert np.allclose(_points(plane)[spec.ATTR_WIDTH], 3.0)  # widening is capped


def test_reduced_viewport_layout_is_stable(plane):
    group = plane.vertex_groups.new(name="SF_Base_density")
    every = list(range(len(plane.data.vertices)))
    group.add(every, 1.0, "REPLACE")
    _scatter(plane, density_group=group.name, optimised=True, viewport_density=20.0)
    before = _by_id(_points(plane))
    _set(plane, density=50.0)
    lower = _by_id(_points(plane))
    assert 0.4 < len(lower) / len(before) < 0.6
    assert all(before.get(i) == co for i, co in lower.items())
    group.add(every[: len(every) // 2], 0.0, "REPLACE")
    plane.data.update()
    painted = _by_id(_points(plane))
    assert 0 < len(painted) < len(lower)
    assert all(before.get(i) == co for i, co in painted.items())


def test_cull_thins_points_that_were_not_reduced(plane):
    _scatter(plane, raw=True)
    full = _by_id(_points(plane))
    _set(plane, optimised=True, viewport_density=25.0)
    pts = _points(plane)
    kept = _by_id(pts)
    assert 0.2 < len(kept) / len(full) < 0.3
    assert all(full.get(i) == co for i, co in kept.items())  # a stable subset
    assert np.allclose(pts[spec.ATTR_WIDTH], 2.0, atol=1e-4)


@pytest.mark.parametrize("optimised", [False, True])
def test_no_node_warnings_by_default(plane, camera, optimised):
    mod = _scatter(plane, optimised=optimised)
    _points(plane)
    if not hasattr(mod, "node_warnings"):
        pytest.skip("modifier node warnings are not exposed in this Blender version")
    assert [w.message for w in mod.node_warnings] == []


def test_background_evaluation_counts_as_viewport(plane):
    _scatter(plane, simplify=0.5)
    _set(plane, simplify=1.0)
    full = len(_points(plane)["co"])
    _set(plane, simplify=0.5)
    assert len(_points(plane)["co"]) < 0.6 * full


def _forward_camera(location=(0.0, 0.0, 1.0)):
    """A 50 mm camera looking along +Y, set as the scene camera."""
    bpy.ops.object.camera_add(location=location, rotation=(math.radians(90), 0.0, 0.0))
    cam = bpy.context.active_object
    bpy.context.scene.camera = cam
    return cam


def test_frustum_culling_removes_points_behind_and_beside(plane):
    _forward_camera()
    _scatter(plane, optimised=True, viewport_density=100.0, frustum_cull=True, cull_margin_viewport=0.0,
             lod_enable=False)
    pts = _points(plane)
    co = pts["co"]
    assert len(co) > 500
    # Camera space: depth along +Y, x sideways. 16:9 frame, 36 mm sensor, 50 mm lens.
    tan_x = 18.0 / 50.0
    radius = cull.BLADE_RADIUS * math.sqrt(1 + tan_x ** 2)
    depth = co[:, 1]
    assert depth.min() >= -cull.BLADE_RADIUS - 1e-3
    assert np.all(np.abs(co[:, 0]) <= tan_x * depth + radius + 1e-3)
    assert np.any(np.abs(co[:, 0]) > tan_x * np.maximum(depth, 0))  # sphere allowance keeps the edge
    _set(plane, frustum_cull=False)
    assert len(_points(plane)["co"]) > 1.8 * len(co)


def test_frustum_margin_fov_override_and_ortho(plane):
    _forward_camera()
    _scatter(plane, optimised=True, viewport_density=100.0, cull_margin_viewport=0.0, lod_enable=False)
    narrow = len(_points(plane)["co"])
    _set(plane, cull_margin_viewport=100.0)
    assert len(_points(plane)["co"]) > narrow
    _set(plane, cull_margin_viewport=0.0, cull_fov_override=math.radians(120))
    assert len(_points(plane)["co"]) > narrow
    _set(plane, cull_fov_override=0.0, cam_ortho=True, cam_ortho_scale=2.0)
    co = _points(plane)["co"]
    assert len(co) > 0 and np.abs(co[:, 0]).max() <= 1.0 + cull.BLADE_RADIUS + 1e-3
    assert co[:, 1].min() >= -cull.BLADE_RADIUS - 1e-3


def test_render_culling_does_not_touch_the_viewport(plane):
    _forward_camera()
    _scatter(plane, optimised=False, render_cull=True, lod_enable=False)
    full = len(_points(plane)["co"])
    _set(plane, render_cull=False)
    assert len(_points(plane)["co"]) == full


def test_render_skips_viewport_thinning_and_uses_render_culling(plane):
    _forward_camera()
    _scatter(plane, lod_enable=False)
    full = _by_id(_points(plane))  # Optimised Mode off: no viewport culling
    _set(plane, optimised=True, viewport_density=10.0, simplify=0.5, frustum_cull=True, render_cull=False,
         cull_margin_viewport=200.0, cull_margin_render=0.0)
    assert len(_points(plane)["co"]) < 0.1 * len(full)
    pts = _render_points(plane)
    assert _by_id(pts) == full  # same blades at the same positions
    assert np.allclose(pts[spec.ATTR_WIDTH], 1.0)

    _set(plane, render_cull=True)
    co = _render_points(plane)["co"]
    assert 0 < len(co) < 0.7 * len(full)
    tan_x = 18.0 / 50.0  # render margin 0, not the 200 % viewport margin
    radius = cull.BLADE_RADIUS * math.sqrt(1 + tan_x ** 2)
    assert np.all(np.abs(co[:, 0]) <= tan_x * co[:, 1] + radius + 1e-3)


def test_lod_bands(plane, camera):
    _scatter(plane, lod_near=4.0, lod_mid=7.0, lod_far=10.0, lod_blend=0.0, lod_mid_density=1.0, lod_far_density=1.0,
             lod_mid_width=1.5, lod_far_width=2.5)
    pts = _points(plane)
    dist = pts[spec.ATTR_DIST]
    assert len(dist) > 1000 and dist.max() < 10.0
    expected = np.where(dist < 4.0, 0, np.where(dist < 7.0, 1, 2))
    assert np.array_equal(pts[spec.ATTR_LOD], expected)
    assert np.allclose(pts[spec.ATTR_WIDTH], np.choose(expected, [1.0, 1.5, 2.5]))
    by_band = np.bincount(expected, minlength=3)

    _set(plane, lod_far_density=0.1, lod_mid_density=0.5)
    pts = _points(plane)
    thinned = np.bincount(pts[spec.ATTR_LOD], minlength=3)
    assert thinned[0] == by_band[0]
    assert 0.4 < thinned[1] / by_band[1] < 0.6
    assert 0.05 < thinned[2] / by_band[2] < 0.15

    _set(plane, lod_far=0.0, lod_far_density=1.0, lod_mid_density=1.0)  # 0: no far limit
    assert _points(plane)[spec.ATTR_DIST].max() > 10.0

    _set(plane, lod_enable=False)
    pts = _points(plane)
    assert np.all(pts[spec.ATTR_LOD] == 0) and np.allclose(pts[spec.ATTR_WIDTH], 1.0)


def test_lod_blend_dithers_band_borders(plane, camera):
    _scatter(plane, lod_near=6.0, lod_mid=100.0, lod_far=0.0, lod_blend=2.0, lod_mid_density=1.0)
    pts = _points(plane)
    dist, lod = pts[spec.ATTR_DIST], pts[spec.ATTR_LOD]
    assert np.all(lod[dist < 5.0 - 1e-3] == 0) and np.all(lod[dist > 7.0 + 1e-3] == 1)
    border = (dist > 5.5) & (dist < 6.5)
    assert 0 < lod[border].mean() < 1
