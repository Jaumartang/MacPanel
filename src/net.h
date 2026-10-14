#pragma once

#include <stddef.h>

/*
 * net.h - Enllac per WiFi (alternativa al port serie).
 *
 * L'ESP32 es connecta a la xarxa WiFi de casa i obre un servidor TCP al port
 * 8771. El Mac hi connecta i fa servir EXACTAMENT el mateix protocol de linies
 * de text que pel port serie (S ..., CFG ..., C ..., etc.).
 *
 * Tambe s'anuncia per mDNS com a "macpanel.local", aixi el Mac no cal que
 * sàpiga la IP.
 *
 * Les credencials es desen a la NVS i s'hi poden posar des del panell de
 * control (el Mac les envia amb la linia 'W ssid|contrasenya').
 */

namespace Net {

/* Arrenca la WiFi amb les credencials desades (si n'hi ha). */
void begin();

/* Desa les credencials i s'hi connecta. */
void setCredentials(const char* ssid, const char* pass);

bool connected();

/* IP actual ("" si no esta connectat). */
const char* ip();

/* Aten el servidor TCP i llegeix el que arriba. Cridar sovint. */
void poll();

/* Linia rebuda del client TCP (sense '\n'). Torna false si no n'hi ha cap. */
bool pollLine(char* out, size_t outSize);

/* Envia una linia al client TCP (si n'hi ha). */
bool sendLine(const char* line);

}  // namespace Net
