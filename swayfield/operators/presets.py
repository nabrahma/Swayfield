# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators for grass presets, wind presets and user presets."""

from __future__ import annotations

import json

import bpy
from bpy.props import EnumProperty, StringProperty

# Blender keeps only a pointer to dynamic enum items, so the lists must stay alive.
_grass_items: list = []
_wind_items: list = []
_kind_items = [("GRASS", "Grass", "Save the whole grass look"), ("WIND", "Wind", "Save only the wind type")]


def _items(entries: list[dict], cache: list) -> list:
    cache.clear()
    for i, e in enumerate(entries):
        cache.append((e["id"], e["name"], e["description"], "NONE", i))
    if not cache:
        cache.append(("NONE", "No presets", "", "NONE", 0))
    return cache


def grass_items(self, context):
    """Dynamic items: all grass presets."""
    from ..core import presets

    return _items(presets.list_grass_presets(), _grass_items)


def wind_items(self, context):
    """Dynamic items: all wind presets."""
    from ..core import presets

    return _items(presets.list_wind_presets(), _wind_items)


def _target(operator, context):
    """Return (object, layer, modifier, material) for the active layer, or report why not."""
    from ..core import layers

    ob = layers.surface_of(context.active_object)
    if ob is None:
        operator.report({"ERROR"}, "Select a mesh object with Swayfield grass first")
        return None
    layer = layers.active_layer(ob)
    mod = layers.get_modifier(ob, layer) if layer is not None else None
    if layer is None or mod is None:
        operator.report({"ERROR"}, "Add grass to this object first, then choose a preset")
        return None
    return ob, layer, mod, layers.layer_material(ob, layer)


def _has_effector(mod, effector: str) -> bool:
    """True when the layer's effector collection holds an effector of this type."""
    from ..core import compat

    try:
        coll = compat.get_input(mod, "effector_collection")
    except KeyError:
        coll = None
    if coll is None:
        return False
    wanted = effector.replace("_", "").lower()
    for ob in coll.all_objects:
        kind = str(ob.get("sf_effector_type", ob.name)).replace("_", "").replace(" ", "").lower()
        if wanted in kind:
            return True
    return False


class SWAYFIELD_OT_apply_preset(bpy.types.Operator):
    bl_idname = "swayfield.apply_preset"
    bl_label = "Apply Grass Preset"
    bl_description = "Replace the active layer's look with a grass preset (blade shape, wind and material)"
    bl_options = {"REGISTER", "UNDO"}

    preset_id: EnumProperty(name="Preset", items=grass_items, description="Grass preset to apply")

    def execute(self, context):
        from ..core import presets

        target = _target(self, context)
        if target is None:
            return {"CANCELLED"}
        _ob, layer, mod, mat = target
        try:
            data = presets.apply_grass_preset(mod, mat, self.preset_id)
        except KeyError:
            self.report({"ERROR"}, "That preset no longer exists. Pick another one")
            return {"CANCELLED"}
        layer.preset = self.preset_id
        layer.wind_preset = data.get("wind") or "CUSTOM"
        layer.preset_hash = presets.snapshot_hash(mod)
        return {"FINISHED"}


class SWAYFIELD_OT_apply_wind_preset(bpy.types.Operator):
    bl_idname = "swayfield.apply_wind_preset"
    bl_label = "Apply Wind Type"
    bl_description = "Set the active layer's wind to this animation type. Your direction and loop settings stay"
    bl_options = {"REGISTER", "UNDO"}

    wind_id: EnumProperty(name="Wind", items=wind_items, description="Wind type to apply")

    def execute(self, context):
        from ..core import presets

        target = _target(self, context)
        if target is None:
            return {"CANCELLED"}
        _ob, layer, mod, mat = target
        try:
            data = presets.apply_wind_preset(mod, mat, self.wind_id)
        except KeyError:
            self.report({"ERROR"}, "That wind type no longer exists. Pick another one")
            return {"CANCELLED"}
        layer.wind_preset = self.wind_id
        effector = data.get("effector")
        if effector and not _has_effector(mod, effector):
            label = effector.replace("_", " ").title()
            self.report({"INFO"}, f"Add a {label} effector from the Effectors panel")
        return {"FINISHED"}


class SWAYFIELD_OT_save_preset(bpy.types.Operator):
    bl_idname = "swayfield.save_preset"
    bl_label = "Save Preset"
    bl_description = "Save the active layer's current look as your own preset"
    bl_options = {"REGISTER", "UNDO"}

    name: StringProperty(name="Name", description="Name shown in the preset list")
    kind: EnumProperty(name="Save", items=_kind_items, default="GRASS",
                       description="Save the whole grass look, or only the wind type")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        from ..core import presets

        if not self.name.strip():
            self.report({"ERROR"}, "Enter a name for the preset")
            return {"CANCELLED"}
        target = _target(self, context)
        if target is None:
            return {"CANCELLED"}
        _ob, layer, mod, mat = target
        try:
            path = presets.save_user_preset(self.kind, self.name, mod, mat)
            with open(path, encoding="utf-8") as fh:
                pid = json.load(fh)["id"]
        except (OSError, ValueError) as exc:
            self.report({"ERROR"}, f"Could not save the preset: {exc}")
            return {"CANCELLED"}
        if self.kind == "GRASS":
            layer.preset = pid
            layer.preset_hash = presets.snapshot_hash(mod)
        else:
            layer.wind_preset = pid
        self.report({"INFO"}, f"Saved preset {self.name.strip()}")
        return {"FINISHED"}


class SWAYFIELD_OT_delete_preset(bpy.types.Operator):
    bl_idname = "swayfield.delete_preset"
    bl_label = "Delete Preset"
    bl_description = "Delete one of your own presets. Built-in presets cannot be deleted"
    bl_options = {"REGISTER", "UNDO"}

    preset_id: StringProperty(name="Preset", description="Id of the user preset to delete")
    kind: EnumProperty(name="Kind", items=_kind_items, default="GRASS")

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        from ..core import presets

        if not self.preset_id.startswith(presets.USER_PREFIX):
            self.report({"ERROR"}, "Only your own presets can be deleted")
            return {"CANCELLED"}
        try:
            presets.delete_user_preset(self.kind, self.preset_id)
        except (KeyError, OSError, ValueError) as exc:
            self.report({"ERROR"}, f"Could not delete the preset: {exc}")
            return {"CANCELLED"}
        return {"FINISHED"}


classes = (
    SWAYFIELD_OT_apply_preset,
    SWAYFIELD_OT_apply_wind_preset,
    SWAYFIELD_OT_save_preset,
    SWAYFIELD_OT_delete_preset,
)


def register() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
