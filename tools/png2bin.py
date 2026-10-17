#!/usr/bin/env python3
"""
png2bin.py - Converteix els PNG de Assets/icons a .bin RGB565 (big-endian) per a
la SD de l'ESP32.

Cada PNG es converteix a ICON_PX x ICON_PX (32x32, 2048 bytes) amb fons
transparent 0xF81F. Les vores es resolen amb un llindar d'alfa net (el firmware
pinta el transparent amb el color del boto) i l'RGB porta un tramat Bayer
lleuger per evitar bandes.
El resultat es desa a Assets/icons/bin/<nom>.bin.

Hi ha DOS tipus d'icona i es tracten diferent:

  * SIMBOL (wifi, volum, llum, play...): un dibuix sobre un fons pla. Es treu el
    fons perque sobre el boto quedi nomes el dibuix.
      1. Si el PNG te canal alfa, l'usa.
      2. Si no, fa un FLOOD FILL des de les vores: elimina els pixels
         connectats a la vora que s'assemblen al color del marc.

  * ICONA D'APP (Finder, Notes, Chrome...): un quadre arrodonit amb fons propi,
    amb el dibuix fins a les vores. Aqui el flood fill faria un desastre (a
    Notes li quedaria nomes la tira groga, a TextEdit nomes la ploma). Aquestes
    es converteixen SENCERES i nomes se'ls arrodoneixen les cantonades, com fa
    el macOS. Qui es qui ho diu Assets/icons/apps.txt.

Us:
    python3 tools/png2bin.py                 # tots els PNG de Assets/icons
    python3 tools/png2bin.py <fitxer.png>    # un de concret

Requisit: Pillow  (python3 -m pip install Pillow)
"""

import io
import os
import sys
from collections import deque

try:
    from PIL import Image, ImageChops, ImageDraw
except ImportError:
    Image = None      # es comprova a main(): aixi es pot importar sense Pillow

SIZE = 32                  # mida dels .bin (ha de coincidir amb ICON_PX)
TRANS = 0xF81F            # magenta = color transparent que enten el firmware
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "Assets", "icons")
OUT_DIR = os.path.join(SRC_DIR, "bin")
APPS_FILE = os.path.join(SRC_DIR, "apps.txt")

# Radi de les cantonades de les icones d'app, en proporcio del costat. El macOS
# fa servir mes o menys aquesta mida (a 32 px son ~7 px de radi).
RADI_CANTONADA = 0.225


def app_icons():
    """Noms (en minuscules) de les icones que son icones d'app, segons apps.txt."""
    noms = set()
    if not os.path.isfile(APPS_FILE):
        return noms
    with open(APPS_FILE, "r", encoding="utf-8") as fh:
        for linia in fh:
            linia = linia.split("#", 1)[0].strip().lower()
            if linia:
                noms.add(linia)
    return noms


def cantonades_rodones(im, radi=RADI_CANTONADA):
    """Fa transparent les cantonades, com les icones del macOS.

    La mascara es dibuixa 4 cops mes gran i despres s'encongeix: aixi les
    cantonades queden suaus i no amb dents de serra.
    """
    w, h = im.size
    ss = 4
    mask = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, w * ss - 1, h * ss - 1],
        radius=int(min(w, h) * ss * radi), fill=255)
    mask = mask.resize((w, h), Image.LANCZOS)

    out = im.convert("RGBA")
    out.putalpha(ImageChops.darker(out.getchannel("A"), mask))
    return out


def _es_dibuix_pla(im):
    """Te poques tonalitats? Llavors es un dibuix/logo pla (i no pas una imatge
    amb degradats ni un favicon borros, que en tenen moltes)."""
    return im.convert("RGB").getcolors(maxcolors=64) is not None


def escala_neta(im, size):
    """Redimensiona a size x size amb la MILLOR qualitat possible.

    - Ja hi es: no es toca (1:1).
    - Dibuix pla que s'amplia (un simbol de 16 px): NEAREST, que replica els
      pixels exactes i queda nitid, sense interpolacio.
    - Qualsevol altre cas (favicon borros, foto, o qualsevol reduccio):
      LANCZOS amb PREMULTIPLICACIO d'alfa.

    Per que la premultiplicacio: els PNG dels simbols tenen els pixels
    transparents amb RGB=(0,0,0). Si es redueix l'RGBA tal qual, aquest negre es
    barreja amb el dibuix i les vores surten GRISES en lloc de blanques (aixo
    era part del que feia que les icones es veiessin malament).
    """
    im = im.convert("RGBA")
    w, h = im.size
    if w == size and h == size:
        return im
    if w <= size and h <= size and _es_dibuix_pla(im):
        return im.resize((size, size), Image.NEAREST)
    return _escala_alfa(im, size)


