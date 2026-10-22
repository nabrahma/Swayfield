# Architecture

Swayfield is a thin Python add-on wrapped around a library of versioned
Geometry Nodes groups. Python handles UI, presets and setup. All per-frame work
runs inside Geometry Nodes, so playback and render farms never depend on Python
handlers, and a `.blend` made with Swayfield renders on a machine without the
add-on installed.

This page is the contract between the parts of the code base. If you change
something listed here, update this page in the same pull request.

## Repository layout

```
swayfield/                 the extension package (what ships)
  blender_manifest.toml
  __init__.py              register / unregister
  props.py                 PropertyGroups: UI state only
  core/
    spec.py                every modifier input (single source of truth)
    compat.py              modifier input access for Blender 4.2 and 5.x
    nodes/                 node groups as code, one module per stage
      builder.py           NodeBuilder helper
      __init__.py          ensure(stage), STAGES
    materials.py           layer material (Procedural / Image Maps / Single Color)
    layers.py              find layers and their modifiers
    node_setup.py          create a layer: modifier, material, drivers
    drivers.py             camera lens and Simplify drivers
    presets.py             load, apply and save JSON presets
    budget.py              blade counter and budget guard
    versioning.py          group versions and layer upgrade
  operators/               bpy operators, one module per area
  ui/                      N-panel, UI lists, strings
  presets/grass/*.json     full grass presets (+ thumbnails)
  presets/wind/*.json      wind animation types
  textures/                CC0 default texture sets
tests/                     pytest suite, runs inside Blender
tools/                     test runner, build, benchmark, asset generators
docs/                      documentation site (MkDocs)
```

## Nodes as code

The PRD planned a binary `sf_nodes.blend`. Swayfield instead builds every node
group from Python (`swayfield/core/nodes/`), the first time it is needed. The
built groups are saved inside the user's file like any other data, so
portability is the same, and the node graphs can be reviewed and diffed in
pull requests.

A released group (`SF_Main_v1`) is never rebuilt inside a user's file:
rebuilding regenerates socket identifiers and would drop modifier values.
Changes to a released group ship as a new version (`SF_Main_v2`) plus an
upgrade step in `core/versioning.py`.

## Pipeline

```
Surface ─► to world ─► SF_Masks ─► SF_Distribute ─► [Bake] ─► SF_Cull ─► SF_Blade ─► SF_Wind ─► SF_Store ─► to local ─► + Surface
            (Main)     surface      points                    points      curves /     bent        strands /
                       attributes                                         instances    blades      ribbons
```

* `SF_Main_v1` is the modifier group. It exposes every input in `spec.py`
  (grouped in panels), transforms the surface to world space so every stage
  works in world units, runs the stages, transforms the result back, and joins
  it with the original surface.
* The static half (Masks, Distribute) sits before a Bake node named `SF_Bake`,
  so heavy masks can be cached. Culling, blades, wind and shading are evaluated
  every frame, and culling runs before blades are built.
* Each stage group exposes the spec inputs it needs **with the same socket
  names as `SF_Main_v1`**. `NodeBuilder.group()` links matching names
  automatically, so adding an input to a stage only means adding its key to
  the stage's input list.

### Stage interfaces

All geometry is in world space. "Spec inputs" are `spec.Input` keys.

| Group | Geometry in | Geometry out | Spec inputs (keys) | Extra inputs |
| --- | --- | --- | --- | --- |
| `SF_Masks_v1` | `Surface` mesh | `Surface` mesh with point-domain attributes `sf_mask`, `sf_length`, `sf_wind_scale`, `sf_variation` | all `Masks` panel inputs, `exclusion_*` | – |
| `SF_Distribute_v1` | `Surface` from Masks | `Points` | `seed`, `seed_offset`, `density`, `density_ceiling`, `min_distance`, `orient_normal`, `clump_density`, `clump_radius`, `wisp_percent`, `length_falloff` | – |
| `SF_Cull_v1` | `Points` | `Points` | `optimised`, `viewport_density`, `simplify`, `frustum_cull`, `render_cull`, `cull_margin_*`, `cull_fov_override`, `cam_*`, `res_x`, `res_y`, `lod_*` (not `lod_*_points`) | – |
| `SF_Blade_v1` | `Points` | `Blades` (curves, or instances for Custom Instances) | `blade_source`, `instance_*`, `length_*`, `root_width`, `tip_taper`, `rest_lean`, `curl`, `random_tilt`, `random_rotation`, `blade_points`, `lod_mid_points`, `lod_far_points`, `clump_pull`, `wisp_length`, `wisp_width` | `Force Lite` (bool: 3 points per blade) |
| `SF_Effectors_v1` | – (field group) | `Force` vector field, `Flatten` float field, `Shelter` float field (1 = no shelter) | `effector_collection` | `Position` vector field |
| `SF_Wind_v1` | `Blades` | `Blades` | all `Wind` panel inputs except `mute_viewport` handled inside, `anim_lod_*`, `effector_collection` | `Force Rigid` (bool) |
| `SF_Store_v1` | `Blades` | `Grass` | `blade_source`, `material`, `instance_material_override` | – |
| `SF_EffectorPoint_v1` | `Geometry` (effector object mesh) | one point with `sf_type`, `sf_radius`, `sf_strength`, `sf_falloff` | – | `Type` (int), `Radius`, `Strength`, `Falloff` |

