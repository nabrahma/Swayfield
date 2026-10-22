# SPDX-License-Identifier: GPL-3.0-or-later
"""The Swayfield sidebar tab. Every modifier input is drawn through ``compat.draw_input``."""

from __future__ import annotations

import importlib
from typing import Callable, NamedTuple

import bpy

from ..core import compat, spec
from . import icons, strings
from .lists import _op, layer_modifier

_MODE_NAMES = ("PROCEDURAL", "IMAGE", "SINGLE")
INSTANCES_INDEX = 2

# ---------------------------------------------------------------------------
# Defensive helpers
# ---------------------------------------------------------------------------


def _core(module: str, name: str):
    """Return ``swayfield.core.<module>.<name>`` or None when it is not available yet."""
    try:
        return getattr(importlib.import_module(f"swayfield.core.{module}"), name, None)
    except Exception:
        return None


def _call(module: str, name: str, *args, default=None):
    fn = _core(module, name)
    if fn is None:
        return default
    try:
        return fn(*args)
    except Exception:
        return default


class State(NamedTuple):
    """The active object, its active layer and that layer's modifier."""

    ob: bpy.types.Object
    layer: object
    mod: bpy.types.Modifier | None


def _active_layer(ob):
    settings = getattr(ob, "swayfield", None)
    if settings is None:
        return None
    layers = settings.layers
    index = settings.active_layer_index
    if 0 <= index < len(layers):
        return layers[index]
    return None


def _modifier(ob, layer):
    mod = layer_modifier(ob, layer)
    if mod is None or mod.type != "NODES" or mod.node_group is None:
        return None
    return mod


def _surface(ob):
    """The surface for the surface or its grass object, or None."""
    if ob is None:
        return None
    fn = _core("layers", "surface_of")
    if fn is not None:
        return fn(ob)
    return ob if getattr(ob, "swayfield", None) is not None else None


def layer_state(context, need_modifier: bool = True) -> State | None:
    """Active object, layer and modifier, or None when any of them is missing."""
    ob = _surface(getattr(context, "active_object", None))
    if ob is None:
        return None
    layer = _active_layer(ob)
    if layer is None:
        return None
    mod = _modifier(ob, layer)
    if mod is None and need_modifier:
        return None
    return State(ob, layer, mod)


def _get(mod, key: str, default=None):
    try:
        return compat.get_input(mod, key)
    except Exception:
        return default


def draw_keys(layout: bpy.types.UILayout, st: State, keys, **kwargs) -> None:
    """Draw spec inputs. Enum-like inputs go through the layer's proxy property."""
    for key in keys:
        item = spec.BY_KEY.get(key)
        if item is None:
            continue
        try:
            if item.items and hasattr(st.layer, key):
                layout.prop(st.layer, key, text=item.name)
            else:
                compat.draw_input(layout, st.mod, key, **kwargs)
        except KeyError:
            continue  # input missing from an older group version


def _proxy(layout, st: State, key: str, text: str | None = None, **kwargs) -> None:
    if hasattr(st.layer, key):
        layout.prop(st.layer, key, text=text if text is not None else spec.BY_KEY[key].name, **kwargs)


def _fmt(value) -> str:
    return f"{int(value):,}"


