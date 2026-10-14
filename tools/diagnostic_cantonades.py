#!/usr/bin/env python3
"""diagnostic_cantonades.py - que hi ha a les cantonades dels PNG?

Si les cantonades son transparents (alfa 0), la icona ja ve retallada i no cal
tocar res. Si son d'un color pla, la icona es un quadre i el conversor decideix
si aquell color es fons o no.
"""
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "Assets", "icons")

NOMS = ["notes", "textedit", "finder", "vscode", "calendar", "word",
        "bluetooth", "wifi", "chrome", "safari", "dropbox", "term"]


def main():
    for n in NOMS:
        p = os.path.join(SRC, n + ".png")
        if not os.path.exists(p):
            print("%-12s (no hi es)" % n)
            continue
        im = Image.open(p).convert("RGBA")
        w, h = im.size
        px = im.load()
        c = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
        mig = px[w // 2, h // 2]
        print("%-12s %3dx%-3d cantonades=%s  mig=%s" % (n, w, h, c, mig))


if __name__ == "__main__":
    main()
