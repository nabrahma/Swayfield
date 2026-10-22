# Default textures

CC0 texture sets made by the Swayfield project with `tools/generate_textures.py`
(procedural, fixed seeds, so the output is reproducible).

| File | Size | Use |
| --- | --- | --- |
| `grass_blade_basecolor.png` | 512 x 2048 | Blade colour, root (bottom) to tip (top) |
| `grass_blade_opacity.png` | 512 x 2048 | Tapered blade silhouette |
| `grass_blade_normal.png` | 512 x 2048 | Normal map, OpenGL convention |
| `grass_blade_roughness.png` | 512 x 2048 | Roughness |
| `lawn_tuft_basecolor.png` | 1024 x 1024 | Short lawn tuft card colour |
| `lawn_tuft_opacity.png` | 1024 x 1024 | Tuft silhouette (about 16 blades) |
| `lawn_tuft_normal.png` | 1024 x 1024 | Normal map, OpenGL convention |
| `lawn_tuft_roughness.png` | 1024 x 1024 | Roughness |

Total size is about 4 MB. Regenerate from the repository root:

    blender -b --factory-startup --python tools/generate_textures.py

License: see `LICENSE.txt` (CC0 1.0).
