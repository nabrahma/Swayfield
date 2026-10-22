# SPDX-License-Identifier: GPL-3.0-or-later
"""Swayfield's Geometry Nodes library, built from Python.

Each stage module defines ``NAME`` (the versioned group name) and
``build(tree)``. ``ensure(stage)`` returns the group, building it on first use.

A released group version is never rebuilt in a user's file, because
rebuilding regenerates socket identifiers and would drop modifier values.
Changing a released group means adding a new version (``SF_Main_v2``) and an
upgrade path in ``core/versioning.py``.
"""

from __future__ import annotations

import importlib

import bpy

from . import builder

#: Pipeline order. ``main`` wires the others together.
STAGES = ("distribute", "masks", "cull", "blade", "effectors", "wind", "store", "main")


def _module(stage: str):
    return importlib.import_module(f".{stage}", __name__)


def group_name(stage: str) -> str:
    return _module(stage).NAME


def ensure(stage: str, *, rebuild: bool = False):
    """Return the node group for ``stage``, building it if it does not exist yet.

    ``rebuild=True`` is for development and tests only.
    """
    mod = _module(stage)
    tree = bpy.data.node_groups.get(mod.NAME)
    if tree is not None and not rebuild:
        return tree
    tree = builder.ensure_group(mod.NAME)
    builder.clear_tree(tree)
    mod.build(tree)
    tree["sf_stage"] = stage
    return tree


def rebuild_all() -> None:
    """Rebuild every group in dependency order (development helper)."""
    for stage in STAGES:
        ensure(stage, rebuild=True)
