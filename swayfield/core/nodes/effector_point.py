# SPDX-License-Identifier: GPL-3.0-or-later
"""SF_EffectorPoint: the modifier group on an effector object.

An effector is a single-vertex mesh object. This group replaces its geometry
with one point at the object origin that carries the effector settings as
point attributes, read by SF_Effectors through Collection Info. Because the
settings are modifier inputs they can be keyframed (a Radial Blast pulse).

In the viewport it also outputs a wire circle of the radius so the effector
can be seen and grabbed. The circle is a *mesh* component and the settings
point is a *point cloud* component; SF_Effectors reads only point clouds, so
the circle never reaches the wind. The settings point has radius 0, so it does
not render.
"""

from __future__ import annotations

from . import builder

NAME = "SF_EffectorPoint_v1"
INPUT_KEYS: tuple[str, ...] = ()

TYPES = ("VORTEX", "RADIAL_BLAST", "TRAMPLE", "SHELTER")
ATTR_TYPE = "sf_type"
ATTR_RADIUS = "sf_radius"
ATTR_STRENGTH = "sf_strength"
ATTR_FALLOFF = "sf_falloff"

CIRCLE_VERTICES = 48


def _input(tree, name, socket_type, **kwargs):
    sock = builder.add_socket(tree, name, socket_type, **kwargs)
    if hasattr(sock, "force_non_field"):
        sock.force_non_field = True
    return sock


def build(tree) -> None:
    builder.add_socket(tree, "Geometry", "GEOMETRY", "INPUT")
    _input(tree, "Type", "INT", default=0, min_value=0, max_value=len(TYPES) - 1,
           description="0 Vortex (swirl around the object), 1 Radial Blast (push outward), "
                       "2 Trample (push away and flatten), 3 Shelter (calm the wind)")
    _input(tree, "Radius", "FLOAT", default=3.0, min_value=0.0, max_value=1_000.0, subtype="DISTANCE",
           description="Reach of the effector. Scales with the object's largest scale")
    _input(tree, "Strength", "FLOAT", default=1.0, min_value=-5.0, max_value=5.0,
           description="Force of the effector. Negative values reverse it (clockwise vortex, pull inward). "
                       "Keyframe it for a one-off pulse")
    _input(tree, "Falloff", "FLOAT", default=0.5, min_value=0.0, max_value=1.0, subtype="FACTOR",
           description="Share of the radius over which the effect fades out. 0 gives a hard edge")
    builder.add_socket(tree, "Geometry", "GEOMETRY", "OUTPUT")

    b = builder.NodeBuilder(tree)
    info = b.node("GeometryNodeObjectInfo", {"Object": b.out("GeometryNodeSelfObject")},
                  transform_space="ORIGINAL")
    sx, sy, sz = b.separate_xyz(builder.find_socket(info.outputs, "Scale"))
    largest = b.math("MAXIMUM", b.math("ABSOLUTE", sx), b.math("MAXIMUM", b.math("ABSOLUTE", sy),
                                                                 b.math("ABSOLUTE", sz)))
    point = b.out("GeometryNodePoints", {"Count": 1, "Position": (0.0, 0.0, 0.0), "Radius": 0.0})
    point = b.store(point, ATTR_TYPE, b.inp("Type"), data_type="INT")
    point = b.store(point, ATTR_RADIUS, b.math("MULTIPLY", b.inp("Radius"), largest))
    point = b.store(point, ATTR_STRENGTH, b.inp("Strength"))
    point = b.store(point, ATTR_FALLOFF, b.inp("Falloff"))

    circle = b.out("GeometryNodeMeshCircle", {"Vertices": CIRCLE_VERTICES, "Radius": b.inp("Radius")},
                   fill_type="NONE")
    circle = b.switch("GEOMETRY", b.out("GeometryNodeIsViewport"), None, circle)
    join = b.node("GeometryNodeJoinGeometry")
    b.link(point, join.inputs[0])
    b.link(circle, join.inputs[0])
    b.output("Geometry", join)
    b.arrange()

