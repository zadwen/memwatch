"""
icon.py
Generates the zadwen-style monogram icon programmatically (no external
image files needed). Produces a gradient circle with a "M" mark, saved
as both .ico (for Windows taskbar/tray) and .png (for the tray lib).
"""

import os
from PIL import Image, ImageDraw, ImageFont

from core import branding


def _gradient_circle(size=256):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    top = tuple(int(branding.COLOR_ACCENT_1[i:i + 2], 16) for i in (1, 3, 5))
    bottom = tuple(int(branding.COLOR_ACCENT_2[i:i + 2], 16) for i in (1, 3, 5))

    grad = Image.new("RGBA", (1, size), (0, 0, 0, 0))
    for y in range(size):
        t = y / (size - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        grad.putpixel((0, y), (r, g, b, 255))
    grad = grad.resize((size, size))

    mask = Image.new("L", (size, size), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.ellipse((4, 4, size - 4, size - 4), fill=255)

    img = Image.composite(grad, img, mask)
    return img


def _draw_mark(img):
    size = img.size[0]
    draw = ImageDraw.Draw(img)
    letter = "M"
    font = None
    for candidate in ("arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
        try:
            font = ImageFont.truetype(candidate, int(size * 0.52))
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), letter, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pos = ((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1])
    draw.text(pos, letter, font=font, fill=(255, 255, 255, 235))
    return img


def generate(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    base = _gradient_circle(256)
    base = _draw_mark(base)

    png_path = os.path.join(output_dir, "icon.png")
    ico_path = os.path.join(output_dir, "icon.ico")

    base.save(png_path)
    base.save(ico_path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return png_path, ico_path


if __name__ == "__main__":
    p1, p2 = generate(os.path.join(os.path.dirname(__file__), "..", "assets"))
    print("Generated:", p1, p2)
