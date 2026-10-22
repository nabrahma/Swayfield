# SPDX-License-Identifier: GPL-3.0-or-later
"""Internal sub-groups of SF_Wind_v1 (``SF_Wind_<Part>_v1``).

Editing a node tree from Python costs time proportional to the size of that
tree, so building one 700-node tree is quadratic and took seconds. The wind is
split into small groups, each built once and instanced where it is needed (the
gust field is sampled up to six times). Group nodes are inlined when Geometry
Nodes evaluates them, so this changes build time only, not evaluation.

Like released stage groups, a part that already exists in the file is reused,
never rebuilt (its sockets would get new identifiers).
"""

from __future__ import annotations

import math

from .. import spec
from . import builder
from .blade import read_attr, scale

#: Share of max bend a rigidly swaying blade turns by at full strength.
RIGID_FACTOR = 0.6
#: Exponent applied to the smoothstepped sf_wind, so streaks read with dark gaps.
GUST_SHAPE = 1.5
#: Frame rate assumed at frame 0 only, where Scene Time cannot tell it (loop mode).
FALLBACK_FPS = 24.0

PUSH_KEYS = ("base_lean", "gust_strength", "gust_scale", "gust_stretch", "gust_speed", "gust_evolution",
             "gust_contrast", "wave_strength", "wave_length", "wave_speed", "wave_sharpness")
WANDER_KEYS = ("direction_variation", "direction_variation_speed")
FLUTTER_KEYS = ("flutter_frequency",)
TIME_KEYS = ("speed_multiplier", "time_offset", "freeze", "loop_frames")
LOOP_KEYS = ("loop_enable", "time_offset")
FIELD_KEYS = tuple(dict.fromkeys(
    PUSH_KEYS + WANDER_KEYS + FLUTTER_KEYS + LOOP_KEYS
    + ("intensity", "direction", "direction_object", "flutter_strength", "wisp_flutter", "max_bend", "tip_lag",
       "effector_collection")))
BEND_KEYS = ("max_bend", "stiffness")


def part(name: str, build_fn):
    """The sub-group ``name``, built with ``build_fn(tree)`` only if it is missing or empty."""
    tree = builder.ensure_group(name)
    if len(tree.nodes) == 0:
        build_fn(tree)
        tree["sf_part"] = True  # marks internal sub-groups, like "sf_stage" marks stages
    return tree


def _float_inputs(tree, *names: str, socket_type: str = "FLOAT") -> None:
    for name in names:
        builder.add_socket(tree, name, socket_type, "INPUT")


# ---------------------------------------------------------------------------
# Shared node helpers
# ---------------------------------------------------------------------------

def floored_mod(b, x, period):
    """``x mod period`` in [0, period); 0 for period 0. Exact for whole numbers."""
    return b.math("SUBTRACT", x, b.math("MULTIPLY", period, b.math("FLOOR", b.math("DIVIDE", x, period))))


def when(b, key, value, off=0.0, input_type="FLOAT"):
    """``value`` while input ``key`` is above 0, else ``off``. Lazy: a disabled component costs nothing."""
    return b.switch(input_type, b.compare("GREATER_THAN", b.inp(key), 0.0), off, value)


def noise4d(b, vector, w, detail):
    node = b.node("ShaderNodeTexNoise", {"Vector": vector, "W": w, "Scale": 1.0, "Detail": detail,
                                         "Roughness": 0.5, "Distortion": 0.0}, noise_dimensions="4D")
    return node.outputs[0]


def bend_rotation(b, up, wind, flutter):
    """(rotation vector of the full bend, bend amount 0..1) for a wind vector."""
    amount = b.math("MINIMUM", b.vmath("LENGTH", wind), 1.0, clamp=True)
    axis = b.vmath("NORMALIZE", b.vmath("CROSS_PRODUCT", up, wind))
    return b.vmath("ADD", scale(b, axis, b.math("MULTIPLY", amount, b.inp("max_bend"))), flutter), amount


def gust_amount(b, amount, rest):
    """``sf_wind``: bend amount beyond the steady lean ``rest``, remapped to 0..1."""
    span = b.math("MAXIMUM", b.math("SUBTRACT", 1.0, rest), 0.05)
    beyond = b.math("DIVIDE", b.math("SUBTRACT", amount, rest), span, clamp=True)
    # Smoothstep, then ^1.5: most of the field stays dark and gust crests stay bright.
    return b.math("POWER", b.map_range(beyond, interpolation="SMOOTHSTEP"), GUST_SHAPE)


