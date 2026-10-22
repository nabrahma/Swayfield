# SPDX-License-Identifier: GPL-3.0-or-later
"""Single source of truth for every Swayfield modifier input.

Every user-facing setting is a Geometry Nodes modifier input declared here.
The node builders create the modifier interface from this table, the UI draws
it, presets are keyed by ``Input.key`` and tests validate against it.

Rules:
- ``key`` is the stable Python identifier used by presets and code.
- ``name`` is the socket name shown in Blender. Names must be unique across the
  whole table, because sub-groups expose inputs with the same names and the
  main group wires them by name.
- Enum-like inputs are INT sockets with ``items``. Item values are their index,
  so items may only ever be appended, never reordered.
- Never rename or remove an input of a released group version. Add a new
  group version instead (see ``core/versioning.py``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Attribute contract shared by the node groups and the material
# ---------------------------------------------------------------------------

#: Stable per-blade identity, written by distribution.
ATTR_ID = "id"
#: Blade growth direction (unit vector), blend of surface normal and world up.
ATTR_UP = "sf_up"
#: Position along the blade, 0 at the root and 1 at the tip.
ATTR_FACTOR = "sf_factor"
#: Current bend amount from wind, 0 to 1. Drives shader brightening.
ATTR_WIND = "sf_wind"
#: Stable random value per blade, 0 to 1.
ATTR_RANDOM = "sf_random"
#: Painted or noise colour-variation mask, 0 to 1.
ATTR_VARIATION = "sf_variation"
#: Random value per clump, 0 to 1.
ATTR_CLUMP = "sf_clump"
#: World-space centre of the blade's clump.
ATTR_CLUMP_CENTER = "sf_clump_center"
#: Distance to the active camera in metres.
ATTR_DIST = "sf_dist"
#: Blade length multiplier from length paint, mask falloff and exclusion.
ATTR_LENGTH = "sf_length"
#: Wind strength multiplier from the shelter paint map, 0 to 1.
ATTR_WIND_SCALE = "sf_wind_scale"
#: True for the long, thin, extra-fluttery wisp sub-layer.
ATTR_WISP = "sf_wisp"
#: LOD band index: 0 near, 1 mid, 2 far.
ATTR_LOD = "sf_lod"
#: Blade width multiplier from the LOD band and viewport widening.
ATTR_WIDTH = "sf_width"
#: Final density mask on the surface, used by mask preview.
ATTR_MASK = "sf_mask"
#: Root position of the blade (world-space of the modifier object).
ATTR_ROOT = "sf_root"

#: Attributes documented for user shaders (see docs/materials.md).
PUBLIC_ATTRIBUTES = (
    ATTR_FACTOR,
    ATTR_WIND,
    ATTR_RANDOM,
    ATTR_VARIATION,
    ATTR_CLUMP,
    ATTR_DIST,
)

# ---------------------------------------------------------------------------
# Input table
# ---------------------------------------------------------------------------

SOCKET_TYPES = {
    "GEOMETRY": "NodeSocketGeometry",
    "FLOAT": "NodeSocketFloat",
    "INT": "NodeSocketInt",
    "BOOLEAN": "NodeSocketBool",
    "VECTOR": "NodeSocketVector",
    "COLOR": "NodeSocketColor",
    "STRING": "NodeSocketString",
    "OBJECT": "NodeSocketObject",
    "COLLECTION": "NodeSocketCollection",
    "MATERIAL": "NodeSocketMaterial",
    "IMAGE": "NodeSocketImage",
}


@dataclass(frozen=True)
class Input:
    key: str
    name: str
    type: str
    default: object = None
    min: float | None = None
    max: float | None = None
    subtype: str = "NONE"
    description: str = ""
    panel: str = ""
    #: For enum-like INT inputs: tuples of (identifier, label, description).
    items: tuple = ()
    #: Hidden from the modifier panel (internal, driven or set by operators).
    hidden: bool = False

    @property
    def socket_type(self) -> str:
        return SOCKET_TYPES[self.type]

    def item_index(self, identifier: str) -> int:
        for i, item in enumerate(self.items):
            if item[0] == identifier:
                return i
        raise KeyError(f"{self.key} has no item {identifier!r}")


def _deg(value: float) -> float:
    return math.radians(value)


BLEND_ITEMS = (
    ("MULTIPLY", "Multiply", "Multiply with the masks above"),
    ("ADD", "Add", "Add to the masks above"),
    ("SUBTRACT", "Subtract", "Subtract from the masks above"),
    ("MIN", "Min", "Keep the lower of this mask and the masks above"),
)

PANELS = (
    "Distribution",
    "Blade Shape",
    "Masks",
    "Wind",
    "Effectors",
    "Material",
    "Performance",
    "Internal",
)

_I = Input

# Painted maps: (prefix, label, what it controls)
_PAINT_MAPS = (
    ("density", "Density", "blade density"),
    ("length", "Length", "blade length"),
    ("wind", "Wind", "wind strength (shelter)"),
    ("variation", "Variation", "the secondary colour tint"),
)


def _paint_inputs() -> list[Input]:
    out = []
    for key, label, what in _PAINT_MAPS:
        out += [
            _I(f"{key}_group", f"{label} Group", "STRING", "", panel="Masks",
               description=f"Vertex group that controls {what}. Empty means no map"),
            _I(f"{key}_invert", f"{label} Invert", "BOOLEAN", False, panel="Masks",
               description=f"Invert the {label.lower()} map, so painted areas become unpainted"),
            _I(f"{key}_contrast", f"{label} Contrast", "FLOAT", 1.0, 0.0, 10.0, panel="Masks",
               description=f"Contrast of the {label.lower()} map around 0.5. Raise it to sharpen soft strokes"),
            _I(f"{key}_threshold", f"{label} Threshold", "FLOAT", 0.0, 0.0, 1.0, "FACTOR", panel="Masks",
               description=f"Weights of the {label.lower()} map below this become 0, for crisp edges"),
        ]
    return out


def _mask_inputs(prefix: str, label: str) -> list[Input]:
    return [
        _I(f"{prefix}_enable", f"{label} Mask", "BOOLEAN", False, panel="Masks",
           description=f"Enable the {label.lower()} mask in the mask stack"),
        _I(f"{prefix}_blend", f"{label} Blend", "INT", 0, 0, len(BLEND_ITEMS) - 1, panel="Masks",
           items=BLEND_ITEMS, description=f"How the {label.lower()} mask combines with the masks above it"),
    ]


INPUTS: tuple[Input, ...] = (
    # --- Distribution -------------------------------------------------------
    _I("seed", "Seed", "INT", 0, 0, 1_000_000, panel="Distribution",
       description="Random seed for blade placement"),
    _I("density", "Density", "FLOAT", 800.0, 1.0, 20_000.0, panel="Distribution",
       description="Blades per square metre of world-space surface. Scaling the object keeps the look"),
    _I("density_ceiling", "Generation Density", "FLOAT", 2_000.0, 1.0, 20_000.0, panel="Distribution",
       description="Blades per square metre generated before thinning. Density, masks and painting thin "
                   "this set, so blades never reshuffle. Keep it at or a little above Density"),
    _I("min_distance", "Minimum Distance", "FLOAT", 0.005, 0.0, 1.0, "DISTANCE", panel="Distribution",
       description="Minimum distance between blade roots, to avoid overlapping clumps of roots"),
    _I("orient_normal", "Follow Normal", "FLOAT", 0.2, 0.0, 1.0, "FACTOR", panel="Distribution",
       description="Blend between growing straight up (0) and along the surface normal (1)"),
    _I("blade_source", "Blade Source", "INT", 0, 0, 2, panel="Distribution",
       items=(("STRANDS", "Strands", "Curves rendered as thin hair strands. Lightest, best for long soft grass"),
              ("RIBBONS", "Ribbons", "Flat tapered mesh strips with UVs, for image textures with opacity"),
              ("INSTANCES", "Custom Instances", "Your own meshes from a collection, kept instanced")),
       description="What each blade is made of"),
    _I("instance_collection", "Instance Collection", "COLLECTION", None, panel="Distribution",
       description="Collection of meshes used when Blade Source is Custom Instances"),
    _I("instance_scale_min", "Instance Scale Min", "FLOAT", 0.8, 0.01, 10.0, panel="Distribution",
       description="Smallest random scale for custom instances"),
    _I("instance_scale_max", "Instance Scale Max", "FLOAT", 1.2, 0.01, 10.0, panel="Distribution",
       description="Largest random scale for custom instances"),

    # --- Blade Shape --------------------------------------------------------
    _I("length_min", "Length Min", "FLOAT", 0.5, 0.01, 5.0, "DISTANCE", panel="Blade Shape",
       description="Shortest blade length"),
    _I("length_max", "Length Max", "FLOAT", 0.9, 0.01, 5.0, "DISTANCE", panel="Blade Shape",
       description="Longest blade length"),
    _I("root_width", "Root Width", "FLOAT", 0.006, 0.0005, 0.1, "DISTANCE", panel="Blade Shape",
       description="Blade width at the root"),
    _I("tip_taper", "Tip Taper", "FLOAT", 0.9, 0.0, 1.0, "FACTOR", panel="Blade Shape",
       description="How much the blade narrows toward the tip. 1 ends in a sharp point"),
    _I("rest_lean", "Rest Lean", "FLOAT", _deg(10), 0.0, _deg(80), "ANGLE", panel="Blade Shape",
       description="How far blades lean at rest, before wind, in a random direction"),
    _I("curl", "Curl", "FLOAT", _deg(20), 0.0, _deg(90), "ANGLE", panel="Blade Shape",
       description="Extra bend that builds up from root to tip, in the lean direction"),
    _I("random_tilt", "Random Tilt", "FLOAT", _deg(8), 0.0, _deg(45), "ANGLE", panel="Blade Shape",
       description="Random tilt of each blade away from its growth direction"),
    _I("random_rotation", "Random Rotation", "FLOAT", 1.0, 0.0, 1.0, "FACTOR", panel="Blade Shape",
       description="Random rotation around the growth direction. 1 is a full turn"),
    _I("blade_points", "Blade Points", "INT", 8, 2, 16, panel="Blade Shape",
       description="Points per blade in the near LOD band. More points give smoother bends"),
    _I("clump_density", "Clump Density", "FLOAT", 2.0, 0.0, 100.0, panel="Blade Shape",
       description="Clump centres per square metre"),
    _I("clump_radius", "Clump Radius", "FLOAT", 0.15, 0.01, 2.0, "DISTANCE", panel="Blade Shape",
       description="Radius of each clump"),
    _I("clump_pull", "Clump Pull", "FLOAT", 0.0, 0.0, 1.0, "FACTOR", panel="Blade Shape",
       description="How strongly blade tips are pulled toward their clump centre, giving a tufted look"),
    _I("wisp_percent", "Wisps", "FLOAT", 3.0, 0.0, 100.0, "PERCENTAGE", panel="Blade Shape",
       description="Share of blades that are long, thin wisps whipping above the canopy"),
    _I("wisp_length", "Wisp Length", "FLOAT", 1.3, 1.0, 3.0, panel="Blade Shape",
       description="Wisp length as a multiple of normal blade length"),
    _I("wisp_width", "Wisp Width", "FLOAT", 0.6, 0.1, 1.0, panel="Blade Shape",
       description="Wisp width as a multiple of normal blade width"),

    # --- Masks --------------------------------------------------------------
    *_paint_inputs(),
    _I("length_falloff", "Length Falloff", "FLOAT", 0.5, 0.0, 1.0, "FACTOR", panel="Masks",
       description="Blades in thinned areas are also shortened, so mask edges look natural"),
    *_mask_inputs("slope", "Slope"),
    _I("slope_min", "Slope Min", "FLOAT", 0.0, 0.0, _deg(90), "ANGLE", panel="Masks",
       description="Grass grows on surfaces at least this steep"),
    _I("slope_max", "Slope Max", "FLOAT", _deg(35), 0.0, _deg(90), "ANGLE", panel="Masks",
       description="Grass grows on surfaces at most this steep"),
    _I("slope_smooth", "Slope Smooth", "FLOAT", _deg(5), 0.0, _deg(45), "ANGLE", panel="Masks",
       description="Width of the soft transition at the slope limits"),
    *_mask_inputs("altitude", "Altitude"),
    _I("altitude_min", "Altitude Min", "FLOAT", 0.0, -10_000.0, 10_000.0, "DISTANCE", panel="Masks",
       description="Grass grows at or above this world height"),
    _I("altitude_max", "Altitude Max", "FLOAT", 10.0, -10_000.0, 10_000.0, "DISTANCE", panel="Masks",
       description="Grass grows at or below this world height"),
    _I("altitude_smooth", "Altitude Smooth", "FLOAT", 0.5, 0.0, 1_000.0, "DISTANCE", panel="Masks",
       description="Width of the soft transition at the altitude limits"),
    *_mask_inputs("noise", "Noise"),
    _I("noise_scale", "Noise Scale", "FLOAT", 0.5, 0.001, 100.0, panel="Masks",
       description="Noise frequency per metre. Smaller values give bigger patches"),
    _I("noise_contrast", "Noise Contrast", "FLOAT", 2.0, 0.0, 20.0, panel="Masks",
       description="Contrast of the noise patches. Higher gives crisper patch edges"),
    _I("noise_coverage", "Noise Coverage", "FLOAT", 0.5, 0.0, 1.0, "FACTOR", panel="Masks",
       description="Share of the surface the noise mask keeps"),
    _I("noise_seed", "Noise Seed", "INT", 0, 0, 1_000_000, panel="Masks",
       description="Random seed of the noise mask"),
    *_mask_inputs("image", "Image"),
    _I("image_mask", "Mask Image", "IMAGE", None, panel="Masks",
       description="Black-and-white image read through the surface UVs. White keeps grass"),
    _I("image_uv", "Mask UV Map", "STRING", "UVMap", panel="Masks",
       description="UV map used to read the mask image"),
    *_mask_inputs("proximity", "Proximity"),
    _I("proximity_collection", "Proximity Objects", "COLLECTION", None, panel="Masks",
       description="Grass is kept near these objects (or away from them when inverted)"),
    _I("proximity_distance", "Proximity Distance", "FLOAT", 1.0, 0.0, 1_000.0, "DISTANCE", panel="Masks",
       description="Distance from the proximity objects where the mask changes"),
    _I("proximity_smooth", "Proximity Smooth", "FLOAT", 0.5, 0.0, 1_000.0, "DISTANCE", panel="Masks",
       description="Width of the soft transition"),
    _I("proximity_invert", "Proximity Invert", "BOOLEAN", False, panel="Masks",
       description="Keep grass away from the objects instead of near them"),
    *_mask_inputs("camdist", "Camera Distance"),
    _I("camdist_min", "Camera Distance Min", "FLOAT", 0.0, 0.0, 100_000.0, "DISTANCE", panel="Masks",
       description="Grass is kept from this distance to the camera"),
    _I("camdist_max", "Camera Distance Max", "FLOAT", 100.0, 0.0, 100_000.0, "DISTANCE", panel="Masks",
       description="Grass is kept up to this distance from the camera"),
    _I("camdist_smooth", "Camera Distance Smooth", "FLOAT", 5.0, 0.0, 10_000.0, "DISTANCE", panel="Masks",
       description="Width of the soft transition"),
    _I("mask_preview", "Mask Preview", "BOOLEAN", False, panel="Masks",
       description="Show the final density as a black-to-white overlay on the surface"),

    # --- Wind ---------------------------------------------------------------
    _I("intensity", "Intensity", "FLOAT", 1.0, 0.0, 2.0, panel="Wind",
       description="Scales all wind at once. Keyframe it for gusty shots"),
    _I("direction", "Direction", "FLOAT", 0.0, 0.0, _deg(360), "ANGLE", panel="Wind",
       description="Wind heading around world Z. 0 blows toward +X"),
    _I("direction_object", "Direction Object", "OBJECT", None, panel="Wind",
       description="Optional empty whose local X axis sets the wind direction, so it can be keyframed"),
    _I("base_lean", "Base Lean", "FLOAT", 0.6, 0.0, 1.0, "FACTOR", panel="Wind",
       description="Constant push along the wind. How bent the grass is between gusts"),
    _I("gust_strength", "Gust Strength", "FLOAT", 0.4, 0.0, 1.0, "FACTOR", panel="Wind",
       description="Strength of the travelling gusts that make bright streaks"),
    _I("gust_scale", "Gust Scale", "FLOAT", 0.2, 0.02, 2.0, panel="Wind",
       description="Gust noise frequency per metre. 0.2 gives patches about 5 m across"),
    _I("gust_stretch", "Gust Stretch", "FLOAT", 3.3, 1.0, 10.0, panel="Wind",
       description="How much gusts are stretched along the wind, making long streaks"),
    _I("gust_speed", "Gust Speed", "FLOAT", 4.0, 0.0, 30.0, panel="Wind",
       description="Speed gusts travel across the field, in metres per second"),
    _I("gust_evolution", "Gust Evolution", "FLOAT", 0.15, 0.0, 2.0, panel="Wind",
       description="How fast gust shapes change while they travel, per second"),
    _I("gust_contrast", "Gust Contrast", "FLOAT", 1.5, 0.5, 5.0, panel="Wind",
       description="Contrast of the gust field. Higher gives sharper streaks with darker gaps"),
    _I("direction_variation", "Direction Variation", "FLOAT", 0.0, 0.0, _deg(90), "ANGLE", panel="Wind",
       description="How far the wind direction wanders over time, for turbulent storms"),
    _I("direction_variation_speed", "Variation Speed", "FLOAT", 0.3, 0.0, 5.0, "FREQUENCY", panel="Wind",
       description="How fast the wind direction wanders"),
    _I("wave_strength", "Wave Strength", "FLOAT", 0.0, 0.0, 1.0, "FACTOR", panel="Wind",
       description="Strength of regular rolling waves along the wind"),
    _I("wave_length", "Wavelength", "FLOAT", 4.0, 0.1, 100.0, "DISTANCE", panel="Wind",
       description="Distance between wave crests"),
    _I("wave_speed", "Wave Speed", "FLOAT", 2.0, 0.0, 30.0, panel="Wind",
       description="Speed waves travel, in metres per second"),
    _I("wave_sharpness", "Wave Sharpness", "FLOAT", 0.5, 0.0, 1.0, "FACTOR", panel="Wind",
       description="0 gives smooth sine waves, 1 gives narrow crests with wide troughs"),
    _I("flutter_strength", "Flutter Strength", "FLOAT", 0.08, 0.0, 0.5, panel="Wind",
       description="Fast, small shaking weighted toward the tips"),
    _I("flutter_frequency", "Flutter Frequency", "FLOAT", 3.0, 0.5, 10.0, "FREQUENCY", panel="Wind",
       description="How fast blades flutter, in Hz"),
    _I("wisp_flutter", "Wisp Flutter", "FLOAT", 2.0, 1.0, 4.0, panel="Wind",
       description="Flutter multiplier for wisps"),
    _I("max_bend", "Max Bend", "FLOAT", _deg(80), 0.0, _deg(89), "ANGLE", panel="Wind",
       description="Bend angle at full wind strength"),
    _I("stiffness", "Stiffness", "FLOAT", 1.6, 1.0, 3.0, panel="Wind",
       description="Bend exponent along the blade. Higher keeps the base stiff and bends the tip"),
    _I("tip_lag", "Tip Lag", "FLOAT", 0.15, 0.0, 0.5, "TIME_ABSOLUTE", panel="Wind",
       description="How far tips trail the root in time, like real stems"),
    _I("sway_mode", "Sway Mode", "INT", 0, 0, 1, panel="Wind",
       items=(("BEND", "Bend", "Blades bend along their length"),
              ("RIGID", "Rigid", "Whole blades rock without bending (Toon Bob, cheap)")),
       description="How blades respond to wind"),
    _I("time_offset", "Time Offset", "FLOAT", 0.0, -10_000.0, 10_000.0, "TIME_ABSOLUTE", panel="Wind",
       description="Shifts this layer's wind in time, so layers do not move in lockstep"),
    _I("speed_multiplier", "Speed Multiplier", "FLOAT", 1.0, 0.0, 10.0, panel="Wind",
       description="Speeds up or slows down all wind motion for this layer"),
    _I("loop_enable", "Loop", "BOOLEAN", False, panel="Wind",
       description="Make the wind repeat seamlessly every Loop Length frames"),
    _I("loop_frames", "Loop Length", "INT", 240, 2, 100_000, panel="Wind",
       description="Loop length in frames. Frame Loop Length + 1 matches frame 1"),
    _I("freeze", "Freeze Wind", "BOOLEAN", False, panel="Wind",
       description="Hold the wind still at Time Offset, for posing and stills"),
    _I("mute_viewport", "Mute in Viewport", "BOOLEAN", False, panel="Wind",
       description="Turn wind off in the viewport only, for speed. Renders keep wind"),

    # --- Effectors ----------------------------------------------------------
    _I("effector_collection", "Effectors", "COLLECTION", None, panel="Effectors",
       description="Collection of Swayfield effector objects (vortex, blast, trample, shelter)"),
    _I("exclusion_collection", "Exclusion Objects", "COLLECTION", None, panel="Effectors",
       description="Grass is removed around these objects"),
    _I("exclusion_distance", "Exclusion Distance", "FLOAT", 0.2, 0.0, 100.0, "DISTANCE", panel="Effectors",
       description="Grass is removed within this distance of the exclusion objects"),
    _I("exclusion_falloff", "Exclusion Falloff", "FLOAT", 0.3, 0.0, 100.0, "DISTANCE", panel="Effectors",
       description="Band of shorter grass at the border of excluded areas"),

    # --- Material -----------------------------------------------------------
    _I("material", "Material", "MATERIAL", None, panel="Material",
       description="Material of the grass blades"),
    _I("instance_material_override", "Override Instance Material", "BOOLEAN", False, panel="Material",
       description="Use the layer material on custom instances instead of their own materials"),

    # --- Performance --------------------------------------------------------
    _I("optimised", "Optimised Mode", "BOOLEAN", False, panel="Performance",
       description="Lighten the viewport with the settings below. Final renders are unaffected"),
    _I("viewport_density", "Viewport Density", "FLOAT", 20.0, 0.0, 100.0, "PERCENTAGE", panel="Performance",
       description="Share of blades shown in the viewport in Optimised Mode. Blades widen to stay readable"),
    _I("display_mode", "Display As", "INT", 0, 0, 3, panel="Performance",
       items=(("FULL", "Full", "Full blades"),
              ("LITE", "Strands Lite", "Blades with 3 points and rigid sway"),
              ("POINTS", "Points", "One dot per blade"),
              ("BOUNDS", "Bounds", "Only the layer's bounding box")),
       description="How grass is drawn in the viewport in Optimised Mode"),
    _I("frustum_cull", "Camera Culling", "BOOLEAN", True, panel="Performance",
       description="Remove blades outside the active camera's view in the viewport (Optimised Mode)"),
    _I("render_cull", "Render Culling", "BOOLEAN", True, panel="Performance",
       description="Also remove blades outside the camera view at render time"),
    _I("cull_margin_viewport", "Viewport Margin", "FLOAT", 10.0, 0.0, 200.0, "PERCENTAGE", panel="Performance",
       description="Extra border kept around the camera view in the viewport"),
    _I("cull_margin_render", "Render Margin", "FLOAT", 15.0, 0.0, 200.0, "PERCENTAGE", panel="Performance",
       description="Extra border kept around the camera view at render, to avoid pop-in and motion blur gaps"),
    _I("cull_fov_override", "Culling FOV Override", "FLOAT", 0.0, 0.0, _deg(179), "ANGLE", panel="Performance",
       description="Fixed horizontal field of view for culling. 0 reads the camera lens"),
    _I("lod_enable", "Distance LOD", "BOOLEAN", True, panel="Performance",
       description="Use cheaper, sparser blades far from the camera"),
    _I("lod_near", "Near Distance", "FLOAT", 15.0, 0.0, 100_000.0, "DISTANCE", panel="Performance",
       description="Blades closer than this are full detail"),
    _I("lod_mid", "Mid Distance", "FLOAT", 40.0, 0.0, 100_000.0, "DISTANCE", panel="Performance",
       description="Blades between Near and this distance are mid detail"),
    _I("lod_far", "Far Distance", "FLOAT", 150.0, 0.0, 100_000.0, "DISTANCE", panel="Performance",
       description="Blades beyond this distance are removed. 0 keeps far blades at any distance"),
    _I("lod_blend", "Band Blend", "FLOAT", 3.0, 0.0, 1_000.0, "DISTANCE", panel="Performance",
       description="Width of the blend between LOD bands"),
    _I("lod_mid_density", "Mid Density", "FLOAT", 0.5, 0.0, 1.0, "FACTOR", panel="Performance",
       description="Share of blades kept in the mid band"),
    _I("lod_far_density", "Far Density", "FLOAT", 0.1, 0.0, 1.0, "FACTOR", panel="Performance",
       description="Share of blades kept in the far band"),
    _I("lod_mid_width", "Mid Width", "FLOAT", 1.4, 1.0, 5.0, panel="Performance",
       description="Width multiplier in the mid band, to keep coverage"),
    _I("lod_far_width", "Far Width", "FLOAT", 2.5, 1.0, 10.0, panel="Performance",
       description="Width multiplier in the far band"),
    _I("lod_mid_points", "Mid Points", "INT", 4, 2, 16, panel="Performance",
       description="Points per blade in the mid band"),
    _I("lod_far_points", "Far Points", "INT", 2, 2, 16, panel="Performance",
       description="Points per blade in the far band"),
    _I("anim_lod_enable", "Animation LOD", "BOOLEAN", True, panel="Performance",
       description="Far blades rock as a whole instead of bending, which is cheaper"),
    _I("anim_lod_start", "Animation LOD Start", "FLOAT", 30.0, 0.0, 100_000.0, "DISTANCE", panel="Performance",
       description="Distance where blades start switching to rigid sway"),
    _I("anim_lod_end", "Animation LOD End", "FLOAT", 45.0, 0.0, 100_000.0, "DISTANCE", panel="Performance",
       description="Distance beyond which all blades use rigid sway"),

    # --- Internal (set by operators and drivers) ----------------------------
    _I("seed_offset", "Seed Offset", "INT", 0, 0, 1_000_000, panel="Internal", hidden=True,
       description="Per-object seed offset, set when several objects share a layer"),
    _I("simplify", "Simplify Factor", "FLOAT", 1.0, 0.0, 1.0, "FACTOR", panel="Internal", hidden=True,
       description="Viewport density scale, driven from the scene's Simplify settings"),
    _I("preview_material", "Preview Material", "MATERIAL", None, panel="Internal", hidden=True,
       description="Material used by Mask Preview"),
    _I("cam_focal_length", "Camera Focal Length", "FLOAT", 50.0, 0.1, 10_000.0, panel="Internal", hidden=True,
       description="Driven from the active camera, in millimetres"),
    _I("cam_sensor_width", "Camera Sensor Width", "FLOAT", 36.0, 0.1, 1_000.0, panel="Internal", hidden=True,
       description="Driven from the active camera, in millimetres"),
    _I("cam_sensor_height", "Camera Sensor Height", "FLOAT", 24.0, 0.1, 1_000.0, panel="Internal", hidden=True,
       description="Driven from the active camera, in millimetres"),
    _I("cam_sensor_fit", "Camera Sensor Fit", "INT", 0, 0, 2, panel="Internal", hidden=True,
       items=(("AUTO", "Auto", ""), ("HORIZONTAL", "Horizontal", ""), ("VERTICAL", "Vertical", "")),
       description="Driven from the active camera"),
    _I("cam_shift_x", "Camera Shift X", "FLOAT", 0.0, -10.0, 10.0, panel="Internal", hidden=True,
       description="Driven from the active camera"),
    _I("cam_shift_y", "Camera Shift Y", "FLOAT", 0.0, -10.0, 10.0, panel="Internal", hidden=True,
       description="Driven from the active camera"),
    _I("cam_ortho", "Camera Orthographic", "BOOLEAN", False, panel="Internal", hidden=True,
       description="Driven from the active camera"),
    _I("cam_ortho_scale", "Camera Ortho Scale", "FLOAT", 6.0, 0.001, 100_000.0, panel="Internal", hidden=True,
       description="Driven from the active camera"),
    _I("res_x", "Resolution X", "INT", 1920, 1, 100_000, panel="Internal", hidden=True,
       description="Driven from the scene render resolution"),
    _I("res_y", "Resolution Y", "INT", 1080, 1, 100_000, panel="Internal", hidden=True,
       description="Driven from the scene render resolution"),
)

BY_KEY: dict[str, Input] = {i.key: i for i in INPUTS}
BY_NAME: dict[str, Input] = {i.name: i for i in INPUTS}

assert len(BY_KEY) == len(INPUTS), "duplicate input key"
assert len(BY_NAME) == len(INPUTS), "duplicate input name"
assert all(i.panel in PANELS for i in INPUTS), "unknown panel"


def inputs_in_panel(panel: str) -> list[Input]:
    return [i for i in INPUTS if i.panel == panel]


def get(key: str) -> Input:
    return BY_KEY[key]


def defaults() -> dict[str, object]:
    """Default value of every input, keyed by ``Input.key``."""
    return {i.key: i.default for i in INPUTS}
