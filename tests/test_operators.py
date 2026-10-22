# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators, run through bpy.ops in background mode."""

import math

import bpy
import pytest
from mathutils import Vector

from swayfield.core import compat, drivers, layers, node_setup, nodes, spec, versioning
from swayfield.operators import add_grass


def _clear_data_keep_nodes() -> None:
    """Like conftest's cleanup, but keeps the built Swayfield node groups: building them takes seconds."""
    from swayfield.core import nodes

    keep = {nodes.group_name(stage) for stage in nodes.STAGES}
    for collection in (bpy.data.objects, bpy.data.meshes, bpy.data.curves, bpy.data.hair_curves,
                       bpy.data.materials, bpy.data.cameras, bpy.data.lights, bpy.data.images,
                       bpy.data.worlds):
        for block in list(collection):
            collection.remove(block)
    for group in list(bpy.data.node_groups):
        if group.name not in keep and "sf_part" not in group:
            bpy.data.node_groups.remove(group)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)


@pytest.fixture
def scene():
    """An empty scene at frame 1 (replaces the conftest fixture to keep the node groups between tests)."""
    _clear_data_keep_nodes()
    sc = bpy.context.scene
    sc.camera = None
    sc.render.use_simplify = False
    sc.frame_set(1)
    yield sc
    _clear_data_keep_nodes()



@pytest.fixture(autouse=True)
def _cursor_at_origin():
    bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)


@pytest.fixture(autouse=True)
def _light_layers(monkeypatch):
    """New layers start with a tiny density, so tests that evaluate the pipeline stay fast.

    Presets applied afterwards (Add Grass) still set their own values, and those tests do not evaluate.
    """
    create = node_setup.create_layer

    def light(*args, **kwargs):
        layer, mod = create(*args, **kwargs)
        compat.set_input(mod, "density", 5.0)
        compat.set_input(mod, "density_ceiling", 10.0)
        return layer, mod

    monkeypatch.setattr(node_setup, "create_layer", light)


def _grass_objects():
    return [o for o in bpy.data.objects if o.get("sf_grass")]


def _grid(name, size=10.0, cuts=40, location=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=cuts, y_subdivisions=cuts, size=size, location=location)
    ob = bpy.context.active_object
    ob.name = name
    return ob


def _select(*objects, active=None):
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = active or objects[-1]


def _mod(ob, index=0):
    return layers.get_modifier(ob, ob.swayfield.layers[index])


def _preset(preset_id):
    try:
        from swayfield.core import presets
    except ImportError:
        pytest.skip("presets module not available yet")
    return presets.get_preset("GRASS", preset_id)


def _make_v0_group():
    from swayfield.core.nodes import builder

    tree = bpy.data.node_groups.new("SF_Main_v0", "GeometryNodeTree")
    builder.add_socket(tree, "Geometry", "GEOMETRY", "INPUT")
    builder.add_socket(tree, "Material", "MATERIAL")
    builder.add_socket(tree, "Density", "FLOAT", default=800.0)
    builder.add_socket(tree, "Geometry", "GEOMETRY", "OUTPUT")
    return tree


def _weights(ob, group):
    out = []
    for v in ob.data.vertices:
        out.append(next((g.weight for g in v.groups if g.group == group.index), None))
    return out


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------

OPERATORS = [
    "add_grass", "layer_add", "layer_duplicate", "layer_remove", "layer_move", "layer_solo", "paint", "paint_done",
    "subdivide_surface", "bake_scatter", "free_bake", "add_effector", "add_exclusion", "add_direction_empty",
    "quick_look", "sync_linked", "upgrade_layer",
]


@pytest.mark.parametrize("name", OPERATORS)
def test_operator_is_registered_with_undo(name):
    op = getattr(bpy.ops.swayfield, name)
    props = op.get_rna_type()
    assert props.name
    assert props.description, f"{name} needs a tooltip"


def test_operator_flags():
    from swayfield import operators
    from swayfield.operators import add_grass as ag, bake, effectors, layers as layer_ops, paint, scene

    for module in (ag, bake, effectors, layer_ops, paint, scene):
        for cls in module.classes:
            assert cls.bl_options == {"REGISTER", "UNDO"}, cls.__name__
            assert cls.bl_idname.startswith("swayfield.")
    assert operators._registered


