# SPDX-License-Identifier: GPL-3.0-or-later
"""SF_Masks: per-vertex density, length, wind and variation maps on the surface.

The surface arrives in world space. Every result is stored on the POINT domain,
so Distribute Points on Faces interpolates it onto the blades.

``sf_mask`` is a stack, evaluated in this fixed order:

1. Density paint map (1.0 when no vertex group is set or found).
2. Slope, Altitude, Noise, Image, Proximity, Camera Distance masks, each only
   when enabled, combined with the value above by its blend mode
   (0 Multiply, 1 Add, 2 Subtract, 3 Min) and clamped to 0..1.
3. Exclusion objects: 0 within Exclusion Distance.

Range masks (slope, altitude, camera distance) keep the full value inside
[min, max] and fade out over ``smooth`` *outside* the range, so a minimum of 0
never halves the value at the limit.

Noise mask: 3D Perlin noise at ``world position × noise_scale`` plus a
per-seed offset in noise space (so the seed changes the pattern at any scale).
Its output is roughly normal around 0.5; the central 90 % (0.36..0.64) is
stretched to ``u`` in 0..1, which is close to uniform. Then
``mask = clamp((u + coverage - 1) × contrast + coverage)``: coverage 0 gives 0,
coverage 1 gives 1, and about ``coverage`` of the area is kept in between.
Contrast 0 gives a uniform ``coverage`` with no pattern; higher contrast gives
crisper patch edges.

Masks are evaluated per vertex, so their resolution is the surface's vertex
density (the image mask is sampled per face corner and averaged).
"""

from __future__ import annotations

from .. import spec
from . import builder

NAME = "SF_Masks_v1"

INPUT_KEYS: tuple[str, ...] = tuple(
    i.key for i in spec.inputs_in_panel("Masks") if i.key not in {"mask_preview", "length_falloff"}
) + ("exclusion_collection", "exclusion_distance", "exclusion_falloff")

_BLEND_OPS = ("MULTIPLY", "ADD", "SUBTRACT", "MINIMUM")
#: Distance reported when a collection has nothing to measure against.
_FAR = 1.0e9
_EPS = 1.0e-6
#: Central 90 % of Blender's normalised 3D noise, measured on a 40 m grid.
_NOISE_LO, _NOISE_HI = 0.36, 0.64


def build(tree) -> None:
    builder.add_socket(tree, "Surface", "GEOMETRY", "INPUT")
    builder.add_spec_inputs(tree, INPUT_KEYS, panels=False)
    builder.add_socket(tree, "Surface", "GEOMETRY", "OUTPUT")

    b = builder.NodeBuilder(tree)
    surface = b.inp("Surface")

    # Exclusion distance feeds both sf_mask and sf_length; capture it so the
    # proximity query runs once.
    excl_dist, excl_has = collection_distance(b, b.inp("exclusion_collection"))
    cap = b.node("GeometryNodeCaptureAttribute", domain="POINT")
    cap.capture_items.new("FLOAT", "Distance")
    b.link(surface, cap.inputs["Geometry"])
    b.link(excl_dist, builder.find_socket(cap.inputs, "Distance"))
    geo = cap.outputs["Geometry"]
    d_excl = builder.find_socket(cap.outputs, "Distance")

    mask = _paint_map(b, "density", 1.0)
    mask = _blend(b, mask, _slope_mask(b), "slope")
    mask = _blend(b, mask, _altitude_mask(b), "altitude")
    mask = _blend(b, mask, _noise_mask(b), "noise")
    mask = _blend(b, mask, _image_mask(b), "image")
    mask = _blend(b, mask, _proximity_mask(b), "proximity")
    mask = _blend(b, mask, _camdist_mask(b), "camdist")

    # SC-11: removed inside the exclusion distance, shorter across the falloff band.
    inside = b.boolean("AND", excl_has, b.compare("LESS_THAN", d_excl, b.inp("exclusion_distance")))
    mask = b.switch("FLOAT", inside, mask, 0.0)
    band_end = b.math("ADD", b.inp("exclusion_distance"), b.math("MAXIMUM", b.inp("exclusion_falloff"), _EPS))
    falloff = b.map_range(d_excl, b.inp("exclusion_distance"), band_end, 0.0, 1.0, interpolation="SMOOTHSTEP")
    falloff = b.switch("FLOAT", excl_has, 1.0, falloff)

    length = b.math("MULTIPLY", _paint_map(b, "length", 1.0), falloff)
    geo = b.store(geo, spec.ATTR_MASK, mask)
    geo = b.store(geo, spec.ATTR_LENGTH, length)
    geo = b.store(geo, spec.ATTR_WIND_SCALE, _paint_map(b, "wind", 1.0))
    geo = b.store(geo, spec.ATTR_VARIATION, _paint_map(b, "variation", 0.0))

    # The vertex groups are not needed downstream; dropping them here keeps
    # Distribute from interpolating them onto every blade.
    for prefix in ("density", "length", "wind", "variation"):
        geo = b.out("GeometryNodeRemoveAttribute", {"Geometry": geo, "Name": b.inp(f"{prefix}_group")})

    b.output("Surface", geo)
    b.arrange()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _paint_map(b: builder.NodeBuilder, prefix: str, default: float):
    """Vertex group ``<prefix>_group`` with invert, contrast and threshold (WP-05).

    A missing or unset group gives ``default`` untouched, so Invert never turns
    "no map" into "no grass".
    """
    weight, exists = b.named_attribute(b.inp(f"{prefix}_group"))
    value = b.switch("FLOAT", b.inp(f"{prefix}_invert"), weight, b.math("SUBTRACT", 1.0, weight))
    value = b.math("MULTIPLY_ADD", b.math("SUBTRACT", value, 0.5), b.inp(f"{prefix}_contrast"), 0.5, clamp=True)
    below = b.compare("LESS_THAN", value, b.inp(f"{prefix}_threshold"))
    value = b.switch("FLOAT", below, value, 0.0)
    return b.switch("FLOAT", exists, default, value)