def _mode_index(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.upper()
        for i, name in enumerate(_MODE_NAMES):
            if text.startswith(name):
                return i
    return None


# ---------------------------------------------------------------------------
# Base classes
# ---------------------------------------------------------------------------


class _Base:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Swayfield"


class _LayerPanel(_Base):
    """Top-level panel shown only when the active layer has a live modifier."""

    @classmethod
    def poll(cls, context) -> bool:
        return layer_state(context) is not None


def _sub_panel(idname: str, label: str, parent: str, keys=(), closed: bool = True,
               condition: Callable[[State], bool] | None = None,
               extra: Callable[[bpy.types.UILayout, State], None] | None = None):
    """Build a sub-panel class that draws a list of spec keys."""

    @classmethod
    def poll(cls, context) -> bool:
        st = layer_state(context)
        if st is None:
            return False
        return condition(st) if condition is not None else True

    def draw(self, context) -> None:
        st = layer_state(context)
        if st is None:
            return
        col = self.layout.column()
        draw_keys(col, st, keys)
        if extra is not None:
            extra(col, st)

    namespace = {
        "bl_idname": idname, "bl_label": label, "bl_parent_id": parent,
        "bl_space_type": "VIEW_3D", "bl_region_type": "UI", "bl_category": "Swayfield",
        "bl_options": {"DEFAULT_CLOSED"} if closed else set(),
        "poll": poll, "draw": draw, "__doc__": label,
    }
    return type(idname, (bpy.types.Panel,), namespace)


# ---------------------------------------------------------------------------
# 1. Main panel
# ---------------------------------------------------------------------------


def _draw_preset_picker(layout: bpy.types.UILayout, context) -> None:
    wm = context.window_manager
    if not hasattr(wm, "swayfield_preset"):
        return
    if icons.has_thumbnails():
        layout.template_icon_view(wm, "swayfield_preset", show_labels=True, scale=5.0, scale_popup=5.0)
    else:
        layout.prop(wm, "swayfield_preset", text="")


def _row_value(layout, label: str, value: str) -> None:
    split = layout.split(factor=0.5, align=True)
    split.label(text=label)
    split.label(text=value)


def _draw_counter(layout: bpy.types.UILayout, context, st: State) -> None:
    holder = st.mod.id_data
    viewport = _call("budget", "count_blades", holder, st.mod)
    render = _call("budget", "estimate_render_count", holder, st.mod)
    totals = _call("budget", "scene_totals", context)
    budget = getattr(getattr(context.scene, "swayfield", None), "budget", 0)
    if viewport is None and render is None and totals is None:
        return
    box = layout.box()
    col = box.column(align=True)
    if viewport is not None:
        _row_value(col, strings.LBL_VIEWPORT_BLADES, _fmt(viewport))
    if render is not None:
        _row_value(col, strings.LBL_RENDER_BLADES, _fmt(render))
    if totals is not None:
        over = bool(budget) and totals.viewport > budget
        row = col.row()
        row.alert = over
        text = _fmt(totals.viewport) + (f" / {_fmt(budget)}" if budget else "")
        _row_value(row, strings.LBL_SCENE_BLADES, text)
        if over:
            box.label(text=strings.HINT_OVER_BUDGET, icon=icons.ICON_WARNING)


class SWAYFIELD_PT_main(_Base, bpy.types.Panel):
    bl_idname = "SWAYFIELD_PT_main"
    bl_label = strings.PANEL_MAIN

    def draw(self, context) -> None:
        layout = self.layout
        _draw_preset_picker(layout, context)
        pointer = _op(layout, "swayfield.add_grass", text=strings.BTN_ADD_GRASS, icon=icons.ICON_ADD)
        wm = context.window_manager
        if pointer is not None and hasattr(wm, "swayfield_preset"):
            if wm.swayfield_preset != "NONE":
                pointer.preset = wm.swayfield_preset
        st = layer_state(context)
        ob = context.active_object
        if st is None:
            surface = _surface(ob)
            if surface is not None and _active_layer(surface) is not None:
                layout.label(text=strings.HINT_NO_MODIFIER, icon=icons.ICON_WARNING)
            elif ob is None:
                layout.label(text=strings.HINT_SELECT_MESH_THEN_ADD)
            elif ob.type != "MESH":
                layout.label(text=strings.HINT_SELECT_MESH_FIRST)
            return
        draw_keys(layout, st, ("optimised",), toggle=True)
        _draw_counter(layout, context, st)
        _op(layout, "swayfield.quick_look", text=strings.BTN_QUICK_LOOK, icon=icons.ICON_CAMERA)


# ---------------------------------------------------------------------------
# 2. Layers
# ---------------------------------------------------------------------------


def _has_linked_layer(ob, layer) -> bool:
    link_id = getattr(layer, "link_id", "")
    if not link_id:
        return False
    for other in bpy.data.objects:
        settings = getattr(other, "swayfield", None)
        if other is ob or settings is None:
            continue
        if any(item.link_id == link_id for item in settings.layers):
            return True
    return False


class SWAYFIELD_PT_layers(_Base, bpy.types.Panel):
    bl_idname = "SWAYFIELD_PT_layers"
    bl_label = strings.PANEL_LAYERS

    @classmethod
    def poll(cls, context) -> bool:
        return layer_state(context, need_modifier=False) is not None

    def draw(self, context) -> None:
        layout = self.layout
        settings = _surface(context.active_object).swayfield
        row = layout.row()
        row.template_list("SWAYFIELD_UL_layers", "", settings, "layers", settings, "active_layer_index", rows=3)
        col = row.column(align=True)
        _op(col, "swayfield.layer_add", text="", icon=icons.ICON_ADD)
        _op(col, "swayfield.layer_remove", text="", icon=icons.ICON_REMOVE)
        _op(col, "swayfield.layer_duplicate", text="", icon=icons.ICON_DUPLICATE)
        col.separator()
        _op(col, "swayfield.layer_move", text="", icon=icons.ICON_UP, direction="UP")
        _op(col, "swayfield.layer_move", text="", icon=icons.ICON_DOWN, direction="DOWN")
        st = layer_state(context, need_modifier=False)
        if st is None:
            return
        if st.mod is None:
            layout.label(text=strings.HINT_NO_MODIFIER, icon=icons.ICON_WARNING)
            return
        label = _call("layers", "preset_label", st.ob, st.layer)
        if label is None:
            label = strings.LBL_CUSTOM if st.layer.preset in ("", "CUSTOM") else st.layer.preset
        layout.menu("SWAYFIELD_MT_grass_presets", text=f"{strings.LBL_PRESET}: {label}")
        if _call("versioning", "needs_upgrade", st.mod, default=False):
            _op(layout, "swayfield.upgrade_layer", text=strings.BTN_UPGRADE_LAYER, icon=icons.ICON_UPGRADE)
        if _has_linked_layer(st.ob, st.layer):
            _op(layout, "swayfield.sync_linked", text=strings.BTN_SYNC_LINKED, icon=icons.ICON_SYNC)


# ---------------------------------------------------------------------------
# 3. Distribution, 4. Blade Shape
# ---------------------------------------------------------------------------


class SWAYFIELD_PT_distribution(_LayerPanel, bpy.types.Panel):
    bl_idname = "SWAYFIELD_PT_distribution"
    bl_label = strings.PANEL_DISTRIBUTION

    def draw(self, context) -> None:
        st = layer_state(context)
        col = self.layout.column()
        draw_keys(col, st, ("seed", "density", "density_ceiling", "min_distance", "orient_normal", "blade_source"))


def _is_instances(st: State) -> bool:
    return _get(st.mod, "blade_source", 0) == INSTANCES_INDEX


class SWAYFIELD_PT_blade_shape(_LayerPanel, bpy.types.Panel):
    bl_idname = "SWAYFIELD_PT_blade_shape"
    bl_label = strings.PANEL_BLADE_SHAPE

    def draw(self, context) -> None:
        st = layer_state(context)
        col = self.layout.column()
        draw_keys(col, st, ("length_min", "length_max", "root_width", "tip_taper", "rest_lean", "curl",
                            "random_tilt", "random_rotation", "blade_points"))


# ---------------------------------------------------------------------------
# 5. Masks
# ---------------------------------------------------------------------------

PAINT_MAPS = (
    ("density", "DENSITY", strings.BTN_PAINT_DENSITY),
    ("length", "LENGTH", strings.BTN_PAINT_LENGTH),
    ("wind", "WIND", strings.BTN_PAINT_WIND),
    ("variation", "VARIATION", strings.BTN_PAINT_VARIATION),
)

MASK_STACK = (
    ("slope", ("slope_min", "slope_max", "slope_smooth")),
    ("altitude", ("altitude_min", "altitude_max", "altitude_smooth")),
    ("noise", ("noise_scale", "noise_contrast", "noise_coverage", "noise_seed")),
    ("image", ("image_mask", "image_uv")),
    ("proximity", ("proximity_collection", "proximity_distance", "proximity_smooth", "proximity_invert")),
    ("camdist", ("camdist_min", "camdist_max", "camdist_smooth")),
)


def _mask_enabled(mod, prefix: str) -> bool:
    return bool(_get(mod, f"{prefix}_enable", False))


class SWAYFIELD_MT_add_mask(bpy.types.Menu):
    bl_idname = "SWAYFIELD_MT_add_mask"
    bl_label = strings.BTN_ADD_MASK

    def draw(self, context) -> None:
        st = layer_state(context)
        if st is None:
            return
        for prefix, _keys in MASK_STACK:
            if not _mask_enabled(st.mod, prefix):
                draw_keys(self.layout, st, (f"{prefix}_enable",))


class SWAYFIELD_PT_masks(_LayerPanel, bpy.types.Panel):
    bl_idname = "SWAYFIELD_PT_masks"
    bl_label = strings.PANEL_MASKS

    def draw(self, context) -> None:
        layout = self.layout
        st = layer_state(context)
        grid = layout.grid_flow(row_major=True, columns=2, align=True)
        for _prefix, map_id, text in PAINT_MAPS:
            _op(grid, "swayfield.paint", text=text, icon=icons.ICON_PAINT, map=map_id)
        if context.mode == "PAINT_WEIGHT":
            _op(layout, "swayfield.paint_done", text=strings.BTN_PAINT_DONE, icon=icons.ICON_DONE)
        if _call("layers", "surface_too_coarse", st.ob, default=False):
            box = layout.box()
            box.label(text=strings.HINT_COARSE_SURFACE, icon=icons.ICON_WARNING)
            _op(box, "swayfield.subdivide_surface", text=strings.BTN_SUBDIVIDE, icon=icons.ICON_SUBDIVIDE)
        for prefix, _map_id, _text in PAINT_MAPS:
            if not _get(st.mod, f"{prefix}_group", ""):
                continue
            col = layout.box().column(align=True)
            draw_keys(col, st, (f"{prefix}_group", f"{prefix}_invert", f"{prefix}_contrast",
                                f"{prefix}_threshold"))
        draw_keys(layout.column(), st, ("length_falloff",))
        for prefix, keys in MASK_STACK:
            if not _mask_enabled(st.mod, prefix):
                continue
            box = layout.box()
            row = box.row(align=True)
            draw_keys(row, st, (f"{prefix}_enable",))
            _proxy(row, st, f"{prefix}_blend", text="")
            draw_keys(box.column(), st, keys)
        layout.menu("SWAYFIELD_MT_add_mask", text=strings.BTN_ADD_MASK, icon=icons.ICON_ADD)
        draw_keys(layout.column(), st, ("mask_preview",))


# ---------------------------------------------------------------------------
# 6. Wind
# ---------------------------------------------------------------------------


def _draw_preset_menu(layout, kind: str, apply_op: str, id_prop: str, delete_menu: str) -> None:
    """Apply entries for every preset, then Save and (when there are user presets) Delete."""
    lister = "list_grass_presets" if kind == "GRASS" else "list_wind_presets"
    presets = _call("presets", lister, default=[]) or []
    for preset in presets:
        _op(layout, apply_op, text=str(preset.get("name", preset.get("id", " "))), **{id_prop: preset.get("id", "")})
    layout.separator()
    _op(layout, "swayfield.save_preset", text=strings.BTN_SAVE_PRESET, icon=icons.ICON_ADD, kind=kind)
    if any(not p.get("builtin", True) for p in presets):
        layout.menu(delete_menu, text=strings.MENU_DELETE_PRESET, icon=icons.ICON_FREE)


def _draw_delete_menu(layout, kind: str) -> None:
    lister = "list_grass_presets" if kind == "GRASS" else "list_wind_presets"
    for preset in _call("presets", lister, default=[]) or []:
        if not preset.get("builtin", True):
            _op(layout, "swayfield.delete_preset", text=str(preset.get("name", preset.get("id", " "))),
                preset_id=preset.get("id", ""), kind=kind)


class SWAYFIELD_MT_grass_presets(bpy.types.Menu):
    bl_idname = "SWAYFIELD_MT_grass_presets"
    bl_label = strings.LBL_PRESET

    def draw(self, context) -> None:
        _draw_preset_menu(self.layout, "GRASS", "swayfield.apply_preset", "preset_id",
                          "SWAYFIELD_MT_delete_grass_preset")


class SWAYFIELD_MT_delete_grass_preset(bpy.types.Menu):
    bl_idname = "SWAYFIELD_MT_delete_grass_preset"
    bl_label = strings.MENU_DELETE_PRESET

    def draw(self, context) -> None:
        _draw_delete_menu(self.layout, "GRASS")


class SWAYFIELD_MT_wind_presets(bpy.types.Menu):
    bl_idname = "SWAYFIELD_MT_wind_presets"
    bl_label = strings.LBL_WIND_TYPE

    def draw(self, context) -> None:
        _draw_preset_menu(self.layout, "WIND", "swayfield.apply_wind_preset", "wind_id",
                          "SWAYFIELD_MT_delete_wind_preset")


class SWAYFIELD_MT_delete_wind_preset(bpy.types.Menu):
    bl_idname = "SWAYFIELD_MT_delete_wind_preset"
    bl_label = strings.MENU_DELETE_PRESET

    def draw(self, context) -> None:
        _draw_delete_menu(self.layout, "WIND")


def _wind_label(st: State) -> str:
    wind_id = getattr(st.layer, "wind_preset", "CUSTOM")
    if wind_id in ("", "CUSTOM"):
        return strings.LBL_CUSTOM
    for preset in _call("presets", "list_wind_presets", default=[]) or []:
        if preset.get("id") == wind_id:
            return str(preset.get("name", wind_id))
    return str(wind_id)


class SWAYFIELD_PT_wind(_LayerPanel, bpy.types.Panel):
    bl_idname = "SWAYFIELD_PT_wind"
    bl_label = strings.PANEL_WIND

    def draw(self, context) -> None:
        layout = self.layout
        st = layer_state(context)
        layout.menu("SWAYFIELD_MT_wind_presets", text=f"{strings.LBL_WIND_TYPE}: {_wind_label(st)}",
                    icon=icons.ICON_WIND)
        col = layout.column()
        draw_keys(col, st, ("intensity", "direction", "direction_object"))
        _op(col, "swayfield.add_direction_empty", text=strings.BTN_ADD_DIRECTION_EMPTY, icon=icons.ICON_EMPTY)
        draw_keys(col, st, ("base_lean",))
        col.separator()
        draw_keys(col, st, ("freeze", "mute_viewport"))


# ---------------------------------------------------------------------------
# 7. Effectors
# ---------------------------------------------------------------------------


class SWAYFIELD_OT_select_object(bpy.types.Operator):
    """Select an effector object and make it active"""

    bl_idname = "swayfield.select_object"
    bl_label = strings.BTN_SELECT
    bl_options = {"REGISTER", "UNDO"}

    name: bpy.props.StringProperty(name="Object", options={"SKIP_SAVE"})  # type: ignore[valid-type]

    def execute(self, context):
        ob = bpy.data.objects.get(self.name)
        if ob is None:
            self.report({"WARNING"}, "Object not found")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for other in context.view_layer.objects:
            other.select_set(False)
        try:
            ob.select_set(True)
            context.view_layer.objects.active = ob
        except RuntimeError:
            self.report({"WARNING"}, "Object is not in this view layer")
            return {"CANCELLED"}
        return {"FINISHED"}


def _effector_mod(ob):
    for mod in ob.modifiers:
        if mod.type == "NODES" and mod.node_group is not None and mod.node_group.name.startswith("SF_EffectorPoint"):
            return mod
    return None


def _draw_effector(layout: bpy.types.UILayout, ob) -> bool:
    mod = _effector_mod(ob)
    if mod is None:
        return False
    box = layout.box()
    row = box.row()
    row.label(text=ob.name, icon=icons.ICON_VORTEX)
    _op(row, "swayfield.select_object", text=strings.BTN_SELECT, icon=icons.ICON_SELECT, name=ob.name)
    col = box.column(align=True)
    for key, text in (("Type", strings.LBL_EFFECTOR_TYPE), ("Radius", strings.LBL_EFFECTOR_RADIUS),
                      ("Strength", strings.LBL_EFFECTOR_STRENGTH), ("Falloff", strings.LBL_EFFECTOR_FALLOFF)):
        try:
            compat.draw_input(col, mod, key, text=text)
        except KeyError:
            continue
    return True


class SWAYFIELD_PT_effectors(_LayerPanel, bpy.types.Panel):
    bl_idname = "SWAYFIELD_PT_effectors"
    bl_label = strings.PANEL_EFFECTORS
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context) -> None:
        layout = self.layout
        st = layer_state(context)
        grid = layout.grid_flow(row_major=True, columns=2, align=True)
        for text, icon, kind in ((strings.BTN_ADD_VORTEX, icons.ICON_VORTEX, "VORTEX"),
                                 (strings.BTN_ADD_BLAST, icons.ICON_BLAST, "RADIAL_BLAST"),
                                 (strings.BTN_ADD_TRAMPLE, icons.ICON_TRAMPLE, "TRAMPLE"),
                                 (strings.BTN_ADD_SHELTER, icons.ICON_SHELTER, "SHELTER")):
            _op(grid, "swayfield.add_effector", text=text, icon=icon, type=kind)
        coll = _get(st.mod, "effector_collection")
        shown = False
        if coll is not None:
            for ob in list(coll.objects):
                shown = _draw_effector(layout, ob) or shown
        if not shown:
            layout.label(text=strings.HINT_NO_EFFECTORS)


