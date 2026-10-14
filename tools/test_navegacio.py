#!/usr/bin/env python3
"""test_navegacio.py - prova la barra de navegacio i el lliscament.

Fa servir les comandes de consola 'toca' i 'llisca' (que simulen tocs de dit)
per comprovar que es canvia de pantalla amb la barra de baix i lliscant.

Us:
    python3 tools/test_navegacio.py [/dev/cu.usbserial-XXXX]
"""
import re
import sys
import time

import serial

from comu import Enllac, mida_pantalla, troba_port

PORT = sys.argv[1] if len(sys.argv) > 1 else (troba_port() or
                                              "/dev/cu.usbserial-1420")


def main():
    ser = serial.Serial(PORT, 115200, timeout=0.3)
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass
    ser.reset_input_buffer()
    # La placa nomes ensenya les pantalles si te enllac: li enviem linies 'S'.
    enllac = Enllac(ser).comenca()

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

    def cmd(c, sec=1.6):
        enllac.envia(c + "\n")
        return drain(sec)

    def pantalla(out):
        """Ultim numero de pantalla que surt a la sortida."""
        n = None
        for l in out:
            m = re.search(r"pantalla\s*=\s*(\d+)", l)
            if m:
                n = int(m.group(1))
            m = re.search(r"pantalla -> (\d+)", l)
            if m:
                n = int(m.group(1))
        return n

    proves = []

    def prova(nom, out, esperat):
        obtingut = pantalla(out)
        ok = (obtingut == esperat)
        print(f"  {'OK ' if ok else 'MAL'}  {nom}: pantalla {obtingut} "
              f"(esperat {esperat})")
        proves.append(ok)

    # Les coordenades depenen de l'orientacio de la placa.
    W, H = mida_pantalla(enllac, drain)
    NAVY = H - 10            # mig de la barra de navegacio (NAV_H = 20)
    XR = W // 8              # zona de '<'
    XL = W * 7 // 8          # zona de '>'
    XM = W // 2
    print(f">>> pantalla {W}x{H} (barra de navegacio a y={NAVY})")

    print(">>> poso la pantalla 0")
    cmd("page 0")

    print(f">>> barra: toco '<' ({XR},{NAVY})")
    prova("barra < (enrere, circular)", cmd(f"toca {XR} {NAVY}"), 11)

    print(f">>> barra: toco '>' ({XL},{NAVY})")
    prova("barra > (endavant)", cmd(f"toca {XL} {NAVY}"), 0)

    print(">>> llisco cap a l'esquerra")
    prova("lliscar enrere->endavant",
          cmd(f"llisca {W * 3 // 4} {H // 2} {W // 4} {H // 2 + 5}"), 1)

    print(">>> llisco cap a la dreta")
    prova("lliscar endavant->enrere",
          cmd(f"llisca {W // 4} {H // 2} {W * 3 // 4} {H // 2 + 5}"), 0)

    print(f">>> toco al mig de la barra ({XM},{NAVY}): no ha de canviar")
    prova("tocar el mig no canvia", cmd(f"toca {XM} {NAVY}"), 0)

    print()
    print("=== RESULTAT ===")
    print(f"  {sum(proves)}/{len(proves)} correctes")
    ser.close()
    return 0 if all(proves) else 1


if __name__ == "__main__":
    sys.exit(main())
