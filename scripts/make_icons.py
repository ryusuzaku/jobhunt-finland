"""Generate PWA icons for JobHunt (brand gradient + lightning bolt).

Usage:  .venv/Scripts/python scripts/make_icons.py
Output: src/static/icons/icon-192.png, icon-512.png, icon-maskable-512.png
"""

import os

from PIL import Image, ImageDraw

TOP = (69, 73, 232)      # brand-600 #4549e8
BOTTOM = (124, 58, 237)  # violet-600 #7c3aed

# Lightning bolt polygon (fractions of canvas size)
BOLT = [
    (0.56, 0.14), (0.30, 0.55), (0.47, 0.55),
    (0.42, 0.86), (0.70, 0.42), (0.52, 0.42),
]

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "src", "static", "icons")


def gradient(size: int) -> Image.Image:
    """Vertical brand gradient image."""
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(1, size - 1)
        color = tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3))
        draw.line([(0, y), (size, y)], fill=color)
    return img


def bolt_points(size: int, inset: float = 0.0):
    s = size * (1 - 2 * inset)
    ox = size * inset
    oy = size * inset
    return [(ox + fx * s, oy + fy * s) for fx, fy in BOLT]


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def make_icon(size: int, maskable: bool) -> Image.Image:
    img = gradient(size)
    draw = ImageDraw.Draw(img)
    if maskable:
        # Full-bleed background, bolt inside the safe zone (~80%).
        draw.polygon(bolt_points(size, inset=0.16), fill="white")
        return img
    draw.polygon(bolt_points(size, inset=0.10), fill="white")
    mask = rounded_mask(size, radius=int(size * 0.22))
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img.convert("RGBA"), (0, 0), mask)
    return out


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    for size, maskable, name in [
        (192, False, "icon-192.png"),
        (512, False, "icon-512.png"),
        (512, True, "icon-maskable-512.png"),
    ]:
        path = os.path.join(OUT_DIR, name)
        make_icon(size, maskable).save(path)
        print("wrote", path)


if __name__ == "__main__":
    main()
