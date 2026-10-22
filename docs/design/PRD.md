# Swayfield: Blender Grass Scatter Add-on PRD

Oct 22, 2026 · @Nabaskar

## Overview

Swayfield (working name) is a Blender add-on that grows animated grass on any selected mesh with Geometry Nodes, in one click, and keeps the viewport fast while doing it. Its signature is the "Rolling Meadow" wind: long, lush grass bent hard by a strong crosswind, with bright gust streaks racing across the field, matched to the reference clip.

**Problem.** Building a field like the reference by hand takes a long node tree (distribution, curve blades, wind fields, shading attributes, culling). Existing scatter tools are strong at placement and asset libraries, but wind is usually a generic sway, and dense long grass quickly makes the viewport crawl.

**Goals for v1**

- Scatter grass on one or more selected mesh objects with a single operator, fully non-destructive.
- Control density with weight painting, plus slope, height and noise masks.
- Ship a default procedural grass material on Principled BSDF, with a slot for user image maps (color, roughness, normal, opacity, translucency) or a single flat color.
- Ship a wind system with a hero "Rolling Meadow" preset and at least five other animation types.
- Ship an Optimised Mode that keeps the viewport interactive (target 24+ fps) on heavy scenes, while renders stay full quality.

**Non-goals for v1**

- A large photoscanned asset library (users bring their own textures; a small default set ships).
- Trees, rocks and general multi-asset biomes (possible later, see Milestones).
- Physics simulation of grass (collision is faked with an effector, not simulated).
- Game engine export pipelines.

## Market research

The market splits into big asset-library scatterers (Geo-Scatter, Grassblade, Botaniq) and small single-purpose grass node groups ($2 to $10). None of them leads with a cinematic, art-directable wind field like the reference; that is Swayfield's opening. Listing details below come from the product pages as of October 2026.

