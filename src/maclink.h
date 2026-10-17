#pragma once

#include <stdint.h>

#include "panel_config.h"

/*
 * maclink.h - Protocol de l'enllac amb el Mac pel port serie USB.
 *
 * El Mac envia LINIES DE TEXT acabades en '\n':
 *   H                                    (resposta al nostre hello, opcional)
 *   OK Mac-Panel v1                      (handshake)
 *   S cpu=42.1 mem=38 disk=61 bat=88 chg=1 up=1.2 dn=0.3 load=1.8
 *     host=MacBook time=14:32 uptime=8040 dsp=1 dk=1
 *   CFG {"w":["cpu","mem"],"b":[["media_play","PLAY"]]}
 *
 * L'ESP32 respon:
 *   H                                    (hola, a l'arrencada)
 *   A                                    (ack de configuracio rebuda)
 *   C <id>                               (boto premut -> executa l'accio al Mac)
 *
 * La configuracio rebuda es desa a la NVS (Preferences) i es recupera a
 * l'arrencada; si no n'hi ha cap, s'aplica una de per defecte.
 */

namespace MacLink {

struct Stats {
    bool     valid;
    float    cpu;
    float    mem;
    float    disk;
    float    bat;
    float    up;         /* MB/s pujada */
    float    dn;         /* MB/s baixada */
    float    load;       /* load average 1 min */
    float    temp;       /* temperatura exterior (graus C) */
    int8_t   chg;        /* 1 carregant, 0 descarregant, -1 desconegut */
    int8_t   wcode;      /* codi WMO del temps (meteo) */
    int8_t   isDay;      /* 1 = dia, 0 = nit */
    int8_t   dsp;        /* 1 = pantalla del Mac encesa, 0 = dormida, -1 = ? */
    int8_t   dark;       /* 1 = Mac en mode fosc, 0 = clar, -1 = desconegut */
    uint32_t idleS;      /* segons que fa que el Mac no rep cap input */
    uint32_t uptimeS;    /* segons ences */
    char     host[40];
    char     timeStr[8]; /* "HH:MM" */
    char     dateStr[12];/* "11/10" */
    char     wday[8];    /* "dl".."dg" o "Sat" */
    uint32_t lastMs;     /* millis() de l'ultima linia 'S' */
};

struct Button {
    char id[24];
    char label[16];
    char icon[20];   /* nom de la icona a /icons/<icon>.bin ("" = sense icona) */
    char keys[24];   /* combinacio de tecles BLE ("" = comanda al Mac pel serie) */
};

/* Una PANTALLA: te el seu nom, la seva icona, el tipus de disposicio i els
 * seus gadgets (files d'estat) i botons. */
struct Page {
    char   name[16];
    char   icon[20];
    char   layout[10];                       /* "status" (amb gadgets) | "buttons" */
    char   apps[MAX_PAGE_APPS][APP_ID_MAX];  /* apps que obren aquesta pantalla */
    int    appCount;
    char   widgets[MAX_PAGE_WIDGETS][12];
    int    widgetCount;
    Button buttons[MAX_PAGE_BUTTONS];
    int    buttonCount;
};

struct Config {
    char orientation[2];                     /* "v" (320x480) o "h" (480x320) */
    uint8_t theme;                           /* index del tema de colors */
    /* Tema automatic: segueix el mode clar/fosc del Mac. Amb themeAuto=1 el
     * tema surt de themeDark o themeLight (i 'theme' queda com el d'emergencia,
     * quan encara no sabem com te el Mac l'aparença). */
    uint8_t themeAuto;                       /* 1 = segons el Mac */
    uint8_t themeDark;                       /* tema amb el Mac en fosc */
    uint8_t themeLight;                      /* tema amb el Mac en clar */
    uint16_t standbyS;                       /* s sense tocar -> repos (0 = mai) */
    uint16_t idleMin;                        /* min inactiu al Mac -> rellotge (0 = mai) */
    char nav[8];                             /* "both" | "bar" | "swipe" | "off" */
    Page pages[MAX_PAGES];
    int  pageCount;
};

/* Carrega la configuracio de la NVS (o la per defecte) i envia el 'H'. */
void begin();

/* Processa una linia del port serie (sense '\n').
 * Retorna true si era una linia del Mac ('S ' / 'OK' / 'CFG '); false si no
 * ho era (aleshores el cridador pot tractar-la com una comanda de consola). */
bool processLine(char* line);

const Stats&  stats();
const Config& config();

/* Hi ha enllac? (ha arribat alguna linia 'S' fa menys de LINK_TIMEOUT_MS). */
bool linkUp();

/* Nombre de linies d'estadistiques rebudes (es un comptador que va pujant).
 * Serveix per saber si ha arribat una mostra nova. */
uint32_t statsSeq();

/* El widget 'id' esta actiu a la configuracio? */
bool isWidgetEnabled(const char* id);
/* Envia 'H' al Mac (handshake / reinici de l'enllac). */
void sendHello();

/* Envia 'C <id>' al Mac (boto premut). */
void sendCommand(const char* id);

/* Demana al Mac de canviar un ajust des de la pantalla: 'X <clau>=<valor>'.
 * Claus: theme, orient, standby, bright. */
void sendSet(const char* key, const char* value);

/* --- Launcher: apps obertes al Mac (les envia el Mac amb 'L a|b|c') ------
 * Cada app pot portar la seva icona darrere un '=':  'L Finder=finder|Safari=safari'.
 * Les que no en porten surten nomes amb el nom. */
static constexpr int MAX_APPS = 15;

int         appCount();
const char* appName(int index);
/* Nom de la icona de l'app 'index' ("" si no en te). */
const char* appIcon(int index);

/* true un sol cop despres que el Mac hagi actualitzat la llista d'apps. */
bool takeAppsChanged();

/* --- Pestanyes del navegador (les envia el Mac amb 'T nom=icona|...') ------
 * La pantalla de tipus "tabs" mostra les pestanyes obertes del navegador que te
 * el focus, com a botons amb el seu favicon. Com les apps del launcher, es una
 * sola llista (el Mac ja les filtra: nomes envia les del navegador actiu).
 * En tocar-ne una, la placa envia 'C tab:N' (N, 0-based) i el Mac la porta al
 * davant. */
static constexpr int MAX_TABS = 15;         /* pestanyes visibles */

int         tabCount();
const char* tabName(int index);             /* index 0-based */
/* Nom de la icona (favicon) de la pestanya 'index' ("" si no en te). */
const char* tabIcon(int index);

/* true un sol cop despres que el Mac hagi actualitzat la llista de pestanyes. */
bool takeTabsChanged();

/* true si el Mac ja ens ha enviat alguna llista de pestanyes (encara que fos
 * buida). Serveix per no ensenyar la pantalla de "carregant" per sempre quan
 * el navegador no te cap pestanya oberta. */
bool tabsReceived();


/* --- Favorits dels navegadors (els envia el Mac amb 'F nom=icona|...') -----
 * Es la barra de favorits dels navegadors (Safari, Chrome, Edge, Brave,
 * Firefox...): el Mac la llegeix dels fitxers dels navegadors i l'envia amb el
 * favicon de cada lloc. La pantalla de tipus "favs" els mostra com a botons,
 * igual que les pestanyes. En tocar-ne un, la placa envia 'C fav:N' (N,
 * 0-based) i el Mac obre aquella URL al navegador de sempre. */
static constexpr int MAX_FAVS = 15;         /* favorits visibles */

int         favCount();
const char* favName(int index);             /* index 0-based */
/* Nom de la icona (favicon) del favorit 'index' ("" si no en te). */
const char* favIcon(int index);

/* true un sol cop despres que el Mac hagi actualitzat la llista de favorits. */
bool takeFavsChanged();

/* true si el Mac ja ens ha enviat la barra de favorits (encara que fos buida):
 * sense aixo, qui no tingui cap favorit es quedaria amb la pantalla de
 * "carregant" per sempre. */
bool favsReceived();


/* --- Previsio del temps (3 dies) ------------------------------------------ */
struct ForecastDay {
    int8_t code;   /* codi WMO */
    int8_t tmax;   /* graus C */
    int8_t tmin;
};
static constexpr int MAX_FORECAST = 3;

int                 forecastCount();
const ForecastDay&  forecast(int index);

/* --- Agenda: proper esdeveniment del Mac --------------------------------- */
const char* nextEvent();

/* --- Avisos del Mac (notificacions) --------------------------------------- */
/* El Mac els envia com 'N aplicacio|titol|cos' (tots els camps poden ser
 * buits). Es mostren com un baner a dalt de la pantalla, igual que fa macOS. */
struct Notice {
    char app[20];
    char title[44];
    char body[84];
};

/* Retorna l'avis pendent un sol cop, o nullptr si no n'hi ha cap. */
const Notice* takeNotice();

/* --- Aplicacio que te el focus al Mac ('A bundle|nom') -------------------- */
const char* frontAppBundle();
const char* frontAppName();

/* true un sol cop cada vegada que el Mac canvia d'aplicacio. */
bool takeAppChanged();

/* Torna a la configuracio per defecte (i la desa). */
void resetConfig();

/* true un sol cop despres de rebre una configuracio nova (o un reset). */
bool takeConfigChanged();

}  // namespace MacLink
