#pragma once

#include <stdint.h>

#include "maclink.h"

/*
 * history.h - Historial de valors per dibuixar grafics.
 *
 * Guarda les ultimes mostres de cada serie (CPU, RAM, disc, bateria, xarxa,
 * load) en memòria, en un buffer circular. Amb aixo es poden dibuixar grafics
 * de linia i mini-grafics (sparklines) sense demanar res al Mac.
 *
 * Les mostres s'hi afegeixen quan arriba una linia d'estadistiques nova, o
 * sigui mes o menys un cop per segon.
 */

namespace History {

/* Quantes mostres es guarden (2 minuts a una mostra per segon). */
static constexpr int SAMPLES = 120;

/* Series disponibles (les que tenen sentit per a un grafic). */
enum Series {
    CPU = 0,
    MEM,
    DISK,
    BAT,
    LOAD,
    NET,
    SERIES_COUNT
};

/* Neteja-ho tot (en arrencar o en canviar de configuracio). */
void begin();

/* Afegeix una mostra de totes les series. */
void push(const MacLink::Stats& s);

/* Serie a partir del nom del gadget ("cpu", "mem", "disk", "bat", "load",
 * "net"), o -1 si aquell gadget no te grafic. */
int seriesFor(const char* widgetId);

/* Nom curt per mostrar ("CPU", "RAM"...). */
const char* name(int series);

/* Es un percentatge (0-100)? Aixi el grafic pot fixar l'escala. */
bool isPercent(int series);

/* Mostres valides que hi ha ara mateix. */
int count(int series);

/* Valor de la mostra 'i' (0 = la mes antiga de totes). */
float value(int series, int i);

/* Estadistiques de la finestra. */
float minValue(int series);
float maxValue(int series);
float avgValue(int series);
float lastValue(int series);

}  // namespace History
