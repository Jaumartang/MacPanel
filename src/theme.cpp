#include "theme.h"

#include <Arduino.h>

namespace {

struct Palette {
    const char* name;
    uint16_t bg, bg2, card, edge, text, dim, accent, ok, warn, bad, btn, btnP;
};

/* Els temes disponibles.
 * 'bg' i 'bg2' son els dos extrems del degradat de fons: han de ser molt
 * semblants (el degradat ha de notar-se poc, nomes donar profunditat). */
const Palette kThemes[] = {
    /* 0 - Fosc (blau-nit) */
    {"Fosc",    0x10A3, 0x0861, 0x2146, 0x3A08, 0xFFFF, 0x9CF3,
                0x07FF, 0x07E0, 0xFFE0, 0xF800, 0x2965, 0x05BF},
    /* 1 - Clar */
    {"Clar",    0xEF7D, 0xE73C, 0xFFFF, 0xC618, 0x0000, 0x52AA,
                0x03EF, 0x05E0, 0xFD20, 0xF800, 0xCE79, 0x9E7F},
    /* 2 - Neo (fosc amb accents cridaners) */
    {"Neo",     0x0000, 0x0841, 0x1082, 0x2124, 0xFFFF, 0x8410,
                0xF81F, 0x07E0, 0xFFE0, 0xF800, 0x2124, 0xF81F},
    /* 3 - Grafite (gadget sobri, accent teal) */
    {"Grafite", 0x18C3, 0x1082, 0x2965, 0x39E7, 0xFFFF, 0x9CF3,
                0x2DD8, 0x2E68, 0xFE60, 0xF9C8, 0x3186, 0x1A6A},
    /* 4 - Pastel (suau) */
    {"Pastel",  0xF79E, 0xEF5D, 0xFFDF, 0xD69A, 0x39E7, 0x8C71,
                0x5D3F, 0x4E48, 0xFDE0, 0xEAE9, 0xE79D, 0xC6FF},
    /* 5 - HUD (cian sobre negre, estil panell de control) */
    {"HUD",     0x0000, 0x0041, 0x0883, 0x0947, 0xE7FF, 0x5C95,
                0x07BF, 0x07E6, 0xFE20, 0xF9CB, 0x08C4, 0x0988},
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
