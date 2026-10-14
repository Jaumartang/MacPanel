#include "led.h"

#include <Arduino.h>

#include "pins.h"

namespace {

/* Canals LEDC 1..3 (el 0 el reserva Display per a la retroil-luminacio). */
constexpr uint8_t  kChannelR = 1;
constexpr uint8_t  kChannelG = 2;
constexpr uint8_t  kChannelB = 3;
constexpr uint32_t kFrequency = 5000;
constexpr uint8_t  kResolution = 8;  /* 0..255 */

bool gReady = false;

/* Converteix un nivell logic (0..255) en duty LEDC, aplicant la inversio si el
 * LED es d'anode comu (actiu baix). */
uint32_t dutyFor(uint8_t logical)
{
    const uint32_t level = LED_ACTIVE_LOW ? (255u - logical) : logical;
    const uint32_t maxDuty = (1u << kResolution) - 1u;
    return level * maxDuty / 255u;
}

}  // namespace

namespace Led {

void begin()
{
    if (gReady) {
        return;
    }
    ledcSetup(kChannelR, kFrequency, kResolution);
    ledcSetup(kChannelG, kFrequency, kResolution);
    ledcSetup(kChannelB, kFrequency, kResolution);
    ledcAttachPin(PIN_LED_R, kChannelR);
    ledcAttachPin(PIN_LED_G, kChannelG);
    ledcAttachPin(PIN_LED_B, kChannelB);
    gReady = true;
    off();
}

void setRgb(uint8_t r, uint8_t g, uint8_t b)
{
    if (!gReady) {
        begin();
    }
    ledcWrite(kChannelR, dutyFor(r));
    ledcWrite(kChannelG, dutyFor(g));
    ledcWrite(kChannelB, dutyFor(b));
}

void off()
{
    setRgb(0, 0, 0);
}

}  // namespace Led
