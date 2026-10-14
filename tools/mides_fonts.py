#!/usr/bin/env python3
"""Mides reals de les fonts FreeSans de TFT_eSPI.

Llegeix les taules de glifs dels fitxers .h i treu l'amplada (xAdvance) de cada
caracter, per poder calcular exactament si un text hi cap en un espai donat.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, ".pio", "libdeps", "esp32dev", "TFT_eSPI",
                     "Fonts", "GFXFF")

NOMS = {
    "FreeSans9pt7b": "S (9pt)",
    "FreeSansBold12pt7b": "M (12pt negreta)",
    "FreeSansBold18pt7b": "L (18pt negreta)",
    "FreeSansBold24pt7b": "B (24pt negreta)",
}


def carrega(nom):
    """Retorna (amplades, alcada) d'una font: amplades[caracter] = xAdvance."""
    path = os.path.join(FONTS, nom + ".h")
    txt = open(path, encoding="utf-8", errors="replace").read()

    # La taula de glifs es una llista { bitmapOffset, width, height,
    # xAdvance, xOffset, yOffset }. Delimitem pel primer '{' i el primer '};'.
    i = txt.find("Glyphs[] PROGMEM")
    if i < 0:
        raise SystemExit("no trobo la taula de glifs a " + path)
    i = txt.find("{", i)
    j = txt.find("};", i)
    bloc = txt[i:j]

    glifs = re.findall(
        r"\{\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,"
        r"\s*(-?\d+)\s*\}", bloc)

    # Al final de l'estructura GFXfont hi ha "0x20, 0x7E, 22 };".
    m = re.search(r"0x([0-9A-Fa-f]+),\s*0x([0-9A-Fa-f]+),\s*(\d+)\s*\};", txt)
    if not m:
        raise SystemExit("no trobo first/last/yAdvance a " + path)
    primer = int(m.group(1), 16)
    ultim = int(m.group(2), 16)
    yadv = int(m.group(3))

    amp = {}
    for k, g in enumerate(glifs):
        cp = primer + k
        if cp <= ultim:
            amp[chr(cp)] = int(g[3])          # xAdvance
    return amp, yadv


def text_width(amp, text):
    return sum(amp.get(c, 0) for c in text)


def gauge_geom(r):
    """Mateixa geometria que src/ui.cpp (gaugeGeom)."""
    if r >= 60:
        r_out, halo = r - 14, 5
    elif r >= 46:
        r_out, halo = r - 11, 3
    else:
        r_out, halo = r - 8, 2
    gruix = 9 if r >= 60 else (7 if r >= 46 else 6)
    r_in = r_out - gruix
    return r_out, r_in, max(9, r_in - halo - 1)


ORDRE = ["FreeSansBold24pt7b", "FreeSansBold18pt7b",
         "FreeSansBold12pt7b", "FreeSans9pt7b"]
NOM_CURT = ["B (24)", "L (18)", "M (12)", "S (9)"]


def tria_numero(fonts, room):
    """Mateixa logica que drawGaugeNumber: retorna (index, amb_signe)."""
    petit = fonts["FreeSans9pt7b"][0]
    pw = text_width(petit, "%")
    triat = -1
    for k, nom in enumerate(ORDRE):
        if text_width(fonts[nom][0], "100") + 2 + pw <= room:
            triat = k
            break
    signe = (triat >= 0)
    if triat < 0:
        for k, nom in enumerate(ORDRE):
            if text_width(fonts[nom][0], "100") <= room:
                triat = k
                break
    if triat < 0:
        triat = 3
    return triat, signe


def radis_reals(W, H, n):
    """Mateix repartiment que el firmware (buildGauges)."""
    if n == 4:
        hero = min(W // 2 - 34, (H * 46) // 100 // 2)
        hero = max(32, hero)
        cell = W // 3
        small = min(cell // 2 - 10, (H * 26) // 100 // 2)
        small = max(20, small)
        return [hero, small, small, small]
    cols = 1 if n == 1 else (3 if n == 3 else 2)
    rows = (n + cols - 1) // cols
    cw, ch = W // cols, H // rows
    r = min(cw, ch) // 2 - 10
    r = max(24, r)
    r = min(r, 108 if n == 1 else 72)
    return [r] * n


def simulacio_gauges(fonts):
    print()
    print("=== SIMULACIO dels gauges (geometria nova) ===")
    casos = [
        ("vertical 320x480, 4 gauges", 320, 446 - 30, 4),
        ("vertical 320x480, 3 gauges", 320, 446 - 30, 3),
        ("vertical 320x480, 2 gauges", 320, 446 - 30, 2),
        ("vertical 320x480, 1 gauge",  320, 446 - 30, 1),
        ("horitzontal 480x320, 4",     480, 286 - 30, 4),
        ("horitzontal 480x320, 2",     480, 286 - 30, 2),
    ]
    for nom, W, H, n in casos:
        rs = radis_reals(W, H, n)
        trossos = []
        for r in rs:
            r_out, r_in, inner = gauge_geom(r)
            room = 2 * inner
            k, signe = tria_numero(fonts, room)
            trossos.append("r=%d disc=%d -> %s%s" %
                           (r, room, NOM_CURT[k], "" if signe else " (sense %)"))
        print("  %-28s %s" % (nom, " | ".join(trossos)))


def main():
    fonts = {}
    for nom in NOMS:
        try:
            fonts[nom] = carrega(nom)
        except Exception as exc:
            print("!!", nom, exc)

    print("=== amplada de text (pixels) ===")
    print("%-20s %5s %5s %5s %5s %6s" % ("text", "S", "M", "L", "B", "alcada"))
    mostres = ["0", "45", "100", "%", "45%", "100%", "88", "14:32",
               "MacBook_Pro_de_J", "LINK", "NO LINK", "--:--", "dl 12/10"]
    for m in mostres:
        vals = []
        for nom in NOMS:
            vals.append(text_width(fonts[nom][0], m) if nom in fonts else -1)
        h = fonts["FreeSans9pt7b"][1] if "FreeSans9pt7b" in fonts else 0
        print("%-20s %5d %5d %5d %5d %6d" % (m, vals[0], vals[1], vals[2],
                                             vals[3], h))

    print()
    print("=== alcades ===")
    for nom, (amp, y) in fonts.items():
        print("  %-22s yAdvance = %d" % (NOMS[nom], y))

    print()
    print("=== cap en un disc interior de radi 'inner'? ===")
    print("(el numero + '%' ha de cabre dins 2*inner)")
    for inner in (14, 16, 18, 19, 20, 23, 26, 30, 40):
        linia = "  inner=%2d (ample %3d) -> " % (inner, 2 * inner)
        for clau, et in (("FreeSansBold24pt7b", "B"), ("FreeSansBold18pt7b", "L"),
                         ("FreeSansBold12pt7b", "M"), ("FreeSans9pt7b", "S")):
            a = fonts[clau][0]
            ample = text_width(a, "100") + 2 + text_width(fonts["FreeSans9pt7b"][0], "%")
            linia += "%s:%s  " % (et, "SI" if ample <= 2 * inner else "no")
        print(linia)

    simulacio_gauges(fonts)


if __name__ == "__main__":
    main()
