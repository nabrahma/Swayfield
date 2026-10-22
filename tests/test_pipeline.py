# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end tests of SF_Main_v1 with every stage wired in."""

from __future__ import annotations

import bpy
import pytest
from conftest import evaluated

from swayfield.core import compat, nodes, spec


def _grass_object(surface):
    """A hair Curves object carrying the main group, as node_setup creates it."""
    ob = bpy.data.objects.new("Grass", bpy.data.hair_curves.new("Grass"))
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = surface
    mod = ob.modifiers.new("Swayfield", "NODES")
    mod.node_group = nodes.ensure("main")
    compat.set_input(mod, "surface", surface)
    return ob, mod


def _geometry(ob):
    return evaluated(ob).evaluated_geometry()


def _blade_count(ob) -> int:
    geometry = _geometry(ob)
    curves = geometry.curves
    return len(curves.curves) if curves is not None else 0


def test_main_exposes_every_spec_input():
    tree = nodes.ensure("main")
    names = {i.name for i in tree.interface.items_tree if i.item_type == "SOCKET" and i.in_out == "INPUT"}
    assert {i.name for i in spec.INPUTS} <= names


def test_main_has_bake_node():
    assert nodes.ensure("main").nodes.get("SF_Bake") is not None


def test_no_surface_gives_no_grass(scene):
    ob = bpy.data.objects.new("Grass", bpy.data.hair_curves.new("Grass"))
    scene.collection.objects.link(ob)
    mod = ob.modifiers.new("Swayfield", "NODES")
    mod.node_group = nodes.ensure("main")
    assert _blade_count(ob) == 0


def test_defaults_grow_blades(plane, camera):
    ob, mod = _grass_object(plane)
    compat.set_input(mod, "density", 200.0)
    count = _blade_count(ob)
    # 100 m² at 200 per m²; Poisson and camera culling remove some.
    assert 2_000 < count < 22_000


def test_blades_carry_shading_attributes(plane, camera):
    ob, mod = _grass_object(plane)
    compat.set_input(mod, "density", 100.0)
    geometry = _geometry(ob)  # keep the set alive while reading its components
    names = set(geometry.curves.attributes.keys())
    assert set(spec.PUBLIC_ATTRIBUTES) <= names


def test_grass_follows_surface_transform(plane, camera):
    ob, mod = _grass_object(plane)
    compat.set_input(mod, "density", 50.0)
    compat.set_input(mod, "render_cull", False)
    compat.set_input(mod, "lod_enable", False)
    before = _blade_count(ob)
    plane.scale = (2.0, 2.0, 1.0)
    plane.update_tag()
    after = _blade_count(ob)
    assert after == pytest.approx(before * 4, rel=0.15)


def test_mask_preview_adds_surface_copy(plane, camera):
    ob, mod = _grass_object(plane)
    compat.set_input(mod, "density", 10.0)
    geometry = _geometry(ob)
    assert geometry.mesh is None or len(geometry.mesh.polygons) == 0
    compat.set_input(mod, "mask_preview", True)
    geometry = _geometry(ob)
    assert geometry.mesh is not None and len(geometry.mesh.polygons) == len(plane.data.polygons)


@pytest.mark.parametrize("display, component", [("POINTS", "pointcloud"), ("BOUNDS", "curves")])
def test_optimised_display_modes(plane, camera, display, component):
    ob, mod = _grass_object(plane)
    compat.set_input(mod, "density", 50.0)
    compat.set_input(mod, "optimised", True)
    compat.set_input(mod, "display_mode", spec.get("display_mode").item_index(display))
    assert getattr(_geometry(ob), component) is not None


def test_ribbons_render_as_mesh(plane, camera):
    ob, mod = _grass_object(plane)
    compat.set_input(mod, "density", 20.0)
    compat.set_input(mod, "blade_source", spec.get("blade_source").item_index("RIBBONS"))
    geometry = _geometry(ob)
    assert geometry.mesh is not None and "UVMap" in geometry.mesh.attributes
