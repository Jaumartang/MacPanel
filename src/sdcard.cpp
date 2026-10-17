#include "sdcard.h"

#include <Arduino.h>
#include <SD.h>
#include <SPI.h>

#include "pins.h"

namespace {

/* El LCD i el tactil van a HSPI; la SD te el seu propi bus (VSPI). */
SPIClass gSpi(VSPI);
bool gMounted = false;

}  // namespace

namespace Sd {

bool begin()
{
    if (gMounted) {
        return true;
    }

    /* La targeta triga una mica a estar a punt just despres d'engegar (el
     * regulador encara s'estabilitza i la SD fa la seva propia inicialitzacio):
     * val la pena reintentar-ho unes quantes vegades abans de donar-la per
     * perduda. Sense els reintents, un arrencada amb pressa deixava la placa
     * sense cap icona fins al proper reinici. */
    for (int intent = 0; intent < SD_INTENTS; ++intent) {
        if (intent > 0) {
            delay(SD_RETARD_MS);
        }
        gSpi.begin(PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI, PIN_SD_CS);
        if (SD.begin(PIN_SD_CS, gSpi, 20000000)) {
            gMounted = true;
            Serial.printf("[SD] targeta muntada (CS=%d, SCK=%d, MISO=%d, MOSI=%d)%s\n",
                          PIN_SD_CS, PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI,
                          (intent > 0) ? " [al 2n intent o mes]" : "");
            return true;
        }
    }

    Serial.println(F("[SD] no s'ha pogut muntar la targeta (hi ha una SD posada?)"));
    return false;
}

bool isMounted()
{
    return gMounted;
}

}  // namespace Sd
