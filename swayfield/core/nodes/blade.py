# SPDX-License-Identifier: GPL-3.0-or-later
"""SF_Blade: turns scattered points into blades.

Strands and Ribbons both leave this stage as poly curves, one per point
(SF_Store converts ribbons to mesh later). Custom Instances become instances
of the user's collection and are never realised.

Blades are built with Duplicate Elements + Points to Curves, which measured
about twice as fast as instancing per-LOD line prototypes and realising them,
and keeps every point attribute on the curve points without extra work.

The rest shape of a blade is an exact circular arc (rest lean at the root,
curl added along the length), so blade length never depends on the lean or
curl settings. Per-blade randomness hashes the stable ``id``, so it never
changes when blades are thinned.
"""

from __future__ import annotations

import math

from .. import spec
from . import builder

NAME = "SF_Blade_v1"

INPUT_KEYS = (
    "blade_source",
    "instance_collection",
    "instance_scale_min",
    "instance_scale_max",
    "length_min",
    "length_max",
    "root_width",
    "tip_taper",
    "rest_lean",
    "curl",
    "random_tilt",
    "random_rotation",
    "blade_points",
    "lod_mid_points",
    "lod_far_points",
    "clump_pull",
    "wisp_length",
    "wisp_width",
)

FORCE_LITE = "Force Lite"
#: Points per blade when ``Force Lite`` is on (Strands Lite display).
LITE_POINTS = 3

_SRC = "_sf_src"
_SWITCH_TYPES = {"FLOAT": "FLOAT", "INT": "INT", "BOOLEAN": "BOOLEAN", "FLOAT_VECTOR": "VECTOR"}
_INSTANCES = spec.get("blade_source").item_index("INSTANCES")


def read_attr(b: builder.NodeBuilder, name: str, data_type: str = "FLOAT", default=None):
    """Named attribute ``name``, or ``default`` where the geometry does not have it."""
    value, exists = b.named_attribute(name, data_type)
    if default is None:
        return value
    return b.switch(_SWITCH_TYPES[data_type], exists, default, value)


def scale(b: builder.NodeBuilder, vector, factor):
    return b.vmath("SCALE", vector, scale=factor)


