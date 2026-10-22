# SPDX-License-Identifier: GPL-3.0-or-later
"""UI tests: registration, panel polls, strings and icons."""

from __future__ import annotations

import bpy
import pytest

from swayfield import ui
from swayfield.core import nodes, spec
from swayfield.ui import icons, panels, strings


def _make_layer(ob):
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
    _make_layer(plane)
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
    _make_layer(plane)
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
