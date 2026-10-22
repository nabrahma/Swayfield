# SPDX-License-Identifier: GPL-3.0-or-later
"""The layer material: Procedural, Image Maps and Single Color in one node tree.

All three modes live in the same tree at once and are selected by Mix Shader
factors derived from the value of the ``SF_Mode`` Value node, so switching
mode never loses the other modes' settings (MT-01).

Every user control is the output value of a uniquely named Value or RGB node.
``CONTROLS`` maps a stable key to ``(node name, output index)``. Because all
control nodes are Value or RGB nodes, the socket always refers to
``node.outputs[...]``: use ``control_socket()`` instead of resolving it
yourself.

Image slots are Image Texture nodes named ``SF_Image_<Slot>``. Whether a slot is
used is decided by the Value node ``SF_Has_<Slot>`` (0 or 1), which
``assign_image()`` and ``load_texture_set()`` keep in sync with the node's
image, and they mute empty Image Texture nodes. An empty slot falls back to a neutral value (procedural colour,
roughness control, flat normal, opaque, full translucency weight, no AO), so it
never turns a blade black or transparent. After assigning images some other
way (UI image picker), call ``sync_image_flags()``.

Shading reads the public blade attributes (``sf_factor``, ``sf_random``,
``sf_wind``, ``sf_variation``, ``sf_dist``) through Attribute nodes of type
Geometry, so it works for hair strands and ribbons in Cycles and EEVEE (MT-06).
"""

from __future__ import annotations

import os
import re

import bpy

from . import spec
from .nodes.builder import NodeBuilder, find_socket

MODE_PROCEDURAL = 0
MODE_IMAGE = 1
MODE_SINGLE = 2

MODE_ITEMS = (
    ("PROCEDURAL", "Procedural", "Root-to-tip colour gradient with per-blade variation and wind brightening"),
    ("IMAGE", "Image Maps", "Your own texture maps, tinted by the gradient and the wind"),
    ("SINGLE", "Single Color", "One flat colour with a little per-blade variation. Fast, good for stylised looks"),
)

MODE_NODE = "SF_Mode"
MATERIAL_TAG = "sf_material"
MASK_PREVIEW_NAME = "SF_MaskPreview"
UV_MAP = "UVMap"

IMAGE_SLOTS = ("BaseColor", "Roughness", "Normal", "Opacity", "Translucency", "AO")

#: Filename suffixes per slot, matched case-insensitively against the file stem.
SUFFIXES: dict[str, tuple[str, ...]] = {
    "BaseColor": ("_albedo", "_basecolor", "_base_color", "_diffuse", "_diff", "_color", "_colour", "_col"),
    "Roughness": ("_roughness", "_rough", "_rgh"),
    "Normal": ("_normal", "_nrm", "_norm", "_nor", "_normalgl", "_normal_gl"),
    "Opacity": ("_opacity", "_alpha", "_mask"),
    "Translucency": ("_translucency", "_trans", "_sss"),
    "AO": ("_ao", "_occlusion", "_ambientocclusion", "_ambient_occlusion"),
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".tga", ".bmp", ".webp", ".hdr"}

_P, _I, _S = MODE_PROCEDURAL, MODE_IMAGE, MODE_SINGLE

