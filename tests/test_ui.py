# SPDX-License-Identifier: GPL-3.0-or-later
"""UI tests: registration, panel polls, strings and icons."""

from __future__ import annotations

import bpy
import pytest

from swayfield import ui
from swayfield.core import nodes, spec
from swayfield.ui import icons, panels, strings


def _make_layer_legacy(ob):
    """Add a NODES modifier with SF_Main and a layer for it, or skip when props are missing."""
    if not hasattr(ob, "swayfield"):
        pytest.skip("props not available")
    mod = ob.modifiers.new("Swayfield", "NODES")
    mod.node_group = nodes.ensure("main")
    layer = ob.swayfield.layers.add()
    layer.name = "Base Grass"
    layer.modifier_name = mod.name
    ob.swayfield.active_layer_index = len(ob.swayfield.layers) - 1
    return layer, mod


def _activate(ob):
    bpy.context.view_layer.objects.active = ob


def test_classes_registered():
    for cls in ui.panels.CLASSES + ui.lists.CLASSES:
        assert cls.is_registered if hasattr(cls, "is_registered") else cls.bl_rna is not None
    assert hasattr(bpy.types.WindowManager, "swayfield_preset")


def test_register_cycle():
    ui.unregister()
    assert not hasattr(bpy.types.WindowManager, "swayfield_preset")
    ui.register()
    ui.unregister()
    ui.register()
    assert hasattr(bpy.types.WindowManager, "swayfield_preset")
    assert icons.is_loaded()


def test_poll_without_layer(plane):
    _activate(plane)
    assert panels.layer_state(bpy.context) is None
    assert panels.SWAYFIELD_PT_main.poll(bpy.context) if hasattr(panels.SWAYFIELD_PT_main, "poll") else True
    for cls in panels.CLASSES:
        poll = getattr(cls, "poll", None)
        if cls.__name__.startswith("SWAYFIELD_PT") and poll is not None:
            if cls is not panels.SWAYFIELD_PT_main:
                assert not poll(bpy.context), cls.__name__


def test_poll_non_mesh(scene):
    bpy.ops.object.empty_add()
    _activate(bpy.context.active_object)
    assert panels.layer_state(bpy.context) is None
    for cls in panels.CLASSES:
        poll = getattr(cls, "poll", None)
        if cls.__name__.startswith("SWAYFIELD_PT") and poll is not None and cls is not panels.SWAYFIELD_PT_main:
            assert not poll(bpy.context)


def test_poll_without_object(scene):
    _activate(None)
    assert panels.layer_state(bpy.context) is None


def test_poll_with_layer(plane):
    _make_layer_legacy(plane)
    _activate(plane)
    st = panels.layer_state(bpy.context)
    assert st is not None and st.mod is not None
    for cls in panels.CLASSES:
        if cls.__name__.startswith("SWAYFIELD_PT_") and cls.__name__ != "SWAYFIELD_PT_instances":
            poll = getattr(cls, "poll", None)
            if poll is not None:
                assert poll(bpy.context), cls.__name__
    # Custom Instances sub-panel stays hidden for the default blade source
    assert not [c for c in panels.CLASSES if c.__name__ == "SWAYFIELD_PT_instances"][0].poll(bpy.context)


def test_poll_modifier_deleted(plane):
    _make_layer_legacy(plane)
    plane.modifiers.remove(plane.modifiers["Swayfield"])
    _activate(plane)
    assert panels.layer_state(bpy.context) is None
    assert panels.layer_state(bpy.context, need_modifier=False) is not None
    assert panels.SWAYFIELD_PT_layers.poll(bpy.context)
    assert not panels.SWAYFIELD_PT_wind.poll(bpy.context)


def test_panel_keys_exist_in_spec():
    for cls in panels._SUB_PANELS:
        assert cls.bl_parent_id.startswith("SWAYFIELD_PT_")
    for _prefix, keys in panels.MASK_STACK:
        for key in keys:
            assert key in spec.BY_KEY
    for prefix, _map, _text in panels.PAINT_MAPS:
        assert f"{prefix}_group" in spec.BY_KEY


def test_strings_not_empty():
    values = {k: v for k, v in vars(strings).items() if k.isupper() and isinstance(v, str)}
    assert values
    for key, value in values.items():
        assert value.strip(), key


def test_icons_valid():
    valid = {item.identifier for item in
             bpy.types.UILayout.bl_rna.functions["operator"].parameters["icon"].enum_items}
    for name in icons.ALL_ICONS:
        assert name in valid, name


def test_icons_load_and_free():
    icons.load()
    assert icons.is_loaded()
    assert icons.icon_id("does-not-exist") == 0
    icons.free()
    assert not icons.is_loaded()
    icons.load()


def test_preset_items_fallback():
    items = ui._preset_items(None, bpy.context)
    assert items and all(len(item) == 5 for item in items)


