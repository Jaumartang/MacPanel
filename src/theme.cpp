#include "theme.h"

#include <Arduino.h>

namespace {

/* Converteix un color RGB de 8 bits al format de la pantalla (RGB565).
 *
 * Els temes s'escriuen amb RGB de tota la vida perque es puguin LLEGIR i
 * ajustar: abans eren numeros en hexadecimal i no hi havia manera de veure
 * d'un cop d'ull que, per exemple, el boto del tema HUD era gairebe negre. */
constexpr uint16_t rgb(uint8_t r, uint8_t g, uint8_t b)
{
    return static_cast<uint16_t>(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3));
}

struct Palette {
    const char* name;
    uint16_t bg, bg2, card, edge, text, dim, accent, ok, warn, bad, btn, btnP;
};

/* Els temes disponibles.
 *
 * Regla d'or (apresa a cops): el fons i els botons NO poden ser tots dos
 * negres. Si 'btn' i 'card' son gairebe iguals que 'bg', la pantalla queda
 * fosca i els elements no es distingeixen; les icones i el text semblen
 * apagats encara que la retroil-luminacio estigui al 100%. Per aixo, als temes
 * foscos, 'card' i 'btn' son clarament mes clars que 'bg'.
 *
 * 'bg' i 'bg2' son els dos extrems del degradat vertical: han de ser molt
 * semblants (nomes han de donar profunditat, no fer taques). */
const Palette kThemes[] = {
    /* 0 - Fosc (blau-nit) */
    {"Fosc",
     rgb( 12,  19,  33), rgb(  6,  10,  20),   /* bg, bg2 */
     rgb( 30,  43,  62), rgb( 52,  76, 106),   /* card, edge */
     rgb(236, 243, 255), rgb(146, 164, 188),   /* text, dim */
     rgb( 62, 150, 255), rgb( 60, 210, 130), rgb(255, 190,  70), rgb(255,  88,  98),
     rgb( 36,  51,  72), rgb( 44, 112, 190)},  /* btn, btnP */
    /* 1 - Clar */
    {"Clar",
     rgb(240, 244, 248), rgb(224, 230, 238),
     rgb(255, 255, 255), rgb(196, 206, 218),
     rgb( 24,  30,  40), rgb(108, 120, 136),
     rgb(  0, 110, 210), rgb(  0, 160,  80), rgb(215, 130,   0), rgb(215,  40,  50),
     rgb(230, 237, 245), rgb(198, 221, 248)},
    /* 2 - Neo (fosc amb accents cridaners) */
    {"Neo",
     rgb( 12,  11,  20), rgb(  4,   4,   9),
     rgb( 34,  31,  48), rgb( 76,  66, 116),
     rgb(246, 245, 255), rgb(154, 149, 180),
     rgb(255,  64, 220), rgb( 62, 230, 122), rgb(255, 212,  62), rgb(255,  72,  92),
     rgb( 40,  35,  58), rgb(112,  44, 134)},
    /* 3 - Grafite (gadget sobri, accent teal) */
    {"Grafite",
     rgb( 24,  28,  34), rgb( 15,  18,  23),
     rgb( 44,  51,  60), rgb( 72,  83,  96),
     rgb(240, 244, 250), rgb(152, 163, 175),
     rgb( 62, 200, 190), rgb( 72, 205, 132), rgb(240, 190,  80), rgb(240,  96, 102),
     rgb( 48,  56,  66), rgb( 34, 124, 120)},
    /* 4 - Pastel (suau) */
    {"Pastel",
     rgb(248, 244, 238), rgb(236, 230, 222),
     rgb(255, 255, 255), rgb(214, 204, 192),
     rgb( 58,  52,  48), rgb(140, 128, 118),
     rgb( 90, 130, 220), rgb( 70, 175, 120), rgb(225, 155,  50), rgb(220,  90,  90),
     rgb(238, 232, 224), rgb(203, 219, 245)},
    /* 5 - HUD (cian sobre blau nit, estil panell de control) */
    {"HUD",
     rgb( 11,  19,  32), rgb(  5,  10,  19),
     rgb( 28,  42,  60), rgb( 48,  84, 112),
     rgb(236, 250, 255), rgb(138, 168, 192),
     rgb(  0, 220, 240), rgb(  0, 220, 150), rgb(255, 200,  70), rgb(255,  92,  92),
     rgb( 34,  52,  74), rgb(  0, 112, 138)},
};

constexpr uint8_t kCount = sizeof(kThemes) / sizeof(kThemes[0]);
uint8_t gCurrent = 0;

}  // namespace

namespace Th {

uint16_t bg, bg2, card, edge, text, dim, accent, ok, warn, bad, btn, btnP;

uint8_t count()
{
    return kCount;
}

const char* name(uint8_t index)
{
    return (index < kCount) ? kThemes[index].name : kThemes[0].name;
}

void set(uint8_t index)
{
    if (index >= kCount) {
        index = 0;
    }
    gCurrent = index;
    const Palette& p = kThemes[index];
    bg     = p.bg;
    bg2    = p.bg2;
    card   = p.card;
    edge   = p.edge;
    text   = p.text;
    dim    = p.dim;
    accent = p.accent;
    ok     = p.ok;
    warn   = p.warn;
    bad    = p.bad;
    btn    = p.btn;
    btnP   = p.btnP;
    Serial.printf("[UI] tema: %s\n", p.name);
}

uint8_t current()
{
    return gCurrent;
}

}  // namespace Th
