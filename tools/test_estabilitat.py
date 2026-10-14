#!/usr/bin/env python3
"""test_estabilitat.py - comprova que la placa no es reinicia.

Fa enviaments de configuracio repetits (que es el cas mes exigent: la placa ha
de rellegir el JSON amb el Bluetooth ences) i vigila el registre per si hi ha
algun reinici o crash.
"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8770"


def state():
    with urllib.request.urlopen(BASE + "/api/state", timeout=8) as fh:
        return json.load(fh)


def send_config():
    req = urllib.request.Request(BASE + "/api/send", data=b"{}",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as fh:
        return json.load(fh)


def main():
    d = state()
    print(f"connectat: {d['connected']}  |  port: {d['port']}")
    abans = len(d["log"])

    # Enviem la configuracio unes quantes vegades, amb el Bluetooth ja ences.
    for i in range(1, 7):
        print(f"  enviament {i}: {send_config()}")
        time.sleep(15)

    d = state()
    log = d["log"][abans:]
    reboots = [l for l in log
               if "abort()" in l or "Rebooting" in l or "rst:0x" in l]
    errors = [l for l in log if "no hi ha memoria" in l or "invalida" in l]

    print()
    print("=== RESULTAT ===")
    print(f"reinicis/crashes : {len(reboots)}")
    print(f"errors de config : {len(errors)}")
    for l in reboots[:8]:
        print("   ", l)
    for l in errors[:8]:
        print("   ", l)
    print()
    print("ultimes linies:")
    for l in d["log"][-10:]:
        print("   ", l)


if __name__ == "__main__":
    main()
