# SPDX-License-Identifier: GPL-3.0-or-later
"""Swayfield: one-click animated grass with art-directable wind.

Python handles UI, presets and setup. All per-frame work runs inside
Geometry Nodes, so playback and render farms never depend on Python.
"""

from __future__ import annotations

from . import operators, props, ui

_MODULES = (props, operators, ui)


def register() -> None:
    for module in _MODULES:
        module.register()


def unregister() -> None:
    for module in reversed(_MODULES):
        module.unregister()
