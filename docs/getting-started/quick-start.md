# Quick start

Get to the Rolling Meadow look in about 60 seconds.

## Before you start

- Swayfield is [installed](installation.md).
- You have a mesh to grow grass on. A hill, a subdivided plane or a terrain all work.

## Steps

1. **Select the mesh.** Click it in the viewport.
2. **Open the Swayfield tab.** Hover over the 3D Viewport and press `N`, then click the **Swayfield** tab.
3. **Click Add Grass.** A grass layer appears. The first view is light on purpose (reduced density, points) so a large mesh never freezes Blender, and it fills in right after.
4. **Pick the Rolling Meadow preset** from the preset picker at the top of the panel. This sets blade length, density, material and the hero wind.
5. **Press play** (`Space`). Grass leans hard to the right, and bright streaks race across the field.

<!-- TODO: screenshot of the Swayfield panel after step 4 -->

## Make your first render look good

Click **Quick Look**. It adds a test camera at 1 m height, a sun, and the AgX Punchy colour grade. Then press `F12`.

## Next steps

| I want to... | Do this |
| --- | --- |
| Change the wind direction | In the **Wind** panel, set **Direction**, or [pick a direction empty](../guide/wind.md#direction) |
| Try calmer or wilder wind | Change the animation type to Gentle Breeze or Storm |
| Keep a path free of grass | [Paint Density](../guide/painting-and-masks.md) and paint black |
| Use my own grass textures | [Material mode: Image Maps](../guide/materials.md) |
| Keep the viewport smooth | Switch on [Optimised Mode](../guide/performance.md) |
| Make a looping clip | [Seamless loops](../guide/wind.md#seamless-loops-for-social-media) |

!!! tip "If playback is slow"
    Turn on **Optimised Mode** in the header. It affects the viewport only. Renders stay full quality.