def _blend(b: builder.NodeBuilder, running, mask, prefix: str):
    """Combine ``mask`` into ``running`` with ``<prefix>_blend`` when ``<prefix>_enable`` is on."""
    node = b.node("GeometryNodeIndexSwitch", {"Index": b.inp(f"{prefix}_blend")}, data_type="FLOAT")
    while len(node.index_switch_items) < len(_BLEND_OPS):
        node.index_switch_items.new()
    for i, op in enumerate(_BLEND_OPS):
        b.link(b.math(op, running, mask, clamp=True), builder.find_socket(node.inputs, str(i)))
    # The switch is lazy on its single-value condition, so a disabled mask
    # (and any geometry it reads) is never evaluated.
    return b.switch("FLOAT", b.inp(f"{prefix}_enable"), running, node.outputs[0])


def _range(b: builder.NodeBuilder, value, lo, hi, smooth):
    """1 inside [lo, hi], smooth fade to 0 over ``smooth`` outside the range."""
    s = b.math("MAXIMUM", smooth, _EPS)
    rise = b.map_range(value, b.math("SUBTRACT", lo, s), lo, 0.0, 1.0, interpolation="SMOOTHSTEP")
    fall = b.map_range(value, hi, b.math("ADD", hi, s), 1.0, 0.0, interpolation="SMOOTHSTEP")
    return b.math("MULTIPLY", rise, fall)


def _slope_mask(b: builder.NodeBuilder):
    _, _, nz = b.separate_xyz(b.out("GeometryNodeInputNormal"))
    angle = b.math("ARCCOSINE", b.math("MINIMUM", b.math("MAXIMUM", nz, -1.0), 1.0))
    return _range(b, angle, b.inp("slope_min"), b.inp("slope_max"), b.inp("slope_smooth"))


def _altitude_mask(b: builder.NodeBuilder):
    _, _, z = b.separate_xyz(b.out("GeometryNodeInputPosition"))
    return _range(b, z, b.inp("altitude_min"), b.inp("altitude_max"), b.inp("altitude_smooth"))


