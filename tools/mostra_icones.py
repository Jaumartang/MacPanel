#!/usr/bin/env python3
"""mostra_icones.py - full de contacte amb totes les icones, tal com es veuen
a la placa.

Dibuixa cada icona sobre el color de fons de la targeta (com fa el firmware) a
la mida real dels botons (40 px) i a la mida nativa (64 px), per poder detectar
d'un cop d'ull quines es veuen malament: fons que no s'ha tret, simbols que no
es llegeixen, etc.

Us:
    python3 tools/mostra_icones.py
"""
import os
import struct

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "Assets", "icons", "bin")
OUT = os.path.join(ROOT, "mostra_icones.png")

SIZE = 64
TRANS = 0xF81F

# Colors del tema HUD, com a la placa
BG = 0x0000
CARD = 0x0883
EDGE = 0x0947
ACCENT = 0x07BF
DIM = 0x5C95


def rgb(c):
    return (((c >> 11) & 0x1F) * 255 // 31,
            ((c >> 5) & 0x3F) * 255 // 63,
            (c & 0x1F) * 255 // 31)


def llegeix(nom):
    """(imatge RGB, pct_transparent) de la icona .bin (RGB565 big-endian)."""
    d = open(os.path.join(BIN, nom + ".bin"), "rb").read()
    v = struct.unpack(">%dH" % (SIZE * SIZE), d[:SIZE * SIZE * 2])
    im = Image.new("RGB", (SIZE, SIZE))
    px = im.load()
    mg = 0
    for i, c in enumerate(v):
        if c == TRANS:
            mg += 1
            px[i % SIZE, i // SIZE] = rgb(CARD)      # el fons de destí
        else:
            px[i % SIZE, i // SIZE] = rgb(c)
    return im, 100.0 * mg / (SIZE * SIZE)


def main():
    noms = sorted(n[:-4] for n in os.listdir(BIN) if n.endswith(".bin"))
    if not noms:
        print("no hi ha cap .bin a", BIN)
        return

    cols = 6
    cellw, cellh = 110, 116
    rows = (len(noms) + cols - 1) // cols
    full = Image.new("RGB", (cols * cellw, rows * cellh + 30), rgb(BG))
    d = ImageDraw.Draw(full)

    d.text((6, 8), "ICONES sobre el fons de targeta (com a la placa)",
           fill=rgb(ACCENT))

    for i, nom in enumerate(noms):
        im, pct = llegeix(nom)
        cx = (i % cols) * cellw
        cy = (i // cols) * cellh + 30

        # requadre de la cel·la
        d.rectangle([cx + 2, cy + 2, cx + cellw - 3, cy + cellh - 3],
                    outline=rgb(EDGE))

        # la icona tal com la dibuixa el firmware (64 px i 40 px)
        full.paste(im, (cx + 4, cy + 16))
        petita = im.resize((40, 40), Image.LANCZOS)
        full.paste(petita, (cx + 68, cy + 28))

        # nom + estat del fons
        col = rgb(ACCENT) if pct > 5 else (255, 60, 60)
        d.text((cx + 4, cy + 4), nom[:15], fill=col)
        d.text((cx + 4, cy + 82), "%.0f%% fons" % (100 - pct), fill=rgb(DIM))

    full.save(OUT)
    print("desat:", OUT)
    print("%d icones en una graella de %d x %d" % (len(noms), cols, rows))
    print()
    print("A l'esquerra de cada cela: la icona a 64 px (mida nativa).")
    print("A la dreta: a 40 px (com surt als botons).")
    print("En vermell: icones que NO tenen fons transparent.")


if __name__ == "__main__":
    main()