# key: (node name, label, kind, mode, default). Defaults are sRGB hex for colours.
_DEFS: dict[str, tuple[str, str, str, int | None, object]] = {
    "mode": (MODE_NODE, "Mode", "FLOAT", None, 0.0),
    "color_root": ("SF_ColorRoot", "Root", "COLOR", None, "#0B3A05"),
    "color_mid": ("SF_ColorMid", "Middle", "COLOR", None, "#3F7A12"),
    "color_tip": ("SF_ColorTip", "Tip", "COLOR", None, "#8BD63A"),
    "color_highlight": ("SF_ColorHighlight", "Wind Highlight", "COLOR", None, "#C4F25A"),
    "wind_brighten": ("SF_WindBrighten", "Wind Brightening", "FACTOR", _P, 0.6),
    "hue_jitter": ("SF_HueJitter", "Hue Variation", "FACTOR", None, 0.03),
    "value_jitter": ("SF_ValueJitter", "Value Variation", "FACTOR", None, 0.15),
    "color_variation": ("SF_ColorVariation", "Dry Patches", "COLOR", None, "#C2A65A"),
    "variation_strength": ("SF_VariationStrength", "Dry Patch Strength", "FACTOR", None, 0.5),
    "roughness": ("SF_Roughness", "Roughness", "FACTOR", None, 0.45),
    "specular": ("SF_Specular", "Specular", "FACTOR", None, 0.3),
    "translucency": ("SF_Translucency", "Translucency", "FACTOR", None, 0.2),
    "color_haze": ("SF_ColorHaze", "Haze", "COLOR", None, "#5E8F31"),
    "haze_start": ("SF_HazeStart", "Haze Start", "DISTANCE", None, 30.0),
    "haze_end": ("SF_HazeEnd", "Haze End", "DISTANCE", None, 150.0),
    "haze_strength": ("SF_HazeStrength", "Haze Strength", "FACTOR", None, 0.6),
    "single_color": ("SF_SingleColor", "Color", "COLOR", _S, "#4C8A1C"),
    "single_variation": ("SF_SingleVariation", "Variation", "FACTOR", _S, 0.2),
    "single_roughness": ("SF_SingleRoughness", "Roughness", "FACTOR", _S, 0.5),
    "image_tint": ("SF_ImageTint", "Gradient Tint", "FACTOR", _I, 0.5),
    "image_wind": ("SF_ImageWind", "Wind Brightening", "FACTOR", _I, 0.6),
}

#: Control key -> (node name, output index). Every control node is a Value or RGB node.
CONTROLS: dict[str, tuple[str, str | int]] = {key: (d[0], 0) for key, d in _DEFS.items()}

#: Control key -> (label, kind, mode). kind is COLOR, FACTOR, FLOAT or DISTANCE; mode None = several modes.
#: ``mode`` is better drawn as an enum from ``MODE_ITEMS`` (see ``get_mode`` / ``set_mode``).
CONTROL_INFO: dict[str, tuple[str, str, int | None]] = {key: (d[1], d[2], d[3]) for key, d in _DEFS.items()}

DEFAULTS: dict[str, object] = {key: d[4] for key, d in _DEFS.items()}

#: sf_wind values mapped to "upright" (no glow) and "flattened" (full glow).
WIND_CALM = 0.4
WIND_FLAT = 0.95
#: How much darker calm blades get, per unit of wind brightening.
GAP_DARKEN = 0.6

_NON_COLOR_SLOTS = {"Roughness", "Normal", "Opacity", "Translucency", "AO"}


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c: float) -> float:
    c = max(0.0, c)
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1.0 / 2.4) - 0.055