def capture(b, geometry, domain: str, items):
    """Capture several fields on ``domain`` in one evaluation, so shared parts are computed once.

    ``items`` is [(socket type, name, value)]; returns (geometry, {name: field}).
    """
    node = b.node("GeometryNodeCaptureAttribute", domain=domain)
    node.capture_items.clear()
    for socket_type, name, _value in items:
        node.capture_items.new(socket_type, name)
    b.set(builder.find_socket(node.inputs, "Geometry"), geometry)
    for _type, name, value in items:
        b.set(builder.find_socket(node.inputs, name), value)
    fields = {name: builder.find_socket(node.outputs, name) for _type, name, _value in items}
    return builder.find_socket(node.outputs, "Geometry"), fields


def up_vector(b):
    return b.vmath("NORMALIZE", read_attr(b, spec.ATTR_UP, "FLOAT_VECTOR", (0.0, 0.0, 1.0)))


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------

def _build_time(tree) -> None:
    builder.add_spec_inputs(tree, TIME_KEYS, panels=False)
    for name in ("Plain", "U", "Period"):
        builder.add_socket(tree, name, "FLOAT", "OUTPUT")
    b = builder.NodeBuilder(tree)
    node = b.node("GeometryNodeInputSceneTime")
    seconds = builder.find_socket(node.outputs, "Seconds")
    frame = builder.find_socket(node.outputs, "Frame")
    speed, freeze = b.inp("speed_multiplier"), b.inp("freeze")
    # Frame rate rounded to 1/1000, so it is bit-identical on every frame (loop exactness).
    known = b.compare("GREATER_THAN", b.math("ABSOLUTE", seconds), 1e-9)
    fps = b.math("DIVIDE", b.math("ROUND", b.math("MULTIPLY", b.math("DIVIDE", frame, seconds), 1000.0)), 1000.0)
    spf = b.math("DIVIDE", 1.0, b.switch("FLOAT", known, FALLBACK_FPS, fps))
    running = b.switch("FLOAT", freeze, b.math("MULTIPLY", seconds, speed), 0.0)
    b.output("Plain", b.math("ADD", running, b.inp("time_offset")))
    # Loop: frame position inside the loop, computed in whole frames so it is exact.
    length = b.inp("loop_frames")
    u_frames = floored_mod(b, b.math("SUBTRACT", frame, 1.0), length)
    b.output("Period", b.math("MULTIPLY", b.math("MULTIPLY", length, spf), speed))
    b.output("U", b.switch("FLOAT", freeze, b.math("MULTIPLY", b.math("MULTIPLY", u_frames, spf), speed), 0.0))
    b.arrange()


def time_group():
    """Plain wind time, loop position U (0 at frame 1 and frame L + 1) and loop period, in wind seconds."""
    return part("SF_Wind_Time_v1", _build_time)


# ---------------------------------------------------------------------------
# Time-dependent components (functions of a single Time input)
# ---------------------------------------------------------------------------

def _build_push(tree) -> None:
    _float_inputs(tree, "Along", "Across", "Time")
    builder.add_spec_inputs(tree, PUSH_KEYS, panels=False)
    builder.add_socket(tree, "Push", "FLOAT", "OUTPUT")
    b = builder.NodeBuilder(tree)
    t, along = b.inp("Time"), b.inp("Along")
    gust_scale = b.inp("gust_scale")
    scrolled = b.math("SUBTRACT", along, b.math("MULTIPLY", b.inp("gust_speed"), t))
    gx = b.math("DIVIDE", b.math("MULTIPLY", scrolled, gust_scale), b.inp("gust_stretch"))
    gy = b.math("MULTIPLY", b.inp("Across"), gust_scale)
    noise = noise4d(b, b.combine_xyz(gx, gy, 0.0), b.math("MULTIPLY", t, b.inp("gust_evolution")), 2.0)
    # Noise sits mostly within 0.5 +- 0.25: double it, then apply contrast around 0.5.
    contrast = b.math("MULTIPLY", b.inp("gust_contrast"), 2.0)
    gust = b.math("ADD", b.math("MULTIPLY", b.math("SUBTRACT", noise, 0.5), contrast), 0.5, clamp=True)
    gust = when(b, "gust_strength", b.math("MULTIPLY", b.inp("gust_strength"), gust))

    travelled = b.math("SUBTRACT", along, b.math("MULTIPLY", b.inp("wave_speed"), t))
    phase = b.math("DIVIDE", b.math("MULTIPLY", travelled, math.tau), b.inp("wave_length"))
    sine = b.math("ADD", b.math("MULTIPLY", b.math("SINE", phase), 0.5), 0.5)
    wave = b.math("POWER", sine, b.math("ADD", b.math("MULTIPLY", b.inp("wave_sharpness"), 7.0), 1.0))
    wave = when(b, "wave_strength", b.math("MULTIPLY", b.inp("wave_strength"), wave))
    b.output("Push", b.math("ADD", b.math("ADD", b.inp("base_lean"), gust), wave))
    b.arrange()


