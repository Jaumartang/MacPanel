#!/usr/bin/env python3
"""test_inici.py - prova la pantalla d'inici i la marquesina de la capcalera.

Comprova que:
  1) a l'engegada la placa ensenya la pantalla d'inici (es veu al registre)
  2) la comanda 'splash' la torna a mostrar i deixa la interficie com estava
  3) despres de l'splash els tocs segueixen funcionant
  4) si el nom del Mac no cap a la capcalera, s'hi engega la marquesina

Us:
    python3 tools/test_inici.py [/dev/cu.usbserial-XXXX]
"""
import sys
import time

import serial

from comu import Enllac, troba_port

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

    # Obrir el port reinicia la placa: recollim el registre de l'engegada, que
    # es on surt la pantalla d'inici.
    t0 = time.time()
    while time.time() - t0 < 12.0:
        raw = ser.readline()
        if raw and b"Mac Panel" in raw:
            break

    arrencada = []
    t = time.time()
    while time.time() - t < 5.0:
        raw = ser.readline()
        if raw:
            arrencada.append(raw.decode("utf-8", "replace").rstrip())

    # La placa nomes ensenya les pantalles si te enllac: li enviem linies 'S'.
    enllac = Enllac(ser).comenca()

    def drain(sec=1.5):
        out = []
        t = time.time()
        while time.time() - t < sec:
            raw = ser.readline()
            if raw:
                out.append(raw.decode("utf-8", "replace").rstrip())
        return out

    proves = []

    # 1) A l'engegada hi surt la pantalla d'inici amb els passos de la barra.
    print("=== 1) pantalla d'inici a l'engegada ===")
    for l in arrencada:
        if "[UI] pantalla d'inici" in l or "[UI] engegant:" in l:
            print("   ", l)
    te_inici = any("[UI] pantalla d'inici" in l for l in arrencada)
    passos = sum(1 for l in arrencada if "[UI] engegant:" in l)
    print(f"   -> surt: {'SI' if te_inici else 'NO'}  ({passos} passos)")
    proves.append(("la pantalla d'inici surt a l'engegada",
                   te_inici and passos >= 4))

    # 2) La comanda 'splash' la torna a mostrar.
    print("=== 2) comanda 'splash' ===")
    enllac.envia("splash\n")
    out = drain(5.0)
    passos = [l for l in out if "[UI] engegant:" in l]
    final = any("pantalla d'inici mostrada" in l for l in out)
    for l in passos:
        print("   ", l)
    print(f"   -> es torna a mostrar i acaba: {'SI' if final else 'NO'}")
    proves.append(("la comanda 'splash' funciona", final and len(passos) >= 3))

    # 3) Despres de l'splash la interficie torna i els tocs funcionen.
    print("=== 3) despres de l'splash, boto de menu (15,15) ===")
    enllac.envia("toca 15 15\n")
    out = drain(1.5)
    m = [l for l in out if "[TEST] menu=" in l]
    obert = bool(m) and "menu=1" in m[-1]
    print(f"   -> el boto de menu obre el menu: {'SI' if obert else 'NO'}")
    proves.append(("despres de l'splash la interficie respon", obert))
    enllac.envia("toca 15 15\n")        # el tanco
    drain(1.0)

    # 4) Marquesina: amb un nom de Mac llarg, la capcalera el fa passar.
    print("=== 4) marquesina amb un nom llarg ===")
    enllac.atura()
    time.sleep(0.2)
    enllac = Enllac(ser, host="MacBook_Pro_de_Jaume_Marti_i_Maria_Mac").comenca()
    out = drain(4.0)
    marq = [l for l in out if "[UI] capcalera:" in l]
    for l in marq:
        print("   ", l)
    print(f"   -> s'hi engega la marquesina: {'SI' if marq else 'NO'}"
          f"  ({len(marq)} cops)")
    proves.append(("un nom llarg fa marquesina", bool(marq)))
    # Nomes s'ha d'engegar quan arriba el nom: si es reinicies a cada linia
    # d'estadistiques, la passada no s'acabaria mai (passa si l'hora canvia de
    # mida i la zona es recalcula).
    proves.append(("la marquesina no es reinicia tota l'estona", len(marq) <= 2))

    # 5) Amb la marquesina en marxa, la placa segueix responent de seguida.
    print("=== 5) la placa respon amb la marquesina en marxa ===")
    t0 = time.time()
    enllac.envia("info\n")
    viu = False
    while time.time() - t0 < 2.0:
        raw = ser.readline()
        if raw and b"[SYS] chip=" in raw:
            viu = True
            break
    print(f"   -> respon: {'SI' if viu else 'NO'} ({time.time() - t0:.2f} s)")
    proves.append(("la placa respon amb la marquesina en marxa", viu))

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
