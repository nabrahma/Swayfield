<!--
  GENERATED FILE. Do not edit by hand.
  Source: swayfield/core/spec.py
  Regenerate with: python tools/gen_settings_reference.py
-->

# Settings reference

Every Swayfield setting is an input of the layer's Geometry Nodes modifier. This page lists them all, grouped by panel. **Key** is the name used in [preset files](../guide/presets.md). Angles are shown in degrees here, and in preset files too.

## Distribution

| Setting | Key | Type | Default | Range | Description |
| --- | --- | --- | --- | --- | --- |
| Surface | `surface` | Object | none |  | Mesh object the grass grows on. Its modifiers are included. |
| Seed | `seed` | Integer | 0 | 0 to 1000000 | Random seed for blade placement. |
| Density | `density` | Float | 800 | 1 to 20000 | Blades per square metre of world-space surface. Scaling the object keeps the look. |
| Generation Density | `density_ceiling` | Float | 2000 | 1 to 20000 | Blades per square metre generated before thinning. Density, masks and painting thin this set, so blades never reshuffle. Keep it at or a little above Density. |
| Minimum Distance | `min_distance` | Float | 0.005 m | 0 m to 1 m | Minimum distance between blade roots, to avoid overlapping clumps of roots. |
| Follow Normal | `orient_normal` | Float | 0.2 | 0 to 1 | Blend between growing straight up (0) and along the surface normal (1). |
| Blade Source | `blade_source` | Choice | Strands |  | What each blade is made of. Options: **Strands** (Curves rendered as thin hair strands. Lightest, best for long soft grass); **Ribbons** (Flat tapered mesh strips with UVs, for image textures with opacity); **Custom Instances** (Your own meshes from a collection, kept instanced). |
| Instance Collection | `instance_collection` | Collection | none |  | Collection of meshes used when Blade Source is Custom Instances. |
| Instance Scale Min | `instance_scale_min` | Float | 0.8 | 0.01 to 10 | Smallest random scale for custom instances. |
| Instance Scale Max | `instance_scale_max` | Float | 1.2 | 0.01 to 10 | Largest random scale for custom instances. |

## Blade Shape

| Setting | Key | Type | Default | Range | Description |
| --- | --- | --- | --- | --- | --- |
| Length Min | `length_min` | Float | 0.5 m | 0.01 m to 5 m | Shortest blade length. |
| Length Max | `length_max` | Float | 0.9 m | 0.01 m to 5 m | Longest blade length. |
| Root Width | `root_width` | Float | 0.006 m | 0.0005 m to 0.1 m | Blade width at the root. |
| Tip Taper | `tip_taper` | Float | 0.9 | 0 to 1 | How much the blade narrows toward the tip. 1 ends in a sharp point. |
| Rest Lean | `rest_lean` | Float | 10° | 0° to 80° | How far blades lean at rest, before wind, in a random direction. |
| Curl | `curl` | Float | 20° | 0° to 90° | Extra bend that builds up from root to tip, in the lean direction. |
| Random Tilt | `random_tilt` | Float | 8° | 0° to 45° | Random tilt of each blade away from its growth direction. |
| Random Rotation | `random_rotation` | Float | 1 | 0 to 1 | Random rotation around the growth direction. 1 is a full turn. |
| Blade Points | `blade_points` | Integer | 8 | 2 to 16 | Points per blade in the near LOD band. More points give smoother bends. |
| Clump Density | `clump_density` | Float | 2 | 0 to 100 | Clump centres per square metre. |
| Clump Radius | `clump_radius` | Float | 0.15 m | 0.01 m to 2 m | Radius of each clump. |
| Clump Pull | `clump_pull` | Float | 0 | 0 to 1 | How strongly blade tips are pulled toward their clump centre, giving a tufted look. |
| Wisps | `wisp_percent` | Float | 3 % | 0 % to 100 % | Share of blades that are long, thin wisps whipping above the canopy. |
| Wisp Length | `wisp_length` | Float | 1.3 | 1 to 3 | Wisp length as a multiple of normal blade length. |
| Wisp Width | `wisp_width` | Float | 0.6 | 0.1 to 1 | Wisp width as a multiple of normal blade width. |

## Masks

