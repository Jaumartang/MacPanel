#include "touch.h"

#include <Arduino.h>
#include <Preferences.h>
#include <TFT_eSPI.h>

#include "panel_config.h"
#include "display.h"

namespace {

/* NVS (Preferences): l'espai de noms admet 15 caracters com a maxim. */
constexpr const char* kPrefsNamespace = "mp_touch";
constexpr uint16_t kCalibrationMagic = 0x7A11;  /* marca de calibracio propia */

/* Rang cru per defecte (mesurat en aquesta placa). Nota: l'eix Y va INVERTIT
 * (tocar a dalt dona un valor cru mes gran). Aixi el tactil ja funciona sense
 * calibrar; la calibracio fina el sobreescriu. */
constexpr int32_t kDefXmin = 300;
constexpr int32_t kDefXmax = 3480;
constexpr int32_t kDefYmin = 3800;
constexpr int32_t kDefYmax = 420;

bool gReady = false;
bool gCalibrated = false;      /* hi ha calibracio desada (diferent del defecte) */
bool gPressed = false;
int16_t gX = 0;
int16_t gY = 0;
bool gHasRawSample = false;
uint16_t gLastRawX = 0;
uint16_t gLastRawY = 0;
uint32_t gLastReadMs = 0;
uint16_t gPressureThreshold = TOUCH_DEFAULT_PRESSURE;

int32_t gXmin = kDefXmin;
int32_t gXmax = kDefXmax;
int32_t gYmin = kDefYmin;
int32_t gYmax = kDefYmax;

/* Orientacio del display (0..3). El tactil es fix al panell: si el display
 * gira, les coordenades tambe. */
uint8_t gRotation = 0;

void loadCalibration()
{
    Preferences prefs;
    /* Obrim en lectura-escriptura: crea l'espai si no existeix i evita
     * l'error 'nvs_open failed: NOT_FOUND' a la primera arrencada. */
    if (!prefs.begin(kPrefsNamespace, /*readOnly=*/false)) {
        return;
    }
    if (prefs.getUShort("magic", 0) == kCalibrationMagic) {
        gXmin = prefs.getInt("xmin", kDefXmin);
        gXmax = prefs.getInt("xmax", kDefXmax);
        gYmin = prefs.getInt("ymin", kDefYmin);
        gYmax = prefs.getInt("ymax", kDefYmax);
        gCalibrated = true;
    }
    prefs.end();
}

void saveCalibration()
{
    Preferences prefs;
    if (!prefs.begin(kPrefsNamespace, /*readOnly=*/false)) {
        Serial.println(F("[Touch] No s'ha pogut obrir la NVS per desar el calibratge"));
        return;
    }
    prefs.putUShort("magic", kCalibrationMagic);
    prefs.putInt("xmin", gXmin);
    prefs.putInt("xmax", gXmax);
    prefs.putInt("ymin", gYmin);
    prefs.putInt("ymax", gYmax);
    prefs.end();
}

/* Mapa lineal cru -> pixels (en ORIENTACIO VERTICAL) i despres gir segons
 * l'orientacio del display. */
void mapToScreen(uint16_t rawX, uint16_t rawY, int16_t& sx, int16_t& sy)
{
    const int32_t dx = gXmax - gXmin;
    const int32_t dy = gYmax - gYmin;

    int32_t px = (dx != 0) ? ((static_cast<int32_t>(rawX) - gXmin) * (SCREEN_W - 1)) / dx : 0;
    int32_t py = (dy != 0) ? ((static_cast<int32_t>(rawY) - gYmin) * (SCREEN_H - 1)) / dy : 0;
    if (px < 0) { px = 0; }
    if (px > SCREEN_W - 1) { px = SCREEN_W - 1; }
    if (py < 0) { py = 0; }
    if (py > SCREEN_H - 1) { py = SCREEN_H - 1; }

    int32_t x = px;
    int32_t y = py;
    switch (gRotation) {
        case 1:  x = py;                     y = (SCREEN_W - 1) - px; break;
        case 2:  x = (SCREEN_W - 1) - px;    y = (SCREEN_H - 1) - py; break;
        case 3:  x = (SCREEN_H - 1) - py;    y = px;                 break;
        default: break;
    }

    sx = static_cast<int16_t>(x);
    sy = static_cast<int16_t>(y);
}

void drawTarget(int x, int y)
{
    TFT_eSPI& t = Display::driver();
    t.drawCircle(x, y, 16, TFT_WHITE);
    t.fillCircle(x, y, 9, TFT_RED);
    t.drawFastHLine(x - 28, y, 56, TFT_WHITE);
    t.drawFastVLine(x, y - 28, 56, TFT_WHITE);
}

/* Espera un toc i en retorna el valor cru mig (per al calibratge). */
bool waitRawTouch(int16_t& rx, int16_t& ry, uint32_t timeoutMs)
{
    TFT_eSPI& tft = Display::driver();

    uint32_t t0 = millis();
    while ((millis() - t0) < timeoutMs) {
        if (tft.getTouchRawZ() >= gPressureThreshold) {
            break;
        }
        delay(10);
    }
    if ((millis() - t0) >= timeoutMs) {
        return false;
    }

    int32_t sx = 0;
    int32_t sy = 0;
    int n = 0;
    t0 = millis();
    while ((millis() - t0) < 1500) {
        if (tft.getTouchRawZ() >= gPressureThreshold) {
            uint16_t x = 0;
            uint16_t y = 0;
            tft.getTouchRaw(&x, &y);
            sx += x;
            sy += y;
            ++n;
        } else if (n >= 3) {
            break;  /* el dit ja s'ha aixecat */
        }
        delay(10);
    }
    if (n == 0) {
        return false;
    }
    rx = static_cast<int16_t>(sx / n);
    ry = static_cast<int16_t>(sy / n);

    /* Espera que s'aixequi el dit abans del seguent objectiu. */
    t0 = millis();
    while ((millis() - t0) < 2000 && tft.getTouchRawZ() >= gPressureThreshold) {
        delay(10);
    }
    return true;
}

/* Una lectura del panell (sense els delays de tft.getTouch()). */
void readPanel()
{
    TFT_eSPI& tft = Display::driver();

    if (tft.getTouchRawZ() < gPressureThreshold) {
        gPressed = false;
        gHasRawSample = false;  /* el proxim toc comencara de nou */
        return;
    }

    uint16_t rawX = 0;
    uint16_t rawY = 0;
    tft.getTouchRaw(&rawX, &rawY);

    /* Descarta mostres inestables (soroll electric del panell resistiu). */
    if (gHasRawSample &&
        (abs(static_cast<int32_t>(rawX) - static_cast<int32_t>(gLastRawX)) > TOUCH_RAW_TOLERANCE ||
         abs(static_cast<int32_t>(rawY) - static_cast<int32_t>(gLastRawY)) > TOUCH_RAW_TOLERANCE)) {
        return;  /* ens quedem amb l'ultima de bona */
    }
    gLastRawX = rawX;
    gLastRawY = rawY;
    gHasRawSample = true;

    mapToScreen(rawX, rawY, gX, gY);
    gPressed = true;
}

}  // namespace

