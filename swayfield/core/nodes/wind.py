# SPDX-License-Identifier: GPL-3.0-or-later
"""SF_Wind: bends blades with the layered wind field (Blades -> Blades).

Per blade (evaluated once per curve, at the root ``sf_root``):

* time ``t`` = Scene Time x Speed Multiplier + Time Offset (Freeze holds it at
  Time Offset). Loop mode works in frames: ``u = (frame - 1) mod L`` and the
  field is sampled at ``u`` and ``u - L`` and blended by ``u / L``, so frame
  L + 1 gives exactly the same numbers as frame 1.
* direction: Direction angle, or the Direction Object's X axis, wandering by
  Direction Variation.
* strength = Intensity x sf_wind_scale x Shelter x (base lean + gust + waves)
  + Flatten; wind vector = direction x strength + effector Force.
* the field is sampled twice, at ``t`` (root) and ``t - tip_lag`` (tip), and
  blended along the blade, so tips trail the root.

Per curve point the bend is a rotation by
``clamp(|wind|, 0, 1) x max_bend x factor^stiffness`` (plus flutter) about
``cross(sf_up, wind)``. Rotating every point about the root would stretch a
blade whose angle varies along its length, so each *segment* is rotated by the
angle at its midpoint and the segments are summed again from the root
(Accumulate Field). Every segment keeps its length, so blades never stretch.
Rigid sway (Toon Bob, Force Rigid, Animation LOD) rotates the whole blade
about its root instead. Custom instances rock rigidly with Rotate Instances.

``sf_wind`` is stored on the points (on the instances for Custom Instances)
for shading. It means how far a blade is flattened beyond its steady lean:
``rest = clamp(intensity x sf_wind_scale x shelter x base_lean)`` and
``x = clamp((clamp(|wind|) - rest) / max(1 - rest, 0.05))`` and
``sf_wind = smoothstep(x) ^ 1.5``. 0 is the steady lean (or no wind), 1 is fully
flattened by a gust or an effector; the shaping keeps most of the field dark so
gusts read as bright streaks with dark gaps. Point count and order never change.

The pieces live in small sub-groups (``wind_parts``) so the group builds fast.
"""

from __future__ import annotations

from .. import spec
from . import builder
from .blade import read_attr
from .wind_parts import (
    RIGID_FACTOR,
    bend_group,
    bend_rotation,
    capture,
    field_group,
    gust_amount,
    rigid_group,
    time_group,
    up_vector,
)

NAME = "SF_Wind_v1"

INPUT_KEYS = tuple(i.key for i in spec.inputs_in_panel("Wind")) + (
    "anim_lod_enable",
    "anim_lod_start",
    "anim_lod_end",
    "effector_collection",
)

FORCE_RIGID = "Force Rigid"
_RIGID = spec.get("sway_mode").item_index("RIGID")


def _time_inputs(b, time) -> dict:
    return {name: builder.find_socket(time.outputs, name) for name in ("Plain", "U", "Period")}


def _curve_wind(b, time, curves):
    """Wind on curves: (bent curves, rigidly swayed curves).

    Needs ``sf_root`` and ``sf_factor`` on the points, which SF_Blade always writes.
    """
    far = b.map_range(read_attr(b, spec.ATTR_DIST, "FLOAT", 0.0), b.inp("anim_lod_start"),
                      b.math("MAXIMUM", b.inp("anim_lod_end"), b.math("ADD", b.inp("anim_lod_start"), 1e-3)),
                      0.0, 1.0, interpolation="SMOOTHSTEP")
    far = b.switch("FLOAT", b.inp("anim_lod_enable"), 0.0, far)
    field = b.group(field_group(), {"Root": read_attr(b, spec.ATTR_ROOT, "FLOAT_VECTOR"), "Up": up_vector(b),
                                    **_time_inputs(b, time)})
    # The field is evaluated once per blade (curve domain), not per point.
    items = [("VECTOR", name, builder.find_socket(field.outputs, name)) for name in ("Wind Root", "Wind Tip",
                                                                                   "Flutter")]
    items += [("FLOAT", "Far", far), ("FLOAT", "Rest", builder.find_socket(field.outputs, "Rest"))]
    curves, per_blade = capture(b, curves, "CURVE", items)
    bent = b.group(bend_group(), {"Curves": curves, **per_blade})
    rigid = b.group(rigid_group(), {"Curves": curves, **{k: per_blade[k] for k in ("Wind Root", "Flutter", "Rest")}})
    return builder.find_socket(bent.outputs, "Curves"), builder.find_socket(rigid.outputs, "Curves")


def _instance_wind(b, time, instances):
    """Custom instances rock rigidly about their own origin; they stay instances."""
    root = b.out("GeometryNodeInputPosition")
    up = up_vector(b)
    field = b.group(field_group(), {"Root": root, "Up": up, **_time_inputs(b, time)})
    rotation, amount = bend_rotation(b, up, builder.find_socket(field.outputs, "Wind Root"),
                                     builder.find_socket(field.outputs, "Flutter"))
    amount = gust_amount(b, amount, builder.find_socket(field.outputs, "Rest"))
    instances, sway = capture(b, instances, "INSTANCE", [("VECTOR", "Rotation", rotation), ("FLOAT", "Amount", amount)])
    rotation = sway["Rotation"]
    rot = b.out("FunctionNodeAxisAngleToRotation", {
        "Axis": b.vmath("NORMALIZE", rotation),
        "Angle": b.math("MULTIPLY", b.vmath("LENGTH", rotation), RIGID_FACTOR)})
    out = b.store(instances, spec.ATTR_WIND, sway["Amount"], domain="INSTANCE")
    return b.out("GeometryNodeRotateInstances", {"Instances": out, "Rotation": rot, "Pivot Point": root,
                                                 "Local Space": False})


def build(tree) -> None:
    builder.add_socket(tree, "Blades", "GEOMETRY", "INPUT")
    builder.add_spec_inputs(tree, INPUT_KEYS, panels=False)
    builder.add_socket(tree, FORCE_RIGID, "BOOLEAN", default=False,
                       description="Sway every blade rigidly about its root (cheap viewport display)")
    builder.add_socket(tree, "Blades", "GEOMETRY", "OUTPUT")

    b = builder.NodeBuilder(tree)
    blades = b.inp("Blades")
    time = b.group(time_group())
    parts = b.node("GeometryNodeSeparateComponents", {"Geometry": blades})
    bent, rigid = _curve_wind(b, time, builder.find_socket(parts.outputs, "Curve"))
    all_rigid = b.boolean("OR", b.inp(FORCE_RIGID), b.compare("EQUAL", b.inp("sway_mode"), _RIGID, data_type="INT"))
    curves = b.switch("GEOMETRY", all_rigid, bent, rigid)
    instances = _instance_wind(b, time, builder.find_socket(parts.outputs, "Instances"))

    join = b.node("GeometryNodeJoinGeometry")
    for sock in parts.outputs:
        if sock.enabled and sock.name not in {"Curve", "Instances"}:
            b.link(sock, join.inputs[0])
    b.link(curves, join.inputs[0])
    b.link(instances, join.inputs[0])

    # Mute in Viewport: rest pose with no bend, viewport only.
    rest = b.store(blades, spec.ATTR_WIND, 0.0)
    rest = b.store(rest, spec.ATTR_WIND, 0.0, domain="INSTANCE")
    muted = b.boolean("AND", b.inp("mute_viewport"), b.out("GeometryNodeIsViewport"))
    b.output("Blades", b.switch("GEOMETRY", muted, join, rest))
    b.arrange()
