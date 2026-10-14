#!/usr/bin/env python3
"""test_menu.py - prova el menu de pantalles simulant tocs.

Fa servir la comanda de consola 'toca x y' (que simula un toc: prem i aixeca)
per comprovar que el menu s'obre i ES QUEDA obert, que es tanca en triar una
pantalla i que es tanca tocant fora.

Us:
    python3 tools/test_menu.py [/dev/cu.usbserial-XXXX]
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
    # La placa nomes ensenya les pantalles si te enllac: li enviem linies 'S'.
    enllac = Enllac(ser).comenca()

    # Obrir el port reinicia la placa: esperem que arrenqui de veritat.
    t0 = time.time()
    while time.time() - t0 < 10.0:
        raw = ser.readline()
        if raw and b"Mac Panel" in raw:
            break
    time.sleep(2.0)
    ser.reset_input_buffer()

    def drain(sec=1.4):
        out = []
        t = time.time()
        while time.time() - t < sec:
            raw = ser.readline()
            if raw:
                out.append(raw.decode("utf-8", "replace").rstrip())
        return out

    # La placa nomes ensenya les pantalles si te enllac. Si comencem a tocar
    # abans que l'hagi detectat, el menu nomes te la fila 'Ajustos' i no hi ha
    # cap pantalla a triar. (Amb la pantalla d'inici, l'arrencada dura una mica
    # mes, aixi que aquesta espera es necessaria.)
    t0 = time.time()
    while time.time() - t0 < 8.0:
        enllac.envia("info\n")
        if any("link=1" in l for l in drain(0.7)):
            break
    ser.reset_input_buffer()

    def toca(x, y):
        enllac.envia(f"toca {x} {y}\n")
        return drain()

    def llisca(x1, y1, x2, y2):
        enllac.envia(f"llisca {x1} {y1} {x2} {y2}\n")
        return drain(2.2)

    proves = []

    # 1) Obrir el menu amb el boto ☰ (a dalt a l'esquerra).
    print("=== 1) toco el boto de menu (15,15) ===")
    out = toca(15, 15)
    for l in out:
        if "[TEST]" in l:
            print("   ", l)
    m = [l for l in out if "[TEST] menu=" in l]
    obert = bool(m) and "menu=1" in m[-1]
    print(f"   -> s'obre i ES QUEDA obert: {'SI' if obert else 'NO'}")
    proves.append(("obre el menu i es queda obert", obert))

    # 2) Triar una pantalla (una fila del menu).
    print("=== 2) toco una fila del menu (200,110) ===")
    out = toca(200, 110)
    for l in out:
        if "[TEST]" in l:
            print("   ", l)
    m = [l for l in out if "[TEST] menu=" in l]
    tancat = bool(m) and "menu=0" in m[-1]
    print(f"   -> es tanca en triar: {'SI' if tancat else 'NO'}")
    proves.append(("es tanca en triar una pantalla", tancat))

    # 3) Tornar a obrir i tancar tocant la capcalera (fora de les files).
    print("=== 3) obro i toco la capcalera (200,15) ===")
    toca(15, 15)
    out = toca(200, 15)
    for l in out:
        if "[TEST]" in l:
            print("   ", l)
    m = [l for l in out if "[TEST] menu=" in l]
    tancat2 = bool(m) and "menu=0" in m[-1]
    print(f"   -> es tanca tocant fora: {'SI' if tancat2 else 'NO'}")
    proves.append(("es tanca tocant la capcalera", tancat2))

    # 4) Arrossegar dins del menu = fer scroll, no tancar-lo ni triar res.
    print("=== 4) obro el menu i l'arrossego (scroll) ===")
    toca(15, 15)
    out = llisca(200, 350, 200, 120)
    for l in out:
        if "[TEST]" in l:
            print("   ", l)
    m = [l for l in out if "[TEST] menu=" in l]
    segueix = bool(m) and "menu=1" in m[-1]
    print(f"   -> despres d'arrossegar segueix obert: {'SI' if segueix else 'NO'}")
    proves.append(("arrossegar fa scroll i no tanca", segueix))

    # 5) Les pestanyes del menu: Ajustos i Sobre.
    # La posicio de les pestanyes depen de l'amplada, aixi que la mirem.
    enllac.envia("cfg\n")
    ori = "v"
    for l in drain(1.2):
        if "orientacio=" in l:
            ori = l.split("orientacio=")[1].split()[0]
    W = 480 if ori[:1] == "h" else 320
    tabx = [W * (2 * i + 1) // 6 for i in range(3)]
    print(f"=== 5) pestanya 'Ajustos' (orientacio {ori}, x={tabx[1]}) ===")
    out = toca(tabx[1], 46)
    tab = [l for l in out if "menu:" in l]
    for l in tab:
        print("   ", l)
    ok_tab = any("Ajustos" in l for l in tab)
    proves.append(("la pestanya 'Ajustos' s'obre", ok_tab))

    # 6) Una fila d'ajustos canvia el valor (la segona es el tema).
    print("=== 6) toco la fila 'Tema' ===")
    out = toca(W // 2, 110)
    canvi = [l for l in out if "[UI] tema" in l]
    for l in canvi:
        print("   ", l)
    print(f"   -> ha canviat el tema: {'SI' if canvi else 'NO'}")
    proves.append(("una fila d'ajustos canvia el valor", bool(canvi)))

    print(f"=== 7) pestanya 'Sobre' (x={tabx[2]}) ===")
    out = toca(tabx[2], 46)
    tab = [l for l in out if "menu:" in l]
    for l in tab:
        print("   ", l)
    ok_sobre = any("Sobre" in l for l in tab)
    proves.append(("la pestanya 'Sobre' s'obre", ok_sobre))

    print("=== 8) ajustos nous des de la consola ===")
    enllac.envia("ajust idle\n")
    out = drain(1.4)
    idle = [l for l in out if "rellotge si inactiu" in l]
    for l in idle:
        print("   ", l)
    proves.append(("l'ajust del rellotge funciona", bool(idle)))
    enllac.envia("ajust nav\n")
    out = drain(1.4)
    nav = [l for l in out if "navegacio ->" in l]
    for l in nav:
        print("   ", l)
    proves.append(("l'ajust de navegacio funciona", bool(nav)))

    toca(15, 15)                      # tanco el menu

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
