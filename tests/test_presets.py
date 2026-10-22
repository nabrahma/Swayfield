# SPDX-License-Identifier: GPL-3.0-or-later
import math
import os
from pathlib import Path

import bpy
import pytest

from swayfield.core import compat, nodes, presets, spec


def _mod(ob):
    mod = ob.modifiers.new("Swayfield", "NODES")
    mod.node_group = nodes.ensure("main")
    return mod


@pytest.fixture(autouse=True)
def user_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(presets, "user_dir", lambda: tmp_path)
    return tmp_path


def _all():
    return [("GRASS", p) for p in presets.list_grass_presets() if p["builtin"]] + \
           [("WIND", p) for p in presets.list_wind_presets() if p["builtin"]]


def test_expected_presets_exist():
    assert [p["id"] for p in presets.list_grass_presets()] == [
        "ROLLING_MEADOW", "LAWN", "WILD_FIELD", "STORMY_STEPPE", "ANIME_FIELD"]
    assert [p["id"] for p in presets.list_wind_presets()] == [
        "ROLLING_MEADOW", "GENTLE_BREEZE", "STORM", "ROLLING_WAVES", "VORTEX", "RADIAL_BLAST",
        "TRAMPLE_PATH", "TOON_BOB"]


def test_every_preset_validates():
    for kind, entry in _all():
        data = presets.get_preset(kind, entry["id"])
        assert presets.validate_preset(data, kind) == [], entry["path"]
    for kind in ("GRASS", "WIND"):
        ids = [p["id"] for p in (presets.list_grass_presets() if kind == "GRASS" else presets.list_wind_presets())]
        assert len(ids) == len(set(ids))


def test_grass_presets_reference_real_winds_and_density_ceiling():
    winds = {p["id"] for p in presets.list_wind_presets()}
    for entry in presets.list_grass_presets():
        data = presets.get_preset("GRASS", entry["id"])
        assert data["wind"] in winds
        inp = data["inputs"]
        assert inp["density_ceiling"] >= inp["density"]


def test_validate_catches_problems():
    data = presets.get_preset("GRASS", "LAWN")
    data["inputs"]["seed"] = 5
    data["inputs"]["density"] = 1e9
    data["inputs"]["bogus"] = 1
    data["material"]["nope"] = 1
    problems = "\n".join(presets.validate_preset(data, "GRASS"))
    for word in ("seed", "density", "bogus", "nope"):
        assert word in problems


def test_rolling_meadow_wind_matches_prd():
    inp = presets.get_preset("WIND", "ROLLING_MEADOW")["inputs"]
    expected = dict(base_lean=0.6, gust_strength=0.4, gust_scale=0.2, gust_stretch=3.3, gust_speed=4,
                    max_bend=80, stiffness=1.6, flutter_strength=0.08, flutter_frequency=3, wisp_flutter=2,
                    tip_lag=0.15)
    for key, value in expected.items():
        assert inp[key] == pytest.approx(value)
    assert presets.get_preset("WIND", "ROLLING_MEADOW")["material"]["wind_brighten"] == 0.6


def test_effectors_declared():
    assert presets.get_preset("WIND", "VORTEX")["effector"] == "VORTEX"
    assert presets.get_preset("WIND", "RADIAL_BLAST")["effector"] == "RADIAL_BLAST"
    assert presets.get_preset("WIND", "TRAMPLE_PATH")["effector"] == "TRAMPLE"
    assert presets.get_preset("WIND", "TOON_BOB")["inputs"]["sway_mode"] == 1


def test_apply_grass_preset_sets_inputs(plane):
    mod = _mod(plane)
    compat.set_input(mod, "clump_pull", 0.9)  # must be reset by the preset
    presets.apply_grass_preset(mod, None, "ROLLING_MEADOW")
    assert compat.get_input(mod, "density") == pytest.approx(1500)
    assert compat.get_input(mod, "max_bend") == pytest.approx(math.radians(80))
    assert compat.get_input(mod, "length_max") == pytest.approx(0.9)
    assert compat.get_input(mod, "gust_speed") == pytest.approx(4)
    presets.apply_grass_preset(mod, None, "STORMY_STEPPE")
    assert compat.get_input(mod, "direction_variation") == pytest.approx(math.radians(30))
    presets.apply_grass_preset(mod, None, "LAWN")
    assert compat.get_input(mod, "optimised") is True
    assert compat.get_input(mod, "viewport_density") == pytest.approx(15)
    assert compat.get_input(mod, "direction_variation") == pytest.approx(0)


