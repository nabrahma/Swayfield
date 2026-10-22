# SPDX-License-Identifier: GPL-3.0-or-later
"""Camera and Simplify drivers evaluate in background mode."""

import math

import bpy
import pytest

from swayfield.core import compat, drivers, node_setup


def _update():
    bpy.context.view_layer.update()


@pytest.fixture
def layer_mod(plane, camera):
    _, mod = node_setup.create_layer(plane, "Grass")
    return plane, mod


def _get(mod, key):
    return compat.get_input(mod, key)


def test_every_driven_input_gets_a_driver(layer_mod, camera):
    ob, mod = layer_mod
    assert drivers.has_camera_drivers(ob, mod)
    paths = {f.data_path for f in ob.animation_data.drivers}
    for key in drivers.DRIVEN_KEYS:
        assert compat.input_data_path(mod, key) in paths, key
    assert set(drivers.DRIVEN_KEYS) >= {
        "cam_focal_length", "cam_sensor_width", "cam_sensor_height", "cam_sensor_fit", "cam_shift_x",
        "cam_shift_y", "cam_ortho", "cam_ortho_scale", "res_x", "res_y", "simplify"}


def test_expressions_are_simple(layer_mod, camera):
    """Simple expressions run without Python, so they work even with auto-run scripts disabled."""
    ob, _ = layer_mod
    for fcurve in ob.animation_data.drivers:
        assert fcurve.driver.is_simple_expression, fcurve.driver.expression


def test_lens_follows_the_camera(layer_mod, camera):
    ob, mod = layer_mod
    cam = camera.data
    cam.lens = 85.0
    cam.sensor_width = 24.0
    cam.sensor_height = 13.5
    cam.shift_x = 0.1
    cam.shift_y = -0.2
    cam.sensor_fit = "VERTICAL"
    _update()
    assert _get(mod, "cam_focal_length") == pytest.approx(85.0)
    assert _get(mod, "cam_sensor_width") == pytest.approx(24.0)
    assert _get(mod, "cam_sensor_height") == pytest.approx(13.5)
    assert _get(mod, "cam_shift_x") == pytest.approx(0.1)
    assert _get(mod, "cam_shift_y") == pytest.approx(-0.2)
    assert _get(mod, "cam_sensor_fit") == 2


@pytest.mark.parametrize("fit,index", [("AUTO", 0), ("HORIZONTAL", 1), ("VERTICAL", 2)])
def test_sensor_fit_matches_the_input_items(layer_mod, camera, fit, index):
    ob, mod = layer_mod
    camera.data.sensor_fit = fit
    _update()
    assert _get(mod, "cam_sensor_fit") == index


def test_orthographic_camera(layer_mod, camera):
    ob, mod = layer_mod
    _update()
    assert _get(mod, "cam_ortho") is False or _get(mod, "cam_ortho") == 0
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 12.5
    _update()
    assert bool(_get(mod, "cam_ortho")) is True
    assert _get(mod, "cam_ortho_scale") == pytest.approx(12.5)
    camera.data.type = "PANO"
    _update()
    assert bool(_get(mod, "cam_ortho")) is False


def test_resolution_follows_the_scene(layer_mod, camera, scene):
    ob, mod = layer_mod
    scene.render.resolution_x = 2048
    scene.render.resolution_y = 858
    _update()
    assert _get(mod, "res_x") == 2048
    assert _get(mod, "res_y") == 858


def test_drivers_follow_the_active_camera(layer_mod, camera, scene):
    ob, mod = layer_mod
    camera.data.lens = 35.0
    other_data = bpy.data.cameras.new("Other")
    other_data.lens = 120.0
    other = bpy.data.objects.new("Other", other_data)
    scene.collection.objects.link(other)
    _update()
    assert _get(mod, "cam_focal_length") == pytest.approx(35.0)
    scene.camera = other
    _update()
    assert _get(mod, "cam_focal_length") == pytest.approx(120.0)


