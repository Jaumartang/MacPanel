#include "maclink.h"

#include <Arduino.h>
#include <Preferences.h>
#include <SPIFFS.h>

#include <stdlib.h>
#include <string.h>

#include "panel_config.h"
#include "icons.h"
#include "net.h"

namespace {

/* Envia una linia de protocol pel port serie I pel WiFi (si hi ha client). */
void out(const char* s)
{
    Serial.println(s);
    Net::sendLine(s);
}

constexpr const char* kPrefsNamespace = "macpanel";
constexpr const char* kPrefsKey       = "cfg";   /* format vell (una sola clau) */

/* La NVS limita cada valor a ~4000 bytes: trossegem la configuracio. */
constexpr size_t kNvsChunk     = 1800;
constexpr int    kNvsMaxChunks = 12;             /* fins a ~21 KB */

MacLink::Stats  gStats;
MacLink::Config gConfig;
bool gConfigChanged = false;
uint32_t gStatsSeq  = 0;      /* comptador de linies d'estadistiques rebudes */

/* Apps obertes al Mac (per al launcher). */
char gApps[MacLink::MAX_APPS][20];
char gAppIcons[MacLink::MAX_APPS][20];
int  gAppCount = 0;
bool gAppsChanged = false;

/* Pestanyes del navegador (per a la pantalla "tabs"). El Mac envia 'T' amb les
 * pestanyes obertes del navegador que te el focus; cada una pot portar el
 * favicon darrere un '=' (com les apps del launcher). */
char gTabs[MacLink::MAX_TABS][28];
char gTabIcons[MacLink::MAX_TABS][20];
int  gTabCount = 0;
bool gTabsChanged = false;

/* Avis pendent de mostrar (notificacio del Mac). */
MacLink::Notice gNotice = {"", "", ""};
bool            gNoticeNew = false;

/* Aplicacio que te el focus al Mac. */
char gAppBundle[64] = "";
char gAppName[28]   = "";
bool gAppNew        = false;

/* Previsio del temps i agenda. */
MacLink::ForecastDay gForecast[MacLink::MAX_FORECAST];
int  gForecastCount = 0;
char gEvent[44] = "";

/* --- On es desa la configuracio -------------------------------------------
 * La NVS de l'ESP32 es petita (20 KB) i WiFi/Bluetooth ja n'ocupen bona part:
 * la configuracio de la pantalla (que pot fer varis KB) NO hi cap. Per aixo es
 * desa a SPIFFS (la taula de particions estandard en reserva 960 KB). Si
 * SPIFFS no estigues disponible, es faria servir la NVS com a pla B.
 */
constexpr const char* kFsPath = "/panel.json";
bool gFsReady = false;

bool fsBegin()
{
    if (gFsReady) {
        return true;
    }
    gFsReady = SPIFFS.begin(/*formatOnFail=*/true, "/spiffs", 10, "spiffs");
    Serial.printf("[MAC] SPIFFS %s\n", gFsReady ? "llest" : "NO disponible");
    return gFsReady;
}

void saveConfigJson(const char* json)
{
    const size_t len = strlen(json);

    if (fsBegin()) {
        File f = SPIFFS.open(kFsPath, FILE_WRITE);
        if (f) {
            const size_t n = f.print(json);
            f.close();
            if (n == len) {
                Serial.printf("[MAC] configuracio desada (%u bytes)\n",
                              static_cast<unsigned>(len));
                return;
            }
            Serial.println(F("[MAC] escriptura incompleta a SPIFFS"));
        } else {
            Serial.println(F("[MAC] no s'ha pogut obrir el fitxer de configuracio"));
        }
    }

    /* Pla B: la NVS, en trossos (cada valor hi te un limit de ~4000 bytes). */
    Preferences prefs;
    if (!prefs.begin(kPrefsNamespace, /*readOnly=*/false)) {
        Serial.println(F("[MAC] no s'ha pogut obrir la NVS per desar la config"));
        return;
    }
    const int chunks = static_cast<int>((len + kNvsChunk - 1) / kNvsChunk);
    if (chunks <= 0 || chunks > kNvsMaxChunks) {
        Serial.printf("[MAC] configuracio massa gran (%u bytes)\n",
                      static_cast<unsigned>(len));
        prefs.end();
        return;
    }
    char buf[kNvsChunk + 1];
    for (int i = 0; i < chunks; ++i) {
        const size_t off = static_cast<size_t>(i) * kNvsChunk;
        size_t n = len - off;
        if (n > kNvsChunk) {
            n = kNvsChunk;
        }
        memcpy(buf, json + off, n);
        buf[n] = '\0';
        char key[8];
        snprintf(key, sizeof(key), "cfg%d", i);
        prefs.putString(key, buf);
    }
    prefs.putInt("cfgn", chunks);
    prefs.end();
}

bool readConfigJson(char* out, size_t outSize)
{
    if (fsBegin() && SPIFFS.exists(kFsPath)) {
        File f = SPIFFS.open(kFsPath, FILE_READ);
        if (f) {
            const size_t n = f.readBytes(out, outSize - 1);
            f.close();
            out[n] = '\0';
            if (n > 0) {
                return true;
            }
        }
    }

    /* Pla B: la NVS. */
    Preferences prefs;
    /* Obrim en lectura-escriptura: crea l'espai si no existeix i evita
     * l'error 'nvs_open failed: NOT_FOUND' a la primera arrencada. */
    if (!prefs.begin(kPrefsNamespace, /*readOnly=*/false)) {
        return false;
    }
    const int chunks = prefs.getInt("cfgn", 0);
    if (chunks <= 0 || chunks > kNvsMaxChunks) {
        prefs.end();
        return false;
    }
    size_t total = 0;
    for (int i = 0; i < chunks; ++i) {
        char key[8];
        snprintf(key, sizeof(key), "cfg%d", i);
        if (!prefs.isKey(key)) {
            prefs.end();
            return false;
        }
        const String s = prefs.getString(key, "");
        const size_t n = s.length();
        if (total + n + 1 > outSize) {
            prefs.end();
            return false;
        }
        memcpy(out + total, s.c_str(), n);
        total += n;
    }
    out[total] = '\0';
    prefs.end();
    return total > 0;
}

/* --- Parser de la configuracio ---------------------------------------------
 * El parser es a src/cfg_parse.h. No fa servir gens de memoria dinamica: amb el
 * Bluetooth ences al heap hi queden pocs kilobytes i ArduinoJson no hi cabia
 * (calien ~10 KB i sovint no hi eren), cosa que obligava a reiniciar la placa.
 */
#include "cfg_parse.h"

/* Aplica un JSON de configuracio. Si 'persist', el desa. */
void applyConfig(const char* json, bool persist)
{
    /* Desem PRIMER: aixi, encara que despres hi hagues qualsevol problema, la
     * configuracio queda guardada i s'aplicara al proper reinici. */
    if (persist) {
        saveConfigJson(json);
    }

    if (!parseConfigJson(json, gConfig)) {
        Serial.println(F("[MAC] configuracio invalida"));
        return;
    }

    if (gConfig.pageCount == 0) {
        Serial.println(F("[MAC] cap pantalla a la configuracio"));
    }

    gConfigChanged = true;
    Serial.printf("[MAC] configuracio: %d pantalles (orientacio %s, tema %u)\n",
                  gConfig.pageCount, gConfig.orientation,
                  static_cast<unsigned>(gConfig.theme));
}
void applyDefaultConfig()
{
    applyConfig(DEFAULT_CFG_JSON, /*persist=*/false);
}

/* Omple gStats a partir de "cpu=.. mem=.. ..." (modifica el buffer). */
void parseStats(char* s)
{
    char* save = nullptr;
    for (char* tok = strtok_r(s, " ", &save); tok != nullptr;
         tok = strtok_r(nullptr, " ", &save)) {
        char* eq = strchr(tok, '=');
        if (eq == nullptr) {
            continue;
        }
        *eq = '\0';
        const char* k = tok;
        const char* v = eq + 1;
        if      (strcmp(k, "cpu") == 0)    { gStats.cpu  = atof(v); }
        else if (strcmp(k, "mem") == 0)    { gStats.mem  = atof(v); }
        else if (strcmp(k, "disk") == 0)   { gStats.disk = atof(v); }
        else if (strcmp(k, "bat") == 0)    { gStats.bat  = atof(v); }
        else if (strcmp(k, "up") == 0)     { gStats.up   = atof(v); }
        else if (strcmp(k, "dn") == 0)     { gStats.dn   = atof(v); }
        else if (strcmp(k, "load") == 0)   { gStats.load = atof(v); }
        else if (strcmp(k, "temp") == 0)   { gStats.temp = atof(v); }
        else if (strcmp(k, "wc") == 0)     { gStats.wcode = static_cast<int8_t>(atoi(v)); }
        else if (strcmp(k, "isd") == 0)    { gStats.isDay = static_cast<int8_t>(atoi(v)); }
        else if (strcmp(k, "date") == 0)   { strlcpy(gStats.dateStr, v, sizeof(gStats.dateStr)); }
        else if (strcmp(k, "wd") == 0)     { strlcpy(gStats.wday, v, sizeof(gStats.wday)); }
        else if (strcmp(k, "chg") == 0)    { gStats.chg  = static_cast<int8_t>(atoi(v)); }
        else if (strcmp(k, "dsp") == 0)    { gStats.dsp  = static_cast<int8_t>(atoi(v)); }
        else if (strcmp(k, "dk") == 0)     { gStats.dark = static_cast<int8_t>(atoi(v)); }
        else if (strcmp(k, "idl") == 0)    { gStats.idleS = strtoul(v, nullptr, 10); }
        else if (strcmp(k, "uptime") == 0) { gStats.uptimeS = strtoul(v, nullptr, 10); }
        else if (strcmp(k, "host") == 0)   { strlcpy(gStats.host, v, sizeof(gStats.host)); }
        else if (strcmp(k, "time") == 0)   { strlcpy(gStats.timeStr, v, sizeof(gStats.timeStr)); }
    }
    gStats.valid  = true;
    gStats.lastMs = millis();
    ++gStatsSeq;
}

}  // namespace