| Tool | Price | How it scatters | Wind | Performance features | Masks |
| --- | --- | --- | --- | --- | --- |
| [Geo-Scatter 5.6](https://superhivemarket.com/products/scatter) | $99 individual | Geometry Nodes engine, presets, brush painting, biomes, ecosystem attract/repel rules | One-click "wind wave" | Field-of-view culling, distance culling, viewport placeholders, camera-based LODs | Elevation, slope, curvature, orientation, ID maps, flowmaps |
| [Grassblade](https://superhivemarket.com/products/grassblade) | $39 Lite / $77 Pro | Built on the Geo-Scatter engine; 204 biomes, 550+ photoscanned assets | Not described on page | Proxy display in viewport, full mesh at render | Vertex paint |
| [INS Grass 2.4](https://superhivemarket.com/products/ins-grass-2) | $49 | Emitter-based instancing, multiple emitters and occluders | Bending from breeze to hurricane; cheap rotation-only mode past a distance, blended | Active-camera culling, LOD by screen size or distance, near detail plus far clumps, placeholders | Vertex groups, texture paint, curves, slope, proximity |
| [GScatter (Graswald)](https://www.cgchannel.com/2023/04/graswald-releases-gscatter-0-10) | Free beta, paid library | Emitter plus stackable effect layers | Not described | Active-camera culling, point-cloud proxy | Painted weight masks, procedural effects |
| [Botaniq](https://docs.polygoniq.com/botaniq/6.8.0/getting_started/animations/) | Library product | Asset library with particle scattering | Per-asset presets (Breeze, Wind, Storm), looping or procedural, Alembic bake | Instance collections, mute animation for viewport speed | Not covered |
| [Dual Level Scatter](https://superhivemarket.com/products/dual-level-scatter) | $5 | Merges grass into blocks, then scatters blocks to cut draw calls | Light breeze | Frustum and distance culling; claims up to 80x speedup | Not described |
| [Physical Grass Scatter and Draw](https://superhivemarket.com/products/physical-grass-scatter-and-draw) | $14 / $23 Pro | Scatter tool plus draw tool | Detailed wind settings | Low-res proxy colliders | Draw tool |
| [Grassify](https://www.cgchannel.com/2023/06/free-tool-grassify-adds-grass-to-blender-models) | Free / about 2.5 EUR | Procedural Geometry Nodes strands | Wind parameters | Fast enough for real-time EEVEE at high density | Weight painting |
| [Ultimate Grass Scatter](https://superhivemarket.com/products/ultimate-grass-scatter/docs) | $4 | Geometry Nodes modifier with target and collection | Not described | Not described | Not described |

**Patterns worth copying**

- **Camera-aware culling is table stakes.** Every serious tool culls by camera frustum and distance, and the better ones follow the active camera's focal length, sensor and resolution automatically (INS Grass).
- **Viewport proxies and placeholders.** Show points or simple shapes in the viewport and swap in full detail only at render (Geo-Scatter, Grassblade, GScatter).
- **Near detail, far clumps.** Detailed blades near the camera, merged clumps or cards farther out, with a blend distance (INS Grass, Dual Level Scatter).
- **Distance-based animation LOD.** Full bending near the camera, cheap whole-instance rotation far away (INS Grass).
- **Wind presets by intensity** (Breeze, Wind, Storm), a looping mode for game and loop renders, and a quick mute for viewport speed (Botaniq).
- **Stackable mask and effect layers** rather than one fixed mask (GScatter, Geo-Scatter).
- **Exclusion around objects** so grass does not poke through props, and lean-away for characters (Geo-Scatter).

**Gaps Swayfield targets**

- No product sells a hero wind look; wind is a checkbox, not a feature you can art-direct with gust streaks and shading tied to bend.
- Wind shading feedback (flattened grass reading brighter) is absent from the listings reviewed.
- Long, soft, hair-like grass is poorly served; most tools instance short mesh tufts.

## Users and use cases

The primary user is a solo 3D generalist or small studio artist who needs a beautiful wind-swept field fast, without building node trees.

| User | Wants | Key need |
| --- | --- | --- |
| Environment / landscape artist | Stills and flythroughs of meadows, hills, fields | Realism, masks, big areas without lag |
| Motion designer / social content creator | Short looping clips like the reference | Hero wind preset, seamless loops, punchy look |
| Archviz artist | Lawns and gardens around buildings | Exclusion around paths and props, short-grass presets |
| Indie game dev (previs, cutscenes) | Rendered cinematics, look development | Optimised Mode, loopable wind |
| Hobbyist / learner | One click to a pretty result | Sensible defaults, tooltips |

**Core use cases**

1. Select a hill mesh, click **Add Grass**, pick the **Rolling Meadow** preset, press play: the reference look within 60 seconds.
2. Weight paint a path through a field so grass is absent on the path and shorter at its edges.
3. Swap the default material for an image texture set (color, roughness, normal, opacity) from a downloaded grass pack.
4. Change the animation type from Rolling Meadow to Gentle Breeze or Storm for a different shot, without rebuilding.
5. Fill a 200 m x 200 m terrain, switch on Optimised Mode, and keep the viewport interactive while animating the camera.
6. Make a 240-frame seamless loop for social media.

## Scattering requirements

One operator turns any selected mesh into a grass surface through a Geometry Nodes modifier; nothing is ever applied or destroyed unless the user bakes. Priority: P0 = v1 must ship, P1 = v1 should ship, P2 = later.

| ID | Requirement | Priority |
| --- | --- | --- |
| SC-01 | **Add Grass** operator adds a Swayfield modifier to every selected mesh object. With several selected, all share one system (same settings), each with its own seed offset. | P0 |
| SC-02 | A surface can hold several **grass layers** (for example Base Grass, Tall Wisps, Flowers), each its own modifier with its own settings, masks and material. | P0 |
| SC-03 | **Density in blades per square metre**, computed on world-space area, so scaling the object keeps the look. Default 800/m², range 1 to 20,000. | P0 |
| SC-04 | Poisson-disk distribution with a minimum-distance slider to avoid clumps of overlapping roots. | P0 |
| SC-05 | **Stable blade identity:** blades are distributed once at maximum density, then thinned by masks and the density slider. Painting or lowering density removes blades, it never reshuffles the ones that remain. | P0 |
| SC-06 | **Two blade sources:** Procedural Strands (default, curve blades generated in nodes) and Custom Instances (any user collection of meshes, such as grass tufts or cards, picked with weights). | P0 |
| SC-07 | Blade shape controls: length min/max, root width, tip taper, rest lean, curl, random tilt, random rotation around up. | P0 |
| SC-08 | **Clumping:** clump count per m², clump radius, and pull strength toward clump centres, giving the tufted look visible in the reference foreground. | P1 |
| SC-09 | **Wisp sub-layer:** a percentage (default 3%) of blades that are 1.3x longer and thinner and react twice as strongly to flutter. | P0 |
| SC-10 | Orientation blend between surface normal and world up (default 0.2 normal, 0.8 up), so grass on slopes still grows mostly upward. | P0 |
| SC-11 | **Exclusion objects:** a collection whose objects remove grass within a distance, with a falloff band of shorter grass at the border. | P1 |
| SC-12 | **Trample / lean-away effector:** an empty or object that bends grass away within a radius (for characters walking through). | P1 |
| SC-13 | Edge offset: no grass within N cm of open mesh borders. | P2 |
| SC-14 | **Bake:** cache the scatter (not the wind) with Blender's Bake node so heavy masks are not re-evaluated every frame. | P0 |
| SC-15 | **Apply / Export:** convert to real curves or mesh, or to Alembic for other software. | P2 |
| SC-16 | Works on the evaluated surface (respects modifiers such as Subdivision and Displace below the Swayfield modifier). | P0 |

## Weight painting and masks

Weight painting is a first-class control: one click creates a vertex group and drops the user into Weight Paint mode, and the grass updates live as they paint. Masks stack like layers, so painting, slope and noise combine without node editing.

**Painting workflow**

1. User clicks **Paint Density** in the Swayfield panel.
2. Swayfield creates a vertex group named `SF_<layer>_density` (filled with weight 1.0 so nothing disappears), links it to the layer, and switches to Weight Paint mode with a soft brush.
3. Painting black removes grass, white restores it, grey thins it. Grass updates live; in Optimised Mode it shows as points while painting for speed.
4. A **Done** button returns to Object mode.

| ID | Requirement | Priority |
| --- | --- | --- |
| WP-01 | Paint Density operator as above; one vertex group per layer, chosen from a dropdown or auto-created. | P0 |
| WP-02 | **Paint Length** map: a second vertex group that scales blade length (mown paths, longer grass at field edges). | P0 |
| WP-03 | **Paint Wind Strength** map: shelter areas behind walls or rocks where wind is weaker. | P1 |
| WP-04 | Paint Color Variation map: drives the material's secondary tint (dry or yellow patches). | P1 |
| WP-05 | Each painted map has Invert, Contrast and Threshold sliders, so a soft paint stroke can produce a crisp edge. | P0 |
| WP-06 | **Mask stack** per layer, combined by multiply (default), add, subtract or min: Vertex Group, Slope (min/max angle), Altitude (min/max Z), Noise (scale, contrast, seed), Image texture (UV), Proximity to object collection, Camera distance. | P0 for Vertex Group, Slope, Noise; P1 others |
| WP-07 | **Mask preview:** a toggle that shows the final density as a black-to-white overlay color on the surface, so users see what they are painting. | P1 |
| WP-08 | Masks thin blades stochastically by weight (weight 0.3 keeps about 30% of blades), with optional length falloff so edges look natural rather than a hard cut. | P0 |
| WP-09 | Works with Blender's own weight paint tools and brushes; Swayfield adds no custom brush in v1. | P0 |
| WP-10 | Texture paint mode (paint an image instead of vertex weights) for low-poly surfaces where vertex density is too coarse. | P2 |

A note for users is shown in the panel when the surface has too few vertices for clean painting (under about 1 vertex per 25 cm), with a one-click Subdivide suggestion.

## Blade geometry and materials

Every layer ships with a ready default material built on Principled BSDF, and the user can switch it to their own image maps or a single flat color from one dropdown. The geometry and the shader share attributes, so wind can brighten flattened grass exactly as in the reference.

**Blade render modes**

| Mode | What it is | Best for | Notes |
| --- | --- | --- | --- |
| Strands (default) | Curves rendered as thin hair strands | Long, soft, dense grass like the reference | Lightest memory; no UV textures along width |
| Ribbons | Curves converted to flat tapered mesh strips with UVs | Image textures with opacity, close-ups | U runs across the blade, V from root (0) to tip (1) |
| Custom Instances | User meshes from a collection | Photoscanned tufts, flowers, stylised grass | Material comes from the user's mesh unless overridden |

**Material modes** (one dropdown per layer: Procedural, Image Maps, Single Color)

- **Procedural (default).** Principled BSDF with a root-to-tip color ramp, per-blade random hue and value jitter, and the wind-brightening effect. Default colors are sampled from the reference: root shadow #0B3A05, mid #3F7A12, lit tip #8BD63A, far-field haze #5E8F31. Roughness 0.45, soft specular 0.3, mixed with a Translucent BSDF at 0.2 (toggle) for backlit glow.
- **Image Maps.** Slots for Base Color, Roughness, Normal, Opacity (alpha), Translucency and AO. A **Load Texture Set** button picks a folder and auto-fills slots by filename suffix (for example `_albedo`, `_basecolor`, `_diff`, `_rough`, `_nrm`, `_normal`, `_opacity`, `_alpha`, `_trans`). Choosing Image Maps with an opacity map switches the blade mode to Ribbons automatically. The map is tinted by the same root-to-tip gradient and wind attribute, each with a strength slider (0 = raw texture).
- **Single Color.** One color picker plus Variation (0 to 1) and Roughness. Fast for stylised or toon looks.

**Bundled default textures (shipped with the add-on, CC0, made by the author)**

- One grass blade texture set (base color, opacity, normal, roughness) at 512 x 2048, painted or procedurally baked by the project author.
- One short-lawn tuft set for archviz.
- No third-party textures are bundled, to keep licensing clean.

**Attributes exposed to any material** (so users can build their own shaders)

| Attribute | Range | Meaning |
| --- | --- | --- |
| `sf_factor` | 0 to 1 | Position along the blade, root to tip |
| `sf_wind` | 0 to 1 | Current bend amount from wind; drives brightening |
| `sf_random` | 0 to 1 | Stable random value per blade |
| `sf_variation` | 0 to 1 | Painted or noise color-variation mask |
| `sf_clump` | 0 to 1 | Random value per clump, for patchy color |
| `sf_dist` | metres | Distance to the active camera, for haze and LOD fades |

| ID | Requirement | Priority |
| --- | --- | --- |
| MT-01 | The three material modes above, switchable without losing the other modes' settings. | P0 |
| MT-02 | Auto-fill of image slots by filename suffix. | P1 |
| MT-03 | Wind brightening: lerp toward a highlight color by `sf_wind` x strength (default 0.6). | P0 |
| MT-04 | Distance haze: blend toward the far-field color by `sf_dist`, start and end distances exposed. | P1 |
| MT-05 | Season slider (green to dry yellow) as a quick global tint. | P2 |
| MT-06 | Materials work in Cycles and EEVEE; EEVEE uses alpha-hashed opacity for Ribbons. | P0 |

## Wind and animation

Wind is Swayfield's headline feature: a layered wind field drives every blade, with **Rolling Meadow** as the hero preset tuned to the reference clip, plus seven more animation types. All of it is procedural, driven by scene time, so there is nothing to simulate or bake unless the user wants a loop or export.

### How the wind field works

Every frame, each blade samples a wind vector made of stacked components, then bends by rotating its points around its root (never by offsetting, so blades keep their length).

1. **Base lean:** a constant push along the wind direction (how bent the grass is at rest).
2. **Gust field:** a low-frequency noise, stretched along the wind direction and scrolled with time, producing the travelling bright streaks.
3. **Waves (optional):** a sine wave along the wind direction for regular rolling rows.
4. **Flutter:** fast, small noise weighted toward the tips, stronger on wisps.
5. **Effectors:** local forces from objects (radial blast, vortex, trample, shelter).
6. **Bend:** angle = total strength x max angle x factor^stiffness, around the axis perpendicular to wind and up. Tip lag samples the field slightly back in time toward the tip, so tips trail the root like real stems.
7. **Outputs:** `sf_wind` (bend amount) is stored for shading, which makes flattened crests glow.

### Hero preset: Rolling Meadow

Tuned from a frame-by-frame read of the reference: a strong crosswind blowing left to right, foreground blades nearly horizontal at peak gusts, long horizontal streaks of bright flattened crests separated by dark gaps, gusts crossing the frame in about 1 to 2 seconds, loose wisps whipping above the canopy.

| Parameter | Default | Range |
| --- | --- | --- |
| Direction | +X (screen right for a camera looking +Y) | 0 to 360°, or follow an empty's rotation |
| Base lean | 0.6 | 0 to 1 |
| Gust strength | 0.4 | 0 to 1 |
| Gust scale (noise) | 0.2 (patches about 5 m) | 0.02 to 2 |
| Gust stretch along wind | 3.3x (axis scale 0.3) | 1 to 10x |
| Gust speed | 4 m/s | 0 to 30 m/s |
| Max bend angle | 80° | 0 to 89° |
| Stiffness exponent | 1.6 | 1 to 3 |
| Flutter strength | 0.08 | 0 to 0.5 |
| Flutter frequency | 3 Hz | 0.5 to 10 Hz |
| Wisp flutter multiplier | 2x | 1 to 4x |
| Tip lag | 0.15 s | 0 to 0.5 s |
| Wind brightening (shader) | 0.6 | 0 to 1 |

**Acceptance test:** a side-by-side of a Swayfield render and the reference, judged on lean angle, streak shape and direction, gust speed and crest brightening. The preset ships only when three viewers pick it as "the same kind of wind".

### Animation types

| Type | Look | Driven by | Priority |
| --- | --- | --- | --- |
| **Rolling Meadow (hero)** | Strong crosswind, racing gust streaks, glowing crests | Base lean + stretched gusts + flutter | P0 |
| Gentle Breeze | Calm sway, small slow gusts, upright grass | Low lean, small gusts, soft flutter | P0 |
| Storm | Violent, turbulent, shifting direction | High lean, fast gusts, direction noise up to 30° | P0 |
| Rolling Waves | Regular parallel rows, stylised or anime look | Sine waves along wind, adjustable wavelength and speed | P0 |
| Vortex | Grass swirls around a point (whirlwind, magic effect) | Tangential force around an empty, with radius and falloff | P1 |
| Radial Blast | Grass flattened outward (helicopter downdraft, shockwave) | Outward force from an empty; strength is keyframable for a one-off pulse | P1 |
| Trample Path | Grass parts around a moving character | Effector object or collection, push-away radius, optional recovery time | P1 |
| Toon Bob | Whole-blade stylised rocking, no bending | Rotation-only sway, cheap | P1 |

All types can be mixed: one layer has one base type plus any number of effectors.

### Animation requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| AN-01 | Preset dropdown with the types above; selecting one fills the sliders, and editing a slider marks the preset as Custom. | P0 |
| AN-02 | Global **Intensity** slider (0 to 2) scaling all wind at once, keyframable. | P0 |
| AN-03 | **Wind Direction Empty:** an optional empty whose rotation sets direction, so animators keyframe direction changes. | P0 |
| AN-04 | **Seamless loop mode:** loop length in frames; the gust field cross-fades from time t to t minus the loop length, so frame N matches frame 1. | P0 |
| AN-05 | **Time offset and speed multiplier** per layer, so layers do not move in lockstep. | P0 |
| AN-06 | **Wind shelter** from the painted Wind Strength map (WP-03). | P1 |
| AN-07 | **Animation LOD:** past a distance, blades switch from bending to cheap whole-blade rotation, with a blend band (as in INS Grass). | P1 |
| AN-08 | **Motion blur safe:** blade count and order stay constant through a frame's shutter so Cycles and EEVEE motion blur work. | P0 |
| AN-09 | **Freeze Wind** toggle for posing and stills, and a viewport-only mute for speed. | P0 |
| AN-10 | Save and load user wind presets to a JSON file in the user's config folder. | P1 |
| AN-11 | Bake wind to Alembic or a Geometry Nodes bake for export or render farms. | P2 |

## Optimised Mode and performance

Optimised Mode is one toggle (on by default for scenes over 500,000 blades) that makes the viewport light while leaving final renders untouched. It works because Geometry Nodes can tell viewport from render (the Is Viewport node), so every saving below applies to the viewport only unless the user opts in for renders too.

**What Optimised Mode changes**

| Technique | Viewport effect | Render effect | Priority |
| --- | --- | --- | --- |
| **Viewport density %** | Shows a stable subset of blades (default 20%), widened to stay readable | None | P0 |
| **Display as** Full, Strands lite, Points or Bounds | Points shows one dot per blade, coloured by the material's base color; Bounds shows only the layer's box | None | P0 |
| **Camera frustum culling** | Removes blades outside the active camera's view plus a margin (default 10%) | Optional, on by default with a 15% margin to avoid pop-in at frame edges and in motion blur | P0 |
| **Distance culling and LOD bands** | Near band: full strands with 8 points. Mid band: 50% density, 4 points, blades 1.4x wider to keep coverage. Far band: 10% density, 2 points, or none with the ground material tinted to match | Same bands at render, with user distances | P0 |
| **Animation LOD** | Far blades rotate instead of bend (AN-07) | Same | P1 |
| **Pause wind while navigating** | Wind freezes while the user orbits or paints, resumes on release | None | P1 |
| **Scatter bake** | Static distribution and masks cached; only wind evaluated per frame | Same | P0 |
| **Keep instances** | Custom Instances stay instanced (never realised), so the GPU draws one mesh many times | Same | P0 |
| **Viewport follow (experimental)** | Culls to the 3D view rather than the scene camera, via a Python timer that copies the view matrix to a hidden empty at about 4 Hz | None | P2 |

**Safeguards**

- **Blade counter** in the panel: live viewport count and estimated render count per layer and in total.
- **Budget guard:** before a change would push the viewport above a user budget (default 2 million blades), Swayfield warns and offers to switch on Optimised Mode or lower density, instead of freezing Blender.
- **Density preview on Add:** the first evaluation after Add Grass always runs at 10% density and points display, then ramps up, so a huge mesh never locks the UI on the first click.
- **Simplify hook:** respects Blender's Simplify panel, scaling viewport density by its child-particle percentage.

**Performance targets** (to be measured during development on a reference test scene: a 100 m x 100 m terrain with the Rolling Meadow preset, camera at 1 m height, 1920 x 1080)

| Metric | Target |
| --- | --- |
| Viewport playback with Optimised Mode on, mid-range GPU (RTX 3060 class) | 24 fps or more |
| Viewport playback with Optimised Mode off, same scene | Measured and published, no target |
| Time from Add Grass click to first visible result | Under 2 seconds |
| Render blades in camera after culling | About 3 to 6 million |
| Peak RAM increase for the test scene at render | Under 6 GB |
| Slider response (density, length) in viewport | Under 150 ms |

## UI and workflow

All controls live in one **Swayfield** tab in the 3D Viewport sidebar (N panel), ordered the way an artist works: add, shape, paint, light it with wind, then optimise. Every slider maps to one modifier input, so power users can still open the node tree.

**Panel layout (top to bottom)**

1. **Header:** Add Grass button, preset picker (thumbnails), Optimised Mode toggle, live blade counter.
2. **Layers:** a list of grass layers on the active object (UIList) with eye, render and solo toggles; add, duplicate, remove, reorder.
3. **Distribution:** density, minimum distance, seed, blade source (Strands, Ribbons, Custom Instances).
4. **Blade Shape:** length, width, taper, lean, curl, clumping, wisps.
5. **Masks:** the mask stack with add-mask menu; Paint Density, Paint Length, Paint Wind buttons; mask preview toggle.
6. **Wind:** animation type dropdown, Intensity, direction (angle or empty picker), then the type's sliders; Loop, Freeze and Mute toggles.
7. **Material:** mode dropdown (Procedural, Image Maps, Single Color) and its slots; Load Texture Set button.
8. **Effectors:** add Vortex, Radial Blast, Trample or Exclusion objects; each shows as a list row with radius and strength.
9. **Performance:** viewport density %, display mode, culling margins, LOD band distances, budget, Bake Scatter button.

**Presets**

| Preset | Blade length | Density | Wind type | Notes |
| --- | --- | --- | --- | --- |
| Rolling Meadow (hero) | 0.5 to 0.9 m | 1,500/m² | Rolling Meadow | Reference look, wisps on |
| Lawn | 0.05 to 0.1 m | 6,000/m² | Gentle Breeze | Archviz, low lean |
| Wild Field | 0.3 to 1.2 m | 900/m² | Gentle Breeze | Strong clumping, colour variation |
| Stormy Steppe | 0.4 to 0.8 m | 1,200/m² | Storm | Dry tint |
| Anime Field | 0.4 to 0.6 m | 1,000/m² | Rolling Waves | Single Color material, saturated |

Presets are JSON files plus thumbnails; users can save their own (AN-10).

**UX rules**

- Every control has a tooltip saying what it does in plain words and its unit.
- Sliders show real units (m, m/s, degrees, Hz), never raw 0-to-1 values where a unit exists.
- Undo works for every operator; no operator runs more than 2 seconds without a progress bar.
- Error messages say what to do ("Select a mesh object first"), never a stack trace.
- A **Quick Look** button sets up a test camera at 1 m height, a sun and the punchy colour grade (AgX, Punchy look) so first renders look good.

## Technical architecture

Swayfield is a thin Python add-on wrapped around a library of versioned Geometry Nodes groups. Python handles UI, presets and setup; all per-frame work runs inside Geometry Nodes, so playback and render farms never depend on Python handlers.

&#91;embedded content: Swayfield node pipeline · 8 stages\]

The static half (surface to masks) can be baked once; culling, blade building, wind and shading are re-evaluated each frame, and culling runs before blades are built so hidden blades cost almost nothing.

**Node group library** (stored in `swayfield/assets/sf_nodes.blend`, appended on first use)

| Group | Job |
| --- | --- |
| `SF_Main_v1` | The modifier group; exposes every user input and wires the stages |
| `SF_Distribute` | Poisson-disk points at max density, area-normalised, stable `id` attribute |
| `SF_Masks` | Mask stack: vertex groups, slope, altitude, noise, image, proximity; outputs keep-probability |
| `SF_Cull` | Frustum test from camera matrix and lens inputs, distance bands, viewport % via Is Viewport |
| `SF_Blade` | Curve blades (strands or ribbons with UVs) or instance picking; shape, clumps, wisps |
| `SF_Wind` | Wind field and bending, presets as switchable sub-groups, loop cross-fade |
| `SF_Effectors` | Reads effector points and their `sf_radius`, `sf_strength`, `sf_type` attributes |
| `SF_Store` | Writes `sf_*` attributes and sets the material |

**Key implementation decisions**

- **Bending by rotation:** each curve point is rotated about its root with Vector Rotate (axis angle); the root comes from Points of Curve plus Evaluate at Index. This keeps blade length constant.
- **Camera data:** Geometry Nodes can read the active camera's transform but not its lens, so Swayfield adds drivers that copy focal length, sensor size, shift and render resolution into hidden modifier inputs. Drivers (not handlers) keep it working in background renders.
- **Effectors:** created as single-vertex mesh objects in an `SF_Effectors` collection; Python writes radius, strength and type as named attributes when sliders change, which Geometry Nodes reads through Collection Info.
- **Loop mode:** wind noise is sampled at time t and t minus loop length, blended by t divided by loop length.
- **Single source of truth:** every setting lives as a modifier input; the Python PropertyGroup on the object stores only UI state (layer name, preset name, linked vertex group names).
- **Versioning:** node groups carry a version suffix; opening an old file keeps the old groups working, and an **Upgrade Layer** operator migrates inputs to the new version.

**Code layout**

```
swayfield/
  blender_manifest.toml
  __init__.py
  operators/   add_grass.py, paint.py, layers.py, bake.py, presets.py, effectors.py
  ui/          panels.py, lists.py, icons/
  core/        node_setup.py, drivers.py, versioning.py, budget.py
  assets/      sf_nodes.blend, sf_materials.blend
  presets/     *.json + thumbnails
  textures/    default blade and lawn sets (CC0)
  tests/       unit, render regression, benchmark
```

**Testing**

- Unit tests run in `blender --background` with pytest for every operator (add, layer, paint, preset load, upgrade).
- Render regression: each preset renders a 256 x 256 frame at fixed frames and is compared to a stored reference by SSIM, failing below 0.98.
- Benchmark script records viewport fps, evaluation time and peak memory on the reference scene for every release, published in the changelog.

## Non-functional requirements

A .blend made with Swayfield must open and render on any machine, even without the add-on installed, because all the work lives in Geometry Nodes groups saved inside the file. That makes it render-farm safe and is a selling point worth stating on the store page.

| Area | Requirement |
| --- | --- |
| Blender versions | Minimum 4.2 LTS (Extensions platform); tested on 4.2 LTS, 4.5 LTS and the latest 5.x release. A week-1 spike confirms every node used exists in 4.2, else the minimum moves up. |
| Operating systems | Windows 10/11, macOS (Apple Silicon), Linux |
| Render engines | Cycles and EEVEE for final renders; Workbench and Material Preview for viewport |
| Dependencies | None outside Blender; no pip packages, no network calls |
| Portability | Files render without the add-on installed (node groups and materials are embedded); drivers use only built-in functions |
| Stability | No crash in the test suite; every operator undo-safe; no Python exceptions shown to users |
| Performance | Targets in the Optimised Mode section, measured every release |
| Size | Download under 50 MB including default textures and preset thumbnails |
| Documentation | Docs site with a quick start, every panel explained, and three short videos: Quick start, Painting, Hero wind |
| Language | English UI in v1; strings kept in one module for later translation |

**Packaging and licensing**

- Python code under GPL-3.0-or-later, as Blender add-ons that use its Python API generally are.
- Default textures and preset thumbnails made by the author and shipped as CC0, so customers can use them anywhere.
- Node group and material .blend files: licence to be decided with the store's guidance (open question below).

**Distribution and pricing (proposal)**

| Edition | Where | Price | Contents |
| --- | --- | --- | --- |
| Lite | Gumroad (pay what you want) | Free or tip | Scatter, weight painting, Procedural and Single Color materials, Gentle Breeze, Optimised Mode |
| Pro | Superhive and Gumroad | $29 individual, $79 studio | Everything, including Rolling Meadow, all wind types, effectors, Image Maps mode, presets, loop mode |

Pricing sits between the $4 to $14 single-purpose grass tools and the $49 to $99 full scatter suites found in the market research.

## Milestones

v1 takes about 10 weeks for one developer, and the first gate is the riskiest: if the hero wind does not match the reference by the end of the spike, everything else waits. Durations are estimates, not commitments.

&#91;embedded content: Swayfield v1 roadmap · 5 phases, 4 gates\]

Each phase ships a usable build to testers; Optimised Mode lands before the extra wind types so testers can stress big scenes early.

**After v1 (v1.1 and later)**

- Texture-paint masks (WP-10) and edge offset (SC-13).
- Bake wind to Alembic and Apply to mesh (AN-11, SC-15).
- Viewport-follow culling (experimental).
- Season slider and dry-grass presets.
- Flower and weed layers mixed into the grass (a small biome system).

## Success metrics, risks and open questions

Success means artists reach the reference look fast, the viewport stays usable, and the hero wind sells the product.

**Success metrics**

| Metric | Target |
| --- | --- |
| New user from install to a Rolling Meadow render | Under 5 minutes, in a test with 5 users |
| Optimised Mode viewport on the reference scene | 24 fps or more on a mid-range GPU |
| Store rating 3 months after launch | 4.5 out of 5 or higher |
| Refund rate | Under 3% |
| Share of store-page and social clips using Rolling Meadow | Tracked; the hero preset should lead the marketing |

**Risks**

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Hero wind does not match the reference | Product loses its hook | Spike gate M0; compare side by side every build; tune shading, not only motion |
| Dense long strands are too heavy even with culling | Laggy viewport, bad reviews | LOD bands, budget guard, points display; publish honest benchmarks |
| Camera-lens drivers break in some setups (linked cameras, render farms) | Wrong culling, popping blades | Fallback: fixed culling angle input; render culling margin of 15% |
| Frustum culling causes pop-in during camera moves or motion blur | Visible artefacts | Margin, and culling against the shutter's start and end camera positions |
| Blender API or node changes between versions | Broken files after updates | Versioned node groups, Upgrade operator, test on LTS and latest |
| Crowded market (Geo-Scatter and others) | Low sales | Lead with wind; price below suites; free Lite tier for reach |
| Licensing of bundled .blend node groups | Store rejection or disputes | Ask the store before launch; ship only author-made assets |

**Open questions**

- [ ] Final product name: keep Swayfield, or pick another?
- [ ] Is Optimised Mode in the free Lite tier (good for reach) or Pro only?
- [ ] Should v1 include Custom Instances, or ship strands and ribbons only and add instances in v1.1?
- [ ] Licence for the node group and material .blend files under Superhive's rules.
- [ ] Lowest Blender version, after the M0 spike confirms which nodes exist in 4.2.

**Sources** (product pages opened October 2026)

- [Geo-Scatter on Superhive](https://superhivemarket.com/products/scatter)
- [Grassblade on Superhive](https://superhivemarket.com/products/grassblade)
- [INS Grass 2.4 on Superhive](https://superhivemarket.com/products/ins-grass-2)
- [GScatter 0.10 release, CG Channel](https://www.cgchannel.com/2023/04/graswald-releases-gscatter-0-10)
- [Botaniq animation docs](https://docs.polygoniq.com/botaniq/6.8.0/getting_started/animations/)
- [Dual Level Scatter on Superhive](https://superhivemarket.com/products/dual-level-scatter)
- [Physical Grass Scatter and Draw on Superhive](https://superhivemarket.com/products/physical-grass-scatter-and-draw)
- [Grassify, CG Channel](https://www.cgchannel.com/2023/06/free-tool-grassify-adds-grass-to-blender-models)
- [Ultimate Grass Scatter docs on Superhive](https://superhivemarket.com/products/ultimate-grass-scatter/docs)