def _build_wander(tree) -> None:
    _float_inputs(tree, "Root", socket_type="VECTOR")
    _float_inputs(tree, "Time")
    builder.add_spec_inputs(tree, WANDER_KEYS, panels=False)
    builder.add_socket(tree, "Offset", "FLOAT", "OUTPUT")
    b = builder.NodeBuilder(tree)
    # Slow noise of time, a little of position.
    noise = noise4d(b, scale(b, b.inp("Root"), 0.02),
                    b.math("MULTIPLY", b.inp("Time"), b.inp("direction_variation_speed")), 1.0)
    b.output("Offset", b.math("MULTIPLY", b.map_range(noise, 0.5 - 1 / 3, 0.5 + 1 / 3, -1.0, 1.0),
                              b.inp("direction_variation")))
    b.arrange()


def _build_flutter(tree) -> None:
    _float_inputs(tree, "Root", socket_type="VECTOR")
    _float_inputs(tree, "Time")
    builder.add_spec_inputs(tree, FLUTTER_KEYS, panels=False)
    builder.add_socket(tree, "X", "FLOAT", "OUTPUT")
    builder.add_socket(tree, "Y", "FLOAT", "OUTPUT")
    b = builder.NodeBuilder(tree)
    w = b.math("MULTIPLY", b.inp("Time"), b.inp("flutter_frequency"))
    p = scale(b, b.inp("Root"), 1.7)
    for name, offset in (("X", 0.0), ("Y", 37.1)):
        noise = noise4d(b, p, b.math("ADD", w, offset), 0.0)
        b.output(name, b.math("MULTIPLY", b.math("SUBTRACT", noise, 0.5), 3.0))  # roughly -1..1
    b.arrange()


#: name -> (builder, field inputs [(name, type)], spec keys, outputs)
_COMPONENTS = {
    "Push": (_build_push, [("Along", "FLOAT"), ("Across", "FLOAT")], PUSH_KEYS, ["Push"]),
    "Wander": (_build_wander, [("Root", "VECTOR")], WANDER_KEYS, ["Offset"]),
    "Flutter": (_build_flutter, [("Root", "VECTOR")], FLUTTER_KEYS, ["X", "Y"]),
}


def _build_timed(tree, component: str) -> None:
    """Sample a component at wind time minus ``Lag``; in loop mode at u and u - L, blended by u / L."""
    build_fn, fields, keys, outputs = _COMPONENTS[component]
    inner = part(f"SF_Wind_{component}_v1", build_fn)
    for name, socket_type in fields:
        builder.add_socket(tree, name, socket_type, "INPUT")
    _float_inputs(tree, "Plain", "U", "Period", "Lag")
    builder.add_spec_inputs(tree, tuple(keys) + LOOP_KEYS, panels=False)
    for name in outputs:
        builder.add_socket(tree, name, "FLOAT", "OUTPUT")
    b = builder.NodeBuilder(tree)
    period, offset = b.inp("Period"), b.inp("time_offset")
    plain_t = b.math("SUBTRACT", b.inp("Plain"), b.inp("Lag"))
    u = floored_mod(b, b.math("SUBTRACT", b.inp("U"), b.inp("Lag")), period)
    start_t = b.math("ADD", u, offset)
    samples = [b.group(inner, {"Time": t}) for t in (plain_t, start_t, b.math("SUBTRACT", start_t, period))]
    w = b.math("DIVIDE", u, period)
    for name in outputs:
        plain, start, end = (builder.find_socket(s.outputs, name) for s in samples)
        b.output(name, b.switch("FLOAT", b.inp("loop_enable"), plain, b.mix(w, start, end)))
    b.arrange()


def timed_group(component: str):
    return part(f"SF_Wind_Timed{component}_v1", lambda tree: _build_timed(tree, component))


# ---------------------------------------------------------------------------
# Wind field per blade root
# ---------------------------------------------------------------------------

