# SPDX-License-Identifier: GPL-3.0-or-later
"""Weight painting workflow: paint, done, and subdividing a surface that is too coarse (WP-01 to WP-04)."""

from __future__ import annotations

import math
import re

import bpy
from bpy.props import EnumProperty

from ..core import budget, compat, layers, spec

#: map id -> (label, weight a new group is filled with). Variation starts at 0 so there is no tint.
MAPS = {
    "DENSITY": ("Density", 1.0),
    "LENGTH": ("Length", 1.0),
    "WIND": ("Wind", 1.0),
    "VARIATION": ("Variation", 0.0),
}
DISPLAY_POINTS = 2
#: Edge length the surface is subdivided to, matching the "too coarse" note.
TARGET_EDGE = layers.MAX_EDGE_LENGTH
MAX_CUTS = 99
MAX_VERTICES = 2_000_000


def group_name(layer_name: str, map_id: str) -> str:
    """``SF_<layer>_<map>`` with the layer name reduced to letters, digits and underscores."""
    clean = re.sub(r"[^A-Za-z0-9]+", "_", layer_name).strip("_") or "Layer"
    return f"SF_{clean}_{map_id.lower()}"


def ensure_group(ob: bpy.types.Object, name: str, weight: float) -> bpy.types.VertexGroup:
    """The vertex group ``name``, created and filled with ``weight`` when missing."""
    group = ob.vertex_groups.get(name)
    if group is None:
        group = ob.vertex_groups.new(name=name)
        group.add(list(range(len(ob.data.vertices))), weight, "REPLACE")
    return group


def _soften_brush(context: bpy.types.Context) -> None:
    """Use a soft falloff on the weight paint brush, where the Blender version exposes it."""
    brush = getattr(context.tool_settings.weight_paint, "brush", None)
    if brush is None:
        return
    for attr in ("curve_distance_falloff_preset", "curve_preset"):
        if hasattr(brush, attr):
            try:
                setattr(brush, attr, "SMOOTH")
            except (TypeError, AttributeError):
                continue
            break


def _go_object_mode(context: bpy.types.Context) -> None:
    if context.mode != "OBJECT" and context.object is not None:
        bpy.ops.object.mode_set(mode="OBJECT")


class SWAYFIELD_OT_paint(bpy.types.Operator):
    bl_idname = "swayfield.paint"
    bl_label = "Paint"
    bl_description = "Create a vertex group for this map and start weight painting. White keeps grass, black removes it"
    bl_options = {"REGISTER", "UNDO"}

    map: EnumProperty(name="Map", description="What the painted weights control",
                      items=(("DENSITY", "Density", "Where blades grow"),
                             ("LENGTH", "Length", "How long blades are"),
                             ("WIND", "Wind", "How strongly wind moves the grass, for shelter behind walls"),
                             ("VARIATION", "Variation", "Where the second colour tint shows")),
                      default="DENSITY")

    @classmethod
    def poll(cls, context):
        if layers.active_target(context) is None:
            cls.poll_message_set("Select an object with a grass layer first")
            return False
        return True

    def execute(self, context):
        ob, layer, mod = layers.active_target(context)
        label, fill = MAPS[self.map]
        key = f"{self.map.lower()}_group"
        if not compat.has_input(mod, spec.BY_KEY[key].name):
            self.report({"ERROR"}, "This layer cannot be painted. Upgrade the layer first")
            return {"CANCELLED"}

        _go_object_mode(context)
        group = ensure_group(ob, group_name(layer.name, self.map), fill)
        compat.set_input(mod, key, group.name)
        ob.vertex_groups.active_index = group.index

        # In Optimised Mode show points while painting, for speed.
        if compat.get_input(mod, "optimised") and layer.paint_restore_display < 0:
            layer.paint_restore_display = int(compat.get_input(mod, "display_mode"))
            compat.set_input(mod, "display_mode", DISPLAY_POINTS)

        context.view_layer.objects.active = ob
        ob.select_set(True)
        try:
            bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
        except RuntimeError:
            self.report({"WARNING"}, "Could not enter Weight Paint mode here. The vertex group is ready, "
                                     "switch to Weight Paint mode yourself")
        else:
            _soften_brush(context)
        budget.invalidate()
        if layers.surface_too_coarse(ob):
            self.report({"INFO"}, f"{label} paint: this surface has few vertices, so strokes will look blocky. "
                                  "Use Subdivide Surface for cleaner painting")
        return {"FINISHED"}


class SWAYFIELD_OT_paint_done(bpy.types.Operator):
    bl_idname = "swayfield.paint_done"
    bl_label = "Done"
    bl_description = "Leave Weight Paint mode and return to Object mode"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if layers.target_mesh(context) is None:
            cls.poll_message_set("Select a mesh object first")
            return False
        return True

    def execute(self, context):
        ob = layers.target_mesh(context)
        _go_object_mode(context)
        for layer in layers.iter_layers(ob):
            if layer.paint_restore_display < 0:
                continue
            mod = layers.get_modifier(ob, layer)
            if mod is not None:
                compat.set_input(mod, "display_mode", layer.paint_restore_display)
            layer.paint_restore_display = -1
        budget.invalidate()
        return {"FINISHED"}


def cuts_for(ob: bpy.types.Object) -> int:
    """Subdivision cuts that bring the average edge close to ``TARGET_EDGE``, kept within sane limits."""
    edge = layers.mean_edge_length(ob)
    if edge <= TARGET_EDGE:
        return 0
    cuts = min(math.ceil(edge / TARGET_EDGE) - 1, MAX_CUTS)
    verts = len(ob.data.vertices)
    while cuts > 0 and verts * (cuts + 1) ** 2 > MAX_VERTICES:
        cuts -= 1
    return cuts


class SWAYFIELD_OT_subdivide_surface(bpy.types.Operator):
    bl_idname = "swayfield.subdivide_surface"
    bl_label = "Subdivide Surface"
    bl_description = ("Add vertices to the surface mesh so painting is smooth, about one vertex per 25 cm. "
                      "This changes the mesh itself")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if layers.target_mesh(context) is None:
            cls.poll_message_set("Select a mesh object first")
            return False
        if context.mode != "OBJECT":
            cls.poll_message_set("Go back to Object mode first")
            return False
        return True

    def invoke(self, context, event):
        message = "This adds vertices to the mesh itself. You can undo it. Continue?"
        if hasattr(context.window_manager, "invoke_confirm"):
            return context.window_manager.invoke_confirm(self, event, message=message)
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        import bmesh

        ob = layers.target_mesh(context)
        cuts = cuts_for(ob)
        if cuts < 1:
            if layers.mean_edge_length(ob) <= TARGET_EDGE:
                self.report({"INFO"}, "This surface already has enough vertices for painting")
            else:
                self.report({"ERROR"}, "This mesh is too large to subdivide further. Subdivide a smaller area")
            return {"CANCELLED"}
        bm = bmesh.new()
        try:
            bm.from_mesh(ob.data)
            bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
            bm.to_mesh(ob.data)
        finally:
            bm.free()
        ob.data.update()
        layers.clear_caches()
        budget.invalidate()
        self.report({"INFO"}, f"Subdivided the surface to {len(ob.data.vertices):,} vertices")
        return {"FINISHED"}


classes = (SWAYFIELD_OT_paint, SWAYFIELD_OT_paint_done, SWAYFIELD_OT_subdivide_surface)
