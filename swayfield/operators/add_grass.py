# SPDX-License-Identifier: GPL-3.0-or-later
"""Add Grass: one click turns every selected mesh into a grass surface (SC-01)."""

from __future__ import annotations

import uuid

import bpy
from bpy.props import EnumProperty, StringProperty

from ..core import budget, compat, layers, node_setup

#: Seed offset between the objects of one Add Grass call.
SEED_STEP = 9973
#: Seconds the first evaluation stays light before the preset's values are restored.
PREVIEW_SECONDS = 0.5
PREVIEW_DENSITY = 10.0
#: Most points the first evaluation may generate. Distribution runs before viewport thinning,
#: so on a huge surface the density itself is lowered for the first pass.
PREVIEW_POINTS = 150_000
DISPLAY_FULL = 0
DISPLAY_POINTS = 2

_FALLBACK_PRESETS = (
    ("ROLLING_MEADOW", "Rolling Meadow", "Tall rolling grass with long gusts"),
    ("LAWN", "Lawn", "Short, dense lawn"),
    ("WILD_FIELD", "Wild Field", "Tufted, uneven wild grass"),
    ("STORMY_STEPPE", "Stormy Steppe", "Dry grass in a storm"),
    ("ANIME_FIELD", "Anime Field", "Flat saturated colours"),
)

# Blender keeps only a pointer to dynamic enum items, so the list must stay alive.
_preset_items: list = []


def preset_items(self, context):
    """Dynamic items: the presets on disk, or a fixed list when the preset module is missing."""
    entries = []
    try:
        from ..core import presets
        entries = [(p["id"], p["name"], p.get("description", "")) for p in presets.list_grass_presets()]
    except (ImportError, AttributeError, OSError):
        pass
    entries = entries or _FALLBACK_PRESETS
    _preset_items[:] = [(pid, name, desc, "NONE", i) for i, (pid, name, desc) in enumerate(entries)]
    return _preset_items


def is_effector(ob: bpy.types.Object) -> bool:
    return any(m.type == "NODES" and m.node_group is not None and m.node_group.name.startswith("SF_EffectorPoint")
               for m in ob.modifiers)


def apply_preset(ob: bpy.types.Object, layer, mod: bpy.types.Modifier, preset_id: str) -> bool:
    """Apply a grass preset to a new layer. Returns False when presets are not available."""
    try:
        from ..core import presets
    except ImportError:
        return False
    try:
        data = presets.apply_grass_preset(mod, layers.layer_material(ob, layer), preset_id)
    except KeyError:
        return False
    layer.wind_preset = data.get("wind") or "CUSTOM"
    layers.mark_preset(ob, layer, preset_id)
    return True


#: Light first-pass state waiting to be restored by the timer.
_pending: list[dict] = []


def flush_density_preview() -> None:
    """Timer callback: put back the real display mode and viewport density after the light first pass."""
    plans = list(_pending)
    _pending.clear()
    for plan in plans:
        ob = bpy.data.objects.get(plan["object"])
        mod = ob.modifiers.get(plan["modifier"]) if ob is not None else None
        if mod is None or mod.node_group is None:
            continue
        compat.set_input(mod, "display_mode", plan["display_mode"])
        compat.set_input(mod, "viewport_density", plan["viewport_density"])
        compat.set_input(mod, "optimised", plan["optimised"])
        if plan["density"] is not None:
            compat.set_input(mod, "density", plan["density"])
            compat.set_input(mod, "density_ceiling", plan["density_ceiling"])
        # The preview changed look inputs, so the preset fingerprint must be taken again.
        surface = bpy.data.objects.get(plan["surface"])
        layer = next((x for x in layers.iter_layers(surface) if x.name == plan["layer"]), None) if surface else None
        if layer is not None and plan["preset"] and layer.preset == plan["preset"]:
            layers.mark_preset(surface, layer, plan["preset"])
    budget.invalidate()


class SWAYFIELD_OT_add_grass(bpy.types.Operator):
    bl_idname = "swayfield.add_grass"
    bl_label = "Add Grass"
    bl_description = "Add a grass layer to every selected mesh. The first view is light, then fills in"
    bl_options = {"REGISTER", "UNDO"}

    preset: EnumProperty(name="Preset", description="Grass look to start from", items=preset_items)
    layer_name: StringProperty(name="Layer Name", description="Name of the new layer", default="Base Grass")

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            cls.poll_message_set("Go back to Object mode first")
            return False
        return True

    def execute(self, context):
        surfaces = [ob for ob in context.selected_objects
                    if ob.type == "MESH" and not is_effector(ob) and not layers.is_grass_object(ob)]
        if not surfaces:
            self.report({"ERROR"}, "Select a mesh object first")
            return {"CANCELLED"}

        settings = context.scene.swayfield
        link_id = uuid.uuid4().hex[:8]
        # Counted before the new layers exist, so the guard never evaluates grass that is about to appear.
        existing = budget.scene_totals(context).viewport
        plans: list[dict] = []
        total_estimate = 0
        used_preset = True
        for i, ob in enumerate(surfaces):
            layer, mod = node_setup.create_layer(ob, self.layer_name, seed_offset=i * SEED_STEP, link_id=link_id)
            used_preset = apply_preset(ob, layer, mod, self.preset or "ROLLING_MEADOW") and used_preset

            # What the preset wants, to restore once the first light evaluation is done.
            full = int(budget.estimate_from_area(ob, compat.get_input(mod, "density")))
            total_estimate += full
            viewport_density = float(compat.get_input(mod, "viewport_density"))
            plans.append({
                "surface": ob.name,
                "layer": layer.name,
                "preset": layer.preset if layer.preset != "CUSTOM" else "",
                "object": layer.grass_object.name,
                "modifier": mod.name,
                "display_mode": int(compat.get_input(mod, "display_mode")),
                "viewport_density": viewport_density,
                "optimised": full > settings.auto_optimise_threshold,
                "density": None,
                "density_ceiling": None,
            })
            # A huge surface would still generate millions of points before thinning: lower the density
            # for the first pass only.
            ceiling = float(compat.get_input(mod, "density_ceiling"))
            generated = budget.estimate_from_area(ob, ceiling)
            if generated > PREVIEW_POINTS:
                factor = PREVIEW_POINTS / generated
                plans[-1]["density"] = float(compat.get_input(mod, "density"))
                plans[-1]["density_ceiling"] = ceiling
                compat.set_input(mod, "density", max(plans[-1]["density"] * factor, 1.0))
                compat.set_input(mod, "density_ceiling", max(ceiling * factor, 1.0))
            # Density preview: the first evaluation is light, so a huge mesh cannot lock the UI.
            compat.set_input(mod, "optimised", True)
            compat.set_input(mod, "viewport_density", PREVIEW_DENSITY)
            compat.set_input(mod, "display_mode", DISPLAY_POINTS)

        if existing + total_estimate > settings.budget:
            for plan in plans:
                plan["optimised"] = True
            self.report({"WARNING"}, f"About {total_estimate:,} blades is over your budget of "
                                     f"{settings.budget:,}. Optimised Mode stays on. Lower the density or raise "
                                     "the budget under Performance.")

        _pending.extend(plans)
        if not bpy.app.timers.is_registered(flush_density_preview):
            bpy.app.timers.register(flush_density_preview, first_interval=PREVIEW_SECONDS)
        if not used_preset:
            self.report({"INFO"}, "Presets are not available yet, so the default look was used")
        count = len(surfaces)
        self.report({"INFO"}, f"Added grass to {count} object" + ("s" if count != 1 else ""))
        return {"FINISHED"}


classes = (SWAYFIELD_OT_add_grass,)
