# SPDX-License-Identifier: GPL-3.0-or-later
"""Render the built-in grass preset thumbnails.

Usage::

    blender -b --factory-startup --python tools/render_thumbnails.py -- [PRESET_ID ...]

For every built-in grass preset (or only the ids given), this builds the same small scene (a gently
rolling 8 m patch), adds grass with the preset through the real ``swayfield.add_grass`` and
``swayfield.quick_look`` operators, frames it from 1.6 m looking slightly down along the wind, and
renders a 256 x 256 EEVEE image to ``swayfield/presets/grass/<file stem>.png``, next to the JSON,
where ``core.presets`` finds it.
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent.parent
RESOLUTION = 256
FRAME = 24  # a moment with gusts already travelling across the patch
SAMPLES = 32
PATCH_SIZE = 12.0
CAMERA_LOCATION = (0.0, -5.5, 2.2)
CAMERA_ROTATION = (math.radians(63.0), 0.0, 0.0)
CAMERA_LENS = 30.0
SOIL_COLOR = (0.035, 0.03, 0.015, 1.0)
#: Pixel filter width; a slightly soft filter keeps the PNG small without visible blur at 256 px.
FILTER_SIZE = 2.5
#: Colour levels per channel tried after rendering, until the file fits. Fewer levels compress better.
LEVELS = (64, 48, 40, 32, 24)
MAX_KB = 60


def _register():
    sys.path.insert(0, str(ROOT))
    import swayfield

    swayfield.register()
    return swayfield


def _scene(preset_id: str) -> bpy.types.Scene:
    from swayfield.operators import add_grass

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=48, y_subdivisions=48, size=PATCH_SIZE)
    surface = bpy.context.active_object
    texture = bpy.data.textures.new("SF_Thumb_Hills", "CLOUDS")
    texture.noise_scale = 1.2
    displace = surface.modifiers.new("Displace", "DISPLACE")
    displace.texture = texture
    displace.strength = 0.35
    soil = bpy.data.materials.new("SF_Thumb_Soil")
    soil.diffuse_color = SOIL_COLOR
    if bpy.app.version < (5, 0, 0):
        soil.use_nodes = True
    bsdf = soil.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = SOIL_COLOR
        bsdf.inputs["Roughness"].default_value = 0.9
    surface.data.materials.append(soil)
    surface.select_set(True)
    result = bpy.ops.swayfield.add_grass(preset=preset_id)
    if "FINISHED" not in result:
        raise RuntimeError(f"Add Grass failed for {preset_id}")
    add_grass.flush_density_preview()
    bpy.ops.swayfield.quick_look()

    camera = scene.camera
    camera.location = CAMERA_LOCATION
    camera.rotation_euler = CAMERA_ROTATION
    camera.data.lens = CAMERA_LENS

    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in _engines() else "BLENDER_EEVEE"
    if hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = SAMPLES
    scene.render.resolution_x = scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = 100
    scene.render.filter_size = FILTER_SIZE
    settings = scene.render.image_settings
    settings.file_format = "PNG"
    settings.color_mode = "RGB"
    settings.color_depth = "8"
    settings.compression = 100
    scene.frame_set(FRAME)
    return scene


def _quantize(path: Path, levels: int) -> None:
    """Reduce the PNG to ``levels`` levels per channel, so it compresses better."""
    import numpy as np

    image = bpy.data.images.load(str(path), check_existing=False)
    pixels = np.empty(len(image.pixels), dtype=np.float32)
    image.pixels.foreach_get(pixels)
    step = 255.0 / (levels - 1)
    pixels = np.round(np.round(pixels * 255.0 / step) * step) / 255.0
    image.pixels.foreach_set(pixels.astype(np.float32))
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def _save_small(scene: bpy.types.Scene, path: Path) -> None:
    """Render, then lower the colour levels until the PNG fits in ``MAX_KB``."""
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    raw = path.read_bytes()
    for levels in LEVELS:
        path.write_bytes(raw)
        _quantize(path, levels)
        if path.stat().st_size <= MAX_KB * 1024:
            return
    print(f"WARNING: {path.name} is larger than {MAX_KB} KB")


def _engines() -> set[str]:
    return {item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}


def main() -> int:
    swayfield = _register()
    from swayfield.core import presets

    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    wanted = set(argv)
    entries = [p for p in presets.list_grass_presets() if p.get("builtin") and (not wanted or p["id"] in wanted)]
    if not entries:
        print("No matching built-in grass presets")
        return 1
    for entry in entries:
        start = time.perf_counter()
        scene = _scene(entry["id"])
        out = Path(entry["path"]).with_suffix(".png")
        _save_small(scene, out)
        print(f"{entry['id']}: {out.name} {out.stat().st_size / 1024:.1f} KB in {time.perf_counter() - start:.1f} s")
    swayfield.unregister()
    return 0


if __name__ == "__main__":
    sys.exit(main())