def test_unregister_and_register_again(addon):
    addon.unregister()
    assert not hasattr(bpy.types.Object, "swayfield")
    assert not hasattr(bpy.types, "SWAYFIELD_OT_add_grass")
    assert not bpy.app.timers.is_registered(drivers._watch_cameras)
    addon.register()
    assert hasattr(bpy.types.Object, "swayfield")
    assert hasattr(bpy.types, "SWAYFIELD_OT_add_grass")
    assert bpy.app.timers.is_registered(drivers._watch_cameras)


# ---------------------------------------------------------------------------
# add_grass
# ---------------------------------------------------------------------------

def test_add_grass_needs_a_mesh(scene):
    with pytest.raises(RuntimeError, match="Select a mesh object first"):
        bpy.ops.swayfield.add_grass()
    bpy.ops.object.empty_add()
    with pytest.raises(RuntimeError, match="Select a mesh object first"):
        bpy.ops.swayfield.add_grass()


def test_add_grass_creates_a_layer_with_a_preset(plane):
    assert bpy.ops.swayfield.add_grass(preset="LAWN", layer_name="Base Grass") == {"FINISHED"}
    layer = plane.swayfield.layers[0]
    mod = layers.get_modifier(plane, layer)
    assert layer.name == "Base Grass" and layer.preset == "LAWN"
    assert layers.is_swayfield_modifier(mod)
    add_grass.flush_density_preview()
    assert layers.preset_label(plane, layer) != "Custom"
    inputs = _preset("LAWN")["inputs"]
    assert compat.get_input(mod, "length_max") == pytest.approx(inputs["length_max"])


def test_add_grass_default_preset_is_rolling_meadow(plane):
    bpy.ops.swayfield.add_grass()
    assert plane.swayfield.layers[0].preset == "ROLLING_MEADOW"


def test_add_grass_makes_a_hair_object_and_leaves_the_surface_modifiers(plane):
    plane.modifiers.new("Subdivision", "SUBSURF")
    bpy.ops.swayfield.add_grass()
    grass = plane.swayfield.layers[0].grass_object
    assert grass.type == "CURVES" and grass.parent == plane
    assert [m.type for m in plane.modifiers] == ["SUBSURF"]
    assert layers.is_swayfield_modifier(grass.modifiers[0])
    assert not grass.select_get(), "hide_select keeps the grass out of the selection"


def test_add_grass_ignores_grass_objects(plane):
    bpy.ops.swayfield.add_grass()
    grass = plane.swayfield.layers[0].grass_object
    grass.hide_select = False
    grass.select_set(True)
    bpy.ops.swayfield.add_grass()
    assert len(plane.swayfield.layers) == 2 and not grass.swayfield.layers


def test_add_grass_first_evaluation_is_light(plane):
    bpy.ops.swayfield.add_grass()
    mod = _mod(plane)
    assert bool(compat.get_input(mod, "optimised")) is True
    assert compat.get_input(mod, "viewport_density") == pytest.approx(10.0)
    assert compat.get_input(mod, "display_mode") == 2, "Points"
    assert add_grass._pending, "a restore is waiting for the timer"
    assert bpy.app.timers.is_registered(add_grass.flush_density_preview)
    bpy.app.timers.unregister(add_grass.flush_density_preview)


def test_add_grass_first_evaluation_shows_points(scene, camera):
    small = _grid("Small", size=2.0, cuts=8)
    bpy.ops.swayfield.add_grass(preset="LAWN")
    grass = small.swayfield.layers[0].grass_object
    from conftest import evaluated
    geometry = evaluated(grass).evaluated_geometry()
    assert geometry.pointcloud is not None and len(geometry.pointcloud.points) > 0
    assert geometry.curves is None or len(geometry.curves.curves) == 0
    bpy.app.timers.unregister(add_grass.flush_density_preview)
    add_grass.flush_density_preview()
    geometry = evaluated(grass).evaluated_geometry()
    assert geometry.curves is not None and len(geometry.curves.curves) > 0


def test_add_grass_ramps_up_on_a_small_surface(plane):
    bpy.ops.swayfield.add_grass(preset="WILD_FIELD")
    add_grass.flush_density_preview()
    mod = _mod(plane)
    data = _preset("WILD_FIELD")
    expected = data.get("inputs", {}).get("viewport_density", spec.get("viewport_density").default)
    assert compat.get_input(mod, "display_mode") == 0, "Full"
    assert compat.get_input(mod, "viewport_density") == pytest.approx(expected)
    # 100 m2 of wild field is far below the auto-optimise threshold.
    assert bool(compat.get_input(mod, "optimised")) is False
    assert not add_grass._pending


