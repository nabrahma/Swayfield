# SPDX-License-Identifier: GPL-3.0-or-later
"""SF_Distribute: blade roots on the masked surface.

Points are distributed once with Poisson disk at Generation Density
(``density_ceiling``) and thinned through Density Factor
``sf_mask × min(density / density_ceiling, 1)``. Blender removes Poisson
points by a hash of each point's barycentric coordinate compared against the
factor, and the Poisson minimum-distance pass runs before that, so lowering
density or painting only removes blades: the survivors keep their positions
and their ``id`` (SC-05). Distribute Points on Faces writes ``id`` itself (a
hash of the barycentric coordinate and triangle), so it is stable too.

Surface point attributes from SF_Masks (``sf_mask``, ``sf_length``,
``sf_wind_scale``, ``sf_variation``) are interpolated onto the points by the
distribute node.

Viewport thinning happens here, not in SF_Cull, because the Poisson pass
costs time per *generated* point. In the viewport (Is Viewport) Density Max is
``density_ceiling × share``, with ``share = simplify × viewport_density / 100``
(viewport density only in Optimised Mode). Optimised Mode also skips the
minimum-distance pass in the viewport: it is most of the cost, and overlapping
roots do not show at viewport densities. Within a fixed share the layout is
still stable under painting and Density. Renders always use the full set.
Reduced points carry ``ATTR_SHARE`` (the share already applied), so SF_Cull
thins only by what is left, for example when the scatter was baked at full
density.

Clumps (SC-08) are random points at Clump Density on the same surface. Each
blade takes its nearest centre within Clump Radius; blades farther away are
their own clump (centre = own position, ``sf_clump`` = ``sf_random``).
"""

from __future__ import annotations

from .. import spec
from . import builder

NAME = "SF_Distribute_v1"

INPUT_KEYS: tuple[str, ...] = (
    "seed", "seed_offset", "density", "density_ceiling", "min_distance", "orient_normal",
    "clump_density", "clump_radius", "wisp_percent", "length_falloff",
    "optimised", "viewport_density", "simplify",
)

#: Point attribute on viewport-reduced points: the share of Generation Density kept (internal).
ATTR_SHARE = "sf_viewport_share"

#: Fixed Random Value seeds, one per purpose, so the values are independent.
SEED_RANDOM = 1
SEED_WISP = 2
SEED_CLUMP = 3
#: Added to the layer seed for the clump centre distribution.
CLUMP_SEED_OFFSET = 7919


def build(tree) -> None:
    builder.add_socket(tree, "Surface", "GEOMETRY", "INPUT")
    builder.add_spec_inputs(tree, INPUT_KEYS, panels=False)
    builder.add_socket(tree, "Points", "GEOMETRY", "OUTPUT")

    b = builder.NodeBuilder(tree)
    surface = b.inp("Surface")
    # Seeds are below 2^24, so the float add is exact before the int conversion.
    seed = b.math("ADD", b.inp("seed"), b.inp("seed_offset"))

    is_viewport = b.out("GeometryNodeIsViewport")
    share = viewport_share(b, is_viewport)
    fast = b.boolean("AND", is_viewport, b.inp("optimised"))

    thin = b.math("MINIMUM", b.math("DIVIDE", b.inp("density"), b.inp("density_ceiling")), 1.0)
    dist = b.node("GeometryNodeDistributePointsOnFaces", {
        "Mesh": surface,
        "Distance Min": b.switch("FLOAT", fast, b.inp("min_distance"), 0.0),
        "Density Max": b.math("MULTIPLY", b.inp("density_ceiling"), share),
        "Density Factor": b.math("MULTIPLY", _attr_or(b, spec.ATTR_MASK, 1.0), thin),
        "Seed": seed,
    }, distribute_method="POISSON")
    points = dist.outputs["Points"]
    reduced = b.compare("LESS_THAN", share, 1.0)
    points = b.switch("GEOMETRY", reduced, points, b.store(points, ATTR_SHARE, share))

    # SC-10: growth direction between world up and the surface normal.
    up = b.mix(b.inp("orient_normal"), (0.0, 0.0, 1.0), dist.outputs["Normal"], data_type="VECTOR")
    points = b.store(points, spec.ATTR_UP, b.vmath("NORMALIZE", up), data_type="FLOAT_VECTOR")

    blade_id = b.out("GeometryNodeInputID")
    rand = b.random_float(blade_id, SEED_RANDOM)
    points = b.store(points, spec.ATTR_RANDOM, rand)

    # SC-09: a stable share of blades are wisps.
    wisp = b.compare("LESS_THAN", b.random_float(blade_id, SEED_WISP), b.math("DIVIDE", b.inp("wisp_percent"), 100.0))
    points = b.store(points, spec.ATTR_WISP, wisp, data_type="BOOLEAN")

    # WP-08: blades in thinned areas are also shorter.
    falloff = b.mix(b.inp("length_falloff"), 1.0, _attr_or(b, spec.ATTR_MASK, 1.0))
    points = b.store(points, spec.ATTR_LENGTH, b.math("MULTIPLY", _attr_or(b, spec.ATTR_LENGTH, 1.0), falloff))

    points = _clumps(b, points, surface, seed, rand)
    # sf_mask is only needed on the surface (Mask Preview).
    points = b.out("GeometryNodeRemoveAttribute", {"Geometry": points, "Name": spec.ATTR_MASK})

    b.output("Points", points)
    b.arrange()


