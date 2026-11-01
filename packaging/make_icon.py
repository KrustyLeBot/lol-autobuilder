"""Génère `packaging/lolbuilds.ico` (hexagone or sur fond nuit, comme le logo de la barre de titre).

Usage : python packaging/make_icon.py   (nécessite Pillow)
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

GOLD = (201, 164, 95, 255)
NIGHT = (10, 13, 19, 255)
SIZE = 512


def hexagon(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    return [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in range(-90, 270, 60)]


def main() -> None:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((16, 16, SIZE - 16, SIZE - 16), radius=96, fill=NIGHT)
    c = SIZE / 2
    draw.polygon(hexagon(c, c, 190), outline=GOLD, width=26)
    draw.polygon(hexagon(c, c, 96), fill=GOLD)
    out = Path(__file__).with_name("lolbuilds.ico")
    img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(out)


if __name__ == "__main__":
    main()
