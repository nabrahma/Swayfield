# SPDX-License-Identifier: GPL-3.0-or-later
"""Create, remove and duplicate grass layers: modifier, material, drivers and list entry."""

from __future__ import annotations

import bpy

from . import compat, drivers, layers, nodes, spec

EFFECTORS_COLLECTION = "SF_Effectors"

#: Inputs that belong to one layer or are driven, so duplicating a layer does not copy them.
_NOT_COPIED = frozenset({"material", "preview_material", *drivers.DRIVEN_KEYS})


def ensure_effector_collection(scene: bpy.types.Scene | None = None) -> bpy.types.Collection:
    """The shared ``SF_Effectors`` collection, created and linked under the scene collection on demand."""
    scene = scene or bpy.context.scene
    coll = bpy.data.collections.get(EFFECTORS_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(EFFECTORS_COLLECTION)
    if coll.name not in scene.collection.children:
        # The collection may already sit under another collection of the scene.
        if not any(coll.name in c.children for c in scene.collection.children_recursive):
            scene.collection.children.link(coll)
    return coll


def _fallback_material(name: str) -> bpy.types.Material:
    """A plain green Principled material, used while core.materials is not available."""
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
    except AttributeError:
        pass  # Blender versions where node materials are always on
    if mat.node_tree is not None:
        for node in mat.node_tree.nodes:
            if node.bl_idname == "ShaderNodeBsdfPrincipled":
                node.inputs["Base Color"].default_value = (0.1, 0.35, 0.05, 1.0)
    return mat


def _create_material(name: str) -> bpy.types.Material:
    try:
        from . import materials
        return materials.create_layer_material(name)
    except (ImportError, AttributeError):
        return _fallback_material(name)


def _preview_material() -> bpy.types.Material | None:
    try:
        from . import materials
        return materials.ensure_mask_preview_material()
    except (ImportError, AttributeError):
        return None


def material_name(ob: bpy.types.Object, layer_name: str) -> str:
    return f"SF_{ob.name}_{layer_name}"


def move_modifier(ob: bpy.types.Object, mod: bpy.types.Modifier, target_index: int) -> None:
    """Move ``mod`` to ``target_index`` in the stack, on Blender 4.2 and newer."""
    current = list(ob.modifiers).index(mod)
    if current == target_index:
        return
    if hasattr(ob.modifiers, "move"):
        ob.modifiers.move(current, target_index)
        return
    with bpy.context.temp_override(object=ob, active_object=ob):
        bpy.ops.object.modifier_move_to_index(modifier=mod.name, index=target_index)


def create_layer(ob: bpy.types.Object, name: str, *, seed_offset: int = 0, link_id: str = "",
                 material: bpy.types.Material | None = None):
    """Add a grass layer to ``ob`` and return ``(layer, modifier)``.

    The modifier goes last in the stack, so it sees Subdivision, Displace and
    similar modifiers below it (SC-16). ``material`` reuses an existing
    material instead of creating a new one (used by duplicate).
    """
    name = layers.unique_layer_name(ob, name)
    mod = ob.modifiers.new(f"Swayfield {name}", "NODES")
    mod.node_group = nodes.ensure("main")
    if hasattr(mod, "use_pin_to_last"):
        mod.use_pin_to_last = True  # keeps it below later additions, Blender 4.2+
    mod.show_expanded = False  # the Swayfield panel replaces the modifier panel
    # Pinned modifiers are inserted before older pinned ones. Keep layers in list order.
    move_modifier(ob, mod, len(ob.modifiers) - 1)

    mat = material or _create_material(material_name(ob, name))
    compat.set_input(mod, "material", mat)
    preview = _preview_material()
    if preview is not None:
        compat.set_input(mod, "preview_material", preview)
    compat.set_input(mod, "effector_collection", ensure_effector_collection())
    compat.set_input(mod, "seed_offset", seed_offset)
    drivers.add_camera_drivers(ob, mod)

    settings = ob.swayfield
    layer = settings.layers.add()
    layer.name = name
    layer.modifier_name = mod.name
    layer.preset = "CUSTOM"
    layer.wind_preset = "CUSTOM"
    layer.link_id = link_id
    settings.active_layer_index = len(settings.layers) - 1
    return layer, mod


def _material_in_use(mat: bpy.types.Material, ignore: bpy.types.Modifier) -> bool:
    for other in bpy.data.objects:
        for mod in layers.swayfield_modifiers(other):
            if mod == ignore:
                continue
            try:
                if compat.get_input(mod, "material") == mat:
                    return True
            except KeyError:
                continue
    return False


def _collection_in_use(coll: bpy.types.Collection, ignore: bpy.types.Modifier) -> bool:
    for other in bpy.data.objects:
        for mod in layers.swayfield_modifiers(other):
            if mod == ignore:
                continue
            for key in ("exclusion_collection", "proximity_collection", "effector_collection", "instance_collection"):
                try:
                    if compat.get_input(mod, key) == coll:
                        return True
                except KeyError:
                    continue
    return False


def remove_layer(ob: bpy.types.Object, layer) -> None:
    """Delete the layer, its modifier, its drivers, and its material and exclusion collection if unused."""
    settings = ob.swayfield
    index = layers.layer_index(ob, layer)
    mod = layers.get_modifier(ob, layer)
    if mod is not None:
        mat = layers.layer_material(ob, layer)
        try:
            exclusion = compat.get_input(mod, "exclusion_collection")
        except KeyError:
            exclusion = None
        drivers.remove_all_drivers(ob, mod)
        if mat is not None and mat.name.startswith("SF_") and not _material_in_use(mat, mod):
            compat.set_input(mod, "material", None)
            bpy.data.materials.remove(mat)
        in_use = exclusion is not None and _collection_in_use(exclusion, mod)
        ob.modifiers.remove(mod)
        if exclusion is not None and exclusion.name.startswith("SF_Exclude_") and not in_use:
            bpy.data.collections.remove(exclusion)
    if index >= 0:
        settings.layers.remove(index)
    settings.active_layer_index = max(0, min(settings.active_layer_index, len(settings.layers) - 1))


def copy_inputs(src: bpy.types.Modifier, dst: bpy.types.Modifier, skip: frozenset | set = frozenset()) -> None:
    """Copy every spec input value that both modifiers have (through compat)."""
    for item in spec.INPUTS:
        if item.key in skip or not compat.has_input(src, item.name) or not compat.has_input(dst, item.name):
            continue
        compat.set_input(dst, item.key, compat.get_input(src, item.key))


def duplicate_layer(ob: bpy.types.Object, layer):
    """Copy ``layer`` with all its settings and its own copy of the material. Returns ``(layer, modifier)``."""
    src = layers.get_modifier(ob, layer)
    if src is None:
        raise ValueError("this layer has no Swayfield modifier")
    name = layers.unique_layer_name(ob, f"{layer.name} Copy")
    src_mat = layers.layer_material(ob, layer)
    mat = src_mat.copy() if src_mat is not None else None
    if mat is not None:
        mat.name = material_name(ob, name)
    new_layer, mod = create_layer(ob, name, material=mat)
    copy_inputs(src, mod, _NOT_COPIED)
    new_layer.preset = layer.preset
    new_layer.wind_preset = layer.wind_preset
    new_layer.preset_hash = layer.preset_hash
    return new_layer, mod
