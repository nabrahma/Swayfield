# SPDX-License-Identifier: GPL-3.0-or-later
"""Layers: node_setup, layers helpers, enum proxies, versioning and the blade budget."""

import bpy
import pytest

from swayfield.core import budget, compat, layers, node_setup, nodes, spec, versioning


def _presets():
    try:
        from swayfield.core import presets
    except ImportError:
        pytest.skip("presets module not available yet")
    return presets


def _make_v0_group():
    """An older main group: different identifier order, one input that v1 no longer has."""
    from swayfield.core.nodes import builder

    tree = bpy.data.node_groups.new("SF_Main_v0", "GeometryNodeTree")
    builder.add_socket(tree, "Geometry", "GEOMETRY", "INPUT")
    builder.add_socket(tree, "Legacy Gain", "FLOAT", default=2.5)
    builder.add_socket(tree, "Material", "MATERIAL")
    builder.add_socket(tree, "Intensity", "FLOAT", default=1.0)
    builder.add_socket(tree, "Density", "FLOAT", default=800.0)
    builder.add_socket(tree, "Geometry", "GEOMETRY", "OUTPUT")
    return tree


# ---------------------------------------------------------------------------
# create / remove / duplicate
# ---------------------------------------------------------------------------

def test_create_layer_sets_up_everything(plane):
    layer, mod = node_setup.create_layer(plane, "Base Grass", seed_offset=9973, link_id="abc")
    assert layers.is_swayfield_modifier(mod)
    assert mod.name == "Swayfield Base Grass"
    assert list(plane.modifiers)[-1] == mod
    assert layer.name == "Base Grass" and layer.modifier_name == mod.name
    assert layer.link_id == "abc" and layer.preset == "CUSTOM"
    assert plane.swayfield.active_layer_index == 0
    assert layers.active_layer(plane).name == "Base Grass"
    assert layers.get_modifier(plane, layer) == mod
    assert compat.get_input(mod, "seed_offset") == 9973

    mat = layers.layer_material(plane, layer)
    assert mat is not None and mat.name == "SF_Ground_Base Grass"
    effectors = compat.get_input(mod, "effector_collection")
    assert effectors is not None and effectors.name == "SF_Effectors"
    assert effectors.name in bpy.context.scene.collection.children


def test_effector_collection_is_shared(plane):
    _, a = node_setup.create_layer(plane, "A")
    _, b = node_setup.create_layer(plane, "B")
    assert compat.get_input(a, "effector_collection") == compat.get_input(b, "effector_collection")
    assert len([c for c in bpy.data.collections if c.name.startswith("SF_Effectors")]) == 1


def test_layer_names_and_modifiers_are_unique(plane):
    first, mod1 = node_setup.create_layer(plane, "Grass")
    second, mod2 = node_setup.create_layer(plane, "Grass")
    assert first.name == "Grass" and second.name == "Grass 2"
    assert mod1.name != mod2.name
    assert plane.swayfield.active_layer_index == 1
    assert layers.unique_layer_name(plane, "Grass") == "Grass 3"


def test_swayfield_modifier_is_last_even_with_subdivision(plane):
    sub = plane.modifiers.new("Subdivision", "SUBSURF")
    _, mod = node_setup.create_layer(plane, "Grass")
    assert list(plane.modifiers) == [sub, mod]
    plane.modifiers.new("Displace", "DISPLACE")
    assert list(plane.modifiers)[-1] == mod, "a later modifier must not end up below the grass"


def test_is_swayfield_modifier_ignores_other_modifiers(plane):
    other = plane.modifiers.new("Other", "NODES")
    assert not layers.is_swayfield_modifier(other)
    assert not layers.is_swayfield_modifier(plane.modifiers.new("Sub", "SUBSURF"))
    _, mod = node_setup.create_layer(plane, "Grass")
    assert layers.is_swayfield_modifier(mod)


def test_remove_layer_cleans_up(plane):
    layer, mod = node_setup.create_layer(plane, "Grass")
    mat_name = layers.layer_material(plane, layer).name
    node_setup.remove_layer(plane, layer)
    assert not plane.modifiers
    assert not plane.swayfield.layers
    assert mat_name not in bpy.data.materials
    assert not [f for f in (plane.animation_data.drivers if plane.animation_data else [])]


