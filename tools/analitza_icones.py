#!/usr/bin/env python3
"""analitza_icones.py - informe de les icones: quines falten i com han quedat.

Comprova, per a cada icona que fa servir la configuracio:
  - si hi ha el PNG a Assets/icons/
  - si hi ha el .bin a Assets/icons/bin/
  - com ha quedat el .bin (fons tret, fons propi o buida)

Us:  python3 tools/analitza_icones.py
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "Assets", "icons")
BIN = os.path.join(SRC, "bin")
TRANS = 0xF81F
SIZE = 64

# Icones que fa servir el firmware (no surten a la configuracio).
DEL_FIRMWARE = ["sun", "moon", "cloud", "fog", "rain", "snow", "storm",
                "system_settings"]


def icones_config():
    """Totes les icones que referencia la configuracio (pagines i botons)."""
    sys.path.insert(0, os.path.join(ROOT, "mac"))
    try:
        import bridge
        cfg = bridge.load_config()
    except Exception as exc:
        print("(no he pogut llegir la configuracio:", exc, ")")
        return []

    noms = set(DEL_FIRMWARE)
    for p in cfg.get("pages", []):
        if p.get("icon"):
            noms.add(p["icon"])
        for b in p.get("buttons", []):
            if b.get("icon"):
                noms.add(b["icon"])
    return sorted(noms)


def estat_bin(nom):
    """(pct_transparent, te_fons, existeix)"""
    p = os.path.join(BIN, nom + ".bin")
    if not os.path.exists(p):
        return 0.0, False, False
    d = open(p, "rb").read()
    n = len(d) // 2
    if n != SIZE * SIZE:
        return 0.0, False, True
    v = struct.unpack(">%dH" % n, d[:n * 2])
    mg = sum(1 for x in v if x == TRANS)
    pct = 100.0 * mg / n
    cant = [v[0], v[SIZE - 1], v[(SIZE - 1) * SIZE], v[SIZE * SIZE - 1]]
    return pct, any(c != TRANS for c in cant), True


def main():
    noms = icones_config()
    if not noms:
        return

    sense_png, sense_bin, buides, amb_fons, ok = [], [], [], [], []

    for n in noms:
        pct, te_fons, hi_es = estat_bin(n)
        png = os.path.exists(os.path.join(SRC, n + ".png"))
        if not hi_es:
            sense_bin.append(n)
        elif pct >= 99:
            buides.append(n)
        elif te_fons:
            amb_fons.append(n)
        else:
            ok.append(n)
        if not png:
            sense_png.append(n)

    print(f"Icones que fa servir la configuracio: {len(noms)}")
    print(f"  correctes (fons transparent) : {len(ok)}")
    print(f"  amb fons propi (apps)        : {len(amb_fons)}")
    print(f"  TOTALMENT buides             : {len(buides)}")
    print(f"  sense .bin a la SD           : {len(sense_bin)}")
    print(f"  sense PNG d'origen           : {len(sense_png)}")
    print()

    if sense_bin:
        print("!! FALTEN (cal generar l'icona i pujar-la):")
        for n in sense_bin:
            print("   ", n)
        print()

    if buides:
        print("!! BUIDES (el PNG no te res aprofitable; torna'l a fer):")
        for n in buides:
            print("   ", n)
        print()

    if amb_fons:
        print("AMB FONS PROPI (pot ser correcte si es una icona d'app):")
        for n in amb_fons:
            pct, _, _ = estat_bin(n)
            print(f"    {n:<24} {pct:5.1f}% transparent")
        print()

    if sense_png:
        print("SENSE PNG (nomes hi ha el .bin):")
        print("   ", ", ".join(sense_png))
        print()

    print("Consell: per a les icones de tipus simbol, el millor es un PNG amb")
    print("transparencia de veritat. Despres:")
    print("   python3 tools/png2bin.py && python3 tools/puja-icones.py")


if __name__ == "__main__":
    main()
