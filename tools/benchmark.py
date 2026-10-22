# SPDX-License-Identifier: GPL-3.0-or-later
"""Benchmark the PRD reference scene.

Usage::

    blender -b --factory-startup --python tools/benchmark.py -- [--frames N] [--out DIR]

Scene: 100 m x 100 m noise-displaced terrain, Rolling Meadow preset, camera at 1 m height, 1920 x 1080.
Measures per-frame depsgraph evaluation time with Optimised Mode off and on, the blade count and peak memory.

Limitation: background mode measures evaluation cost on the CPU. It does NOT measure GPU viewport fps,
so it cannot confirm the PRD "24 fps with Optimised Mode on" target. Use it to compare releases.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HEADLESS_NOTE = (
    "Measured in background mode: this is depsgraph evaluation cost (CPU), not GPU viewport fps. "
    "It does not verify the viewport playback targets."
)


def peak_memory_mb() -> float | None:
    """Peak resident memory of this process in MB, or None if it cannot be obtained."""
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024
    except ImportError:
        pass
    try:
        import psutil

        info = psutil.Process().memory_info()
        return getattr(info, "peak_wset", info.rss) / (1024 * 1024)
    except ImportError:
        return None


def build_scene(bpy) -> object:
    """Create the terrain, camera and settings; return the terrain object."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    scene.render.resolution_percentage = 100

    bpy.ops.mesh.primitive_grid_add(x_subdivisions=200, y_subdivisions=200, size=100.0)
    terrain = bpy.context.active_object
    terrain.name = "Terrain"
    tex = bpy.data.textures.new("TerrainNoise", "CLOUDS")
    tex.noise_scale = 25.0
    disp = terrain.modifiers.new("Displace", "DISPLACE")
    disp.texture = tex
    disp.strength = 1.5
    disp.mid_level = 0.5
    bpy.ops.object.modifier_apply(modifier=disp.name)

    cam_data = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = (0.0, -20.0, 1.0)
    cam.rotation_euler = (math.radians(88), 0.0, 0.0)
    scene.camera = cam
    return terrain


def find_modifier(terrain):
    """Return the Swayfield modifier of the first layer."""
    try:
        return terrain.modifiers[terrain.swayfield.layers[0].modifier_name]
    except (AttributeError, IndexError, KeyError):
        for mod in terrain.modifiers:
            if mod.type == "NODES":
                return mod
    raise RuntimeError("No Swayfield modifier found on the terrain")


def count_blades(bpy, terrain) -> int | None:
    """Blade count via swayfield.core.budget.count_blades, or None when unavailable."""
    try:
        from swayfield.core import budget
    except ImportError:
        return None
    for args in ((terrain,), (bpy.context.evaluated_depsgraph_get(), terrain)):
        try:
            return int(budget.count_blades(*args))
        except Exception:  # noqa: BLE001 - signature not final, try the next form
            continue
    return None


def time_frames(bpy, frames: int) -> dict:
    """Step ``frames`` frames and time frame_set plus a depsgraph update; return timing statistics in ms."""
    scene = bpy.context.scene
    start = scene.frame_start
    samples = []
    for i in range(frames):
        t0 = time.perf_counter()
        scene.frame_set(start + i)
        bpy.context.evaluated_depsgraph_get().update()
        samples.append((time.perf_counter() - t0) * 1000.0)
    ordered = sorted(samples)
    return {
        "frames": frames,
        "mean_ms": statistics.fmean(samples),
        "median_ms": statistics.median(samples),
        "p95_ms": ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))],
        "max_ms": ordered[-1],
        "eval_fps": 1000.0 / statistics.fmean(samples),
    }


def to_markdown(report: dict) -> str:
    """Render the report as a Markdown table."""
    lines = [
        "# Swayfield benchmark",
        "",
        f"Blender {report['blender']}, {report['platform']}, {report['frames']} frames.",
        "",
        f"> {HEADLESS_NOTE}",
        "",
        "| Optimised Mode | Blades | Mean ms | Median ms | P95 ms | Max ms | Eval fps | Peak RAM MB |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for run in report["runs"]:
        t = run["timing"]
        blades = "n/a" if run["blades"] is None else f"{run['blades']:,}"
        mem = "n/a" if run["peak_memory_mb"] is None else f"{run['peak_memory_mb']:.0f}"
        lines.append(
            f"| {'on' if run['optimised'] else 'off'} | {blades} | {t['mean_ms']:.1f} | {t['median_ms']:.1f} "
            f"| {t['p95_ms']:.1f} | {t['max_ms']:.1f} | {t['eval_fps']:.1f} | {mem} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=24, help="frames to time per run")
    parser.add_argument("--out", default=str(ROOT / "benchmarks" / "results"), help="output directory")
    args = parser.parse_args(argv)

    import bpy

    sys.path.insert(0, str(ROOT))
    import swayfield
    from swayfield.core import compat

    swayfield.register()
    terrain = build_scene(bpy)
    if not hasattr(bpy.ops.swayfield, "add_grass"):
        print("ERROR: bpy.ops.swayfield.add_grass is not available; the operators are not finished yet.")
        return 2
    bpy.context.view_layer.objects.active = terrain
    terrain.select_set(True)
    t0 = time.perf_counter()
    if "FINISHED" not in bpy.ops.swayfield.add_grass(preset="ROLLING_MEADOW"):
        print("ERROR: add_grass(preset='ROLLING_MEADOW') did not finish.")
        return 2
    bpy.context.evaluated_depsgraph_get().update()
    add_seconds = time.perf_counter() - t0
    mod = find_modifier(terrain)

    runs = []
    for optimised in (False, True):
        compat.set_input(mod, "optimised", optimised)
        bpy.context.evaluated_depsgraph_get().update()
        runs.append({
            "optimised": optimised,
            "blades": count_blades(bpy, terrain),
            "timing": time_frames(bpy, args.frames),
            "peak_memory_mb": peak_memory_mb(),
        })

    report = {
        "blender": bpy.app.version_string,
        "platform": platform.platform(),
        "frames": args.frames,
        "add_grass_seconds": add_seconds,
        "note": HEADLESS_NOTE,
        "runs": runs,
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (out / f"benchmark-{stamp}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown = to_markdown(report)
    (out / f"benchmark-{stamp}.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"Add Grass took {add_seconds:.2f} s. Results written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