# ---------------------------------------------------------------------------
# Real draw() calls against a recording layout
# ---------------------------------------------------------------------------


class FakeOperatorProps:
    """Operator pointer that rejects property names the real operator does not have."""

    def __init__(self, idname: str):
        object.__setattr__(self, "_idname", idname)
        rna = getattr(bpy.ops.swayfield, idname.split(".")[1]).get_rna_type()
        object.__setattr__(self, "_props", {p.identifier: p for p in rna.properties})

    def __setattr__(self, name, value):
        prop = self._props.get(name)
        assert prop is not None, f"{self._idname} has no property {name!r}"
        if prop.type == "ENUM":
            ids = {item.identifier for item in prop.enum_items} if not prop.is_enum_flag else None
            if ids is not None and ids:
                assert value in ids, f"{self._idname}.{name}: {value!r} not in {sorted(ids)}"


class FakeLayout:
    """Records calls; every container method returns the layout itself."""

    def __init__(self):
        self.calls: list = []
        self.alert = False
        self.active = True
        self.enabled = True
        self.operator_context = "INVOKE_DEFAULT"

    def operator(self, idname, text="", icon="NONE", **kw):
        assert icon in icons.ALL_ICONS or icon == "NONE", icon
        self.calls.append(("operator", idname))
        return FakeOperatorProps(idname)

    def prop(self, data, name, **kw):
        if not name.startswith("["):
            assert name in data.bl_rna.properties, f"{data!r} has no property {name!r}"
        self.calls.append(("prop", name))

    def label(self, text="", icon="NONE", **kw):
        assert text is not None
        self.calls.append(("label", text))

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def method(*args, **kwargs):
            self.calls.append((name, args))
            return self

        return method


class FakePanel:
    def __init__(self):
        self.layout = FakeLayout()


def _draw_all(context):
    drawn = 0
    for cls in panels.CLASSES:
        if not cls.__name__.startswith(("SWAYFIELD_PT", "SWAYFIELD_MT")):
            continue
        poll = getattr(cls, "poll", None)
        if poll is not None and not poll(context):
            continue
        fake = FakePanel()
        cls.draw(fake, context)
        drawn += 1
    return drawn


def _add_grass(plane):
    from swayfield.core import compat, layers

    plane.select_set(True)
    _activate(plane)
    assert bpy.ops.swayfield.add_grass(layer_name="Test") == {"FINISHED"}
    layer = layers.active_layer(plane)
    mod = layers.get_modifier(plane, layer)
    compat.set_input(mod, "density", 20.0)
    compat.set_input(mod, "density_ceiling", 40.0)
    return layer, mod


def test_draw_without_layer(plane):
    _activate(plane)
    assert _draw_all(bpy.context) >= 1


def test_draw_with_layer(plane):
    from swayfield.core import compat, layers

    layer, mod = _add_grass(plane)
    assert _draw_all(bpy.context) > 10
    # Masks, painted groups, instances, image mode, single colour mode
    for prefix in ("slope", "altitude", "noise", "image", "proximity", "camdist"):
        compat.set_input(mod, f"{prefix}_enable", True)
    compat.set_input(mod, "density_group", "SF_Test_Density")
    compat.set_input(mod, "blade_source", 2)
    assert _draw_all(bpy.context) > 10
    mat = layers.layer_material(plane, layer)
    for mode in ("IMAGE", "SINGLE", "PROCEDURAL"):
        layer.material_mode = mode
        assert _draw_all(bpy.context) > 10
    assert mat is not None


def test_draw_with_grass_object_active(plane):
    from swayfield.core import layers

    layer, mod = _add_grass(plane)
    holder = mod.id_data
    if holder is plane:
        pytest.skip("layers still live on the surface")
    _activate(holder)
    assert layers.surface_of(holder) == plane
    assert panels.layer_state(bpy.context) is not None
    assert _draw_all(bpy.context) > 10


def test_draw_with_effector(plane):
    _add_grass(plane)
    assert bpy.ops.swayfield.add_effector(type="VORTEX") == {"FINISHED"}
    _activate(plane)
    assert _draw_all(bpy.context) > 10


def test_image_operators(plane):
    from swayfield.core import layers, materials

    layer, _mod = _add_grass(plane)
    mat = layers.layer_material(plane, layer)
    img = bpy.data.images.new("t_rough", 4, 4)
    img.filepath_raw = bpy.app.tempdir + "t_rough.png"
    img.file_format = "PNG"
    img.save()
    assert bpy.ops.swayfield.pick_image(slot="Roughness", filepath=img.filepath_raw) == {"FINISHED"}
    assert materials.image_node(mat, "Roughness").image is not None
    assert materials._flag_socket(mat, "Roughness").default_value == 1.0
    assert bpy.ops.swayfield.clear_image(slot="Roughness") == {"FINISHED"}
    assert materials.image_node(mat, "Roughness").image is None
    assert materials._flag_socket(mat, "Roughness").default_value == 0.0
