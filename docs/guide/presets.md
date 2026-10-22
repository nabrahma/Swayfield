# Presets

A preset stores a whole look: blade shape, density, wind and material. Pick one from the preset picker when you add grass, or apply one to an existing layer.

## Built-in presets

| Preset | Blade length | Density | Wind | Notes |
| --- | --- | --- | --- | --- |
| **Rolling Meadow** (hero) | 0.5 to 0.9 m | 1,500/m² | Rolling Meadow | Reference look, wisps on |
| **Lawn** | 0.05 to 0.1 m | 6,000/m² | Gentle Breeze | Archviz, low lean |
| **Wild Field** | 0.3 to 1.2 m | 900/m² | Gentle Breeze | Strong clumping, colour variation |
| **Stormy Steppe** | 0.4 to 0.8 m | 1,200/m² | Storm | Dry tint |
| **Anime Field** | 0.4 to 0.6 m | 1,000/m² | Rolling Waves | Single Color material, saturated |

## Wind presets

Wind types (Rolling Meadow, Gentle Breeze, Storm, Rolling Waves, Toon Bob) are presets too. You can change the wind type without changing the rest of the grass. Editing any slider marks the preset as **Custom**.

## Saving your own

1. Set the layer up the way you like.
2. Click **Save Preset** and type a name.

User presets are saved as JSON files in Blender's user config folder, so they are there in every file. Use **Delete Preset** to remove one. Built-in presets cannot be deleted.

## The JSON format

Presets are plain text. You can share them, edit them and keep them in version control.

```json
{
  "schema": 1,
  "id": "my_tall_meadow",
  "name": "My Tall Meadow",
  "description": "Tall, dense grass with a strong breeze.",
  "wind": "ROLLING_MEADOW",
  "effector": null,
  "inputs": {
    "density": 1200,
    "length_min": 0.6,
    "length_max": 1.1,
    "rest_lean": 12,
    "max_bend": 80,
    "base_lean": 0.6
  },
  "material": {
    "mode": "PROCEDURAL",
    "root_color": "#0B3A05",
    "mid_color": "#3F7A12",
    "tip_color": "#8BD63A"
  }
}
```

!!! warning "Example only"
    The block above shows the shape of the format. The exact set of fields inside `wind`, `effector` and `material` can grow between versions. Open a built-in preset or save one yourself to see what the current version writes.

| Field | Meaning |
| --- | --- |
| `schema` | Preset format version |
| `id` | Short unique name, lowercase with underscores. Also the file name |
| `name` | Name shown in the picker |
| `description` | Short text shown as a tooltip |
| `wind` | The wind type the preset uses |
| `effector` | Effector settings, or `null` for none |
| `inputs` | Settings, keyed by the **Key** column in the [settings reference](../reference/settings.md). **Angles are written in degrees** (the modifier stores radians, Swayfield converts) |
| `material` | Material mode and colours. Colours are hex strings such as `#8BD63A` |

Settings you leave out of `inputs` are left alone when the preset is applied.
