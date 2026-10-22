# SPDX-License-Identifier: GPL-3.0-or-later
"""SF_Cull: per-frame thinning, camera frustum culling and distance LOD bands.

Every removal uses a hash of ``id``, so each one keeps a stable subset of
blades and the same blades survive from frame to frame.

* Viewport thinning (viewport only, via Is Viewport): keep
  ``random(id) < simplify × viewport_density`` (viewport density only in
  Optimised Mode). Survivors widen by ``sqrt(1 / kept share)``, at most 3×.
* Frustum culling: in the viewport with Optimised Mode and Camera Culling, at
  render with Render Culling. Needs an active camera. The frame is the lens
  frustum from the driven ``cam_*``/``res_*`` inputs (or Culling FOV Override),
  grown by the margin percentage. Blades have height and bend, so each root is
  tested as a sphere of ``BLADE_RADIUS`` metres: it is kept while the sphere
  touches the grown frustum. This also keeps roots up to that radius behind
  the camera plane. Everything farther behind the camera is removed.
* LOD bands (viewport and render, needs a camera): the camera distance is
  jittered by ``(random(id) - 0.5) × lod_blend`` so band borders dither instead
  of forming a line. Mid and far keep a random share (one hash, so the far
  subset is inside the mid subset and blades only ever drop out with
  distance), and beyond Far Distance blades are removed (0: no limit).

Outputs ``sf_dist`` (0 without a camera), ``sf_lod`` and ``sf_width``.
"""

from __future__ import annotations

from .. import spec
from . import builder
from .masks import active_camera

NAME = "SF_Cull_v1"

INPUT_KEYS: tuple[str, ...] = (
    "optimised", "viewport_density", "simplify", "frustum_cull", "render_cull",
    "cull_margin_viewport", "cull_margin_render", "cull_fov_override",
    *(i.key for i in spec.INPUTS if i.key.startswith("cam_")),
    "res_x", "res_y",
    *(i.key for i in spec.INPUTS if i.key.startswith("lod_") and not i.key.endswith("_points")),
)

#: Independent Random Value seeds (distinct from SF_Distribute's).
SEED_THIN = 11
SEED_LOD_JITTER = 12
SEED_LOD_KEEP = 13
#: Radius in metres of the sphere each root is culled as (blade height and bend).
BLADE_RADIUS = 1.0
#: Widening limit for thinned viewport blades.
MAX_WIDEN = 3.0
#: Keep hashes stay below 1, so a share of 1 keeps every blade.
_RAND_MAX = 0.9999999
_FAR = 1.0e30


