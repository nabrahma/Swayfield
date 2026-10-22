# Presets

A preset stores a look: blade shape, density, wind type and material colours. There are two kinds: **grass presets** (a whole look) and **wind types**.

## Built-in grass presets

| Preset | Blade length | Density | Wind | Notes |
| --- | --- | --- | --- | --- |
| **Rolling Meadow** (hero) | 0.5 to 0.9 m | 1,500/m² | Rolling Meadow | Reference look, wisps on |
| **Lawn** | 0.05 to 0.1 m | 6,000/m² | Gentle Breeze | Archviz, low lean |
| **Wild Field** | 0.3 to 1.2 m | 900/m² | Gentle Breeze | Strong clumping, colour variation |
| **Stormy Steppe** | 0.4 to 0.8 m | 1,200/m² | Storm | Dry tint |
| **Anime Field** | 0.4 to 0.6 m | 1,000/m² | Rolling Waves | Single Color material, saturated |

Pick one in the **Grass Preset** picker at the top of the Swayfield panel, then click **Add Grass**. The layer list shows the layer's preset name, or **Custom** once you change a look setting.

## Wind types

Open the **Wind Type** menu in the Wind panel to change the animation of the active layer without changing anything else. Your direction, time offset, loop and freeze settings stay.

There are eight: Rolling Meadow, Gentle Breeze, Storm, Rolling Waves, Vortex, Radial Blast, Trample Path and Toon Bob. Vortex, Radial Blast and Trample Path are designed to be used with an [effector](effectors.md) of the same kind.

## Saving your own

The Save Preset, Apply Grass Preset and Delete Preset operators exist, but 0.1.0 has no panel buttons for them yet. Run them from the Python console or a script:

```python
import bpy
bpy.ops.swayfield.save_preset('INVOKE_DEFAULT')       # opens a dialog
bpy.ops.swayfield.apply_preset(preset_id="USER_MY_LOOK")
```

User presets are JSON files in a `presets` folder in the extension's user data (`grass/` and `wind/` inside it). Their ids start with `USER_`. You can also drop a JSON file there by hand. Built-in presets cannot be deleted.

## The JSON format

Presets are plain text, so you can share them and keep them in version control. This is the built-in Anime Field preset:

```json
{
  "schema": 1,
  "id": "ANIME_FIELD",
  "name": "Anime Field",
  "description": "Stylised field in one saturated colour with regular rolling waves.",
  "wind": "ROLLING_WAVES",
  "inputs": {
    "density": 1000.0,
    "density_ceiling": 1200.0,
    "length_min": 0.4,
    "length_max": 0.6,
    "tip_taper": 0.8,
    "curl": 30.0,
    "rest_lean": 6.0,
    "random_tilt": 5.0,
    "wisp_percent": 0.0
  },
  "material": {
    "mode": 2,
    "single_color": "#4FD02A",
    "single_variation": 0.15,
    "single_roughness": 0.6,
    "wind_brighten": 0.6
  }
}
```

| Field | Meaning |
| --- | --- |
| `schema` | Preset format version (1) |
| `id` | Unique id. Built-ins are upper case, such as `ROLLING_MEADOW`. User presets start with `USER_` |
| `name` | Name shown in the picker |
| `description` | Short text for the tooltip |
| `wind` | (grass presets) the id of the wind type to apply first, or `null` |
| `effector` | (wind types) the effector kind the wind type goes with (`VORTEX`, `RADIAL_BLAST` or `TRAMPLE`), or `null` |
| `inputs` | Settings, keyed by the **Key** column in the [settings reference](../reference/settings.md). **Angles are in degrees.** Applied on top of the wind type |
| `material` | Material controls (below). Colours are `#RRGGBB` hex strings |

Only "look" settings can be in a preset: Distribution and Blade Shape settings, the wind type settings, and for grass presets `optimised` and `viewport_density`. Objects, collections, images, vertex group names, seeds, Mask Preview, and per-shot wind settings (direction, direction object, time offset, loop, freeze, mute) are never stored.

### Material keys

`mode` (0 Procedural, 1 Image Maps, 2 Single Color), `color_root`, `color_mid`, `color_tip`, `color_haze`, `color_highlight`, `wind_brighten`, `hue_jitter`, `value_jitter`, `color_variation`, `variation_strength`, `roughness`, `specular`, `translucency`, `haze_start`, `haze_end`, `haze_strength`, `single_color`, `single_variation`, `single_roughness`, `image_tint`, `image_wind`.

Colour keys (`color_*` and `single_color`) take hex strings. The rest are numbers: 0 to 1, except the haze distances which are in metres.