def test_add_grass_keeps_optimised_mode_on_a_huge_surface(scene):
    big = _grid("Big", size=40.0, cuts=4)
    bpy.ops.swayfield.add_grass(preset="LAWN")
    mod = _mod(big)
    density = _preset("LAWN")["inputs"]["density"]
    assert compat.get_input(mod, "density") < density / 10, "the first pass is much lighter on a huge surface"
    add_grass.flush_density_preview()
    assert compat.get_input(mod, "density") == pytest.approx(density)
    assert bool(compat.get_input(mod, "optimised")) is True
    assert compat.get_input(mod, "display_mode") == 0


def test_add_grass_over_budget_keeps_optimised_mode(plane, scene):
    scene.swayfield.budget = 1000
    bpy.ops.swayfield.add_grass(preset="LAWN")
    add_grass.flush_density_preview()
    assert bool(compat.get_input(_mod(plane), "optimised")) is True


def test_add_grass_on_several_objects_shares_a_link_id(scene):
    a = _grid("A")
    b = _grid("B", location=(20.0, 0.0, 0.0))
    c = _grid("C", location=(40.0, 0.0, 0.0))
    _select(a, b, c)
    bpy.ops.swayfield.add_grass(preset="WILD_FIELD")
    add_grass.flush_density_preview()
    seeds, links = [], set()
    for ob in (a, b, c):
        layer = ob.swayfield.layers[0]
        seeds.append(compat.get_input(layers.get_modifier(ob, layer), "seed_offset"))
        links.add(layer.link_id)
        assert layer.preset == "WILD_FIELD"
    assert sorted(seeds) == [0, 9973, 2 * 9973]
    assert len(links) == 1 and "" not in links


def test_add_grass_ignores_unselected_and_effector_objects(scene):
    a = _grid("A")
    b = _grid("B")
    _select(a)
    bpy.ops.swayfield.add_grass()
    assert len(a.swayfield.layers) == 1 and len(b.swayfield.layers) == 0


def test_add_grass_twice_adds_a_second_layer(plane):
    bpy.ops.swayfield.add_grass()
    bpy.ops.swayfield.add_grass()
    assert [layer.name for layer in plane.swayfield.layers] == ["Base Grass", "Base Grass 2"]


# ---------------------------------------------------------------------------
# layers
# ---------------------------------------------------------------------------

def test_layer_add_duplicate_remove(plane):
    bpy.ops.swayfield.layer_add(layer_name="Tall Wisps")
    bpy.ops.swayfield.layer_add(layer_name="Flowers")
    assert [layer.name for layer in plane.swayfield.layers] == ["Tall Wisps", "Flowers"]
    seeds = [compat.get_input(_mod(plane, i), "seed_offset") for i in range(2)]
    assert seeds[0] != seeds[1], "layers must not share root positions"

    bpy.ops.swayfield.layer_duplicate()
    assert [layer.name for layer in plane.swayfield.layers][-1] == "Flowers Copy"
    assert plane.swayfield.active_layer_index == 2

    bpy.ops.swayfield.layer_remove()
    assert [layer.name for layer in plane.swayfield.layers] == ["Tall Wisps", "Flowers"]
    assert len(_grass_objects()) == 2
    bpy.ops.swayfield.layer_remove(index=0)
    assert [layer.name for layer in plane.swayfield.layers] == ["Flowers"]
    assert plane.swayfield.active_layer_index == 0


def test_layer_remove_deletes_modifier_and_unused_material(plane):
    bpy.ops.swayfield.layer_add(layer_name="Only")
    name = layers.layer_material(plane, plane.swayfield.layers[0]).name
    bpy.ops.swayfield.layer_remove()
    assert not _grass_objects() and not bpy.data.hair_curves
    assert name not in bpy.data.materials


def test_layer_operators_need_a_layer(plane):
    for name in ("layer_duplicate", "layer_remove", "layer_move", "layer_solo", "upgrade_layer", "paint",
                 "add_exclusion", "add_direction_empty", "sync_linked"):
        with pytest.raises(RuntimeError):
            getattr(bpy.ops.swayfield, name)()