`Force Lite` and `Force Rigid` are computed by Main from Optimised Mode,
`display_mode` and Is Viewport.

### Attribute contract

Constants live in `spec.py` (`ATTR_*`). Point attributes written by the static
half and read downstream:

| Attribute | Domain | Written by | Meaning |
| --- | --- | --- | --- |
| `id` | point | Distribute | stable blade identity (never reshuffled by density or masks) |
| `sf_up` | point | Distribute | unit growth direction, blend of normal and world up |
| `sf_random` | point | Distribute | stable random 0–1 per blade |
| `sf_clump` | point | Distribute | random 0–1 per clump |
| `sf_clump_center` | point | Distribute | world position of the blade's clump centre |
| `sf_wisp` | point | Distribute | true for wisps |
| `sf_length` | point | Masks → Distribute | length multiplier (length paint × mask falloff × exclusion falloff) |
| `sf_wind_scale` | point | Masks → Distribute | wind multiplier from the shelter map |
| `sf_variation` | point | Masks → Distribute | colour variation 0–1 |
| `sf_dist` | point | Cull | distance to the active camera, metres |
| `sf_lod` | point | Cull | LOD band: 0 near, 1 mid, 2 far |
| `sf_width` | point | Cull | width multiplier (LOD band × viewport widening) |
| `sf_mask` | surface point | Masks | final density 0–1, for Mask Preview |

Blade attributes (on curve points, carried to ribbons) read by materials:
`sf_factor` (root 0 → tip 1), `sf_wind` (bend amount 0–1), plus `sf_random`,
`sf_variation`, `sf_clump`, `sf_dist` propagated from the points. These six are
the public attributes users can read in their own shaders.

### Thinning and stable identity

Blades are distributed once with Poisson disk at `density_ceiling` and then
thinned. Distribute's *Density Factor* is
`sf_mask × density / density_ceiling`; Blender eliminates points by a
per-point random value that does not depend on the factor, so lowering density
or painting removes blades without moving the remaining ones (SC-05). Viewport
density, Simplify and LOD bands thin again in Cull, using a hash of `id`.

### Wind

Every frame each blade samples a wind vector: base lean + gust field (noise
stretched along the wind and scrolled at gust speed) + waves + flutter
(tip-weighted) + effector forces. Each blade segment is rotated by the bend at
its midpoint (Vector Rotate, axis angle about `cross(sf_up, wind)`, angle =
`strength × max_bend × factor^stiffness`) and the segments are re-summed from
the root with Accumulate Field, so blades keep their exact length. Rotating
points about the root instead would stretch strongly bent blades. Tips
sample the field `tip_lag` seconds earlier. Loop mode samples the field at
`t' = t mod L` and `t' − L` and blends by `t' / L`, so frame L + 1 matches
frame 1. `sf_wind` (bend amount) is stored for shading.

Custom Instances are never realised: they rock rigidly with Rotate Instances.

### Ribbons

Store converts curves to ribbons with Curve to Mesh. The strip's width runs
perpendicular to the blade's bend plane (curve normal = `normalize(lean × up)`
in Free mode), so blades fold like real leaves: the face is vertical at the
root and turns toward the sky where the blade bends over, which is what makes
flattened crests catch the light. Ribbon width is twice the curve radius.

### Effectors

Effectors are single-vertex mesh objects in a collection (default
`SF_Effectors`), each with a small `SF_EffectorPoint_v1` Geometry Nodes
modifier whose inputs (type, radius, strength, falloff) are written to point
attributes. `SF_Effectors_v1` reads them through Collection Info. Because the
values are modifier inputs, they can be keyframed (a Radial Blast pulse) and
need no Python at render time.

Types: `0` Vortex, `1` Radial Blast, `2` Trample, `3` Shelter. Every
effector is summed (a Repeat zone over the effector points), using horizontal
distance. The settings point is a point cloud and the viewport circle a mesh;
`SF_Effectors_v1` reads only point clouds.

### Camera data

Geometry Nodes reads the active camera's transform (Active Camera node), but
not its lens. `core/drivers.py` adds drivers that copy focal length, sensor
size and fit, shift, orthographic scale and render resolution into the hidden
`cam_*` and `res_*` inputs. Drivers (not handlers) keep it working in
background renders. `cull_fov_override` is the fallback when drivers cannot be
used.

## Materials

