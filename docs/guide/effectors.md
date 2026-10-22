# Effectors

Effectors are objects that push grass around locally, on top of the base wind. Use them for whirlwinds, shockwaves, characters walking through a field, and shelter behind walls. Swayfield fakes these forces. It is not a physics simulation.

## Adding an effector

In the **Effectors** panel, click one of the add buttons: **Vortex**, **Radial Blast**, **Trample** or **Shelter**. Swayfield creates a small object (placed at the 3D cursor) in an `SF_Effectors` collection and links the collection to the layer. Each effector shows as a row in the list with its **radius** and **strength**. Move, rotate and animate the object like any other.

<!-- TODO: screenshot of the Effectors panel -->

| Effector | What the grass does |
| --- | --- |
| **Vortex** | Swirls around the effector. Good for whirlwinds and magic effects |
| **Radial Blast** | Is flattened outward from the effector. Good for helicopter downdrafts and shockwaves |
| **Trample** | Bends away from the effector. Good for characters walking through |
| **Shelter** | Is protected from wind inside the radius. Good for the lee of a wall or a rock |

Each effector has a **radius** (how far it reaches, in metres) and a **strength**. Forces fade smoothly toward the edge of the radius.

### Radial Blast pulse

Strength can be keyframed. For a one-off shockwave:

1. Add a **Radial Blast** and place it where the blast starts.
2. At frame 1, set its strength to 0 and press `I` over the field to keyframe it.
3. At frame 10, set a high strength and keyframe it.
4. At frame 40, set it back to 0 and keyframe it.

The grass flattens outward and springs back as the strength drops.

### Trample

Parent a Trample effector to a character's feet or root, or animate it along a path. Grass bends away from it within its radius. In 0.1.0 grass returns as soon as the effector moves away. A recovery time (grass slowly standing back up) is planned.

### Where effectors overlap

If effectors overlap, the **closest one wins**. At any point in the field only the nearest effector affects the grass. They do not add together. Keep this in mind when you place a Trample effector inside a Vortex. Move them apart, or keep their radii from overlapping, if you want both.

## Exclusion objects

Exclusion objects remove grass around them, so grass does not poke through paths, props and buildings.

1. Select the objects that should stay clear of grass.
2. Click **Add Exclusion** in the **Effectors** panel. They are added to the layer's exclusion collection.
3. Set **Exclusion Distance**: grass is removed within this distance of those objects.
4. Set **Exclusion Falloff**: a band of shorter grass at the border, so the edge looks natural.

Exclusion uses the shape of the object, so a long path object clears a long strip.
