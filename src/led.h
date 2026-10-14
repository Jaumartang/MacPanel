#pragma once

#include <stdint.h>

/*
 * led.h - LED RGB de la placa (anode comu: actiu a nivell BAIX).
 *
 * Els tres canals es controlen per PWM (LEDC) per poder fer colors suaus.
 * L'API treballa amb valors LOGICS 0..255 (0 = apagat, 255 = maxim); la
 * inversio per anode comu la gestiona aquest modul.
 */

namespace Led {

/* Configura els 3 pins com a PWM i apaga el LED. Idempotent. */
void begin();

/* Color logic: 0..255 per canal (0 = apagat, 255 = maxim). */
void setRgb(uint8_t r, uint8_t g, uint8_t b);

/* Apaga el LED (equivaleix a setRgb(0,0,0)). */
void off();

}  // namespace Led
