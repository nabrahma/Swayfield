# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators for the layer material."""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, StringProperty


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

        ob = context.active_object
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


classes = (SWAYFIELD_OT_load_texture_set,)


def register() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
