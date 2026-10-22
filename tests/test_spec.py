# SPDX-License-Identifier: GPL-3.0-or-later
from swayfield.core import spec


def test_keys_and_names_are_unique():
    assert len({i.key for i in spec.INPUTS}) == len(spec.INPUTS)
    assert len({i.name for i in spec.INPUTS}) == len(spec.INPUTS)


def test_defaults_within_range():
    for item in spec.INPUTS:
        if item.type in {"FLOAT", "INT"}:
            assert item.min <= item.default <= item.max, item.key


def test_enum_inputs_cover_items():
    for item in spec.INPUTS:
        if item.items:
            assert item.type == "INT"
            assert item.max == len(item.items) - 1, item.key


def test_every_input_has_a_tooltip():
    assert all(i.description for i in spec.INPUTS)
