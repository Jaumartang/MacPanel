#pragma once

#include <stdint.h>

#include "maclink.h"

/*
 * ui.h - Interficie en pantalla, dibuixada amb primitives de TFT_eSPI i
 * generada DINAMICAMENT a partir de la configuracio del Mac.
 *
 * Disposicio (320x480 vertical):
 *   y 0..30        capcalera: hora · host · indicador LINK
 *   y 30..N        files d'estat (una per widget actiu)
 *   y N..480       graella de botons (shortcuts), 3 columnes
 *
 * Les files d'estat i la capcalera es repinten NOMES quan canvia el valor; els
 * botons es pinten un sol cop (o en premuts).
 */

namespace Ui {

/* Dibuixa tota la pantalla segons la configuracio actual. */
void begin();

/* Torna a calcular la disposicio i repintar (quan canvia la configuracio). */
void layout();

/* Igual que layout(), pero si a la pantalla actual encara li falten les dades
 * del Mac (launcher o pestanyes sense rebre), mostra la pantalla d'inici amb
 * el nom de la pantalla destí: aixi no es veu ni una pagina buida ni
 * parpelleigs mentre carrega. */
void rebuild();

/* Pantalla d'inici amb el nom de la pantalla que s'obrira quan arribin les
 * dades ("carregant «Pestanyes»..."). */
void splashLoading();

/* Actualitza capcalera i valors d'estat (nomes el que canvia). */
void refresh(const MacLink::Stats& s, bool linkUp);

/* Index del boto que hi ha sota (x,y), o -1 si no n'hi ha cap. */
int hitTest(int16_t x, int16_t y);

/* Boto de la pantalla actual (o nullptr si l'index no es valid). */
const MacLink::Button* buttonAt(int index);

/* --- Menu desplegable de pantalles (barra de dalt) ------------------------ */
bool menuOpen();
void setMenuOpen(bool open);

/* Pantalla actual i canvi de pantalla. */
int  currentPage();
void setPage(int index);

/* Pantalla de repòs (rellotge + previsio): surt tota sola quan el Mac fa
 * estona que no rep cap input. Qualsevol toc la treu. */
void setIdleMode(bool on);
bool idleMode();

/* Pantalla assignada a una aplicacio (bundle id), o -1 si no n'hi ha cap. */
int pageForApp(const char* bundle);

/* Gestiona un toc (premut/aixecat): menu, boto de menu, barra de navegacio,
 * lliscament I ELS BOTONS DE LA PANTALLA (premut, accio i feedback visual).
 * Retorna true si el toc l'ha consumit la propia UI. */
bool touch(bool pressed, int16_t x, int16_t y);

/* Cancel·la el boto que hi hagi premut (quan el toc s'ha fet servir per una
 * altra cosa: treure un avis, desvetllar la pantalla...). */
void cancelPress();

/* S'ha tocat el boto de menu (☰) de la capcalera? */
bool hitMenuButton(int16_t x, int16_t y);

/* Marca/desmarca un boto com a premut (feedback visual). */
void setPressed(int index, bool down);

/* Forca que el proper refresh repinti tot (en canviar d'estat d'enllac). */
void invalidate();

/* --- Repos de la pantalla ------------------------------------------------- */
/* Encen/apaga la pantalla (retroil-luminacio). Idempotent. */
void setScreenOn(bool on);
bool screenOn();

/* El Mac ha dit que esta despert/dormit (dsp=1/0). */
void setMacAwake(bool awake);

/* Temps d'inactivitat abans d'entrar en repos (ms). 0 = mai. */
void setStandbyMs(uint32_t ms);
uint32_t standbyMs();

/* Crida des del bucle: gestiona el repos per inactivitat. */
void updateStandby();

/* Hi ha hagut un toc: reinicia el comptador i, si cal, desperta la pantalla. */
void touchActivity();

/* --- Ajustos a la pantalla ------------------------------------------------ */
/* Executa una accio dels ajustos ('cfg:...'). Retorna true si l'ha gestionada. */
bool settingsAction(const char* id);

/* Hi ha els ajustos oberts? */
bool settingsOpen();
void openSettings();
void closeSettings();

/* Mostra un avis a la capcalera durant uns segons. */
void showBanner(const char* text);
/* Igual, pero amb l'avis complet (aplicacio + titol + cos). */
void showBanner(const MacLink::Notice& n);

/* S'ha de cridar al bucle: amaga l'avis quan toca. */
void updateBanner();
/* El baner es pot treure tocant la pantalla. */
bool bannerOn();
void dismissBanner();

/* --- Pantalla d'inici (splash) -------------------------------------------- */
/* Logo + nom del producte + barra de carrega. Es mostra mentre s'engega: cada
 * pas de la inicialitzacio fa avançar la barra. */
void splashBegin();
/* Avança la barra fins a 'pct' i canvia el text del pas. */
void splashStep(int pct, const char* pas);
/* Tanca la pantalla d'inici (deixa passar la interficie). */
void splashEnd();

/* El Mac ha actualitzat la llista d'apps: repinta si som al launcher. */
void onAppsChanged();

/* El Mac ha actualitzat les pestanyes del navegador: repinta si som a una
 * pantalla de tipus "tabs". */
void onTabsChanged();

}  // namespace Ui
