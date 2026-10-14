#include "display.h"

#include <Arduino.h>
#include <TFT_eSPI.h>

#include "panel_config.h"
#include "pins.h"
#include "theme.h"

/* Garantia en temps de compilacio: TFT_eSPI ha d'haver carregat
 * include/tft_setup.h (els pins del E32R40T). Si salta aquest error, revisa que
 * include/tft_setup.h hi sigui i que '-I include' estigui a build_flags. */
#ifndef MP_TFT_SETUP
#error "TFT_eSPI no ha carregat include/tft_setup.h (pins de la placa)."
#endif

namespace {

TFT_eSPI tft = TFT_eSPI();

/* 0 = vertical 320x480. */
constexpr uint8_t kRotation = 0;

/* Retroil-luminacio: PWM al pin TFT_BL (canal 0 de LEDC). */
constexpr uint8_t  kBacklightChannel    = 0;
constexpr uint32_t kBacklightFrequency  = 5000;
constexpr uint8_t  kBacklightResolution = 8;  /* 0..255 */

bool gReady = false;
bool gBacklightReady = false;
uint8_t gBacklightPct = 100;

}  // namespace

namespace Display {

bool init()
{
    if (gReady) {
        return true;
    }

    tft.init();
    tft.setRotation(kRotation);
    tft.setSwapBytes(false);
    tft.fillScreen(Th::bg);

    gReady = true;
    setBacklight(100);

    Serial.printf("[GFX] ST7796S %ux%u a punt (HSPI, LCD_CS=%d, DC=%d, RST=%d)\n",
                  static_cast<unsigned>(SCREEN_W), static_cast<unsigned>(SCREEN_H),
                  PIN_LCD_CS, PIN_LCD_DC, PIN_LCD_RST);
    return true;
}

TFT_eSPI& driver()
{
    return tft;
}

uint16_t width()  { return static_cast<uint16_t>(tft.width()); }

uint16_t height() { return static_cast<uint16_t>(tft.height()); }

void setRotation(uint8_t rotation)
{
    tft.setRotation(rotation);
    tft.fillScreen(Th::bg);
}

void setBacklight(uint8_t percent)
{
    if (percent > 100) {
        percent = 100;
    }
    gBacklightPct = percent;

    const uint32_t maxDuty = (1UL << kBacklightResolution) - 1UL;
    const uint32_t level   = BL_ACTIVE_LOW ? (100u - percent) : percent;
    const uint32_t duty    = (level * maxDuty) / 100UL;

    if (!gBacklightReady) {
        ledcSetup(kBacklightChannel, kBacklightFrequency, kBacklightResolution);
        ledcAttachPin(TFT_BL, kBacklightChannel);
        gBacklightReady = true;
    }
    ledcWrite(kBacklightChannel, duty);
}

uint8_t backlight()
{
    return gBacklightPct;
}

}  // namespace Display
