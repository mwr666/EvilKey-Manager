#!/usr/bin/env python3
"""Render EvilKey desktop assets from the approved two-tone logo source."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "firmware" / "assets" / "evilkey_mark_source.png"
ASSETS = ROOT / "manager" / "assets"


def render(source: Image.Image, size: int) -> Image.Image:
    box = source.getchannel("A").getbbox()
    if box is None:
        raise ValueError("EvilKey logo source is transparent")
    mark = source.crop(box)
    scale = min(size / mark.width, size / mark.height)
    dimensions = (max(1, round(mark.width * scale)), max(1, round(mark.height * scale)))
    mark = mark.resize(dimensions, Image.Resampling.LANCZOS)
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    image.alpha_composite(mark, ((size - dimensions[0]) // 2, (size - dimensions[1]) // 2))
    return image


def main() -> None:
    source = Image.open(SOURCE).convert("RGBA")
    ASSETS.mkdir(parents=True, exist_ok=True)
    for name, size in (("evilkey_logo_header.png", 62),
                       ("evilkey_logo_hero.png", 184),
                       ("evilkey_logo_small.png", 48),
                       ("evilkey_icon.png", 512)):
        render(source, size).save(ASSETS / name)
    render(source, 256).save(ASSETS / "evilkey.ico", format="ICO",
                             sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                    (64, 64), (128, 128), (256, 256)])
    print(f"Wrote EvilKey PNG and ICO assets to {ASSETS}")


if __name__ == "__main__":
    main()
