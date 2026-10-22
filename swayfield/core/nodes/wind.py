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
"""

from __future__ import annotations

import math

from .. import spec
from . import builder
from .blade import read_attr, scale

NAME = "SF_Wind_v1"

INPUT_KEYS = tuple(i.key for i in spec.inputs_in_panel("Wind")) + (
    "anim_lod_enable",
    "anim_lod_start",
    "anim_lod_end",
    "effector_collection",
)

FORCE_RIGID = "Force Rigid"
#: Share of max bend a rigidly swaying blade turns by at full strength.
RIGID_FACTOR = 0.6
#: Exponent applied to the smoothstepped sf_wind, so streaks read with dark gaps.
GUST_SHAPE = 1.5
#: Frame rate assumed at frame 0 only, where Scene Time cannot tell it (loop mode).
FALLBACK_FPS = 24.0
_RIGID = spec.get("sway_mode").item_index("RIGID")


class _Time:
    """Scene time in the forms the wind needs (all single values)."""

    def __init__(self, b: builder.NodeBuilder):
        node = b.node("GeometryNodeInputSceneTime")
        seconds = builder.find_socket(node.outputs, "Seconds")
        frame = builder.find_socket(node.outputs, "Frame")
        speed, self.offset = b.inp("speed_multiplier"), b.inp("time_offset")
        freeze = b.inp("freeze")
        # Frame rate rounded to 1/1000, so it is bit-identical on every frame (loop exactness).
        known = b.compare("GREATER_THAN", b.math("ABSOLUTE", seconds), 1e-9)
        fps = b.math("DIVIDE", b.math("ROUND", b.math("MULTIPLY", b.math("DIVIDE", frame, seconds), 1000.0)), 1000.0)
        fps = b.switch("FLOAT", known, FALLBACK_FPS, fps)
        spf = b.math("DIVIDE", 1.0, fps)
        running = b.switch("FLOAT", freeze, b.math("MULTIPLY", seconds, speed), 0.0)
        #: Plain wind time in seconds.
        self.plain = b.math("ADD", running, self.offset)
        # Loop: frame position inside the loop, computed in whole frames so it is exact.
        length = b.inp("loop_frames")
        x = b.math("SUBTRACT", frame, 1.0)
        u_frames = floored_mod(b, x, length)
        #: Loop period in wind seconds.
        self.period = b.math("MULTIPLY", b.math("MULTIPLY", length, spf), speed)
        #: Position inside the loop, in wind seconds (0 at frame 1 and frame L + 1).
        self.u = b.switch("FLOAT", freeze, b.math("MULTIPLY", b.math("MULTIPLY", u_frames, spf), speed), 0.0)


def floored_mod(b, x, period):
    """``x mod period`` in [0, period); 0 for period 0. Exact for whole numbers."""
    return b.math("SUBTRACT", x, b.math("MULTIPLY", period, b.math("FLOOR", b.math("DIVIDE", x, period))))


class _Field:
    """Builds the wind field for one set of blade roots (a curve or instance context)."""

    def __init__(self, b: builder.NodeBuilder, time: _Time, root, up):
        self.b, self.time, self.root, self.up = b, time, root, up
        info = b.node("GeometryNodeObjectInfo", {"Object": b.inp("direction_object")}, transform_space="ORIGINAL")
        x_axis = b.out("FunctionNodeRotateVector", {"Vector": (1.0, 0.0, 0.0),
                                                     "Rotation": builder.find_socket(info.outputs, "Rotation")})
        ax, ay, _ = b.separate_xyz(x_axis)
        # Object Info gives zero scale when no object is set.
        has_object = b.compare("GREATER_THAN", b.vmath("LENGTH", builder.find_socket(info.outputs, "Scale")), 0.0)
        self.heading = b.switch("FLOAT", has_object, b.inp("direction"), b.math("ARCTAN2", ay, ax))
        cos0, sin0 = b.math("COSINE", self.heading), b.math("SINE", self.heading)
        rx, ry, _ = b.separate_xyz(root)
        # Wind-aligned coordinates of the root, in metres.
        self.along = b.math("ADD", b.math("MULTIPLY", rx, cos0), b.math("MULTIPLY", ry, sin0))
        self.across = b.math("SUBTRACT", b.math("MULTIPLY", ry, cos0), b.math("MULTIPLY", rx, sin0))
        self.wisp = read_attr(b, spec.ATTR_WISP, "BOOLEAN", False)
        eff = b.group(_effectors(), {"Position": root})
        self.force = builder.find_socket(eff.outputs, "Force")
        self.flatten = builder.find_socket(eff.outputs, "Flatten")
        gain = b.math("MULTIPLY", b.inp("intensity"), read_attr(b, spec.ATTR_WIND_SCALE, "FLOAT", 1.0))
        #: Intensity x shelter paint x shelter effectors.
        self.gain = b.math("MULTIPLY", gain, builder.find_socket(eff.outputs, "Shelter"))
        #: Bend amount of the steady lean alone; sf_wind measures flattening beyond it.
        self.rest = b.math("MULTIPLY", self.gain, b.inp("base_lean"), clamp=True)

    # -- time-dependent components -------------------------------------------

    def _noise(self, vector, w, detail):
        node = self.b.node("ShaderNodeTexNoise", {"Vector": vector, "W": w, "Scale": 1.0, "Detail": detail,
                                                  "Roughness": 0.5, "Distortion": 0.0}, noise_dimensions="4D")
        return node.outputs[0]

    def _when(self, key, value, off=0.0, input_type="FLOAT"):
        """``value`` while input ``key`` is above 0, else ``off``. Lazy: a disabled component costs nothing."""
        b = self.b
        return b.switch(input_type, b.compare("GREATER_THAN", b.inp(key), 0.0), off, value)

    def push(self, t):
        """Base lean + gusts + waves at wind time ``t`` (before intensity and shelter)."""
        b = self.b
        gust_scale = b.inp("gust_scale")
        scrolled = b.math("SUBTRACT", self.along, b.math("MULTIPLY", b.inp("gust_speed"), t))
        gx = b.math("DIVIDE", b.math("MULTIPLY", scrolled, gust_scale), b.inp("gust_stretch"))
        gy = b.math("MULTIPLY", self.across, gust_scale)
        noise = self._noise(b.combine_xyz(gx, gy, 0.0), b.math("MULTIPLY", t, b.inp("gust_evolution")), 2.0)
        # Noise sits mostly within 0.5 +- 0.25: double it, then apply contrast around 0.5.
        contrast = b.math("MULTIPLY", b.inp("gust_contrast"), 2.0)
        gust = b.math("ADD", b.math("MULTIPLY", b.math("SUBTRACT", noise, 0.5), contrast), 0.5, clamp=True)
        gust = self._when("gust_strength", b.math("MULTIPLY", b.inp("gust_strength"), gust))

        travelled = b.math("SUBTRACT", self.along, b.math("MULTIPLY", b.inp("wave_speed"), t))
        phase = b.math("DIVIDE", b.math("MULTIPLY", travelled, math.tau), b.inp("wave_length"))
        sine = b.math("ADD", b.math("MULTIPLY", b.math("SINE", phase), 0.5), 0.5)
        wave = b.math("POWER", sine, b.math("ADD", b.math("MULTIPLY", b.inp("wave_sharpness"), 7.0), 1.0))
        wave = self._when("wave_strength", b.math("MULTIPLY", b.inp("wave_strength"), wave))
        return [b.math("ADD", b.math("ADD", b.inp("base_lean"), gust), wave)]

    def wander(self, t):
        """[direction offset in radians] at wind time ``t``: slow noise of time, a little of position."""
        b = self.b
        noise = self._noise(scale(b, self.root, 0.02), b.math("MULTIPLY", t, b.inp("direction_variation_speed")), 1.0)
        return [b.math("MULTIPLY", b.map_range(noise, 0.5 - 1 / 3, 0.5 + 1 / 3, -1.0, 1.0),
                       b.inp("direction_variation"))]

    def flutter(self, t):
        """[x, y] of the fast flutter noise at wind time ``t``, roughly -1..1."""
        b = self.b
        w = b.math("MULTIPLY", t, b.inp("flutter_frequency"))
        p = scale(b, self.root, 1.7)
        return [b.math("MULTIPLY", b.math("SUBTRACT", self._noise(p, b.math("ADD", w, offset), 0.0), 0.5), 3.0)
                for offset in (0.0, 37.1)]

    def timed(self, fn, lag=None):
        """Evaluate ``fn(t)`` at the current wind time (minus ``lag``), looping if enabled."""
        b, time = self.b, self.time
        plain_t, u = time.plain, time.u
        if lag is not None:
            plain_t = b.math("SUBTRACT", plain_t, lag)
            u = floored_mod(b, b.math("SUBTRACT", u, lag), time.period)
        plain = fn(plain_t)
        start = fn(b.math("ADD", u, time.offset))
        end = fn(b.math("SUBTRACT", b.math("ADD", u, time.offset), time.period))
        w = b.math("DIVIDE", u, time.period)
        looped = [b.mix(w, s, e) for s, e in zip(start, end)]
        return [b.switch("FLOAT", b.inp("loop_enable"), p, lp) for p, lp in zip(plain, looped)]

    # -- outputs ----------------------------------------------------------------

    def vectors(self):
        """(wind vector at the root time, wind vector at the tip time, flutter rotation vector)."""
        b = self.b
        (offset,) = self.timed(self.wander)
        heading = b.math("ADD", self.heading, self._when("direction_variation", offset))
        direction = b.combine_xyz(b.math("COSINE", heading), b.math("SINE", heading), 0.0)

        def wind(push):
            strength = b.math("ADD", b.math("MULTIPLY", self.gain, push), self.flatten)
            return b.vmath("ADD", scale(b, direction, strength), self.force)

        (push_root,) = self.timed(self.push)
        (push_tip,) = self.timed(self.push, lag=b.inp("tip_lag"))
        wind_root = wind(push_root)
        wind_tip = self._when("tip_lag", wind(push_tip), wind_root, "VECTOR")

        fx, fy = self.timed(self.flutter)
        amount = b.math("MULTIPLY", b.math("MULTIPLY", b.inp("flutter_strength"), b.inp("max_bend")), self.gain)
        amount = b.math("MULTIPLY", amount, b.switch("FLOAT", self.wisp, 1.0, b.inp("wisp_flutter")))
        flutter = b.vmath("CROSS_PRODUCT", self.up, scale(b, b.combine_xyz(fx, fy, 0.0), amount))
        flutter = self._when("flutter_strength", flutter, (0.0, 0.0, 0.0), "VECTOR")
        return wind_root, wind_tip, flutter


def _effectors():
    from . import ensure

    return ensure("effectors")


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


def _curve_wind(b, time, curves):
    """Wind on curves: returns (bent curves, rigidly swayed curves).

    Needs ``sf_root`` and ``sf_factor`` on the points, which SF_Blade always writes.
    """
    root = read_attr(b, spec.ATTR_ROOT, "FLOAT_VECTOR")
    up = b.vmath("NORMALIZE", read_attr(b, spec.ATTR_UP, "FLOAT_VECTOR", (0.0, 0.0, 1.0)))
    far = b.map_range(read_attr(b, spec.ATTR_DIST, "FLOAT", 0.0), b.inp("anim_lod_start"),
                      b.math("MAXIMUM", b.inp("anim_lod_end"), b.math("ADD", b.inp("anim_lod_start"), 1e-3)),
                      0.0, 1.0, interpolation="SMOOTHSTEP")
    far = b.switch("FLOAT", b.inp("anim_lod_enable"), 0.0, far)
    # The field is evaluated once per blade (curve domain), not per point.
    field = _Field(b, time, root, up)
    wind_root, wind_tip, flutter = field.vectors()
    curves, per_blade = capture(b, curves, "CURVE", [
        ("VECTOR", "Wind Root", wind_root), ("VECTOR", "Wind Tip", wind_tip),
        ("VECTOR", "Flutter", flutter), ("FLOAT", "Far", far), ("FLOAT", "Rest", field.rest)])
    wind_root, wind_tip, flutter, far, rest = (per_blade[k] for k in ("Wind Root", "Wind Tip", "Flutter", "Far",
                                                                      "Rest"))
    pos = b.out("GeometryNodeInputPosition")

    # Rigid: the whole blade turns about its root.
    rotation, amount = bend_rotation(b, up, wind_root, flutter)
    rigid_pos = b.out("ShaderNodeVectorRotate", {
        "Vector": pos, "Center": root, "Axis": b.vmath("NORMALIZE", rotation),
        "Angle": b.math("MULTIPLY", b.vmath("LENGTH", rotation), RIGID_FACTOR)}, rotation_type="AXIS_ANGLE")
    rigid = b.store(curves, spec.ATTR_WIND, gust_amount(b, amount, rest))
    rigid = b.out("GeometryNodeSetPosition", {"Geometry": rigid, "Position": rigid_pos})

    # Bend: rotate each segment by the bend at its midpoint, then re-sum from the root.
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
    lag = b.math("MULTIPLY", mid, b.math("SUBTRACT", 1.0, far))
    wind = b.mix(lag, wind_root, wind_tip, data_type="VECTOR")
    rotation, amount = bend_rotation(b, up, wind, flutter)
    profile = b.mix(far, b.math("POWER", mid, b.inp("stiffness")), RIGID_FACTOR)
    segment = b.out("ShaderNodeVectorRotate", {
        "Vector": b.vmath("SUBTRACT", pos, prev_pos), "Center": (0.0, 0.0, 0.0),
        "Axis": b.vmath("NORMALIZE", rotation),
        "Angle": b.math("MULTIPLY", b.vmath("LENGTH", rotation), profile)}, rotation_type="AXIS_ANGLE")
    acc = b.node("GeometryNodeAccumulateField", {"Value": segment}, data_type="FLOAT_VECTOR", domain="POINT")
    b.link(b.out("GeometryNodeCurveOfPoint"), acc.inputs[1])
    bent_pos = b.vmath("ADD", root, builder.find_socket(acc.outputs, "Leading"))
    bent = b.store(curves, spec.ATTR_WIND, gust_amount(b, amount, rest))
    bent = b.out("GeometryNodeSetPosition", {"Geometry": bent, "Position": bent_pos})
    return bent, rigid


def _instance_wind(b, time, instances):
    """Custom instances rock rigidly about their own origin; they stay instances."""
    root = b.out("GeometryNodeInputPosition")
    up = b.vmath("NORMALIZE", read_attr(b, spec.ATTR_UP, "FLOAT_VECTOR", (0.0, 0.0, 1.0)))
    field = _Field(b, time, root, up)
    wind_root, _tip, flutter = field.vectors()
    rotation, amount = bend_rotation(b, up, wind_root, flutter)
    instances, sway = capture(b, instances, "INSTANCE", [("VECTOR", "Rotation", rotation),
                                                         ("FLOAT", "Amount", gust_amount(b, amount, field.rest))])
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
    time = _Time(b)
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