def test_wind_preset_keeps_shot_settings(plane):
    mod = _mod(plane)
    compat.set_input(mod, "direction", 1.0)
    compat.set_input(mod, "loop_enable", True)
    presets.apply_wind_preset(mod, None, "TOON_BOB")
    assert compat.get_input(mod, "sway_mode") == 1
    assert compat.get_input(mod, "direction") == pytest.approx(1.0)
    assert compat.get_input(mod, "loop_enable") is True
    presets.apply_wind_preset(mod, None, "ROLLING_MEADOW")
    assert compat.get_input(mod, "sway_mode") == 0


def test_snapshot_hash_changes(plane):
    mod = _mod(plane)
    presets.apply_grass_preset(mod, None, "ROLLING_MEADOW")
    before = presets.snapshot_hash(mod)
    assert before == presets.snapshot_hash(mod)
    compat.set_input(mod, "curl", math.radians(33))
    assert presets.snapshot_hash(mod) != before
    snap = presets.snapshot(mod)
    assert snap["curl"] == pytest.approx(33)
    assert "seed" not in snap and "material" not in snap


def test_user_preset_round_trip(plane, user_folder):
    mod = _mod(plane)
    presets.apply_grass_preset(mod, None, "WILD_FIELD")
    compat.set_input(mod, "rest_lean", math.radians(21))
    path = presets.save_user_preset("GRASS", "My Field!", mod, None)
    assert Path(path).is_file() and Path(path).parent.parent == user_folder
    entries = presets.list_grass_presets()
    assert entries[-1]["id"] == "USER_MY_FIELD" and not entries[-1]["builtin"]
    assert entries[0]["builtin"]
    data = presets.get_preset("GRASS", "USER_MY_FIELD")
    assert presets.validate_preset(data, "GRASS") == []
    assert data["inputs"]["rest_lean"] == pytest.approx(21)
    compat.set_input(mod, "rest_lean", 0.0)
    presets.apply_grass_preset(mod, None, "USER_MY_FIELD")
    assert compat.get_input(mod, "rest_lean") == pytest.approx(math.radians(21))
    wpath = presets.save_user_preset("WIND", "Soft", mod, None)
    assert presets.get_preset("WIND", "USER_SOFT")["path"] == wpath
    presets.delete_user_preset("GRASS", "USER_MY_FIELD")
    presets.delete_user_preset("WIND", "USER_SOFT")
    assert not os.path.exists(path) and not os.path.exists(wpath)
    with pytest.raises(KeyError):
        presets.get_preset("GRASS", "USER_MY_FIELD")
    with pytest.raises(ValueError):
        presets.delete_user_preset("GRASS", "LAWN")


def test_material_controls_applied(plane):
    try:
        from swayfield.core import materials
    except ImportError:
        pytest.skip("materials module not available yet")
    if not hasattr(materials, "set_control") or not hasattr(materials, "get_control"):
        pytest.skip("materials.set_control not available yet")
    mat = materials.create_layer_material("m")
    presets.apply_material(mat, {"wind_brighten": 0.25, "color_tip": "#808080"})
    assert materials.get_control(mat, "wind_brighten") == pytest.approx(0.25)
    assert materials.get_control(mat, "color_tip")[0] == pytest.approx(0.2159, abs=1e-3)


def test_hex_round_trip():
    assert presets.linear_to_hex(presets.hex_to_linear("#4FD02A")) == "#4FD02A"


def test_texture_files():
    root = presets.builtin_dir().parent / "textures"
    sizes = {"grass_blade": (512, 2048), "lawn_tuft": (1024, 1024)}
    total = 0
    for prefix, (w, h) in sizes.items():
        for suffix in ("basecolor", "opacity", "normal", "roughness"):
            path = root / f"{prefix}_{suffix}.png"
            assert path.is_file(), path
            total += path.stat().st_size
            img = bpy.data.images.load(str(path))
            try:
                assert tuple(img.size) == (w, h)
            finally:
                bpy.data.images.remove(img)
    assert total < 8 * 1024 * 1024
    assert (root / "LICENSE.txt").is_file() and (root / "README.md").is_file()


def test_look_keys_are_spec_keys():
    assert all(k in spec.BY_KEY for k in presets.LOOK_KEYS)
    assert "seed" not in presets.LOOK_KEYS
