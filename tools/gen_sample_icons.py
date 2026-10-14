#!/usr/bin/env python3
"""
gen_sample_icons.py - Genera un joc d'icones de mostra (blanc sobre transparent)
a Assets/icons/. Son senzilles pero funcionals: serveixen per provar el circuit
complet (PNG -> .bin -> SD -> boto) i com a plantilla per substituir-les.

Us:
    python3 tools/gen_sample_icons.py
    python3 tools/png2bin.py
"""

import os

from PIL import Image, ImageDraw

SIZE = 256
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "Assets", "icons")
W = (255, 255, 255, 255)


def canvas():
    im = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def save(im, name):
    os.makedirs(OUT, exist_ok=True)
    im.save(os.path.join(OUT, name + ".png"))


def speaker(d, waves):
    d.polygon([(56, 96), (104, 96), (156, 48), (156, 208), (104, 160), (56, 160)], fill=W)
    for i in range(waves):
        r = 46 + i * 34
        d.arc([156 - r // 2, 128 - r, 156 + r * 3 // 2, 128 + r], -55, 55, fill=W, width=16)


def tri(d, x0, x1, y0, y1):
    d.polygon([(x0, y0), (x1, (y0 + y1) // 2), (x0, y1)], fill=W)


def main():
    os.makedirs(OUT, exist_ok=True)

    im, d = canvas(); tri(d, 88, 200, 56, 200); save(im, "play")
    im, d = canvas(); d.rectangle([80, 56, 116, 200], fill=W); tri(d, 140, 236, 56, 200); save(im, "prev")
    im, d = canvas(); tri(d, 20, 116, 56, 200); d.rectangle([140, 56, 176, 200], fill=W); save(im, "next")
    im, d = canvas(); d.rectangle([84, 60, 116, 196], fill=W); d.rectangle([140, 60, 172, 196], fill=W); save(im, "pause")
    im, d = canvas(); speaker(d, 1); d.line([200, 96, 240, 160], fill=W, width=18); d.line([240, 96, 200, 160], fill=W, width=18); save(im, "vol_down")
    im, d = canvas(); speaker(d, 3); save(im, "vol_up")
    im, d = canvas(); speaker(d, 0); d.line([186, 88, 238, 168], fill=W, width=20); d.line([238, 88, 186, 168], fill=W, width=20); save(im, "mute")

    im, d = canvas(); d.rounded_rectangle([64, 116, 192, 216], 20, fill=W); d.arc([92, 48, 164, 150], 180, 360, fill=W, width=20); save(im, "lock")
    im, d = canvas(); d.ellipse([48, 48, 208, 208], fill=W); d.ellipse([96, 24, 256, 184], fill=(0, 0, 0, 0)); save(im, "sleep")
    im, d = canvas(); d.rounded_rectangle([40, 84, 216, 200], 22, fill=W); d.rounded_rectangle([92, 60, 164, 96], 10, fill=W); d.ellipse([104, 116, 152, 164], fill=(0, 0, 0, 0)); save(im, "shot")
    im, d = canvas(); d.ellipse([48, 48, 208, 208], fill=W); d.pieslice([48, 48, 208, 208], 90, 270, fill=(0, 0, 0, 0)); save(im, "dark")
    im, d = canvas(); tri(d, 96, 208, 56, 200); d.rectangle([56, 56, 84, 200], fill=W); save(im, "home")

    im, d = canvas(); d.rounded_rectangle([36, 56, 220, 200], 18, fill=W); d.line([80, 100, 120, 128], fill=(0, 0, 0, 0), width=16); d.line([120, 128, 80, 156], fill=(0, 0, 0, 0), width=16); d.line([150, 164, 200, 164], fill=(0, 0, 0, 0), width=14); save(im, "term")
    im, d = canvas(); d.rounded_rectangle([72, 40, 184, 152], 16, outline=W, width=18); d.rounded_rectangle([104, 104, 216, 216], 16, fill=W); save(im, "copy")
    im, d = canvas(); d.rounded_rectangle([72, 72, 184, 216], 16, fill=W); d.rounded_rectangle([104, 40, 152, 72], 10, fill=W); save(im, "paste")
    im, d = canvas(); d.line([96, 60, 176, 196], fill=W, width=18); d.line([176, 60, 96, 196], fill=W, width=18); d.ellipse([56, 168, 112, 224], outline=W, width=18); d.ellipse([160, 168, 216, 224], outline=W, width=18); save(im, "cut")
    im, d = canvas(); d.arc([48, 80, 208, 240], 180, 360, fill=W, width=22); tri(d, 96, 176, 40, 104); save(im, "undo")
    im, d = canvas(); d.arc([48, 80, 208, 240], 180, 360, fill=W, width=22); d.polygon([(160, 40), (240, 72), (160, 104)], fill=W); save(im, "redo")

    im, d = canvas(); d.rounded_rectangle([48, 48, 208, 208], 20, fill=W); d.rectangle([92, 128, 164, 208], fill=(0, 0, 0, 0)); save(im, "save")
    im, d = canvas(); d.rounded_rectangle([36, 96, 180, 208], 14, outline=W, width=16); d.line([108, 152, 108, 60], fill=W, width=16); d.polygon([(72, 88), (144, 88), (108, 32)], fill=W); save(im, "export")
    im, d = canvas(); d.rounded_rectangle([36, 96, 180, 208], 14, outline=W, width=16); d.line([108, 108, 108, 200], fill=W, width=16); d.polygon([(72, 172), (144, 172), (108, 228)], fill=W); save(im, "import")
    im, d = canvas()
    for yy in (40, 144):
        for xx in (40, 144):
            d.rounded_rectangle([xx, yy, xx + 72, yy + 72], 12, fill=W)
    save(im, "group")

    # --- Meteo -------------------------------------------------------------
    im, d = canvas()
    d.ellipse([88, 88, 168, 168], fill=W)
    for a in range(0, 360, 45):
        import math
        x1 = 128 + 62 * math.cos(math.radians(a)); y1 = 128 + 62 * math.sin(math.radians(a))
        x2 = 128 + 96 * math.cos(math.radians(a)); y2 = 128 + 96 * math.sin(math.radians(a))
        d.line([x1, y1, x2, y2], fill=W, width=16)
    save(im, "sun")

    im, d = canvas()
    d.ellipse([48, 48, 208, 208], fill=W)
    d.ellipse([96, 20, 260, 180], fill=(0, 0, 0, 0))
    save(im, "moon")

    def cloud_shape(d, dy=0):
        d.ellipse([60, 96 + dy, 132, 168 + dy], fill=W)
        d.ellipse([104, 72 + dy, 196, 164 + dy], fill=W)
        d.ellipse([156, 100 + dy, 216, 160 + dy], fill=W)
        d.rectangle([64, 132 + dy, 212, 160 + dy], fill=W)

    im, d = canvas(); cloud_shape(d); save(im, "cloud")
    im, d = canvas(); cloud_shape(d, -22)
    for xx in (86, 128, 170):
        d.line([xx, 190, xx - 16, 232], fill=W, width=14)
    save(im, "rain")
    im, d = canvas(); cloud_shape(d, -22)
    for xx, yy in ((86, 196), (128, 214), (170, 196), (107, 232), (149, 232)):
        d.ellipse([xx - 11, yy - 11, xx + 11, yy + 11], fill=W)
    save(im, "snow")
    im, d = canvas(); cloud_shape(d, -26)
    d.polygon([(132, 168), (168, 168), (140, 208), (162, 208), (118, 248), (134, 200), (110, 200)], fill=W)
    save(im, "storm")
    im, d = canvas(); cloud_shape(d, -20)
    for yy in (176, 204, 232):
        d.line([72, yy, 196, yy], fill=W, width=14)
    save(im, "fog")

    # --- Icones de la interficie (les pantalles) ---------------------------
    # Rellotge: esfera amb dues agulles.
    im, d = canvas()
    d.ellipse([40, 40, 216, 216], outline=W, width=16)
    d.line([128, 128, 128, 76], fill=W, width=15)       # hores
    d.line([128, 128, 180, 152], fill=W, width=13)      # minuts
    save(im, "clock")

    # Graella: quatre quadrats (pantalles / espais).
    im, d = canvas()
    for yy in (44, 140):
        for xx in (44, 140):
            d.rounded_rectangle([xx, yy, xx + 72, yy + 72], 14, fill=W)
    save(im, "grid")

    # Teclat numeric: nou punts i la barra del zero.
    im, d = canvas()
    for row in range(3):
        for col in range(3):
            cx = 68 + col * 60
            cy = 62 + row * 52
            d.ellipse([cx - 18, cy - 18, cx + 18, cy + 18], fill=W)
    d.rounded_rectangle([56, 176, 200, 212], 16, fill=W)
    save(im, "num")

    print(f"Icones de mostra generades a {OUT}")


if __name__ == "__main__":
    main()
