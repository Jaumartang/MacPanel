#pragma once

#include <stdint.h>

/*
 * theme.h - Temes de color de la interficie.
 *
 * Els colors son variables en temps d'execucio (no constexpr) perque es poden
 * canviar des del panell de control sense refer el firmware.
 */

namespace Th {

/* Colors actuals (els fa servir tota la UI). */
extern uint16_t bg;      /* fons */
extern uint16_t bg2;     /* fons (l'altre extrem del degradat) */
extern uint16_t card;    /* targetes / capcalera */
extern uint16_t edge;    /* vores */
extern uint16_t text;    /* text principal */
extern uint16_t dim;     /* text secundari */
extern uint16_t accent;  /* accent */
extern uint16_t ok;      /* verd */
extern uint16_t warn;    /* groc */
extern uint16_t bad;     /* vermell */
extern uint16_t btn;     /* fons de boto */
extern uint16_t btnP;    /* boto premut */

/* Nombre de temes disponibles. */
uint8_t count();

/* Nom del tema (per mostrar-lo). */
const char* name(uint8_t index);

/* Aplica un tema (0..count()-1). */
void set(uint8_t index);

/* Tema actual. */
uint8_t current();

}  // namespace Th
