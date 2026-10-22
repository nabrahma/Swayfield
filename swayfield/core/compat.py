# SPDX-License-Identifier: GPL-3.0-or-later
"""Version-independent access to Geometry Nodes modifier inputs.

Blender 4.2 to 4.x store modifier input values as ID properties on the
modifier (``mod["Socket_2"]``). Blender 5.x moved them to
``mod.properties.inputs.Socket_2.value``. Everything in Swayfield goes through
this module so the rest of the code never cares which one it runs on.

Inputs are addressed by socket *name* (``spec.Input.name``), never by
identifier, because identifiers depend on creation order.
"""

from __future__ import annotations

import bpy

from . import spec


def uses_properties_api(mod: bpy.types.Modifier) -> bool:
    """True on Blender 5.x, where inputs live under ``mod.properties``."""
    return hasattr(mod, "properties") and hasattr(mod.properties, "inputs")


def input_identifier(mod: bpy.types.Modifier, name: str) -> str:
    """Return the socket identifier (``Socket_N``) of the input called ``name``."""
    group = mod.node_group
    if group is None:
        raise KeyError(f"modifier {mod.name!r} has no node group")
    for item in group.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name == name:
            return item.identifier
    raise KeyError(f"node group {group.name!r} has no input {name!r}")


def has_input(mod: bpy.types.Modifier, name: str) -> bool:
    try:
        input_identifier(mod, name)
    except KeyError:
        return False
    return True


def _resolve(mod, key_or_name: str) -> str:
    """Accept either a spec key (``"density"``) or a socket name (``"Density"``)."""
    item = spec.BY_KEY.get(key_or_name)
    return item.name if item is not None else key_or_name


def get_input(mod: bpy.types.Modifier, key: str):
    """Read an input value. ``key`` is a spec key or a socket name."""
    ident = input_identifier(mod, _resolve(mod, key))
    if uses_properties_api(mod):
        return getattr(mod.properties.inputs, ident).value
    return mod[ident]


def set_input(mod: bpy.types.Modifier, key: str, value) -> None:
    """Write an input value. ``key`` is a spec key or a socket name."""
    item = spec.BY_KEY.get(key) or spec.BY_NAME.get(key)
    ident = input_identifier(mod, _resolve(mod, key))
    if item is not None:
        value = _coerce(item, value)
    if uses_properties_api(mod):
        getattr(mod.properties.inputs, ident).value = value
    else:
        mod[ident] = value
    # Neither API tags the object for re-evaluation when written from Python.
    if mod.id_data is not None:
        mod.id_data.update_tag()


def _coerce(item: spec.Input, value):
    if item.type == "FLOAT":
        return float(value)
    if item.type == "INT":
        return int(value)
    if item.type == "BOOLEAN":
        return bool(value)
    if item.type in {"VECTOR", "COLOR"} and value is not None:
        return tuple(value)
    return value


def input_data_path(mod: bpy.types.Modifier, key: str) -> str:
    """Data path of an input relative to the object, for drivers and keyframes."""
    ident = input_identifier(mod, _resolve(mod, key))
    if uses_properties_api(mod):
        return getattr(mod.properties.inputs, ident).path_from_id("value")
    return f'modifiers["{bpy.utils.escape_identifier(mod.name)}"]["{ident}"]'


def draw_input(layout: bpy.types.UILayout, mod: bpy.types.Modifier, key: str, text: str | None = None, **kwargs):
    """Draw an input as a regular property, so keyframing and drivers work from the UI."""
    item = spec.BY_KEY.get(key) or spec.BY_NAME.get(key)
    label = text if text is not None else (item.name if item else key)
    ident = input_identifier(mod, _resolve(mod, key))
    if uses_properties_api(mod):
        return layout.prop(getattr(mod.properties.inputs, ident), "value", text=label, **kwargs)
    return layout.prop(mod, f'["{ident}"]', text=label, **kwargs)