def test_layer_move_reorders_the_list(plane):
    for name in ("A", "B", "C"):
        bpy.ops.swayfield.layer_add(layer_name=name)

    def order():
        return [layer.name for layer in plane.swayfield.layers]

    grass = {layer.name: layer.grass_object for layer in plane.swayfield.layers}
    assert order() == ["A", "B", "C"]
    bpy.ops.swayfield.layer_move(direction="UP")
    assert order() == ["A", "C", "B"]
    assert plane.swayfield.layers[plane.swayfield.active_layer_index].name == "C"
    bpy.ops.swayfield.layer_move(direction="UP")
    assert order() == ["C", "A", "B"]
    assert bpy.ops.swayfield.layer_move(direction="UP") == {"CANCELLED"}
    bpy.ops.swayfield.layer_move(direction="DOWN")
    assert order() == ["A", "C", "B"]
    assert {layer.name: layer.grass_object for layer in plane.swayfield.layers} == grass
    assert all(layers.get_modifier(plane, layer) is not None for layer in plane.swayfield.layers)


def test_operators_work_with_the_grass_object_active(plane):
    bpy.ops.swayfield.layer_add(layer_name="A")
    grass = plane.swayfield.layers[0].grass_object
    _select(plane)
    grass.hide_select = False
    _select(grass)
    assert bpy.context.active_object == grass
    bpy.ops.swayfield.layer_duplicate()
    assert [layer.name for layer in plane.swayfield.layers] == ["A", "A Copy"]
    assert len(_grass_objects()) == 2
    bpy.ops.swayfield.layer_remove()
    assert len(_grass_objects()) == 1


def test_layer_solo_toggles(plane):
    for name in ("A", "B", "C"):
        bpy.ops.swayfield.layer_add(layer_name=name)
    mods = [_mod(plane, i) for i in range(3)]
    mods[2].show_viewport = False  # hidden by the user before soloing

    bpy.ops.swayfield.layer_solo(index=1)
    assert [m.show_viewport for m in mods] == [False, True, False]
    assert plane.swayfield.layers[1].solo
    bpy.ops.swayfield.layer_solo(index=1)
    assert [m.show_viewport for m in mods] == [True, True, False], "back to the state before solo"
    assert not plane.swayfield.layers[1].solo

    bpy.ops.swayfield.layer_solo(index=0)
    bpy.ops.swayfield.layer_solo(index=1)  # switching solo to another layer
    assert [m.show_viewport for m in mods] == [False, True, False]
    assert [layer.solo for layer in plane.swayfield.layers] == [False, True, False]


def test_upgrade_layer_operator(plane, camera):
    _select(plane)
    bpy.ops.swayfield.layer_add(layer_name="Old")
    mod = _mod(plane)
    with pytest.raises(RuntimeError):
        bpy.ops.swayfield.upgrade_layer()  # already current: poll fails
    mod.node_group = _make_v0_group()
    compat.set_input(mod, "Density", 55.0)
    assert versioning.needs_upgrade(mod)
    assert bpy.ops.swayfield.upgrade_layer() == {"FINISHED"}
    assert mod.node_group.name == versioning.CURRENT_MAIN
    assert compat.get_input(mod, "density") == pytest.approx(55.0)
    assert compat.get_input(mod, "surface") == plane


def test_sync_linked(scene):
    a = _grid("A")
    b = _grid("B", location=(20.0, 0.0, 0.0))
    _select(a, b, active=a)
    bpy.ops.swayfield.add_grass(preset="LAWN")
    add_grass.flush_density_preview()
    mod_a, mod_b = _mod(a), _mod(b)
    seed_b = compat.get_input(mod_b, "seed_offset")
    compat.set_input(mod_a, "density", 1234.0)
    compat.set_input(mod_a, "blade_source", 1)
    compat.set_input(mod_a, "density_group", "OnlyOnA")
    _select(a)
    assert bpy.ops.swayfield.sync_linked() == {"FINISHED"}
    assert compat.get_input(mod_b, "density") == pytest.approx(1234.0)
    assert compat.get_input(mod_b, "blade_source") == 1
    assert compat.get_input(mod_b, "seed_offset") == seed_b, "each object keeps its own seed"
    assert compat.get_input(mod_b, "density_group") == "", "vertex groups are per object"
    assert b.swayfield.layers[0].preset == a.swayfield.layers[0].preset


def test_sync_linked_needs_a_link(plane):
    bpy.ops.swayfield.layer_add()
    with pytest.raises(RuntimeError):
        bpy.ops.swayfield.sync_linked()


# ---------------------------------------------------------------------------
# painting
# ---------------------------------------------------------------------------

