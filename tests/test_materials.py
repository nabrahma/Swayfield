# SPDX-License-Identifier: GPL-3.0-or-later
import os

import bpy
import pytest
from conftest import evaluated

from swayfield.core import materials, spec
from swayfield.core.nodes import builder, store
from swayfield.core.nodes.builder import NodeBuilder, add_socket

# ---------------------------------------------------------------------------
# Material
# ---------------------------------------------------------------------------

def test_material_builds_with_all_controls(scene):
    mat = materials.create_layer_material("Grass")
    assert materials.is_swayfield_material(mat)
    assert set(materials.CONTROLS) == set(materials.CONTROL_INFO)
    for key in materials.CONTROLS:
        value = materials.get_control(mat, key)
        label, kind, mode = materials.CONTROL_INFO[key]
        assert kind in {"COLOR", "FACTOR", "FLOAT", "DISTANCE"}
        assert mode in (None, 0, 1, 2)
        assert len(value) == 4 if kind == "COLOR" else isinstance(value, float)
    for slot in materials.IMAGE_SLOTS:
        assert mat.node_tree.nodes[f"SF_Image_{slot}"].bl_idname == "ShaderNodeTexImage"
    assert materials.get_mode(mat) == materials.MODE_PROCEDURAL
    assert materials.get_control(mat, "roughness") == pytest.approx(0.45)
    assert materials.get_control(mat, "translucency") == pytest.approx(0.2)
    assert materials.linear_to_hex(materials.get_control(mat, "color_root")) == "#0B3A05"
    assert materials.linear_to_hex(materials.get_control(mat, "color_haze")) == "#5E8F31"
    assert len(materials.MODE_ITEMS) == 3
    if hasattr(mat, "surface_render_method"):
        assert mat.surface_render_method == "DITHERED"
    assert not materials.has_opacity(mat)