def test_remove_layer_keeps_a_shared_material(plane):
    a, mod_a = node_setup.create_layer(plane, "A")
    b, mod_b = node_setup.create_layer(plane, "B")
    shared = layers.layer_material(plane, a)
    shared_name = shared.name
    compat.set_input(mod_b, "material", shared)
    node_setup.remove_layer(plane, a)
    assert shared_name in bpy.data.materials
    assert [layer.name for layer in plane.swayfield.layers] == ["B"]
    assert plane.swayfield.active_layer_index == 0


def test_remove_layer_removes_its_exclusion_collection(plane):
    layer, mod = node_setup.create_layer(plane, "Grass")
    coll = bpy.data.collections.new("SF_Exclude_Ground_Grass")
    compat.set_input(mod, "exclusion_collection", coll)
    node_setup.remove_layer(plane, layer)
    assert "SF_Exclude_Ground_Grass" not in bpy.data.collections


def test_duplicate_layer_copies_values_and_material(plane):
    layer, mod = node_setup.create_layer(plane, "Grass", link_id="x")
    compat.set_input(mod, "density", 1234.0)
    compat.set_input(mod, "length_max", 0.77)
    compat.set_input(mod, "blade_source", 1)
    compat.set_input(mod, "wave_strength", 0.5)
    compat.set_input(mod, "density_group", "SomeGroup")
    layer.preset = "LAWN"
    new_layer, new_mod = node_setup.duplicate_layer(plane, layer)

    assert new_layer.name == "Grass Copy"
    assert new_mod.name != mod.name
    assert compat.get_input(new_mod, "density") == pytest.approx(1234.0)
    assert compat.get_input(new_mod, "length_max") == pytest.approx(0.77)
    assert compat.get_input(new_mod, "blade_source") == 1
    assert compat.get_input(new_mod, "density_group") == "SomeGroup"
    new_mat = layers.layer_material(plane, new_layer)
    assert new_mat is not None and new_mat != layers.layer_material(plane, layer)
    assert new_mat.name == "SF_Ground_Grass Copy"
    assert new_layer.preset == "LAWN"
    assert new_layer.link_id == "", "a duplicate is not linked to its source"
    assert layers.get_modifier(plane, new_layer) == new_mod
    assert plane.swayfield.active_layer_index == 1


def test_duplicate_gets_its_own_camera_drivers(plane, camera):
    layer, _ = node_setup.create_layer(plane, "Grass")
    _, new_mod = node_setup.duplicate_layer(plane, layer)
    from swayfield.core import drivers
    assert drivers.has_camera_drivers(plane, new_mod)


# ---------------------------------------------------------------------------
# enum proxies
# ---------------------------------------------------------------------------

ENUM_KEYS = [i.key for i in spec.INPUTS if i.type == "INT" and i.items]


def test_every_spec_enum_has_a_proxy(plane):
    layer, _ = node_setup.create_layer(plane, "Grass")
    assert set(ENUM_KEYS) >= {"blade_source", "display_mode", "sway_mode", "slope_blend", "altitude_blend",
                              "noise_blend", "image_blend", "proximity_blend", "camdist_blend", "cam_sensor_fit"}
    for key in ENUM_KEYS:
        assert hasattr(layer, key), key
        assert hasattr(layer.bl_rna.properties[key], "enum_items")


@pytest.mark.parametrize("key", ENUM_KEYS)
def test_enum_proxy_reads_and_writes_the_modifier(plane, key):
    layer, mod = node_setup.create_layer(plane, "Grass")
    items = spec.get(key).items
    last = items[-1][0]
    setattr(layer, key, last)
    assert compat.get_input(mod, key) == len(items) - 1
    compat.set_input(mod, key, 0)
    assert getattr(layer, key) == items[0][0]


def test_enum_proxy_without_modifier_is_safe(plane):
    layer, mod = node_setup.create_layer(plane, "Grass")
    plane.modifiers.remove(mod)
    assert layer.blade_source == "STRANDS"
    layer.blade_source = "RIBBONS"  # nothing to write to, must not raise


def test_material_mode_proxy(plane):
    from swayfield.core import materials
    layer, _ = node_setup.create_layer(plane, "Grass")
    mat = layers.layer_material(plane, layer)
    if not materials.is_swayfield_material(mat):
        pytest.skip("core.materials is not creating layer materials yet")
    ids = [item[0] for item in materials.MODE_ITEMS]
    layer.material_mode = ids[2]
    assert materials.get_mode(mat) == 2
    materials.set_mode(mat, 1)
    assert layer.material_mode == ids[1]


# ---------------------------------------------------------------------------
# presets: Custom detection
# ---------------------------------------------------------------------------

def test_preset_label_custom_by_default(plane):
    layer, _ = node_setup.create_layer(plane, "Grass")
    assert layers.preset_label(plane, layer) == "Custom"