| Setting | Key | Type | Default | Range | Description |
| --- | --- | --- | --- | --- | --- |
| Density Group | `density_group` | Text | empty |  | Vertex group that controls blade density. Empty means no map. |
| Density Invert | `density_invert` | Toggle | off |  | Invert the density map, so painted areas become unpainted. |
| Density Contrast | `density_contrast` | Float | 1 | 0 to 10 | Contrast of the density map around 0.5. Raise it to sharpen soft strokes. |
| Density Threshold | `density_threshold` | Float | 0 | 0 to 1 | Weights of the density map below this become 0, for crisp edges. |
| Length Group | `length_group` | Text | empty |  | Vertex group that controls blade length. Empty means no map. |
| Length Invert | `length_invert` | Toggle | off |  | Invert the length map, so painted areas become unpainted. |
| Length Contrast | `length_contrast` | Float | 1 | 0 to 10 | Contrast of the length map around 0.5. Raise it to sharpen soft strokes. |
| Length Threshold | `length_threshold` | Float | 0 | 0 to 1 | Weights of the length map below this become 0, for crisp edges. |
| Wind Group | `wind_group` | Text | empty |  | Vertex group that controls wind strength (shelter). Empty means no map. |
| Wind Invert | `wind_invert` | Toggle | off |  | Invert the wind map, so painted areas become unpainted. |
| Wind Contrast | `wind_contrast` | Float | 1 | 0 to 10 | Contrast of the wind map around 0.5. Raise it to sharpen soft strokes. |
| Wind Threshold | `wind_threshold` | Float | 0 | 0 to 1 | Weights of the wind map below this become 0, for crisp edges. |
| Variation Group | `variation_group` | Text | empty |  | Vertex group that controls the secondary colour tint. Empty means no map. |
| Variation Invert | `variation_invert` | Toggle | off |  | Invert the variation map, so painted areas become unpainted. |
| Variation Contrast | `variation_contrast` | Float | 1 | 0 to 10 | Contrast of the variation map around 0.5. Raise it to sharpen soft strokes. |
| Variation Threshold | `variation_threshold` | Float | 0 | 0 to 1 | Weights of the variation map below this become 0, for crisp edges. |
| Length Falloff | `length_falloff` | Float | 0.5 | 0 to 1 | Blades in thinned areas are also shortened, so mask edges look natural. |
| Slope Mask | `slope_enable` | Toggle | off |  | Enable the slope mask in the mask stack. |
| Slope Blend | `slope_blend` | Choice | Multiply |  | How the slope mask combines with the masks above it. Options: **Multiply** (Multiply with the masks above); **Add** (Add to the masks above); **Subtract** (Subtract from the masks above); **Min** (Keep the lower of this mask and the masks above). |
| Slope Min | `slope_min` | Float | 0° | 0° to 90° | Grass grows on surfaces at least this steep. |
| Slope Max | `slope_max` | Float | 35° | 0° to 90° | Grass grows on surfaces at most this steep. |
| Slope Smooth | `slope_smooth` | Float | 5° | 0° to 45° | Width of the soft transition at the slope limits. |
| Altitude Mask | `altitude_enable` | Toggle | off |  | Enable the altitude mask in the mask stack. |
| Altitude Blend | `altitude_blend` | Choice | Multiply |  | How the altitude mask combines with the masks above it. Options: **Multiply** (Multiply with the masks above); **Add** (Add to the masks above); **Subtract** (Subtract from the masks above); **Min** (Keep the lower of this mask and the masks above). |
| Altitude Min | `altitude_min` | Float | 0 m | -10000 m to 10000 m | Grass grows at or above this world height. |
| Altitude Max | `altitude_max` | Float | 10 m | -10000 m to 10000 m | Grass grows at or below this world height. |
| Altitude Smooth | `altitude_smooth` | Float | 0.5 m | 0 m to 1000 m | Width of the soft transition at the altitude limits. |
| Noise Mask | `noise_enable` | Toggle | off |  | Enable the noise mask in the mask stack. |
| Noise Blend | `noise_blend` | Choice | Multiply |  | How the noise mask combines with the masks above it. Options: **Multiply** (Multiply with the masks above); **Add** (Add to the masks above); **Subtract** (Subtract from the masks above); **Min** (Keep the lower of this mask and the masks above). |
| Noise Scale | `noise_scale` | Float | 0.5 | 0.001 to 100 | Noise frequency per metre. Smaller values give bigger patches. |
| Noise Contrast | `noise_contrast` | Float | 2 | 0 to 20 | Contrast of the noise patches. Higher gives crisper patch edges. |
| Noise Coverage | `noise_coverage` | Float | 0.5 | 0 to 1 | Share of the surface the noise mask keeps. |
| Noise Seed | `noise_seed` | Integer | 0 | 0 to 1000000 | Random seed of the noise mask. |
| Image Mask | `image_enable` | Toggle | off |  | Enable the image mask in the mask stack. |
| Image Blend | `image_blend` | Choice | Multiply |  | How the image mask combines with the masks above it. Options: **Multiply** (Multiply with the masks above); **Add** (Add to the masks above); **Subtract** (Subtract from the masks above); **Min** (Keep the lower of this mask and the masks above). |
| Mask Image | `image_mask` | Image | none |  | Black-and-white image read through the surface UVs. White keeps grass. |
| Mask UV Map | `image_uv` | Text | `UVMap` |  | UV map used to read the mask image. |
| Proximity Mask | `proximity_enable` | Toggle | off |  | Enable the proximity mask in the mask stack. |
| Proximity Blend | `proximity_blend` | Choice | Multiply |  | How the proximity mask combines with the masks above it. Options: **Multiply** (Multiply with the masks above); **Add** (Add to the masks above); **Subtract** (Subtract from the masks above); **Min** (Keep the lower of this mask and the masks above). |
| Proximity Objects | `proximity_collection` | Collection | none |  | Grass is kept near these objects (or away from them when inverted). |
| Proximity Distance | `proximity_distance` | Float | 1 m | 0 m to 1000 m | Distance from the proximity objects where the mask changes. |
| Proximity Smooth | `proximity_smooth` | Float | 0.5 m | 0 m to 1000 m | Width of the soft transition. |
| Proximity Invert | `proximity_invert` | Toggle | off |  | Keep grass away from the objects instead of near them. |
| Camera Distance Mask | `camdist_enable` | Toggle | off |  | Enable the camera distance mask in the mask stack. |
| Camera Distance Blend | `camdist_blend` | Choice | Multiply |  | How the camera distance mask combines with the masks above it. Options: **Multiply** (Multiply with the masks above); **Add** (Add to the masks above); **Subtract** (Subtract from the masks above); **Min** (Keep the lower of this mask and the masks above). |
| Camera Distance Min | `camdist_min` | Float | 0 m | 0 m to 100000 m | Grass is kept from this distance to the camera. |
| Camera Distance Max | `camdist_max` | Float | 100 m | 0 m to 100000 m | Grass is kept up to this distance from the camera. |
| Camera Distance Smooth | `camdist_smooth` | Float | 5 m | 0 m to 10000 m | Width of the soft transition. |
| Mask Preview | `mask_preview` | Toggle | off |  | Show the final density as a black-to-white overlay on the surface. |