def test_paint_density_creates_group_and_enters_weight_paint(plane):
    bpy.ops.swayfield.layer_add(layer_name="Base Grass")
    mod = _mod(plane)
    assert bpy.ops.swayfield.paint(map="DENSITY") == {"FINISHED"}
    group = plane.vertex_groups["SF_Base_Grass_density"]
    assert compat.get_input(mod, "density_group") == "SF_Base_Grass_density"
    assert plane.vertex_groups.active == group
    weights = _weights(plane, group)
    assert len(weights) == len(plane.data.vertices) and set(weights) == {1.0}
    assert plane.mode == "WEIGHT_PAINT"
    assert bpy.ops.swayfield.paint_done() == {"FINISHED"}
    assert plane.mode == "OBJECT"


def test_paint_with_the_grass_object_active_makes_the_surface_active(plane):
    bpy.ops.swayfield.layer_add(layer_name="Base Grass")
    grass = plane.swayfield.layers[0].grass_object
    grass.hide_select = False
    _select(grass)
    assert bpy.ops.swayfield.paint(map="DENSITY") == {"FINISHED"}
    assert bpy.context.active_object == plane and plane.mode == "WEIGHT_PAINT"
    assert "SF_Base_Grass_density" in plane.vertex_groups
    assert bpy.ops.swayfield.paint_done() == {"FINISHED"}
    assert plane.mode == "OBJECT"


@pytest.mark.parametrize("map_id,fill", [("LENGTH", 1.0), ("WIND", 1.0), ("VARIATION", 0.0)])
def test_paint_other_maps(plane, map_id, fill):
    bpy.ops.swayfield.layer_add(layer_name="Base Grass")
    bpy.ops.swayfield.paint(map=map_id)
    name = f"SF_Base_Grass_{map_id.lower()}"
    assert compat.get_input(_mod(plane), f"{map_id.lower()}_group") == name
    assert set(_weights(plane, plane.vertex_groups[name])) == {fill}
    bpy.ops.swayfield.paint_done()


def test_paint_reuses_an_existing_group(plane):
    bpy.ops.swayfield.layer_add(layer_name="Base Grass")
    bpy.ops.swayfield.paint(map="DENSITY")
    bpy.ops.swayfield.paint_done()
    group = plane.vertex_groups["SF_Base_Grass_density"]
    group.add([3], 0.25, "REPLACE")
    bpy.ops.swayfield.paint(map="DENSITY")
    bpy.ops.swayfield.paint_done()
    assert len(plane.vertex_groups) == 1
    assert _weights(plane, plane.vertex_groups[0])[3] == pytest.approx(0.25)


def test_paint_group_name_is_sanitised(plane):
    bpy.ops.swayfield.layer_add(layer_name="Tall / Wisps!")
    bpy.ops.swayfield.paint(map="LENGTH")
    assert "SF_Tall_Wisps_length" in plane.vertex_groups
    bpy.ops.swayfield.paint_done()


def test_paint_shows_points_in_optimised_mode(plane):
    bpy.ops.swayfield.layer_add(layer_name="Base Grass")
    mod = _mod(plane)
    compat.set_input(mod, "optimised", True)
    compat.set_input(mod, "display_mode", 1)  # Strands Lite
    bpy.ops.swayfield.paint(map="DENSITY")
    assert compat.get_input(mod, "display_mode") == 2
    bpy.ops.swayfield.paint(map="LENGTH")  # a second map must not forget the original display
    bpy.ops.swayfield.paint_done()
    assert compat.get_input(mod, "display_mode") == 1


def test_paint_leaves_display_alone_without_optimised_mode(plane):
    bpy.ops.swayfield.layer_add(layer_name="Base Grass")
    mod = _mod(plane)
    bpy.ops.swayfield.paint(map="DENSITY")
    assert compat.get_input(mod, "display_mode") == 0
    bpy.ops.swayfield.paint_done()
    assert compat.get_input(mod, "display_mode") == 0


def test_group_name_helper():
    from swayfield.operators.paint import group_name
    assert group_name("Base Grass", "DENSITY") == "SF_Base_Grass_density"
    assert group_name("!!!", "WIND") == "SF_Layer_wind"