def test_simplify_factor(layer_mod, scene):
    ob, mod = layer_mod
    scene.render.use_simplify = False
    scene.render.simplify_child_particles = 0.25
    _update()
    assert _get(mod, "simplify") == pytest.approx(1.0)
    scene.render.use_simplify = True
    _update()
    assert _get(mod, "simplify") == pytest.approx(0.25)
    scene.render.use_simplify = False
    _update()
    assert _get(mod, "simplify") == pytest.approx(1.0)


def test_missing_camera_does_not_raise(plane, scene):
    scene.camera = None
    _, mod = node_setup.create_layer(plane, "Grass")
    _update()
    # No camera drivers: an unresolvable driver would write 0, so the inputs keep their defaults.
    assert _get(mod, "cam_focal_length") == pytest.approx(50.0)
    assert _get(mod, "cam_sensor_width") == pytest.approx(36.0)
    assert bool(_get(mod, "cam_ortho")) is False
    assert not drivers.has_camera_drivers(plane, mod)
    # The scene drivers are still there.
    scene.render.resolution_x = 1280
    _update()
    assert _get(mod, "res_x") == 1280


def test_camera_added_later_is_picked_up(plane, scene):
    scene.camera = None
    _, mod = node_setup.create_layer(plane, "Grass")
    drivers.check_cameras()
    cam_data = bpy.data.cameras.new("Late")
    cam_data.lens = 18.0
    cam = bpy.data.objects.new("Late", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    assert drivers.check_cameras() is True
    _update()
    assert drivers.has_camera_drivers(plane, mod)
    assert _get(mod, "cam_focal_length") == pytest.approx(18.0)
    assert drivers.check_cameras() is False, "nothing changed since the last check"


def test_removing_the_camera_restores_defaults(layer_mod, camera, scene):
    ob, mod = layer_mod
    camera.data.lens = 85.0
    drivers.check_cameras()
    _update()
    assert _get(mod, "cam_focal_length") == pytest.approx(85.0)
    scene.camera = None
    assert drivers.check_cameras() is True
    _update()
    assert not drivers.has_camera_drivers(ob, mod)
    assert _get(mod, "cam_focal_length") == pytest.approx(50.0)
    scene.camera = camera
    drivers.check_cameras()
    _update()
    assert _get(mod, "cam_focal_length") == pytest.approx(85.0)


def test_camera_watch_timer(addon):
    assert bpy.app.timers.is_registered(drivers._watch_cameras)


def test_adding_drivers_twice_does_not_duplicate(layer_mod, camera):
    ob, mod = layer_mod
    before = len(ob.animation_data.drivers)
    drivers.add_camera_drivers(ob, mod)
    assert len(ob.animation_data.drivers) == before


def test_remove_drivers(layer_mod, camera):
    ob, mod = layer_mod
    drivers.remove_camera_drivers(ob, mod)
    assert not drivers.has_camera_drivers(ob, mod)
    assert len(ob.animation_data.drivers) == 0


def test_two_layers_have_their_own_drivers(plane, camera):
    _, a = node_setup.create_layer(plane, "A")
    _, b = node_setup.create_layer(plane, "B")
    camera.data.lens = 70.0
    _update()
    assert _get(a, "cam_focal_length") == pytest.approx(70.0)
    assert _get(b, "cam_focal_length") == pytest.approx(70.0)
    assert len(plane.animation_data.drivers) == 2 * len(drivers.DRIVEN_KEYS)


def test_fov_math_is_consistent(layer_mod, camera):
    """The values are enough to rebuild the field of view in nodes."""
    ob, mod = layer_mod
    camera.data.lens = 50.0
    camera.data.sensor_width = 36.0
    _update()
    fov = 2 * math.atan(_get(mod, "cam_sensor_width") / (2 * _get(mod, "cam_focal_length")))
    assert fov == pytest.approx(camera.data.angle_x, rel=1e-4)
