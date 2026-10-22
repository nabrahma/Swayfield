# SPDX-License-Identifier: GPL-3.0-or-later
"""Drivers that copy camera lens data and Simplify settings into hidden modifier inputs.

Geometry Nodes can read the active camera's transform but not its lens, so
these drivers copy it. Every variable reads ``scene.camera.data...`` through
the scene, so the drivers follow whichever camera is active. Drivers (not
handlers) keep this working in background renders.

Enum properties read as their integer value in a driver: ``sensor_fit`` gives
0 Auto, 1 Horizontal, 2 Vertical (the same order as the ``cam_sensor_fit``
input) and the camera ``type`` gives 0 Perspective, 1 Orthographic, 2 Panoramic.
"""

from __future__ import annotations

import bpy

from . import compat, spec

_ORTHO = 1

#: (input key, scene data path, expression). ``v`` is the first variable, ``s`` the second.
_DRIVEN: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("cam_focal_length", ("camera.data.lens",), "v"),
    ("cam_sensor_width", ("camera.data.sensor_width",), "v"),
    ("cam_sensor_height", ("camera.data.sensor_height",), "v"),
    ("cam_sensor_fit", ("camera.data.sensor_fit",), "v"),
    ("cam_shift_x", ("camera.data.shift_x",), "v"),
    ("cam_shift_y", ("camera.data.shift_y",), "v"),
    ("cam_ortho", ("camera.data.type",), f"1 if v == {_ORTHO} else 0"),
    ("cam_ortho_scale", ("camera.data.ortho_scale",), "v"),
    ("res_x", ("render.resolution_x",), "v"),
    ("res_y", ("render.resolution_y",), "v"),
    # Factor 1 when Simplify is off, otherwise the viewport child-particle percentage.
    ("simplify", ("render.simplify_child_particles", "render.use_simplify"), "v if s else 1"),
)

DRIVEN_KEYS = tuple(key for key, _, _ in _DRIVEN)
#: The drivers that read the camera, which only exist while the scene has one.
CAMERA_KEYS = tuple(key for key, paths, _ in _DRIVEN if paths[0].startswith("camera."))
#: Seconds between looks at the scene camera.
WATCH_SECONDS = 1.0


def _has(mod: bpy.types.Modifier, key: str) -> bool:
    return compat.has_input(mod, spec.BY_KEY[key].name)


def _scene_for(ob: bpy.types.Object) -> bpy.types.Scene:
    scenes = ob.users_scene
    return scenes[0] if scenes else bpy.context.scene


def _add_driver(ob: bpy.types.Object, mod: bpy.types.Modifier, scene: bpy.types.Scene, key: str,
                paths: tuple[str, ...], expression: str) -> None:
    data_path = compat.input_data_path(mod, key)
    try:
        ob.driver_remove(data_path)
    except (TypeError, RuntimeError, KeyError):
        pass  # no driver there yet
    fcurve = ob.driver_add(data_path)
    driver = fcurve.driver
    driver.type = "SCRIPTED"
    for name, path in zip(("v", "s"), paths):
        var = driver.variables.new()
        var.name = name
        var.type = "SINGLE_PROP"
        target = var.targets[0]
        target.id_type = "SCENE"
        target.id = scene
        target.data_path = path
    driver.expression = expression


def _remove_driver(ob: bpy.types.Object, mod: bpy.types.Modifier, key: str) -> None:
    try:
        ob.driver_remove(compat.input_data_path(mod, key))
    except (TypeError, RuntimeError, KeyError):
        pass