`core/materials.py` builds one material per layer whose node tree holds all
three modes at once, so switching never loses settings (MT-01). The mode is the
output value of a Value node named `SF_Mode` (0 Procedural, 1 Image Maps,
2 Single Color).

Every user control is an input or value of a uniquely named node. The table
`materials.CONTROLS` maps a stable control key to `(node name, socket)` so the
UI and presets can address them:

| Key | Meaning | Default |
| --- | --- | --- |
| `mode` | 0 Procedural, 1 Image Maps, 2 Single Color | 0 |
| `color_root` | root shadow colour | #0B3A05 |
| `color_mid` | mid colour | #3F7A12 |
| `color_tip` | lit tip colour | #8BD63A |
| `color_haze` | far-field haze colour | #5E8F31 |
| `color_highlight` | colour flattened (windy) grass brightens toward | lighter tip colour |
| `wind_brighten` | wind brightening strength (MT-03) | 0.6 |
| `hue_jitter` | per-blade hue variation | 0.03 |
| `value_jitter` | per-blade value variation | 0.15 |
| `color_variation` | tint for `sf_variation` (dry patches) | straw yellow |
| `variation_strength` | strength of that tint | 0.5 |
| `roughness` | roughness | 0.45 |
| `specular` | specular | 0.3 |
| `translucency` | Translucent BSDF mix (0 disables) | 0.2 |
| `haze_start`, `haze_end` | distance haze range, metres (MT-04) | 30, 150 |
| `haze_strength` | distance haze amount | 0.6 |
| `single_color`, `single_variation`, `single_roughness` | Single Color mode | – |
| `image_tint` | gradient tint strength over image maps (0 = raw) | 0.5 |
| `image_wind` | wind brightening strength over image maps | 0.6 |

Image slots are Image Texture nodes named `SF_Image_<Slot>` for
`BaseColor`, `Roughness`, `Normal`, `Opacity`, `Translucency` and `AO`. Each
slot is switched on by a Value node `SF_Has_<Slot>` so an empty slot falls
back to neutral values. `assign_image`, `load_texture_set` and
`sync_image_flags(mat)` keep the flags in sync with the image nodes.

## Python side

### Data model (`props.py`)

Settings live on the modifier. PropertyGroups hold only UI state.

```
Object.swayfield: SF_ObjectSettings
    layers: Collection[SF_Layer]
    active_layer_index: int
SF_Layer
    name            display name ("Base Grass")
    modifier_name   name of its NODES modifier
    preset          grass preset id, or "CUSTOM"
    wind_preset     wind type id, or "CUSTOM"
    link_id         shared by layers created together on several objects
    + enum proxies  one EnumProperty per INT input with items (blade_source,
                    display_mode, sway_mode, *_blend, cam_sensor_fit) and
                    material_mode, implemented with get/set on the modifier or
                    material, so no value is stored twice
Scene.swayfield: SF_SceneSettings
    budget                  viewport blade budget (default 2,000,000)
    auto_optimise_threshold blades above which Add Grass turns on Optimised Mode (500,000)
```

### Operators

| bl_idname | Does |
| --- | --- |
| `swayfield.add_grass` | add a layer to every selected mesh (`preset` property) |
| `swayfield.layer_add` / `layer_duplicate` / `layer_remove` / `layer_move` | layer list editing |
| `swayfield.paint` | create or reuse `SF_<layer>_<map>` and enter Weight Paint (`map`: DENSITY, LENGTH, WIND, VARIATION) |
| `swayfield.paint_done` | back to Object mode |
| `swayfield.subdivide_surface` | add a Subdivision modifier below Swayfield for cleaner painting |
| `swayfield.apply_preset` / `apply_wind_preset` | fill inputs from a preset |
| `swayfield.save_preset` / `delete_preset` | user presets in the config folder |
| `swayfield.add_effector` | add a Vortex, Radial Blast, Trample or Shelter effector |
| `swayfield.add_exclusion` | add selected objects to the layer's exclusion collection |
| `swayfield.add_direction_empty` | create and link a wind direction empty |
| `swayfield.bake_scatter` / `free_bake` | bake or free the static half |
| `swayfield.load_texture_set` | fill image slots from a folder by filename suffix |
| `swayfield.quick_look` | test camera at 1 m, sun, AgX Punchy |
| `swayfield.upgrade_layer` | migrate a layer to the newest group version |
| `swayfield.sync_linked` | copy settings to layers sharing a `link_id` |

Every operator has `bl_options = {"REGISTER", "UNDO"}`, reports errors as
plain instructions ("Select a mesh object first") and never shows a traceback.

## Conventions

* Every Python file starts with `# SPDX-License-Identifier: GPL-3.0-or-later`.
* Read and write modifier inputs only through `core.compat`, by spec key.
* No `frame_change` or `depsgraph` handlers in the render path.
* Strings shown in the UI live in `ui/strings.py`.
* New behaviour comes with a test in `tests/` that runs in `blender --background`.
