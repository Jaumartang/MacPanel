#!/usr/bin/env python3
"""test_tema.py - prova el tema automatic (clar/fosc segons el Mac).

Comprova que:
  1) amb el tema automatic desactivat, el Mac pot canviar d'aparenca i la placa
     no canvia de tema (mana el tema manual)
  2) activant el tema automatic, s'aplica el tema de l'aparenca que te el Mac
  3) si el Mac passa de fosc a clar, la placa canvia de tema tota sola
  4) els botons 'Tema <' / 'Tema >' canvien el tema de l'aparenca actual

Fa servir la comanda de consola 'ajust <id>' (com si es premes un boto dels
ajustos) i linies 'S' amb 'dk=1'/'dk=0' per dir si el Mac es fosc o clar.

Us:
    python3 tools/test_tema.py [/dev/cu.usbserial-XXXX]
"""
import re
import sys
import time

import serial

from comu import Enllac, troba_port

PORT = sys.argv[1] if len(sys.argv) > 1 else (troba_port() or
                                              "/dev/cu.usbserial-1420")

# Els mateixos noms que src/theme.cpp (per saber quin tema s'ha aplicat).
TEMES = ["Fosc", "Clar", "Neo", "Grafite", "Pastel", "HUD"]


def tema_de(out):
    """Ultim tema aplicat que surt al registre ('[UI] tema: X')."""
    noms = [l.split("tema:", 1)[1].strip() for l in out if "[UI] tema: " in l]
    return noms[-1] if noms else None


def main():
    ser = serial.Serial(PORT, 115200, timeout=0.3)
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass
    ser.reset_input_buffer()

    # Obrir el port reinicia la placa: esperem que arrenqui.
    t0 = time.time()
    while time.time() - t0 < 12.0:
        raw = ser.readline()
        if raw and b"Mac Panel" in raw:
            break
    time.sleep(2.0)
    ser.reset_input_buffer()

    # El Mac el fem nosaltres. Comencem dient que te l'aparenca fosca.
    enllac = Enllac(ser, dark=1).comenca()

    def drain(sec=1.6):
        out = []
        t = time.time()
        while time.time() - t < sec:
            raw = ser.readline()
            if raw:
                out.append(raw.decode("utf-8", "replace").rstrip())
        return out

    def ajust(que, sec=1.6):
        enllac.envia(f"ajust {que}\n")
        return drain(sec)

    def cfg_actual():
        enllac.envia("cfg\n")
        for l in drain(1.2):
            m = re.search(r"tema=(\d+) auto=(\d+) fosc=(\d+) clar=(\d+)", l)
            if m:
                return tuple(int(x) for x in m.groups())
        return None

    proves = []

    cf = cfg_actual()
    if cf is None:
        print("NO he pogut llegir la configuracio de la placa")
        ser.close()
        return 1
    tema, auto, fosc, clar = cf
    print(f"=== configuracio de la placa: tema={tema} auto={auto} "
          f"fosc={fosc} clar={clar} ===")
    print(f"    (tema fosc = {TEMES[fosc]}, tema clar = {TEMES[clar]})")
    print()

    # 1) Sense tema automatic: el Mac canvia d'aparenca i la placa no es mou.
    print("=== 1) tema automatic desactivat: mana el tema manual ===")
    if auto:
        ajust("themeauto")
    out = ajust("theme+")                    # un tema manual qualsevol
    abans = tema_de(out)
    print(f"    tema manual: {abans}")
    enllac.dark = 0
    out1 = drain(1.6)
    enllac.dark = 1
    out2 = drain(1.6)
    # Si no surt cap linia nova de tema es que no ha canviat: segueix el mateix.
    segueix = tema_de(out1 + out2) or abans
    canvi = any("el Mac es" in l for l in out1 + out2)
    print(f"    despres de canviar el Mac de clar a fosc: {segueix}"
          f"  (canvis automatics: {'SI' if canvi else 'no'})")
    proves.append(("amb el tema automatic desactivat mana el manual",
                   (segueix == abans) and not canvi))

    # 2) Tema automatic: s'aplica el tema de l'aparenca del Mac (fosc).
    print("=== 2) activo el tema automatic amb el Mac en fosc ===")
    out = ajust("themeauto", 2.2)
    for l in out:
        if "tema automatic" in l or "el Mac es" in l or "[UI] tema: " in l:
            print("   ", l)
    actiu = any("tema automatic activat" in l for l in out)
    ara = tema_de(out)
    print(f"   -> tema automatic actiu: {'SI' if actiu else 'NO'}; tema: {ara}")
    proves.append(("el tema automatic agafa el tema fosc",
                   actiu and ara == TEMES[fosc]))

    # 3) El Mac passa a clar: la placa canvia de tema tota sola.
    print("=== 3) el Mac passa a clar ===")
    enllac.dark = 0
    out = drain(2.2)
    for l in out:
        if "el Mac es" in l or "[UI] tema: " in l:
            print("   ", l)
    clar_ok = any("el Mac es clar" in l for l in out)
    ara = tema_de(out)
    if fosc == clar:
        print("   -> (el tema fosc i el clar son el mateix: no pot canviar)")
        proves.append(("el Mac passa a clar", True))
    else:
        print(f"   -> canvia sol: {'SI' if clar_ok else 'NO'}; tema: {ara}")
        proves.append(("el Mac passa a clar i canvia sol",
                       clar_ok and ara == TEMES[clar]))

    # 4) Amb el tema automatic, 'Tema >' canvia el tema de l'aparenca actual.
    print("=== 4) 'Tema >' amb el Mac en clar ===")
    out = ajust("theme+", 1.8)
    for l in out:
        if "[UI] tema " in l or "[UI] tema: " in l:
            print("   ", l)
    tocat = any("[UI] tema clar ->" in l for l in out)
    nou = tema_de(out)
    print(f"   -> canvia el tema clar: {'SI' if tocat else 'NO'}; tema: {nou}")
    proves.append(("'Tema >' canvia el tema de l'aparenca actual", tocat))

    # Deixem el tema automatic com estava.
    if not auto:
        ajust("themeauto")

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
