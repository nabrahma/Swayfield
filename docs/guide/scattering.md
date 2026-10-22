# Scattering

The **Distribution** and **Blade Shape** panels control where blades grow and what they look like. Each setting has a tooltip in Blender. Full details of every setting are in the [settings reference](../reference/settings.md).

## Density

**Density** is blades per square metre, measured on the world-space area of the surface. If you scale the object, the grass keeps the same look. The default is 800 per m² and the range is 1 to 20,000.

Behind the scenes Swayfield generates blades once at **Generation Density** (default 2,000 per m²) and then thins that fixed set with the Density slider and your masks. That is why painting or lowering density only removes blades. The ones that remain never move or reshuffle. Keep Generation Density at or a little above Density. If you want more than 2,000 blades per m², raise Generation Density too.

**Minimum Distance** keeps roots from piling up on top of each other.

**Seed** changes the random placement.

## Blade source

| Source | What it is | Best for |
| --- | --- | --- |
| **Strands** (default) | Curves rendered as thin hair strands | Long, soft, dense grass. Lightest on memory |
| **Ribbons** | Flat tapered mesh strips with UVs (U across the blade, V from root 0 to tip 1) | Image textures with opacity, close-ups |
| **Custom Instances** | Your own meshes from a collection, kept instanced | Photoscanned tufts, flowers, stylised grass |

For Custom Instances, put your meshes in a collection and pick it as the **Instance Collection**. Use **Instance Scale Min** and **Max** for size variety. By default each mesh keeps its own material. Turn on **Override Instance Material** to use the layer material instead.

## Blade shape

- **Length Min / Max**: shortest and longest blade, in metres.
- **Root Width** and **Tip Taper**: how wide the blade is at the root, and how much it narrows. A taper of 1 ends in a sharp point.
- **Rest Lean**: how far blades lean before any wind.
- **Curl**: extra bend that builds from root to tip.
- **Random Tilt** and **Random Rotation**: variety between blades.
- **Blade Points**: points per blade in the near band. More points make smoother bends.

## Clumps and wisps

- **Clump Density**, **Clump Radius** and **Clump Pull** make a tufted look. Pull moves blade tips toward the clump centre.
- **Wisps** (default 3%) are longer, thinner blades that flutter harder, so loose strands whip above the canopy. Tune them with **Wisp Length** and **Wisp Width**.

## Growth direction

**Follow Normal** blends between growing straight up (0) and along the surface normal (1). The default is 0.2, so grass on a slope still grows mostly upward.

## Other modifiers on the surface

Swayfield works on the evaluated surface, so modifiers such as Subdivision or Displace change where grass grows. Blender runs the modifier stack from top to bottom, so put those modifiers **above** the Swayfield modifier if you want the grass to follow the final shape.

## Bake Scatter

Heavy masks can be slow to re-evaluate. **Bake Scatter** caches the static half (placement and masks) so only the wind is calculated each frame. Use **Free Bake** to clear it, for example before you repaint.
