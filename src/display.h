#pragma once

#include <TFT_eSPI.h>

#include <stdint.h>

/*
 * display.h - Pantalla principal (LCDWiki E32R40T: ST7796S 320x480 per SPI).
 *
 * Encapsula TFT_eSPI i la retroil-luminacio per PWM. Cap altre modul no ha de
 * tocar TFT_eSPI directament: sempre a traves d'aquest modul (o del driver()
 * que exposa).
 *
 * Configuracio de maquinari a include/tft_setup.h (pins a include/pins.h).
 */

namespace Display {

/* Inicialitza TFT_eSPI i la retroil-luminacio. Idempotent.
 * Retorna false si no s'ha pogut inicialitzar (mai deixa el sistema penjat). */
bool init();

/* Driver TFT_eSPI de sota. */
TFT_eSPI& driver();

/* Mides en pixels segons l'orientacio configurada (320x480 vertical). */
uint16_t width();
uint16_t height();

/* Canvia l'orientacio: 0 = vertical (320x480), 1 = horitzontal (480x320). */
void setRotation(uint8_t rotation);

/* Retroil-luminacio per PWM: 0 = apagada, 100 = maxima. */
void setBacklight(uint8_t percent);

/* Ultim percentatge aplicat amb setBacklight() (comenca a 100). */
uint8_t backlight();

}  // namespace Display
