# Changelog

All notable changes to Swayfield are recorded here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-22

First public release.

### Added

#### Scattering
- Add Grass operator: adds a non-destructive Geometry Nodes layer to every selected mesh. Several meshes share one system, each with its own seed offset.
- Several grass layers per surface, with add, duplicate, remove and reorder.
- Density in blades per square metre on world-space area, with a minimum root distance.
- Stable blade identity: masks and density thin a fixed set, so blades never reshuffle.
- Blade sources: Strands, Ribbons and Custom Instances.
- Blade shape controls: length, root width, tip taper, rest lean, curl, random tilt and rotation.
- Clumping and a wisp sub-layer.
- Follow Normal blend between surface normal and world up.
- Exclusion objects with a falloff band.
- Bake Scatter and Free Bake.
- Works on the evaluated surface, so modifiers below Swayfield are respected.

#### Painting and masks
- Paint Density, Length, Wind Strength and Color Variation, with one vertex group per map.
- Invert, Contrast and Threshold for every painted map.
- Mask stack with Slope, Altitude, Noise, Image, Proximity and Camera Distance masks, combined by Multiply, Add, Subtract or Min.
- Length falloff, so mask edges look natural.
- Mask Preview overlay.
- Low-vertex note with a one-click Subdivide suggestion.

#### Materials
- Procedural, Image Maps and Single Color material modes, switchable without losing settings.
- Load Texture Set: fills image slots from a folder by filename suffix.
- Wind brightening and distance haze.
- Public attributes for custom shaders: `sf_factor`, `sf_wind`, `sf_random`, `sf_variation`, `sf_clump`, `sf_dist`.
- Bundled CC0 grass blade and short-lawn texture sets.
- Cycles and EEVEE support.

#### Wind
- Rolling Meadow hero wind, plus Gentle Breeze, Storm, Rolling Waves and Toon Bob.
- Intensity, direction angle or direction empty, time offset and speed multiplier.
- Seamless loop mode, Freeze Wind and viewport Mute.
- Animation LOD: far blades rock instead of bending.
- Motion-blur-safe blade order.

#### Effectors
- Vortex, Radial Blast, Trample and Shelter effectors.

#### Performance
- Optimised Mode with viewport density and Full / Strands Lite / Points / Bounds display.
- Camera frustum culling with separate viewport and render margins.
- Near, mid and far LOD bands.
- Blade counter, budget guard (default 2 million blades) and a light first evaluation after Add Grass.
- Support for Blender's Simplify setting.

#### UI
- A single Swayfield tab in the 3D Viewport sidebar.
- Five built-in grass presets, and user presets saved as JSON.
- Quick Look: test camera, sun and AgX Punchy grade.
- Upgrade Layer operator for future node group versions.

#### Tooling
- Every setting declared once in `swayfield/core/spec.py`.
- Test suite that runs inside Blender (`tools/run_tests.py`).
- GitHub Actions CI.
- MkDocs documentation site with a generated settings reference.

### Not included yet

Texture-paint masks, edge offset, Apply and Alembic export, viewport-follow culling, season slider, pause wind while navigating, trample recovery time. See the [roadmap](https://nabrahma.github.io/Swayfield/roadmap/).

[Unreleased]: https://github.com/nabrahma/Swayfield/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/nabrahma/Swayfield/releases/tag/v0.1.0
