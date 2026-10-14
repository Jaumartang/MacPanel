#!/usr/bin/env python3
"""canvia_orientacio.py - canvia la orientacio (v/h) des de la linia d'ordres.

Us:
    python3 tools/canvia_orientacio.py h
    python3 tools/canvia_orientacio.py v
"""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8770"


def main():
    o = (sys.argv[1] if len(sys.argv) > 1 else "h").lower()[:1]
    o = "h" if o == "h" else "v"

    with urllib.request.urlopen(BASE + "/api/state", timeout=8) as fh:
        cfg = json.load(fh)["config"]
    cfg["orientation"] = o

    req = urllib.request.Request(
        BASE + "/api/config",
        data=json.dumps({"config": cfg}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as fh:
        res = json.load(fh)
    print(f"orientacio -> {o} | enviat: {res.get('sent')}")


if __name__ == "__main__":
    main()
