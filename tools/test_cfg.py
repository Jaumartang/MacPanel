#!/usr/bin/env python3
"""Prova de carrega: envia una configuracio amb 15 botons (la linia CFG mes
llarga possible) i comprova que l'ESP32 l'accepta sense trencar-se."""
import json
import sys
import time
import urllib.request

ACTS = [("media_prev", "PREV", "prev"), ("media_play", "PLAY", "play"),
        ("media_next", "NEXT", "next"), ("vol_down", "VOL-", "vol_down"),
        ("vol_up", "VOL+", "vol_up"), ("mute", "MUTE", "mute"),
        ("sys_lock", "LOCK", "lock"), ("sys_sleep", "SLEEP", "sleep"),
        ("sys_shot", "SHOT", "shot"), ("sys_dark", "DARK", "dark"),
        ("app_vscode", "VSC", ""), ("app_terminal", "TERM", "term"),
        ("app_safari", "SAFARI", ""), ("app_music", "MUSIC", ""),
        ("app_finder", "FINDER", "")]

BASE = "http://127.0.0.1:8770"


def main():
    cfg = {
        "port": "", "refresh_ms": 1000,
        "widgets": ["cpu", "mem", "disk", "bat", "net", "load", "uptime", "time", "host"],
        "buttons": [{"id": i, "label": l, "on": True, "icon": c} for (i, l, c) in ACTS],
    }
    line = "CFG " + json.dumps({"w": cfg["widgets"],
                                "b": [[i, l, c] for (i, l, c) in ACTS]},
                               separators=(",", ":"))
    print(f"mida de la linia CFG: {len(line)} bytes")

    req = urllib.request.Request(
        BASE + "/api/config",
        data=json.dumps({"config": cfg}).encode(),
        headers={"Content-Type": "application/json"})
    print("resposta:", json.load(urllib.request.urlopen(req, timeout=6)))

    time.sleep(2.5)
    st = json.load(urllib.request.urlopen(BASE + "/api/state", timeout=5))
    print("--- registre ---")
    for l in st["log"][-6:]:
        print("  ", l)
    bad = [l for l in st["log"][-8:] if "invalida" in l]
    print()
    print("RESULTAT:", "TRENCADA (bug!)" if bad else "OK - la placa ha acceptat la config")


if __name__ == "__main__":
    main()
