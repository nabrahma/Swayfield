# SPDX-License-Identifier: GPL-3.0-or-later
"""Create, remove and duplicate grass layers.

Each layer is a hair Curves object parented to the surface, because Cycles and EEVEE
only render curves as hair on Curves objects. It carries the modifier, the material
slot and the drivers. The layer list stays on the surface.
"""

from __future__ import annotations

import bpy
from mathutils import Matrix

from . import compat, drivers, layers, nodes, spec

EFFECTORS_COLLECTION = "SF_Effectors"

#: Inputs that belong to one layer or are driven, so duplicating a layer does not copy them.
_NOT_COPIED = frozenset({"surface", "material", "preview_material", *drivers.DRIVEN_KEYS})


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


def grass_object_name(surface: bpy.types.Object, layer_name: str) -> str:
    return f"SF_{surface.name}_{layer_name}"


def _make_grass_object(surface: bpy.types.Object, name: str) -> bpy.types.Object:
    """A hair Curves object that follows ``surface``, in the surface's collection."""
    ob = bpy.data.objects.new(name, bpy.data.hair_curves.new(name))
    collection = surface.users_collection[0] if surface.users_collection else bpy.context.scene.collection
    collection.objects.link(ob)
    ob.parent = surface
    ob.matrix_parent_inverse = Matrix.Identity(4)
    ob["sf_grass"] = True
    ob.hide_select = True  # clicking the terrain must not pick the grass
    return ob


def create_layer(surface: bpy.types.Object, name: str, *, seed_offset: int = 0, link_id: str = "",
                 material: bpy.types.Material | None = None):
    """Add a grass layer to ``surface`` and return ``(layer, modifier)``.

    The modifier sits on a new hair Curves object ``SF_<surface>_<layer>`` that is
    parented to the surface. The modifier reads the surface through its
    ``surface`` input, so the surface's own modifiers (Subdivision, Displace)
    count (SC-16). ``material`` reuses an existing material instead of creating
    a new one (used by duplicate).
    """
    name = layers.unique_layer_name(surface, name)
    grass = _make_grass_object(surface, grass_object_name(surface, name))
    mod = grass.modifiers.new(f"Swayfield {name}", "NODES")
    mod.node_group = nodes.ensure("main")
    mod.show_expanded = False  # the Swayfield panel replaces the modifier panel
    compat.set_input(mod, "surface", surface)

    mat = material or _create_material(material_name(surface, name))
    compat.set_input(mod, "material", mat)
    grass.data.materials.append(mat)
    preview = _preview_material()
    if preview is not None:
        compat.set_input(mod, "preview_material", preview)
    compat.set_input(mod, "effector_collection", ensure_effector_collection())
    compat.set_input(mod, "seed_offset", seed_offset)
    drivers.add_camera_drivers(grass, mod)

    settings = surface.swayfield
    layer = settings.layers.add()
    layer.name = name
    layer.grass_object = grass
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
    """Delete the layer, its grass object and hair data, and its material and exclusion collection if unused."""
    settings = ob.swayfield
    index = layers.layer_index(ob, layer)
    mod = layers.get_modifier(ob, layer)
    grass = layer.grass_object
    if mod is not None:
        mat = layers.layer_material(ob, layer)
        try:
            exclusion = compat.get_input(mod, "exclusion_collection")
        except KeyError:
            exclusion = None
        exclusion_in_use = exclusion is not None and _collection_in_use(exclusion, mod)
        material_in_use = mat is not None and _material_in_use(mat, mod)
    if index >= 0:
        settings.layers.remove(index)
    if grass is not None:
        data = grass.data
        bpy.data.objects.remove(grass)
        if data is not None and data.users == 0:
            bpy.data.hair_curves.remove(data)
    if mod is not None:
        if mat is not None and mat.name.startswith("SF_") and not material_in_use:
            bpy.data.materials.remove(mat)
        if exclusion is not None and exclusion.name.startswith("SF_Exclude_") and not exclusion_in_use:
            bpy.data.collections.remove(exclusion)
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
