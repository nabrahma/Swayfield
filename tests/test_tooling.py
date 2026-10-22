# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for repo tooling: manifest, pyproject and the render-regression SSIM."""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def _load_toml(path: Path) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def _load_render_regression():
    spec = importlib.util.spec_from_file_location("render_regression", ROOT / "tools" / "render_regression.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_has_required_fields():
    manifest = _load_toml(ROOT / "swayfield" / "blender_manifest.toml")
    for key in ("schema_version", "id", "version", "name", "tagline", "maintainer", "type",
                "blender_version_min", "license"):
        assert key in manifest, key
    assert manifest["id"] == "swayfield"
    assert manifest["type"] == "add-on"


def test_manifest_version_matches_pyproject():
    manifest = _load_toml(ROOT / "swayfield" / "blender_manifest.toml")
    pyproject = _load_toml(ROOT / "pyproject.toml")
    assert manifest["version"] == pyproject["project"]["version"]


def test_ssim_identical_images_is_one():
    rr = _load_render_regression()
    img = np.random.default_rng(0).random((64, 64, 3))
    assert rr.ssim(img, img) == 1.0


def test_ssim_different_images_is_low():
    rr = _load_render_regression()
    rng = np.random.default_rng(1)
    a = rng.random((64, 64, 3))
    b = rng.random((64, 64, 3))
    assert rr.ssim(a, b) < rr.THRESHOLD
    gradient = np.tile(np.linspace(0.0, 1.0, 64), (64, 1))
    assert rr.ssim(gradient, 1.0 - gradient) < rr.THRESHOLD
