# Layers

A **layer** is one set of grass: its own settings, masks, wind and material. A surface can hold several layers, for example Base Grass, Tall Wisps and Flowers.

Each layer is its own **hair Curves object** named `SF_<surface>_<layer>`, parented to the surface mesh and carrying the Swayfield modifier. Cycles and EEVEE only render curves as hair on a Curves object, which is why grass is a separate object rather than a modifier on your mesh.

The modifier reads your surface through its **Surface** input. That includes all of the surface's own modifiers (for example Subdivision or Displace) and its vertex groups, so you do not need to order anything.

Grass objects are not selectable by default, so clicking the terrain picks the terrain. The Swayfield panel works whether the surface or the grass object is active. Every Swayfield slider maps to one modifier input, so you can also open the modifier on the grass object.

Files still render without the add-on, because the node groups and materials are saved in the .blend.

## The layer list

The **Layers** section of the panel lists the layers on the active object. Each row has:

- **Eye**: show or hide the layer in the viewport.
- **Render**: include or exclude the layer in renders.
- **Solo**: show only this layer. Click it again to show all layers.

Buttons next to the list let you **add layer**, **duplicate layer**, **remove layer** and **move up** or **down**. Click a row to make it the active layer. Every panel below the list edits the active layer.

## Several meshes at once

Select more than one mesh and click **Add Grass**. All of them get a layer that shares the same settings, and each mesh gets its own seed offset so the grass does not repeat. Use **Sync Linked** to copy changes from one to the others.

## Ideas for layer stacks

- **Base Grass** (short, dense) plus **Tall Wisps** (few, long, thin) with a different wind **Time Offset** so they do not move in lockstep.
- A **Lawn** layer with an exclusion collection around paths, and a **Wild Field** layer limited to a slope or altitude mask.

## Upgrading old layers

Swayfield versions its node groups. Files made with an older version keep working. To move a layer to the newest node group version, click **Upgrade Layer**.
