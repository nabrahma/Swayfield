# SPDX-License-Identifier: GPL-3.0-or-later
"""SF_Main: the modifier group. Exposes every spec input and wires the stages.

The modifier lives on the layer's own hair Curves object, because Cycles and
EEVEE render curves as hair only on Curves objects. It reads the surface
through the Surface input (evaluated, so the surface's own modifiers count):

Surface -> world space -> Masks -> Distribute -> Bake -> Cull -> Blade -> Wind
-> Store -> display mode -> object space.
"""

from __future__ import annotations

from .. import spec
from . import builder, ensure

NAME = "SF_Main_v1"
BAKE_NODE = "SF_Bake"

#: How far Mask Preview lifts the surface copy, to avoid z-fighting with the surface.
_PREVIEW_LIFT = 0.002

_DISPLAY = {item[0]: i for i, item in enumerate(spec.get("display_mode").items)}


def _transform(b: builder.NodeBuilder, geometry, matrix):
    node = b.node("GeometryNodeTransform", {"Geometry": geometry})
    mode = node.inputs.get("Mode")
    if mode is not None:
        mode.default_value = "Matrix"
    elif hasattr(node, "mode"):
        node.mode = "MATRIX"
    b.set(builder.find_socket(node.inputs, "Transform"), matrix)
    return node.outputs["Geometry"]


def _bake(b: builder.NodeBuilder, geometry):
    node = b.tree.nodes.new("GeometryNodeBake")
    node.name = BAKE_NODE
    node.label = "Bake Scatter"
    if len(node.bake_items) == 0:
        node.bake_items.new("GEOMETRY", "Geometry")
    b.link(geometry, node.inputs[0])
    return node.outputs[0]


def _index_switch(b: builder.NodeBuilder, index, options: list):
    node = b.node("GeometryNodeIndexSwitch", data_type="GEOMETRY")
    while len(node.index_switch_items) < len(options):
        node.index_switch_items.new()
    b.set(node.inputs["Index"], index)
    for i, option in enumerate(options):
        b.set(node.inputs[i + 1], option)
    return node.outputs["Output"]


def _join(b: builder.NodeBuilder, *geometries):
    node = b.node("GeometryNodeJoinGeometry")
    for geometry in reversed(geometries):
        b.link(geometry, node.inputs[0])
    return node.outputs[0]


def build(tree) -> None:
    builder.add_socket(tree, "Geometry", "GEOMETRY", "INPUT")
    builder.add_spec_inputs(tree)
    builder.add_socket(tree, "Geometry", "GEOMETRY", "OUTPUT")
    tree.description = "Swayfield grass layer. Settings are in the Swayfield tab of the 3D Viewport sidebar"

    b = builder.NodeBuilder(tree)

    # Surface in this object's space; RELATIVE keeps it aligned however the objects move.
    surface_info = b.node("GeometryNodeObjectInfo", {"Object": b.inp("surface")}, transform_space="RELATIVE")
    surface = b.out("GeometryNodeSeparateComponents", {"Geometry": surface_info.outputs["Geometry"]}, output="Mesh")

    # Work in world space so densities, wind, camera and effectors use world units.
    self_info = b.node("GeometryNodeObjectInfo", {"Object": b.out("GeometryNodeSelfObject")},
                       transform_space="ORIGINAL")
    to_world = self_info.outputs["Transform"]
    to_local = b.out("FunctionNodeInvertMatrix", {"Matrix": to_world}, output="Matrix")
    world_surface = _transform(b, surface, to_world)

    # Static half: cached by the Bake node.
    masked = b.group(ensure("masks"), {"Surface": world_surface}, label="Masks").outputs["Surface"]
    points = b.group(ensure("distribute"), {"Surface": masked}, label="Distribute").outputs["Points"]
    baked = _bake(b, points)

    # Per-frame half.
    culled = b.group(ensure("cull"), {"Points": baked}, label="Cull").outputs["Points"]

    viewport_optimised = b.boolean("AND", b.out("GeometryNodeIsViewport"), b.inp("optimised"))
    lite = b.boolean("AND", viewport_optimised,
                     b.compare("EQUAL", b.inp("display_mode"), _DISPLAY["LITE"], data_type="INT"))

    blades = b.group(ensure("blade"), {"Points": culled, "Force Lite": lite}, label="Blade").outputs["Blades"]
    bent = b.group(ensure("wind"), {"Blades": blades, "Force Rigid": lite}, label="Wind").outputs["Blades"]
    grass = b.group(ensure("store"), {"Blades": bent}, label="Store").outputs["Grass"]

    # Viewport display modes (Optimised Mode only).
    dots = b.out("GeometryNodeSetPointRadius", {"Points": culled, "Radius": 0.015})
    dots = b.out("GeometryNodeSetMaterial", {"Geometry": dots, "Material": b.inp("material")})
    box = b.out("GeometryNodeBoundBox", {"Geometry": culled}, output="Bounding Box")
    box = b.out("GeometryNodeMeshToCurve", {"Mesh": box})
    shown = _index_switch(b, b.inp("display_mode"), [grass, grass, dots, box])
    shown = b.switch("GEOMETRY", viewport_optimised, grass, shown)

    # Mask Preview: a lifted copy of the surface carrying sf_mask, with the preview material.
    lift = b.vmath("SCALE", b.out("GeometryNodeInputNormal"), scale=_PREVIEW_LIFT)
    preview = b.out("GeometryNodeSetPosition", {"Geometry": masked, "Offset": lift})
    preview = b.out("GeometryNodeSetMaterial", {"Geometry": preview, "Material": b.inp("preview_material")})
    empty = b.out("GeometryNodeSeparateComponents", {"Geometry": preview}, output="Volume")
    preview = b.switch("GEOMETRY", b.inp("mask_preview"), empty, preview)

    b.output("Geometry", _transform(b, _join(b, shown, preview), to_local))
    b.arrange()