def _draw_exclusion(layout: bpy.types.UILayout, st: State) -> None:
    draw_keys(layout, st, ("exclusion_collection",))
    _op(layout, "swayfield.add_exclusion", text=strings.BTN_ADD_EXCLUSION, icon=icons.ICON_EXCLUDE)
    draw_keys(layout, st, ("exclusion_distance", "exclusion_falloff"))


# ---------------------------------------------------------------------------
# 8. Material
# ---------------------------------------------------------------------------


def _control_socket(mat, key: str):
    """Socket whose ``default_value`` holds the control, or None."""
    fn = _core("materials", "control_socket")
    if fn is None:
        return None
    try:
        return fn(mat, key)
    except (KeyError, IndexError):
        return None


def _current_mode(st: State, mat) -> int | None:
    mode = _mode_index(getattr(st.layer, "material_mode", None))
    if mode is None and mat is not None:
        mode = _mode_index(_call("materials", "get_mode", mat))
    return mode


def _draw_image_slots(layout: bpy.types.UILayout, mat) -> None:
    for slot in _core("materials", "IMAGE_SLOTS") or ():
        node = mat.node_tree.nodes.get(f"SF_Image_{slot}")
        if node is None:
            continue
        row = layout.row(align=True)
        image = node.image
        row.label(text=f"{slot}: {image.name if image is not None else strings.LBL_NO_IMAGE}")
        _op(row, "swayfield.pick_image", text="", icon=icons.ICON_IMAGE, slot=slot)
        if image is not None:
            _op(row, "swayfield.clear_image", text="", icon=icons.ICON_REMOVE, slot=slot)
    _op(layout, "swayfield.load_texture_set", text=strings.BTN_LOAD_TEXTURE_SET, icon=icons.ICON_IMAGE)


