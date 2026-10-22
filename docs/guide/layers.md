# Layers

A **layer** is one set of grass: its own settings, masks, wind and material. A surface can hold several layers, for example Base Grass, Tall Wisps and Flowers.

Each layer is a Geometry Nodes modifier on the mesh. You can see them in the Modifiers tab, and every Swayfield slider maps to one modifier input.

## The layer list

The **Layers** section of the panel lists the layers on the active object. Each row has:

- **Eye**: show or hide the layer in the viewport.
- **Render**: include or exclude the layer in renders.
- **Solo**: show only this layer.

Buttons next to the list let you **add**, **duplicate**, **remove** and **reorder** layers. Click a row to make it the active layer. Every panel below the list edits the active layer.

## Several meshes at once

Select more than one mesh and click **Add Grass**. All of them get a layer that shares the same settings, and each mesh gets its own seed offset so the grass does not repeat. Use **Sync Linked** to copy changes from one to the others.

## Ideas for layer stacks

- **Base Grass** (short, dense) plus **Tall Wisps** (few, long, thin) with a different wind **Time Offset** so they do not move in lockstep.
- A **Lawn** layer with an exclusion collection around paths, and a **Wild Field** layer limited to a slope or altitude mask.

## Upgrading old layers

Swayfield versions its node groups. Files made with an older version keep working. To move a layer to the newest node group version, click **Upgrade Layer**.
