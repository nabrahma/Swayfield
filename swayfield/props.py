# SPDX-License-Identifier: GPL-3.0-or-later
"""PropertyGroups: UI state only. Every real setting lives on the modifier.

The enum proxies on ``SF_Layer`` have no storage of their own. Their getters
and setters read and write the modifier input (or the material mode) through
``core.compat``, so a value is never stored twice.
"""

# No `from __future__ import annotations` here: Blender reads the class
# annotations at registration time and needs real property objects.

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, IntProperty, PointerProperty,
                       StringProperty)

from .core import compat, spec

#: Fallback items for the material mode when core.materials is not available.
_FALLBACK_MODE_ITEMS = (
    ("PROCEDURAL", "Procedural", "Colours and gradients made from nodes, no image files needed"),
    ("IMAGE_MAPS", "Image Maps", "Blade textures from image files"),
    ("SINGLE_COLOR", "Single Color", "One flat colour, for stylised looks"),
)


def _modifier_of(layer) -> "bpy.types.Modifier | None":
    ob = layer.id_data
    if not isinstance(ob, bpy.types.Object):
        return None
    return ob.modifiers.get(layer.modifier_name)


def _modifier_enum(item: spec.Input):
    """An EnumProperty that reads and writes the modifier input ``item.key``."""
    key = item.key
    items = [(i[0], i[1], i[2]) for i in item.items]

    def getter(self) -> int:
        mod = _modifier_of(self)
        if mod is None or mod.node_group is None:
            return 0
        try:
            return int(compat.get_input(mod, key))
        except KeyError:
            return 0

    def setter(self, value: int) -> None:
        mod = _modifier_of(self)
        if mod is not None and mod.node_group is not None:
            try:
                compat.set_input(mod, key, value)
            except KeyError:
                pass

    return EnumProperty(name=item.name, description=item.description, items=items, get=getter, set=setter)


def _material_mode_enum():
    try:
        from .core import materials
        items = [(i[0], i[1], i[2]) for i in materials.MODE_ITEMS]
    except (ImportError, AttributeError):
        materials = None
        items = list(_FALLBACK_MODE_ITEMS)

    def getter(self) -> int:
        mat = _layer_material(self)
        if mat is None or materials is None:
            return 0
        try:
            return int(materials.get_mode(mat))
        except (KeyError, AttributeError):
            return 0

    def setter(self, value: int) -> None:
        mat = _layer_material(self)
        if mat is not None and materials is not None:
            try:
                materials.set_mode(mat, value)
            except (KeyError, AttributeError):
                pass  # not a Swayfield material

    return EnumProperty(name="Material Mode", description="How the grass is coloured", items=items,
                        get=getter, set=setter)


def _layer_material(layer) -> "bpy.types.Material | None":
    mod = _modifier_of(layer)
    if mod is None or mod.node_group is None:
        return None
    try:
        return compat.get_input(mod, "material")
    except KeyError:
        return None


class SF_Layer(bpy.types.PropertyGroup):
    name: StringProperty(name="Name", description="Name of this grass layer", default="Grass")
    modifier_name: StringProperty(name="Modifier", description="Name of the layer's Geometry Nodes modifier")
    preset: StringProperty(name="Preset", description="Grass preset this layer started from, or CUSTOM",
                           default="CUSTOM")
    wind_preset: StringProperty(name="Wind Type", description="Wind type this layer started from, or CUSTOM",
                                default="CUSTOM")
    link_id: StringProperty(name="Link ID", description="Shared by layers created together on several objects")
    preset_hash: StringProperty(name="Preset Hash", description="Fingerprint of the settings when the preset was "
                                "applied. A different fingerprint means the preset was edited")
    solo: BoolProperty(name="Solo", description="Only this layer is shown in the viewport", default=False)
    hidden_by_solo: BoolProperty(name="Hidden by Solo", description="This layer was hidden by another layer's solo",
                                 default=False)
    paint_restore_display: IntProperty(name="Display Before Painting", default=-1,
                                       description="Display mode to restore after painting, -1 when unused")


def _install_proxies() -> None:
    """Add the enum proxies to SF_Layer, generated from the spec."""
    annotations = SF_Layer.__annotations__
    for item in spec.INPUTS:
        if item.type == "INT" and item.items:
            annotations[item.key] = _modifier_enum(item)
    annotations["material_mode"] = _material_mode_enum()


_install_proxies()


class SF_ObjectSettings(bpy.types.PropertyGroup):
    layers: CollectionProperty(type=SF_Layer)
    active_layer_index: IntProperty(name="Active Layer", default=0, min=0)


class SF_SceneSettings(bpy.types.PropertyGroup):
    budget: IntProperty(name="Blade Budget", description="Most blades to show in the viewport before Swayfield "
                        "warns you. Turn on Optimised Mode or lower the density to stay under it",
                        default=2_000_000, min=1000, soft_max=50_000_000)
    auto_optimise_threshold: IntProperty(name="Auto Optimise Above", description="Add Grass turns on Optimised "
                                         "Mode when a surface would grow more blades than this",
                                         default=500_000, min=0, soft_max=10_000_000)


classes = (SF_Layer, SF_ObjectSettings, SF_SceneSettings)


def register() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.swayfield = PointerProperty(type=SF_ObjectSettings)
    bpy.types.Scene.swayfield = PointerProperty(type=SF_SceneSettings)


def unregister() -> None:
    del bpy.types.Scene.swayfield
    del bpy.types.Object.swayfield
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
