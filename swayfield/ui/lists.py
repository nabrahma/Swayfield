# SPDX-License-Identifier: GPL-3.0-or-later
"""UI list of the layers on the active object."""

from __future__ import annotations

import bpy

from . import icons, strings


def _op(layout: bpy.types.UILayout, idname: str, text: str = "", icon: str = "NONE", **props):
    """Draw an operator button. Unknown property names raise; an unregistered operator draws nothing."""
    try:
        getattr(bpy.ops.swayfield, idname.split(".")[1]).get_rna_type()
    except (KeyError, AttributeError):
        return None
    pointer = layout.operator(idname, text=text, icon=icon)
    for key, value in props.items():
        setattr(pointer, key, value)
    return pointer


def layer_modifier(ob, layer):
    """The layer's modifier (on its grass object), or None."""
    try:
        from ..core import layers

        mod = layers.get_modifier(ob, layer)
        if mod is not None:
            return mod
    except Exception:
        pass
    grass = getattr(layer, "grass_object", None)
    holder = grass if grass is not None else ob
    return holder.modifiers.get(layer.modifier_name)


class SWAYFIELD_UL_layers(bpy.types.UIList):
    """Layer name, viewport and render visibility, and solo."""

    bl_idname = "SWAYFIELD_UL_layers"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        ob = data.id_data
        mod = layer_modifier(ob, item) if ob is not None else None
        row = layout.row(align=True)
        row.prop(item, "name", text="", emboss=False)
        sub = row.row(align=True)
        if mod is None:
            sub.label(text="", icon=icons.ICON_WARNING)
            return
        sub.prop(mod, "show_viewport", text="", emboss=False,
                 icon=icons.ICON_EYE_ON if mod.show_viewport else icons.ICON_EYE_OFF)
        sub.prop(mod, "show_render", text="", emboss=False,
                 icon=icons.ICON_RENDER_ON if mod.show_render else icons.ICON_RENDER_OFF)
        _op(sub, "swayfield.layer_solo", text="", icon=icons.ICON_SOLO, index=index)


CLASSES = (SWAYFIELD_UL_layers,)
