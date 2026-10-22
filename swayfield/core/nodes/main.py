# SPDX-License-Identifier: GPL-3.0-or-later
"""SF_Main: the modifier group. Exposes every spec input and wires the stages."""

from __future__ import annotations

from . import builder

NAME = "SF_Main_v1"


def build(tree) -> None:
    builder.add_socket(tree, "Geometry", "GEOMETRY", "INPUT")
    builder.add_spec_inputs(tree)
    builder.add_socket(tree, "Geometry", "GEOMETRY", "OUTPUT")

    b = builder.NodeBuilder(tree)
    # Stub: passes the surface through until the stages are wired in.
    b.output("Geometry", b.inp("Geometry"))
    b.arrange()