def viewport_share(b: builder.NodeBuilder, is_viewport):
    """Share of blades shown: ``simplify × viewport_density / 100`` in the viewport, 1 at render."""
    share = b.switch("FLOAT", b.inp("optimised"), 1.0, b.math("DIVIDE", b.inp("viewport_density"), 100.0))
    share = b.math("MULTIPLY", b.inp("simplify"), share, clamp=True)
    return b.switch("FLOAT", is_viewport, 1.0, share)


def _attr_or(b: builder.NodeBuilder, name: str, default: float):
    value, exists = b.named_attribute(name)
    return b.switch("FLOAT", exists, default, value)


def _clumps(b: builder.NodeBuilder, points, surface, seed, rand):
    """Store ``sf_clump_center`` and ``sf_clump`` (SC-08)."""
    centres = b.out("GeometryNodeDistributePointsOnFaces", {
        "Mesh": surface,
        "Density": b.inp("clump_density"),
        "Seed": b.math("ADD", seed, CLUMP_SEED_OFFSET),
    }, distribute_method="RANDOM")
    count = b.out("GeometryNodeAttributeDomainSize", {"Geometry": centres}, output="Point Count",
                  component="POINTCLOUD")
    has_centres = b.compare("GREATER_THAN", count, 0, data_type="INT")

    position = b.out("GeometryNodeInputPosition")
    nearest = b.out("GeometryNodeSampleNearest", {"Geometry": centres, "Sample Position": position}, domain="POINT")
    centre = b.out("GeometryNodeSampleIndex", {"Geometry": centres, "Value": position, "Index": nearest},
                   data_type="FLOAT_VECTOR", domain="POINT")
    clump_rand = b.random_float(b.out("GeometryNodeInputID"), SEED_CLUMP)
    centre_rand = b.out("GeometryNodeSampleIndex", {"Geometry": centres, "Value": clump_rand, "Index": nearest},
                        data_type="FLOAT", domain="POINT")
    alone = b.compare("GREATER_THAN", b.vmath("DISTANCE", position, centre), b.inp("clump_radius"))
    # The outer switches are single-value, so no lookup runs without centres.
    centre = b.switch("VECTOR", has_centres, position, b.switch("VECTOR", alone, centre, position))
    clump = b.switch("FLOAT", has_centres, rand, b.switch("FLOAT", alone, centre_rand, rand))

    # One capture evaluates the nearest-centre lookup once for both attributes.
    cap = b.node("GeometryNodeCaptureAttribute", domain="POINT")
    cap.capture_items.new("VECTOR", "Center")
    cap.capture_items.new("FLOAT", "Clump")
    b.link(points, cap.inputs["Geometry"])
    b.link(centre, builder.find_socket(cap.inputs, "Center"))
    b.link(clump, builder.find_socket(cap.inputs, "Clump"))
    points = b.store(cap.outputs["Geometry"], spec.ATTR_CLUMP_CENTER, builder.find_socket(cap.outputs, "Center"),
                     data_type="FLOAT_VECTOR")
    return b.store(points, spec.ATTR_CLUMP, builder.find_socket(cap.outputs, "Clump"))
