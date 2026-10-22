# SPDX-License-Identifier: GPL-3.0-or-later
"""Load, validate, apply and save JSON presets (grass looks and wind types).

Presets only hold "look" inputs. Object, collection, material, image and string
inputs, seeds, hidden inputs and per-shot wind settings are never part of one.
ANGLE inputs are written in degrees in JSON and converted on load and save.
Colours are ``#RRGGBB`` sRGB hex.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path

from . import compat, spec

KINDS = ("GRASS", "WIND")
EFFECTORS = ("VORTEX", "RADIAL_BLAST", "TRAMPLE")
USER_PREFIX = "USER_"
SCHEMA = 1

_TOP_KEYS = {"schema", "id", "name", "description", "wind", "effector", "inputs", "material"}
_EXCLUDED_TYPES = {"GEOMETRY", "OBJECT", "COLLECTION", "MATERIAL", "IMAGE", "STRING"}
_EXCLUDED_KEYS = {"seed", "seed_offset", "noise_seed", "mask_preview"}
#: Wind-panel inputs that belong to the user's shot, not to a wind type.
SHOT_WIND_KEYS = frozenset({"direction", "direction_object", "time_offset", "loop_enable", "loop_frames",
                            "freeze", "mute_viewport"})
#: Performance inputs a grass preset may set but that are not part of its identity.
EXTRA_PRESET_KEYS = ("optimised", "viewport_density")


def _is_look(i: spec.Input) -> bool:
    return i.type not in _EXCLUDED_TYPES and i.key not in _EXCLUDED_KEYS and not i.hidden


#: Wind-type inputs (every wind preset sets all of them).
WIND_KEYS: tuple[str, ...] = tuple(
    i.key for i in spec.INPUTS if i.panel == "Wind" and _is_look(i) and i.key not in SHOT_WIND_KEYS)
#: Distribution and Blade Shape look inputs.
SHAPE_KEYS: tuple[str, ...] = tuple(
    i.key for i in spec.INPUTS if i.panel in ("Distribution", "Blade Shape") and _is_look(i))
#: Inputs reset, snapshotted and hashed.
LOOK_KEYS: tuple[str, ...] = SHAPE_KEYS + WIND_KEYS
#: Inputs a preset file may contain.
GRASS_KEYS = frozenset(LOOK_KEYS) | set(EXTRA_PRESET_KEYS)
WIND_FILE_KEYS = frozenset(WIND_KEYS)

#: Material control keys (docs/architecture.md); colours are hex in JSON.
MATERIAL_KEYS = frozenset({
    "mode", "color_root", "color_mid", "color_tip", "color_haze", "color_highlight", "wind_brighten",
    "hue_jitter", "value_jitter", "color_variation", "variation_strength", "roughness", "specular",
    "translucency", "haze_start", "haze_end", "haze_strength", "single_color", "single_variation",
    "single_roughness", "image_tint", "image_wind"})
COLOR_KEYS = frozenset({"color_root", "color_mid", "color_tip", "color_haze", "color_highlight",
                        "color_variation", "single_color"})
_MATERIAL_RANGES = {
    "mode": (0, 2), "wind_brighten": (0, 1), "hue_jitter": (0, 1), "value_jitter": (0, 1),
    "variation_strength": (0, 1), "roughness": (0, 1), "specular": (0, 1), "translucency": (0, 1),
    "haze_start": (0, 1e5), "haze_end": (0, 1e5), "haze_strength": (0, 1), "single_variation": (0, 1),
    "single_roughness": (0, 1), "image_tint": (0, 1), "image_wind": (0, 1)}

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

def builtin_dir() -> Path:
    """Folder with the presets that ship with the add-on."""
    return Path(__file__).resolve().parent.parent / "presets"


def _base_package() -> str:
    return (__package__ or "swayfield").rsplit(".", 1)[0]


def user_dir() -> Path:
    """Folder for user presets (created on demand)."""
    import bpy

    try:
        path = bpy.utils.extension_path_user(_base_package(), path="presets", create=True)
    except Exception:
        path = bpy.utils.user_resource("CONFIG", path="swayfield/presets", create=True)
    return Path(path)


def _kind_folder(kind: str) -> str:
    _check_kind(kind)
    return "grass" if kind == "GRASS" else "wind"


def _check_kind(kind: str) -> None:
    if kind not in KINDS:
        raise ValueError(f"Unknown preset kind {kind!r}, use GRASS or WIND")


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def hex_to_linear(value: str) -> tuple[float, float, float, float]:
    """``#RRGGBB`` (sRGB) to a linear RGBA tuple."""
    out = []
    for i in (1, 3, 5):
        c = int(value[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (out[0], out[1], out[2], 1.0)


def linear_to_hex(color) -> str:
    """Linear RGB(A) to ``#RRGGBB`` (sRGB)."""
    parts = []
    for c in tuple(color)[:3]:
        c = min(1.0, max(0.0, float(c)))
        c = c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        parts.append(round(c * 255))
    return "#{:02X}{:02X}{:02X}".format(*parts)


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# Listing and loading
# ---------------------------------------------------------------------------

def _read(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _thumbnail(path: Path) -> str | None:
    for ext in (".png", ".jpg", ".jpeg"):
        thumb = path.with_suffix(ext)
        if thumb.is_file():
            return str(thumb)
    return None


def _list(kind: str) -> list[dict]:
    folder = _kind_folder(kind)
    out: list[dict] = []
    for builtin, root in ((True, builtin_dir()), (False, user_dir())):
        directory = root / folder
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                data = _read(path)
                pid = str(data["id"])
            except (OSError, ValueError, KeyError):
                continue
            out.append({"id": pid, "name": str(data.get("name", pid)),
                        "description": str(data.get("description", "")), "path": str(path),
                        "builtin": builtin, "thumbnail": _thumbnail(path)})
    return out


def list_grass_presets() -> list[dict]:
    """Built-in grass presets first, then user presets."""
    return _list("GRASS")


def list_wind_presets() -> list[dict]:
    """Built-in wind presets first, then user presets."""
    return _list("WIND")


def get_preset(kind: str, preset_id: str) -> dict:
    """Return the preset's parsed JSON (plus ``path`` and ``builtin``). Raises KeyError if missing."""
    _check_kind(kind)
    for entry in _list(kind):
        if entry["id"] == preset_id:
            data = _read(Path(entry["path"]))
            data["path"] = entry["path"]
            data["builtin"] = entry["builtin"]
            return data
    raise KeyError(f"No {kind.lower()} preset called {preset_id!r}")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _check_value(item: spec.Input, value, problems: list[str]) -> None:
    key = item.key
    if item.type == "BOOLEAN":
        if not isinstance(value, bool):
            problems.append(f"{key}: expected true or false")
        return
    if item.type == "INT" and item.items and isinstance(value, str):
        if value not in [it[0] for it in item.items]:
            problems.append(f"{key}: unknown item {value!r}")
        return
    if not _num(value):
        problems.append(f"{key}: expected a number")
        return
    if item.type == "INT" and int(value) != value:
        problems.append(f"{key}: expected a whole number")
    lo, hi = item.min, item.max
    if item.subtype == "ANGLE":
        lo = None if lo is None else math.degrees(lo)
        hi = None if hi is None else math.degrees(hi)
    if lo is not None and value < lo - 1e-6:
        problems.append(f"{key}: {value} is below the minimum {lo:g}")
    if hi is not None and value > hi + 1e-6:
        problems.append(f"{key}: {value} is above the maximum {hi:g}")


def validate_preset(data, kind: str | None = None) -> list[str]:
    """Return a list of problems (empty when the preset is valid)."""
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["preset must be a JSON object"]
    if kind is None:
        kind = "GRASS" if "wind" in data else "WIND"
    for key in data:
        if key not in _TOP_KEYS and key not in ("path", "builtin"):
            problems.append(f"unknown key {key!r}")
    if data.get("schema") != SCHEMA:
        problems.append(f"schema must be {SCHEMA}")
    for key in ("id", "name", "description"):
        if not isinstance(data.get(key), str) or not data.get(key):
            problems.append(f"{key} must be a non-empty string")
    if kind == "WIND":
        if "wind" in data:
            problems.append("wind presets cannot name a wind preset")
        if data.get("effector") not in (None, *EFFECTORS):
            problems.append(f"effector must be null or one of {', '.join(EFFECTORS)}")
    else:
        if data.get("effector") is not None:
            problems.append("grass presets cannot name an effector")
        if data.get("wind") is not None and not isinstance(data.get("wind"), str):
            problems.append("wind must be a preset id or null")
    allowed = WIND_FILE_KEYS if kind == "WIND" else GRASS_KEYS
    inputs = data.get("inputs", {})
    if not isinstance(inputs, dict):
        problems.append("inputs must be an object")
        inputs = {}
    for key, value in inputs.items():
        item = spec.BY_KEY.get(key)
        if item is None:
            problems.append(f"inputs: {key!r} is not a Swayfield input")
        elif key not in allowed:
            problems.append(f"inputs: {key!r} is not allowed in a {kind.lower()} preset")
        else:
            _check_value(item, value, problems)
    material = data.get("material", {})
    if not isinstance(material, dict):
        problems.append("material must be an object")
        material = {}
    for key, value in material.items():
        if key not in MATERIAL_KEYS:
            problems.append(f"material: {key!r} is not a material control")
        elif key in COLOR_KEYS:
            if not isinstance(value, str) or not _HEX.match(value):
                problems.append(f"material: {key} must be a #RRGGBB colour")
        elif not _num(value):
            problems.append(f"material: {key} must be a number")
        else:
            lo, hi = _MATERIAL_RANGES.get(key, (None, None))
            if lo is not None and not lo <= value <= hi:
                problems.append(f"material: {key} must be between {lo:g} and {hi:g}")
    if kind == "WIND" and not str(data.get("id", "")).startswith(USER_PREFIX):
        missing = [k for k in WIND_KEYS if k not in inputs]
        if missing:
            problems.append("wind preset must set every wind input, missing: " + ", ".join(missing))
    return problems


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------

def _to_modifier_value(item: spec.Input, value):
    if item.type == "INT" and item.items and isinstance(value, str):
        return item.item_index(value)
    if item.subtype == "ANGLE":
        return math.radians(value)
    return value


def apply_inputs(mod, inputs: dict) -> None:
    """Write preset ``inputs`` (angles in degrees) to the modifier."""
    for key, value in inputs.items():
        item = spec.BY_KEY.get(key)
        if item is None or not compat.has_input(mod, item.name):
            continue
        compat.set_input(mod, key, _to_modifier_value(item, value))


def _materials():
    from . import materials

    return materials


def apply_material(mat, values: dict) -> None:
    """Apply material control values (colours given as hex). Skipped when ``mat`` is None."""
    if mat is None or not values:
        return
    materials = _materials()
    for key, value in values.items():
        if key in COLOR_KEYS and isinstance(value, str):
            value = hex_to_linear(value)
        materials.set_control(mat, key, value)


def reset_look(mod) -> None:
    """Put every look input back to its spec default."""
    for key in LOOK_KEYS:
        item = spec.BY_KEY[key]
        if compat.has_input(mod, item.name):
            compat.set_input(mod, key, item.default)


def apply_wind_preset(mod, mat, wind_id: str) -> dict:
    """Apply a wind type. Returns the preset data."""
    data = get_preset("WIND", wind_id)
    apply_inputs(mod, data.get("inputs", {}))
    apply_material(mat, data.get("material", {}))
    return data


def apply_grass_preset(mod, mat, preset_id: str) -> dict:
    """Reset the look, apply the preset's wind type, then the preset itself."""
    data = get_preset("GRASS", preset_id)
    reset_look(mod)
    if data.get("wind"):
        apply_wind_preset(mod, mat, data["wind"])
    apply_inputs(mod, data.get("inputs", {}))
    apply_material(mat, data.get("material", {}))
    return data


# ---------------------------------------------------------------------------
# Snapshot, hash and user presets
# ---------------------------------------------------------------------------

def _from_modifier_value(item: spec.Input, value):
    if item.type == "BOOLEAN":
        return bool(value)
    if item.type == "INT":
        return int(value)
    value = float(value)
    if item.subtype == "ANGLE":
        value = math.degrees(value)
    return round(value, 4)


def snapshot(mod, keys: tuple[str, ...] = LOOK_KEYS) -> dict:
    """Current look inputs as JSON-ready values (angles in degrees)."""
    out = {}
    for key in keys:
        item = spec.BY_KEY[key]
        if compat.has_input(mod, item.name):
            out[key] = _from_modifier_value(item, compat.get_input(mod, key))
    return out


def snapshot_hash(mod) -> str:
    """Stable hash of the look inputs, used to detect "Custom"."""
    text = json.dumps(snapshot(mod), sort_keys=True)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _slug(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    return slug or "PRESET"


def _snapshot_material(mat) -> dict:
    if mat is None:
        return {}
    try:
        getter = _materials().get_control
    except (ImportError, AttributeError):
        return {}
    out = {}
    for key in sorted(MATERIAL_KEYS):
        try:
            value = getter(mat, key)
        except Exception:
            continue
        if value is None:
            continue
        if key in COLOR_KEYS:
            value = linear_to_hex(value)
        elif key == "mode":
            value = int(value)
        else:
            value = round(float(value), 5)
        out[key] = value
    return out


def save_user_preset(kind: str, name: str, mod, mat, description: str = "") -> str:
    """Save the modifier's current look as a user preset and return the file path."""
    _check_kind(kind)
    name = name.strip()
    if not name:
        raise ValueError("Enter a name for the preset")
    directory = user_dir() / _kind_folder(kind)
    directory.mkdir(parents=True, exist_ok=True)
    base = USER_PREFIX + _slug(name)
    pid, n = base, 2
    while (directory / f"{pid}.json").exists():
        pid, n = f"{base}_{n}", n + 1
    data: dict = {"schema": SCHEMA, "id": pid, "name": name,
                  "description": description or f"Saved from your scene: {name}."}
    if kind == "GRASS":
        data["wind"] = None
        data["inputs"] = {**snapshot(mod, LOOK_KEYS), **snapshot(mod, EXTRA_PRESET_KEYS)}
        data["material"] = _snapshot_material(mat)
    else:
        data["effector"] = None
        data["inputs"] = snapshot(mod, WIND_KEYS)
        material = _snapshot_material(mat)
        data["material"] = {k: v for k, v in material.items() if k == "wind_brighten"}
    path = directory / f"{pid}.json"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    return str(path)


def delete_user_preset(kind: str, preset_id: str) -> None:
    """Delete a user preset (and its thumbnail). Built-in presets cannot be deleted."""
    if not preset_id.startswith(USER_PREFIX):
        raise ValueError("Built-in presets cannot be deleted")
    data = get_preset(kind, preset_id)
    if data["builtin"]:
        raise ValueError("Built-in presets cannot be deleted")
    path = Path(data["path"])
    thumb = _thumbnail(path)
    os.remove(path)
    if thumb:
        os.remove(thumb)
