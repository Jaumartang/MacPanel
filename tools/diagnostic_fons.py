#!/usr/bin/env python3
"""diagnostic_fons.py - mira quin tant per cent de cada PNG es fons.

Serveix per ajustar el llindar de seguretat del png2bin (una icona petita
sobre un fons gran elimina legítimament mes del 85% de la imatge).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image
import png2bin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "Assets", "icons")

NOMS = ["bluetooth", "wifi", "volume_up", "brightness_up", "eject",
        "spotlight", "vscode", "option_key", "airdrop", "do_not_disturb",
        "textedit", "play", "finder", "mail", "calendar", "chrome"]


def main():
    print(f"{'icona':<20} {'fons':>7}  {'queda':>7}")
    print("-" * 38)
    for n in NOMS:
        p = os.path.join(SRC, n + ".png")
        if not os.path.exists(p):
            continue
        im = Image.open(p)
        if png2bin.has_alpha(im):
            print(f"{n:<20} {'(alfa)':>7}  {'-':>7}")
            continue
        rgb = im.convert("RGB")
        mask, _ = png2bin.bg_mask(rgb)
        frac = sum(mask) / float(rgb.size[0] * rgb.size[1])
        print(f"{n:<20} {frac*100:6.1f}%  {(1-frac)*100:6.1f}%")


if __name__ == "__main__":
    main()