## Wind

| Setting | Key | Type | Default | Range | Description |
| --- | --- | --- | --- | --- | --- |
| Intensity | `intensity` | Float | 1 | 0 to 2 | Scales all wind at once. Keyframe it for gusty shots. |
| Direction | `direction` | Float | 0° | 0° to 360° | Wind heading around world Z. 0 blows toward +X. |
| Direction Object | `direction_object` | Object | none |  | Optional empty whose local X axis sets the wind direction, so it can be keyframed. |
| Base Lean | `base_lean` | Float | 0.6 | 0 to 1 | Constant push along the wind. How bent the grass is between gusts. |
| Gust Strength | `gust_strength` | Float | 0.4 | 0 to 1 | Strength of the travelling gusts that make bright streaks. |
| Gust Scale | `gust_scale` | Float | 0.2 | 0.02 to 2 | Gust noise frequency per metre. 0.2 gives patches about 5 m across. |
| Gust Stretch | `gust_stretch` | Float | 3.3 | 1 to 10 | How much gusts are stretched along the wind, making long streaks. |
| Gust Speed | `gust_speed` | Float | 4 | 0 to 30 | Speed gusts travel across the field, in metres per second. |
| Gust Evolution | `gust_evolution` | Float | 0.15 | 0 to 2 | How fast gust shapes change while they travel, per second. |
| Gust Contrast | `gust_contrast` | Float | 1.5 | 0.5 to 5 | Contrast of the gust field. Higher gives sharper streaks with darker gaps. |
| Direction Variation | `direction_variation` | Float | 0° | 0° to 90° | How far the wind direction wanders over time, for turbulent storms. |
| Variation Speed | `direction_variation_speed` | Float | 0.3 Hz | 0 Hz to 5 Hz | How fast the wind direction wanders. |
| Wave Strength | `wave_strength` | Float | 0 | 0 to 1 | Strength of regular rolling waves along the wind. |
| Wavelength | `wave_length` | Float | 4 m | 0.1 m to 100 m | Distance between wave crests. |
| Wave Speed | `wave_speed` | Float | 2 | 0 to 30 | Speed waves travel, in metres per second. |
| Wave Sharpness | `wave_sharpness` | Float | 0.5 | 0 to 1 | 0 gives smooth sine waves, 1 gives narrow crests with wide troughs. |
| Flutter Strength | `flutter_strength` | Float | 0.08 | 0 to 0.5 | Fast, small shaking weighted toward the tips. |
| Flutter Frequency | `flutter_frequency` | Float | 3 Hz | 0.5 Hz to 10 Hz | How fast blades flutter, in Hz. |
| Wisp Flutter | `wisp_flutter` | Float | 2 | 1 to 4 | Flutter multiplier for wisps. |
| Max Bend | `max_bend` | Float | 80° | 0° to 89° | Bend angle at full wind strength. |
| Stiffness | `stiffness` | Float | 1.6 | 1 to 3 | Bend exponent along the blade. Higher keeps the base stiff and bends the tip. |
| Tip Lag | `tip_lag` | Float | 0.15 s | 0 s to 0.5 s | How far tips trail the root in time, like real stems. |
| Sway Mode | `sway_mode` | Choice | Bend |  | How blades respond to wind. Options: **Bend** (Blades bend along their length); **Rigid** (Whole blades rock without bending (Toon Bob, cheap)). |
| Time Offset | `time_offset` | Float | 0 s | -10000 s to 10000 s | Shifts this layer's wind in time, so layers do not move in lockstep. |
| Speed Multiplier | `speed_multiplier` | Float | 1 | 0 to 10 | Speeds up or slows down all wind motion for this layer. |
| Loop | `loop_enable` | Toggle | off |  | Make the wind repeat seamlessly every Loop Length frames. |
| Loop Length | `loop_frames` | Integer | 240 | 2 to 100000 | Loop length in frames. Frame Loop Length + 1 matches frame 1. |
| Freeze Wind | `freeze` | Toggle | off |  | Hold the wind still at Time Offset, for posing and stills. |
| Mute in Viewport | `mute_viewport` | Toggle | off |  | Turn wind off in the viewport only, for speed. Renders keep wind. |

