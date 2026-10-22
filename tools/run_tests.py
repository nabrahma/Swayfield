# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the Swayfield test suite inside Blender.

Usage::

    blender -b --factory-startup --python-exit-code 1 --python tools/run_tests.py -- [pytest args]

pytest is installed on first run into ``.blender-deps/`` next to the repo, so
Blender's own Python installation is never modified.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPS = os.path.join(ROOT, ".blender-deps")


def ensure_pytest() -> None:
    try:
        import pytest  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "ensurepip", "--upgrade"],
                              stdout=subprocess.DEVNULL)
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                               "--target", DEPS, "pytest>=8"])
        import importlib

        importlib.invalidate_caches()


def main() -> int:
    sys.path.insert(0, DEPS)
    sys.path.insert(0, ROOT)
    ensure_pytest()
    import pytest

    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not any(not a.startswith("-") for a in argv):
        argv.append(os.path.join(ROOT, "tests"))
    return pytest.main(["--rootdir", ROOT, "-p", "no:cacheprovider", *argv])


if __name__ == "__main__":
    sys.exit(main())
