# SPDX-License-Identifier: GPL-3.0-or-later
"""Quick Look: a test camera at 1 m height, a warm sun and the Punchy colour grade."""

from __future__ import annotations

import math

import bpy
from mathutils import Vector

from ..core import drivers
from .effectors import world_bounds

CAMERA_NAME = "SF_Quick_Look_Camera"
SUN_NAME = "SF_Quick_Look_Sun"
WORLD_NAME = "SF_Quick_Look_World"
CAMERA_HEIGHT = 1.0
#: Identifier of the Punchy look; older Blender versions name it differently.
LOOK_CANDIDATES = ("AgX - Punchy", "Punchy")


def _surface_height(ob: bpy.types.Object, x: float, y: float, low_z: float, high_z: float) -> float:
    """World height of the surface at (x, y), or the bottom of its bounds when the ray misses."""
    inverse = ob.matrix_world.inverted()
    origin = inverse @ Vector((x, y, high_z + 10.0))
    direction = (inverse.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
    hit, location, _normal, _index = ob.ray_cast(origin, direction)
    if hit:
        return (ob.matrix_world @ location).z
    return low_z


def _ensure_object(scene: bpy.types.Scene, name: str, data) -> bpy.types.Object:
    ob = bpy.data.objects.get(name)
    if ob is None or ob.type != ("CAMERA" if isinstance(data, bpy.types.Camera) else "LIGHT"):
        ob = bpy.data.objects.new(name, data)
    else:
        ob.data = data
    if ob.name not in scene.collection.all_objects:
        scene.collection.objects.link(ob)
    return ob


def _grade(scene: bpy.types.Scene) -> bool:
    """AgX with the Punchy look. Returns False when the look is not available."""
    settings = scene.view_settings
    try:
        settings.view_transform = "AgX"
    except TypeError:
        return False
    for look in LOOK_CANDIDATES:
        try:
            settings.look = look
            return True
        except TypeError:
            continue
    return False


def _sky(scene: bpy.types.Scene) -> None:
    """Give the scene a soft blue sky when it has no world, so first renders are not black."""
    if scene.world is not None:
        return
    world = bpy.data.worlds.new(WORLD_NAME)
    if hasattr(world, "use_nodes"):
        world.use_nodes = True
    background = world.node_tree.nodes.get("Background") if world.node_tree is not None else None
    if background is not None:
        background.inputs["Color"].default_value = (0.45, 0.62, 0.9, 1.0)
        background.inputs["Strength"].default_value = 1.0
    scene.world = world


class SWAYFIELD_OT_quick_look(bpy.types.Operator):
    bl_idname = "swayfield.quick_look"
    bl_label = "Quick Look"
    bl_description = ("Set up a test camera 1 m above the grass surface, a warm sun and the AgX Punchy look, "
                      "so the first render looks good")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        if ob is None or ob.type != "MESH":
            cls.poll_message_set("Select the grass surface first")
            return False
        return True

    def execute(self, context):
        ob = context.active_object
        scene = context.scene
        low, high = world_bounds(ob)
        size_y = max(high.y - low.y, 0.1)
        centre_x = (low.x + high.x) / 2.0
        edge_y = low.y + 0.02 * size_y
        ground = _surface_height(ob, centre_x, edge_y, low.z, high.z)

        cam_data = bpy.data.cameras.get(CAMERA_NAME) or bpy.data.cameras.new(CAMERA_NAME)
        cam_data.lens = 35.0
        cam_data.clip_end = max(cam_data.clip_end, size_y * 4.0)
        cam = _ensure_object(scene, CAMERA_NAME, cam_data)
        cam.location = (centre_x, low.y, ground + CAMERA_HEIGHT)
        cam.rotation_euler = (math.radians(87.0), 0.0, 0.0)  # level, looking along +Y, a touch downward
        scene.camera = cam
        drivers.check_cameras(force=True)  # grass layers pick up the new camera's lens

        sun_data = bpy.data.lights.get(SUN_NAME) or bpy.data.lights.new(SUN_NAME, "SUN")
        sun_data.energy = 4.0
        sun_data.angle = math.radians(3.0)
        sun_data.color = (1.0, 0.85, 0.65)
        sun = _ensure_object(scene, SUN_NAME, sun_data)
        sun.location = (centre_x, low.y, high.z + 10.0)
        sun.rotation_euler = (math.radians(60.0), 0.0, math.radians(30.0))

        _sky(scene)
        if not _grade(scene):
            self.report({"WARNING"}, "The Punchy look is not available in this Blender version. "
                                     "Pick a look in Color Management")
        self.report({"INFO"}, "Quick Look is ready. Press F12 to render")
        return {"FINISHED"}


classes = (SWAYFIELD_OT_quick_look,)
