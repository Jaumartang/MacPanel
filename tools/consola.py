#!/usr/bin/env python3
"""consola.py - envia una comanda a la consola de la placa i mostra la resposta.

La placa te una consola propia pel port serie (mira 'help'). Aquesta eina
serveix per provar coses sense el panell de control engegat (que tambe fa
servir el port).

Us:
    python3 tools/consola.py help
    python3 tools/consola.py info
    python3 tools/consola.py "page 1"      (canviar de pantalla)
    python3 tools/consola.py cfg
"""
import sys
import time

import serial

PORT = "/dev/cu.usbserial-1420"
ARRENCADA_S = 6.0      # obrir el port reinicia la placa: cal esperar


def main():
    cmd = " ".join(sys.argv[1:]).strip() or "help"
    ser = serial.Serial(PORT, 115200, timeout=0.3)
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass
    ser.reset_input_buffer()

    # Esperem que arrenqui (mentre obrim el port, la placa es reinicia).
    t0 = time.time()
    while time.time() - t0 < ARRENCADA_S:
        if ser.readline():
            break
    ser.reset_input_buffer()

    print(f">>> {cmd}")
    ser.write((cmd + "\n").encode("utf-8"))

    t0 = time.time()
    while time.time() - t0 < 3.0:
        raw = ser.readline()
        if raw:
            print("   ", raw.decode("utf-8", "replace").rstrip())
    ser.close()


if __name__ == "__main__":
    main()
