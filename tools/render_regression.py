# SPDX-License-Identifier: GPL-3.0-or-later
"""Render regression: render every preset and compare to stored references by SSIM.

Usage::

    blender -b --factory-startup --python tools/render_regression.py -- [--update] [--engine auto|eevee|cycles]

References live in ``tests/render/reference/<preset>_f<frame>.png``; outputs and diffs are written to
``tests/output/``. See ``tests/render/README.md``. ``bpy`` is imported lazily so that :func:`ssim` can be
imported (and unit tested) without it.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
REFERENCE_DIR = ROOT / "tests" / "render" / "reference"
OUTPUT_DIR = ROOT / "tests" / "output"

PRESETS = ("ROLLING_MEADOW", "LAWN", "WILD_FIELD", "STORMY_STEPPE", "ANIME_FIELD")
FRAMES = (1, 24)
RESOLUTION = 256
THRESHOLD = 0.98


# --------------------------------------------------------------------------- SSIM


def _gaussian_kernel(size: int = 11, sigma: float = 1.5) -> np.ndarray:
    """Normalised 1D Gaussian kernel."""
    x = np.arange(size, dtype=np.float64) - (size - 1) / 2.0
    k = np.exp(-(x**2) / (2.0 * sigma**2))
    return k / k.sum()


def _filter(img: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Separable 'valid' convolution of a 2D array with a 1D kernel."""
    size = kernel.size
    h, w = img.shape
    rows = np.zeros((h, w - size + 1))
    for i, weight in enumerate(kernel):
        rows += weight * img[:, i:i + w - size + 1]
    out = np.zeros((h - size + 1, w - size + 1))
    for i, weight in enumerate(kernel):
        out += weight * rows[i:i + h - size + 1, :]
    return out


def to_gray(img: np.ndarray) -> np.ndarray:
    """Convert an HxW, HxWx3 or HxWx4 float array to grayscale (Rec. 601 luma)."""
    img = np.asarray(img, dtype=np.float64)
    if img.ndim == 2:
        return img
    return img[..., 0] * 0.299 + img[..., 1] * 0.587 + img[..., 2] * 0.114


def ssim_map(a: np.ndarray, b: np.ndarray, data_range: float = 1.0) -> np.ndarray:
    """Per-pixel SSIM map (Gaussian window 11x11, sigma 1.5) of two images, cropped by the window border."""
    a, b = to_gray(a), to_gray(b)
    if a.shape != b.shape:
        raise ValueError(f"image shapes differ: {a.shape} vs {b.shape}")
    kernel = _gaussian_kernel()
    if min(a.shape) < kernel.size:
        raise ValueError("images are smaller than the SSIM window")
    c1, c2 = (0.01 * data_range) ** 2, (0.03 * data_range) ** 2
    mu_a, mu_b = _filter(a, kernel), _filter(b, kernel)
    var_a = _filter(a * a, kernel) - mu_a**2
    var_b = _filter(b * b, kernel) - mu_b**2
    cov = _filter(a * b, kernel) - mu_a * mu_b
    return ((2 * mu_a * mu_b + c1) * (2 * cov + c2)) / ((mu_a**2 + mu_b**2 + c1) * (var_a + var_b + c2))


def ssim(a: np.ndarray, b: np.ndarray, data_range: float = 1.0) -> float:
    """Mean grayscale SSIM of two images with values in ``[0, data_range]``."""
    return float(ssim_map(a, b, data_range).mean())


# --------------------------------------------------------------------------- Blender side


def _read_png(path: Path) -> np.ndarray:
    """Load a PNG as a top-down HxWx4 float array in [0, 1] (display-referred, no colour conversion)."""
    import bpy

    img = bpy.data.images.load(str(path))
    try:
        img.colorspace_settings.name = "Non-Color"
        w, h = img.size
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        return np.flipud(buf.reshape(h, w, 4))
    finally:
        bpy.data.images.remove(img)


def _write_png(path: Path, pixels: np.ndarray) -> None:
    """Save a top-down HxWx(3|4) float array as PNG."""
    import bpy

    h, w = pixels.shape[:2]
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[..., : pixels.shape[2]] = pixels
    img = bpy.data.images.new("sf_tmp", w, h, alpha=False, float_buffer=False)
    try:
        img.colorspace_settings.name = "Non-Color"
        img.pixels.foreach_set(np.flipud(rgba).ravel())
        img.filepath_raw = str(path)
        img.file_format = "PNG"
        img.save()
    finally:
        bpy.data.images.remove(img)


