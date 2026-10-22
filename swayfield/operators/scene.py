# SPDX-License-Identifier: GPL-3.0-or-later
"""Quick Look: a test camera at 1 m height, a warm sun and the Punchy colour grade."""

from __future__ import annotations

import math

import bpy
from mathutils import Vector

from ..core import drivers, layers
from .effectors import world_bounds

CAMERA_NAME = "SF_Quick_Look_Camera"
SUN_NAME = "SF_Quick_Look_Sun"
WORLD_NAME = "SF_Quick_Look_World"
CAMERA_HEIGHT = 1.0
#: Identifier of the Punchy look; older Blender versions name it differently.
LOOK_CANDIDATES = ("AgX - Punchy", "Punchy")

# Late-afternoon light: a low warm sun skimming the field from the left (upwind for the default +X
# wind), so flattened crests catch the light and the upright blades in the gaps fall into shade.
# The sky is a dim gradient, so shadows stay dark and the greens stay saturated.
SUN_ENERGY = 7.0
SUN_COLOR = (1.0, 0.9, 0.72)
SUN_ROTATION = (math.radians(64.0), 0.0, math.radians(260.0))  # 26 deg high, from the left (upwind)
SKY_HORIZON = (0.80, 0.66, 0.48, 1.0)
SKY_ZENITH = (0.16, 0.34, 0.80, 1.0)
SKY_STRENGTH = 0.8
EXPOSURE = 0.0


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


def _sky(scene: bpy.types.Scene) -> str | None:
    """A late-afternoon gradient sky: warm pale horizon, deeper blue zenith.

    Built from basic nodes (no Sky Texture) so it looks the same in EEVEE and Cycles on every
    supported version. It is kept dim next to the sun, so blades in shadow stay dark.
    """
    world = bpy.data.worlds.get(WORLD_NAME) or bpy.data.worlds.new(WORLD_NAME)
    if world.node_tree is None and hasattr(world, "use_nodes"):
        world.use_nodes = True  # Blender 4.x; newer versions create the node tree themselves
    nt = world.node_tree
    nt.nodes.clear()
    coords = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    background = nt.nodes.new("ShaderNodeBackground")
    output = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(coords.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], background.inputs["Color"])
    nt.links.new(background.outputs[0], output.inputs["Surface"])
    stops = ramp.color_ramp.elements
    stops[0].position, stops[0].color = 0.0, SKY_HORIZON
    stops[1].position, stops[1].color = 0.3, SKY_ZENITH
    background.inputs["Strength"].default_value = SKY_STRENGTH
    for i, node in enumerate((coords, sep, ramp, background, output)):
        node.location = (i * 250.0, 0.0)
    previous = scene.world
    if previous is not None and previous != world:
        # Keep the user's own world in the file, so it is not purged on save once unassigned.
        previous.use_fake_user = True
    scene.world = world
    return previous.name if previous is not None and previous != world else None


class SWAYFIELD_OT_quick_look(bpy.types.Operator):
    bl_idname = "swayfield.quick_look"
    bl_label = "Quick Look"
    bl_description = ("Set up a test camera 1 m above the grass surface, a low warm sun, a sky and the AgX Punchy "
                      "look, so the first render looks good")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if layers.target_mesh(context) is None:
            cls.poll_message_set("Select the grass surface first")
            return False
        return True

    def execute(self, context):
        ob = layers.target_mesh(context)
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
        sun_data.energy = SUN_ENERGY
        sun_data.angle = math.radians(3.0)
        sun_data.color = SUN_COLOR
        sun = _ensure_object(scene, SUN_NAME, sun_data)
        sun.location = (centre_x, low.y, high.z + 10.0)
        sun.rotation_euler = SUN_ROTATION

        previous_world = _sky(scene)
        scene.view_settings.exposure = EXPOSURE
        if not _grade(scene):
            self.report({"WARNING"}, "The Punchy look is not available in this Blender version. "
                                     "Pick a look in Color Management")
        if previous_world:
            self.report({"INFO"}, f"Quick Look is ready. Press F12 to render. Your world \"{previous_world}\" "
                                  "is kept; switch back in the World properties")
        else:
            self.report({"INFO"}, "Quick Look is ready. Press F12 to render")
        return {"FINISHED"}


classes = (SWAYFIELD_OT_quick_look,)
