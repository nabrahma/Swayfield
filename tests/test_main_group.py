# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from swayfield.core import compat, nodes, spec


def _add_modifier(ob):
    mod = ob.modifiers.new("Swayfield", "NODES")
    mod.node_group = nodes.ensure("main")
    return mod


def test_main_exposes_every_spec_input(plane):
    tree = nodes.ensure("main")
    names = {i.name for i in tree.interface.items_tree if i.item_type == "SOCKET" and i.in_out == "INPUT"}
    assert {i.name for i in spec.INPUTS} <= names


@pytest.mark.parametrize("key", ["density", "seed", "loop_enable", "blade_source"])
def test_inputs_round_trip_through_compat(plane, key):
    mod = _add_modifier(plane)
    item = spec.get(key)
    value = {"FLOAT": 1234.0, "INT": 1, "BOOLEAN": True}[item.type]
    compat.set_input(mod, key, value)
    assert compat.get_input(mod, key) == value


def test_driver_path_is_valid(plane):
    mod = _add_modifier(plane)
    path = compat.input_data_path(mod, "intensity")
    fcurve = plane.driver_add(path)
    fcurve.driver.expression = "1.5"
    plane.update_tag()
    import bpy
    bpy.context.view_layer.update()
    assert compat.get_input(mod, "intensity") == pytest.approx(1.5)
