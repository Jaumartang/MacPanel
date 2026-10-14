#!/usr/bin/env python3
"""test_icon_upload.py - Prova: genera un PNG al vol i el puja a la SD de la placa.

Fa servir el mateix endpoint que el panell de control (/api/icon).
"""

import base64
import io
import json
import urllib.request

from PIL import Image, ImageDraw

BASE = "http://127.0.0.1:8770"


def main():
    # Una cara somrient, fons transparent
    im = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([24, 24, 232, 232], fill=(255, 205, 40, 255))
    d.ellipse([88, 84, 124, 124], fill=(30, 30, 30, 255))
    d.ellipse([132, 84, 168, 124], fill=(30, 30, 30, 255))
    d.arc([76, 104, 180, 196], 20, 160, fill=(30, 30, 30, 255), width=16)

    buf = io.BytesIO()
    im.save(buf, "PNG")
    png_b64 = base64.b64encode(buf.getvalue()).decode()

    req = urllib.request.Request(
        BASE + "/api/icon",
        data=json.dumps({"name": "prova_smile", "png": png_b64}).encode(),
        headers={"Content-Type": "application/json"})
    print("resposta:", json.load(urllib.request.urlopen(req, timeout=40)))

    import time
    time.sleep(2)
    st = json.load(urllib.request.urlopen(BASE + "/api/state", timeout=5))
    print("--- registre ---")
    for l in st["log"][-8:]:
        print("  ", l)


if __name__ == "__main__":
    main()
