# Performance

Dense, long grass is heavy. **Optimised Mode** keeps the viewport interactive while leaving final renders at full quality. It works because Geometry Nodes can tell the viewport from a render, so these savings apply to the viewport only, unless a setting says otherwise.

Turn it on with the **Optimised Mode** toggle near the top of the panel. Add Grass turns it on automatically if the scene would go over 500,000 blades.

## What Optimised Mode changes

| Technique | In the viewport | At render |
| --- | --- | --- |
| **Viewport Density** | Shows a stable subset of blades (default 20%). Blades are widened so the field stays readable | No change |
| **Display As** | Full, Strands Lite (3 points, rigid sway), Points (one dot per blade, coloured like the material) or Bounds (just the layer's box) | No change |
| **Camera Culling** | Removes blades outside the active camera's view plus a margin (default 10%) | Optional, on by default with a 15% margin |
| **Distance LOD bands** | Near: full blades. Mid: 50% of blades, 4 points, 1.4x wider. Far: 10% of blades, 2 points, 2.5x wider | Same bands, with your distances |
| **Animation LOD** | Far blades rock instead of bending | Same |
| **Bake Scatter** | Placement and masks cached, only wind is evaluated each frame | Same |
| **Keep instances** | Custom Instances stay instanced and are never turned into real geometry | Same |

## LOD bands

Grass is split into three bands by distance from the camera.

| Setting | Default | Meaning |
| --- | --- | --- |
| Near Distance | 15 m | Closer than this is full detail |
| Mid Distance | 40 m | Between Near and this is mid detail |
| Far Distance | 150 m | Beyond this, blades are removed (0 keeps them at any distance) |
| Band Blend | 3 m | Width of the blend between bands |
| Mid Density / Far Density | 50% / 10% | Share of blades kept |
| Mid Width / Far Width | 1.4x / 2.5x | Wider blades keep coverage |
| Mid Points / Far Points | 4 / 2 | Points per blade |

Switch **Distance LOD** off if you see bands in a wide shot, or raise the distances.

## Culling margins

Camera culling removes blades you cannot see. A margin keeps a border of extra blades around the view so blades do not pop in at the frame edges when the camera moves or when motion blur is on.

- **Viewport Margin** (default 10%)
- **Render Margin** (default 15%). **Render Culling** is on by default.

If you see pop-in or gaps at the edges, raise the margin. See [Troubleshooting](../troubleshooting.md#blades-pop-in-at-the-frame-edges).

Culling reads the camera lens through hidden inputs that Swayfield keeps in sync. If a setup breaks that (a linked camera, say), set **Culling FOV Override** to a fixed horizontal field of view.

## Safeguards

- **Blade counter**: live viewport count and estimated render count per layer and in total.
- **Budget guard**: default 2 million blades in the viewport. If a change would go over, Swayfield warns you and offers to switch on Optimised Mode or lower density, instead of freezing Blender. Change the budget in the scene settings.
- **Light first evaluation**: right after Add Grass, grass starts as a light points preview at 10% density (lower still on very large surfaces), then fills in, so a huge mesh does not lock the UI.
- **Simplify**: Swayfield respects Blender's Simplify panel and scales viewport density by its child-particle percentage.

## Indicative measurements

These numbers come from one development machine (Blender 5.2, CPU evaluation of the node tree). They are not frame rates and not guarantees. Your scene and hardware will differ.

| Case | Time |
| --- | --- |
| 50 m x 50 m field at 20% viewport density | about 0.1 s |
| 200 m x 200 m terrain at 20% viewport density | under 1 s |
| Add Grass on a 60 m field | about 1 s |
| Full-density render evaluation of about 2 million blades | roughly 15 to 20 s |

In Optimised Mode the viewport places blades at the Viewport Density directly and skips the minimum-distance pass, which is where most of the time goes. That is why the viewport is so much faster than a full-density evaluation. The slow full-density pass is the reason **Bake Scatter** matters for renders.

## Bake Scatter

Click **Bake Scatter** to cache the static part of the system (blade placement and masks). Only the wind is calculated each frame afterwards. This helps most when you use many masks or a dense surface. Bake Scatter always bakes at full density, even when Optimised Mode is on. The wind itself is not baked. Click **Free Bake** to edit masks or density again.

## Quick fixes for a slow viewport

1. Turn on Optimised Mode.
2. Set **Display As** to Points or Strands Lite while you work.
3. Lower **Viewport Density**.
4. Turn on **Mute in Viewport** for wind when you are not judging motion.
5. Use Bake Scatter once the layout is final.