def test_subdivide_surface(scene):
    ob = _grid("Coarse", size=20.0, cuts=4)
    bpy.ops.swayfield.layer_add()
    group = ob.vertex_groups.new(name="Keep")
    group.add(list(range(len(ob.data.vertices))), 0.5, "REPLACE")
    before = len(ob.data.vertices)
    assert layers.surface_too_coarse(ob)
    assert bpy.ops.swayfield.subdivide_surface() == {"FINISHED"}
    assert len(ob.data.vertices) > before * 10
    assert not layers.surface_too_coarse(ob)
    assert layers.mean_edge_length(ob) <= 0.26
    assert "Keep" in ob.vertex_groups
    assert set(_weights(ob, ob.vertex_groups["Keep"])) == {0.5}


def test_subdivide_surface_is_capped(scene, monkeypatch):
    from swayfield.operators import paint
    ob = _grid("Huge", size=1000.0, cuts=100)
    monkeypatch.setattr(paint, "MAX_VERTICES", 250_000)
    cuts = paint.cuts_for(ob)
    assert 0 < cuts < 5
    assert len(ob.data.vertices) * (cuts + 1) ** 2 <= 250_000


def test_subdivide_surface_leaves_fine_meshes_alone(scene):
    ob = _grid("Fine", size=10.0, cuts=100)
    before = len(ob.data.vertices)
    assert bpy.ops.swayfield.subdivide_surface() == {"CANCELLED"}
    assert len(ob.data.vertices) == before


# ---------------------------------------------------------------------------
# bake
# ---------------------------------------------------------------------------

def test_bake_reports_a_missing_bake_node(plane):
    bpy.ops.swayfield.layer_add()
    mod = _mod(plane)
    node = mod.node_group.nodes.get("SF_Bake")
    old_name = node.name
    node.name = "Renamed"
    try:
        for name in ("bake_scatter", "free_bake"):
            with pytest.raises(RuntimeError, match="no scatter bake node"):
                getattr(bpy.ops.swayfield, name)()
    finally:
        node.name = old_name


def test_bake_and_free(plane, camera):
    from swayfield.operators import bake
    _select(plane)
    bpy.ops.swayfield.layer_add()
    mod = _mod(plane)
    assert bake.find_bake_id(mod) == mod.bakes[0].bake_id
    assert mod.id_data.session_uid != plane.session_uid
    assert bpy.ops.swayfield.bake_scatter() == {"FINISHED"}
    assert bpy.ops.swayfield.free_bake() == {"FINISHED"}


def _optimised_layer(plane):
    _select(plane)
    bpy.ops.swayfield.layer_add()
    mod = _mod(plane)
    compat.set_input(mod, "optimised", True)
    compat.set_input(mod, "viewport_density", 20.0)
    return mod


def test_bake_holds_optimised_and_simplify_off_then_restores(plane, camera, monkeypatch):
    from swayfield.operators import bake
    mod = _optimised_layer(plane)
    bpy.context.scene.render.use_simplify = True
    bpy.context.scene.render.simplify_child_particles = 0.3
    bpy.context.view_layer.update()
    assert compat.get_input(mod, "simplify") == pytest.approx(0.3)
    seen = {}

    def fake(context, grass, modifier, bake_id):
        seen["optimised"] = bool(compat.get_input(modifier, "optimised"))
        seen["simplify"] = compat.get_input(modifier, "simplify")
        bpy.context.view_layer.update()  # the driver must not pull the value back
        seen["simplify_after_update"] = compat.get_input(modifier, "simplify")
        return {"FINISHED"}

    monkeypatch.setattr(bake, "run_bake", fake)
    assert bpy.ops.swayfield.bake_scatter() == {"FINISHED"}
    assert seen == {"optimised": False, "simplify": 1.0, "simplify_after_update": 1.0}
    assert bool(compat.get_input(mod, "optimised")) is True
    assert compat.get_input(mod, "simplify") == pytest.approx(0.3)
    driver = [f for f in mod.id_data.animation_data.drivers
              if f.data_path == compat.input_data_path(mod, "simplify")][0]
    assert not driver.mute
    bpy.context.view_layer.update()
    assert compat.get_input(mod, "simplify") == pytest.approx(0.3), "the driver works again"


