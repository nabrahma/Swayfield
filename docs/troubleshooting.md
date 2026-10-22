# Troubleshooting

## The viewport is slow

1. Turn on **Optimised Mode** in the panel header.
2. Set **Display As** to Points or Strands Lite while you work.
3. Lower **Viewport Density**.
4. Turn on **Mute in Viewport** for wind.
5. Use **Bake Scatter** once the layout is final.
6. Check the **blade counter**. If it is far over your budget (default 2 million), lower density or shorten the far band.

See [Performance](guide/performance.md).

## Grass is missing after painting

- **You painted black.** Black removes grass. Paint white to bring it back, or turn on **Mask Preview** to see the final density.
- **The vertex group is empty or wrong.** Check that the right group is linked in the Masks panel. A new group starts at weight 1.0.
- **Threshold or Invert is set.** A high Threshold zeroes light weights. Invert flips painted and unpainted areas.
- **A mask is hiding it.** Check Slope, Altitude, Noise and the other masks. Each enabled mask must allow grass.
- **The surface has few vertices.** Weights are per vertex, so a coarse mesh gives coarse results. Use the **Subdivide** button in the note (it subdivides the mesh itself).
- **A bake is active.** Click **Free Bake** after changing masks.

## Blades pop in at the frame edges

Camera culling removes blades outside the view. Blades can appear suddenly when the camera moves or when motion blur is on.

Fix: raise **Viewport Margin** or **Render Margin** (defaults 10% and 15%). Or turn off **Render Culling** for that layer.

If culling looks wrong with a linked camera or an unusual setup, set **Culling FOV Override** to a fixed field of view.

## Grass looks like bands or patches in the distance

These are the LOD bands. Raise **Near Distance** and **Mid Distance**, increase **Band Blend**, or turn off **Distance LOD**.

## I opened a file and there is no Swayfield panel

The file was made with Swayfield and the add-on is not installed or enabled here. The grass still works and renders. Settings are in the Geometry Nodes modifier on the grass object (`SF_<surface>_<layer>`). Install Swayfield to get the full panel.

## The wind does not move

- Check that **Freeze Wind** and **Mute in Viewport** are off.
- Check that **Intensity** is above 0.
- The timeline must be playing, or scrubbed. Wind follows scene time.

## The wind blows the wrong way

Change **Direction**, or use a direction empty. 0° blows toward +X. Rolling Meadow reads as left to right for a camera looking along +Y.

## I click the terrain and cannot select the grass

That is on purpose. Grass objects are not selectable by default, so clicking the terrain picks the terrain. The Swayfield panel works with the terrain active. To reach the grass object, use the Outliner.

## Add Grass says to select a mesh

Swayfield works on mesh objects. Select a mesh (not an empty, a curve or a camera) and try again.

## Still stuck?

Open an issue on [GitHub](https://github.com/nabrahma/Swayfield/issues) with your Blender version and a small .blend if you can.