def _effectors():
    from . import ensure

    return ensure("effectors")


def _build_field(tree) -> None:
    _float_inputs(tree, "Root", "Up", socket_type="VECTOR")
    _float_inputs(tree, "Plain", "U", "Period")
    builder.add_spec_inputs(tree, FIELD_KEYS, panels=False)
    for name in ("Wind Root", "Wind Tip", "Flutter"):
        builder.add_socket(tree, name, "VECTOR", "OUTPUT")
    builder.add_socket(tree, "Rest", "FLOAT", "OUTPUT")
    b = builder.NodeBuilder(tree)
    root, up = b.inp("Root"), b.inp("Up")

    info = b.node("GeometryNodeObjectInfo", {"Object": b.inp("direction_object")}, transform_space="ORIGINAL")
    x_axis = b.out("FunctionNodeRotateVector", {"Vector": (1.0, 0.0, 0.0),
                                                 "Rotation": builder.find_socket(info.outputs, "Rotation")})
    ax, ay, _ = b.separate_xyz(x_axis)
    # Object Info gives zero scale when no object is set.
    has_object = b.compare("GREATER_THAN", b.vmath("LENGTH", builder.find_socket(info.outputs, "Scale")), 0.0)
    heading = b.switch("FLOAT", has_object, b.inp("direction"), b.math("ARCTAN2", ay, ax))
    cos0, sin0 = b.math("COSINE", heading), b.math("SINE", heading)
    rx, ry, _ = b.separate_xyz(root)
    # Wind-aligned coordinates of the root, in metres.
    along = b.math("ADD", b.math("MULTIPLY", rx, cos0), b.math("MULTIPLY", ry, sin0))
    across = b.math("SUBTRACT", b.math("MULTIPLY", ry, cos0), b.math("MULTIPLY", rx, sin0))

    eff = b.group(_effectors(), {"Position": root})
    force = builder.find_socket(eff.outputs, "Force")
    flatten = builder.find_socket(eff.outputs, "Flatten")
    gain = b.math("MULTIPLY", b.inp("intensity"), read_attr(b, spec.ATTR_WIND_SCALE, "FLOAT", 1.0))
    gain = b.math("MULTIPLY", gain, builder.find_socket(eff.outputs, "Shelter"))  # x shelter effectors
    # Bend amount of the steady lean alone; sf_wind measures flattening beyond it.
    b.output("Rest", b.math("MULTIPLY", gain, b.inp("base_lean"), clamp=True))

    wander = b.group(timed_group("Wander"), {"Lag": 0.0})
    offset = when(b, "direction_variation", builder.find_socket(wander.outputs, "Offset"))
    heading = b.math("ADD", heading, offset)
    direction = b.combine_xyz(b.math("COSINE", heading), b.math("SINE", heading), 0.0)

    def wind(lag):
        push = b.group(timed_group("Push"), {"Along": along, "Across": across, "Lag": lag})
        strength = b.math("ADD", b.math("MULTIPLY", gain, builder.find_socket(push.outputs, "Push")), flatten)
        return b.vmath("ADD", scale(b, direction, strength), force)

    wind_root = wind(0.0)
    b.output("Wind Root", wind_root)
    b.output("Wind Tip", when(b, "tip_lag", wind(b.inp("tip_lag")), wind_root, "VECTOR"))

    flutter = b.group(timed_group("Flutter"), {"Lag": 0.0})
    fx, fy = (builder.find_socket(flutter.outputs, n) for n in ("X", "Y"))
    wisp = read_attr(b, spec.ATTR_WISP, "BOOLEAN", False)
    amount = b.math("MULTIPLY", b.math("MULTIPLY", b.inp("flutter_strength"), b.inp("max_bend")), gain)
    amount = b.math("MULTIPLY", amount, b.switch("FLOAT", wisp, 1.0, b.inp("wisp_flutter")))
    rotation = b.vmath("CROSS_PRODUCT", up, scale(b, b.combine_xyz(fx, fy, 0.0), amount))
    b.output("Flutter", when(b, "flutter_strength", rotation, (0.0, 0.0, 0.0), "VECTOR"))
    b.arrange()


def field_group():
    """Per blade root: wind vector at the root time and the tip time, flutter rotation and steady-lean bend."""
    return part("SF_Wind_Field_v1", _build_field)


# ---------------------------------------------------------------------------
# Applying the wind to curves
# ---------------------------------------------------------------------------