class SWAYFIELD_PT_material(_LayerPanel, bpy.types.Panel):
    bl_idname = "SWAYFIELD_PT_material"
    bl_label = strings.PANEL_MATERIAL
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context) -> None:
        layout = self.layout
        st = layer_state(context)
        mat = _call("layers", "layer_material", st.ob, st.layer)
        _proxy(layout, st, "material_mode", text=strings.LBL_MATERIAL_MODE)
        if mat is None or mat.node_tree is None:
            layout.label(text=strings.HINT_NO_MATERIAL)
        else:
            mode = _current_mode(st, mat)
            col = layout.column(align=True)
            for key, entry in (_core("materials", "CONTROL_INFO") or {}).items():
                if key == "mode":
                    continue
                label, _kind, control_mode = entry
                if control_mode is not None and control_mode != mode:
                    continue
                sock = _control_socket(mat, key)
                if sock is not None:
                    col.prop(sock, "default_value", text=label)
            if mode == 1:
                _draw_image_slots(layout, mat)
        if _is_instances(st):
            draw_keys(layout, st, ("instance_material_override",))


# ---------------------------------------------------------------------------
# 9. Performance
# ---------------------------------------------------------------------------


def _draw_budget(layout: bpy.types.UILayout, st: State) -> None:
    settings = getattr(bpy.context.scene, "swayfield", None)
    if settings is not None:
        layout.prop(settings, "budget", text=strings.LBL_BUDGET)
        if hasattr(settings, "auto_optimise_threshold"):
            layout.prop(settings, "auto_optimise_threshold", text=strings.LBL_AUTO_OPTIMISE)
    row = layout.row(align=True)
    _op(row, "swayfield.bake_scatter", text=strings.BTN_BAKE_SCATTER, icon=icons.ICON_BAKE)
    _op(row, "swayfield.free_bake", text=strings.BTN_FREE_BAKE, icon=icons.ICON_FREE)