@pytest.mark.parametrize("failure", ["error", "cancelled"])
def test_bake_restores_inputs_when_the_bake_fails(plane, camera, monkeypatch, failure):
    from swayfield.operators import bake
    mod = _optimised_layer(plane)
    bpy.context.scene.render.use_simplify = True
    bpy.context.scene.render.simplify_child_particles = 0.5
    bpy.context.view_layer.update()
    assert compat.get_input(mod, "simplify") == pytest.approx(0.5)

    def fake(context, grass, modifier, bake_id):
        if failure == "error":
            raise RuntimeError("bake failed")
        return {"CANCELLED"}

    monkeypatch.setattr(bake, "run_bake", fake)
    with pytest.raises(RuntimeError, match="did not run"):
        bpy.ops.swayfield.bake_scatter()
    assert bool(compat.get_input(mod, "optimised")) is True
    assert compat.get_input(mod, "simplify") == pytest.approx(0.5)
    bpy.context.view_layer.update()
    assert compat.get_input(mod, "simplify") == pytest.approx(0.5)
    assert not [f for f in mod.id_data.animation_data.drivers if f.mute]


def test_real_bake_restores_inputs(plane, camera):
    mod = _optimised_layer(plane)
    try:
        result = bpy.ops.swayfield.bake_scatter()
    except RuntimeError as err:
        pytest.skip(f"the bake cannot run headless here: {err}")
    assert result == {"FINISHED"}
    assert bool(compat.get_input(mod, "optimised")) is True
    assert compat.get_input(mod, "viewport_density") == pytest.approx(20.0)
    bpy.ops.swayfield.free_bake()


def test_bake_works_with_the_grass_object_active(plane, camera):
    _select(plane)
    bpy.ops.swayfield.layer_add()
    grass = plane.swayfield.layers[0].grass_object
    grass.hide_select = False
    _select(grass)
    assert bpy.ops.swayfield.bake_scatter() == {"FINISHED"}
    assert bpy.ops.swayfield.free_bake() == {"FINISHED"}


# ---------------------------------------------------------------------------
# effectors, exclusion, direction
# ---------------------------------------------------------------------------

@pytest.fixture
def effector_ready():
    try:
        nodes.ensure("effector_point")
    except ImportError:
        pytest.skip("the effector_point group is not available yet")


TYPE_VALUES = {"VORTEX": 0, "RADIAL_BLAST": 1, "TRAMPLE": 2, "SHELTER": 3}


@pytest.mark.parametrize("kind", list(TYPE_VALUES))
def test_add_effector(plane, effector_ready, kind):
    bpy.ops.swayfield.layer_add()
    bpy.context.scene.cursor.location = (1.0, 2.0, 0.5)
    assert bpy.ops.swayfield.add_effector(type=kind, pulse=False) == {"FINISHED"}
    ob = bpy.data.objects[{"VORTEX": "SF_Vortex", "RADIAL_BLAST": "SF_Radial_Blast", "TRAMPLE": "SF_Trample",
                           "SHELTER": "SF_Shelter"}[kind]]
    assert len(ob.data.vertices) == 1 and not ob.data.edges
    assert tuple(ob.location) == pytest.approx((1.0, 2.0, 0.5))
    assert [c.name for c in ob.users_collection] == ["SF_Effectors"]
    mod = ob.modifiers[0]
    assert mod.node_group.name.startswith("SF_EffectorPoint")
    assert compat.get_input(mod, "Type") == TYPE_VALUES[kind]
    assert ob["sf_effector_type"] == kind
    coll = compat.get_input(_mod(plane), "effector_collection")
    assert coll is not None and coll.name == "SF_Effectors" and ob.name in coll.objects
    assert not ob.animation_data, "no pulse requested"


def test_effectors_point_the_active_layer_at_the_collection(plane, effector_ready):
    bpy.ops.swayfield.layer_add()
    mod = _mod(plane)
    compat.set_input(mod, "effector_collection", None)
    bpy.ops.swayfield.add_effector(type="TRAMPLE")
    assert compat.get_input(mod, "effector_collection").name == "SF_Effectors"


def test_add_effector_without_a_surface(scene, effector_ready):
    assert bpy.ops.swayfield.add_effector(type="VORTEX") == {"FINISHED"}
    assert bpy.data.collections["SF_Effectors"].objects[0].name == "SF_Vortex"
    assert "SF_Effectors" in scene.collection.children


def test_radial_blast_pulse(plane, effector_ready):
    bpy.ops.swayfield.layer_add()
    scene = bpy.context.scene
    scene.frame_set(10)
    bpy.ops.swayfield.add_effector(type="RADIAL_BLAST", pulse=True)
    ob = bpy.data.objects["SF_Radial_Blast"]
    mod = ob.modifiers[0]
    assert ob.animation_data and ob.animation_data.action
    for frame, expected in ((10, 0.0), (22, 1.0), (34, 0.0), (16, 0.5)):
        scene.frame_set(frame)
        assert compat.get_input(mod, "Strength") == pytest.approx(expected, abs=0.1), frame