namespace Touch {

void init()
{
    if (gReady) {
        return;
    }

    loadCalibration();
    Serial.printf("[Touch] mapa cru->pixels: x[%ld..%ld] y[%ld..%ld] (%s)\n",
                  static_cast<long>(gXmin), static_cast<long>(gXmax),
                  static_cast<long>(gYmin), static_cast<long>(gYmax),
                  gCalibrated ? "calibrat per l'usuari" : "per defecte");

    gReady = true;
    Serial.printf("[Touch] XPT2046 a punt (llindar z=%u, %s)\n",
                  static_cast<unsigned>(gPressureThreshold),
                  gCalibrated ? "calibratge carregat de la NVS" : "SENSE calibrar");
}

bool update()
{
    if (!gReady) {
        return false;
    }

    const uint32_t nowMs = millis();
    if (gLastReadMs != 0 && (nowMs - gLastReadMs) < TOUCH_MIN_READ_INTERVAL_MS) {
        return gPressed;  /* lectura massa recent: aprofitem l'anterior */
    }
    gLastReadMs = nowMs;
    readPanel();
    return gPressed;
}

bool isPressed()
{
    return update();
}

void getCoords(int16_t& x, int16_t& y)
{
    x = gX;
    y = gY;
}

bool isCalibrated()
{
    return gCalibrated;
}

void calibrate()
{
    if (!gReady) {
        Serial.println(F("[Touch] calibrate() s'ha de cridar despres d'init()"));
        return;
    }

    TFT_eSPI& t = Display::driver();
    const int m = 24;
    const int tx[4] = {m, SCREEN_W - 1 - m, m, SCREEN_W - 1 - m};
    const int ty[4] = {m, m, SCREEN_H - 1 - m, SCREEN_H - 1 - m};
    static const char* const ord[4] = {
        "1/4  dalt-esquerra", "2/4  dalt-dreta",
        "3/4  baix-esquerra", "4/4  baix-dreta"};
    int16_t rx[4] = {0, 0, 0, 0};
    int16_t ry[4] = {0, 0, 0, 0};

    for (int i = 0; i < 4; ++i) {
        t.fillScreen(TFT_BLACK);
        t.setTextDatum(TC_DATUM);
        t.setTextFont(2);
        t.setTextColor(TFT_WHITE, TFT_BLACK);
        t.drawString("CALIBRACIO DEL TACTIL", SCREEN_W / 2, 8);
        t.setTextColor(TFT_YELLOW, TFT_BLACK);
        t.drawString("Toca el cercle vermell", SCREEN_W / 2, SCREEN_H / 2 - 34);
        t.setTextColor(TFT_WHITE, TFT_BLACK);
        t.drawString(ord[i], SCREEN_W / 2, SCREEN_H / 2 + 2);
        drawTarget(tx[i], ty[i]);

        Serial.printf("[Touch] calibracio: toca %s\n", ord[i]);
        if (!waitRawTouch(rx[i], ry[i], 20000)) {
            Serial.println(F("[Touch] calibracio cancel.lada (no s'ha detectat el toc)"));
            t.fillScreen(TFT_BLACK);
            return;
        }
        Serial.printf("[Touch]   raw=(%d,%d)\n", static_cast<int>(rx[i]), static_cast<int>(ry[i]));
    }

    gXmin = (static_cast<int32_t>(rx[0]) + rx[2]) / 2;
    gXmax = (static_cast<int32_t>(rx[1]) + rx[3]) / 2;
    gYmin = (static_cast<int32_t>(ry[0]) + ry[1]) / 2;
    gYmax = (static_cast<int32_t>(ry[2]) + ry[3]) / 2;

    if (gXmax == gXmin || gYmax == gYmin) {
        Serial.println(F("[Touch] calibracio invalida (punts coincidents); no es desa"));
        t.fillScreen(TFT_BLACK);
        return;
    }

    saveCalibration();
    gCalibrated = true;
    Serial.printf("[Touch] calibracio nova OK: x[%ld..%ld] y[%ld..%ld]\n",
                  static_cast<long>(gXmin), static_cast<long>(gXmax),
                  static_cast<long>(gYmin), static_cast<long>(gYmax));
    t.fillScreen(TFT_BLACK);
}

void setPressureThreshold(uint16_t threshold)
{
    gPressureThreshold = threshold;
}

uint16_t pressureThreshold()
{
    return gPressureThreshold;
}

void setRotation(uint8_t rotation)
{
    gRotation = rotation & 0x03;
}

}  // namespace Touch
