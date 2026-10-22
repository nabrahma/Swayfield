# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate the CC0 default texture sets shipped in swayfield/textures.

Usage::

    blender -b --factory-startup --python tools/generate_textures.py

Writes a 512 x 2048 grass blade set and a 1024 x 1024 lawn tuft set (base colour,
opacity, normal in OpenGL convention, roughness). Deterministic: fixed seeds.
"""

import os
import sys

import bpy
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "swayfield", "textures")


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def blur(a, n=1):
    for _ in range(n):
        p = np.pad(a, 1, mode="edge")
        a = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] + 4 * p[1:-1, 1:-1]) / 8.0
    return a


def value_noise(rng, h, w, cells):
    """Smooth tileless value noise in 0..1 with roughly ``cells`` cells across the width."""
    ch, cw = max(2, int(cells * h / w) + 2), cells + 2
    grid = rng.random((ch, cw))
    ys = np.linspace(0, ch - 2, h)[:, None]
    xs = np.linspace(0, cw - 2, w)[None, :]
    y0, x0 = ys.astype(int), xs.astype(int)
    fy, fx = smoothstep(0, 1, ys - y0), smoothstep(0, 1, xs - x0)
    top = grid[y0, x0] * (1 - fx) + grid[y0, x0 + 1] * fx
    bot = grid[y0 + 1, x0] * (1 - fx) + grid[y0 + 1, x0 + 1] * fx
    return top * (1 - fy) + bot * fy


def normal_from_height(height, strength):
    """Tangent-space normal map (OpenGL, +Y up) from a height field with row 0 at the bottom."""
    gy, gx = np.gradient(height)
    n = np.dstack([-gx * strength, -gy * strength, np.ones_like(height)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5


def save(name, rgb, alpha, srgb):
    """Write an image. ``rgb`` is (h, w, 3) float, row 0 is the bottom row (as in Blender)."""
    h, w = rgb.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    rgba = np.dstack([np.clip(rgb, 0, 1), np.ones((h, w)) if alpha is None else alpha]).astype(np.float32)
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = os.path.join(OUT, name + ".png")
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def gray(a):
    return np.dstack([a, a, a])


def green_ramp(t, rng_field):
    """Root-dark to tip-light green. ``t`` 0 at the root, 1 at the tip."""
    root, mid, tip = (np.array(c) for c in ((0.10, 0.22, 0.04), (0.22, 0.42, 0.07), (0.42, 0.62, 0.14)))
    t = t[..., None]
    low = root + (mid - root) * smoothstep(0, 0.5, t)
    col = low + (tip - mid) * smoothstep(0.5, 1.0, t)
    return col * (0.92 + 0.16 * rng_field[..., None])


def blade_set():
    h, w = 2048, 512
    rng = np.random.default_rng(1234)
    v = (np.arange(h) + 0.5)[:, None] / h
    u = (np.arange(w) + 0.5)[None, :] / w
    x = (u - 0.5) * 2.0  # -1..1 across the card
    half = 0.97 * np.clip(1 - v ** 1.8, 0, 1) ** 0.55 * (0.35 + 0.65 * smoothstep(0, 0.08, v))
    d = (np.abs(x) - half) * (w / 2)  # signed distance in pixels
    alpha = np.clip(0.5 - d, 0, 1)
    rel = np.abs(x) / np.maximum(half, 1e-3)  # 0 midrib, 1 edge
    noise = value_noise(rng, h, w, 24)
    fine = rng.random((h, w))
    veins = 0.5 + 0.5 * np.cos(rel * np.pi * 9)
    rib = np.exp(-(np.abs(x) * w / 6.0) ** 2)
    height = -0.35 * rel * half + 0.012 * veins * half - 0.02 * rib
    color = green_ramp(v + 0.0 * u, noise)
    color *= 1.0 - 0.10 * veins[..., None] * 0.5
    color += rib[..., None] * np.array([0.10, 0.12, 0.04]) * 0.8
    color += (blur(fine, 1)[..., None] - 0.5) * 0.02
    rough = np.round(0.55 + 0.1 * noise - 0.1 * rib, 2)
    normal = normal_from_height(blur(height * 40.0, 1), 14.0)
    save("grass_blade_basecolor", color, None, True)
    save("grass_blade_opacity", gray(alpha), None, False)
    save("grass_blade_normal", normal, None, False)
    save("grass_blade_roughness", gray(rough), None, False)


def tuft_set():
    n = 1024
    rng = np.random.default_rng(4321)
    cover = np.zeros((n, n))
    tpar = np.zeros((n, n))
    shade = np.zeros((n, n))
    side = np.zeros((n, n))
    count = 16
    yy, xx = np.mgrid[0:n, 0:n]
    for i in range(count):
        angle = np.radians(-38 + 76 * (i + rng.uniform(-0.3, 0.3)) / (count - 1))
        length = rng.uniform(0.55, 0.95) * n
        bend = rng.uniform(-0.25, 0.25) * length * np.sign(angle if angle else 1)
        rootx = n * (0.5 + rng.uniform(-0.05, 0.05))
        base_w = rng.uniform(15, 24)
        tone = rng.uniform(0.85, 1.15)
        for t in np.linspace(0, 1, 500):
            px = rootx + np.sin(angle) * length * t + bend * t * t
            py = 4 + np.cos(angle) * length * t
            r = base_w * 0.5 * (1 - t) ** 0.7 + 0.3
            x0, x1 = int(max(px - r - 2, 0)), int(min(px + r + 3, n))
            y0, y1 = int(max(py - r - 2, 0)), int(min(py + r + 3, n))
            if x1 <= x0 or y1 <= y0:
                continue
            dx = xx[y0:y1, x0:x1] - px
            dy = yy[y0:y1, x0:x1] - py
            cov = np.clip(r + 0.5 - np.hypot(dx, dy), 0, 1)
            upd = cov >= cover[y0:y1, x0:x1] - 1e-6
            upd &= cov > 0.02
            sl = (slice(y0, y1), slice(x0, x1))
            cover[sl] = np.where(upd, np.maximum(cov, cover[sl]), cover[sl])
            tpar[sl] = np.where(upd, t, tpar[sl])
            shade[sl] = np.where(upd, tone, shade[sl])
            side[sl] = np.where(upd, np.clip(dx / (r + 1e-3), -1, 1), side[sl])
    noise = value_noise(rng, n, n, 32)
    fine = rng.random((n, n))
    color = green_ramp(tpar * 0.9, noise) * np.where(cover > 0, shade, 1.0)[..., None]
    color += (blur(fine, 1)[..., None] - 0.5) * 0.02
    height = blur(cover * 1.0, 2) * 6.0 - 0.6 * np.abs(side) * cover
    normal = normal_from_height(blur(height, 1), 0.6)
    rough = np.round(0.5 + 0.1 * noise, 2)
    save("lawn_tuft_basecolor", color, None, True)
    save("lawn_tuft_opacity", gray(cover), None, False)
    save("lawn_tuft_normal", normal, None, False)
    save("lawn_tuft_roughness", gray(rough), None, False)


def main():
    os.makedirs(OUT, exist_ok=True)
    blade_set()
    tuft_set()
    total = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT) if f.endswith(".png"))
    print(f"Wrote textures to {OUT} ({total / 1e6:.2f} MB)")


if __name__ == "__main__":
    sys.exit(main())