def test_other_effectors_do_not_pulse(plane, effector_ready):
    bpy.ops.swayfield.layer_add()
    bpy.ops.swayfield.add_effector(type="VORTEX", pulse=True)
    assert not bpy.data.objects["SF_Vortex"].animation_data


def test_add_exclusion(plane):
    bpy.ops.swayfield.layer_add(layer_name="Base Grass")
    bpy.ops.mesh.primitive_cube_add(location=(2, 2, 0))
    rock = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(location=(-2, 2, 0))
    path = bpy.context.active_object
    _select(rock, path, plane, active=plane)
    assert bpy.ops.swayfield.add_exclusion() == {"FINISHED"}
    coll = compat.get_input(_mod(plane), "exclusion_collection")
    assert coll.name == "SF_Exclude_Ground_Base Grass"
    assert {o.name for o in coll.objects} == {rock.name, path.name}
    assert coll not in list(bpy.context.scene.collection.children_recursive)
    assert coll.name in bpy.data.collections

    # A second call reuses the collection.
    bpy.ops.mesh.primitive_cube_add(location=(0, -2, 0))
    tree = bpy.context.active_object
    _select(tree, plane, active=plane)
    bpy.ops.swayfield.add_exclusion()
    assert compat.get_input(_mod(plane), "exclusion_collection") == coll
    assert tree.name in coll.objects
    assert len([c for c in bpy.data.collections if c.name.startswith("SF_Exclude")]) == 1


def test_add_exclusion_needs_other_objects(plane):
    bpy.ops.swayfield.layer_add()
    _select(plane)
    with pytest.raises(RuntimeError, match="Select the objects"):
        bpy.ops.swayfield.add_exclusion()


def test_add_direction_empty(plane):
    bpy.ops.swayfield.layer_add()
    mod = _mod(plane)
    compat.set_input(mod, "direction", math.radians(90))
    assert bpy.ops.swayfield.add_direction_empty() == {"FINISHED"}
    empty = compat.get_input(mod, "direction_object")
    assert empty is not None and empty.name == "SF_Wind_Direction"
    assert empty.type == "EMPTY" and empty.empty_display_type == "PLAIN_AXES"
    assert empty.location.z > 0.5
    assert empty.rotation_euler.z == pytest.approx(math.radians(90))
    assert (empty.matrix_world.to_3x3() @ Vector((1, 0, 0))).y == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# quick look
# ---------------------------------------------------------------------------

def test_quick_look(plane):
    bpy.ops.swayfield.layer_add()
    scene = bpy.context.scene
    assert bpy.ops.swayfield.quick_look() == {"FINISHED"}
    cam = scene.camera
    assert cam is not None and cam.name == "SF_Quick_Look_Camera"
    assert cam.location.y == pytest.approx(-5.0, abs=0.3), "at the edge of the surface"
    assert cam.location.z == pytest.approx(1.0, abs=0.05), "1 m above the surface"
    # Looks along +Y, level.
    forward = cam.matrix_world.to_quaternion() @ Vector((0, 0, -1))
    assert forward.y > 0.95
    sun = bpy.data.objects["SF_Quick_Look_Sun"]
    assert sun.data.type == "SUN"
    assert sun.data.energy == pytest.approx(4.0)
    assert sun.data.angle == pytest.approx(math.radians(3.0))
    assert sun.data.color[0] > sun.data.color[2], "warm"
    assert scene.view_settings.view_transform == "AgX"
    assert "Punchy" in scene.view_settings.look
    assert scene.world is not None


def test_quick_look_twice_does_not_duplicate(plane):
    bpy.ops.swayfield.layer_add()
    bpy.ops.swayfield.quick_look()
    bpy.ops.swayfield.quick_look()
    assert len([o for o in bpy.data.objects if o.name.startswith("SF_Quick_Look")]) == 2


def test_quick_look_feeds_the_camera_drivers(plane):
    bpy.ops.swayfield.layer_add()
    mod = _mod(plane)
    assert compat.get_input(mod, "cam_focal_length") == pytest.approx(50.0)
    bpy.ops.swayfield.quick_look()
    bpy.context.view_layer.update()
    assert compat.get_input(mod, "cam_focal_length") == pytest.approx(35.0)


def test_quick_look_needs_a_mesh(scene):
    with pytest.raises(RuntimeError):
        bpy.ops.swayfield.quick_look()
