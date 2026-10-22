# Contributing

Bug reports, test scenes, docs fixes and pull requests are welcome.

The full guide is in [CONTRIBUTING.md on GitHub](https://github.com/nabrahma/Swayfield/blob/main/CONTRIBUTING.md). Read it before opening a pull request.

## Quick pointers

- Every setting is declared once in `swayfield/core/spec.py`. The settings reference is generated from it. After you change it, run `python tools/gen_settings_reference.py`.
- Run the tests with `blender -b --factory-startup --python-exit-code 1 --python tools/run_tests.py`.
- Read the [architecture](architecture.md) before changing node groups or operators.
- New behaviour comes with a test.

Each page in these docs has an edit button that opens the file on GitHub.
