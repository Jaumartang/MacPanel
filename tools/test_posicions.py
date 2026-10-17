#!/usr/bin/env python3
"""test_posicions.py - prova que la placa respecta la posicio fixa d'un boto.

L'editor visual pot fixar un boto en una casella de la graella. Aixo viatja a la
placa com a cinque camp del boto ("col,row,w,h") i el firmware l'ha de complir:
el boto ha de caure exactament a la casella demanada i, si n'ocupa mes d'una,
ha de ser mes ample o mes alt.

Tambe comprova que, si es treu la posicio, tot torna a repartir-se sol (es a
dir, que no hem trencat el comportament de sempre).

Cal el pont engegat (mac/panel_server.py).

Us:
    python3 tools/test_posicions.py
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


def desa(cfg):
    """Desa la configuracio i dona temps a la placa d'aplicar-la.

    Sense aquesta espera, la comanda 'botons' pot arribar a la placa abans que
    hagi processat la configuracio nova i respondria amb la geometria VELLA: la
    prova fallaria tot i que el firmware ho fa be.
    """
    r = post("/api/config", {"config": cfg})
    time.sleep(2.0)
    return r


def botons():
    """Demana la geometria a la placa i la torna com a [(x0,x1,y0,y1,label)].

    Les linies es busquen DESPRES del marcatge de la comanda: si nomes es mira
    una finestra de temps, les respostes de dues comandes seguides es barregen i
    la prova dona resultats d'una altra tirada.
    """
    post("/api/board", {"cmd": "botons"})
    reixa = []
    for _ in range(12):
        time.sleep(1.0)
        log = get("/api/state").get("log") or []
        # La marca de la comanda i el que ve despres (fins a la propera comanda).
        idx = None
        for i in range(len(log) - 1, -1, -1):
            if "comanda de placa: botons" in log[i]:
                idx = i
                break
        if idx is None:
            continue
        trossos = []
        for l in log[idx + 1:]:
            if "comanda de placa:" in l:
                break
            trossos.append(l)
        for l in trossos:
            m = re.search(r"\[BTN\]\s+\d+\s+x=\s*(\d+)\.\.\s*(\d+)\s+y=\s*(\d+)\.\.\s*(\d+)\s+'(.*)'", l)
            if m:
                reixa.append(tuple(int(m.group(i)) for i in (1, 2, 3, 4)) + (m.group(5),))
        if len(reixa) >= 3:
            return reixa, trossos
    return reixa, []


def comprova(nom, condicio, detall=""):
    if condicio:
        print("  ok    %s" % nom)
    else:
        print("  FALLA %s  %s" % (nom, detall))
        fallades.append(nom)


def main():
    est = get("/api/state")
    if not est.get("connected"):
        print("El pont ha d'estar connectat a la placa.")
        return 2
    original = json.loads(json.dumps(est["config"]))
    cfg = json.loads(json.dumps(original))
    pg = cfg["pages"][0]

    # IMPORTANT: la placa nomes rep els botons ACTIVATS (el pont en salta els
    # que tenen `on: false`), aixi que les posicions s'han de provar sobre
    # aquests. Es un error facil de cometre i fa que la prova passi sense
    # provar res.
    actius = [b for b in pg["buttons"] if b.get("on", True)]
    if len(actius) < 3:
        print("Calen almenys 3 botons activats a la primera pantalla.")
        return 2

    try:
        print("A) sense posicions fixes: el repartiment de sempre")
        for b in pg["buttons"]:
            b.pop("pos", None)
        desa(cfg)
        reixa, _ = botons()
        comprova("la placa respon amb la graella", len(reixa) == len(actius),
                 "%d botons a la placa, %d activats" % (len(reixa), len(actius)))
        if len(reixa) < 3:
            return 1
        base = reixa[0]
        comprova("el primer boto es a l'esquerra",
                 base[0] <= 8, "x0=%d" % base[0])
        amplada = base[1] - base[0] + 1
        comprova("l'amplada es la d'una casella",
                 amplada > 60, "amplada=%d" % amplada)
        comprova("el segon boto es mes a la dreta",
                 reixa[1][0] > base[0] + 20,
                 "x0=%d vs %d" % (reixa[1][0], base[0]))

        print("B) el segon boto activat, fixat a la columna 2")
        actius[1]["pos"] = {"col": 2, "row": 0, "w": 1, "h": 1}
        desa(cfg)
        reixa, _ = botons()
        b1 = reixa[1]
        comprova("ha anat a la dreta de tot", b1[0] > base[0] + 150,
                 "x0=%d (el primer es a %d)" % (b1[0], base[0]))
        comprova("te la mateixa mida",
                 abs((b1[1] - b1[0]) - (base[1] - base[0])) <= 2,
                 "%d vs %d" % (b1[1] - b1[0], base[1] - base[0]))
        comprova("es a la primera fila", b1[2] == base[2],
                 "y=%d vs %d" % (b1[2], base[2]))

        print("C) el primer boto activat, fixat a la fila 1")
        actius[0]["pos"] = {"col": 0, "row": 1, "w": 1, "h": 1}
        desa(cfg)
        reixa, _ = botons()
        b0 = reixa[0]
        # Amb dues files, el conjunt puja per fer-hi lloc: el que importa es que
        # aquest boto quedi MES AVALL que els altres, no el valor absolut de y.
        comprova("ha baixat de fila", b0[2] > reixa[1][2] + 20,
                 "y=%d vs y=%d del segon" % (b0[2], reixa[1][2]))
        comprova("segueix a l'esquerra", b0[0] <= 8, "x0=%d" % b0[0])

        print("D) un boto que ocupa dues caselles")
        actius[0]["pos"] = {"col": 0, "row": 0, "w": 2, "h": 1}
        desa(cfg)
        reixa, _ = botons()
        b0 = reixa[0]
        ample = b0[1] - b0[0] + 1
        comprova("es mes ample que una casella", ample > amplada + 40,
                 "amplada=%d vs %d" % (ample, amplada))

        print("E) un boto alt (dues files)")
        actius[0]["pos"] = {"col": 0, "row": 0, "w": 1, "h": 2}
        desa(cfg)
        reixa, _ = botons()
        b0 = reixa[0]
        alt = b0[3] - b0[2] + 1
        comprova("es mes alt", alt > (base[3] - base[2] + 1) + 20,
                 "alcada=%d vs %d" % (alt, base[3] - base[2] + 1))

        print("F) tornant a treure la posicio, es reparteix sol")
        for b in pg["buttons"]:
            b.pop("pos", None)
        desa(cfg)
        reixa, _ = botons()
        comprova("torna a la casella d'abans",
                 abs(reixa[0][0] - base[0]) <= 2 and abs(reixa[0][2] - base[2]) <= 2,
                 "x=%d y=%d vs x=%d y=%d" % (reixa[0][0], reixa[0][2], base[0], base[2]))
    finally:
        desa(original)
        print("configuracio original restaurada")

    print()
    if fallades:
        print("=== HI HA %d PROBLEMES: %s ===" % (len(fallades), ", ".join(fallades)))
        return 1
    print("=== TOT OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