def _escala_alfa(im, size):
    """LANCZOS amb premultiplicacio d'alfa (vores sense halo gris)."""
    r, g, b, a = im.split()
    pre = Image.merge("RGBA", (ImageChops.multiply(r, a),
                               ImageChops.multiply(g, a),
                               ImageChops.multiply(b, a), a))
    small = pre.resize((size, size), Image.LANCZOS)

    # Des-premultiplica: RGB = premult / alfa (recupera el color de debo).
    sp = small.load()
    for y in range(size):
        for x in range(size):
            pr, pg, pb, pa = sp[x, y]
            if pa == 0:
                sp[x, y] = (0, 0, 0, 0)
            elif pa < 255:
                f = 255.0 / pa
                sp[x, y] = (min(255, int(pr * f + 0.5)),
                            min(255, int(pg * f + 0.5)),
                            min(255, int(pb * f + 0.5)), pa)
    return small


def rgb565(r, g, b):
    r = 0 if r < 0 else (255 if r > 255 else int(r))
    g = 0 if g < 0 else (255 if g > 255 else int(g))
    b = 0 if b < 0 else (255 if b > 255 else int(b))
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def has_alpha(im):
    """El PNG te alfa 'de veritat' (alguna cosa transparent)?"""
    if im.mode not in ("RGBA", "LA", "P"):
        return False
    return im.convert("RGBA").getchannel("A").getextrema()[0] < 250