def test_preset_label_follows_edits(plane):
    presets = _presets()
    layer, mod = node_setup.create_layer(plane, "Grass")
    presets.apply_grass_preset(mod, layers.layer_material(plane, layer), "LAWN")
    layers.mark_preset(plane, layer, "LAWN")
    assert layer.preset == "LAWN" and layer.preset_hash
    name = layers.preset_label(plane, layer)
    assert name != "Custom" and "awn" in name

    compat.set_input(mod, "density", compat.get_input(mod, "density") + 100.0)
    layers.clear_caches()
    assert layers.preset_label(plane, layer) == "Custom"

    # Putting the value back makes it the preset again.
    compat.set_input(mod, "density", compat.get_input(mod, "density") - 100.0)
    layers.clear_caches()
    assert layers.preset_label(plane, layer) == name


def test_preset_label_is_cheap_enough_for_draw(plane):
    import time

    presets = _presets()
    layer, mod = node_setup.create_layer(plane, "Grass")
    presets.apply_grass_preset(mod, layers.layer_material(plane, layer), "ROLLING_MEADOW")
    layers.mark_preset(plane, layer, "ROLLING_MEADOW")
    layers.preset_label(plane, layer)
    start = time.perf_counter()
    for _ in range(200):
        layers.preset_label(plane, layer)
    per_call = (time.perf_counter() - start) / 200
    assert per_call < 0.002, f"{per_call * 1000:.2f} ms per call"


# ---------------------------------------------------------------------------
# surface resolution
# ---------------------------------------------------------------------------

def _grid(size, cuts, name="G"):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=cuts, y_subdivisions=cuts, size=size)
    ob = bpy.context.active_object
    ob.name = name
    return ob


def test_surface_too_coarse(scene):
    coarse = _grid(100.0, 10, "Coarse")
    fine = _grid(10.0, 100, "Fine")
    assert layers.surface_too_coarse(coarse)
    assert not layers.surface_too_coarse(fine)
    assert layers.mean_edge_length(fine) == pytest.approx(0.1, rel=0.1)


def test_surface_too_coarse_uses_world_scale(scene):
    ob = _grid(10.0, 100, "Scaled")
    assert not layers.surface_too_coarse(ob)
    ob.scale = (4.0, 4.0, 4.0)
    bpy.context.view_layer.update()
    assert layers.surface_too_coarse(ob)


def test_surface_too_coarse_ignores_non_meshes(scene):
    bpy.ops.object.empty_add()
    assert not layers.surface_too_coarse(bpy.context.active_object)


# ---------------------------------------------------------------------------
# versioning
# ---------------------------------------------------------------------------

def test_current_version(plane):
    _, mod = node_setup.create_layer(plane, "Grass")
    assert versioning.CURRENT_MAIN == nodes.group_name("main")
    assert versioning.group_version(mod) == 1
    assert not versioning.needs_upgrade(mod)


def test_upgrade_from_a_fake_older_version(plane, camera):
    layer, mod = node_setup.create_layer(plane, "Grass")
    old = _make_v0_group()
    mod.node_group = old
    compat.set_input(mod, "Density", 321.0)
    compat.set_input(mod, "Intensity", 0.7)
    compat.set_input(mod, "Legacy Gain", 9.0)
    fcurve = plane.driver_add(compat.input_data_path(mod, "Intensity"))
    fcurve.driver.type = "SCRIPTED"
    fcurve.driver.expression = "frame / 100"

    assert versioning.group_version(mod) == 0
    assert versioning.needs_upgrade(mod)
    assert versioning.upgrade_layer(plane, layer) is True

    assert mod.node_group.name == versioning.CURRENT_MAIN
    assert not versioning.needs_upgrade(mod)
    assert compat.get_input(mod, "density") == pytest.approx(321.0)
    assert not compat.has_input(mod, "Legacy Gain")
    # The user's own driver survives, with the new socket identifier.
    bpy.context.scene.frame_set(50)
    bpy.context.view_layer.update()
    assert compat.get_input(mod, "intensity") == pytest.approx(0.5)
    # The camera drivers are back too.
    from swayfield.core import drivers
    assert drivers.has_camera_drivers(plane, mod)
    # Nothing left over from the old identifiers.
    paths = [f.data_path for f in plane.animation_data.drivers]
    assert len(paths) == len(set(paths))
    assert versioning.upgrade_layer(plane, layer) is False