def add_camera_drivers(ob: bpy.types.Object, mod: bpy.types.Modifier) -> None:
    """Add (or re-add) the camera, resolution and Simplify drivers on ``mod``.

    The camera drivers need a scene camera: a driver whose path cannot be
    resolved is flagged invalid and then writes 0, and Blender only clears
    that flag when the driver is edited. So without a camera they are left
    out and the inputs keep their defaults. ``sync_camera_drivers`` adds them
    once a camera exists.
    """
    scene = _scene_for(ob)
    has_camera = scene.camera is not None and scene.camera.type == "CAMERA"
    for key, paths, expression in _DRIVEN:
        if not _has(mod, key):
            continue
        if key in CAMERA_KEYS and not has_camera:
            _remove_driver(ob, mod, key)
            continue
        _add_driver(ob, mod, scene, key, paths, expression)


def sync_camera_drivers(ob: bpy.types.Object) -> None:
    """Make the camera drivers of every Swayfield layer on ``ob`` match the scene camera.

    Adds them when a camera appeared, and removes them (restoring the default
    values) when the camera is gone.
    """
    from . import layers

    scene = _scene_for(ob)
    has_camera = scene.camera is not None and scene.camera.type == "CAMERA"
    paths = {key: (p, e) for key, p, e in _DRIVEN}
    for mod in layers.swayfield_modifiers(ob):
        present = {f.data_path for f in ob.animation_data.drivers} if ob.animation_data else set()
        for key in CAMERA_KEYS:
            if not _has(mod, key):
                continue
            has_driver = compat.input_data_path(mod, key) in present
            if has_camera:
                # Re-adding also clears an "invalid" flag left by an earlier camera change.
                _add_driver(ob, mod, scene, key, *paths[key])
            elif has_driver:
                _remove_driver(ob, mod, key)
                compat.set_input(mod, key, spec.BY_KEY[key].default)


_seen_cameras: dict[str, tuple | None] = {}


def check_cameras(force: bool = False) -> bool:
    """Sync the drivers of every scene whose camera changed since the last call. Returns True if any did.

    ``force=True`` syncs every scene, for operators that just changed the camera.
    """
    from . import layers

    changed = False
    for scene in bpy.data.scenes:
        cam = scene.camera
        stamp = (cam.name, cam.as_pointer()) if cam is not None else None
        if not force and _seen_cameras.get(scene.name, "") == stamp:
            continue
        _seen_cameras[scene.name] = stamp
        changed = True
        for ob in scene.objects:
            if ob.type == "MESH" and any(layers.iter_layers(ob)):
                sync_camera_drivers(ob)
    return changed


def _watch_cameras() -> float:
    """Timer: cheap, only looks at the scene cameras. Not part of any render path."""
    try:
        check_cameras()
    except (ReferenceError, RuntimeError):
        pass
    return WATCH_SECONDS


def start_camera_watch() -> None:
    _seen_cameras.clear()
    if not bpy.app.timers.is_registered(_watch_cameras):
        bpy.app.timers.register(_watch_cameras, first_interval=WATCH_SECONDS, persistent=True)


def stop_camera_watch() -> None:
    if bpy.app.timers.is_registered(_watch_cameras):
        bpy.app.timers.unregister(_watch_cameras)


def remove_camera_drivers(ob: bpy.types.Object, mod: bpy.types.Modifier) -> None:
    """Remove every driver this module added to ``mod``."""
    for key in DRIVEN_KEYS:
        if _has(mod, key):
            _remove_driver(ob, mod, key)


def remove_all_drivers(ob: bpy.types.Object, mod: bpy.types.Modifier) -> None:
    """Remove every driver that targets ``mod``, e.g. before deleting it."""
    prefix = f'modifiers["{bpy.utils.escape_identifier(mod.name)}"]'
    anim = ob.animation_data
    if anim is None:
        return
    for fcurve in [f for f in anim.drivers if f.data_path.startswith(prefix)]:
        anim.drivers.remove(fcurve)


def has_camera_drivers(ob: bpy.types.Object, mod: bpy.types.Modifier) -> bool:
    anim = ob.animation_data
    if anim is None:
        return False
    paths = {f.data_path for f in anim.drivers}
    return all(compat.input_data_path(mod, key) in paths for key in DRIVEN_KEYS if _has(mod, key))
