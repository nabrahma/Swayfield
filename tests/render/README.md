# Render regression

Each grass preset (`ROLLING_MEADOW`, `LAWN`, `WILD_FIELD`, `STORMY_STEPPE`, `ANIME_FIELD`) is rendered at
256 x 256 on frames 1 and 24 in a fixed scene (10 m ground plane, fixed camera and sun) and compared with
`tests/render/reference/<PRESET>_f<frame>.png` by grayscale SSIM (11 x 11 Gaussian window, sigma 1.5).
A score below 0.98 fails.

```
blender -b --factory-startup --python-exit-code 1 --python tools/render_regression.py -- [--update] [--engine auto|eevee|cycles]
```

- Renders and `*_diff.png` images (difference x4) go to `tests/output/` (gitignored).
- `--update` rewrites the references. Review the new images before committing them.
- `--engine auto` uses EEVEE when a GPU context is available and falls back to Cycles (CPU, 16 samples).
  References are engine specific: regenerate and compare with the same engine. CI (no GPU) uses Cycles.
- The workflow `render-regression.yml` is manual (`workflow_dispatch`) and uploads `tests/output/` as an artifact.
- SSIM lives in `tools/render_regression.py` (`ssim`) and is unit tested in `tests/test_tooling.py`.
