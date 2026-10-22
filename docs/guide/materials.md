# Materials

Every layer comes with a ready material built on Principled BSDF. Pick a **material mode** from one dropdown. Switching modes does not lose the settings of the other modes.

| Mode | What it is |
| --- | --- |
| **Procedural** (default) | Root-to-tip colour ramp, per-blade hue and value jitter, wind brightening, optional translucency |
| **Image Maps** | Your texture set: Base Color, Roughness, Normal, Opacity, Translucency and AO |
| **Single Color** | One colour, plus Variation and Roughness. Fast, good for stylised or toon looks |

## Procedural

The default colours are root shadow `#0B3A05`, mid `#3F7A12`, lit tip `#8BD63A` and far haze `#5E8F31`. Roughness is 0.45. A little translucency gives a backlit glow.

- **Wind brightening** blends toward a highlight colour where the grass is bent (default 0.6). Set it to 0 to turn it off.
- **Distance haze** blends toward the far colour with distance. You set the start and end distance.

## Image Maps

1. Set the material mode to **Image Maps**.
2. Click **Load Texture Set** and pick a folder.
3. Swayfield fills the slots by filename suffix.

| Slot | Suffixes it looks for |
| --- | --- |
| Base Color | `_albedo`, `_basecolor`, `_diff` |
| Roughness | `_rough` |
| Normal | `_nrm`, `_normal` |
| Opacity | `_opacity`, `_alpha` |
| Translucency | `_trans` |

Other names may work too, such as `_ao` for the AO slot. If a slot is not filled, set it by hand.

If your set has an opacity map, Swayfield switches the blade source to **Ribbons** for you, because opacity needs flat blades with UVs.

The image is tinted by the same root-to-tip gradient and wind brightening as the procedural look. Each has a strength slider, and 0 means the raw texture.

Swayfield ships two CC0 texture sets, a grass blade and a short lawn tuft, that you can use as they are.

## Single Color

Pick a colour. **Variation** (0 to 1) adds random difference between blades. Set the **Roughness**.

## Painted colour variation

Use **Paint Color Variation** (see [Painting and masks](painting-and-masks.md#other-maps)) to add dry or yellow patches. The painted map feeds the secondary tint.

## Attributes for your own shaders

Swayfield writes these attributes onto the grass. Read them with an **Attribute** node (type: Geometry) in your own shader.

| Attribute | Range | Meaning |
| --- | --- | --- |
| `sf_factor` | 0 to 1 | Position along the blade, root to tip |
| `sf_wind` | 0 to 1 | Current bend amount from wind. Drives brightening |
| `sf_random` | 0 to 1 | Stable random value per blade |
| `sf_variation` | 0 to 1 | Painted or noise colour-variation mask |
| `sf_clump` | 0 to 1 | Random value per clump, for patchy colour |
| `sf_dist` | metres | Distance to the active camera, for haze and LOD fades |

Assign your material to the layer's **Material** slot in the Material panel.

## Cycles and EEVEE

Materials work in both. In EEVEE, Ribbons use alpha-hashed opacity. Strands use hair-style rendering, so they stay light.

<!-- TODO: screenshot comparing the three material modes -->
