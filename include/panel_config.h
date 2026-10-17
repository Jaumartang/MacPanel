#pragma once

#include <stddef.h>
#include <stdint.h>

/*
 * panel_config.h - Parametres del projecte Mac Panel. Cap numero magic al codi:
 * tot es aqui (geometria, temps, catalegs, colors) o a include/pins.h.
 */

/* Versio del firmware. Es veu a la pantalla 'Sobre' del menu. */
#define MP_VERSION "Mac Panel v1.3"

/* --- Geometria de la pantalla (vertical) ---------------------------------- */
/* Han de coincidir amb TFT_WIDTH/TFT_HEIGHT de include/tft_setup.h (320x480). */
static constexpr int SCREEN_W = 320;
static constexpr int SCREEN_H = 480;

/* --- Port serie ----------------------------------------------------------- */
static constexpr uint32_t SERIAL_BAUD = 115200;

/* --- Protocol ------------------------------------------------------------- */
/* Linia maxima de la consola local (comandes escrites pel monitor serie). */
static constexpr size_t CONSOLE_LINE_MAX = 96;
/* Linia maxima que arriba del Mac (les de configuracio CFG poden ser llargues:
 * fins a 12 pantalles amb 15 botons cadascuna). Compte: cada byte d'aquest
 * buffer es DRAM estatica que no queda per a la pila de Bluetooth. */
static constexpr size_t MACLINE_MAX = 4096;
/* Si no arriba cap linia d'estadistiques 'S' en aquest temps, es NO LINK.
 * 10 s (abans 3): el Mac pot tenir iteracions puntualment lentes (subprocessos
 * que es traben quan el sistema esta carregat) i no val la pena que, per 8 s
 * sense stats, la placa es passi a "sense enllac" i apagui la pantalla. */
static constexpr uint32_t LINK_TIMEOUT_MS = 10000;
/* Cada quan s'escriu l'estat de memoria pel port serie. */
static constexpr uint32_t HEAP_LOG_INTERVAL_MS = 10000;

/* --- Retroil-luminacio ---------------------------------------------------- */
/* A la placa ESP32-32E el backlight va al GPIO 27 i es ACTIU ALT. */
static constexpr bool BL_ACTIVE_LOW = false;

/* --- Bluetooth (teclat HID) ------------------------------------------------ */
/* La pila de Bluetooth necessita un bloc de memoria contigu gran. Si el bloc
 * lliure mes gran es mes petit que aixo, no s'hi encen: es millor quedar-se
 * sense tecles que no pas quedar-se en bucle de reinicis. */
static constexpr uint32_t BT_MIN_FREE_HEAP = 40000;

/* El Bluetooth ocupa mes de 100 KB i deixa el heap molt just. Per aixo no
 * s'encen fins que ha passat una estona: aixi la configuracio que envia el Mac
 * just connectar-se es pot llegir amb memoria de sobres. */
static constexpr uint32_t BT_START_DELAY_MS = 6000;

/* --- Tactil XPT2046 ------------------------------------------------------- */
static constexpr uint16_t TOUCH_DEFAULT_PRESSURE = 400;
static constexpr uint32_t TOUCH_MIN_READ_INTERVAL_MS = 15;
static constexpr int32_t  TOUCH_RAW_TOLERANCE = 40;

/* --- Limits de configuracio ----------------------------------------------- */
static constexpr int MAX_WIDGETS = 10;
static constexpr int MAX_BUTTONS = 15;

/* --- Pantalles (pages) ---------------------------------------------------- */
static constexpr int MAX_PAGES        = 12;   /* pantalles configurables */
static constexpr int MAX_PAGE_BUTTONS = 15;   /* botons per pantalla */
static constexpr int MAX_PAGE_WIDGETS = 9;    /* gadgets per pantalla */
/* Graella de botons: el maxim de columnes (teclat numeric) i de files que pot
 * arribar a demanar una posicio fixa triada a l'editor visual. */
static constexpr int BTN_MAX_COLS     = 4;
static constexpr int BTN_MAX_ROWS     = 8;
/* Apps (bundle id) que fan saltar la placa a aquesta pantalla tota sola. */
static constexpr int MAX_PAGE_APPS    = 3;
static constexpr int APP_ID_MAX       = 40;

/* --- Repos (standby) ------------------------------------------------------ */
/* Temps sense tocar la pantalla abans d'apagar la retroil-luminacio (ms).
 * 0 = mai: la pantalla nomes s'apaga quan ho fa la del Mac (que es el que
 * normalment vols: si estas treballant, la pantalla no s'ha d'apagar).
 * Es pot canviar des dels ajustos de la pantalla. */
static constexpr uint32_t STANDBY_DEFAULT_MS = 0;
/* Si fa tant de temps que no sabem res del Mac (ha dormit o s'ha apagat),
 * tambe s'apaga la pantalla. */
static constexpr uint32_t LINK_SLEEP_MS      = 45000;

/* --- Pantalla de repòs (rellotge) ----------------------------------------- */
/* Minuts que pot estar el Mac sense rebre cap input abans que la placa passi
 * sola a la pantalla de rellotge amb la previsio del temps (com el
 * salvapantalles del Mac). 0 = mai. Es pot canviar des del panell. */
static constexpr uint32_t IDLE_CLOCK_DEFAULT_MIN = 5;

