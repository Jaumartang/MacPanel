#pragma once

#include <stdint.h>

/*
 * icons.h - Icones dels botons, carregades de la SD.
 *
 * Cada icona es un fitxer /icons/<nom>.bin amb pixels RGB565 en big-endian,
 * quadrat i de ICON_PX x ICON_PX (vegeu include/panel_config.h). Els genera
 * l'eina tools/png2bin.py a partir dels PNG de Assets/icons/.
 *
 * Es guarda a la memoria l'ultima icona carregada: repintar el mateix boto
 * (per exemple en premut/alliberat) no torna a llegir la targeta.
 */

namespace Icons {

/* Hi ha la icona /icons/<nom>.bin a la SD? */
bool exists(const char* name);

/* Quantes icones hi ha a /icons (es compta un sol cop i es guarda). */
int count();

/* Dibuixa la icona amb l'angle superior esquerre a (x,y), mida ICON_PX.
 * Retorna false si no s'ha pogut carregar. */
bool draw(const char* name, int x, int y);

/* Dibuixa la icona centrada a (cx,cy) i escalada a 'size' px (<= ICON_PX).
 * Els pixels de color ICON_TRANSPARENT es pinten amb 'bg' (aixi les icones
 * queden bé sobre qualsevol fons: botons, targetes, menu...).
 * Retorna false si no s'ha pogut carregar. */
bool drawCentered(const char* name, int cx, int cy, int size, uint16_t bg);

/* --- Escriptura d'icones (pujades des del panell de control) -------------- */

/* Comenca a escriure /icons/<nom>.bin. Torna false si no hi ha SD. */
bool beginWrite(const char* name, uint32_t totalBytes);

/* Afegeix un tros: 'b64' es base64 dels bytes RGB565 big-endian. */
bool writeBase64Chunk(const char* b64);

/* Tanca el fitxer. Torna true si s'han rebut tots els bytes esperats. */
bool endWrite();

/* Esborra /icons/<nom>.bin. */
bool remove(const char* name);

}  // namespace Icons