def test_shader_reads_blade_attributes(scene):
    mat = materials.create_layer_material("Grass")
    names = {n.attribute_name for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeAttribute"}
    assert {spec.ATTR_FACTOR, spec.ATTR_RANDOM, spec.ATTR_WIND, spec.ATTR_VARIATION, spec.ATTR_DIST} <= names
    out = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
    assert out.inputs["Surface"].is_linked


def test_switching_mode_keeps_settings(scene):
    mat = materials.create_layer_material("Grass")
    materials.set_control(mat, "color_tip", "#FF0000")
    materials.set_control(mat, "single_roughness", 0.8)
    materials.set_control(mat, "image_tint", 0.25)
    for mode in (materials.MODE_SINGLE, materials.MODE_IMAGE, materials.MODE_PROCEDURAL):
        materials.set_mode(mat, mode)
        assert materials.get_mode(mat) == mode
        assert materials.get_control(mat, "color_tip")[:3] == pytest.approx((1.0, 0.0, 0.0))
        assert materials.get_control(mat, "single_roughness") == pytest.approx(0.8)
        assert materials.get_control(mat, "image_tint") == pytest.approx(0.25)
    with pytest.raises(ValueError):
        materials.set_mode(mat, 5)


def test_colour_conversion(scene):
    assert materials.hex_to_linear("#808080") == pytest.approx((0.2159,) * 3, abs=1e-4)
    assert materials.hex_to_linear("#000000") == (0.0, 0.0, 0.0)
    assert materials.hex_to_linear("ffffff") == pytest.approx((1.0, 1.0, 1.0))
    mat = materials.create_layer_material("Grass")
    materials.set_control(mat, "single_color", "#808080")
    assert materials.get_control(mat, "single_color") == pytest.approx((0.2159, 0.2159, 0.2159, 1.0), abs=1e-4)
    materials.set_control(mat, "single_color", (0.1, 0.2, 0.3))
    assert materials.get_control(mat, "single_color") == pytest.approx((0.1, 0.2, 0.3, 1.0))
    materials.set_control(mat, "color_mid", (0.1, 0.2, 0.3, 1.0))
    assert materials.linear_to_hex((0.2159, 0.2159, 0.2159)) == "#808080"


def _write_png(path: str) -> None:
    img = bpy.data.images.new("tmp", 4, 4)
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


@pytest.mark.parametrize("name, slot", [
    ("grass_ALBEDO.png", "BaseColor"), ("Grass_Diffuse.JPG", "BaseColor"), ("g_base_color.tif", "BaseColor"),
    ("g_col.png", "BaseColor"), ("g_Rough.png", "Roughness"), ("g_NRM.png", "Normal"), ("g_nor.png", "Normal"),
    ("g_normal_dx.png", "Normal"), ("g_Mask.png", "Opacity"), ("g_SSS.exr", "Translucency"),
    ("g_occlusion.png", "AO"), ("g_ao.png", "AO"), ("g_albedo.txt", None), ("readme.png", None),
])
def test_suffix_matching(name, slot):
    assert materials.match_slot(name) == slot


def test_load_texture_set(scene, tmp_path):
    files = {
        "Blade_BaseColor.png": "BaseColor", "Blade_ROUGHNESS.png": "Roughness", "blade_Nrm.PNG": "Normal",
        "blade_alpha.png": "Opacity", "blade_Trans.png": "Translucency", "blade_AO.png": "AO",
    }
    for name in files:
        _write_png(str(tmp_path / name))
    _write_png(str(tmp_path / "unrelated.png"))
    mat = materials.create_layer_material("Grass")
    loaded = materials.load_texture_set(mat, str(tmp_path))
    assert {slot: os.path.basename(path) for slot, path in loaded.items()} == {v: k for k, v in files.items()}
    for slot in materials.IMAGE_SLOTS:
        image = mat.node_tree.nodes[f"SF_Image_{slot}"].image
        assert image is not None
        assert mat.node_tree.nodes[f"SF_Has_{slot}"].outputs[0].default_value == 1.0
        if slot != "BaseColor":
            assert image.colorspace_settings.name == "Non-Color"
    assert materials.has_opacity(mat)
    materials.assign_image(mat, "Opacity", None)
    assert not materials.has_opacity(mat)
    assert mat.node_tree.nodes["SF_Has_Opacity"].outputs[0].default_value == 0.0


def test_mask_preview_material(scene):
    mat = materials.ensure_mask_preview_material()
    assert mat.name == "SF_MaskPreview"
    assert materials.ensure_mask_preview_material() == mat
    assert not materials.is_swayfield_material(mat)
    attrs = [n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeAttribute"]
    assert [n.attribute_name for n in attrs] == [spec.ATTR_MASK]
    assert any(n.bl_idname == "ShaderNodeEmission" for n in mat.node_tree.nodes)


# ---------------------------------------------------------------------------
# SF_Store_v1
# ---------------------------------------------------------------------------

BLADES = 3
POINTS = 6


def _store_object(blade_source: int, *, override: bool = False, instances: bool = False, as_mesh: bool = False):
    """An object whose modifier fabricates bent blades and feeds them through SF_Store_v1."""
    store_tree = builder.ensure_group(store.NAME)
    builder.clear_tree(store_tree)
    store.build(store_tree)

    tree = bpy.data.node_groups.new("SF_TestStore", "GeometryNodeTree")
    add_socket(tree, "Geometry", "GEOMETRY", "OUTPUT")
    b = NodeBuilder(tree)
    points = b.out("GeometryNodeMeshToPoints", {
        "Mesh": b.out("GeometryNodeMeshLine", {"Count": BLADES, "Offset": (1.0, 0.0, 0.0)})})
    if instances:
        blades = b.out("GeometryNodeInstanceOnPoints", {"Points": points, "Instance": b.out("GeometryNodeMeshCube")})
    else:
        bezier = b.out("GeometryNodeCurveQuadraticBezier", {
            "Start": (0.0, 0.0, 0.0), "Middle": (0.0, 0.0, 0.5), "End": (0.4, 0.0, 0.8), "Resolution": POINTS - 1})
        blades = b.out("GeometryNodeRealizeInstances", {
            "Geometry": b.out("GeometryNodeInstanceOnPoints", {"Points": points, "Instance": bezier})})
        factor = b.out("GeometryNodeSplineParameter")
        blades = b.store(blades, spec.ATTR_FACTOR, factor)
        blades = b.store(blades, spec.ATTR_RANDOM, 0.25)
        blades = b.store(blades, spec.ATTR_WIND, 0.5)
        blades = b.store(blades, spec.ATTR_UP, (0.0, 0.0, 1.0), data_type="FLOAT_VECTOR")
        radius = b.math("MULTIPLY", b.math("MULTIPLY_ADD", factor, -0.9, 1.0), 0.005)
        blades = b.out("GeometryNodeSetCurveRadius", {"Curve": blades, "Radius": radius})
    node = b.group(store_tree, {"Blades": blades, "Blade Source": blade_source,
                                "Override Instance Material": override}, forward=False)
    mat = materials.create_layer_material("Grass")
    node.inputs["Material"].default_value = mat
    grass = node.outputs["Grass"]
    if as_mesh:
        # Curves to a wire mesh, so the result (and its materials) can be inspected from Python.
        grass = b.out("GeometryNodeCurveToMesh", {"Curve": grass})
    b.output("Geometry", grass)

    ob = bpy.data.objects.new("Blades", bpy.data.meshes.new("Blades"))
    bpy.context.scene.collection.objects.link(ob)
    ob.modifiers.new("Store", "NODES").node_group = tree
    return ob, mat


def test_store_interface(scene):
    tree = builder.ensure_group(store.NAME)
    builder.clear_tree(tree)
    store.build(tree)
    items = [i for i in tree.interface.items_tree if i.item_type == "SOCKET"]
    inputs = {i.name for i in items if i.in_out == "INPUT"}
    assert {"Blades", "Blade Source", "Material", "Override Instance Material"} <= inputs
    assert [i.name for i in items if i.in_out == "OUTPUT"] == ["Grass"]


def test_store_ribbons(scene):
    ob, mat = _store_object(store.SOURCE_RIBBONS)
    mesh = evaluated(ob).to_mesh()
    assert len(mesh.polygons) == BLADES * (POINTS - 1)
    assert len(mesh.vertices) == BLADES * POINTS * 2
    uv = mesh.attributes.get("UVMap")
    assert uv is not None and uv.domain == "CORNER" and uv.data_type == "FLOAT2"
    assert ".sf_u" not in mesh.attributes
    for name in (spec.ATTR_FACTOR, spec.ATTR_RANDOM, spec.ATTR_WIND):
        assert name in mesh.attributes
    factor = mesh.attributes[spec.ATTR_FACTOR]
    us, vs = set(), []
    for loop in mesh.loops:
        u, v = uv.data[loop.index].vector
        us.add(round(u, 4))
        assert v == pytest.approx(factor.data[loop.vertex_index].value)
        vs.append(v)
    assert us == {0.0, 1.0}
    assert min(vs) == pytest.approx(0.0) and max(vs) == pytest.approx(1.0)
    assert [m.name for m in mesh.materials if m] == [mat.name]

    # Width at the root is 2 x radius, across the bend plane (Y); faces turn up where the blade bends over.
    co = [v.co for v in mesh.vertices]
    root = [c for c, f in zip(co, factor.data, strict=False) if f.value == 0.0][:2]
    assert (root[0] - root[1]).length == pytest.approx(0.01, abs=1e-4)
    assert abs((root[0] - root[1]).y) == pytest.approx(0.01, abs=1e-4)
    normals = [p.normal for p in mesh.polygons[:POINTS - 1]]
    assert abs(normals[0].z) < 0.5
    assert normals[-1].z > normals[0].z
    assert all(abs(n.y) < 1e-3 for n in normals)


def test_store_strands_stay_curves(scene):
    ob, _mat = _store_object(store.SOURCE_STRANDS)
    ev = evaluated(ob)
    kinds = {inst.object.type for inst in bpy.context.evaluated_depsgraph_get().object_instances
             if inst.is_instance and inst.parent and inst.parent.original == ob}
    assert kinds == {"CURVE"}
    assert len(ev.data.polygons) == 0

    # The same curves converted to a wire mesh afterwards: one edge chain per blade, material assigned.
    ob, mat = _store_object(store.SOURCE_STRANDS, as_mesh=True)
    mesh = evaluated(ob).to_mesh()
    assert len(mesh.polygons) == 0
    assert len(mesh.edges) == BLADES * (POINTS - 1)
    assert spec.ATTR_FACTOR in mesh.attributes
    assert [m.name for m in mesh.materials if m] == [mat.name]


@pytest.mark.parametrize("override", [False, True])
def test_store_instances(scene, override):
    ob, mat = _store_object(store.SOURCE_INSTANCES, override=override, instances=True)
    evaluated(ob)
    meshes = [inst.object.data for inst in bpy.context.evaluated_depsgraph_get().object_instances
              if inst.is_instance and inst.parent and inst.parent.original == ob]
    assert len(meshes) == BLADES
    has_mat = mat.name in [m.name for m in meshes[0].materials if m]
    assert has_mat == override


def test_wind_brightening_is_remapped(scene):
    """Only flattened blades glow: sf_wind goes through a smoothstep before the highlight lerp."""
    mat = materials.create_layer_material("Grass")
    assert materials.linear_to_hex(materials.get_control(mat, "color_highlight")) == "#C4F25A"
    remaps = [n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeMapRange"
              and n.interpolation_type == "SMOOTHSTEP"
              and any(link.from_node.bl_idname == "ShaderNodeAttribute"
                      and link.from_node.attribute_name == spec.ATTR_WIND for link in n.inputs[0].links)]
    assert len(remaps) == 1
    node = remaps[0]
    assert node.inputs["From Min"].default_value == pytest.approx(materials.WIND_CALM)
    assert node.inputs["From Max"].default_value == pytest.approx(materials.WIND_FLAT)