def _curve_interface(tree, fields) -> None:
    builder.add_socket(tree, "Curves", "GEOMETRY", "INPUT")
    for name, socket_type in fields:
        builder.add_socket(tree, name, socket_type, "INPUT")
    builder.add_spec_inputs(tree, BEND_KEYS, panels=False)
    builder.add_socket(tree, "Curves", "GEOMETRY", "OUTPUT")


def _build_rigid(tree) -> None:
    _curve_interface(tree, [("Wind Root", "VECTOR"), ("Flutter", "VECTOR"), ("Rest", "FLOAT")])
    b = builder.NodeBuilder(tree)
    root = read_attr(b, spec.ATTR_ROOT, "FLOAT_VECTOR")
    rotation, amount = bend_rotation(b, up_vector(b), b.inp("Wind Root"), b.inp("Flutter"))
    pos = b.out("ShaderNodeVectorRotate", {
        "Vector": b.out("GeometryNodeInputPosition"), "Center": root, "Axis": b.vmath("NORMALIZE", rotation),
        "Angle": b.math("MULTIPLY", b.vmath("LENGTH", rotation), RIGID_FACTOR)}, rotation_type="AXIS_ANGLE")
    curves = b.store(b.inp("Curves"), spec.ATTR_WIND, gust_amount(b, amount, b.inp("Rest")))
    b.output("Curves", b.out("GeometryNodeSetPosition", {"Geometry": curves, "Position": pos}))
    b.arrange()


def rigid_group():
    """The whole blade turns about its root."""
    return part("SF_Wind_Rigid_v1", _build_rigid)


def _build_bend(tree) -> None:
    _curve_interface(tree, [("Wind Root", "VECTOR"), ("Wind Tip", "VECTOR"), ("Flutter", "VECTOR"),
                            ("Far", "FLOAT"), ("Rest", "FLOAT")])
    b = builder.NodeBuilder(tree)
    root = read_attr(b, spec.ATTR_ROOT, "FLOAT_VECTOR")
    pos = b.out("GeometryNodeInputPosition")
    factor = read_attr(b, spec.ATTR_FACTOR)
    prev = b.node("GeometryNodeOffsetPointInCurve", {"Offset": -1})
    has_prev = builder.find_socket(prev.outputs, "Is Valid Offset")
    prev_index = builder.find_socket(prev.outputs, "Point Index")

    def at_prev(value, data_type):
        return b.out("GeometryNodeFieldAtIndex", {"Value": value, "Index": prev_index},
                     data_type=data_type, domain="POINT")

    prev_pos = b.switch("VECTOR", has_prev, root, at_prev(pos, "FLOAT_VECTOR"))
    prev_factor = b.switch("FLOAT", has_prev, 0.0, at_prev(factor, "FLOAT"))
    mid = b.math("MULTIPLY", b.math("ADD", factor, prev_factor), 0.5)
    far = b.inp("Far")
    lag = b.math("MULTIPLY", mid, b.math("SUBTRACT", 1.0, far))
    wind = b.mix(lag, b.inp("Wind Root"), b.inp("Wind Tip"), data_type="VECTOR")
    rotation, amount = bend_rotation(b, up_vector(b), wind, b.inp("Flutter"))
    profile = b.mix(far, b.math("POWER", mid, b.inp("stiffness")), RIGID_FACTOR)
    segment = b.out("ShaderNodeVectorRotate", {
        "Vector": b.vmath("SUBTRACT", pos, prev_pos), "Center": (0.0, 0.0, 0.0),
        "Axis": b.vmath("NORMALIZE", rotation),
        "Angle": b.math("MULTIPLY", b.vmath("LENGTH", rotation), profile)}, rotation_type="AXIS_ANGLE")
    acc = b.node("GeometryNodeAccumulateField", {"Value": segment}, data_type="FLOAT_VECTOR", domain="POINT")
    b.link(b.out("GeometryNodeCurveOfPoint"), acc.inputs[1])
    bent_pos = b.vmath("ADD", root, builder.find_socket(acc.outputs, "Leading"))
    curves = b.store(b.inp("Curves"), spec.ATTR_WIND, gust_amount(b, amount, b.inp("Rest")))
    b.output("Curves", b.out("GeometryNodeSetPosition", {"Geometry": curves, "Position": bent_pos}))
    b.arrange()


def bend_group():
    """Rotate each segment by the bend at its midpoint, then re-sum the segments from the root."""
    return part("SF_Wind_Bend_v1", _build_bend)
