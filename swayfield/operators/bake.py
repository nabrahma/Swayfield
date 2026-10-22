# SPDX-License-Identifier: GPL-3.0-or-later
"""Bake the scatter with Blender's Bake node (SC-14)."""

from __future__ import annotations

import bpy

from ..core import compat, layers

BAKE_NODE_NAME = "SF_Bake"
#: Seconds between checks for a finished bake job, and the longest wait before giving up.
RESTORE_POLL_SECONDS = 0.5
RESTORE_GIVE_UP_SECONDS = 1800.0


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
        _surface, _layer, mod = layers.active_target(context)
        grass = mod.id_data  # the modifier, and so the bake, lives on the layer's grass object
        bake_id = find_bake_id(mod)
        if bake_id is None:
            self.report({"ERROR"}, "This layer has no scatter bake node. Upgrade the layer, then try again")
            return None
        return grass, mod, bake_id


class _FullDensity:
    """Optimised Mode and Simplify thin the scatter before the Bake node, so a bake taken with
    them on would be used for renders too. This holds them at "off" and restores them afterwards."""

    def __init__(self, grass: bpy.types.Object, mod: bpy.types.Modifier):
        self.grass, self.mod = grass, mod
        self.optimised = compat.get_input(mod, "optimised")
        self.simplify = compat.get_input(mod, "simplify")
        anim = grass.animation_data
        path = compat.input_data_path(mod, "simplify")
        self.driver = next((f for f in anim.drivers if f.data_path == path), None) if anim else None
        self.driver_muted = self.driver.mute if self.driver is not None else False

    def apply(self) -> None:
        if self.driver is not None:
            self.driver.mute = True  # a muted driver keeps the value we set
        compat.set_input(self.mod, "optimised", False)
        compat.set_input(self.mod, "simplify", 1.0)

    def restore(self) -> None:
        try:
            compat.set_input(self.mod, "optimised", self.optimised)
            compat.set_input(self.mod, "simplify", self.simplify)
            if self.driver is not None:
                self.driver.mute = self.driver_muted
        except ReferenceError:
            pass  # the object was deleted while the bake ran


def _restore_when_done(state: _FullDensity) -> None:
    """Restore after the bake job ends. In the interface the bake runs as a background job."""
    waited = [0.0]

    def poll():
        waited[0] += RESTORE_POLL_SECONDS
        if bpy.app.is_job_running("OBJECT_BAKE") and waited[0] < RESTORE_GIVE_UP_SECONDS:
            return RESTORE_POLL_SECONDS
        state.restore()
        return None

    bpy.app.timers.register(poll, first_interval=RESTORE_POLL_SECONDS * 2)


def run_bake(context, grass: bpy.types.Object, mod: bpy.types.Modifier, bake_id: int):
    """Call Blender's bake operator for one bake node."""
    with context.temp_override(object=grass, active_object=grass):
        return bpy.ops.object.geometry_node_bake_single(
            session_uid=grass.session_uid, modifier_name=mod.name, bake_id=bake_id)


class SWAYFIELD_OT_bake_scatter(_BakeOperator):
    bl_idname = "swayfield.bake_scatter"
    bl_label = "Bake Scatter"
    bl_description = "Store the blade placement so heavy masks are not recalculated every frame. Wind stays live"

    def execute(self, context):
        target = self._target(context)
        if target is None:
            return {"CANCELLED"}
        ob, mod, bake_id = target
        state = _FullDensity(ob, mod)
        state.apply()
        try:
            result = run_bake(context, ob, mod, bake_id)
        except RuntimeError:
            state.restore()
            self.report({"ERROR"}, "The bake did not run. Check that the layer is visible, then try again")
            return {"CANCELLED"}
        started = "FINISHED" in result
        if started and not bpy.app.background:
            _restore_when_done(state)
        else:
            state.restore()  # failed, or finished already (background mode runs the bake in place)
        if not started:
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
