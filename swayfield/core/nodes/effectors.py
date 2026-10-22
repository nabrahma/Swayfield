# SPDX-License-Identifier: GPL-3.0-or-later
"""SF_Effectors: local wind forces from effector objects (a field group).

Reads the settings points written by SF_EffectorPoint through Collection Info
(world space, realised) and returns, at ``Position``:

* ``Force``: horizontal world vector added to the wind vector.
* ``Flatten``: 0..1 extra bend (Trample).
* ``Shelter``: 0..1 wind multiplier, 1 means no shelter.

Every effector in the collection is summed exactly with a Repeat zone, one
iteration per effector. The cost grows with the number of effectors (a few
dozen math operations per blade each), which stays cheap for the handful of
effectors a shot uses, and avoids the seams a nearest-effector lookup gives
where two effectors overlap. Distances are horizontal (XY): effectors act on
all grass under them regardless of height.

Only point cloud components are read, so the viewport circle that
SF_EffectorPoint draws (a mesh) and any other object in the collection are
ignored. No collection, or an empty one, gives zero force and shelter 1.
"""

from __future__ import annotations

from . import builder
from .blade import scale as scale_vec
from .effector_point import ATTR_FALLOFF, ATTR_RADIUS, ATTR_STRENGTH, ATTR_TYPE, TYPES

NAME = "SF_Effectors_v1"
INPUT_KEYS = ("effector_collection",)

#: Trample pushes harder than a blast of the same strength, so grass parts clearly.
TRAMPLE_PUSH = 1.5


def _repeat_zone(tree, items):
    """Paired Repeat Input/Output nodes with ``items`` [(socket type, name)]."""
    rin = tree.nodes.new("GeometryNodeRepeatInput")
    rout = tree.nodes.new("GeometryNodeRepeatOutput")
    rin.pair_with_output(rout)
    rout.repeat_items.clear()
    for socket_type, name in items:
        rout.repeat_items.new(socket_type, name)
    return rin, rout


def build(tree) -> None:
    pos_sock = builder.add_socket(tree, "Position", "VECTOR", "INPUT",
                                  description="Where to evaluate the effectors (world space)")
    if hasattr(pos_sock, "default_input"):
        pos_sock.default_input = "POSITION"
        pos_sock.hide_value = True
    builder.add_spec_inputs(tree, INPUT_KEYS, panels=False)
    builder.add_socket(tree, "Force", "VECTOR", "OUTPUT", description="Horizontal force added to the wind vector")
    builder.add_socket(tree, "Flatten", "FLOAT", "OUTPUT", description="Extra bend, 0 to 1")
    builder.add_socket(tree, "Shelter", "FLOAT", "OUTPUT", description="Wind multiplier, 1 means no shelter")

    b = builder.NodeBuilder(tree)
    coll = b.out("GeometryNodeCollectionInfo", {"Collection": b.inp("effector_collection"),
                                                "Separate Children": False, "Reset Children": False},
                 transform_space="ORIGINAL")
    realized = b.out("GeometryNodeRealizeInstances", {"Geometry": coll})
    effectors = builder.find_socket(b.node("GeometryNodeSeparateComponents", {"Geometry": realized}).outputs,
                                    "Point Cloud")
    count = b.out("GeometryNodeAttributeDomainSize", {"Geometry": effectors}, component="POINTCLOUD")

    rin, rout = _repeat_zone(tree, [("VECTOR", "Force"), ("FLOAT", "Flatten"), ("FLOAT", "Shelter"),
                                    ("INT", "Effector")])
    b.set(builder.find_socket(rin.inputs, "Iterations"), count)
    b.set(builder.find_socket(rin.inputs, "Force"), (0.0, 0.0, 0.0))
    b.set(builder.find_socket(rin.inputs, "Flatten"), 0.0)
    b.set(builder.find_socket(rin.inputs, "Shelter"), 1.0)
    b.set(builder.find_socket(rin.inputs, "Effector"), 0)
    index = builder.find_socket(rin.outputs, "Effector")

    def sample(value, data_type="FLOAT"):
        return b.out("GeometryNodeSampleIndex", {"Geometry": effectors, "Value": value, "Index": index},
                     data_type=data_type, domain="POINT")

    centre = sample(b.out("GeometryNodeInputPosition"), "FLOAT_VECTOR")
    kind = sample(b.named_attribute(ATTR_TYPE, "INT")[0], "INT")
    radius = sample(b.named_attribute(ATTR_RADIUS)[0])
    strength = sample(b.named_attribute(ATTR_STRENGTH)[0])
    falloff = sample(b.named_attribute(ATTR_FALLOFF)[0])

    px, py, _ = b.separate_xyz(b.vmath("SUBTRACT", b.inp("Position"), centre))
    offset = b.combine_xyz(px, py, 0.0)
    radial = b.vmath("NORMALIZE", offset)
    x = b.math("DIVIDE", b.vmath("LENGTH", offset), b.math("MAXIMUM", radius, 1e-6))
    fade_start = b.math("SUBTRACT", 1.0, b.math("MAXIMUM", falloff, 1e-3))
    weight = b.map_range(x, fade_start, 1.0, 1.0, 0.0, interpolation="SMOOTHSTEP")
    weight = b.math("MULTIPLY", weight, b.compare("LESS_THAN", x, 1.0))
    push = b.math("MULTIPLY", weight, strength)

    def is_type(name):
        return b.compare("EQUAL", kind, TYPES.index(name), data_type="INT")

    rx, ry, _ = b.separate_xyz(radial)
    tangent = b.combine_xyz(b.math("MULTIPLY", ry, -1.0), rx, 0.0)  # counter-clockwise around world Z
    outward = b.math("ADD", is_type("RADIAL_BLAST"),
                     b.math("MULTIPLY", is_type("TRAMPLE"), TRAMPLE_PUSH))
    force = b.vmath("ADD", scale_vec(b, tangent, b.math("MULTIPLY", push, is_type("VORTEX"))),
                    scale_vec(b, radial, b.math("MULTIPLY", push, outward)))
    flatten = b.math("MULTIPLY", b.math("MULTIPLY", weight, b.math("ABSOLUTE", strength)), is_type("TRAMPLE"))
    calm = b.math("MULTIPLY", b.math("MULTIPLY", weight, b.math("MINIMUM", b.math("MAXIMUM", strength, 0.0), 1.0)),
                  is_type("SHELTER"))

    b.link(b.vmath("ADD", builder.find_socket(rin.outputs, "Force"), force), builder.find_socket(rout.inputs, "Force"))
    b.link(b.math("ADD", builder.find_socket(rin.outputs, "Flatten"), flatten),
           builder.find_socket(rout.inputs, "Flatten"))
    b.link(b.math("MULTIPLY", builder.find_socket(rin.outputs, "Shelter"), b.math("SUBTRACT", 1.0, calm)),
           builder.find_socket(rout.inputs, "Shelter"))
    b.link(b.math("ADD", index, 1.0), builder.find_socket(rout.inputs, "Effector"))

    b.output("Force", builder.find_socket(rout.outputs, "Force"))
    b.output("Flatten", b.math("MINIMUM", builder.find_socket(rout.outputs, "Flatten"), 1.0, clamp=True))
    b.output("Shelter", b.math("MINIMUM", builder.find_socket(rout.outputs, "Shelter"), 1.0, clamp=True))
    b.arrange()