namespace MacLink {

void begin()
{
    gStats.valid   = false;
    gStats.chg     = -1;
    gStats.dsp     = -1;
    gStats.dark    = -1;
    gStats.idleS   = 0;
    gStats.lastMs  = 0;
    gStats.host[0] = '\0';
    gStats.timeStr[0] = '\0';

    /* El buffer del JSON es demana i s'allibera aqui mateix: aquests kilobytes
     * no es queden ocupats tota l'estona i la pila de Bluetooth (que ve tot
     * seguit) els pot fer servir per arrencar. */
    char* buf = static_cast<char*>(malloc(MACLINE_MAX));
    if (buf != nullptr) {
        if (readConfigJson(buf, MACLINE_MAX)) {
            applyConfig(buf, /*persist=*/false);
            Serial.println(F("[MAC] configuracio carregada"));
        } else {
            applyDefaultConfig();
            Serial.println(F("[MAC] configuracio per defecte"));
        }
        free(buf);
    } else {
        applyDefaultConfig();
        Serial.println(F("[MAC] sense memoria per a la configuracio"));
    }

    sendHello();
}

bool processLine(char* line)
{
    if (line[0] == 'S' && line[1] == ' ') {
        parseStats(line + 2);
        return true;
    }
    if (strncmp(line, "OK", 2) == 0) {
        Serial.printf("[MAC] handshake: %s\n", line);
        return true;
    }
    if (strncmp(line, "CFG ", 4) == 0) {
        applyConfig(line + 4, /*persist=*/true);
        out("A");  /* ack */
        return true;
    }

    /* --- Credencials WiFi: 'W ssid|contrasenya' -------------------------- */
    if (strncmp(line, "W ", 2) == 0) {
        char* bar = strchr(line + 2, '|');
        if (bar != nullptr) {
            *bar = '\0';
            Net::setCredentials(line + 2, bar + 1);
            out("A");
        } else {
            out("E");
        }
        return true;
    }

    /* --- Pujada d'icones des del panell de control ----------------------- */
    if (strncmp(line, "ICONPUT ", 8) == 0) {
        char name[24] = {0};
        unsigned long total = 0;
        if (sscanf(line + 8, "%23s %lu", name, &total) == 2) {
            out(Icons::beginWrite(name, total) ? "K" : "E");
        } else {
            out("E");
        }
        return true;
    }
    if (strncmp(line, "ICONCHUNK ", 10) == 0) {
        out(Icons::writeBase64Chunk(line + 10) ? "K" : "E");
        return true;
    }
    if (strcmp(line, "ICONDONE") == 0) {
        out(Icons::endWrite() ? "I" : "E");
        return true;
    }
    if (strncmp(line, "ICONDEL ", 8) == 0) {
        char name[24] = {0};
        if (sscanf(line + 8, "%23s", name) == 1) {
            out(Icons::remove(name) ? "I" : "E");
        } else {
            out("E");
        }
        return true;
    }

    /* --- Llista d'apps obertes (launcher) -------------------------------- */
    if (strncmp(line, "L ", 2) == 0) {
        gAppCount = 0;
        char* save = nullptr;
        for (char* tok = strtok_r(line + 2, "|", &save);
             tok != nullptr && gAppCount < MacLink::MAX_APPS;
             tok = strtok_r(nullptr, "|", &save)) {
            /* Cada element es 'nom' o 'nom=icona'. */
            char* igual = strchr(tok, '=');
            if (igual != nullptr) {
                *igual = '\0';
                strlcpy(gAppIcons[gAppCount], igual + 1, sizeof(gAppIcons[0]));
            } else {
                gAppIcons[gAppCount][0] = '\0';
            }
            strlcpy(gApps[gAppCount], tok, sizeof(gApps[0]));
            ++gAppCount;
        }
        gAppsChanged = true;
        return true;
    }

    /* --- Pestanyes del navegador: 'T Titol=favicon|Titol2=...' -------------- *
     * El Mac ja filtra: nomes envia les pestanyes del navegador que te el
     * focus. Els titols van netejats al Mac (sense '|' ni '='): aixi el primer
     * '=' separa sempre el titol del favicon. Una linia 'T' buida (= cap
     * pestanya) es valida i deixa la llista a zero. */
    if (strncmp(line, "T ", 2) == 0) {
        gTabCount = 0;
        char* save = nullptr;
        for (char* tok = strtok_r(line + 2, "|", &save);
             tok != nullptr && gTabCount < MacLink::MAX_TABS;
             tok = strtok_r(nullptr, "|", &save)) {
            char* igual = strchr(tok, '=');
            if (igual != nullptr) {
                *igual = '\0';
                strlcpy(gTabIcons[gTabCount], igual + 1, sizeof(gTabIcons[0]));
            } else {
                gTabIcons[gTabCount][0] = '\0';
            }
            strlcpy(gTabs[gTabCount], tok, sizeof(gTabs[0]));
            ++gTabCount;
        }
        gTabsChanged = true;
        return true;
    }

    /* --- Avis per a la pantalla: 'N aplicacio|titol|cos' ------------------ */
    if (strncmp(line, "N ", 2) == 0) {
        char* s = line + 2;
        /* Sense '|' tambe funciona: tot el text va al titol (avisos simples
         * com el de bateria baixa). */
        char* bar1 = strchr(s, '|');
        if (bar1 != nullptr) {
            *bar1 = '\0';
            char* bar2 = strchr(bar1 + 1, '|');
            if (bar2 != nullptr) {
                *bar2 = '\0';
                strlcpy(gNotice.body, bar2 + 1, sizeof(gNotice.body));
            } else {
                gNotice.body[0] = '\0';
            }
            strlcpy(gNotice.app, s, sizeof(gNotice.app));
            strlcpy(gNotice.title, bar1 + 1, sizeof(gNotice.title));
        } else {
            gNotice.app[0] = '\0';
            strlcpy(gNotice.title, s, sizeof(gNotice.title));
            gNotice.body[0] = '\0';
        }
        gNoticeNew = true;
        return true;
    }

    /* --- Aplicacio que te el focus: 'A bundle|nom' ------------------------ */
    if (strncmp(line, "A ", 2) == 0) {
        char* bar = strchr(line + 2, '|');
        if (bar != nullptr) {
            *bar = '\0';
            strlcpy(gAppName, bar + 1, sizeof(gAppName));
        } else {
            gAppName[0] = '\0';
        }
        strlcpy(gAppBundle, line + 2, sizeof(gAppBundle));
        gAppNew = true;
        return true;
    }

    /* --- Previsio del temps: 'F codi,max,min|codi,max,min|...' ----------- */
    if (strncmp(line, "F ", 2) == 0) {
        gForecastCount = 0;
        char* save = nullptr;
        for (char* tok = strtok_r(line + 2, "|", &save);
             tok != nullptr && gForecastCount < MacLink::MAX_FORECAST;
             tok = strtok_r(nullptr, "|", &save)) {
            int c = 0, mx = 0, mn = 0;
            if (sscanf(tok, "%d,%d,%d", &c, &mx, &mn) == 3) {
                gForecast[gForecastCount].code = static_cast<int8_t>(c);
                gForecast[gForecastCount].tmax = static_cast<int8_t>(mx);
                gForecast[gForecastCount].tmin = static_cast<int8_t>(mn);
                ++gForecastCount;
            }
        }
        gAppsChanged = true;   /* aprofitem el mateix senyal per repintar */
        return true;
    }

    /* --- Agenda: proper esdeveniment ------------------------------------- */
    if (strncmp(line, "E ", 2) == 0) {
        strlcpy(gEvent, line + 2, sizeof(gEvent));
        gAppsChanged = true;
        return true;
    }

    return false;
}

const Stats&  stats()  { return gStats; }
const Config& config() { return gConfig; }

bool linkUp()
{
    return gStats.valid && (millis() - gStats.lastMs) < LINK_TIMEOUT_MS;
}

uint32_t statsSeq()
{
    return gStatsSeq;
}

void sendHello()
{
    out("H");
}

void sendCommand(const char* id)
{
    char buf[40];
    snprintf(buf, sizeof(buf), "C %s", id);
    out(buf);
}

void sendSet(const char* key, const char* value)
{
    char buf[48];
    snprintf(buf, sizeof(buf), "X %s=%s", key, value);
    out(buf);
}

void resetConfig()
{
    applyConfig(DEFAULT_CFG_JSON, /*persist=*/true);
}

bool takeConfigChanged()
{
    const bool c = gConfigChanged;
    gConfigChanged = false;
    return c;
}

int appCount()
{
    return gAppCount;
}

const char* appName(int index)
{
    if (index < 0 || index >= gAppCount) {
        return "";
    }
    return gApps[index];
}

const char* appIcon(int index)
{
    if (index < 0 || index >= gAppCount) {
        return "";
    }
    return gAppIcons[index];
}

bool takeAppsChanged()
{
    const bool c = gAppsChanged;
    gAppsChanged = false;
    return c;
}

const Notice* takeNotice()
{
    if (!gNoticeNew) {
        return nullptr;
    }
    gNoticeNew = false;
    return &gNotice;
}

const char* frontAppBundle() { return gAppBundle; }
const char* frontAppName()   { return gAppName; }

bool takeAppChanged()
{
    if (!gAppNew) {
        return false;
    }
    gAppNew = false;
    return true;
}

int forecastCount()
{
    return gForecastCount;
}

const ForecastDay& forecast(int index)
{
    if (index < 0 || index >= gForecastCount) {
        index = 0;
    }
    return gForecast[index];
}

const char* nextEvent()
{
    return gEvent;
}

/* --- Pestanyes del navegador --------------------------------------------- */
int tabCount()
{
    return gTabCount;
}

const char* tabName(int index)
{
    if (index < 0 || index >= gTabCount) {
        return "";
    }
    return gTabs[index];
}

const char* tabIcon(int index)
{
    if (index < 0 || index >= gTabCount) {
        return "";
    }
    return gTabIcons[index];
}

bool takeTabsChanged()
{
    const bool c = gTabsChanged;
    gTabsChanged = false;
    return c;
}

}  // namespace MacLink
