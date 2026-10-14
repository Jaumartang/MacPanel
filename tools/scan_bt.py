#!/usr/bin/env python3
"""scan_bt.py - Escaneja dispositius Bluetooth per comprovar que l'ESP32
anuncia el teclat 'Mac Panel'.

Us:  python3 tools/scan_bt.py
Requisit: pip install bleak
"""

import asyncio
import sys

try:
    from bleak import BleakScanner
except ImportError:
    print("Cal bleak:  python3 -m pip install bleak")
    sys.exit(1)


async def main():
    print("escannejant 8 segons...")
    devs = await BleakScanner.discover(timeout=8.0)
    trobat = False
    for d in devs:
        nom = d.name or "(sense nom)"
        print(f"  {nom:32} {d.address}")
        if "mac panel" in nom.lower():
            trobat = True
    print("---")
    print("RESULTAT:", "'Mac Panel' ANUNCIA correctament!" if trobat
          else "'Mac Panel' NO s'ha trobat (comprova que la placa estigui encesa)")


if __name__ == "__main__":
    asyncio.run(main())