/* --- Disposicio ----------------------------------------------------------- */
static constexpr int HEADER_H = 30;    /* capcalera (hora · host · enllac) */
static constexpr int TABBAR_H = 34;    /* barra de pestanyes (pantalles) */
static constexpr int PAD      = 6;     /* marge generic */
static constexpr int WIDGET_ROW_H = 34;  /* alcada de cada fila d'estat */
static constexpr int BTN_COLS = 3;     /* columnes de la graella de botons */
static constexpr int BTN_GAP  = 6;     /* separacio entre botons */

/* --- Tipus de pantalla (layout) ------------------------------------------- */
/* "status"  = gadgets (files) + botons
 * "buttons" = nomes botons
 * "gauges"  = rellotges circulars dels gadgets + botons
 * "numpad"  = teclat numeric (envia digits per Bluetooth)
 * "clock"   = rellotge gran + data + meteo + botons
 */
static constexpr int MAX_GAUGES = 4;

/* --- Icones (SD: /icons/<nom>.bin, RGB565 big-endian, quadrades) ---------- */
/* 32x32 (2048 bytes): 1:1 sense escalat = sense deformacio. */
static constexpr int ICON_PX     = 32;   /* mida dels .bin (quadrats) */
static constexpr int ICON_BTN_PX = 32;   /* mida amb que es dibuixen als botons */
/* Color de les icones que s'ha de pintar amb el fons (transparent). */
static constexpr uint16_t ICON_TRANSPARENT = 0xF81F;

/* --- Cataleg de widgets --------------------------------------------------- */
static constexpr int WIDGET_COUNT = 9;
static constexpr const char* WIDGET_IDS[WIDGET_COUNT] = {
    "cpu", "mem", "disk", "bat", "net", "load", "uptime", "time", "host"
};

/* --- Cataleg d'accions d'estoc -------------------------------------------- */
static constexpr int ACTION_COUNT = 15;
static constexpr const char* ACTION_IDS[ACTION_COUNT] = {
    "media_prev", "media_play", "media_next", "vol_down", "vol_up", "mute",
    "app_terminal", "app_safari", "app_vscode", "app_music", "app_finder",
    "sys_lock", "sys_sleep", "sys_shot", "sys_dark"
};

/* --- Configuracio per defecte (si no n'hi ha cap desada a la NVS) --------- */
/* Format: o=orientacio, p=pantalles; cada pantalla te n=nom, i=icona,
 * l=disposicio ("status" amb gadgets | "buttons"), w=gadgets, b=botons
 * (cada boto es [id, text, icona, tecles]). */
static constexpr const char* DEFAULT_CFG_JSON =
    "{\"o\":\"v\",\"p\":["
    "{\"n\":\"Estat\",\"i\":\"grid\",\"l\":\"status\","
    "\"w\":[\"cpu\",\"mem\",\"disk\",\"bat\",\"net\"],"
    "\"b\":[[\"media_play\",\"PLAY\",\"play\",\"media_playpause\"]]},"
    "{\"n\":\"Mitjans\",\"i\":\"play\",\"l\":\"buttons\",\"b\":["
    "[\"media_prev\",\"PREV\",\"prev\",\"media_prev\"],"
    "[\"media_play\",\"PLAY\",\"play\",\"media_playpause\"],"
    "[\"media_next\",\"NEXT\",\"next\",\"media_next\"],"
    "[\"vol_down\",\"VOL-\",\"vol_down\",\"media_volumedown\"],"
    "[\"vol_up\",\"VOL+\",\"vol_up\",\"media_volumeup\"],"
    "[\"mute\",\"MUTE\",\"mute\",\"media_mute\"]]},"
    "{\"n\":\"Eines\",\"i\":\"copy\",\"l\":\"buttons\",\"b\":["
    "[\"edit_copy\",\"COPY\",\"copy\",\"cmd+c\"],"
    "[\"edit_paste\",\"PASTE\",\"paste\",\"cmd+v\"],"
    "[\"edit_cut\",\"CUT\",\"cut\",\"cmd+x\"],"
    "[\"edit_undo\",\"UNDO\",\"undo\",\"cmd+z\"],"
    "[\"edit_redo\",\"REDO\",\"redo\",\"shift+cmd+z\"],"
    "[\"edit_group\",\"GROUP\",\"group\",\"cmd+g\"],"
    "[\"edit_export\",\"EXPORT\",\"export\",\"shift+cmd+e\"],"
    "[\"edit_import\",\"IMPORT\",\"import\",\"shift+cmd+i\"],"
    "[\"edit_save\",\"SAVE\",\"save\",\"cmd+s\"]]},"
    "{\"n\":\"Sistema\",\"i\":\"lock\",\"l\":\"buttons\",\"b\":["
    "[\"sys_lock\",\"LOCK\",\"lock\",\"\"],"
    "[\"sys_sleep\",\"SLEEP\",\"sleep\",\"\"],"
    "[\"sys_shot\",\"SHOT\",\"shot\",\"\"],"
    "[\"sys_dark\",\"DARK\",\"dark\",\"\"]]}"
    "]}";

/* --- Paleta de colors ----------------------------------------------------- */
/* Els colors son variables en temps d'execucio i viuen a src/theme.h (es poden
 * canviar des del panell de control). Aqui ja no hi ha cap color fix. */
