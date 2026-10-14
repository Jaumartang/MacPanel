#!/usr/bin/env python3
"""mostra_originals.py - full de contacte amb tots els PNG d'origen.

Serveix per classificar-los a ull: quins son ICONES D'APP (quadres arrodonits
amb fons propi, que s'han de mantenir sencers) i quins son SIMBOLS (un dibuix
sobre un fons pla, que s'ha de treure el fons).

Us:
    python3 tools/mostra_originals.py
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "Assets", "icons")
OUT = os.path.join(ROOT, "mostra_originals.png")


def main():
    noms = sorted(n[:-4] for n in os.listdir(SRC) if n.endswith(".png"))
    cols, cellw, cellh = 6, 130, 152
    rows = (len(noms) + cols - 1) // cols
    full = Image.new("RGB", (cols * cellw, rows * cellh + 26), (18, 22, 30))
    d = ImageDraw.Draw(full)
    d.text((6, 7), "ORIGINALS dels PNG (fons blau fosc = transparencia real)",
           fill=(0, 200, 255))

    for i, nom in enumerate(noms):
        im = Image.open(os.path.join(SRC, nom + ".png")).convert("RGBA")
        fons = Image.new("RGBA", im.size, (8, 16, 40, 255))
        fons.alpha_composite(im)
        fons = fons.convert("RGB").resize((112, 112))
        x = (i % cols) * cellw
        y = (i // cols) * cellh + 26
        d.rectangle([x + 2, y + 2, x + cellw - 3, y + cellh - 3],
                    outline=(40, 60, 90))
        d.text((x + 6, y + 5), nom[:16], fill=(255, 255, 255))
        full.paste(fons, (x + 8, y + 20))

    full.save(OUT)
    print("desat:", OUT)


if __name__ == "__main__":
    main()