def bg_mask(im):
    """Mascara del fons (1 = fons) fent flood fill des de les vores.

    Nomes es considera fons el que s'assembla al color de la vora. NO es fa
    servir cap regla de "pixel gris = fons": amb un fons gris i una icona
    grisa (com la del Bluetooth) aquella regla s'empassava la icona sencera.

    Retorna (mascara, color_de_fons).
    """
    w, h = im.size
    px = im.load()

    # Color de fons = mediana dels pixels del marc (es mes robust que les
    # quatre cantonades, que poden caure en un racó amb un dibuix).
    samples = []
    for x in range(w):
        for y in (0, 1, h - 2, h - 1):
            samples.append(px[x, y])
    for y in range(h):
        for x in (0, 1, w - 2, w - 1):
            samples.append(px[x, y])
    samples.sort(key=lambda c: c[0] + c[1] + c[2])
    br, bgc, bb = samples[len(samples) // 2]

    def is_bg(r, g, b, pr, pg, pb):
        # Semblant al pixel del costat (aixi funciona amb fons amb DEGRADAT,
        # que amb una comparacio contra un color fix es tallava a mitges)...
        if abs(r - pr) + abs(g - pg) + abs(b - pb) >= 35:
            return False
        # ...i sense allunyar-se massa del color de fons general (aixo evita
        # que s'escoli cap a dins de la icona).
        return abs(r - br) + abs(g - bgc) + abs(b - bb) < 150

    mask = bytearray(w * h)
    q = deque()

    def push(x, y, pr, pg, pb):
        q.append((x, y, pr, pg, pb))

    for x in range(w):
        push(x, 0, br, bgc, bb)
        push(x, h - 1, br, bgc, bb)
    for y in range(h):
        push(0, y, br, bgc, bb)
        push(w - 1, y, br, bgc, bb)

    while q:
        x, y, pr, pg, pb = q.popleft()
        i = y * w + x
        if mask[i]:
            continue
        r, g, b = px[x, y]
        if not is_bg(r, g, b, pr, pg, pb):
            continue
        mask[i] = 1
        if x > 0:
            push(x - 1, y, r, g, b)
        if x < w - 1:
            push(x + 1, y, r, g, b)
        if y > 0:
            push(x, y - 1, r, g, b)
        if y < h - 1:
            push(x, y + 1, r, g, b)
    return mask, (br, bgc, bb)


def sprite_from_image(im, nom=None, apps=None):
    """Retorna la imatge com a RGBA, llesta per convertir a .bin.

    - Icona d'app (el nom es a apps.txt): es queda SENCERA i nomes se li
      arrodoneixen les cantonades. Es el cas de Finder, Notes, Chrome...
    - Si el PNG te canal alfa, l'usa tal qual.
    - Si no, fa un flood fill des de les vores per treure el fons.
    """
    if nom is not None:
        if apps is None:
            apps = app_icons()
        if nom.lower() in apps:
            return cantonades_rodones(im)

    if has_alpha(im):
        return im.convert("RGBA")

    rgb = im.convert("RGB")
    w, h = rgb.size
    mask, _bgcol = bg_mask(rgb)
    frac = sum(mask) / float(w * h)

    if frac > 0.98:
        # S'ha menjat GAIREBE TOT: o la icona es una app amb fons propi (una
        # quadrat de color, com el VS Code) o el detector s'ha passat. En tots
        # dos casos val mes deixar la imatge sencera.
        # (Una icona petita sobre un fons gran elimina legítimament el 90%,
        #  aixi que el llindar ha de ser molt alt.)
        return rgb.convert("RGBA")

    sprite = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sp = sprite.load()
    px = rgb.load()
    for y in range(h):
        base = y * w
        for x in range(w):
            if not mask[base + x]:
                r, g, b = px[x, y]
                sp[x, y] = (r, g, b, 255)
    return sprite


# Llindar d'alfa: per sobre = opac, per sota = transparent (i el firmware hi
# pinta el color del boto). Es 96 en lloc de 128 perque els simbols son blancs
# sobre fons fosc: amb un llindar alt, els traços prims (les radiacions del
# sol, els arcs del wifi) s'aprimen massa i gairebe desapareixen.
ALFA_LLINDAR = 96

# Tramat ordenat de Bayer 4x4 (0..15). S'aplica NOMES a l'RGB, per amagar les
# bandes dels degradats (5 bits al vermell/blau, 6 al verd).
# NO es trama l'alfa: provat, i en un simbol prim a 32 px gairebe tots els
# pixels son de vora, aixi que el tramat el converteix en una taca de soroll.
BAYER4 = (0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5)


def bin_from_sprite(sprite, size=SIZE):
    """RGB565 big-endian amb el fons marcat amb el magenta transparent.

    Qualitat (aixo es el que fa que les icones no es vegin \"cutres\"):

      * Escalat net (escala_neta) amb PREMULTIPLICACIO d'alfa: les vores
        surten del color de debo, sense halo gris.
      * ALFA: llindar net (ALFA_LLINDAR). El firmware pinta el transparent amb
        el color del boto, aixi que les vores queden suau sobre qualsevol fons.
      * RGB: mig pas de tramat de Bayer abans de RGB565, per amagar les bandes.
    """
    small = escala_neta(sprite, size)
    sp = small.load()

    out = bytearray(size * size * 2)
    i = 0
    for y in range(size):
        for x in range(size):
            r, g, b, a = sp[x, y]
            if a < ALFA_LLINDAR:
                v = TRANS
            else:
                d = BAYER4[(y & 3) * 4 + (x & 3)]
                v = rgb565(r + (d >> 1) - 4,
                           g + (d >> 2) - 2,
                           b + (d >> 1) - 4)
            out[i] = (v >> 8) & 0xFF          # big-endian
            out[i + 1] = v & 0xFF
            i += 2
    return bytes(out)


def png_bytes_to_bin(png_bytes, size=SIZE, nom=None):
    """Converteix els bytes d'un PNG a .bin (el fa servir el panell web)."""
    if Image is None:
        raise RuntimeError("Cal Pillow: python3 -m pip install Pillow")
    im = Image.open(io.BytesIO(png_bytes))
    return bin_from_sprite(sprite_from_image(im, nom), size)


def convert(src, dst, apps=None):
    """Converteix un PNG a .bin. Retorna (bytes, es_icona_d_app)."""
    name = os.path.splitext(os.path.basename(src))[0]
    if apps is None:
        apps = app_icons()
    im = Image.open(src)
    data = bin_from_sprite(sprite_from_image(im, name, apps), SIZE)
    with open(dst, "wb") as fh:
        fh.write(data)
    return len(data), name.lower() in apps


def main():
    if Image is None:
        print("Cal Pillow:  python3 -m pip install Pillow")
        sys.exit(1)
    if not os.path.isdir(SRC_DIR):
        print(f"No existeix la carpeta: {SRC_DIR}")
        sys.exit(1)
    os.makedirs(OUT_DIR, exist_ok=True)

    if len(sys.argv) > 1:
        files = [sys.argv[1]]
    else:
        files = sorted(
            os.path.join(SRC_DIR, f)
            for f in os.listdir(SRC_DIR)
            if f.lower().endswith(".png")
        )

    if not files:
        print(f"No hi ha cap PNG a {SRC_DIR}")
        return

    apps = app_icons()
    n_apps = 0
    for src in files:
        name = os.path.splitext(os.path.basename(src))[0]
        dst = os.path.join(OUT_DIR, name + ".bin")
        n, es_app = convert(src, dst, apps)
        if es_app:
            n_apps += 1
        print(f"  {os.path.basename(src):<28} -> {name}.bin  ({n} bytes)"
              f"{'  [app: sencera]' if es_app else ''}")

    print()
    print(f"Fet! {len(files)} icona(es) a {OUT_DIR} "
          f"({n_apps} d'app senceres, la resta amb el fons tret)")
    print("Mira com queden:  python3 tools/mostra_icones.py")
    print("Puja-les amb:     python3 tools/puja-icones.py")


if __name__ == "__main__":
    main()
