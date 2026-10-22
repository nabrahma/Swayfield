# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators for the layer material."""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty


class SWAYFIELD_OT_load_texture_set(bpy.types.Operator):
    bl_idname = "swayfield.load_texture_set"
    bl_label = "Load Texture Set"
    bl_description = ("Pick a folder with texture maps and fill the Image Maps slots by file name suffix "
                      "(_albedo, _rough, _normal, _opacity, ...)")
    bl_options = {"REGISTER", "UNDO"}

    directory: StringProperty(name="Folder", subtype="DIR_PATH", description="Folder that holds the texture maps")
    filter_folder: BoolProperty(default=True, options={"HIDDEN"})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        from ..core import compat, layers, materials

        ob = layers.surface_of(context.active_object)
        layer = layers.active_layer(ob) if ob is not None else None
        mat = layers.layer_material(ob, layer) if layer is not None else None
        if mat is None:
            self.report({"ERROR"}, "Select a mesh with Swayfield grass first")
            return {"CANCELLED"}
        if not self.directory:
            self.report({"ERROR"}, "Choose a folder that contains texture maps")
            return {"CANCELLED"}
        result = materials.load_texture_set(mat, self.directory)
        try:
            count = len(result)
        except TypeError:
            count = int(result or 0)
        if count <= 0:
            self.report({"WARNING"}, "No texture maps found. Files need suffixes like _albedo, _rough, _normal, "
                                     "_opacity")
            return {"CANCELLED"}
        materials.set_mode(mat, 1)
        node = mat.node_tree.nodes.get("SF_Image_Opacity") if mat.node_tree else None
        if node is not None and getattr(node, "image", None) is not None:
            mod = layers.get_modifier(ob, layer)
            if mod is not None:
                compat.set_input(mod, "blade_source", 1)
        self.report({"INFO"}, f"Loaded {count} texture map{'s' if count != 1 else ''}")
        return {"FINISHED"}


_SLOT_ITEMS: list[tuple[str, str, str]] = []


def _slot_items(self, context):
    # Blender keeps pointers into these strings, so the list must outlive the call.
    if not _SLOT_ITEMS:
        from ..core import materials

        _SLOT_ITEMS.extend((slot, slot, f"{slot} map") for slot in materials.IMAGE_SLOTS)
    return _SLOT_ITEMS


def _layer_material(context):
    from ..core import layers

    surface = layers.surface_of(context.active_object)
    layer = layers.active_layer(surface) if surface is not None else None
    return layers.layer_material(surface, layer) if layer is not None else None


class SWAYFIELD_OT_pick_image(bpy.types.Operator):
    bl_idname = "swayfield.pick_image"
    bl_label = "Pick Image"
    bl_description = "Choose an image file for this material slot. The colour space is set for you"
    bl_options = {"REGISTER", "UNDO"}

    slot: EnumProperty(name="Slot", items=_slot_items, description="Material slot to fill")
    filepath: StringProperty(name="File", subtype="FILE_PATH", description="Image file to load")
    filter_image: BoolProperty(default=True, options={"HIDDEN"})
    filter_folder: BoolProperty(default=True, options={"HIDDEN"})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        from ..core import materials

        mat = _layer_material(context)
        if mat is None:
            self.report({"ERROR"}, "Select a mesh with Swayfield grass first")
            return {"CANCELLED"}
        if not self.filepath:
            self.report({"ERROR"}, "Choose an image file")
            return {"CANCELLED"}
        try:
            image = bpy.data.images.load(self.filepath, check_existing=True)
        except RuntimeError:
            self.report({"ERROR"}, "Could not read that file. Choose a PNG, JPG, TIFF or EXR image")
            return {"CANCELLED"}
        materials.assign_image(mat, self.slot, image)
        return {"FINISHED"}


class SWAYFIELD_OT_clear_image(bpy.types.Operator):
    bl_idname = "swayfield.clear_image"
    bl_label = "Clear Image"
    bl_description = "Remove the image from this material slot, so the slot falls back to its neutral value"
    bl_options = {"REGISTER", "UNDO"}

    slot: EnumProperty(name="Slot", items=_slot_items, description="Material slot to empty")

    def execute(self, context):
        from ..core import materials

        mat = _layer_material(context)
        if mat is None:
            self.report({"ERROR"}, "Select a mesh with Swayfield grass first")
            return {"CANCELLED"}
        materials.assign_image(mat, self.slot, None)
        return {"FINISHED"}


classes = (SWAYFIELD_OT_load_texture_set, SWAYFIELD_OT_pick_image, SWAYFIELD_OT_clear_image)


def register() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