def build(tree) -> None:
    builder.add_socket(tree, "Points", "GEOMETRY", "INPUT")
    builder.add_spec_inputs(tree, INPUT_KEYS, panels=False)
    builder.add_socket(tree, "Points", "GEOMETRY", "OUTPUT")

    b = builder.NodeBuilder(tree)
    is_viewport = b.out("GeometryNodeIsViewport")
    camera, has_camera = active_camera(b)
    blade_id = b.out("GeometryNodeInputID")
    position = b.out("GeometryNodeInputPosition")
    dist = b.switch("FLOAT", has_camera, 0.0, b.vmath("DISTANCE", position, camera.outputs["Location"]))

    # Viewport thinning: one hash for Simplify and Viewport Density.
    share = b.switch("FLOAT", b.inp("optimised"), 1.0, b.math("DIVIDE", b.inp("viewport_density"), 100.0))
    share = b.math("MULTIPLY", b.inp("simplify"), share, clamp=True)
    share = b.switch("FLOAT", is_viewport, 1.0, share)
    keep = b.compare("LESS_THAN", b.random_float(blade_id, SEED_THIN, max_value=_RAND_MAX), share)
    widen = b.math("MINIMUM", b.math("SQRT", b.math("DIVIDE", 1.0, b.math("MAXIMUM", share, 1.0e-6))), MAX_WIDEN)

    # LOD bands.
    lod_on = b.boolean("AND", b.inp("lod_enable"), has_camera)
    jitter = b.math("MULTIPLY", b.math("SUBTRACT", b.random_float(blade_id, SEED_LOD_JITTER), 0.5), b.inp("lod_blend"))
    banded = b.math("ADD", dist, jitter)
    past_near = b.compare("GREATER_EQUAL", banded, b.inp("lod_near"))
    past_mid = b.compare("GREATER_EQUAL", banded, b.inp("lod_mid"))
    band_share = b.switch("FLOAT", past_mid, b.switch("FLOAT", past_near, 1.0, b.inp("lod_mid_density")),
                          b.inp("lod_far_density"))
    keep_band = b.compare("LESS_THAN", b.random_float(blade_id, SEED_LOD_KEEP, max_value=_RAND_MAX), band_share)
    too_far = b.boolean("AND", b.compare("GREATER_THAN", b.inp("lod_far"), 0.0),
                        b.compare("GREATER_EQUAL", banded, b.inp("lod_far")))
    keep_lod = b.boolean("AND", keep_band, b.boolean("NOT", too_far))
    keep = b.boolean("AND", keep, b.switch("BOOLEAN", lod_on, True, keep_lod))

    # Frustum culling.
    cull_viewport = b.boolean("AND", b.inp("optimised"), b.inp("frustum_cull"))
    cull_on = b.boolean("AND", has_camera, b.switch("BOOLEAN", is_viewport, b.inp("render_cull"), cull_viewport))
    in_frustum = _in_frustum(b, camera.outputs["Transform"], is_viewport, position)
    keep = b.boolean("AND", keep, b.switch("BOOLEAN", cull_on, True, in_frustum))

    points = b.out("GeometryNodeDeleteGeometry", {"Geometry": b.inp("Points"), "Selection": b.boolean("NOT", keep)},
                   domain="POINT")

    # Attributes are written after deletion, on the survivors only.
    band = b.math("ADD", past_near, past_mid)
    band_width = b.switch("FLOAT", past_mid, b.switch("FLOAT", past_near, 1.0, b.inp("lod_mid_width")),
                          b.inp("lod_far_width"))
    points = b.store(points, spec.ATTR_DIST, dist)
    points = b.store(points, spec.ATTR_LOD, b.switch("FLOAT", lod_on, 0.0, band), data_type="INT")
    points = b.store(points, spec.ATTR_WIDTH, b.math("MULTIPLY", b.switch("FLOAT", lod_on, 1.0, band_width), widen))

    b.output("Points", points)
    b.arrange()


