"""Genera les fonts antialiassades (.vlw) que llegeix TFT_eSPI.

TFT_eSPI te un format propi, 'VLW', que es el que produeix la seva eina
'Create_Smooth_Font'. El generem aqui per poder-lo fer servir des de Python.

Format (tot en int32 BIG-ENDIAN):

  Capcalera (24 bytes):
    0  gCount      nombre de glifs
    4  versio      (3)
    8  yAdvance    (mida en punts)
    12 (descartat)
    16 ascent      de la linia de base cap amunt
    20 descent     de la linia de base cap avall

  Taula de glifs (28 bytes cada un):
    unicode, alcada, amplada, xAdvance, dY, dX, (descartat)

  Bitmaps: per cada glif, alcada*amplada bytes (0-255, grisos), en ordre.

Els bitmaps comencen a 24 + gCount*28 i van seguits, en el mateix ordre que la
taula: TFT_eSPI els va recorrent i calcula els desplacaments ell mateix.
"""
import struct
from PIL import Image, ImageFont

SFNS = '/System/Library/Fonts/SFNS.ttf'

# Caracters: ASCII imprimible + els que fa servir la interficie de la placa.
CARACTERS = ([chr(c) for c in range(0x20, 0x7F)] +
             ['¡', '«', '·', '»', 'ò', '▲', '▼'])


def fes(fitxer, mida, pes, caracters=CARACTERS):
    """Bytes del .vlw d'una font."""
    f = ImageFont.truetype(fitxer, mida)
    if pes:
        f.set_variation_by_name(pes)
    ascent, descent = f.getmetrics()

    glifs = []
    for ch in caracters:
        adv = int(round(f.getlength(ch)))
        l, t, r, b = f.getbbox(ch)
        if r <= l or b <= t:                  # espai i semblants: sense tinta
            glifs.append((ord(ch), 0, 0, adv, 0, 0, b''))
            continue
        # Retallem el glif a la seva tinta (aixi el bitmap es el minim).
        im = Image.new('L', (r - l, b - t), 0)
        ImageDraw = __import__('PIL.ImageDraw', fromlist=['Draw']).Draw
        ImageDraw(im).text((-l, -t), ch, font=f, fill=255)
        glifs.append((ord(ch), b - t, r - l, adv, ascent - t, l, im.tobytes()))

    out = bytearray()
    out += struct.pack('>6i', len(glifs), 3, ascent + descent, 0, ascent, descent)
    for u, h, w, adv, dy, dx, _ in glifs:
        out += struct.pack('>7i', u, h, w, adv, dy, dx, 0)
    for _, _, _, _, _, _, bm in glifs:
        out += bm
    return bytes(out)


def com_a_c(font_bytes, nom):
    """Array de C (PROGMEM) amb els bytes de la font."""
    linies = []
    for i in range(0, len(font_bytes), 16):
        tros = font_bytes[i:i + 16]
        linies.append('    ' + ', '.join('0x%02X' % b for b in tros) + ',')
    return ('/* Generat per tools/fes_fonts.py - no editar a ma. */\n'
            'static const uint8_t %s[] = {\n%s\n};\n' % (nom, '\n'.join(linies)))


if __name__ == '__main__':
    import os
    import sys

    # Que fa servir cada mida (vegeu src/ui.cpp):
    #   S (18 px)  etiquetes petites, noms d'app, gadgets, avisos...  -> tot
    #   M (24 px)  titols, noms de boto, avisos grans                -> tot
    #   L (35 px)  temperatura, teclat numeric, "MAC PANEL"           -> tot
    #   B (47 px)  rellotge gran ("14:32") i el logo "MP"             -> nomes el que cal
    MIDA_B = '0123456789:-MP '

    FEINES = [
        ('font_s.h', 'kFontS', 18, 'Regular',  CARACTERS),
        ('font_m.h', 'kFontM', 24, 'Semibold', CARACTERS),
        ('font_l.h', 'kFontL', 35, 'Bold',     CARACTERS),
        ('font_b.h', 'kFontB', 47, 'Bold',     list(MIDA_B)),
    ]

    ARREL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DESTI = os.path.join(ARREL, 'include')
    total = 0
    for fitxer, nom, mida, pes, chars in FEINES:
        d = fes(SFNS, mida, pes, chars)
        total += len(d)
        cami = os.path.join(DESTI, fitxer)
        with open(cami, 'w', encoding='utf-8') as fh:
            fh.write('#pragma once\n#include <stdint.h>\n\n')
            fh.write('/* Font %d px %s, %d glifs. Generada per '
                     'tools/fes_fonts.py. */\n' % (mida, pes, len(chars)))
            fh.write(com_a_c(d, nom))
        print('%-12s %-6s %2d px  %2d glifs  %6d bytes' %
              (fitxer, pes, mida, len(chars), len(d)))
    print('total: %.1f KB de flash' % (total / 1024.0))

