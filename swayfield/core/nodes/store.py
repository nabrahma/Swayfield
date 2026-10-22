# SPDX-License-Identifier: GPL-3.0-or-later
"""SF_Store_v1: turn the bent blades into the final grass geometry.

``Blade Source`` picks what leaves the stage:

* 0 Strands: the curves are kept (rendered as hair strands) and get the layer material.
* 1 Ribbons: each curve becomes a flat strip with Curve to Mesh, UV map ``UVMap``
  (U across 0..1, V root 0 -> tip 1 = ``sf_factor``) and the layer material.
* 2 Custom Instances: instances pass through unrealized. With *Override Instance
  Material* on, Set Material replaces the material of the instanced geometry
  (Set Material works on instance references without realizing them).

Ribbon orientation. The profile is a line along the curve normal, scaled by the
curve radius (the radius is root width / 2 x taper, so the strip is exactly
root width wide at the root). The normal is set explicitly (Free mode) to the
blade's *width direction* ``W = normalize(lean x up)``, where ``lean`` is the
root-to-tip vector and ``up`` is ``sf_up``. ``W`` is horizontal and
perpendicular to the plane the blade bends in, so the blade bends like a real
leaf: the face normal lies in the bend plane, horizontal at the root and tilting
toward the sky where the blade bends over. Wind-flattened grass therefore faces
the light, which is what makes the bright crests read. The sign is chosen so the
face normal points up and back (away from the lean). Straight vertical blades
(no lean) use a random horizontal direction from ``sf_random``.
"""

from __future__ import annotations

import math

from .. import spec
from . import builder
from .builder import NodeBuilder, add_socket, find_socket

NAME = "SF_Store_v1"

INPUT_KEYS = ("blade_source", "material", "instance_material_override")

SOURCE_STRANDS = 0
SOURCE_RIBBONS = 1
SOURCE_INSTANCES = 2

UV_MAP = "UVMap"
_U_ATTR = ".sf_u"


def _set_free_normal_mode(node) -> None:
    """Set Curve Normal to Free mode (property in 4.x, menu socket in 5.x), Z Up as fallback."""
    if hasattr(node, "mode"):
        try:
            node.mode = "FREE"
        except TypeError:
            node.mode = "Z_UP"
        return
    sock = find_socket(node.inputs, "Mode")
    try:
        sock.default_value = "Free"
    except TypeError:
        sock.default_value = "Z Up"


def _width_direction(b: NodeBuilder):
    """Unit vector across the blade, perpendicular to the curve tangent (point field)."""
    up_attr, up_exists = b.named_attribute(spec.ATTR_UP, "FLOAT_VECTOR")
    up = b.out("GeometryNodeSwitch", {"Switch": up_exists, "False": (0.0, 0.0, 1.0), "True": up_attr},
               input_type="VECTOR")

    curve_index = find_socket(b.node("GeometryNodeCurveOfPoint").outputs, "Curve Index")
    position = b.out("GeometryNodeInputPosition")

    def end_position(sort_index: int):
        poc = b.node("GeometryNodePointsOfCurve", {"Curve Index": curve_index, "Sort Index": sort_index})
        return b.out("GeometryNodeFieldAtIndex", {"Index": find_socket(poc.outputs, "Point Index"),
                                                  "Value": position},
                     data_type="FLOAT_VECTOR", domain="POINT")

    lean = b.vmath("SUBTRACT", end_position(-1), end_position(0))
    across = b.vmath("CROSS_PRODUCT", lean, up)

    # Fallback for straight blades: a random horizontal direction per blade.
    rand, _ = b.named_attribute(spec.ATTR_RANDOM)
    angle = b.math("MULTIPLY", rand, 2.0 * math.pi)
    random_dir = b.combine_xyz(b.math("COSINE", angle), b.math("SINE", angle), 0.0)
    fallback = b.vmath("CROSS_PRODUCT", random_dir, up)
    degenerate = b.compare("LESS_THAN", b.vmath("LENGTH", across), 1e-5)
    across = b.out("GeometryNodeSwitch", {"Switch": degenerate, "False": across, "True": fallback},
                   input_type="VECTOR")

    # Make it exactly perpendicular to the tangent, as Curve to Mesh expects.
    tangent = b.out("GeometryNodeInputTangent")
    along = b.vmath("SCALE", tangent, scale=b.vmath("DOT_PRODUCT", across, tangent))
    return b.vmath("NORMALIZE", b.vmath("SUBTRACT", across, along))


def _ribbons(b: NodeBuilder, blades, material):
    normal = b.node("GeometryNodeSetCurveNormal", {"Curve": blades})
    _set_free_normal_mode(normal)
    if "Normal" in {s.name for s in normal.inputs}:
        b.set(find_socket(normal.inputs, "Normal"), _width_direction(b))

    profile = b.out("GeometryNodeCurvePrimitiveLine", {"Start": (-1.0, 0.0, 0.0), "End": (1.0, 0.0, 0.0)},
                    mode="POINTS")
    profile = b.store(profile, _U_ATTR, b.out("GeometryNodeInputIndex"))

    c2m = b.node("GeometryNodeCurveToMesh", {"Curve": find_socket(normal.outputs, "Curve"), "Profile Curve": profile})
    if "Scale" in {s.name for s in c2m.inputs}:
        # Blender 4.3+ no longer scales the profile by the radius implicitly.
        b.set(find_socket(c2m.inputs, "Scale"), b.out("GeometryNodeInputRadius"))
    mesh = find_socket(c2m.outputs, "Mesh")

    u, _ = b.named_attribute(_U_ATTR)
    v, _ = b.named_attribute(spec.ATTR_FACTOR)
    mesh = b.store(mesh, UV_MAP, b.combine_xyz(u, v, 0.0), data_type="FLOAT2", domain="CORNER")
    mesh = b.out("GeometryNodeRemoveAttribute", {"Geometry": mesh, "Name": _U_ATTR})
    mesh = b.out("GeometryNodeSetShadeSmooth", {"Geometry": mesh})
    return b.out("GeometryNodeSetMaterial", {"Geometry": mesh, "Material": material})


def build(tree) -> None:
    add_socket(tree, "Blades", "GEOMETRY")
    builder.add_spec_inputs(tree, INPUT_KEYS, panels=False)
    add_socket(tree, "Grass", "GEOMETRY", "OUTPUT")

    b = NodeBuilder(tree)
    blades = b.inp("Blades")
    material = b.inp("material")
    source = b.inp("blade_source")

    strands = b.out("GeometryNodeSetMaterial", {"Geometry": blades, "Material": material})
    ribbons = _ribbons(b, blades, material)
    overridden = b.out("GeometryNodeSetMaterial", {"Geometry": blades, "Material": material})
    instances = b.switch("GEOMETRY", b.inp("instance_material_override"), blades, overridden)

    is_ribbons = b.compare("EQUAL", source, SOURCE_RIBBONS, data_type="INT")
    is_instances = b.compare("EQUAL", source, SOURCE_INSTANCES, data_type="INT")
    result = b.switch("GEOMETRY", is_ribbons, strands, ribbons)
    result = b.switch("GEOMETRY", is_instances, result, instances)
    b.output("Grass", result)
    b.arrange()
