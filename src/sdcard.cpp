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

    gSpi.begin(PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI, PIN_SD_CS);

    if (!SD.begin(PIN_SD_CS, gSpi, 20000000)) {
        Serial.println(F("[SD] no s'ha pogut muntar la targeta (hi ha una SD posada?)"));
        return false;
    }

    gMounted = true;
    Serial.printf("[SD] targeta muntada (CS=%d, SCK=%d, MISO=%d, MOSI=%d)\n",
                  PIN_SD_CS, PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI);
    return true;
}

bool isMounted()
{
    return gMounted;
}

}  // namespace Sd
