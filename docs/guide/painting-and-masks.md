# Painting and masks

Control where grass grows, how long it is and where wind is weaker. You paint with Blender's own Weight Paint tools. Swayfield adds no custom brush.

## Paint workflow

1. Select the mesh and the layer you want to edit.
2. In the **Masks** panel, click **Paint Density**.
3. Swayfield creates a vertex group named `SF_<layer>_density`, filled with weight 1.0 so nothing disappears. It links the group to the layer and switches to Weight Paint mode.
4. Paint with the normal brushes. **Black removes grass, white restores it, grey thins it.** The grass updates as you paint. In Optimised Mode it shows as points while you paint, for speed.
5. Click **Done** to return to Object mode.

<!-- TODO: GIF of painting a path through a field -->

Weight 0.3 keeps about 30% of the blades. Because blades are thinned from a fixed set, painting never reshuffles the grass that stays.

### Other maps

| Button | Controls | Typical use |
| --- | --- | --- |
| **Paint Density** | How many blades grow | Paths, bare patches |
| **Paint Length** | Blade length | Mown paths, longer grass at field edges |
| **Paint Wind Strength** | How strongly wind affects the grass | Shelter behind walls and rocks |
| **Paint Color Variation** | The material's secondary tint | Dry or yellow patches |

Each map has its own vertex group (`SF_<layer>_length`, `_wind`, `_variation`). You can also pick any existing vertex group from the dropdown.

### Sharpening soft strokes

Every painted map has three sliders:

- **Invert**: swap painted and unpainted areas.
- **Contrast**: sharpen or soften the map around 0.5. Raise it to turn a soft brush into a crisp edge.
- **Threshold**: weights below this value become 0.

!!! note "Few vertices?"
    Weights are painted on vertices, so a surface with big polygons gives coarse results. If the surface has fewer than about one vertex per 25 cm, the panel shows a note with a one-click **Subdivide** suggestion. It adds a Subdivision modifier ahead of Swayfield so painting gets finer. For very low-poly surfaces, subdivide first, or use an Image mask. (Texture-paint masks are not in 0.1.0.)

## The mask stack

Masks stack like layers. You can mix painting, slope and noise without touching nodes. Each mask has an enable toggle and a **Blend** mode that says how it combines with the masks above it.

| Blend | Result |
| --- | --- |
| **Multiply** (default) | Grass must pass both masks. Good for "paint, but only on gentle slopes" |
| **Add** | Grass appears where either mask allows it |
| **Subtract** | Removes grass where this mask is strong |
| **Min** | Keeps the lower of the two |

Available masks:

- **Vertex Group** (the painted maps above)
- **Slope**: grass grows between a minimum and maximum surface angle, with a smooth transition.
- **Altitude**: grass grows between a minimum and maximum world height.
- **Noise**: patchy coverage. Set scale, contrast, coverage and seed.
- **Image**: a black-and-white image read through the surface UVs. White keeps grass.
- **Proximity**: keep grass near a collection of objects, or away from them when inverted.
- **Camera Distance**: keep grass between two distances from the camera.

**Length Falloff** also shortens blades in thinned areas, so mask edges look natural rather than cut.

## Mask Preview

Turn on **Mask Preview** to see the final density as a black-to-white overlay on the surface. Black means no grass, white means full density. Use it to check what your masks add up to. Turn it off before rendering.

## Tips

- Paint with a large soft brush, then raise **Contrast** for a clean edge.
- For a path, paint black in the centre and grey at its edges, and add **Length Falloff** so grass gets shorter near the path.
- To keep grass off props instead of painting around them, use [exclusion objects](effectors.md#exclusion-objects).
