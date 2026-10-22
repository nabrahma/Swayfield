# SPDX-License-Identifier: GPL-3.0-or-later
"""Group versions and layer upgrade.

A released group is never rebuilt in a user's file. A new version
(``SF_Main_v2``) ships next to the old one, and ``upgrade_layer`` moves a
layer's modifier over by copying every input whose name exists in both groups.
"""

from __future__ import annotations

import re

import bpy

from . import compat, drivers, layers, spec

CURRENT_MAIN = "SF_Main_v1"

_VERSION = re.compile(r"^SF_Main_v(\d+)")


def _version_of(name: str) -> int:
    match = _VERSION.match(name)
    return int(match.group(1)) if match else 0


def group_version(mod: bpy.types.Modifier) -> int:
    """Version number of the modifier's main group (0 when it is not a versioned Swayfield group)."""
    if mod.node_group is None:
        return 0
    return _version_of(mod.node_group.name)


def needs_upgrade(mod: bpy.types.Modifier) -> bool:
    return layers.is_swayfield_modifier(mod) and group_version(mod) < _version_of(CURRENT_MAIN)


def _input_sockets(group: bpy.types.NodeTree) -> dict[str, str]:
    """Map socket name to identifier for the value inputs of ``group``."""
    return {item.name: item.identifier for item in group.interface.items_tree
            if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.socket_type != "NodeSocketGeometry"}


def _driver_curves(ob: bpy.types.Object, mod: bpy.types.Modifier) -> list:
    anim = ob.animation_data
    if anim is None:
        return []
    prefix = f'modifiers["{bpy.utils.escape_identifier(mod.name)}"]'
    return [f for f in anim.drivers if f.data_path.startswith(prefix)]


def _copy_drivers(ob: bpy.types.Object, mod: bpy.types.Modifier, old_ids: dict[str, str]) -> list[tuple[str, dict]]:
    """Describe the user's own drivers (not the camera ones) so they can be recreated."""
    camera_ids = {old_ids[name] for name in (spec.BY_KEY[k].name for k in drivers.DRIVEN_KEYS)
                  if name in old_ids}
    kept = []
    for fcurve in _driver_curves(ob, mod):
        ident = next((i for i in old_ids.values() if re.search(rf"(?<!\w){re.escape(i)}(?!\w)", fcurve.data_path)),
                     None)
        if ident is None or ident in camera_ids:
            continue
        driver = fcurve.driver
        kept.append((ident, {
            "type": driver.type,
            "expression": driver.expression,
            "variables": [{"name": v.name, "type": v.type,
                           "targets": [{"id_type": t.id_type, "id": t.id, "data_path": t.data_path,
                                        "transform_type": t.transform_type, "transform_space": t.transform_space,
                                        "bone_target": t.bone_target}
                                       for t in v.targets[:(2 if v.type in {"LOC_DIFF", "ROTATION_DIFF"} else 1)]]}
                          for v in driver.variables],
        }))
    return kept


def _restore_drivers(ob: bpy.types.Object, mod: bpy.types.Modifier, old_ids: dict[str, str],
                     new_ids: dict[str, str], saved: list[tuple[str, dict]]) -> None:
    by_old = {ident: name for name, ident in old_ids.items()}
    for old_ident, data in saved:
        name = by_old.get(old_ident)
        if name is None or name not in new_ids or not compat.has_input(mod, name):
            continue
        fcurve = ob.driver_add(compat.input_data_path(mod, name))
        driver = fcurve.driver
        driver.type = data["type"]
        for var_data in data["variables"]:
            var = driver.variables.new()
            var.name = var_data["name"]
            var.type = var_data["type"]
            for target, t in zip(var.targets, var_data["targets"], strict=False):
                if t["id_type"]:
                    target.id_type = t["id_type"]
                target.id = t["id"]
                target.data_path = t["data_path"]
                if var.type == "TRANSFORMS":
                    target.transform_type = t["transform_type"]
                    target.transform_space = t["transform_space"]
        if data["type"] == "SCRIPTED":
            driver.expression = data["expression"]


def upgrade_layer(ob: bpy.types.Object, layer) -> bool:
    """Move ``layer`` of surface ``ob`` to the newest main group. Returns False when it is already current."""
    from . import nodes

    mod = layers.get_modifier(ob, layer)
    if mod is None:
        raise ValueError("this layer has no Swayfield modifier")
    if not needs_upgrade(mod):
        return False

    grass = mod.id_data  # drivers live on the layer's grass object
    old_group = mod.node_group
    old_ids = _input_sockets(old_group)
    values = {name: compat.get_input(mod, name) for name in old_ids}
    saved = _copy_drivers(grass, mod, old_ids)
    for fcurve in _driver_curves(grass, mod):
        grass.animation_data.drivers.remove(fcurve)

    new_group = nodes.ensure("main")
    mod.node_group = new_group
    new_ids = _input_sockets(new_group)
    for name, value in values.items():
        if name in new_ids:
            try:
                compat.set_input(mod, name, value)
            except (TypeError, ValueError, AttributeError):
                pass  # the socket type changed between versions, keep the new default
    if compat.has_input(mod, spec.BY_KEY["surface"].name):
        compat.set_input(mod, "surface", ob)  # older groups may not have had the input
    drivers.add_camera_drivers(grass, mod)
    _restore_drivers(grass, mod, old_ids, new_ids, saved)
    grass.update_tag()
    return True
