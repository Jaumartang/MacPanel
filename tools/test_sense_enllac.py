#!/usr/bin/env python3
"""test_sense_enllac.py - comprova el mode "sense enllac" de la placa.

Quan la placa no rep cap linia d'estadistiques del Mac durant uns segons,
considera que no te enllac i ha de:
  - passar tota sola a la pantalla de rellotge
  - deixar NOMES els ajustos de la placa (el menu amb un sol item)
  - no fer res quan es toca un boto
  - tornar a les pantalles normals quan l'enllac es recupera

Us:
    python3 tools/test_sense_enllac.py [/dev/cu.usbserial-XXXX]
"""
import glob
import re
import sys
import time

import serial

from comu import Enllac, troba_port

PORT = sys.argv[1] if len(sys.argv) > 1 else (troba_port() or
                                              "/dev/cu.usbserial-1420")
OK = []
KO = []


def comprova(nom, cond, detall=""):
    (OK if cond else KO).append(nom)
    print(("  OK   " if cond else "  FALLA") + "  " + nom)
    if detall:
        print("        %s" % detall)


def main():
    print("port:", PORT)
    ser = serial.Serial(PORT, 115200, timeout=0.2)
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass
    ser.reset_input_buffer()

    def llegeix(segons):
        fi = time.time() + segons
        out = ""
        while time.time() < fi:
            try:
                d = ser.read(4096)
            except serial.SerialException:
                # El cable USB ha fet un glitch: ho diem i parem.
                print("        !! el port USB s'ha desconnectat a mig test")
                return out
            if d:
                out += d.decode("utf-8", "replace")
        return out

    def resum(txt):
        return txt.strip().replace("\n", " | ")[:150] or "(cap sortida)"

    enllac = Enllac(ser, periode=0.6)
    enllac.comenca()
    time.sleep(5)                       # que la placa es vegi enllacada

    # --- 1) Amb enllac: el menu te totes les pantalles --------------------
    print("\n1) Amb enllac, el menu ha de tenir totes les pantalles...")
    ser.reset_input_buffer()
    enllac.envia("menu\n")
    txt = llegeix(2)
    enllac.envia("menu\n")              # el tanco
    llegeix(1)
    m = re.search(r"menu: (\d+) items", txt)
    comprova("el menu te mes d'un item (pantalles + Ajustos)",
             m is not None and int(m.group(1)) > 1, resum(txt))

    # --- 2) Deixo d'enviar 'S': ha de passar a rellotge -------------------
    print("\n2) Deixo d'enviar estadistiques: ha de passar a rellotge...")
    enllac.atura()
    time.sleep(1)
    ser.reset_input_buffer()
    txt = llegeix(7)
    comprova("la placa es declara sense enllac", "sense enllac" in txt,
             resum(txt))

    # --- 3) Nomes ajustos --------------------------------------------------
    print("\n3) El menu nomes ha de tenir 1 item (Ajustos)...")
    ser.reset_input_buffer()
    ser.write(b"menu\n")
    txt = llegeix(2)
    comprova("el menu nomes te 1 item (Ajustos)",
             "menu: 1 items" in txt, resum(txt))

    # --- 4) Els botons no fan res -----------------------------------------
    print("\n4) Toco on hi hauria un boto: no ha de fer res...")
    ser.write(b"menu\n")                # el menu es tanca (es commutador)
    time.sleep(0.6)
    ser.reset_input_buffer()
    ser.write(b"toca 160 200\n")
    txt = llegeix(2)
    comprova("tocar un boto no envia cap comanda ni executa res",
             "C " not in txt and "-> boto" not in txt, resum(txt))

    # --- 5) Torna l'enllac -------------------------------------------------
    print("\n5) Torno a enviar estadistiques: ha de recuperar les pantalles...")
    ser.reset_input_buffer()
    enllac.comenca()
    txt = llegeix(6)
    comprova("la placa recupera l'enllac", "enllac recuperat" in txt,
             resum(txt))

    enllac.atura()
    ser.close()
    print("\n=== RESULTAT ===")
    print("correctes : %d/%d" % (len(OK), len(OK) + len(KO)))
    for n in KO:
        print("   FALLA:", n)
    return 1 if KO else 0


if __name__ == "__main__":
    sys.exit(main())