def _noise_mask(b: builder.NodeBuilder):
    """See the module docstring for the coverage and contrast mapping."""
    const_id = b.node("FunctionNodeInputInt", integer=0).outputs[0]
    offset = b.node("FunctionNodeRandomValue", data_type="FLOAT_VECTOR")
    b.set(builder.find_socket(offset.inputs, "Min"), (0.0, 0.0, 0.0))
    b.set(builder.find_socket(offset.inputs, "Max"), (1000.0, 1000.0, 1000.0))
    b.link(const_id, builder.find_socket(offset.inputs, "ID"))
    b.link(b.inp("noise_seed"), builder.find_socket(offset.inputs, "Seed"))
    coords = b.vmath("MULTIPLY_ADD", b.out("GeometryNodeInputPosition"),
                     b.combine_xyz(b.inp("noise_scale"), b.inp("noise_scale"), b.inp("noise_scale")),
                     builder.first_output(offset))
    noise = b.out("ShaderNodeTexNoise", {"Vector": coords, "Scale": 1.0, "Detail": 2.0, "Roughness": 0.5},
                  output="Fac", noise_dimensions="3D")
    u = b.map_range(noise, _NOISE_LO, _NOISE_HI)
    coverage = b.inp("noise_coverage")
    shifted = b.math("SUBTRACT", b.math("ADD", u, coverage), 1.0)
    return b.math("MULTIPLY_ADD", shifted, b.inp("noise_contrast"), coverage, clamp=True)


def _image_mask(b: builder.NodeBuilder):
    """Image brightness through the UV map. No image is neutral (1)."""
    image = b.inp("image_mask")
    uv, _ = b.named_attribute(b.inp("image_uv"), "FLOAT_VECTOR")
    color = b.out("GeometryNodeImageTexture", {"Image": image, "Vector": uv}, output="Color", extension="EXTEND")
    # UVs live on face corners; sampling there and averaging to the vertex
    # avoids reading averaged (wrong) UVs across seams.
    sampled = b.node("GeometryNodeFieldOnDomain", domain="CORNER", data_type="FLOAT")
    b.link(color, sampled.inputs[0])
    has_image = b.compare("GREATER_THAN", b.out("GeometryNodeImageInfo", {"Image": image}, output="Width"), 0,
                          data_type="INT")
    return b.switch("FLOAT", has_image, 1.0, sampled.outputs[0])


def _proximity_mask(b: builder.NodeBuilder):
    """1 near the collection, fading to 0 beyond Proximity Distance. An empty collection is neutral."""
    dist, has = collection_distance(b, b.inp("proximity_collection"))
    near = b.map_range(dist, b.inp("proximity_distance"),
                       b.math("ADD", b.inp("proximity_distance"), b.math("MAXIMUM", b.inp("proximity_smooth"), _EPS)),
                       1.0, 0.0, interpolation="SMOOTHSTEP")
    value = b.switch("FLOAT", b.inp("proximity_invert"), near, b.math("SUBTRACT", 1.0, near))
    return b.switch("FLOAT", has, 1.0, value)


def _camdist_mask(b: builder.NodeBuilder):
    """Keep grass between the min and max camera distance. No active camera is neutral."""
    camera, has_camera = active_camera(b)
    dist = b.vmath("DISTANCE", b.out("GeometryNodeInputPosition"), camera.outputs["Location"])
    value = _range(b, dist, b.inp("camdist_min"), b.inp("camdist_max"), b.inp("camdist_smooth"))
    return b.switch("FLOAT", has_camera, 1.0, value)


def active_camera(b: builder.NodeBuilder):
    """Return ``(Object Info node, has_camera)`` for the scene camera, in world space.

    Object Info of no object reports an identity transform, so the camera is
    detected by instancing it and counting the instances.
    """
    camera = b.out("GeometryNodeInputActiveCamera")
    info = b.node("GeometryNodeObjectInfo", {"Object": camera, "As Instance": True}, transform_space="ORIGINAL")
    count = b.out("GeometryNodeAttributeDomainSize", {"Geometry": info.outputs["Geometry"]},
                  output="Instance Count", component="INSTANCES")
    has_camera = b.compare("GREATER_THAN", count, 0, data_type="INT")
    return info, has_camera


