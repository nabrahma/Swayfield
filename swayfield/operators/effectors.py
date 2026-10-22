# SPDX-License-Identifier: GPL-3.0-or-later
"""Effectors, exclusion objects and the wind direction empty (SC-11, SC-12, AN effectors)."""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, EnumProperty
from mathutils import Vector

from ..core import budget, compat, layers, node_setup

#: type id -> (Type input value, object name, label)
EFFECTOR_TYPES = {
    "VORTEX": (0, "SF_Vortex", "Vortex"),
    "RADIAL_BLAST": (1, "SF_Radial_Blast", "Radial Blast"),
    "TRAMPLE": (2, "SF_Trample", "Trample"),
    "SHELTER": (3, "SF_Shelter", "Shelter"),
}
#: A blast pulse rises over this many frames and falls over the same number.
PULSE_HALF_FRAMES = 12


def _keyframe_pulse(ob: bpy.types.Object, mod: bpy.types.Modifier, start: int) -> None:
    """Strength 0 -> 1 -> 0 over about 24 frames, so a Radial Blast goes off once."""
    path = compat.input_data_path(mod, "Strength")
    for frame, value in ((start, 0.0), (start + PULSE_HALF_FRAMES, 1.0), (start + 2 * PULSE_HALF_FRAMES, 0.0)):
        compat.set_input(mod, "Strength", value)
        ob.keyframe_insert(data_path=path, frame=frame)


class SWAYFIELD_OT_add_effector(bpy.types.Operator):
    bl_idname = "swayfield.add_effector"
    bl_label = "Add Effector"
    bl_description = "Add a Vortex, Radial Blast, Trample or Shelter effector at the 3D cursor"
    bl_options = {"REGISTER", "UNDO"}

    type: EnumProperty(name="Type", description="What the effector does to the grass",
                       items=(("VORTEX", "Vortex", "Swirls grass around a point"),
                              ("RADIAL_BLAST", "Radial Blast", "Pushes grass away from a point, like an explosion"),
                              ("TRAMPLE", "Trample", "Bends grass away from something walking through it"),
                              ("SHELTER", "Shelter", "Calms the wind behind a wall or rock")),
                       default="VORTEX")
    pulse: BoolProperty(name="Pulse", description="Keyframe a Radial Blast that goes off once, starting at the "
                        "current frame", default=True)

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            cls.poll_message_set("Go back to Object mode first")
            return False
        return True

    def execute(self, context):
        from ..core import nodes

        try:
            group = nodes.ensure("effector_point")
        except ImportError:
            self.report({"ERROR"}, "Effectors are not available in this version of Swayfield")
            return {"CANCELLED"}

        type_value, name, label = EFFECTOR_TYPES[self.type]
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([(0.0, 0.0, 0.0)], [], [])
        ob = bpy.data.objects.new(name, mesh)
        ob.location = context.scene.cursor.location
        ob["sf_effector_type"] = self.type
        ob.show_name = True
        collection = node_setup.ensure_effector_collection(context.scene)
        collection.objects.link(ob)

        mod = ob.modifiers.new("Effector", "NODES")
        mod.node_group = group
        compat.set_input(mod, "Type", type_value)
        if self.type == "RADIAL_BLAST" and self.pulse:
            _keyframe_pulse(ob, mod, context.scene.frame_current)

        target = layers.active_target(context)
        if target is not None:
            compat.set_input(target[2], "effector_collection", collection)
            self.report({"INFO"}, f"Added {label} effector {ob.name} at the 3D cursor")
        else:
            self.report({"INFO"}, f"Added {label} effector {ob.name}. Add grass to a surface to use it")
        budget.invalidate()
        return {"FINISHED"}


class SWAYFIELD_OT_add_exclusion(bpy.types.Operator):
    bl_idname = "swayfield.add_exclusion"
    bl_label = "Add Exclusion Objects"
    bl_description = ("Clear grass around the other selected objects, such as paths, rocks or buildings. "
                      "Make the grass surface the active object")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if layers.active_target(context) is None:
            cls.poll_message_set("Select an object with a grass layer first")
            return False
        return True

    def execute(self, context):
        from .add_grass import is_effector

        ob, layer, mod = layers.active_target(context)
        chosen = [o for o in context.selected_objects if o != ob and not is_effector(o)
                  and "sf_effector_type" not in o and not layers.is_grass_object(o)]
        if not chosen:
            self.report({"ERROR"}, "Select the objects that should clear grass, then select the grass surface "
                                   "last so it is active")
            return {"CANCELLED"}
        collection = compat.get_input(mod, "exclusion_collection")
        if collection is None:
            collection = bpy.data.collections.new(f"SF_Exclude_{ob.name}_{layer.name}")
            compat.set_input(mod, "exclusion_collection", collection)
        for other in chosen:
            if other.name not in collection.objects:
                collection.objects.link(other)
        budget.invalidate()
        self.report({"INFO"}, f"{len(chosen)} object" + ("s" if len(chosen) != 1 else "") + " now clear grass")
        return {"FINISHED"}


def world_bounds(ob: bpy.types.Object) -> tuple[Vector, Vector]:
    """Minimum and maximum corner of the object's bounding box in world space."""
    corners = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    low = Vector(min(c[i] for c in corners) for i in range(3))
    high = Vector(max(c[i] for c in corners) for i in range(3))
    return low, high


class SWAYFIELD_OT_add_direction_empty(bpy.types.Operator):
    bl_idname = "swayfield.add_direction_empty"
    bl_label = "Add Wind Direction Empty"
    bl_description = ("Add an empty above the surface whose X arrow sets the wind direction. "
                      "Rotate or keyframe it to steer the wind")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if layers.active_target(context) is None:
            cls.poll_message_set("Select an object with a grass layer first")
            return False
        return True

    def execute(self, context):
        ob, _layer, mod = layers.active_target(context)
        low, high = world_bounds(ob)
        empty = bpy.data.objects.new("SF_Wind_Direction", None)
        empty.empty_display_type = "PLAIN_AXES"
        empty.empty_display_size = 1.0
        empty.location = ((low.x + high.x) / 2.0, (low.y + high.y) / 2.0, high.z + 1.0)
        empty.rotation_euler = (0.0, 0.0, float(compat.get_input(mod, "direction")))
        context.collection.objects.link(empty)
        compat.set_input(mod, "direction_object", empty)
        self.report({"INFO"}, f"Added {empty.name}. Rotate it around Z to turn the wind")
        return {"FINISHED"}


classes = (SWAYFIELD_OT_add_effector, SWAYFIELD_OT_add_exclusion, SWAYFIELD_OT_add_direction_empty)
