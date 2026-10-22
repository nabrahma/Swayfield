# FAQ

## Which Blender versions work?

Blender 4.5 LTS and newer. The test suite runs on Blender 4.5 LTS and 5.2 LTS in CI.

## Do I need Swayfield installed to render a file?

No. Node groups and materials are saved inside the .blend, so the file opens and renders on any machine, including render farms. The grass is a hair Curves object with a Geometry Nodes modifier, so without the add-on you can still change settings in the modifier panel. You just do not get the Swayfield sidebar.

## Does it work with Cycles and EEVEE?

Yes, for final renders. Workbench and Material Preview work in the viewport.

## Is it free?

Swayfield is open source under GPL-3.0-or-later. The bundled textures are CC0.

## Does it phone home?

No. It has no dependencies and makes no network calls.

## Can I use it on several objects at once?

Yes. Select them all and click Add Grass. They share one system, each with its own seed offset.

## Why does lowering density never move the remaining grass?

Swayfield makes blades once at a fixed maximum and only thins them. See [Scattering](guide/scattering.md#density).

## Can I raise density above 2,000 blades per m²?

Yes. Raise **Generation Density** to match, or the extra density has no blades to show.

## Does it simulate physics?

No. Wind is procedural. Effectors fake collision. Nothing needs baking.

## Can I use my own grass meshes?

Yes. Set Blade Source to **Custom Instances** and pick a collection.

## Can I export to Alembic or other software?

Not in 0.1.0. See the [roadmap](roadmap.md).

## Does the wind loop?

Yes. Turn on **Loop** and set the loop length in frames. See [Wind](guide/wind.md#seamless-loops-for-social-media).

## Where are my presets saved?

In Blender's user config folder, as JSON files. See [Presets](guide/presets.md).

## How do I report a bug?

Open an issue on [GitHub](https://github.com/nabrahma/Swayfield/issues). Include your Blender version, your operating system and, if you can, a small .blend that shows the problem.
