#!/usr/bin/env python3
"""diagnostic_anell.py - distingeix icones d'app de simbols.

El problema: els PNG de les icones d'app de macOS son QUADRES ARRODONITS amb
fons propi (Finder, Notes, VS Code...). Si el conversor els treu el fons, les
destrossa (queda nomes un tros: la tira groga de Notes, la ploma de TextEdit).

Com distingir-los? Un SIMBOL (bluetooth, wifi, volum...) te un fons pla d'un
sol color que arriba a totes les vores. Una ICONA D'APP omple el quadre, aixi
que el seu anell exterior te colors del propi dibuix.

Us:
    python3 tools/diagnostic_anell.py
"""
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "Assets", "icons")


def colors_anell(im, gruix=2, minim=0.02):
    """Quants colors diferents (que ocupin > minim de l'anell) te l'anell
    exterior de la imatge. 1 = fons pla (simbol); mes = icona que omple."""
    w, h = im.size
    px = im.load()
    punts = []
    for x in range(w):
        for k in range(gruix):
            punts.append(px[x, k])
            punts.append(px[x, h - 1 - k])
    for y in range(h):
        for k in range(gruix):
            punts.append(px[k, y])
            punts.append(px[w - 1 - k, y])
    comptes = {}
    for c in punts:
        comptes[c] = comptes.get(c, 0) + 1
    n = len(punts)
    return sum(1 for v in comptes.values() if v > n * minim)


def main():
    apps, simbols = [], []
    for f in sorted(os.listdir(SRC)):
        if not f.endswith(".png"):
            continue
        nom = f[:-4]
        im = Image.open(os.path.join(SRC, f)).convert("RGBA")
        te_alfa = im.getchannel("A").getextrema()[0] < 255
        c = colors_anell(im)
        if te_alfa:
            simbols.append((nom, "ja te alfa", c))
        elif c > 1:
            apps.append((nom, c))
        else:
            simbols.append((nom, "fons pla", c))

    print("ICONES D'APP (omplen el quadre -> cal MANTENIR el fons): %d"
          % len(apps))
    for n, c in apps:
        print("    %-22s %d colors a l'anell" % (n, c))
    print()
    print("SIMBOLS (fons pla o ja amb alfa -> es treu el fons): %d"
          % len(simbols))
    for n, motiu, c in simbols:
        print("    %-22s %s" % (n, motiu))


if __name__ == "__main__":
    main()
