#pragma once

/*
 * pins.h - Unica font de veritat del mapa de pins de la placa (ESP32-32E).
 *
 * Els valors son els PROVATS i funcionals a la placa (projecte Tamagoxi), on la
 * pantalla, el tactil i la microSD es van validar en hardware real.
 *
 * Es fan servir #define (i no constexpr) perque include/tft_setup.h els pugui
 * aliasar (TFT_CS, TFT_DC...) i TFT_eSPI els entengui en el seu proces de
 * preprocessador.
 */

/* --- LCD ST7796S (bus HSPI) ----------------------------------------------- */
#define PIN_LCD_MISO 12
#define PIN_LCD_MOSI 13
#define PIN_LCD_SCLK 14
#define PIN_LCD_CS   15
#define PIN_LCD_DC    2   /* Data / Command */
#define PIN_LCD_RST  -1   /* RST del LCD lligat a EN: no hi ha pin dedicat */
#define PIN_LCD_BL   27   /* retroil-luminacio, PWM, actiu ALT */

/* --- Tactil XPT2046 (comparteix el bus HSPI amb el LCD) ------------------- */
#define PIN_TOUCH_CS  33
#define PIN_TOUCH_IRQ 36  /* actiu baix, nomes entrada (34-39) */

/* --- microSD (bus VSPI, independent del LCD) ------------------------------ */
#define PIN_SD_CS    5
#define PIN_SD_SCK  18
#define PIN_SD_MISO 19
#define PIN_SD_MOSI 23

/* --- LED RGB (anode comu -> actiu a nivell BAIX) -------------------------- */
#define PIN_LED_R 22
#define PIN_LED_G 16
#define PIN_LED_B 17
#define LED_ACTIVE_LOW 1
