#!/usr/bin/env python3
"""diagnostic_png.py - mira si els PNG d'origen tenen transparencia de veritat.

Es important: si un PNG es totalment opac (un quadre amb fons), el conversor ha
d'endevinar que es fons i que es dibuix, i amb les icones d'app sovint s'equivoca
(treu el fons clar i deixa l'icona trencada).
"""
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "Assets", "icons")


def main():
    noms = sorted(n[:-4] for n in os.listdir(SRC) if n.endswith(".png"))
    transparents, opacs, mixtos = [], [], []
    for n in noms:
        im = Image.open(os.path.join(SRC, n + ".png")).convert("RGBA")
        a = im.getchannel("A")
        lo, hi = a.getextrema()
        if lo == 255:
            opacs.append(n)
        elif hi == 0:
            transparents.append(n)
        else:
            mixtos.append((n, lo))

    print("PNG d'origen: %d" % len(noms))
    print("  amb transparencia de veritat (alfa variable): %d" % len(mixtos))
    print("  TOTALMENT opacs (el conversor ha d'endevinar el fons): %d"
          % len(opacs))
    print("  totalment transparents: %d" % len(transparents))
    print()
    if opacs:
        print("OPACS (aquests son els que poden sortir malament):")
        for n in opacs:
            print("   ", n)
        print()
    if mixtos:
        print("AMB ALFA (aquests surten sempre be):")
        for n, lo in mixtos:
            print("    %-24s alfa minim = %d" % (n, lo))


if __name__ == "__main__":
    main()
