# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures. Tests run inside Blender via tools/run_tests.py."""

from __future__ import annotations

import bpy
import pytest


@pytest.fixture(scope="session", autouse=True)
def addon():
    import swayfield

    swayfield.register()
    yield swayfield
    swayfield.unregister()


def _clear_data() -> None:
    for collection in (bpy.data.objects, bpy.data.meshes, bpy.data.curves, bpy.data.materials,
                       bpy.data.node_groups, bpy.data.cameras, bpy.data.lights, bpy.data.images):
        for block in list(collection):
            collection.remove(block)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)


@pytest.fixture
def scene():
    """An empty scene with frame 1 set."""
    _clear_data()
    sc = bpy.context.scene
    sc.frame_set(1)
    yield sc
    _clear_data()


@pytest.fixture
def plane(scene):
    """A 10 m x 10 m subdivided plane, selected and active."""
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=40, y_subdivisions=40, size=10.0)
    ob = bpy.context.active_object
    ob.name = "Ground"
    return ob


@pytest.fixture
def camera(scene):
    """A camera at 1 m height looking along +Y, set as the scene camera."""
    import math

    bpy.ops.object.camera_add(location=(0.0, -6.0, 1.0), rotation=(math.radians(85), 0.0, 0.0))
    cam = bpy.context.active_object
    scene.camera = cam
    return cam


def evaluated(ob):
    """The evaluated version of ``ob`` after a depsgraph update."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    return ob.evaluated_get(depsgraph)
