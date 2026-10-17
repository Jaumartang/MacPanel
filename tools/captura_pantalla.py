#!/usr/bin/env python3
"""captura_pantalla.py - Captura la pantalla de la placa (com a PNG).

La placa te una comanda de consola 'captura' que llegeix la pantalla i l'envia
en base64 (RGB565), per franges. Aquesta eina ho recull i ho desa com a PNG:
es la manera de veure de debò com queda la pantalla (colors, fonts, mides,
textos tallats...) sense haver-la de fotografiar.

Mentrestant va enviant linies 'S' perque la placa no trobi a faltar el Mac i no
se'n vagi a la pantalla de "sense enllac" (que es el que sortiria a la captura).

Us:
    python3 tools/captura_pantalla.py [pagina] [sortida.png]

IMPORTANT: el pont (panel_server.py) ha d'estar ATURAT. La placa envia ~400 KB
en una sola comanda i, si el pont tambe hi escriu (estadistiques, icones...),
les linies de la captura es perden.
"""
import base64
import os
import re
import struct
import sys
import threading
import time

import serial

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from comu import troba_port
except Exception:                       # l'eina tambe ha de funcionar sola
    def troba_port():
        return "/dev/cu.usbserial-1420"

from PIL import Image

PORT = os.environ.get("MACPANEL_PORT") or troba_port() or "/dev/cu.usbserial-1420"

# Una linia d'estadistiques creible: sense 'idl' el Mac no es "inactiu" i la
# placa no se'n va a la pantalla de rellotge. El 'host' es llarg a posta, perque
# surti la marquesina de la capcalera (que es el que volem comprovar).
STATS = ("S cpu=12.5 mem=42 disk=61 bat=88 chg=1 up=1.2 dn=0.3 load=1.8 "
         "host=MacBook_Pro_de_Jaume time=12:00 uptime=8040 dsp=1 idl=0")


def obre_port(port, intents=5):
    """Obre el port amb paciencia.

    El CH340 d'aquesta placa es re-enumera de tant en tant (i aleshores
    qualsevol operacio falla amb 'Device not configured'). Tambe evitem tocar
    DTR/RTS: en aquesta placa el circuit auto-reset fa reiniciar l'ESP32 i, si
    ho fem just en obrir, el port es queda penjat.
    """
    ultim = None
    for _ in range(intents):
        try:
            ser = serial.Serial(port, 115200, timeout=1.0)
            try:
                ser.reset_input_buffer()
            except Exception:
                ser.close()
                raise
            time.sleep(0.4)
            return ser
        except Exception as exc:
            ultim = exc
            time.sleep(2.5)
    raise SystemExit("no s'ha pogut obrir %s: %s" % (port, ultim))


def manté_enllac(ser, fi):
    """Envia estadistiques cada 2 s fins que 'fi' es cert."""
    while not fi[0]:
        try:
            ser.write((STATS + "\n").encode())
        except Exception:
            return
        time.sleep(2.0)


def captura(port, pagina=None):
    ser = obre_port(port)

    fi = [False]
    threading.Thread(target=manté_enllac, args=(ser, fi), daemon=True).start()

    time.sleep(1.0)
    if pagina is not None:
        ser.write(("page %d\n" % pagina).encode())
        time.sleep(1.5)
    time.sleep(2.0)

    ser.reset_input_buffer()
    ser.write(b"captura\n")

    caps = {}
    mida = None
    fi_lectura = time.time() + 120
    while time.time() < fi_lectura:
        try:
            linia = ser.readline().decode("utf-8", "replace").strip()
        except Exception as exc:
            print("avís: lectura fallida (%s), reintento..." % exc)
            try:
                ser.close()
            except Exception:
                pass
            time.sleep(2.0)
            ser = obre_port(port)
            fi_lectura = time.time() + 120
            continue
        if not linia:
            continue
        if linia.startswith("[SHOT] "):
            cos = linia[7:]
            if cos == "FI":
                break
            parts = cos.split()
            if len(parts) == 3 and all(p.isdigit() for p in parts):
                mida = tuple(int(p) for p in parts)
            elif len(parts) == 2:
                try:
                    caps[int(parts[0])] = parts[1]
                except ValueError:
                    pass

    fi[0] = True
    try:
        ser.close()
    except Exception:
        pass

    if mida is None or not caps:
        raise SystemExit("no s'ha rebut cap captura (la placa respon?)")
    W, H, franges = mida
    print("captura: %dx%d, %d franges, %d rebudes" % (W, H, franges, len(caps)))

    dades = bytearray()
    for f in range(franges):
        if f not in caps:
            raise SystemExit("falta la frange %d" % f)
        try:
            dades += base64.b64decode(caps[f], validate=True)
        except Exception as exc:
            raise SystemExit("frange %d corrupta (%s)" % (f, exc))
    if len(dades) < W * H * 2:
        raise SystemExit("falten dades: %d bytes de %d" % (len(dades), W * H * 2))

    im = Image.new("RGB", (W, H))
    px = im.load()
    for i in range(W * H):
        v = struct.unpack_from(">H", dades, i * 2)[0]
        px[i % W, i // W] = (((v >> 11) & 0x1F) * 255 // 31,
                             ((v >> 5) & 0x3F) * 255 // 63,
                             (v & 0x1F) * 255 // 31)
    return im


def main():
    pagina = None
    sortida = "/tmp/pantalla.png"
    args = sys.argv[1:]
    if args and args[0].isdigit():
        pagina = int(args.pop(0))
    if args:
        sortida = args.pop(0)
    # El port serie no es perfecte: si una frange arriba tallada, es torna a
    # provar. Al cap de tres intents ja no insistim.
    for intent in range(3):
        try:
            im = captura(PORT, pagina)
            im.save(sortida)
            print("desat", sortida, im.size)
            return
        except SystemExit as exc:
            print("intent %d fallit: %s" % (intent + 1, exc))
            time.sleep(2.5)
    raise SystemExit("no s'ha pogut capturar la pantalla")


if __name__ == "__main__":
    main()