def tangent_frame(b: builder.NodeBuilder, up):
    """Two unit vectors perpendicular to ``up`` (and to each other)."""
    ux = b.separate_xyz(up)[0]
    near_x = b.compare("GREATER_THAN", b.math("ABSOLUTE", ux), 0.9)
    ref = b.switch("VECTOR", near_x, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    t1 = b.vmath("NORMALIZE", b.vmath("SUBTRACT", ref, scale(b, up, b.vmath("DOT_PRODUCT", ref, up))))
    t2 = b.vmath("CROSS_PRODUCT", up, t1)
    return t1, t2


def _in_frame(b, t1, t2, angle):
    """Unit vector at ``angle`` in the plane spanned by ``t1`` and ``t2``."""
    return b.vmath("ADD", scale(b, t1, b.math("COSINE", angle)), scale(b, t2, b.math("SINE", angle)))


def _point_count(b):
    lod = read_attr(b, spec.ATTR_LOD, "INT", 0)
    mid_or_far = b.switch("INT", b.compare("GREATER_EQUAL", lod, 2, data_type="INT"),
                          b.inp("lod_mid_points"), b.inp("lod_far_points"))
    full = b.switch("INT", b.compare("GREATER_EQUAL", lod, 1, data_type="INT"), b.inp("blade_points"), mid_or_far)
    return b.switch("INT", b.inp(FORCE_LITE), full, LITE_POINTS)


def _curves(b, points):
    """Points -> one poly curve per point, shaped, with blade attributes."""
    count = _point_count(b)
    pts = b.store(points, _SRC, b.out("GeometryNodeInputIndex"), data_type="INT")
    pts = b.store(pts, spec.ATTR_ROOT, b.out("GeometryNodeInputPosition"), data_type="FLOAT_VECTOR")
    dup = b.node("GeometryNodeDuplicateElements", {"Geometry": pts, "Amount": count}, domain="POINT")
    dup_index = builder.find_socket(dup.outputs, "Duplicate Index")
    factor = b.math("DIVIDE", dup_index, b.math("SUBTRACT", count, 1.0))
    geo = b.store(builder.find_socket(dup.outputs, "Geometry"), spec.ATTR_FACTOR, factor)
    # Duplicate Elements gives copies new ids; every point of a blade keeps the blade's id.
    src = read_attr(b, _SRC, "INT")
    orig_id = b.out("GeometryNodeSampleIndex", {"Geometry": pts, "Value": b.out("GeometryNodeInputID"), "Index": src},
                    data_type="INT", domain="POINT")
    geo = b.store(geo, spec.ATTR_ID, orig_id, data_type="INT")
    geo = b.out("GeometryNodePointsToCurves", {"Points": geo, "Curve Group ID": src,
                                               "Weight": read_attr(b, spec.ATTR_FACTOR)})
    geo = b.out("GeometryNodeRemoveAttribute", {"Geometry": geo, "Name": _SRC})

    # --- shape (point domain; every point of a blade sees the same blade values)
    f = read_attr(b, spec.ATTR_FACTOR)
    root = b.out("GeometryNodeInputPosition")  # all points still sit on the root here
    id_ = read_attr(b, spec.ATTR_ID, "INT")
    up = b.vmath("NORMALIZE", read_attr(b, spec.ATTR_UP, "FLOAT_VECTOR", (0.0, 0.0, 1.0)))
    wisp = read_attr(b, spec.ATTR_WISP, "BOOLEAN", False)
    t1, t2 = tangent_frame(b, up)

    def rnd(seed: int, lo=0.0, hi=1.0):
        return b.random_float(id_, seed=seed, min_value=lo, max_value=hi)

    length = b.mix(rnd(11), b.inp("length_min"), b.inp("length_max"), clamp=False)
    length = b.math("MULTIPLY", length, read_attr(b, spec.ATTR_LENGTH, "FLOAT", 1.0))
    length = b.math("MULTIPLY", length, b.switch("FLOAT", wisp, 1.0, b.inp("wisp_length")))

    azimuth = b.math("MULTIPLY", rnd(12, 0.0, math.tau), b.inp("random_rotation"))
    lean_dir = _in_frame(b, t1, t2, azimuth)

    # Clump pull: turn the lean toward the clump centre and curl more, so tips gather.
    centre, has_centre = b.named_attribute(spec.ATTR_CLUMP_CENTER, "FLOAT_VECTOR")
    to_centre = b.vmath("SUBTRACT", centre, root)
    to_centre = b.vmath("SUBTRACT", to_centre, scale(b, up, b.vmath("DOT_PRODUCT", to_centre, up)))
    dist = b.vmath("LENGTH", to_centre)
    pull_on = b.boolean("AND", has_centre, b.compare("GREATER_THAN", dist, 1e-5))
    pull = b.switch("FLOAT", pull_on, 0.0, b.inp("clump_pull"))
    blend = b.mix(pull, lean_dir, b.vmath("NORMALIZE", to_centre), data_type="VECTOR")
    usable = b.compare("GREATER_THAN", b.vmath("LENGTH", blend), 1e-4)
    bend_dir = b.switch("VECTOR", usable, t1, b.vmath("NORMALIZE", blend))
    pull_curl = b.math("MULTIPLY", b.math("MULTIPLY", pull, 2.0),
                       b.math("ARCTAN2", dist, b.math("MAXIMUM", length, 1e-4)))

    lean = b.math("MULTIPLY", b.inp("rest_lean"), rnd(16, 0.7, 1.0))
    curl = b.math("ADD", b.math("MULTIPLY", b.inp("curl"), rnd(15, 0.7, 1.0)), pull_curl)
    curl = b.math("MAXIMUM", curl, 1e-4)

    # Circular arc: tangent angle lean + curl * f. Chord to f has length
    # 2 sin(curl f / 2) / curl and points at angle lean + curl f / 2.
    half = b.math("MULTIPLY", b.math("MULTIPLY", curl, f), 0.5)
    chord = b.math("DIVIDE", b.math("MULTIPLY", b.math("SINE", half), b.math("MULTIPLY", length, 2.0)), curl)
    angle = b.math("ADD", lean, half)
    local = b.vmath("ADD", scale(b, up, b.math("MULTIPLY", chord, b.math("COSINE", angle))),
                    scale(b, bend_dir, b.math("MULTIPLY", chord, b.math("SINE", angle))))

    tilt_axis = _in_frame(b, t1, t2, rnd(14, 0.0, math.tau))
    tilt = b.math("MULTIPLY", rnd(13), b.inp("random_tilt"))
    pos = b.out("ShaderNodeVectorRotate", {"Vector": b.vmath("ADD", root, local), "Center": root,
                                           "Axis": tilt_axis, "Angle": tilt}, rotation_type="AXIS_ANGLE")
    geo = b.out("GeometryNodeSetPosition", {"Geometry": geo, "Position": pos})

    taper = b.mix(f, 1.0, b.math("SUBTRACT", 1.0, b.inp("tip_taper")))
    radius = b.math("MULTIPLY", b.math("MULTIPLY", b.inp("root_width"), 0.5), taper)
    radius = b.math("MULTIPLY", radius, read_attr(b, spec.ATTR_WIDTH, "FLOAT", 1.0))
    radius = b.math("MULTIPLY", radius, b.switch("FLOAT", wisp, 1.0, b.inp("wisp_width")))
    return b.out("GeometryNodeSetCurveRadius", {"Curve": geo, "Radius": radius})


def _instances(b, points):
    """Points -> instances of the user's collection, aligned to sf_up. Never realised."""
    id_ = b.out("GeometryNodeInputID")
    up = b.vmath("NORMALIZE", read_attr(b, spec.ATTR_UP, "FLOAT_VECTOR", (0.0, 0.0, 1.0)))
    coll = b.node("GeometryNodeCollectionInfo", {"Collection": b.inp("instance_collection"),
                                                 "Separate Children": True, "Reset Children": True},
                  transform_space="ORIGINAL")
    pick = b.out("FunctionNodeRandomValue", {"ID": id_, "Seed": 21, "Min": 0, "Max": 1_000_000}, data_type="INT")
    try:
        align = b.out("FunctionNodeAlignRotationToVector", {"Vector": up}, axis="Z")
    except RuntimeError:  # older builds only have the Euler variant; Euler converts to rotation implicitly
        align = b.out("FunctionNodeAlignEulerToVector", {"Vector": up}, axis="Z")
    spin = b.math("MULTIPLY", b.random_float(id_, seed=12, max_value=math.tau), b.inp("random_rotation"))
    tilt = b.math("MULTIPLY", b.random_float(id_, seed=13), b.inp("random_tilt"))
    local = b.out("FunctionNodeEulerToRotation", {"Euler": b.combine_xyz(tilt, 0.0, spin)})
    rotate = b.node("FunctionNodeRotateRotation", {"Rotation": align, "Rotate By": local})
    if hasattr(rotate, "rotation_space"):
        rotate.rotation_space = "LOCAL"
    rotation = builder.first_output(rotate)
    size = b.mix(b.random_float(id_, seed=22), b.inp("instance_scale_min"), b.inp("instance_scale_max"), clamp=False)
    size = b.math("MULTIPLY", size, read_attr(b, spec.ATTR_LENGTH, "FLOAT", 1.0))
    inst = b.out("GeometryNodeInstanceOnPoints", {
        "Points": points, "Instance": coll, "Pick Instance": True, "Instance Index": pick,
        "Rotation": rotation, "Scale": b.combine_xyz(size, size, size)})
    # Point attributes already moved to the instance domain; add the root for Wind.
    return b.store(inst, spec.ATTR_ROOT, b.out("GeometryNodeInputPosition"), data_type="FLOAT_VECTOR",
                   domain="INSTANCE")


def build(tree) -> None:
    builder.add_socket(tree, "Points", "GEOMETRY", "INPUT")
    builder.add_spec_inputs(tree, INPUT_KEYS, panels=False)
    builder.add_socket(tree, FORCE_LITE, "BOOLEAN", default=False,
                       description="Build every blade with 3 points (Strands Lite display)")
    builder.add_socket(tree, "Blades", "GEOMETRY", "OUTPUT")

    b = builder.NodeBuilder(tree)
    points = b.inp("Points")
    use_instances = b.compare("EQUAL", b.inp("blade_source"), _INSTANCES, data_type="INT")
    b.output("Blades", b.switch("GEOMETRY", use_instances, _curves(b, points), _instances(b, points)))
    b.arrange()
