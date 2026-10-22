# Swayfield

**One-click animated grass for Blender, with wind you can art-direct.**

[![CI](https://github.com/nabrahma/Swayfield/actions/workflows/ci.yml/badge.svg)](https://github.com/nabrahma/Swayfield/actions/workflows/ci.yml)
[![Licence: GPL-3.0-or-later](https://img.shields.io/badge/licence-GPL--3.0--or--later-blue.svg)](LICENSE)
[![Blender 4.2+](https://img.shields.io/badge/Blender-4.2%2B-orange.svg)](https://www.blender.org/)

<!-- TODO: hero GIF of the Rolling Meadow preset in motion -->

Select a mesh, click **Add Grass**, press play. Swayfield grows long, soft grass with a strong crosswind, bright gust streaks racing across the field and crests that glow where the grass is bent flat. It is all Geometry Nodes, so it stays non-destructive.

Version 0.1.0 is the first public release.

## What it does

- **One-click grass.** Works on any mesh. Select several meshes and they share one system.
- **Rolling Meadow wind.** The hero preset: a strong crosswind, travelling gust streaks, wisps whipping above the canopy, and shading that brightens where blades bend. Five wind types in all, plus effectors (Vortex, Radial Blast, Trample, Shelter).
- **Painting and masks.** Paint density, length, wind strength and colour variation with Blender's own Weight Paint tools. Stack slope, altitude, noise, image, proximity and camera-distance masks on top.
- **Three material modes.** Procedural (ready to render), Image Maps (load a texture folder and the slots fill themselves) or Single Color (fast, stylised).
- **Optimised Mode.** Keeps the viewport interactive on big fields with a density subset, points display, camera culling and distance bands. Final renders stay full quality.
- **Renders without the add-on.** Everything lives in Geometry Nodes groups and materials saved inside your .blend. Send the file to a colleague or a render farm and it opens and renders, even if Swayfield is not installed there.

<!-- TODO: screenshot of the Swayfield sidebar panel -->

## Quick start

1. Install Swayfield (see [Install](#install)).
2. Select a mesh, such as a hill or a plane.
3. Open the **Swayfield** tab in the 3D Viewport sidebar (press `N`) and click **Add Grass**.
4. Pick the **Rolling Meadow** preset.
5. Press play. Click **Quick Look** to add a test camera, a sun and the Punchy colour grade for a good first render.

The full walkthrough is in the [Quick start](https://nabrahma.github.io/Swayfield/getting-started/quick-start/).

## Features

**Scattering**

- Density in blades per square metre, measured on world-space area (scaling the mesh keeps the look)
- Stable blades: painting or lowering density removes blades and never reshuffles the rest
- Strands, Ribbons or Custom Instances (your own meshes from a collection)
- Blade shape, clumping, wisps, and a blend between surface normal and world up
- Several grass layers per surface, each with its own settings, masks and material
- Exclusion objects
- Bake Scatter, so heavy masks are not re-evaluated every frame

**Painting and masks**

- Paint Density, Length, Wind Strength and Colour Variation maps, each with Invert, Contrast and Threshold
- Mask stack with Multiply, Add, Subtract and Min blending
- Mask Preview overlay

**Wind and effectors**

- Rolling Meadow, Gentle Breeze, Storm, Rolling Waves and Toon Bob
- Intensity, direction angle or direction empty, time offset and speed per layer
- Seamless loop mode, Freeze Wind and viewport Mute
- Vortex, Radial Blast (keyframe it for a one-off pulse), Trample and Shelter effectors

**Performance**

- Viewport density %, and Full / Strands Lite / Points / Bounds display
- Camera frustum culling with separate viewport and render margins
- Near, mid and far LOD bands, and animation LOD
- Blade counter, budget guard and Blender Simplify support

## Presets

| Preset | Blade length | Density | Wind | Notes |
| --- | --- | --- | --- | --- |
| Rolling Meadow (hero) | 0.5 to 0.9 m | 1,500/m² | Rolling Meadow | Reference look, wisps on |
| Lawn | 0.05 to 0.1 m | 6,000/m² | Gentle Breeze | Archviz, low lean |
| Wild Field | 0.3 to 1.2 m | 900/m² | Gentle Breeze | Strong clumping, colour variation |
| Stormy Steppe | 0.4 to 0.8 m | 1,200/m² | Storm | Dry tint |
| Anime Field | 0.4 to 0.6 m | 1,000/m² | Rolling Waves | Single Color material, saturated |

You can save your own presets as JSON files. See [Presets](https://nabrahma.github.io/Swayfield/guide/presets/).

## Install

Swayfield is a Blender 4.2+ extension.

1. Download the zip from [GitHub Releases](https://github.com/nabrahma/Swayfield/releases). Do not unzip it.
2. In Blender, open **Edit > Preferences > Get Extensions**.
3. Open the dropdown at the top right, choose **Install from Disk** and pick the zip. Dragging the zip into the Blender window also works.
4. Make sure Swayfield is enabled. The **Swayfield** tab appears in the 3D Viewport sidebar.

Swayfield has no dependencies and makes no network calls.

Tested on Blender 5.2 LTS. Blender 4.2 LTS is the declared minimum and is verified by CI.

## Documentation

Full docs: **https://nabrahma.github.io/Swayfield/**

## Development

Swayfield is a thin Python add-on around versioned Geometry Nodes groups. The architecture is in [docs/architecture.md](docs/architecture.md), and every setting is declared once in `swayfield/core/spec.py`.

To work on the add-on, point Blender at the `swayfield/` folder: symlink it into a local extension repository, or add a local extension repository (**Preferences > Get Extensions > Repositories**) that points at it.

Run the tests (Blender must be on your PATH):

```
blender -b --factory-startup --python-exit-code 1 --python tools/run_tests.py
```

Regenerate the settings reference after changing `spec.py`:

```
python tools/gen_settings_reference.py
```

## Roadmap

Not in 0.1.0 yet: texture-paint masks, edge offset, Apply and Alembic export, viewport-follow culling, a season slider, pause-wind-while-navigating, and trample recovery time. See the [roadmap](https://nabrahma.github.io/Swayfield/roadmap/).

## Contributing

Bug reports, test scenes and pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) first.

## Licence

The add-on code is GPL-3.0-or-later. Bundled textures are CC0. See [LICENSE](LICENSE).

Made by Nabaskar Brahma.
