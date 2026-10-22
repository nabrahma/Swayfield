# Effectors

Effectors are small objects that push grass around locally, on top of the base wind. Use them for whirlwinds, shockwaves, characters walking through a field, and shelter behind walls. Swayfield fakes these forces. It is not a physics simulation.

## Adding an effector

In the **Effectors** panel, click **Vortex**, **Radial Blast**, **Trample** or **Shelter**. Swayfield creates a small object at the 3D cursor, in an `SF_Effectors` collection linked to the layer. In the viewport it shows a circle for its radius.

Each effector appears in the panel as a box with a **Select** button and four settings:

- **Type**: Vortex, Radial Blast, Trample or Shelter.
- **Radius**: how far it reaches, in metres.
- **Strength**: how hard it pushes.
- **Falloff**: how softly the force fades toward the edge of the radius.

All four are modifier inputs on the effector object, so you can keyframe them. Move, rotate and parent the object like any other.

<!-- TODO: screenshot of the Effectors panel -->

| Effector | What the grass does |
| --- | --- |
| **Vortex** | Swirls around the effector. Good for whirlwinds and magic effects |
| **Radial Blast** | Is flattened outward from the effector. Good for helicopter downdrafts and shockwaves |
| **Trample** | Bends away from the effector. Good for characters walking through |
| **Shelter** | Calms the wind behind a wall or rock |

### Matching wind types

Three wind types go with an effector: **Vortex**, **Radial Blast** and **Trample Path**. They calm the base wind so the effector reads clearly. When you pick one in the **Wind Type** menu and the layer has no effector of that kind, Swayfield reports a hint ("Add a Vortex effector from the Effectors panel"). The wind type works without the effector, but you will not see the effect.

### Radial Blast pulse

A new Radial Blast comes with its Strength already keyframed as a one-off pulse that starts at the current frame: 0, then 1 after 12 frames, then back to 0 after another 12. To change the shape, edit those keyframes in the Dope Sheet or Graph Editor, or change Strength yourself.

### Trample

Parent a Trample effector to a character's feet or root, or animate it along a path. Grass bends away within its radius. In 0.1.0 grass returns as soon as the effector moves away. A recovery time (grass slowly standing back up) is planned.

### Where effectors overlap

All effectors add together, using their horizontal distance to the grass. Two overlapping effectors both act on the grass between them.

## Exclusion objects

Exclusion objects remove grass around them, so grass does not poke through paths, props and buildings.

1. Select the grass surface, then Ctrl-click the objects that should stay clear (the grass surface stays active).
2. Click **Add Exclusion** in the **Exclusion** sub-panel of **Effectors**. The other selected objects join the layer's exclusion collection.
3. Set **Exclusion Distance**: grass is removed within this distance of those objects.
4. Set **Exclusion Falloff**: a band of shorter grass at the border, so the edge looks natural.
