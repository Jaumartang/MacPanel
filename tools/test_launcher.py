#!/usr/bin/env python3
"""test_launcher.py - prova el launcher d'apps obertes (pantalla "Obertes").

El launcher ensenya les apps obertes al Mac amb la seva icona. Les dades arriben
del Mac amb la linia:

    L Finder=finder|Safari=safari|Visual Studio Code=vscode

Comprova que:
  1. La placa enten el format 'nom=icona' i desa les dues coses.
  2. Cada icona que envia el Mac hi es a la SD de la placa.
  3. Una icona que no hi es a la SD es detecta (i el boto no peta).
  4. Una app sense icona tampoc no trenca res.
  5. Tocar un boto d'app envia 'C focus:N' al Mac (per portar-la al davant).

Us:
    python3 tools/test_launcher.py [/dev/cu.usbserial-XXXX]
"""
import re
import sys
import time

import serial

from comu import Enllac, mida_pantalla, troba_port

PORT = sys.argv[1] if len(sys.argv) > 1 else (troba_port() or
                                              "/dev/cu.usbserial-1420")

# La pantalla del launcher i la seva geometria (2 columnes, com a src/ui.cpp).
PAGE_LAUNCHER = 8
BTN_TOP = 36             # HEADER_H + PAD
ROW0_Y = 81              # mig de la primera fila de botons


def columnes_x(W):
    """Centres de les dues columnes de botons per a una amplada W.

    En horitzontal la pantalla es mes ampla i els botons tambe, aixi que les
    coordenades s'han de calcular.
    """
    cw = (W - 6 * 3) // 2          # PAD * (columnes + 1)
    return (6 + cw // 2, 6 + cw + 6 + cw // 2)

# El que enviarem com si fos el Mac: 4 apps, una amb icona que no hi es i una
# sense icona.
APPS = ["Finder", "Safari", "Visual Studio Code", "Terminal",
        "Rara", "SenseIcona"]
ICONES = {"Finder": "finder", "Safari": "safari",
          "Visual Studio Code": "vscode", "Terminal": "terminal",
          "Rara": "no_existeix_aixo"}
# Apps amb icona que NO hi es a la SD a posta (per provar que es detecta).
FALTA_A_POSTA = {"Rara"}
LINIA = ("L " + "|".join(
    f"{a}={ICONES[a]}" if a in ICONES else a for a in APPS))


def main():
    ser = serial.Serial(PORT, 115200, timeout=0.3)
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass
    ser.reset_input_buffer()
    enllac = Enllac(ser).comenca()

    # Obrir el port reinicia la placa: esperem que arrenqui de veritat.
    t0 = time.time()
    while time.time() - t0 < 10.0:
        raw = ser.readline()
        if raw and b"Mac Panel" in raw:
            break
    time.sleep(2.0)
    ser.reset_input_buffer()

    def drain(sec=1.6):
        out = []
        t = time.time()
        while time.time() - t < sec:
            raw = ser.readline()
            if raw:
                out.append(raw.decode("utf-8", "replace").rstrip())
        return out

    def envia(cmd, sec=1.6):
        enllac.envia(cmd + "\n")
        return drain(sec)

    # Les coordenades dels botons depenen de l'orientacio de la placa.
    W, _H = mida_pantalla(enllac, drain)
    COL0_X, COL1_X = columnes_x(W)
    print(f"    (pantalla {W}px -> columnes a x={COL0_X} i x={COL1_X})")

    proves = []

    # --- 1) El Mac envia la llista d'apps amb les icones --------------------
    print("=== 1) envio la llista d'apps (com fa el Mac) ===")
    print(f"    {LINIA}")
    envia(LINIA)
    out = envia("apps")
    files = [l for l in out if l.startswith("[APP]") and "icona=" in l]
    for l in files:
        print("   ", l)

    n = 0
    if out and "apps obertes al Mac" in " ".join(out):
        m = re.search(r"\[APP\] (\d+) apps", " ".join(out))
        n = int(m.group(1)) if m else 0
    print(f"   -> la placa veu {n} apps")
    proves.append(("la placa rep les apps", n == len(APPS)))

    # --- 2) Cada app amb icona hi te la icona a la SD -----------------------
    print("=== 2) les icones existeixen a la SD ===")
    ok_icones = True
    vistes = {}
    for l in files:
        nom = (l.split("[APP]")[1].split("icona=")[0]
               .strip().split(None, 1)[1].strip())
        resta = l.split("icona=")[1]
        icona = resta.split()[0]
        estat = "FALTA" if "FALTA" in resta else (
            "SD" if "a la SD" in resta else "")
        vistes[nom] = (icona, estat)
        if nom in ICONES and nom not in FALTA_A_POSTA:
            be = (icona == ICONES[nom] and estat == "SD")
            print(f"    {nom:<20} icona={icona:<14} {estat or '(sense)'}"
                  f"  {'OK' if be else 'MAL'}")
            ok_icones = ok_icones and be
    proves.append(("les icones del Mac hi son a la SD", ok_icones))

    # --- 3) Una icona que no hi es es detecta ------------------------------
    print("=== 3) una icona que no hi es a la SD es detecta ===")
    ic, est = vistes.get("Rara", ("", ""))
    detectat = (est == "FALTA")
    print(f"    Rara -> icona={ic} {est or '(sense)'}")
    proves.append(("detecta una icona que falta", detectat))

    # --- 4) Una app sense icona no trenca res ------------------------------
    print("=== 4) una app sense icona ===")
    ic, est = vistes.get("SenseIcona", ("", ""))
    sense = (ic == "(cap)")
    print(f"    SenseIcona -> icona={ic} {est or '(sense)'}")
    proves.append(("una app sense icona no trenca", sense))

    # --- 5) Tocar un boto d'app envia 'C focus:N' --------------------------
    print("=== 5) vaig a la pantalla del launcher i toco la primera app ===")
    envia(f"page {PAGE_LAUNCHER}")
    out = envia(f"toca {COL0_X} {ROW0_Y}", 2.0)
    for l in out:
        if "[TEST]" in l or l.startswith("C "):
            print("   ", l)
    focus = [l for l in out if l.startswith("C focus:")]
    be0 = bool(focus) and focus[-1] == "C focus:0"
    print(f"   -> ha enviat: {focus[-1] if focus else '(res)'}"
          f"  {'OK' if be0 else 'MAL'}")
    proves.append(("tocar la app 0 envia 'C focus:0'", be0))

    print("=== 6) toco la segona app (columna de la dreta) ===")
    out = envia(f"toca {COL1_X} {ROW0_Y}", 2.0)
    for l in out:
        if "[TEST]" in l or l.startswith("C "):
            print("   ", l)
    focus = [l for l in out if l.startswith("C focus:")]
    be1 = bool(focus) and focus[-1] == "C focus:1"
    print(f"   -> ha enviat: {focus[-1] if focus else '(res)'}"
          f"  {'OK' if be1 else 'MAL'}")
    proves.append(("tocar la app 1 envia 'C focus:1'", be1))

    print()
    print("=== RESULTAT ===")
    ok = 0
    for nom, res in proves:
        print(f"  {'OK ' if res else 'MAL'}  {nom}")
        ok += 1 if res else 0
    print(f"  {ok}/{len(proves)} correctes")
    ser.close()
    return 0 if ok == len(proves) else 1


if __name__ == "__main__":
    sys.exit(main())
