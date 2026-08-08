#!/usr/bin/env python3
"""Generate this satellite's brand assets: the mark, and the full favicon set.

    python scripts/make_brand_assets.py

Why a generator and not a checked-in binary a designer made once: the mark has
to exist at eight sizes from 16px to 1024px, and the honest way to get a 16px
icon that still reads is to DRAW it at 16px, not to downsample a 512px one.
Thin sketchy strokes disappear under LANCZOS. So stroke weight and jitter are
both functions of the output size, and the small sizes deliberately render a
simplified mark.

THE MARK
--------
Two overlapping hand-drawn wireframe shapes — a square and a circle. That is
the Excalidraw motif reduced to the least it can be and still be recognisable:
it says "diagram" at 512px and it still says *something* at 16px, which a
faithful little pencil or a three-shape flowchart does not.

The "hand-drawn" quality is the same trick roughjs uses and Excalidraw is built
on: draw each edge twice, with the endpoints nudged and the midpoint bowed, so
no two strokes agree exactly. The jitter is seeded, so this script is
deterministic — re-running it produces byte-identical files, which matters
because these are committed and a noisy regenerate would churn the repo.

Palette is Excalidraw's own, with violet leading to match PRIMARY_COLOR in
lib/constants.py.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    print("Pillow is required: pip install Pillow", file=sys.stderr)
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

VIOLET = (103, 65, 217, 255)   # #6741d9 — PRIMARY_COLOR
ORANGE = (240, 140, 0, 255)    # #f08c00 — Excalidraw accent
SEED = 20260808


def _stroke(draw, pts, color, width):
    """Draw a polyline as a stamped brush: segments plus a dot at every vertex.

    Pillow's own `joint="curve"` fringes badly at the widths this mark needs —
    it leaves a comb of spikes along every curve. Stamping a filled circle at
    each vertex gives real round caps and joins, and costs nothing at these
    sizes.
    """
    r = width / 2
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        draw.line([(x0, y0), (x1, y1)], fill=color, width=width)
    for (x, y) in pts:
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)


def _bowed(p0, p1, rng, jitter, steps):
    """A quadratic through p0..p1 whose ends and midpoint are nudged.

    The bow is what reads as hand-drawn; endpoint jitter alone just looks like
    a sloppy polygon. Kept SMALL and tied to stroke width — the first version
    of this used a length-proportional wobble and the result looked shredded
    rather than sketched.
    """
    (x0, y0), (x1, y1) = p0, p1
    length = math.hypot(x1 - x0, y1 - y0) or 1.0
    px, py = -(y1 - y0) / length, (x1 - x0) / length

    ax, ay = x0 + rng.uniform(-jitter, jitter), y0 + rng.uniform(-jitter, jitter)
    bx, by = x1 + rng.uniform(-jitter, jitter), y1 + rng.uniform(-jitter, jitter)
    bow = rng.uniform(-jitter, jitter) * 1.4
    cx, cy = (ax + bx) / 2 + px * bow, (ay + by) / 2 + py * bow

    out = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        out.append((u * u * ax + 2 * u * t * cx + t * t * bx,
                    u * u * ay + 2 * u * t * cy + t * t * by))
    return out


def _sketch_path(draw, corners, color, width, rng, passes, closed=True):
    """Trace a closed path once per pass, as one continuous bowed polyline."""
    seq = list(corners) + ([corners[0]] if closed else [])
    for _ in range(passes):
        pts = []
        for a, b in zip(seq, seq[1:]):
            seg = math.hypot(b[0] - a[0], b[1] - a[1])
            # Jitter is capped by SEGMENT LENGTH, not just stroke width. A
            # circle is 48 short segments, and a width-proportional jitter on
            # each of them accumulates into a lumpy contour rather than a
            # drawn one — the rectangle's four long edges want the full
            # amount, the circle's many short ones want almost none.
            jitter = min(width * 0.28, seg * 0.09)
            pts.extend(_bowed(a, b, rng, jitter, max(4, int(seg / 8))))
        _stroke(draw, pts, color, width)


def _sketch_rect(draw, box, color, width, rng, passes=2):
    x0, y0, x1, y1 = box
    _sketch_path(draw, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                 color, width, rng, passes)


def _sketch_circle(draw, box, color, width, rng, passes=2):
    """A circle as a 48-gon — enough segments that it reads round, not faceted.

    The first version used 12 and the mark looked like a stop sign.
    """
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    n = 48
    pts = [(cx + rx * math.cos(2 * math.pi * i / n),
            cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]
    _sketch_path(draw, pts, color, width, rng, passes)


def render_mark(size: int) -> Image.Image:
    """The mark at one specific size. Small sizes get a bolder, calmer draw.

    Below ~48px a two-pass sketch turns to mush and the shapes stop being
    separable, so the small variants use one pass and a heavier stroke. This is
    the whole reason the generator draws per-size instead of downsampling.
    """
    small = size <= 48
    scale = 4 if small else 2          # supersample, then LANCZOS down
    S = size * scale
    rng = random.Random(SEED)

    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    width = max(1, round(S * (0.105 if small else 0.062)))
    passes = 1 if small else 2

    # Square upper-left, circle lower-right, overlapping about a third.
    # Small sizes trade breathing room for legibility: a 16px favicon sits in
    # a browser tab next to text, so filling the box matters more than margin.
    pad = S * (0.05 if small else 0.10)
    side = S * (0.56 if small else 0.52)
    _sketch_rect(draw, (pad, pad, pad + side, pad + side), VIOLET, width, rng, passes)
    _sketch_circle(
        draw,
        (S - pad - side, S - pad - side, S - pad, S - pad),
        ORANGE, width, rng, passes,
    )

    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "favicon").mkdir(exist_ok=True)
    written = []

    # Header logo + social-card artwork.
    for name, size in [("excalidraw-mark.png", 512), ("excalidraw-mark-144.png", 144)]:
        p = ASSETS / name
        render_mark(size).save(p)
        written.append(p)

    favicons = {
        "favicon-16x16.png": 16,
        "favicon-32x32.png": 32,
        "favicon-96x96.png": 96,
        "apple-touch-icon.png": 180,
        "android-chrome-192x192.png": 192,
        "android-chrome-512x512.png": 512,
    }
    for name, size in favicons.items():
        p = ASSETS / "favicon" / name
        img = render_mark(size)
        if name.startswith("apple-touch"):
            # iOS composites onto black otherwise; Apple ignores transparency.
            flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
            flat.alpha_composite(img)
            img = flat
        img.save(p)
        written.append(p)

    # Multi-resolution .ico — browsers pick the size they want from inside it.
    ico = ASSETS / "favicon.ico"
    render_mark(256).save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)])
    written.append(ico)
    ico2 = ASSETS / "favicon" / "favicon.ico"
    render_mark(256).save(ico2, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)])
    written.append(ico2)

    for p in written:
        print(f"  {p.relative_to(ROOT)}  {p.stat().st_size:,} bytes")
    print(f"\n{len(written)} files written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
