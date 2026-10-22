# SPDX-License-Identifier: GPL-3.0-or-later
"""Layer list editing, upgrade and sync between linked layers."""

from __future__ import annotations

import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty

from ..core import budget, drivers, layers, node_setup, versioning

#: Seed offset between layers on one object, so layers do not share root positions.
LAYER_SEED_STEP = 4999

_NOT_SYNCED = frozenset({"seed_offset", "material", "preview_material", *drivers.DRIVEN_KEYS})
_PAINT_GROUPS = frozenset(f"{key}_group" for key in ("density", "length", "wind", "variation"))


def _mesh_ob(operator, context):
    ob = context.active_object
    if ob is None or ob.type != "MESH":
        operator.report({"ERROR"}, "Select a mesh object first")
        return None
    return ob


def _layer_at(operator, ob, index: int):
    """The layer at ``index`` (or the active one for -1), reporting a plain message when there is none."""
    if index < 0:
        layer = layers.active_layer(ob)
    else:
        layer = ob.swayfield.layers[index] if index < len(ob.swayfield.layers) else None
    if layer is None:
        operator.report({"ERROR"}, "This object has no grass layers. Click Add Grass first")
    return layer


class SWAYFIELD_OT_layer_add(bpy.types.Operator):
    bl_idname = "swayfield.layer_add"
    bl_label = "Add Layer"
    bl_description = "Add another grass layer to the active object, for example tall wisps over base grass"
    bl_options = {"REGISTER", "UNDO"}

    layer_name: StringProperty(name="Layer Name", description="Name of the new layer", default="Grass Layer")

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        if ob is None or ob.type != "MESH":
            cls.poll_message_set("Select a mesh object first")
            return False
        return True

    def execute(self, context):
        ob = _mesh_ob(self, context)
        if ob is None:
            return {"CANCELLED"}
        offset = len(ob.swayfield.layers) * LAYER_SEED_STEP
        node_setup.create_layer(ob, self.layer_name, seed_offset=offset)
        budget.invalidate()
        return {"FINISHED"}


class SWAYFIELD_OT_layer_duplicate(bpy.types.Operator):
    bl_idname = "swayfield.layer_duplicate"
    bl_label = "Duplicate Layer"
    bl_description = "Copy the active layer with all its settings and its own material"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if layers.active_target(context) is None:
            cls.poll_message_set("Select an object with a grass layer first")
            return False
        return True

    def execute(self, context):
        ob, layer, _mod = layers.active_target(context)
        node_setup.duplicate_layer(ob, layer)
        budget.invalidate()
        return {"FINISHED"}


class SWAYFIELD_OT_layer_remove(bpy.types.Operator):
    bl_idname = "swayfield.layer_remove"
    bl_label = "Remove Layer"
    bl_description = "Delete the active layer, its modifier and its material if no other layer uses it"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty(name="Layer", description="Layer to remove, -1 for the active layer", default=-1)

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        if ob is None or ob.type != "MESH" or layers.active_layer(ob) is None:
            cls.poll_message_set("Select an object with a grass layer first")
            return False
        return True

    def execute(self, context):
        ob = _mesh_ob(self, context)
        layer = _layer_at(self, ob, self.index) if ob is not None else None
        if layer is None:
            return {"CANCELLED"}
        node_setup.remove_layer(ob, layer)
        budget.invalidate()
        return {"FINISHED"}


class SWAYFIELD_OT_layer_move(bpy.types.Operator):
    bl_idname = "swayfield.layer_move"
    bl_label = "Move Layer"
    bl_description = "Move the active layer up or down in the list and in the modifier stack"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(name="Direction", description="Where to move the layer",
                            items=(("UP", "Up", "Move the layer up"), ("DOWN", "Down", "Move the layer down")),
                            default="UP")

    @classmethod
    def poll(cls, context):
        if layers.active_target(context) is None:
            cls.poll_message_set("Select an object with a grass layer first")
            return False
        return True

    def execute(self, context):
        ob, layer, mod = layers.active_target(context)
        settings = ob.swayfield
        index = layers.layer_index(ob, layer)
        other_index = index + (-1 if self.direction == "UP" else 1)
        if not 0 <= other_index < len(settings.layers):
            self.report({"INFO"}, "The layer is already at the " + ("top" if self.direction == "UP" else "bottom"))
            return {"CANCELLED"}
        other_mod = layers.get_modifier(ob, settings.layers[other_index])
        if other_mod is not None:
            node_setup.move_modifier(ob, mod, list(ob.modifiers).index(other_mod))
        settings.layers.move(index, other_index)
        settings.active_layer_index = other_index
        return {"FINISHED"}