def hex_to_linear(value: str) -> tuple[float, float, float]:
    """``"#RRGGBB"`` (sRGB) -> linear RGB."""
    text = value.strip().lstrip("#")
    if len(text) != 6:
        raise ValueError(f"expected #RRGGBB, got {value!r}")
    return tuple(srgb_to_linear(int(text[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


def linear_to_hex(rgb) -> str:
    """Linear RGB(A) -> ``"#RRGGBB"`` (sRGB)."""
    return "#" + "".join(f"{round(min(1.0, linear_to_srgb(c)) * 255):02X}" for c in tuple(rgb)[:3])


def _to_rgba(value) -> tuple[float, float, float, float]:
    if isinstance(value, str):
        return (*hex_to_linear(value), 1.0)
    values = tuple(float(v) for v in value)
    if len(values) == 3:
        return (*values, 1.0)
    if len(values) == 4:
        return values
    raise ValueError(f"expected a hex string or an RGB/RGBA tuple, got {value!r}")


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

def is_swayfield_material(mat) -> bool:
    return (mat is not None and mat.get(MATERIAL_TAG) == "layer" and mat.node_tree is not None
            and MODE_NODE in mat.node_tree.nodes)


def control_socket(mat, key: str):
    """The socket holding the value of control ``key`` (``layout.prop(sock, "default_value")``)."""
    node_name, socket = CONTROLS[key]
    node = mat.node_tree.nodes[node_name]
    return node.outputs[socket] if isinstance(socket, int) else find_socket(node.outputs, socket)


def get_control(mat, key: str):
    """Colours return a linear RGBA tuple, everything else a float."""
    value = control_socket(mat, key).default_value
    if CONTROL_INFO[key][1] == "COLOR":
        return tuple(value)
    return float(value)


def set_control(mat, key: str, value) -> None:
    """Colours accept ``"#RRGGBB"`` (sRGB) or linear RGB/RGBA tuples."""
    sock = control_socket(mat, key)
    if CONTROL_INFO[key][1] == "COLOR":
        sock.default_value = _to_rgba(value)
    else:
        sock.default_value = float(value)


def get_mode(mat) -> int:
    return int(round(get_control(mat, "mode")))


def set_mode(mat, mode: int) -> None:
    if mode not in (MODE_PROCEDURAL, MODE_IMAGE, MODE_SINGLE):
        raise ValueError(f"invalid material mode {mode!r}")
    set_control(mat, "mode", float(mode))


# ---------------------------------------------------------------------------
# Image slots
# ---------------------------------------------------------------------------

def image_node(mat, slot: str):
    return mat.node_tree.nodes[f"SF_Image_{slot}"]


def _flag_socket(mat, slot: str):
    return mat.node_tree.nodes[f"SF_Has_{slot}"].outputs[0]


def _set_colorspace(image, slot: str) -> None:
    if slot in _NON_COLOR_SLOTS and image is not None:
        try:
            image.colorspace_settings.name = "Non-Color"
        except TypeError:
            pass  # colour space not available in this OCIO config


def assign_image(mat, slot: str, image) -> None:
    """Put ``image`` (or None to clear) into ``slot`` and switch the slot on or off."""
    if slot not in IMAGE_SLOTS:
        raise KeyError(f"unknown image slot {slot!r}")
    _set_colorspace(image, slot)
    image_node(mat, slot).image = image
    _sync_slot(mat, slot)


def _sync_slot(mat, slot: str) -> None:
    node = image_node(mat, slot)
    used = node.image is not None
    _flag_socket(mat, slot).default_value = 1.0 if used else 0.0
    node.mute = not used  # Cycles logs "Failed to load image" for empty Image Texture nodes


def sync_image_flags(mat) -> None:
    """Switch each slot on or off to match whether its node has an image."""
    for slot in IMAGE_SLOTS:
        _sync_slot(mat, slot)


def has_opacity(mat) -> bool:
    return is_swayfield_material(mat) and image_node(mat, "Opacity").image is not None


def match_slot(filename: str) -> str | None:
    """The slot a texture file belongs to, from its suffix, or None."""
    stem, ext = os.path.splitext(os.path.basename(filename))
    if ext.lower() not in IMAGE_EXTENSIONS:
        return None
    stem = stem.lower()
    # Longest suffix first, so "_diffuse" wins over "_diff" and "_normal_gl" over "_normal".
    ordered = sorted(((s, slot) for slot, sfx in SUFFIXES.items() for s in sfx), key=lambda p: -len(p[0]))
    for suffix, slot in ordered:
        if stem.endswith(suffix):
            return slot
    # Suffix followed by a qualifier ("grass_normal_dx", "grass_albedo_2k").
    for suffix, slot in ordered:
        if re.search(re.escape(suffix) + r"(?:[_\-.][a-z0-9]+)+$", stem):
            return slot
    return None


def load_texture_set(mat, directory: str) -> dict[str, str]:
    """Fill image slots from the files in ``directory``. Returns slot -> loaded file path."""
    found: dict[str, str] = {}
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        slot = match_slot(name)
        if slot is not None and slot not in found:
            found[slot] = path
    for slot, path in found.items():
        assign_image(mat, slot, bpy.data.images.load(path, check_existing=True))
    return found


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------

def _make_controls(b: NodeBuilder) -> dict:
    sockets = {}
    for key, (node_name, label, kind, _mode, default) in _DEFS.items():
        if kind == "COLOR":
            node = b.node("ShaderNodeRGB", name=node_name, label=label)
            node.outputs[0].default_value = _to_rgba(default)
        else:
            node = b.node("ShaderNodeValue", name=node_name, label=label)
            node.outputs[0].default_value = float(default)
        sockets[key] = node.outputs[0]
    return sockets


def _attribute(b: NodeBuilder, name: str):
    node = b.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=name, label=name)
    return find_socket(node.outputs, "Fac")


def _mix_color(b: NodeBuilder, factor, a, c, blend: str = "MIX"):
    node = b.node("ShaderNodeMix", data_type="RGBA", blend_type=blend, clamp_factor=True)
    b.set(find_socket(node.inputs, "Factor"), factor)
    b.set(find_socket(node.inputs, "A"), a)
    b.set(find_socket(node.inputs, "B"), c)
    return find_socket(node.outputs, "Result")


def _jitter(b: NodeBuilder, color, random, hue_amount, value_amount):
    """Hue/value variation per blade: random in [0, 1) -> +-amount."""
    centred = b.math("SUBTRACT", random, 0.5)
    hue = b.math("MULTIPLY_ADD", centred, b.math("MULTIPLY", hue_amount, 2.0), 0.5)
    other = b.math("SUBTRACT", b.math("FRACT", b.math("MULTIPLY", random, 7.37)), 0.5)
    value = b.math("MULTIPLY_ADD", other, b.math("MULTIPLY", value_amount, 2.0), 1.0)
    return b.out("ShaderNodeHueSaturation", {"Hue": hue, "Saturation": 1.0, "Value": value, "Fac": 1.0,
                                             "Color": color}, output="Color")


def _bsdf(b: NodeBuilder, color, roughness, specular, translucency, normal=None):
    """Principled BSDF mixed with a Translucent BSDF by ``translucency``."""
    principled = b.node("ShaderNodeBsdfPrincipled", {"Base Color": color, "Roughness": roughness,
                                                     "Specular IOR Level": specular, "Normal": normal})
    translucent = b.node("ShaderNodeBsdfTranslucent", {"Color": color, "Normal": normal})
    return b.out("ShaderNodeMixShader", {0: translucency, 1: principled.outputs[0], 2: translucent.outputs[0]})


def _build_tree(mat) -> None:
    b = NodeBuilder(mat.node_tree)
    c = _make_controls(b)

    factor = _attribute(b, spec.ATTR_FACTOR)
    random = _attribute(b, spec.ATTR_RANDOM)
    wind = _attribute(b, spec.ATTR_WIND)
    variation = _attribute(b, spec.ATTR_VARIATION)
    dist = _attribute(b, spec.ATTR_DIST)

    # Root -> mid -> tip gradient (Mix nodes, so the stops are addressable controls).
    lower = _mix_color(b, b.math("MULTIPLY", factor, 2.0, clamp=True), c["color_root"], c["color_mid"])
    gradient = _mix_color(b, b.math("MULTIPLY_ADD", factor, 2.0, -1.0, clamp=True), lower, c["color_tip"])
    gradient = _jitter(b, gradient, random, c["hue_jitter"], c["value_jitter"])
    # Dry patches: tint toward the variation colour, kept darker toward the root.
    dry = b.vmath("SCALE", c["color_variation"], scale=b.map_range(factor, 0.0, 1.0, 0.25, 1.0))
    gradient = _mix_color(b, b.math("MULTIPLY", variation, c["variation_strength"], clamp=True), gradient, dry)

    # Wind (MT-03). sf_wind is high almost everywhere under a steady lean, so it is remapped with a
    # smoothstep before it drives the lerp: only the flattened crests glow, and the upright blades in
    # the gaps between gusts get darker by the same strength. That contrast is what makes streaks read.
    gust = b.map_range(wind, WIND_CALM, WIND_FLAT, 0.0, 1.0, interpolation="SMOOTHSTEP")
    calm = b.math("SUBTRACT", 1.0, gust)

    def wind_brighten(color, strength):
        shade = b.math("MULTIPLY_ADD", calm, b.math("MULTIPLY", strength, -GAP_DARKEN), 1.0)
        color = b.vmath("SCALE", color, scale=shade)
        return _mix_color(b, b.math("MULTIPLY", gust, strength, clamp=True), color, c["color_highlight"])

    haze_amount = b.math("MULTIPLY", b.map_range(dist, c["haze_start"], c["haze_end"], 0.0, 1.0),
                         c["haze_strength"], clamp=True)

    def haze(color):
        return _mix_color(b, haze_amount, color, c["color_haze"])

    # -- Procedural ------------------------------------------------------------
    proc_color = haze(wind_brighten(gradient, c["wind_brighten"]))
    procedural = _bsdf(b, proc_color, c["roughness"], c["specular"], c["translucency"])

    # -- Image Maps ------------------------------------------------------------
    uv = b.out("ShaderNodeUVMap", uv_map=UV_MAP)
    tex = {}
    has = {}
    for slot in IMAGE_SLOTS:
        node = b.node("ShaderNodeTexImage", {"Vector": uv}, name=f"SF_Image_{slot}", label=slot, mute=True)
        tex[slot] = find_socket(node.outputs, "Color")
        has[slot] = b.node("ShaderNodeValue", name=f"SF_Has_{slot}", label=f"Has {slot}").outputs[0]
        has[slot].default_value = 0.0

    tinted = _mix_color(b, c["image_tint"], tex["BaseColor"], gradient, blend="COLOR")
    base = _mix_color(b, has["BaseColor"], gradient, tinted)
    ao = b.mix(has["AO"], 1.0, tex["AO"])
    base = b.vmath("MULTIPLY", base, b.combine_xyz(ao, ao, ao))
    image_color = haze(wind_brighten(base, c["image_wind"]))
    image_rough = b.mix(has["Roughness"], c["roughness"], tex["Roughness"])
    normal = b.out("ShaderNodeNormalMap", {"Strength": has["Normal"], "Color": tex["Normal"]},
                   space="TANGENT", uv_map=UV_MAP)
    image_trans = b.math("MULTIPLY", c["translucency"], b.mix(has["Translucency"], 1.0, tex["Translucency"]))
    opacity = b.mix(has["Opacity"], 1.0, tex["Opacity"])
    image_shader = _bsdf(b, image_color, image_rough, c["specular"], image_trans, normal)
    transparent = b.out("ShaderNodeBsdfTransparent")
    image_shader = b.out("ShaderNodeMixShader", {0: opacity, 1: transparent, 2: image_shader})

    # -- Single Color ------------------------------------------------------------
    single_color = haze(_jitter(b, c["single_color"], random, 0.0, c["single_variation"]))
    single = _bsdf(b, single_color, c["single_roughness"], c["specular"], c["translucency"])

    # -- Mode switch -------------------------------------------------------------
    is_image = b.math("GREATER_THAN", c["mode"], 0.5)
    is_single = b.math("GREATER_THAN", c["mode"], 1.5)
    shader = b.out("ShaderNodeMixShader", {0: is_image, 1: procedural, 2: image_shader})
    shader = b.out("ShaderNodeMixShader", {0: is_single, 1: shader, 2: single})
    output = b.node("ShaderNodeOutputMaterial", {"Surface": shader}, target="ALL")
    output.is_active_output = True
    b.arrange()


def _setup_material(mat) -> None:
    if bpy.app.version < (5, 0, 0) and not mat.use_nodes:
        mat.use_nodes = True  # always on (and deprecated) in Blender 5.x
    # MT-06: EEVEE renders opacity maps with hashed / dithered alpha.
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"
    elif hasattr(mat, "blend_method"):
        mat.blend_method = "HASHED"
    if hasattr(mat, "shadow_method"):
        mat.shadow_method = "HASHED"


def create_layer_material(name: str) -> bpy.types.Material:
    """A new layer material with all three modes, set to Procedural."""
    mat = bpy.data.materials.new(name)
    _setup_material(mat)
    _build_tree(mat)
    mat[MATERIAL_TAG] = "layer"
    mat.diffuse_color = (*hex_to_linear(DEFAULTS["color_mid"]), 1.0)  # viewport solid colour
    return mat


def ensure_mask_preview_material() -> bpy.types.Material:
    """``SF_MaskPreview``: emission of ``sf_mask``, black (0) to white (1)."""
    mat = bpy.data.materials.get(MASK_PREVIEW_NAME)
    if mat is not None and mat.get(MATERIAL_TAG) == "mask_preview" and mat.node_tree is not None:
        return mat
    if mat is None:
        mat = bpy.data.materials.new(MASK_PREVIEW_NAME)
    if bpy.app.version < (5, 0, 0) and not mat.use_nodes:
        mat.use_nodes = True
    b = NodeBuilder(mat.node_tree)
    mask = _attribute(b, spec.ATTR_MASK)
    emission = b.out("ShaderNodeEmission", {"Color": b.combine_xyz(mask, mask, mask), "Strength": 1.0})
    output = b.node("ShaderNodeOutputMaterial", {"Surface": emission}, target="ALL")
    output.is_active_output = True
    b.arrange()
    mat[MATERIAL_TAG] = "mask_preview"
    return mat
