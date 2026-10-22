# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate docs/reference/settings.md from swayfield/core/spec.py.

Run from the repository root:  python tools/gen_settings_reference.py

spec.py imports only math and dataclasses, so it is loaded straight from its
file path. The swayfield package itself (which needs bpy) is never imported.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "swayfield" / "core" / "spec.py"
OUT_PATH = ROOT / "docs" / "reference" / "settings.md"

HEADER = """\
<!--
  GENERATED FILE. Do not edit by hand.
  Source: swayfield/core/spec.py
  Regenerate with: python tools/gen_settings_reference.py
-->
"""


def load_spec():
    spec = importlib.util.spec_from_file_location("swayfield_spec", SPEC_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["swayfield_spec"] = module  # dataclasses needs this
    spec.loader.exec_module(module)
    return module


def num(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value):,}".replace(",", "")
    return f"{value:.4g}"


UNITS = {
    "DISTANCE": " m",
    "PERCENTAGE": " %",
    "FREQUENCY": " Hz",
    "TIME_ABSOLUTE": " s",
    "ANGLE": "°",
}


def fmt(inp, value) -> str:
    if value is None:
        return "none"
    if inp.type == "BOOLEAN":
        return "on" if value else "off"
    if inp.type == "STRING":
        return f"`{value}`" if value else "empty"
    if inp.type in ("FLOAT", "INT"):
        if inp.items:
            return inp.items[int(value)][1]
        if inp.subtype == "ANGLE":
            return num(round(math.degrees(value), 3)) + "°"
        return num(value) + UNITS.get(inp.subtype, "")
    return str(value)


def type_label(inp) -> str:
    if inp.items:
        return "Choice"
    return {
        "FLOAT": "Float", "INT": "Integer", "BOOLEAN": "Toggle", "STRING": "Text",
        "OBJECT": "Object", "COLLECTION": "Collection", "MATERIAL": "Material",
        "IMAGE": "Image", "VECTOR": "Vector", "COLOR": "Colour",
    }.get(inp.type, inp.type.title())


def range_label(inp) -> str:
    if inp.type not in ("FLOAT", "INT") or inp.items:
        return ""
    if inp.min is None or inp.max is None:
        return ""
    return f"{fmt(inp, inp.min)} to {fmt(inp, inp.max)}"


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def description(inp) -> str:
    text = inp.description.rstrip(".") + "."
    if inp.items:
        parts = []
        for _ident, label, desc in inp.items:
            parts.append(f"**{label}**" + (f" ({desc.rstrip('.')})" if desc else ""))
        text += " Options: " + "; ".join(parts) + "."
    return cell(text)


def table(inputs) -> list[str]:
    lines = [
        "| Setting | Key | Type | Default | Range | Description |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for i in inputs:
        lines.append(
            f"| {cell(i.name)} | `{i.key}` | {type_label(i)} | {cell(fmt(i, i.default))} "
            f"| {range_label(i)} | {description(i)} |"
        )
    return lines


def main() -> int:
    s = load_spec()
    out = [HEADER, "# Settings reference", ""]
    out += [
        "Every Swayfield setting is an input of the layer's Geometry Nodes modifier. "
        "This page lists them all, grouped by panel. **Key** is the name used in "
        "[preset files](../guide/presets.md). Angles are shown in degrees here, and in "
        "preset files too.",
        "",
    ]
    for panel in s.PANELS:
        if panel == "Internal":
            continue
        inputs = [i for i in s.inputs_in_panel(panel) if not i.hidden]
        if not inputs:
            continue
        out += [f"## {panel}", ""] + table(inputs) + [""]
    hidden = [i for i in s.INPUTS if i.hidden]
    out += [
        "## Internal (hidden)",
        "",
        '??? note "Inputs set by operators and drivers"',
        "    You should not need to touch these. Swayfield sets them for you, for example "
        "by copying the active camera's lens.",
        "",
    ]
    out += ["    " + line for line in table(hidden)]
    out.append("")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(out), encoding="utf-8", newline="\n")
    print(f"Wrote {OUT_PATH.relative_to(ROOT)} ({len(s.INPUTS)} inputs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
