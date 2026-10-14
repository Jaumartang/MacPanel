#!/usr/bin/env python3
"""test_grafics.py - comprova que l'historial dels grafics s'omple i calcula be.

No cal el Mac: envia linies d'estadistiques 'S' fetes a ma amb valors que
coneixem i despres demana l'historial a la placa ('hist') per comprovar que el
minim, la mitjana i el maxim quadren.

Us:
    python3 tools/test_grafics.py [/dev/cu.usbserial-XXXX]
"""
import re
import sys
import time

import serial

from comu import troba_port

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
    # Aquesta prova ja envia ella mateixa les linies 'S' (amb valors de CPU
    # concrets per omplir l'historial), aixi que NO hi posem el fil de fons:
    # les sobreescriuria.

    # Obrir el port reinicia la placa: esperem que ARRENQUI de veritat (que
    # surti el missatge de benvinguda de l'aplicacio, no el del xip).
    t0 = time.time()
    arrencada = False
    while time.time() - t0 < 10.0:
        raw = ser.readline()
        if not raw:
            continue
        if "Mac Panel" in raw.decode("utf-8", "replace"):
            arrencada = True
            break
    if not arrencada:
        print("!! la placa no ha arrencat")
        ser.close()
        return 1
    time.sleep(2.0)                    # que acabi de muntar-ho tot
    ser.reset_input_buffer()

    cpus = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    print(f">>> envio {len(cpus)} mostres de CPU: de {cpus[0]} a {cpus[-1]}")

    for c in cpus:
        line = (f"S cpu={c} mem={c // 2} disk=50 bat=80 chg=1 up=0.1 dn=0.2 "
                f"load=1.0 temp=20 wc=1 isd=1 date=01/01 wd=dl host=Test "
                f"time=12:00 uptime=100 dsp=1\n")
        ser.write(line.encode("utf-8"))
        time.sleep(0.35)

    ser.write(b"hist\n")
    t0 = time.time()
    out = []
    while time.time() - t0 < 3.0:
        raw = ser.readline()
        if not raw:
            continue
        txt = raw.decode("utf-8", "replace").rstrip()
        if txt.startswith("[HIST]"):
            out.append(txt)

    print()
    print("=== HISTORIAL A LA PLACA ===")
    for l in out:
        print("  ", l)

    cpu = next((l for l in out if "CPU" in l), None)
    if cpu is None:
        print("!! no he rebut cap linia [HIST]")
        ser.close()
        return 1

    m = re.search(r"n=\s*(\d+)\s+min=\s*([\d.]+)\s+mitjana=\s*([\d.]+)"
                  r"\s+max=\s*([\d.]+)\s+ara=\s*([\d.]+)", cpu)
    if m is None:
        print("!! no he pogut interpretar la linia de CPU")
        ser.close()
        return 1

    n, mn, av, mx, last = (int(m.group(1)), float(m.group(2)),
                           float(m.group(3)), float(m.group(4)),
                           float(m.group(5)))
    e_min, e_avg = min(cpus), sum(cpus) / len(cpus)
    e_max, e_last = max(cpus), cpus[-1]

    print()
    print(f"  placa  : n={n} min={mn} mitjana={av:.1f} max={mx} ara={last}")
    print(f"  esperat: n={len(cpus)} min={e_min} mitjana={e_avg:.1f} "
          f"max={e_max} ara={e_last}")

    ok = (n == len(cpus) and abs(mn - e_min) < 0.01
          and abs(av - e_avg) < 0.01 and abs(mx - e_max) < 0.01
          and abs(last - e_last) < 0.01)

    print()
    print("=== RESULTAT ===")
    print("historial correcte" if ok else "!! els numeros NO quadren")
    ser.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
