# Contributing to Swayfield

Thanks for wanting to help! Swayfield is a Blender add-on for grass with animated wind, and every kind of help is welcome.

## Ways to contribute

- **Bug reports:** open an issue using the bug report form.
- **Presets:** share looks or settings you have made.
- **Docs:** fix typos, improve guides, or add examples.
- **Code:** fix bugs, add features, or improve performance.

Not sure where to start? Ask in [GitHub Discussions](https://github.com/nabrahma/Swayfield/discussions).

## Development setup

1. Clone the repository:
   ```sh
   git clone https://github.com/nabrahma/Swayfield.git
   ```
2. Install Blender 4.2 or newer.
3. Link the `swayfield/` folder into Blender as a local extension. Either:
   - In Blender, go to **Preferences > Get Extensions > Repositories**, add a local repository, and point it at a folder that contains `swayfield/`, or
   - Symlink `swayfield` into that local repository folder.

## Running tests

```sh
blender -b --factory-startup --python-exit-code 1 --python tools/run_tests.py
```

On the first run, pytest is installed into `.blender-deps/`. Blender's own Python is not modified.

To run a single test file, add it after `--`:

```sh
blender -b --factory-startup --python-exit-code 1 --python tools/run_tests.py -- -q tests/test_spec.py
```

## Linting

```sh
ruff check .
```

You can also install the pre-commit hooks so this runs on every commit:

```sh
pre-commit install
```

## Project rules

Please keep these in mind. The [architecture guide](docs/architecture.md) explains the reasons behind them.

- Every setting is declared once, in `swayfield/core/spec.py`.
- Node groups are built from Python in `swayfield/core/nodes/` ("nodes as code"). Never ship node groups as binary `.blend` files.
- A released node group version (for example `SF_Main_v1`) is never changed. Add a `_v2` and an upgrade step instead.
- Read and write modifier inputs only through `swayfield/core/compat.py`.
- No frame-change handlers in the render path.
- UI strings live in `swayfield/ui/strings.py`.
- Every Python file starts with `# SPDX-License-Identifier: GPL-3.0-or-later`.

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(wind): add gust strength control
fix(ui): keep panel open after preset change
docs: explain local repository setup
```

- Allowed types: `feat`, `fix`, `docs`, `test`, `ci`, `build`, `chore`, `refactor`, `perf`.
- Write the subject in the imperative mood and keep it to 72 characters or fewer.
- Explain *why* the change is needed in the body.

## Branches

Use one of these prefixes:

- `feat/<topic>`
- `fix/<topic>`
- `docs/<topic>`

## Pull requests

- Keep one topic per PR.
- Make sure the tests pass.
- Update `CHANGELOG.md` under **Unreleased**.
- Include screenshots or a short clip for visual changes.

The PR template will guide you through the rest.

## Assets

Only contribute textures or presets that you made yourself, and release them as [CC0](https://creativecommons.org/publicdomain/zero/1.0/). Do not submit anything you do not have the rights to share.

## Code of conduct

Please be kind and respectful. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