## Effectors

| Setting | Key | Type | Default | Range | Description |
| --- | --- | --- | --- | --- | --- |
| Effectors | `effector_collection` | Collection | none |  | Collection of Swayfield effector objects (vortex, blast, trample, shelter). |
| Exclusion Objects | `exclusion_collection` | Collection | none |  | Grass is removed around these objects. |
| Exclusion Distance | `exclusion_distance` | Float | 0.2 m | 0 m to 100 m | Grass is removed within this distance of the exclusion objects. |
| Exclusion Falloff | `exclusion_falloff` | Float | 0.3 m | 0 m to 100 m | Band of shorter grass at the border of excluded areas. |

## Material

| Setting | Key | Type | Default | Range | Description |
| --- | --- | --- | --- | --- | --- |
| Material | `material` | Material | none |  | Material of the grass blades. |
| Override Instance Material | `instance_material_override` | Toggle | off |  | Use the layer material on custom instances instead of their own materials. |

## Performance

| Setting | Key | Type | Default | Range | Description |
| --- | --- | --- | --- | --- | --- |
| Optimised Mode | `optimised` | Toggle | off |  | Lighten the viewport with the settings below. Final renders are unaffected. |
| Viewport Density | `viewport_density` | Float | 20 % | 0 % to 100 % | Share of blades shown in the viewport in Optimised Mode. Blades widen to stay readable. |
| Display As | `display_mode` | Choice | Full |  | How grass is drawn in the viewport in Optimised Mode. Options: **Full** (Full blades); **Strands Lite** (Blades with 3 points and rigid sway); **Points** (One dot per blade); **Bounds** (Only the layer's bounding box). |
| Camera Culling | `frustum_cull` | Toggle | on |  | Remove blades outside the active camera's view in the viewport (Optimised Mode). |
| Render Culling | `render_cull` | Toggle | on |  | Also remove blades outside the camera view at render time. |
| Viewport Margin | `cull_margin_viewport` | Float | 10 % | 0 % to 200 % | Extra border kept around the camera view in the viewport. |
| Render Margin | `cull_margin_render` | Float | 15 % | 0 % to 200 % | Extra border kept around the camera view at render, to avoid pop-in and motion blur gaps. |
| Culling FOV Override | `cull_fov_override` | Float | 0° | 0° to 179° | Fixed horizontal field of view for culling. 0 reads the camera lens. |
| Distance LOD | `lod_enable` | Toggle | on |  | Use cheaper, sparser blades far from the camera. |
| Near Distance | `lod_near` | Float | 15 m | 0 m to 100000 m | Blades closer than this are full detail. |
| Mid Distance | `lod_mid` | Float | 40 m | 0 m to 100000 m | Blades between Near and this distance are mid detail. |
| Far Distance | `lod_far` | Float | 150 m | 0 m to 100000 m | Blades beyond this distance are removed. 0 keeps far blades at any distance. |
| Band Blend | `lod_blend` | Float | 3 m | 0 m to 1000 m | Width of the blend between LOD bands. |
| Mid Density | `lod_mid_density` | Float | 0.5 | 0 to 1 | Share of blades kept in the mid band. |
| Far Density | `lod_far_density` | Float | 0.1 | 0 to 1 | Share of blades kept in the far band. |
| Mid Width | `lod_mid_width` | Float | 1.4 | 1 to 5 | Width multiplier in the mid band, to keep coverage. |
| Far Width | `lod_far_width` | Float | 2.5 | 1 to 10 | Width multiplier in the far band. |
| Mid Points | `lod_mid_points` | Integer | 4 | 2 to 16 | Points per blade in the mid band. |
| Far Points | `lod_far_points` | Integer | 2 | 2 to 16 | Points per blade in the far band. |
| Animation LOD | `anim_lod_enable` | Toggle | on |  | Far blades rock as a whole instead of bending, which is cheaper. |
| Animation LOD Start | `anim_lod_start` | Float | 30 m | 0 m to 100000 m | Distance where blades start switching to rigid sway. |
| Animation LOD End | `anim_lod_end` | Float | 45 m | 0 m to 100000 m | Distance beyond which all blades use rigid sway. |

## Internal (hidden)

??? note "Inputs set by operators and drivers"
    You should not need to touch these. Swayfield sets them for you, for example by copying the active camera's lens.

    | Setting | Key | Type | Default | Range | Description |
    | --- | --- | --- | --- | --- | --- |
    | Seed Offset | `seed_offset` | Integer | 0 | 0 to 1000000 | Per-object seed offset, set when several objects share a layer. |
    | Simplify Factor | `simplify` | Float | 1 | 0 to 1 | Viewport density scale, driven from the scene's Simplify settings. |
    | Preview Material | `preview_material` | Material | none |  | Material used by Mask Preview. |
    | Camera Focal Length | `cam_focal_length` | Float | 50 | 0.1 to 10000 | Driven from the active camera, in millimetres. |
    | Camera Sensor Width | `cam_sensor_width` | Float | 36 | 0.1 to 1000 | Driven from the active camera, in millimetres. |
    | Camera Sensor Height | `cam_sensor_height` | Float | 24 | 0.1 to 1000 | Driven from the active camera, in millimetres. |
    | Camera Sensor Fit | `cam_sensor_fit` | Choice | Auto |  | Driven from the active camera. Options: **Auto**; **Horizontal**; **Vertical**. |
    | Camera Shift X | `cam_shift_x` | Float | 0 | -10 to 10 | Driven from the active camera. |
    | Camera Shift Y | `cam_shift_y` | Float | 0 | -10 to 10 | Driven from the active camera. |
    | Camera Orthographic | `cam_ortho` | Toggle | off |  | Driven from the active camera. |
    | Camera Ortho Scale | `cam_ortho_scale` | Float | 6 | 0.001 to 100000 | Driven from the active camera. |
    | Resolution X | `res_x` | Integer | 1920 | 1 to 100000 | Driven from the scene render resolution. |
    | Resolution Y | `res_y` | Integer | 1080 | 1 to 100000 | Driven from the scene render resolution. |