class SWAYFIELD_PT_performance(_LayerPanel, bpy.types.Panel):
    bl_idname = "SWAYFIELD_PT_performance"
    bl_label = strings.PANEL_PERFORMANCE
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context) -> None:
        st = layer_state(context)
        draw_keys(self.layout.column(), st, ("optimised", "viewport_density", "display_mode"))


# ---------------------------------------------------------------------------
# Sub-panels and registration order
# ---------------------------------------------------------------------------

_SUB_PANELS = (
    _sub_panel("SWAYFIELD_PT_instances", strings.PANEL_INSTANCES, "SWAYFIELD_PT_distribution",
               ("instance_collection", "instance_scale_min", "instance_scale_max"), closed=False,
               condition=_is_instances),
    _sub_panel("SWAYFIELD_PT_clumping", strings.PANEL_CLUMPING, "SWAYFIELD_PT_blade_shape",
               ("clump_density", "clump_radius", "clump_pull"), closed=False),
    _sub_panel("SWAYFIELD_PT_wisps", strings.PANEL_WISPS, "SWAYFIELD_PT_blade_shape",
               ("wisp_percent", "wisp_length", "wisp_width")),
    _sub_panel("SWAYFIELD_PT_gusts", strings.PANEL_GUSTS, "SWAYFIELD_PT_wind",
               ("gust_strength", "gust_scale", "gust_stretch", "gust_speed", "gust_evolution", "gust_contrast"),
               closed=False),
    _sub_panel("SWAYFIELD_PT_direction_variation", strings.PANEL_DIRECTION_VARIATION, "SWAYFIELD_PT_wind",
               ("direction_variation", "direction_variation_speed")),
    _sub_panel("SWAYFIELD_PT_waves", strings.PANEL_WAVES, "SWAYFIELD_PT_wind",
               ("wave_strength", "wave_length", "wave_speed", "wave_sharpness")),
    _sub_panel("SWAYFIELD_PT_flutter", strings.PANEL_FLUTTER, "SWAYFIELD_PT_wind",
               ("flutter_strength", "flutter_frequency", "wisp_flutter")),
    _sub_panel("SWAYFIELD_PT_bend", strings.PANEL_BEND, "SWAYFIELD_PT_wind",
               ("max_bend", "stiffness", "tip_lag", "sway_mode")),
    _sub_panel("SWAYFIELD_PT_timing", strings.PANEL_TIMING, "SWAYFIELD_PT_wind",
               ("time_offset", "speed_multiplier")),
    _sub_panel("SWAYFIELD_PT_loop", strings.PANEL_LOOP, "SWAYFIELD_PT_wind", ("loop_enable", "loop_frames")),
    _sub_panel("SWAYFIELD_PT_exclusion", strings.PANEL_EXCLUSION, "SWAYFIELD_PT_effectors", closed=False,
               extra=_draw_exclusion),
    _sub_panel("SWAYFIELD_PT_culling", strings.PANEL_CULLING, "SWAYFIELD_PT_performance",
               ("frustum_cull", "render_cull", "cull_margin_viewport", "cull_margin_render",
                "cull_fov_override"), closed=False),
    _sub_panel("SWAYFIELD_PT_lod", strings.PANEL_LOD, "SWAYFIELD_PT_performance",
               ("lod_enable", "lod_near", "lod_mid", "lod_far", "lod_blend", "lod_mid_density", "lod_far_density",
                "lod_mid_width", "lod_far_width", "lod_mid_points", "lod_far_points")),
    _sub_panel("SWAYFIELD_PT_anim_lod", strings.PANEL_ANIM_LOD, "SWAYFIELD_PT_performance",
               ("anim_lod_enable", "anim_lod_start", "anim_lod_end")),
    _sub_panel("SWAYFIELD_PT_budget", strings.PANEL_BUDGET, "SWAYFIELD_PT_performance", closed=False,
               extra=_draw_budget),
)


def _ordered_classes() -> tuple:
    """Top-level panels in display order, each followed by its sub-panels."""
    tops = (SWAYFIELD_PT_main, SWAYFIELD_PT_layers, SWAYFIELD_PT_distribution, SWAYFIELD_PT_blade_shape,
            SWAYFIELD_PT_masks, SWAYFIELD_PT_wind, SWAYFIELD_PT_effectors, SWAYFIELD_PT_material,
            SWAYFIELD_PT_performance)
    result = []
    for cls in tops:
        result.append(cls)
        result.extend(sub for sub in _SUB_PANELS if sub.bl_parent_id == cls.bl_idname)
    return tuple(result)


CLASSES = (SWAYFIELD_OT_select_object, SWAYFIELD_MT_add_mask, SWAYFIELD_MT_grass_presets,
           SWAYFIELD_MT_delete_grass_preset, SWAYFIELD_MT_wind_presets, SWAYFIELD_MT_delete_wind_preset,
           *_ordered_classes())
