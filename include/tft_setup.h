#pragma once

/*
 * tft_setup.h - Configuracio de TFT_eSPI per a la placa (LCDWiki E32R40T).
 *
 * TFT_eSPI (>= 2.5.31) carrega aquest fitxer automaticament si el troba a
 * l'include path (__has_include(<tft_setup.h>)), de manera que la configuracio
 * de maquinari viu versionada al repositori i no dins de la llibreria.
 *
 * Els valors son els provats al projecte Tamagoxi (mateixa placa): ST7796S
 * 320x480, LCD + tactil a HSPI.
 */

/* Marca propia: display.cpp la comprova en temps de compilacio per assegurar
 * que TFT_eSPI ha carregat *aquest* fitxer i no un User_Setup.h de la llibreria. */
#define MP_TFT_SETUP 1

/* Els pins surten de la unica font de veritat (include/pins.h). */
#include <pins.h>

/* --- Controlador i mida --------------------------------------------------- */
#define ST7796_DRIVER
#define TFT_WIDTH  320
#define TFT_HEIGHT 480

/* --- Bus SPI del LCD i del tactil (HSPI) ---------------------------------- */
#define USE_HSPI_PORT

#define TFT_MISO PIN_LCD_MISO
#define TFT_MOSI PIN_LCD_MOSI
#define TFT_SCLK PIN_LCD_SCLK
#define TFT_CS   PIN_LCD_CS
#define TFT_DC   PIN_LCD_DC
#define TFT_RST  PIN_LCD_RST

/* --- Retroil-luminacio (PWM gestionat per Display::setBacklight()) -------- */
#define TFT_BL           PIN_LCD_BL
#define TFT_BACKLIGHT_ON HIGH

/* --- Tactil resistiu XPT2046 ---------------------------------------------- */
#define TOUCH_CS PIN_TOUCH_CS
/* L'IRQ (IO36) no es declara: es llegeix per polling. */

/* --- Velocitats SPI ------------------------------------------------------- */
#define SPI_FREQUENCY        40000000
#define SPI_READ_FREQUENCY   20000000
#define SPI_TOUCH_FREQUENCY   2500000

/* --- Fonts ---------------------------------------------------------------- */
#define LOAD_GLCD
#define LOAD_FONT2
#define LOAD_FONT4
#define LOAD_FONT6    /* 48 px (digits i pocs simbols): per al rellotge */
#define LOAD_GFXFF    /* fonts suaus (FreeSans) */
#define SMOOTH_FONT
