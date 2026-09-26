#!/usr/bin/env python3
"""Render Manager sprite sheets from the approved firmware 0.2.14 logo pose.

Pillow is a build dependency only. The packaged Tk application reads the PNG
sheet directly, so animation does not add a runtime dependency or frame I/O.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "firmware" / "tools"))
import build_unified_logo_assets as firmware_logo  # noqa: E402

FRAMES = 256
COLUMNS = 16
TILE = 240
VIEW = (10, 7, 230, 227)
OUTPUT = ROOT / "manager" / "assets"
VARIANTS = (("overview", 96, "#0F1113"),)


def motion(phase: int) -> tuple[int, int]:
    wave = firmware_logo.preview.saver.WAVE[((phase >> 1) + 11) & 63]
    drift = firmware_logo.preview.saver.WAVE[((phase >> 2) + 23) & 63]
    return wave * 28 // 255 - 14, drift * 20 // 255 - 10


def frame(phase: int, mint, sprites) -> Image.Image:
    mint_layer, crystal_layer = firmware_logo.rgba_layers(phase, mint, sprites)
    dx, dy = motion(phase)
    canvas = Image.new("RGBA", (TILE, TILE))
    for layer, bounds in ((mint_layer, firmware_logo.MINT_BOUNDS),
                          (crystal_layer, firmware_logo.CRYSTAL_BOUNDS)):
        canvas.alpha_composite(layer, (bounds[0] + dx, bounds[1] + dy))
    return canvas


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    mint = firmware_logo.preview.saver.logo_masks()[0]
    sprites = [firmware_logo.preview.crystal_preview.sprite(i) for i in range(72)]
    sheets = []
    for name, size, background in VARIANTS:
        sheet = Image.new("RGB", (COLUMNS * size, (FRAMES // COLUMNS) * size), background)
        sheets.append((name, size, background, sheet))
    for phase in range(FRAMES):
        logo = frame(phase, mint, sprites).crop(VIEW)
        for _name, size, color, sheet in sheets:
            small = logo.resize((size, size), Image.Resampling.LANCZOS)
            background = Image.new("RGBA", (size, size), color)
            background.alpha_composite(small)
            sheet.paste(background.convert("RGB"), ((phase % COLUMNS) * size,
                                                    (phase // COLUMNS) * size))
    for name, _size, _color, sheet in sheets:
        path = OUTPUT / f"evilkey_logo_{name}_animated.png"
        sheet.save(path, optimize=True)
        print(f"{path}: {sheet.width}x{sheet.height}")
        if name == "overview":
            frames = [sheet.crop(((phase % COLUMNS) * size,
                                  (phase // COLUMNS) * size,
                                  (phase % COLUMNS + 1) * size,
                                  (phase // COLUMNS + 1) * size))
                      for phase in range(FRAMES)]
            frames[0].save(OUTPUT / "evilkey_logo_overview.png")
            preview_path = ROOT / "docs" / "gui" / "EVILKEY_MANAGER_LOGO_0.2.14.webp"
            frames[0].save(preview_path, save_all=True, append_images=frames[1:],
                           duration=24, loop=0, quality=95, method=5)
            print(f"{preview_path}: {len(frames)} frames at 24 ms")


if __name__ == "__main__":
    main()
