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
/* Buffer per a la substitucio del transparent (mateixa mida que la icona).
 * Ja no cal escalar: tot es 1:1 a 32 px. */
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
/* Nom i camins del fitxer que s'esta rebent: escrivim a un temporal i nome s
 * el posem al seu lloc quan la icona arriba sencera (aixi una pujada que falla
 * no trenca la icona que ja hi havia). */
char gWriteName[24] = {0};
char gWritePath[48] = {0};
char gTmpPath[48]   = {0};

void iconPath(char* out, size_t n, const char* name)
{
    snprintf(out, n, "/icons/%s.bin", name);
}

/* Mida exacta d'una icona: 32x32 px x 2 bytes (RGB565) = 2048. */
static constexpr uint32_t ICON_BIN_BYTES =
    static_cast<uint32_t>(ICON_PX * ICON_PX * 2);

/* Nom del fitxer temporal on es rep una icona abans de posar-la al seu lloc. */
static constexpr const char* ICON_TMP = "_rebut";

/* Nom segur per a la SD: nomes [A-Za-z0-9_.-], sense '/' ni '..'. */
bool nomSegur(const char* name)
{
    if (name == nullptr || name[0] == '\0') {
        return false;
    }
    if (strstr(name, "..") != nullptr || strchr(name, '/') != nullptr) {
        return false;
    }
    for (const char* p = name; *p != '\0'; ++p) {
        const char c = *p;
        const bool ok = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
                        (c >= '0' && c <= '9') || c == '_' || c == '.' ||
                        c == '-';
        if (!ok) {
            return false;
        }
    }
    return true;
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
    if (!nomSegur(name) || !Sd::isMounted()) {
        return false;
    }
    char path[48];
    iconPath(path, sizeof(path), name);
    if (!SD.exists(path)) {
        return false;
    }
    /* Tambe comprovem la MIDA: si a la SD hi ha un .bin d'una versio antiga
     * (64x64 = 8192 B), no el donem per bo. Aixi el boto surt amb el text en
     * lloc de quedar-se amb una icona que no es pot carregar, i el Mac sap que
     * l'ha de tornar a pujar. */
    File f = SD.open(path, FILE_READ);
    if (!f) {
        return false;
    }
    const size_t sz = f.size();
    f.close();
    return sz == ICON_BIN_BYTES;
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
    /* 1:1, sense escalat: la icona ja es de ICON_PX (32) i 'size' tambe ho es.
     * Nomes substituim el transparent pel fons: cap deformacio. */
    if (size != ICON_PX) {
        size = ICON_PX;
    }

    TFT_eSPI& t = Display::driver();

    /* 1:1 sense escalat: substitueix el transparent (magenta) pel fons sense
     * tocar la cau. */
    const uint16_t trans = gira(ICON_TRANSPARENT);
    const uint16_t fons  = gira(bg);
    for (int dy = 0; dy < size; ++dy) {
        const uint16_t* row = &gBuf[dy * ICON_PX];
        uint16_t* out = &gScaled[dy * size];
        for (int dx = 0; dx < size; ++dx) {
            const uint16_t c = row[dx];
            out[dx] = (c == trans) ? fons : c;
        }
    }
    t.pushImage(cx - size / 2, cy - size / 2, size, size, gScaled);
    return true;
}

/* --- Escriptura d'icones (pujades des del panell de control) -------------- */

bool beginWrite(const char* name, uint32_t totalBytes)
{
    if (!nomSegur(name) || !Sd::isMounted()) {
        return false;
    }
    /* Totes les icones son de 32x32 RGB565: rebutgem qualsevol altra mida
     * (p. ex. .bin antics de 64x64 = 8192 bytes). */
    if (totalBytes != ICON_BIN_BYTES) {
        Serial.printf("[ICO] '%s': mida rebutjada (%lu bytes, calen %lu)\n",
                      name, static_cast<unsigned long>(totalBytes),
                      static_cast<unsigned long>(ICON_BIN_BYTES));
        return false;
    }
    if (gWriteFile) {
        gWriteFile.close();
    }

    if (!SD.exists("/icons")) {
        SD.mkdir("/icons");
    }

    /* Escrivim a un fitxer TEMPORAL i, nomes quan la icona arriba sencera, la
     * posem al seu lloc. Si la pujada falla a mig cami (l'ESP32 es queda sense
     * memoria, es perd un tros...), la icona que ja hi havia NO es perd: abans
     * es trencava el fitxer bo i el boto es quedava sense icona per sempre. */
    strlcpy(gWriteName, name, sizeof(gWriteName));
    iconPath(gWritePath, sizeof(gWritePath), name);
    iconPath(gTmpPath, sizeof(gTmpPath), ICON_TMP);
    if (SD.exists(gTmpPath)) {             /* per si n'havia quedat un */
        SD.remove(gTmpPath);
    }

    gWriteFile = SD.open(gTmpPath, FILE_WRITE);
    if (!gWriteFile) {
        Serial.printf("[ICO] no s'ha pogut crear %s\n", gTmpPath);
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
    if (ok && gWritePath[0] != '\0') {
        /* Ja esta sencera: la posem al seu lloc. */
        if (SD.exists(gWritePath)) {
            SD.remove(gWritePath);
        }
        if (!SD.rename(gTmpPath, gWritePath)) {
            Serial.println(F("[ICO] no s'ha pogut reanomenar la icona"));
            SD.remove(gTmpPath);
        }
    } else if (SD.exists(gTmpPath)) {
        /* Incompleta: la llencem i deixem la que hi havia. */
        SD.remove(gTmpPath);
    }
    gWritten    = 0;
    gWriteTotal = 0;
    return ok;
}

bool remove(const char* name)
{
    if (!nomSegur(name) || !Sd::isMounted()) {
        return false;
    }
    char path[48];
    iconPath(path, sizeof(path), name);
    gCacheValid = false;
    return SD.remove(path);
}

}  // namespace Icons