class SWAYFIELD_OT_layer_solo(bpy.types.Operator):
    bl_idname = "swayfield.layer_solo"
    bl_label = "Solo Layer"
    bl_description = "Show only this layer in the viewport. Click again to show all layers"
    bl_options = {"REGISTER", "UNDO"}

    index: IntProperty(name="Layer", description="Layer to solo, -1 for the active layer", default=-1)

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        if ob is None or ob.type != "MESH" or layers.active_layer(ob) is None:
            cls.poll_message_set("Select an object with a grass layer first")
            return False
        return True

    def execute(self, context):
        ob = _mesh_ob(self, context)
        layer = _layer_at(self, ob, self.index) if ob is not None else None
        if layer is None:
            return {"CANCELLED"}
        was_solo = layer.solo
        # Undo any earlier solo first, so the viewport state before soloing comes back.
        for other in layers.iter_layers(ob):
            mod = layers.get_modifier(ob, other)
            if other.hidden_by_solo and mod is not None:
                mod.show_viewport = True
            other.hidden_by_solo = False
            other.solo = False
        if not was_solo:
            layer.solo = True
            for other in layers.iter_layers(ob):
                mod = layers.get_modifier(ob, other)
                if other.as_pointer() != layer.as_pointer() and mod is not None and mod.show_viewport:
                    mod.show_viewport = False
                    other.hidden_by_solo = True
        budget.invalidate()
        return {"FINISHED"}


class SWAYFIELD_OT_upgrade_layer(bpy.types.Operator):
    bl_idname = "swayfield.upgrade_layer"
    bl_label = "Upgrade Layer"
    bl_description = "Move the active layer to the newest Swayfield node group, keeping all its settings"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        target = layers.active_target(context)
        if target is None:
            cls.poll_message_set("Select an object with a grass layer first")
            return False
        if not versioning.needs_upgrade(target[2]):
            cls.poll_message_set("This layer is already up to date")
            return False
        return True

    def execute(self, context):
        ob, layer, _mod = layers.active_target(context)
        try:
            versioning.upgrade_layer(ob, layer)
        except (ValueError, KeyError) as err:
            self.report({"ERROR"}, f"Could not upgrade this layer: {err}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Upgraded {layer.name} to {versioning.CURRENT_MAIN}")
        return {"FINISHED"}


def _copy_material_controls(src_mat, dst_mat) -> None:
    try:
        from ..core import materials
    except ImportError:
        return
    if src_mat is None or dst_mat is None or src_mat == dst_mat:
        return
    for key in getattr(materials, "CONTROLS", {}):
        try:
            materials.set_control(dst_mat, key, materials.get_control(src_mat, key))
        except (KeyError, TypeError, AttributeError):
            continue


class SWAYFIELD_OT_sync_linked(bpy.types.Operator):
    bl_idname = "swayfield.sync_linked"
    bl_label = "Sync Linked Layers"
    bl_description = "Copy this layer's settings to the layers on other objects that were added together"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        target = layers.active_target(context)
        if target is None or not target[1].link_id:
            cls.poll_message_set("This layer is not linked to layers on other objects")
            return False
        return True

    def execute(self, context):
        ob, layer, mod = layers.active_target(context)
        synced = 0
        for other_ob in bpy.data.objects:
            if other_ob.type != "MESH":
                continue
            for other in layers.iter_layers(other_ob):
                other_mod = layers.get_modifier(other_ob, other)
                if other.link_id != layer.link_id or other_mod is None or other_mod == mod:
                    continue
                node_setup.copy_inputs(mod, other_mod, _NOT_SYNCED | _PAINT_GROUPS)
                _copy_material_controls(layers.layer_material(ob, layer), layers.layer_material(other_ob, other))
                other.preset, other.wind_preset, other.preset_hash = layer.preset, layer.wind_preset, layer.preset_hash
                synced += 1
        if not synced:
            self.report({"INFO"}, "No other layers are linked to this one")
            return {"CANCELLED"}
        budget.invalidate()
        self.report({"INFO"}, f"Synced {synced} linked layer" + ("s" if synced != 1 else ""))
        return {"FINISHED"}


classes = (
    SWAYFIELD_OT_layer_add,
    SWAYFIELD_OT_layer_duplicate,
    SWAYFIELD_OT_layer_remove,
    SWAYFIELD_OT_layer_move,
    SWAYFIELD_OT_layer_solo,
    SWAYFIELD_OT_upgrade_layer,
    SWAYFIELD_OT_sync_linked,
)
