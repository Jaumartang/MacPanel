#include "icons.h"

#include <Arduino.h>
#include <SD.h>
#include <TFT_eSPI.h>
#include <mbedtls/base64.h>

#include <string.h>

#include "panel_config.h"
#include "display.h"
#include "sdcard.h"

namespace {

/* Icona tal com ve de la SD (ICON_PX x ICON_PX, RGB565 big-endian). */
uint16_t gBuf[ICON_PX * ICON_PX];
/* Buffer per a l'escalat (mai mes gran que la icona). */
uint16_t gScaled[ICON_PX * ICON_PX];

char gCached[24] = {0};
bool gCacheValid = false;

/* El .bin es RGB565 en BIG-ENDIAN i pushImage envia els bytes tal com son (per
 * aixo els colors es veuen be). Pero al buffer, llegit com a uint16_t en una
 * maquina little-endian, cada valor queda amb els bytes girats: per comparar
 * amb el magenta o per escriure-hi un color cal girar-lo tambe. */
inline uint16_t gira(uint16_t v)
{
    return static_cast<uint16_t>((v >> 8) | (v << 8));
}

/* Escriptura d'icones pujades des del panell. */
File     gWriteFile;
uint32_t gWriteTotal = 0;
uint32_t gWritten    = 0;

void iconPath(char* out, size_t n, const char* name)
{
    snprintf(out, n, "/icons/%s.bin", name);
}

/* Carrega /icons/<name>.bin al buffer (amb cau d'una entrada). */
bool load(const char* name)
{
    if (name == nullptr || name[0] == '\0') {
        return false;
    }
    if (gCacheValid && strcmp(gCached, name) == 0) {
        return true;
    }
    if (!Sd::isMounted()) {
        return false;
    }

    char path[48];
    iconPath(path, sizeof(path), name);

    /* Comprovem que hi sigui abans d'obrir: si no, el VFS escriu un error al
     * log per cada intent (i en repintar molts botons embussaria el registre). */
    if (!SD.exists(path)) {
        return false;
    }

    File f = SD.open(path, FILE_READ);
    if (!f) {
        return false;
    }
    const size_t want = sizeof(gBuf);
    const size_t got  = f.read(reinterpret_cast<uint8_t*>(gBuf), want);
    f.close();

    if (got != want) {
        Serial.printf("[ICO] '%s': mida incorrecta (%u de %u bytes)\n",
                      name, static_cast<unsigned>(got), static_cast<unsigned>(want));
        return false;
    }

    strlcpy(gCached, name, sizeof(gCached));
    gCacheValid = true;
    return true;
}

}  // namespace

namespace Icons {

bool exists(const char* name)
{
    if (name == nullptr || name[0] == '\0' || !Sd::isMounted()) {
        return false;
    }
    char path[48];
    iconPath(path, sizeof(path), name);
    return SD.exists(path);
}

int count()
{
    /* Es compta un sol cop: recorrer la carpeta es lent i el nombre d'icones
     * no canvia mentre la placa esta engegada (nomes si es pugen del panell). */
    static int cache = -1;
    if (cache >= 0) {
        return cache;
    }
    if (!Sd::isMounted()) {
        return 0;
    }
    File dir = SD.open("/icons");
    if (!dir) {
        return 0;
    }
    int n = 0;
    for (;;) {
        File f = dir.openNextFile();
        if (!f) {
            break;
        }
        if (!f.isDirectory()) {
            ++n;
        }
        f.close();
    }
    dir.close();
    cache = n;
    return n;
}

bool draw(const char* name, int x, int y)
{
    if (!load(name)) {
        return false;
    }
    Display::driver().pushImage(x, y, ICON_PX, ICON_PX, gBuf);
    return true;
}

bool drawCentered(const char* name, int cx, int cy, int size, uint16_t bg)
{
    if (!load(name)) {
        return false;
    }
    if (size > ICON_PX) size = ICON_PX;
    if (size < 8)       size = 8;

    TFT_eSPI& t = Display::driver();

    /* Passem SEMPRE pel buffer d'escalat: aixi hi podem canviar el color
     * transparent (magenta) pel fons de destí sense tocar la cau. */
    const uint16_t trans = gira(ICON_TRANSPARENT);
    const uint16_t fons  = gira(bg);
    for (int dy = 0; dy < size; ++dy) {
        const int sy = dy * ICON_PX / size;
        const uint16_t* row = &gBuf[sy * ICON_PX];
        uint16_t* out = &gScaled[dy * size];
        for (int dx = 0; dx < size; ++dx) {
            const uint16_t c = row[dx * ICON_PX / size];
            out[dx] = (c == trans) ? fons : c;
        }
    }
    t.pushImage(cx - size / 2, cy - size / 2, size, size, gScaled);
    return true;
}

/* --- Escriptura d'icones (pujades des del panell de control) -------------- */

bool beginWrite(const char* name, uint32_t totalBytes)
{
    if (name == nullptr || name[0] == '\0' || !Sd::isMounted()) {
        return false;
    }
    if (gWriteFile) {
        gWriteFile.close();
    }

    if (!SD.exists("/icons")) {
        SD.mkdir("/icons");
    }

    char path[48];
    iconPath(path, sizeof(path), name);

    gWriteFile = SD.open(path, FILE_WRITE);   /* crea o trunca */
    if (!gWriteFile) {
        Serial.printf("[ICO] no s'ha pogut crear %s\n", path);
        return false;
    }

    gWriteTotal = totalBytes;
    gWritten    = 0;
    gCacheValid = false;   /* invalidem la cau: aquesta icona canvia */
    Serial.printf("[ICO] rebent '%s' (%lu bytes)...\n",
                  name, static_cast<unsigned long>(totalBytes));
    return true;
}

bool writeBase64Chunk(const char* b64)
{
    if (!gWriteFile) {
        return false;
    }

    static uint8_t buf[1400];
    size_t outLen = 0;
    const int rc = mbedtls_base64_decode(
        buf, sizeof(buf), &outLen,
        reinterpret_cast<const unsigned char*>(b64), strlen(b64));
    if (rc != 0) {
        return false;
    }

    const size_t n = gWriteFile.write(buf, outLen);
    gWritten += static_cast<uint32_t>(n);
    return n == outLen;
}

bool endWrite()
{
    if (!gWriteFile) {
        return false;
    }
    gWriteFile.flush();
    gWriteFile.close();

    const bool ok = (gWritten == gWriteTotal);
    Serial.printf("[ICO] icona desada: %lu/%lu bytes (%s)\n",
                  static_cast<unsigned long>(gWritten),
                  static_cast<unsigned long>(gWriteTotal),
                  ok ? "OK" : "INCOMPLETA");
    gWritten    = 0;
    gWriteTotal = 0;
    return ok;
}

bool remove(const char* name)
{
    if (name == nullptr || name[0] == '\0' || !Sd::isMounted()) {
        return false;
    }
    char path[48];
    iconPath(path, sizeof(path), name);
    gCacheValid = false;
    return SD.remove(path);
}

}  // namespace Icons
