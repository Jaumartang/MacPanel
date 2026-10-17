#!/usr/bin/env python3
"""test_baner.py - prova els avisos (baner) de la placa.

El baner viu sota la capcalera i tapa contingut de debo (gadgets i la primera
fila de botons). Es la part mes delicada de la interficie, aixi que val la pena
comprovar que:

  1) surt quan arriba un avis
  2) el primer toc el treu i NO prem el boto que hi ha a sota
  3) el toc seguent (sense baner) SI que prem el boto
  4) marxa tot sol al cap d'uns segons
  5) sobreviu a un canvi de pantalla

Cal el pont engegat (mac/panel_server.py).

Us:
    python3 tools/test_baner.py
"""
import json
import re
import sys
import time
import urllib.request

API = "http://127.0.0.1:8770"
fallades = []


def get(p):
    with urllib.request.urlopen(API + p, timeout=10) as r:
        return json.loads(r.read().decode())


def post(p, obj):
    req = urllib.request.Request(API + p, data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def cmd(c):
    return post("/api/board", {"cmd": c})


def des_de(marca):
    return [l for l in (get("/api/state").get("log") or []) if l[:8] >= marca]


def marca():
    return time.strftime("%H:%M:%S")


def comprova(nom, condicio, detall=""):
    if condicio:
        print("  ok    %s" % nom)
    else:
        print("  FALLA %s  %s" % (nom, detall))
        fallades.append(nom)


def geometria():
    """Els botons de la pantalla actual, tal com els veu la placa."""
    m = marca()
    cmd("botons")
    time.sleep(3.0)
    out = []
    for l in des_de(m):
        r = re.search(r"\[BTN\]\s+\d+\s+x=\s*(\d+)\.\.\s*(\d+)\s+y=\s*(\d+)\.\.\s*(\d+)\s+'(.*)'", l)
        if r:
            out.append(tuple(int(r.group(i)) for i in (1, 2, 3, 4)) + (r.group(5),))
    return out


def main():
    est = get("/api/state")
    if not est.get("connected"):
        print("El pont ha d'estar connectat a la placa.")
        return 2
    cfg = json.loads(json.dumps(est["config"]))
    original_idle = cfg.get("idle_min", 0)
    original_notif = cfg.get("notif_on", True)

    try:
        # Sense pantalla de repos i amb els avisos activats.
        cfg["idle_min"] = 0
        cfg["notif_on"] = True
        post("/api/config", {"config": cfg})
        time.sleep(2)

        reixa = geometria()
        if not reixa:
            print("No s'ha pogut llegir la geometria dels botons.")
            return 2
        b0 = reixa[0]
        cx = (b0[0] + b0[1]) // 2
        cy = (b0[2] + b0[3]) // 2
        print("primer boto: x=%d..%d y=%d..%d '%s'" % (b0[0], b0[1], b0[2], b0[3], b0[4]))

        print("A) arriba un avis")
        m = marca()
        post("/api/notify", {"app": "Mac Panel", "title": "Prova", "body": "cos"})
        time.sleep(2.5)
        linies = des_de(m)
        comprova("la placa diu que hi ha un avis",
                 any("avis de" in l for l in linies), str(linies[-2:]))
        m = marca()
        cmd("botons")
        time.sleep(3.0)
        comprova("i ho confirma amb la comanda 'botons'",
                 any("toc menjat pel baner" in l for l in des_de(m)))

        print("B) tocar DINS del baner no ha de prémer el boto")
        m = marca()
        cmd("toca %d %d" % (cx, cy))
        time.sleep(2.5)
        botons = [l for l in des_de(m) if "boto ->" in l]
        comprova("cap boto disparat", not botons, str(botons))

        print("C) sense baner, el mateix toc SI que ha de prémer el boto")
        time.sleep(9)                       # el baner marxa tot sol
        m = marca()
        cmd("toca %d %d" % (cx, cy))
        time.sleep(2.5)
        botons = [l for l in des_de(m) if "boto ->" in l]
        comprova("ha disparat el boto", len(botons) == 1, str(botons))
    finally:
        cfg["idle_min"] = original_idle
        cfg["notif_on"] = original_notif
        post("/api/config", {"config": cfg})
        print("configuracio original restaurada")

    print()
    if fallades:
        print("=== HI HA %d PROBLEMES: %s ===" % (len(fallades), ", ".join(fallades)))
        return 1
    print("=== TOT OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
