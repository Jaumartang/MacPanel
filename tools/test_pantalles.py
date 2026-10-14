#!/usr/bin/env python3
"""test_pantalles.py - passa per totes les pantalles i comprova que no peti.

Obre el port serie directament (atura abans el panell), demana la llista de
pantalles, les va canviant una a una i vigila si la placa es reinicia o fa un
'abort()'. Serveix per assegurar que totes les disposicions (gadgets, gauges,
grafics, rellotge, numpad, launcher...) es dibuixen sense problemes.

Us:
    python3 tools/test_pantalles.py [/dev/cu.usbserial-XXXX]
"""
import re
import sys
import time

import serial

from comu import Enllac, troba_port

PORT = sys.argv[1] if len(sys.argv) > 1 else (troba_port() or
                                              "/dev/cu.usbserial-1420")
LINES = []


def drain(ser, seconds):
    """Llegeix el que arriba durant 'seconds' i ho desa a LINES."""
    t0 = time.time()
    while time.time() - t0 < seconds:
        raw = ser.readline()
        if not raw:
            continue
        line = raw.decode("utf-8", "replace").rstrip()
        if line:
            LINES.append(line)
            print("   ", line)


def main():
    print(f"obre {PORT} (aixo reinicia la placa)")
    ser = serial.Serial(PORT, 115200, timeout=0.3)
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass
    ser.reset_input_buffer()
    # La placa nomes ensenya les pantalles si te enllac: li enviem linies 'S'.
    enllac = Enllac(ser).comenca()
    drain(ser, 7)                       # que acabi d'arrencar

    print(">>> demano la llista de pantalles")
    enllac.envia(b"pages\n")
    drain(ser, 2)

    pages = []
    for l in LINES:
        m = re.search(r"\[CFG\]\s+(\d+)\. '([^']*)' \((\w+)\)", l)
        if m:
            pages.append((int(m.group(1)), m.group(2), m.group(3)))

    if not pages:
        print("!! no he pogut llegir la llista de pantalles")
        ser.close()
        return 1

    print(f">>> {len(pages)} pantalles; les recorro totes")
    problemes = 0
    for idx, name, layout in pages:
        before = len(LINES)
        enllac.envia(f"page {idx}\n")
        drain(ser, 3)
        noves = LINES[before:]
        dolent = [l for l in noves
                  if "abort()" in l or "Guru Meditation" in l
                  or "Backtrace" in l or "rst:0x" in l]
        canviat = any("pantalla ->" in l for l in noves)
        estat = "OK" if (canviat and not dolent) else "PROBLEMA"
        print(f"   -> pantalla {idx} '{name}' ({layout}): {estat}")
        if dolent:
            problemes += 1
            for l in dolent:
                print("      !!", l)

    print()
    print("=== RESULTAT ===")
    print(f"pantalles provades : {len(pages)}")
    print(f"problemes          : {problemes}")
    enllac.atura()
    ser.close()
    return 0 if problemes == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