def _in_frustum(b: builder.NodeBuilder, cam_matrix, is_viewport, position):
    """True where a sphere of ``BLADE_RADIUS`` around the point touches the grown camera frustum.

    In camera space the camera looks down -Z. A point is inside when
    ``a_lo × d <= (x, y) <= a_hi × d``, with ``d`` the depth (1 for
    orthographic, where ``a`` holds the frame edges in metres). The sphere
    allowance is the plane distance ``R × sqrt(1 + a²)`` (``R`` when
    orthographic). The Z component of the same vector test removes points
    more than ``R`` behind the camera.
    """
    inverse = b.out("FunctionNodeInvertMatrix", {"Matrix": cam_matrix}, output="Matrix")
    local = b.out("FunctionNodeTransformPoint", {"Vector": position, "Transform": inverse})
    _, _, local_z = b.separate_xyz(local)
    ortho = b.inp("cam_ortho")

    # Frame extents from the lens, following Blender's sensor fit rules.
    aspect = b.math("DIVIDE", b.inp("res_x"), b.inp("res_y"))
    fit = b.inp("cam_sensor_fit")
    fit_horizontal = b.boolean("OR", b.compare("EQUAL", fit, 1, data_type="INT"),
                               b.boolean("AND", b.compare("EQUAL", fit, 0, data_type="INT"),
                                         b.compare("GREATER_EQUAL", b.inp("res_x"), b.inp("res_y"), data_type="INT")))
    sensor = b.switch("FLOAT", b.compare("EQUAL", fit, 2, data_type="INT"),
                      b.inp("cam_sensor_width"), b.inp("cam_sensor_height"))
    extent = b.switch("FLOAT", ortho, b.math("DIVIDE", sensor, b.inp("cam_focal_length")), b.inp("cam_ortho_scale"))
    half = b.math("MULTIPLY", extent, 0.5)
    half_x = b.switch("FLOAT", fit_horizontal, b.math("MULTIPLY", half, aspect), half)
    half_y = b.switch("FLOAT", fit_horizontal, half, b.math("DIVIDE", half, aspect))
    # Shift is measured in units of the fitted frame size.
    centre_x = b.math("MULTIPLY", b.inp("cam_shift_x"), extent)
    centre_y = b.math("MULTIPLY", b.inp("cam_shift_y"), extent)

    override = b.boolean("AND", b.compare("GREATER_THAN", b.inp("cull_fov_override"), 0.0), b.boolean("NOT", ortho))
    o_half = b.math("TANGENT", b.math("MULTIPLY", b.inp("cull_fov_override"), 0.5))
    o_extent = b.math("MULTIPLY", o_half, 2.0)
    half_x = b.switch("FLOAT", override, half_x, o_half)
    half_y = b.switch("FLOAT", override, half_y, b.math("DIVIDE", o_half, aspect))
    centre_x = b.switch("FLOAT", override, centre_x, b.math("MULTIPLY", b.inp("cam_shift_x"), o_extent))
    centre_y = b.switch("FLOAT", override, centre_y, b.math("MULTIPLY", b.inp("cam_shift_y"), o_extent))

    margin = b.switch("FLOAT", is_viewport, b.inp("cull_margin_render"), b.inp("cull_margin_viewport"))
    grow = b.math("ADD", 1.0, b.math("DIVIDE", margin, 100.0))
    half_x = b.math("MULTIPLY", half_x, grow)
    half_y = b.math("MULTIPLY", half_y, grow)

    edges = {
        "right": b.math("ADD", centre_x, half_x), "left": b.math("SUBTRACT", centre_x, half_x),
        "top": b.math("ADD", centre_y, half_y), "bottom": b.math("SUBTRACT", centre_y, half_y),
    }
    allow = {}
    for side, a in edges.items():
        slant = b.math("SQRT", b.math("MULTIPLY_ADD", a, a, 1.0))
        allow[side] = b.math("MULTIPLY", b.switch("FLOAT", ortho, slant, 1.0), BLADE_RADIUS)

    a_hi = b.combine_xyz(edges["right"], edges["top"], 0.0)
    a_lo = b.combine_xyz(edges["left"], edges["bottom"], 0.0)
    b_hi = b.combine_xyz(allow["right"], allow["top"], BLADE_RADIUS)
    b_lo = b.combine_xyz(b.math("MULTIPLY", allow["left"], -1.0), b.math("MULTIPLY", allow["bottom"], -1.0), -_FAR)

    depth = b.switch("FLOAT", ortho, b.math("MULTIPLY", local_z, -1.0), 1.0)
    u_hi = b.vmath("SUBTRACT", local, b.vmath("SCALE", a_hi, scale=depth))
    u_lo = b.vmath("SUBTRACT", local, b.vmath("SCALE", a_lo, scale=depth))
    below_hi = b.out("FunctionNodeCompare", {"A": u_hi, "B": b_hi}, operation="LESS_EQUAL", data_type="VECTOR",
                     mode="ELEMENT")
    above_lo = b.out("FunctionNodeCompare", {"A": u_lo, "B": b_lo}, operation="GREATER_EQUAL", data_type="VECTOR",
                     mode="ELEMENT")
    return b.boolean("AND", below_hi, above_lo)
