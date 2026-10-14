#!/usr/bin/env python3
"""preview_fons.py - renderitza el fons de la pantalla per veure'l abans de
flashejar.

Replica EXACTAMENT el que fa `drawBackground()` de src/ui.cpp (incloent-hi
l'alphaBlend de TFT_eSPI i el degradat) i hi dibuixa a sobre una aproximacio
del contingut, per poder jutjar si el fons es massa fluix o tapa el text.

Us:
    python3 tools/preview_fons.py            # desa preview_fons_v.png
    python3 tools/preview_fons.py --h        # tambe l'horitzontal
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAD = 6
HEADER_H = 30
NAV_H = 34
WIDGET_ROW_H = 34

# --- Colors del tema HUD (src/theme.cpp) -----------------------------------
BG, BG2 = 0x0000, 0x0041
CARD, EDGE = 0x0883, 0x0947
TEXT, DIM = 0xE7FF, 0x5C95
ACCENT, WARN = 0x07BF, 0xFE20
BTN, BTN_P = 0x08C4, 0x0988


def alpha_blend(alpha, fg, bg):
    """Copia exacta de TFT_eSPI::alphaBlend (aritmetica de 32 bits sense signe)."""
    rxb = (bg & 0xF81F)
    diff = ((fg & 0xF81F) - rxb) & 0xFFFFFFFF
    rxb = (rxb + ((diff * (alpha >> 2)) & 0xFFFFFFFF) >> 6) & 0xFFFFFFFF
    xgx = (bg & 0x07E0)
    diff2 = ((fg & 0x07E0) - xgx) & 0xFFFFFFFF
    xgx = (xgx + ((diff2 * alpha) & 0xFFFFFFFF) >> 8) & 0xFFFFFFFF
    return (rxb & 0xF81F) | (xgx & 0x07E0)


def rgb888(c):
    """RGB565 -> (r, g, b) de 8 bits."""
    r = (c >> 11) & 0x1F
    g = (c >> 5) & 0x3F
    b = c & 0x1F
    return (r * 255 // 31, g * 255 // 63, b * 255 // 31)


# Tramat ordenat de Bayer 4x4: es el que fa que els degradats no facin esglaons
# en una pantalla de 5 bits per canal. Els valors son els mateixos que a ui.cpp.
BAYER = (0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5)


def chan(c):
    """RGB565 -> (r, g, b) de 8 bits (com chanR/G/B de ui.cpp)."""
    return (((c >> 11) & 0x1F) << 3, ((c >> 5) & 0x3F) << 2, (c & 0x1F) << 3)


def to565(r, g, b, x, y):
    """8 bits per canal -> RGB565 amb tramat ordenat."""
    d = BAYER[(y & 3) * 4 + (x & 3)] - 8
    r += d >> 1
    g += d >> 2
    b += d >> 1
    r = 0 if r < 0 else (255 if r > 255 else r)
    g = 0 if g < 0 else (255 if g > 255 else g)
    b = 0 if b < 0 else (255 if b > 255 else b)
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


class Pantalla:
    """Llenç que imita les primitives de TFT_eSPI que fem servir."""

    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.im = Image.new("RGB", (w, h), rgb888(BG))
        self.d = ImageDraw.Draw(self.im)

    def px(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.d.point((x, y), fill=rgb888(c))

    def hline(self, x, y, w, c):
        if 0 <= y < self.h and w > 0:
            self.d.line([(x, y), (x + w - 1, y)], fill=rgb888(c))

    def vline(self, x, y, h, c):
        if 0 <= x < self.w and h > 0:
            self.d.line([(x, y), (x, y + h - 1)], fill=rgb888(c))

    def line(self, x0, y0, x1, y1, c):
        self.d.line([(x0, y0), (x1, y1)], fill=rgb888(c))

    def rect(self, x, y, w, h, c):
        self.d.rectangle([x, y, x + w - 1, y + h - 1], fill=rgb888(c))

    def rrect(self, x, y, w, h, r, c):
        self.d.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=r,
                                 fill=rgb888(c))

    def vgradient(self, x, y, w, h, c0, c1):
        """fillRectVGradient de TFT_eSPI: interpolacio lineal en RGB565."""
        if h <= 0:
            return
        r0, g0, b0 = (c0 >> 11) & 0x1F, (c0 >> 5) & 0x3F, c0 & 0x1F
        r1, g1, b1 = (c1 >> 11) & 0x1F, (c1 >> 5) & 0x3F, c1 & 0x1F
        for i in range(h):
            t = (i << 16) // h
            r = (r0 + (((r1 - r0) * t) >> 16)) & 0x1F
            g = (g0 + (((g1 - g0) * t) >> 16)) & 0x3F
            b = (b0 + (((b1 - b0) * t) >> 16)) & 0x1F
            self.d.line([(x, y + i), (x + w - 1, y + i)],
                        fill=rgb888((r << 11) | (g << 5) | b))


def fons_actual(p):
    """El fons que hi ha ara a src/ui.cpp (per comparar)."""
    W, H = p.w, p.h
    p.vgradient(0, 0, W, H, BG, BG2)
    pas = 24
    linia = alpha_blend(26, EDGE, BG)
    creu = alpha_blend(85, ACCENT, BG)
    for x in range(pas, W, pas):
        p.vline(x, 0, H, linia)
    for y in range(pas, H, pas):
        p.hline(0, y, W, linia)
    for y in range(pas, H, pas * 2):
        for x in range(pas, W, pas * 2):
            p.px(x - 1, y, creu)
            p.px(x + 1, y, creu)
            p.px(x, y - 1, creu)
            p.px(x, y + 1, creu)


def fons_nou(p):
    """Proposta: ambient de "aurora" amb degradats suaus, tramats i gra fi."""
    W, H = p.w, p.h
    bgR, bgG, bgB = chan(BG)
    b2R, b2G, b2B = chan(BG2)
    acR, acG, acB = chan(ACCENT)
    waR, waG, waB = chan(WARN)

    # Les llums son EL·LIPTIQUES: les amples i planes es llegeixen com una
    # aurora, no com una taca. Els centres de les dues primeres son FORA de la
    # pantalla, aixi que entren des de dalt i des de baix.
    #   (centre x, centre y, radi x, radi y, color, intensitat)
    llums = (
        (W // 2,          H * -4 // 100,  W * 86 // 100, H * 24 // 100, acR, acG, acB, 175),
        (W // 2,          H * 104 // 100, W * 86 // 100, H * 28 // 100, acR, acG, acB, 155),
        (W * 106 // 100,  H * 52 // 100,  W * 52 // 100, H * 52 // 100, waR, waG, waB, 58),
        (W * -6 // 100,   H * 46 // 100,  W * 46 // 100, H * 50 // 100, acR, acG, acB, 50),
    )
    pre = [(gx, gy, (rx * ry) ** 2, rx, ry, lr, lg, lb, a)
           for (gx, gy, rx, ry, lr, lg, lb, a) in llums]

    for y in range(H):
        # Base: una mica mes clara a dalt i a baix (on hi ha les llums) i mes
        # fosca al mig, pero no del tot negra: aixi no es veu un forat.
        t2 = abs(y * 2 - H)
        f = 90 + (t2 * 166) // H
        baseR = bgR + (((b2R - bgR) * f) >> 8)
        baseG = bgG + (((b2G - bgG) * f) >> 8)
        baseB = bgB + (((b2B - bgB) * f) >> 8)

        dyv = y * 2 - H
        vy = min((dyv * dyv * 58) // (H * H), 80)
        dyll = [((y - gy) * rx) ** 2 for (_gx, gy, _rr, rx, _ry, _lr, _lg, _lb, _a) in pre]

        for x in range(W):
            r, g, b = baseR, baseG, baseB

            for i, (gx, _gy, rr, _rx, ry, lr, lg, lb, aa) in enumerate(pre):
                d = ((x - gx) * ry) ** 2 + dyll[i]
                if d < rr:
                    a = ((rr - d) * 256) // rr      # 0..256
                    a = (a * a) >> 8                # caiguda suau (quadratica)
                    a = (a * aa) >> 8               # intensitat
                    r += ((lr - r) * a) >> 8
                    g += ((lg - g) * a) >> 8
                    b += ((lb - b) * a) >> 8

            # Vinya: les vores i els cantons, una mica mes foscos.
            dxv = x * 2 - W
            v = vy + min((dxv * dxv * 58) // (W * W), 80)
            if v > 0:
                k = 256 - v
                r = (r * k) >> 8
                g = (g * k) >> 8
                b = (b * k) >> 8

            # Gra: un pèl de soroll, perque la superficie no quedi llisa i per
            # acabar d'amagar els esglaons.
            n = ((x * 73856093) ^ (y * 19349663)) & 3
            n -= 2
            r += n
            g += n
            b += n

            p.px(x, y, to565(r, g, b, x, y))

    # Cantonades de reticle: el detall que dona aire de panell de control.
    marc = alpha_blend(150, ACCENT, BG)
    L, M = 26, 5
    for (x, y, sx, sy) in ((M, M, 1, 1), (W - 1 - M, M, -1, 1),
                           (M, H - 1 - M, 1, -1), (W - 1 - M, H - 1 - M, -1, -1)):
        p.hline(min(x, x + sx * L), y, L, marc)
        p.vline(x, min(y, y + sy * L), L, marc)

    # Marques de regla a les vores, molt fluixes.
    tick = alpha_blend(55, ACCENT, BG)
    for y in range(HEADER_H + 20, H - NAV_H - 20, 48):
        p.hline(0, y, 4, tick)
        p.hline(W - 4, y, 4, tick)


def contingut(p):
    """Aproximacio del contingut, per jutjar el contrast."""
    W, H = p.w, p.h
    p.rect(0, 0, W, HEADER_H, CARD)
    p.hline(0, HEADER_H - 1, W, EDGE)

    y = HEADER_H + 4
    for _ in range(5):
        p.rrect(PAD, y, W - 2 * PAD, WIDGET_ROW_H - 6, 8, CARD)
        y += WIDGET_ROW_H

    y += 6
    cw = (W - PAD * 4) // 3
    for i in range(3):
        p.rrect(PAD + i * (cw + PAD), y, cw, 46, 9, BTN)

    p.rect(0, H - NAV_H, W, NAV_H, CARD)


def main():
    ap = argparse.ArgumentParser(description="Previsualitzacio del fons")
    ap.add_argument("--h", action="store_true", help="tambe en horitzontal")
    ap.add_argument("--net", action="store_true", help="nomes el fons")
    args = ap.parse_args()

    mides = [(320, 480, "v")]
    if args.h:
        mides.append((480, 320, "h"))

    for W, H, nom in mides:
        for quin, fn in (("actual", fons_actual), ("nou", fons_nou)):
            p = Pantalla(W, H)
            fn(p)
            if not args.net:
                contingut(p)
            out = os.path.join(ROOT, "preview_fons_%s_%s.png" % (quin, nom))
            p.im.save(out)
            print("desat:", out)

    print()
    print("Obre els PNG i compara'ls: 'actual' es el d'ara, 'nou' la proposta.")


if __name__ == "__main__":
    main()

