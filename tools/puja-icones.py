#!/usr/bin/env python3
"""puja-icones.py - Puja totes les icones de Assets/icons a la SD de la placa.

Fa servir el mateix endpoint que el panell de control (/api/icon): el Mac les
converteix i les escriu a la SD de l'ESP32 pel port serie.

Us:  python3 tools/puja-icones.py
"""

import base64
import json
import os
import urllib.request

BASE = "http://127.0.0.1:8770"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "Assets", "icons")


def main():
    if not os.path.isdir(SRC):
        print("No existeix la carpeta:", SRC)
        return
    pngs = sorted(f for f in os.listdir(SRC) if f.lower().endswith(".png"))
    if not pngs:
        print("No hi ha cap PNG a", SRC)
        return

    ok = 0
    for f in pngs:
        name = os.path.splitext(f)[0]
        with open(os.path.join(SRC, f), "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        req = urllib.request.Request(
            BASE + "/api/icon",
            data=json.dumps({"name": name, "png": b64}).encode(),
            headers={"Content-Type": "application/json"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=40))
            if r.get("ok"):
                print(f"  OK   {name}")
                ok += 1
            else:
                print(f"  ERR  {name}: {r.get('error')}")
        except Exception as exc:
            print(f"  ERR  {name}: {exc}")

    print(f"\n{ok}/{len(pngs)} icones pujades a la placa.")


if __name__ == "__main__":
    main()
