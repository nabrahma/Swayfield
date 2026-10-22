# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the extension zip: ``python tools/build.py [--blender PATH] [--output-dir DIR]``.

Calls ``blender --command extension build`` and prints the path of the produced zip.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def manifest_version() -> str:
    """Return the version declared in the extension manifest."""
    with open(ROOT / "swayfield" / "blender_manifest.toml", "rb") as fh:
        return tomllib.load(fh)["version"]


def build(blender: str, output_dir: Path) -> Path:
    """Run the Blender extension build and return the zip path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        blender, "--command", "extension", "build",
        "--source-dir", str(ROOT / "swayfield"),
        "--output-dir", str(output_dir),
    ]
    subprocess.run(cmd, check=True)
    zip_path = output_dir / f"swayfield-{manifest_version()}.zip"
    if not zip_path.is_file():
        raise FileNotFoundError(f"Blender reported success but {zip_path} does not exist")
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", default=os.environ.get("BLENDER"), help="Blender executable (or $BLENDER)")
    parser.add_argument("--output-dir", default=str(ROOT / "dist"), help="Output directory (default: dist)")
    args = parser.parse_args()
    if not args.blender:
        parser.error("pass --blender or set the BLENDER environment variable")
    try:
        path = build(args.blender, Path(args.output_dir))
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
