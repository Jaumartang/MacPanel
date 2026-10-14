#pragma once

#include <stdint.h>

/*
 * keys.h - Teclat Bluetooth (BLE HID).
 *
 * L'ESP32 classic (WROOM-32E) NO te USB natiu: el port USB de la placa va al
 * xip CH340, aixi que no pot fer d'HID per USB. El que si pot fer es
 * presentar-se com a TECLAT BLUETOOTH: el Mac s'hi emparella un cop i despres
 * els botons envien "tecles de debo" (volum, mitjans, copiar/enganxar,
 * combinacions...). Aixi surt el requadre del volum del macOS, funciona a
 * qualsevol aplicacio i no cal cap permis especial.
 *
 * Els botons amb una accio de tipus 'keys' (p.ex. "cmd+c") s'envien per aqui
 * en comptes de manar una comanda al Mac pel port serie.
 */

namespace Keys {

/* Inicia el teclat Bluetooth (idempotent). */
void begin();

/* Esta iniciat? */
bool started();

/* Hi ha el Mac emparellat i connectat? */
bool connected();

/* Envia una combinacio: "cmd+c", "media_volumeup", "a", "f5", "shift+cmd+z"... */
/* Llista de noms de tecles pel port serie (comanda 'tecles'). */
void printList();

void send(const char* spec);

}  // namespace Keys