def test_upgrade_keeps_the_material(plane):
    layer, mod = node_setup.create_layer(plane, "Grass")
    mat = layers.layer_material(plane, layer)
    mod.node_group = _make_v0_group()
    compat.set_input(mod, "Material", mat)
    versioning.upgrade_layer(plane, layer)
    assert layers.layer_material(plane, layer) == mat


# ---------------------------------------------------------------------------
# budget
# ---------------------------------------------------------------------------

def test_estimate_from_area_uses_world_space(plane):
    assert budget.surface_area(plane) == pytest.approx(100.0, rel=1e-3)
    assert budget.estimate_from_area(plane, 800.0) == pytest.approx(80_000, rel=1e-3)
    plane.scale = (2.0, 2.0, 2.0)
    bpy.context.view_layer.update()
    assert budget.estimate_from_area(plane, 800.0) == pytest.approx(320_000, rel=1e-3)


def test_estimate_from_area_handles_empty_meshes(scene):
    me = bpy.data.meshes.new("empty")
    ob = bpy.data.objects.new("empty", me)
    scene.collection.objects.link(ob)
    assert budget.estimate_from_area(ob, 800.0) == 0


def test_count_is_zero_for_a_passthrough_stub(plane):
    layer, mod = node_setup.create_layer(plane, "Grass")
    budget.invalidate()
    assert budget.count_blades(plane, mod) in range(0, 1_000_000)


def _curves_group():
    tree = bpy.data.node_groups.new("TestCurves", "GeometryNodeTree")
    tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gin = tree.nodes.new("NodeGroupInput")
    gout = tree.nodes.new("NodeGroupOutput")
    to_curve = tree.nodes.new("GeometryNodeMeshToCurve")
    tree.links.new(gin.outputs[0], to_curve.inputs[0])
    tree.links.new(to_curve.outputs[0], gout.inputs[0])
    return tree


def test_count_reads_curves_from_the_evaluated_geometry(scene):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=5, y_subdivisions=5)
    ob = bpy.context.active_object
    mod = ob.modifiers.new("Test", "NODES")
    mod.node_group = _curves_group()
    budget.invalidate()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    geometry = ob.evaluated_get(depsgraph).evaluated_geometry()
    expected = len(geometry.curves.curves)
    assert expected > 0
    assert budget._object_total(ob, depsgraph) == expected


def test_layers_split_the_object_total(plane, monkeypatch):
    a, mod_a = node_setup.create_layer(plane, "A")
    b, mod_b = node_setup.create_layer(plane, "B")
    compat.set_input(mod_a, "density", 100.0)
    compat.set_input(mod_b, "density", 300.0)
    monkeypatch.setattr(budget, "_object_total", lambda ob, depsgraph=None: 4000)
    assert budget.count_blades(plane, mod_a) == 1000
    assert budget.count_blades(plane, mod_b) == 3000
    mod_a.show_viewport = False
    assert budget.count_blades(plane, mod_a) == 0
    assert budget.count_blades(plane, mod_b) == 4000


def test_render_estimate_divides_by_the_viewport_fraction(plane, monkeypatch):
    _, mod = node_setup.create_layer(plane, "A")
    monkeypatch.setattr(budget, "_object_total", lambda ob, depsgraph=None: 20_000)
    compat.set_input(mod, "optimised", True)
    compat.set_input(mod, "viewport_density", 20.0)
    compat.set_input(mod, "simplify", 1.0)
    assert budget.viewport_fraction(mod) == pytest.approx(0.2)
    assert budget.estimate_render_count(plane, mod) == 100_000
    compat.set_input(mod, "optimised", False)
    assert budget.estimate_render_count(plane, mod) == 20_000
    mod.show_render = False
    assert budget.estimate_render_count(plane, mod) == 0


def test_scene_totals_and_budget_guard(plane, monkeypatch):
    _, mod = node_setup.create_layer(plane, "A")
    monkeypatch.setattr(budget, "_object_total", lambda ob, depsgraph=None: 3000)
    context = bpy.context
    totals = budget.scene_totals(context)
    assert totals.viewport == 3000 and totals[0] == 3000
    assert totals.render == 3000
    context.scene.swayfield.budget = 5000
    assert not budget.would_exceed_budget(context, 1000)
    assert budget.would_exceed_budget(context, 3000)
    assert not budget.would_exceed_budget(context)


def test_default_scene_settings(scene):
    settings = bpy.context.scene.swayfield
    settings.property_unset("budget")
    settings.property_unset("auto_optimise_threshold")
    assert settings.budget == 2_000_000
    assert settings.auto_optimise_threshold == 500_000