def collection_distance(b: builder.NodeBuilder, collection):
    """Return ``(distance field, has_targets)`` from the evaluated point to a collection.

    Mesh objects measure to their faces, and points inside a closed mesh (a
    rock sunk into the ground) are at distance 0. Inside means the nearest
    face's normal points away from the point within 60 degrees; for an open
    mesh above the ground this also covers the area below it, out to about
    1.7 × its height past its edges.

    Objects without a mesh (empties, lights, curves) measure to their origin.
    The two are told apart per object: each realised vertex carries its
    object's index, laid out along X, and an origin is dropped when a vertex
    with its index exists.
    """
    info = b.node("GeometryNodeCollectionInfo", {"Collection": collection, "Separate Children": True},
                  transform_space="ORIGINAL")
    tag = b.node("GeometryNodeCaptureAttribute", domain="INSTANCE")
    tag.capture_items.new("INT", "Index")
    b.link(info.outputs[0], tag.inputs["Geometry"])
    b.link(b.out("GeometryNodeInputIndex"), builder.find_socket(tag.inputs, "Index"))
    instances = tag.outputs["Geometry"]
    owner = builder.find_socket(tag.outputs, "Index")

    realized = b.out("GeometryNodeRealizeInstances", {"Geometry": instances})
    keys = b.out("GeometryNodeMeshToPoints", {"Mesh": realized})
    keys = b.out("GeometryNodeSetPosition", {"Geometry": keys, "Position": b.combine_xyz(owner)})
    key_count = b.out("GeometryNodeAttributeDomainSize", {"Geometry": keys}, output="Point Count",
                      component="POINTCLOUD")

    origins = b.out("GeometryNodeInstancesToPoints", {"Instances": instances})
    own_key = b.combine_xyz(b.out("GeometryNodeInputIndex"))
    key_dist = builder.find_socket(proximity(b, keys, "POINTS", own_key).outputs, "Distance")
    has_mesh = b.boolean("AND", b.compare("GREATER_THAN", key_count, 0, data_type="INT"),
                         b.compare("LESS_THAN", key_dist, 0.5))
    origins = b.out("GeometryNodeDeleteGeometry", {"Geometry": origins, "Selection": has_mesh}, domain="POINT")

    face_count = b.out("GeometryNodeAttributeDomainSize", {"Geometry": realized}, output="Face Count",
                       component="MESH")
    origin_count = b.out("GeometryNodeAttributeDomainSize", {"Geometry": origins}, output="Point Count",
                         component="POINTCLOUD")
    has_faces = b.compare("GREATER_THAN", face_count, 0, data_type="INT")
    has_origins = b.compare("GREATER_THAN", origin_count, 0, data_type="INT")

    # Geometry Proximity reports 0 for an empty target, so empty parts are
    # replaced by a far distance (the switch also skips the query).
    nearest = proximity(b, realized, "FACES")
    d_faces = builder.find_socket(nearest.outputs, "Distance")
    normal = b.node("GeometryNodeSampleNearestSurface", {"Mesh": realized}, data_type="FLOAT_VECTOR")
    b.link(b.out("GeometryNodeInputNormal"), builder.find_socket(normal.inputs, "Value"))
    away = b.vmath("NORMALIZE", b.vmath("SUBTRACT", b.out("GeometryNodeInputPosition"), nearest.outputs["Position"]))
    inside = b.compare("LESS_THAN", b.vmath("DOT_PRODUCT", away, builder.find_socket(normal.outputs, "Value")), -0.5)
    d_faces = b.switch("FLOAT", inside, d_faces, 0.0)
    d_origins = builder.find_socket(proximity(b, origins, "POINTS").outputs, "Distance")
    dist = b.math("MINIMUM", b.switch("FLOAT", has_faces, _FAR, d_faces),
                  b.switch("FLOAT", has_origins, _FAR, d_origins))
    return dist, b.boolean("OR", has_faces, has_origins)


def proximity(b: builder.NodeBuilder, target, element: str, position=None):
    """Geometry Proximity node. Socket names differ between 4.2 (Target, Source Position) and 5.x."""
    node = b.node("GeometryNodeProximity", target_element=element)
    b.link(target, node.inputs[0])
    if position is not None:
        names = {s.name for s in node.inputs}
        b.link(position, builder.find_socket(node.inputs, "Sample Position" if "Sample Position" in names
                                             else "Source Position"))
    return node
