#include "net.h"

#include <Arduino.h>
#include <ESPmDNS.h>
#include <Preferences.h>
#include <WiFi.h>

#include <string.h>

#include "panel_config.h"

namespace {

constexpr const char* kPrefsNs = "macpanel";
constexpr uint16_t    kPort    = 8771;
constexpr size_t      kLineMax = 512;

WiFiServer gServer(kPort);
WiFiClient gClient;
bool       gServerStarted = false;
char       gIp[20] = "";

/* Cua d'una linia (per no dependre de maclink des d'aqui). */
char   gLine[kLineMax];
size_t gLineLen = 0;
char   gReady[kLineMax];
bool   gHaveReady = false;

void loadCreds(char* ssid, size_t ns, char* pass, size_t np)
{
    Preferences p;
    p.begin(kPrefsNs, /*readOnly=*/true);
    strlcpy(ssid, p.getString("ssid", "").c_str(), ns);
    strlcpy(pass, p.getString("pass", "").c_str(), np);
    p.end();
}

}  // namespace

namespace Net {

void begin()
{
    char ssid[40] = {0};
    char pass[64] = {0};
    loadCreds(ssid, sizeof(ssid), pass, sizeof(pass));

    if (ssid[0] == '\0') {
        Serial.println(F("[NET] sense WiFi configurat (fes servir el panell de control)"));
        return;
    }

    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);        /* mes estable amb Bluetooth alhora */
    WiFi.begin(ssid, pass);
    Serial.printf("[NET] connectant a '%s'...\n", ssid);
}

void setCredentials(const char* ssid, const char* pass)
{
    Preferences p;
    p.begin(kPrefsNs, /*readOnly=*/false);
    p.putString("ssid", ssid ? ssid : "");
    p.putString("pass", pass ? pass : "");
    p.end();

    WiFi.disconnect(true);
    delay(150);
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    WiFi.begin(ssid, pass);
    Serial.printf("[NET] connectant a '%s'...\n", ssid ? ssid : "");
}

bool connected()
{
    return WiFi.status() == WL_CONNECTED;
}

const char* ip()
{
    return gIp;
}

void poll()
{
    if (!connected()) {
        return;
    }

    if (!gServerStarted) {
        gServer.begin();
        gServerStarted = true;
        strlcpy(gIp, WiFi.localIP().toString().c_str(), sizeof(gIp));
        if (MDNS.begin("macpanel")) {
            MDNS.addService("macpanel", "tcp", kPort);
        }
        Serial.printf("[NET] WiFi OK: IP %s  (macpanel.local:%u)\n", gIp, kPort);
    }

    /* Un sol client a la vegada. */
    if (!gClient || !gClient.connected()) {
        WiFiClient nc = gServer.available();
        if (nc) {
            gClient = nc;
            gLineLen = 0;
            gHaveReady = false;
            Serial.println(F("[NET] client connectat per WiFi"));
        }
        return;
    }

    while (gClient.available() > 0 && !gHaveReady) {
        const char c = static_cast<char>(gClient.read());
        if (c == '\r') {
            continue;
        }
        if (c == '\n') {
            gLine[gLineLen] = '\0';
            if (gLineLen > 0) {
                strlcpy(gReady, gLine, sizeof(gReady));
                gHaveReady = true;
            }
            gLineLen = 0;
        } else if (gLineLen < kLineMax - 1) {
            gLine[gLineLen++] = c;
        } else {
            gLineLen = 0;
        }
    }
}

bool pollLine(char* out, size_t outSize)
{
    if (!gHaveReady) {
        return false;
    }
    strlcpy(out, gReady, outSize);
    gHaveReady = false;
    return true;
}

bool sendLine(const char* line)
{
    if (!gClient || !gClient.connected()) {
        return false;
    }
    gClient.println(line);
    return true;
}

}  // namespace Net
