# SPDX-License-Identifier: GPL-3.0-or-later
"""Bake the scatter with Blender's Bake node (SC-14)."""

from __future__ import annotations

import bpy

from ..core import layers

BAKE_NODE_NAME = "SF_Bake"


def find_bake_id(mod: bpy.types.Modifier) -> int | None:
    """Bake id of the ``SF_Bake`` node in the modifier's group, or None when it has none."""
    group = mod.node_group
    node = group.nodes.get(BAKE_NODE_NAME) if group is not None else None
    if node is None:
        return None
    for bake in mod.bakes:
        bake_node = getattr(bake, "node", None)
        if bake_node is not None and bake_node.name == node.name:
            return bake.bake_id
    # Blender 4.2 versions without Bake.node: the id is the node's identifier.
    identifier = getattr(node, "identifier", None)
    for bake in mod.bakes:
        if bake.bake_id == identifier:
            return bake.bake_id
    return None


class _BakeOperator(bpy.types.Operator):
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if layers.active_target(context) is None:
            cls.poll_message_set("Select an object with a grass layer first")
            return False
        return True

    def _target(self, context):
        ob, layer, mod = layers.active_target(context)
        bake_id = find_bake_id(mod)
        if bake_id is None:
            self.report({"ERROR"}, "This layer has no scatter bake node. Upgrade the layer, then try again")
            return None
        return ob, mod, bake_id


class SWAYFIELD_OT_bake_scatter(_BakeOperator):
    bl_idname = "swayfield.bake_scatter"
    bl_label = "Bake Scatter"
    bl_description = "Store the blade placement so heavy masks are not recalculated every frame. Wind stays live"

    def execute(self, context):
        target = self._target(context)
        if target is None:
            return {"CANCELLED"}
        ob, mod, bake_id = target
        with context.temp_override(object=ob, active_object=ob):
            result = bpy.ops.object.geometry_node_bake_single(
                session_uid=ob.session_uid, modifier_name=mod.name, bake_id=bake_id)
        if "FINISHED" not in result:
            self.report({"ERROR"}, "The bake did not run. Check that the layer is visible, then try again")
            return {"CANCELLED"}
        return {"FINISHED"}


class SWAYFIELD_OT_free_bake(_BakeOperator):
    bl_idname = "swayfield.free_bake"
    bl_label = "Free Bake"
    bl_description = "Delete the stored blade placement, so the scatter updates live again"

    def execute(self, context):
        target = self._target(context)
        if target is None:
            return {"CANCELLED"}
        ob, mod, bake_id = target
        with context.temp_override(object=ob, active_object=ob):
            result = bpy.ops.object.geometry_node_bake_delete_single(
                session_uid=ob.session_uid, modifier_name=mod.name, bake_id=bake_id)
        if "FINISHED" not in result:
            self.report({"ERROR"}, "There was no bake to free")
            return {"CANCELLED"}
        return {"FINISHED"}


classes = (SWAYFIELD_OT_bake_scatter, SWAYFIELD_OT_free_bake)