def pick_engine(requested: str) -> str:
    """Return the render engine id to use; 'auto' prefers EEVEE when a GPU context exists, else Cycles CPU."""
    import bpy

    eevee = next((e for e in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT")
                  if e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items), None)
    if requested == "cycles":
        return "CYCLES"
    if requested == "eevee":
        if eevee is None:
            raise RuntimeError("EEVEE is not available in this Blender build")
        return eevee
    if eevee is not None:
        try:
            import gpu

            gpu.platform.renderer_get()  # raises or returns '' when no GPU context can be created
            if gpu.platform.renderer_get():
                return eevee
        except Exception:  # noqa: BLE001 - any failure means no usable GPU context
            pass
    return "CYCLES"


def build_scene(engine: str) -> None:
    """Reset to an empty scene with a 10 m ground plane, fixed camera and sun."""
    import bpy

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = engine
    scene.render.resolution_x = scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "Standard"
    scene.render.film_transparent = False
    if engine == "CYCLES":
        scene.cycles.device = "CPU"
        scene.cycles.samples = 16
        scene.cycles.use_denoising = False
        scene.cycles.seed = 0
    else:
        scene.eevee.taa_render_samples = 16

    world = bpy.data.worlds.new("World")
    world.color = (0.35, 0.45, 0.6)
    scene.world = world

    bpy.ops.mesh.primitive_grid_add(x_subdivisions=40, y_subdivisions=40, size=10.0)
    ground = bpy.context.active_object
    ground.name = "Ground"

    cam_data = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = (0.0, -6.0, 1.0)
    cam.rotation_euler = (math.radians(85), 0.0, 0.0)
    scene.camera = cam

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("Sun", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(50), 0.0, math.radians(30))

    bpy.ops.object.select_all(action="DESELECT")
    ground.select_set(True)
    bpy.context.view_layer.objects.active = ground


def render_preset(preset: str, frame: int, out_path: Path) -> None:
    """Build the scene, apply ``preset`` and render ``frame`` to ``out_path``."""
    import bpy

    scene = bpy.context.scene
    scene.frame_set(frame)
    scene.render.filepath = str(out_path)
    bpy.ops.render.render(write_still=True)


def run(update: bool, engine_arg: str) -> int:
    """Render all presets; return a process exit code."""
    import bpy

    sys.path.insert(0, str(ROOT))
    import swayfield

    swayfield.register()
    if not hasattr(bpy.ops.swayfield, "add_grass"):
        print("ERROR: bpy.ops.swayfield.add_grass is not available; the grass pipeline is not finished.")
        return 2

    engine = pick_engine(engine_arg)
    print(f"Render engine: {engine}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    for preset in PRESETS:
        build_scene(engine)
        result = bpy.ops.swayfield.add_grass(preset=preset)
        if "FINISHED" not in result:
            failures.append(f"{preset}: add_grass returned {result}")
            continue
        for frame in FRAMES:
            name = f"{preset}_f{frame}"
            out_path = OUTPUT_DIR / f"{name}.png"
            render_preset(preset, frame, out_path)
            reference = REFERENCE_DIR / f"{name}.png"
            if update:
                reference.write_bytes(out_path.read_bytes())
                print(f"updated  {reference.relative_to(ROOT)}")
                continue
            if not reference.is_file():
                failures.append(f"{name}: missing reference (run with --update)")
                continue
            new, ref = _read_png(out_path), _read_png(reference)
            if new.shape != ref.shape:
                failures.append(f"{name}: size {new.shape} differs from reference {ref.shape}")
                continue
            score = ssim(new, ref)
            status = "ok  " if score >= THRESHOLD else "FAIL"
            print(f"{status} {name}: SSIM {score:.4f}")
            if score < THRESHOLD:
                diff = np.abs(to_gray(new) - to_gray(ref))
                _write_png(OUTPUT_DIR / f"{name}_diff.png", np.repeat(np.clip(diff * 4, 0, 1)[..., None], 3, axis=2))
                failures.append(f"{name}: SSIM {score:.4f} < {THRESHOLD}")

    if failures:
        print("\nRender regression failures:")
        for line in failures:
            print(f"  {line}")
        return 1
    print("Render regression passed." if not update else "References updated.")
    return 0


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="rewrite the reference images")
    parser.add_argument("--engine", choices=("auto", "eevee", "cycles"), default="auto")
    args = parser.parse_args(argv)
    return run(args.update, args.engine)


if __name__ == "__main__":
    sys.exit(main())
