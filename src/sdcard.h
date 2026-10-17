#pragma once

#include <stdint.h>

/*
 * sdcard.h - Targeta microSD de la placa (bus VSPI, independent del LCD i el
 * tactil que van a HSPI). Serveix per guardar-hi les icones dels botons
 * (/icons/<nom>.bin) i altres actius.
 *
 * (El fitxer es diu sdcard i no sd per no xocar amb el SD.h del framework.)
 */

namespace Sd {

/* Reintents de muntatge a l'arrencada: la targeta de vegades triga a estar a
 * punt i, sense reintents, una arrencada amb pressa deixava la placa sense cap
 * icona fins al proper reinici. */
static constexpr int SD_INTENTS   = 4;
static constexpr int SD_RETARD_MS = 150;

/* Munta la targeta. Idempotent. Retorna false si no hi ha targeta. */
bool begin();

/* Hi ha la targeta muntada? */
bool isMounted();

}  // namespace Sd
