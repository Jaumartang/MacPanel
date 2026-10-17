#include <Arduino.h>

#include <mbedtls/base64.h>

#include <stdlib.h>
#include <string.h>

#include "panel_config.h"
#include "display.h"
#include "history.h"
#include "touch.h"
#include "led.h"
#include "sdcard.h"
#include "keys.h"
#include "icons.h"
#include "net.h"
#include "maclink.h"
#include "ui.h"

/*
 * main.cpp - Mac Panel
 *
 * Pantalla d'estat del Mac (CPU, RAM, disc, bateria, xarxa...) i graella de
 * botons (shortcuts) que executen accions al Mac. Tot pel port serie USB:
 *
 *   Mac  -> ESP32 :  S cpu=.. mem=.. ...        (estadistiques)
 *                    CFG {"w":[...],"b":[...]} (configuracio)
 *                    OK Mac-Panel v1           (handshake)
 *   ESP32 -> Mac  :  H                          (hola)
 *                    C <id>                     (boto premut)
 *                    A                          (ack de configuracio)
 *
 * El bucle es no bloquejant (tret del calibratge, que es un proces explicit).
 * La configuracio es desa a la NVS: la pantalla funciona igual sense el Mac.
 */

namespace {

/* Buffer del lector serie: prou gran per a les linies d'estadistiques del Mac
 * (que son les mes llargues) i per a les comandes de consola. */
char     gLine[MACLINE_MAX];
uint16_t gLineLen = 0;

/* Estat del boto premut: viu a la UI (Ui::touch()), que es qui tambe gestiona
 * el toc simulat de la consola. Aqui nomes hi ha el que es de main. */
bool     gLastLink   = false;
uint32_t gHeapTimer  = 0;

/* LED RGB: verd = enllac amb el Mac; vermell = sense Mac. */
void updateLed(bool link)
{
    if (link) {
        Led::setRgb(0, 60, 0);
    } else {
        Led::setRgb(60, 0, 0);
    }
}

void printHelp()
{
    Serial.println(F("[CON] comandes:"));
    Serial.println(F("  help          aquesta ajuda"));
    Serial.println(F("  info          estat del sistema i de l'enllac"));
    Serial.println(F("  bl <0-100>    brillantor de la retroil-luminacio"));
    Serial.println(F("  cal           calibratge del tactil (assistent a pantalla)"));
    Serial.println(F("  cfg           mostra la configuracio actual"));
    Serial.println(F("  page <n>      canvia de pantalla (0 = la primera)"));
    Serial.println(F("  hist          mostra l'historial dels grafics"));
    Serial.println(F("  menu          obre/tanca el menu de pantalles"));
    Serial.println(F("  apps          apps obertes al Mac i la seva icona (launcher)"));
    Serial.println(F("  favs          favorits dels navegadors i la seva icona (favs)"));
    Serial.println(F("  botons        geometria dels botons de la pantalla actual"));
    Serial.println(F("  captura       envia una captura de la pantalla pel port serie"));
    Serial.println(F("  splash        torna a mostrar la pantalla d'inici"));
    Serial.println(F("  ajust <id>    prem un boto dels ajustos (ajust theme+)"));
    Serial.println(F("  toca <x> <y>  simula un toc a la pantalla (per provar)"));
    Serial.println(F("  tecla <nom>   envia una tecla pel Bluetooth (tecla kp_plus)"));
    Serial.println(F("  tecles        llista de noms de tecles disponibles"));
    Serial.println(F("  llisca x1 y1 x2 y2   simula un lliscament"));
    Serial.println(F("  reset         torna a la configuracio per defecte"));
    Serial.println(F("  restart       reinicia la placa"));
    Serial.println(F("  h             envia el handshake 'H' al Mac"));
}

void printInfo()
{
    Serial.printf("[SYS] chip=%s heap=%u maxAlloc=%u\n",
                  ESP.getChipModel(),
                  static_cast<unsigned>(ESP.getFreeHeap()),
                  static_cast<unsigned>(ESP.getMaxAllocHeap()));
    Serial.printf("[BL]  backlight=%u%%\n", static_cast<unsigned>(Display::backlight()));
    Serial.printf("[TOUCH] calibrated=%d\n", Touch::isCalibrated() ? 1 : 0);
    Serial.printf("[MAC] link=%d pantalles=%d\n",
                  MacLink::linkUp() ? 1 : 0, MacLink::config().pageCount);
    Ui::printStandbyState();
}

void printConfig()
{
    const MacLink::Config& c = MacLink::config();
    Serial.printf("[CFG] orientacio=%s  pantalles=%d\n", c.orientation, c.pageCount);
    Serial.printf("[CFG] tema=%u auto=%u fosc=%u clar=%u\n",
                  static_cast<unsigned>(c.theme),
                  static_cast<unsigned>(c.themeAuto),
                  static_cast<unsigned>(c.themeDark),
                  static_cast<unsigned>(c.themeLight));
    for (int i = 0; i < c.pageCount; ++i) {
        const MacLink::Page& p = c.pages[i];
        Serial.printf("[CFG]  %d. '%s' (%s) gadgets=%d botons=%d\n",
                      i, p.name, p.layout, p.widgetCount, p.buttonCount);
    }
}

/* Envia la pantalla pel port serie (RGB565 en base64, per franges). Serveix per
 * veure de debò com queda la pantalla sense haver-la de fotografiar: util per
 * comprovar colors, fonts i mides. Ho recull tools/captura_pantalla.py.
 *
 * Els buffers es reserven NOMES durant la captura: la DRAM de l'ESP32 va justa
 * i tenir-los sempre reservats no hi cap. */
void enviaCaptura()
{
    TFT_eSPI& t = Display::driver();
    const int W = Display::width();
    const int H = Display::height();
    constexpr int FILES = 16;                  /* 320x16x2 = 10 KB per frange */
    const size_t nbuf = static_cast<size_t>(W) * FILES;
    const size_t n64 = ((nbuf * 2 + 2) / 3) * 4 + 8;
    uint16_t* buf = static_cast<uint16_t*>(malloc(nbuf * 2));
    char* b64 = static_cast<char*>(malloc(n64));
    if (buf == nullptr || b64 == nullptr) {
        Serial.println(F("[SHOT] sense memoria per a la captura"));
        free(buf);
        free(b64);
        return;
    }
    const int franges = (H + FILES - 1) / FILES;
    Serial.printf("[SHOT] %d %d %d\n", W, H, franges);
    for (int f = 0; f < franges; ++f) {
        const int y0 = f * FILES;
        const int nf = (H - y0 < FILES) ? (H - y0) : FILES;
        t.readRect(0, y0, W, nf, buf);
        size_t n = 0;
        if (mbedtls_base64_encode(reinterpret_cast<unsigned char*>(b64), n64, &n,
                                  reinterpret_cast<const unsigned char*>(buf),
                                  static_cast<size_t>(W) * nf * 2) != 0) {
            Serial.println(F("[SHOT] error codificant"));
            break;
        }
        b64[n] = '\0';
        Serial.printf("[SHOT] %d %s\n", f, b64);
        delay(15);                             /* que el Mac pugui seguir-ho */
    }
    free(buf);
    free(b64);
    Serial.println(F("[SHOT] FI"));
}

void printConfig();

/* Despertar de la pantalla en un toc (definit mes avall, a prop de pollTouch).
 * La comanda de consola 'toca' tambe l'ha de fer servir: ha de comportar-se
 * exactament com un dit de debo. */
bool touchWake(bool pressed);

void handleCommand(char* cmd)
{
    while (*cmd == ' ') {
        ++cmd;  /* treu espais del davant */
    }
    if (*cmd == '\0') {
        return;
    }

    if (strcmp(cmd, "help") == 0) {
        printHelp();
    } else if (strcmp(cmd, "info") == 0) {
        printInfo();
    } else if (strcmp(cmd, "cfg") == 0) {
        printConfig();
    } else if (strcmp(cmd, "reset") == 0) {
        MacLink::resetConfig();
        Ui::layout();
        Serial.println(F("[CFG] configuracio per defecte restaurada"));
    } else if (strcmp(cmd, "h") == 0) {
        MacLink::sendHello();
        Serial.println(F("[MAC] handshake 'H' enviat"));
    } else if (strcmp(cmd, "cal") == 0) {
        Touch::calibrate();
        Ui::layout();
    } else if (strcmp(cmd, "restart") == 0) {
        Serial.println(F("[SYS] reiniciant..."));
        delay(120);
        ESP.restart();
    } else if (strncmp(cmd, "bl ", 3) == 0) {
        const int v = atoi(cmd + 3);
        Display::setBacklight(static_cast<uint8_t>(v));
        Serial.printf("[BL] %d %%\n", v);
    } else if (strncmp(cmd, "page ", 5) == 0) {
        Ui::setPage(atoi(cmd + 5));
        Serial.printf("[UI] pantalla -> %d\n", Ui::currentPage());
    } else if (strncmp(cmd, "tecla ", 6) == 0) {
        /* Envia una tecla pel Bluetooth, com si es premés un boto del teclat
         * numeric. Serveix per provar combinacions sense haver de tocar la
         * pantalla: 'tecla kp_plus', 'tecla cmd+c', 'tecla kp_7'. */
        Keys::send(cmd + 6);
        Serial.printf("[BT] tecla demanada: %s\n", cmd + 6);
    } else if (strcmp(cmd, "tecles") == 0) {
        Keys::printList();
    } else if (strcmp(cmd, "bt") == 0) {
        /* Estat del teclat Bluetooth (les proves hi esperen abans d'enviar
         * tecles: si no esta connectat, les primeres es perden). */
        Serial.printf("[BT] teclat %s (heap=%u)\n",
                      !Keys::started() ? "encara no engegat"
                      : (Keys::connected() ? "connectat al Mac"
                                           : "en marxa, sense connexio"),
                      static_cast<unsigned>(ESP.getFreeHeap()));
    } else if (strcmp(cmd, "apps") == 0) {
        /* Apps obertes al Mac tal com les veu la placa (per al launcher).
         * Serveix per comprovar que cada app te la seva icona a la SD. */
        const int n = MacLink::appCount();
        Serial.printf("[APP] %d apps obertes al Mac:\n", n);
        for (int i = 0; i < n; ++i) {
            const char* ic = MacLink::appIcon(i);
            Serial.printf("[APP] %2d  %-18s icona=%-18s %s\n", i,
                          MacLink::appName(i),
                          (ic[0] != '\0') ? ic : "(cap)",
                          (ic[0] == '\0') ? ""
                          : (Icons::exists(ic) ? "a la SD" : "FALTA A LA SD"));
        }
    } else if (strcmp(cmd, "favs") == 0) {
        /* Barra de favorits dels navegadors tal com la veu la placa (per a la
         * pantalla "favs"). Serveix per comprovar que cada favicon hi es. */
        const int n = MacLink::favCount();
        Serial.printf("[FAV] %d favorits%s:\n", n,
                      MacLink::favsReceived() ? "" : " (encara no n'hem rebuts)");
        for (int i = 0; i < n; ++i) {
            const char* ic = MacLink::favIcon(i);
            Serial.printf("[FAV] %2d  %-18s icona=%-18s %s\n", i,
                          MacLink::favName(i),
                          (ic[0] != '\0') ? ic : "(cap)",
                          (ic[0] == '\0') ? ""
                          : (Icons::exists(ic) ? "a la SD" : "FALTA A LA SD"));
        }
    } else if (strcmp(cmd, "botons") == 0) {
        /* Geometria dels botons de la pantalla actual: serveix per comprovar
         * que el toc hi cau a sobre (i, per tant, on cau el baner d'avisos). */
        Ui::printButtons();
    } else if (strcmp(cmd, "prova") == 0) {
        /* Pinta franges de colors CONEGUTS i les envia de seguida, per
         * comprovar que la lectura de la pantalla (readRect) es fiable. Es fa
         * tot en la mateixa comanda: si no, el bucle principal repintaria la
         * pantalla entremig i llegiriem una altra cosa. */
        TFT_eSPI& t = Display::driver();
        const int W = Display::width();
        const int H = Display::height();
        static const uint16_t colors[8] = {
            0x0000, 0xF800, 0x07E0, 0x001F, 0xFFFF, 0x8410, 0x0884, 0x06FE,
        };
        const int fh = H / 8;
        for (int i = 0; i < 8; ++i) {
            t.fillRect(0, i * fh, W, fh, colors[i]);
        }
        Serial.println(F("[PROVA] 8 franges pintades"));
        enviaCaptura();
    } else if (strcmp(cmd, "captura") == 0) {
        Serial.println(F("[SHOT] comanda rebuda"));
        enviaCaptura();
    } else if (strncmp(cmd, "ajust ", 6) == 0) {
        /* Executa una accio dels ajustos de la pantalla, com si s'hagues premut
         * el boto: 'ajust theme+', 'ajust themeauto', 'ajust bright+'. Serveix
         * per provar-los sense tocar la pantalla. */
        char id[24];
        snprintf(id, sizeof(id), "cfg:%s", cmd + 6);
        const bool fet = Ui::settingsAction(id);
        Serial.printf("[TEST] ajust '%s' -> %s\n", cmd + 6,
                      fet ? "fet" : "desconegut");
    } else if (strcmp(cmd, "splash") == 0) {
        /* Torna a mostrar la pantalla d'inici (la que surt en engegar). */
        Ui::splashBegin();
        Ui::splashStep(35, "tactil");
        Ui::splashStep(70, "targeta SD");
        Ui::splashEnd();
        Ui::layout();                   /* torna a pintar la interficie */
        Serial.println(F("[UI] pantalla d'inici mostrada"));
    } else if (strcmp(cmd, "pages") == 0) {
        printConfig();
    } else if (strncmp(cmd, "toca ", 5) == 0) {
        /* Simula un toc (prem i aixeca) per poder provar la interficie sense
         * tocar la pantalla: 'toca 15 15' = el boto de menu. */
        int tx = 0;
        int ty = 0;
        if (sscanf(cmd + 5, "%d %d", &tx, &ty) == 2) {
            Serial.printf("[TEST] toco (%d,%d)\n", tx, ty);
            /* Com un dit de debo: si la pantalla esta en repòs, el primer toc
             * nomes la desvetlla. */
            if (touchWake(true)) {
                Ui::touch(true, static_cast<int16_t>(tx), static_cast<int16_t>(ty));
            }
            delay(150);
            Ui::touch(false, static_cast<int16_t>(tx), static_cast<int16_t>(ty));
            Serial.printf("[TEST] menu=%d ajustos=%d pantalla=%d\n",
                          Ui::menuOpen() ? 1 : 0, Ui::settingsOpen() ? 1 : 0,
                          Ui::currentPage());
        }
    } else if (strncmp(cmd, "llisca ", 7) == 0) {
        /* Simula un lliscament: 'llisca x1 y1 x2 y2'. */
        int x1 = 0, y1 = 0, x2 = 0, y2 = 0;
        if (sscanf(cmd + 7, "%d %d %d %d", &x1, &y1, &x2, &y2) == 4) {
            Serial.printf("[TEST] llisco (%d,%d) -> (%d,%d)\n", x1, y1, x2, y2);
            if (touchWake(true)) {
                Ui::touch(true, static_cast<int16_t>(x1), static_cast<int16_t>(y1));
                for (int k = 1; k <= 5; ++k) {      /* passos, com un dit */
                    delay(30);
                    Ui::touch(true,
                              static_cast<int16_t>(x1 + (x2 - x1) * k / 5),
                              static_cast<int16_t>(y1 + (y2 - y1) * k / 5));
                }
            }
            delay(30);
            Ui::touch(false, static_cast<int16_t>(x2), static_cast<int16_t>(y2));
            Serial.printf("[TEST] menu=%d ajustos=%d pantalla=%d\n",
                          Ui::menuOpen() ? 1 : 0, Ui::settingsOpen() ? 1 : 0,
                          Ui::currentPage());
        }
    } else if (strcmp(cmd, "menu") == 0) {
        Ui::setMenuOpen(!Ui::menuOpen());
        Serial.printf("[UI] menu %s\n", Ui::menuOpen() ? "obert" : "tancat");
    } else if (strcmp(cmd, "hist") == 0) {
        for (int i = 0; i < History::SERIES_COUNT; ++i) {
            Serial.printf("[HIST] %-5s n=%3d  min=%6.1f  mitjana=%6.1f  max=%6.1f  ara=%6.1f\n",
                          History::name(i), History::count(i),
                          History::minValue(i), History::avgValue(i),
                          History::maxValue(i), History::lastValue(i));
        }
    } else {
        Serial.printf("[CON] comanda desconeguda: %s (prova 'help')\n", cmd);
    }
}

/* Linies amb bytes de control: en arrencar, el xip deixa anar soroll pel port
 * (a un baudrate diferent) i no son cap comanda. Els accents hi son permesos
 * (les etiquetes dels botons en porten). */
bool looksLikeText(const char* s)
{
    for (; *s != '\0'; ++s) {
        const unsigned char c = static_cast<unsigned char>(*s);
        if (c < 32 || c == 127) {
            return false;
        }
    }
    return true;
}

/* Processa una linia que arriba del Mac (o de la consola local) i, si era una
 * mostra d'estadistiques nova, l'afegeix a l'historial dels grafics.
 *
 * Es fa aqui (i no al bucle principal) perque, si arriben diverses linies
 * juntes, cada una compti: mirant nomes el rellotge del sistema es perdien
 * mostres. */
void processLineWithHistory(char* line)
{
    const uint32_t before = MacLink::statsSeq();
    if (!MacLink::processLine(line)) {
        handleCommand(line);
        return;
    }
    if (MacLink::statsSeq() != before) {
        History::push(MacLink::stats());
    }
}

/* Un unic lector del port serie: les linies del Mac van a MacLink, la resta a
 * la consola local. */
void pollSerial()
{
    while (Serial.available() > 0) {
        const char c = static_cast<char>(Serial.read());
        if (c == '\r') {
            continue;
        }
        if (c == '\n') {
            gLine[gLineLen] = '\0';
            if (gLineLen > 0 && looksLikeText(gLine)) {
                processLineWithHistory(gLine);
            }
            gLineLen = 0;
        } else if (gLineLen < MACLINE_MAX - 1) {
            gLine[gLineLen++] = c;
        }
    }
}

/* Primer pas d'un toc: desvetllar la pantalla (i, si cal, el Mac). Retorna
 * false si el toc s'ha consumit aqui i no ha d'arribar cap a la UI.
 *
 * Ho fem servir tant a pollTouch() com a la comanda de consola 'toca', perque
 * el toc simulat faci EXACTAMENT el mateix que un dit de debo. */
bool touchWake(bool pressed)
{
    if (!pressed) {
        return true;
    }

    /* Si estem a la pantalla de repòs (rellotge), el primer toc NOMES la treu:
     * no ha d'activar cap boto sense voler. */
    if (Ui::idleMode()) {
        Ui::setIdleMode(false);
        Ui::touchActivity();
        Ui::cancelPress();
        return false;
    }

    /* Si la pantalla esta en repos, el primer toc NOMES la desvetlla
     * (no activa cap boto). */
    if (!Ui::screenOn()) {
        Ui::touchActivity();
        Ui::cancelPress();
        return false;
    }

    Ui::touchActivity();
    return true;
}

/* Tocs: menu (☰) de dalt, menu desplegable, botons i accio. */
void pollTouch()
{
    const bool pressed = Touch::update();
    int16_t x = 0;
    int16_t y = 0;
    Touch::getCoords(x, y);

    if (!touchWake(pressed)) {
        return;
    }

    /* Menu, boto de menu, barra de navegacio, lliscament I BOTONS: tot ho porta
     * la UI. */
    Ui::touch(pressed, x, y);
}

/* Si algun boto fa servir tecles, encen el teclat Bluetooth. */
void ensureBt()
{
    static bool sBtStarted = false;
    if (sBtStarted) {
        return;                      /* ja esta en marxa */
    }

    const MacLink::Config& cfg = MacLink::config();
    bool needed = false;
    for (int i = 0; i < cfg.pageCount && !needed; ++i) {
        const MacLink::Page& p = cfg.pages[i];
        for (int j = 0; j < p.buttonCount; ++j) {
            if (p.buttons[j].keys[0] != '\0') {
                needed = true;
                break;
            }
        }
    }
    if (!needed) {
        return;
    }

    /* La pila de Bluetooth demana molta memoria CONTIGUA. Si no n'hi ha prou,
     * val mes deixar el teclat apagat que no pas quedar-se en bucle de
     * reinicis (new BLEAdvertising() no te torna: fa abort()). */
    const uint32_t maxBlock = ESP.getMaxAllocHeap();
    Serial.printf("[BT] memoria abans del Bluetooth: heap=%u maxAlloc=%u\n",
                  static_cast<unsigned>(ESP.getFreeHeap()),
                  static_cast<unsigned>(maxBlock));
    if (maxBlock < BT_MIN_FREE_HEAP) {
        Serial.println(F("[BT] falta memoria contigua: NO encenc el teclat"));
        return;
    }
    Keys::begin();
    sBtStarted = true;
}

}  // namespace

void setup()
{
    /* Buffer RX gran (per defecte en son 256): les linies de configuracio del
     * Mac ('CFG ...') poden fer centenars de bytes i, amb el buffer petit, es
     * perdien bytes mentre la pantalla es redibuixava -> la config arribava
     * trencada i es rebutjava. Cal cridar-ho ABANS de Serial.begin(). */
    Serial.setRxBufferSize(8192);
    Serial.begin(SERIAL_BAUD);
    delay(200);
    Serial.println();
    Serial.println(F("=== Mac Panel - pantalla d'estat del Mac ==="));
    Serial.printf("[SYS] chip=%s cores=%d heap=%u\n",
                  ESP.getChipModel(), ESP.getChipCores(),
                  static_cast<unsigned>(ESP.getFreeHeap()));

    Display::init();
    /* Pantalla d'inici: logo, nom del producte i barra de carrega. Cada pas de
     * la inicialitzacio la fa avançar, aixi que tambe serveix per veure que
     * esta fent mentre engega. */
    Ui::splashBegin();

    Led::begin();
    Ui::splashStep(12, "LED");
    Touch::init();
    Ui::splashStep(30, "tactil");
    Sd::begin();           /* targeta SD (icones de /icons) */
    Ui::splashStep(58, "targeta SD");

    MacLink::begin();      /* carrega la configuracio i envia 'H' */
    Ui::splashStep(82, "configuracio");
    History::begin();      /* historial buit per als grafics */
    Ui::splashStep(92, "historial");
    Net::begin();          /* WiFi (si hi ha credencials desades) */
    Ui::splashEnd();

    Ui::setStandbyMs(static_cast<uint32_t>(MacLink::config().standbyS) * 1000UL);
    Ui::begin();           /* dibuixa la pantalla */
    /* NOTA: el teclat Bluetooth NO s'encen aqui. Ocupa mes de 100 KB i deixaria
     * el heap massa just per llegir la configuracio que el Mac envia tot just
     * connectar-se. S'encen des del bucle, uns segons mes tard. */

    updateLed(false);
    printInfo();
    printHelp();

    gHeapTimer = millis();
}

void loop()
{
    pollSerial();          /* un unic lector: Mac + consola */

    /* Enllac per WiFi: atenem el client TCP i processem el que arriba. */
    Net::poll();
    /* Reaprofitem gLine per a la linia WiFi sempre que no hi hagi cap linia del
     * port serie a mig llegir: aixi no cal una segona memoria de 8 KB. */
    if (gLineLen == 0) {
        while (Net::pollLine(gLine, sizeof(gLine))) {
            processLineWithHistory(gLine);
        }
    }

    pollTouch();

    const bool cfgChanged = MacLink::takeConfigChanged();
    if (cfgChanged) {
        Ui::setStandbyMs(static_cast<uint32_t>(MacLink::config().standbyS) * 1000UL);
        Serial.printf("[UI] repos de pantalla: %lus\n",
                      static_cast<unsigned long>(MacLink::config().standbyS));
        Ui::rebuild();
        /* El teclat Bluetooth NO s'encen aqui: es fa des del bucle, amb retard
         * (vegeu BT_START_DELAY_MS), perque necessita mes de 100 KB i deixaria
         * el heap massa just per llegir la configuracio que arriba del Mac. */
        Serial.println(F("[UI] pantalla reconstruida"));
    }

    /* Launcher: el Mac ha actualitzat la llista d'apps obertes. */
    if (MacLink::takeAppsChanged()) {
        Ui::onAppsChanged();
    }

    /* Pestanyes del navegador: el Mac ha actualitzat la llista de la pantalla
     * "tabs" actual. */
    if (MacLink::takeTabsChanged()) {
        Ui::onTabsChanged();
    }

    /* Favorits dels navegadors: el Mac ha actualitzat la barra de favorits de
     * la pantalla "favs" actual. */
    if (MacLink::takeFavsChanged()) {
        Ui::onFavsChanged();
    }

    /* Avis del Mac (notificacions). */
    const MacLink::Notice* notice = MacLink::takeNotice();
    if (notice != nullptr) {
        Ui::showBanner(*notice);
    }
    Ui::updateBanner();

    /* Aplicacio activa: si el Mac canvia d'app (o acabem de rebre la
     * configuracio) i alguna pantalla te aquella app assignada, hi saltem sols:
     * son les dreceres d'aquella aplicacio. */
    const bool appChanged = MacLink::takeAppChanged();
    if ((appChanged || cfgChanged) && !Ui::idleMode()) {
        const int pg = Ui::pageForApp(MacLink::frontAppBundle());
        if (pg >= 0 && pg != Ui::currentPage()) {
            Ui::setPage(pg);
            Serial.printf("[UI] app '%s' -> pantalla %d\n",
                          MacLink::frontAppName(), pg);
        }
    }

    const bool link = MacLink::linkUp();
    if (link != gLastLink) {
        gLastLink = link;
        updateLed(link);
        Ui::invalidate();
        Serial.printf("[MAC] %s\n", link ? "enllac actiu" : "enllac perdut");
    }

    /* Pantalla de repòs: si el Mac fa estona que no rep cap input, passem al
     * rellotge amb la previsio (com el salvapantalles del Mac). Quan el Mac
     * torna a tenir activitat, en sortim tot sol. */
    const uint16_t idleMin = MacLink::config().idleMin;
    const bool idleWant = idleMin > 0 && link &&
                          MacLink::stats().idleS >=
                              static_cast<uint32_t>(idleMin) * 60UL;
    if (idleWant != Ui::idleMode()) {
        Ui::setIdleMode(idleWant);
    }

    /* Amb la pantalla apagada no cal repintar res: estalviem feina (i, si la
     * pantalla es torna a encendre, es repinta tot sencer). */
    if (Ui::screenOn()) {
        Ui::refresh(MacLink::stats(), link);
    }

    /* El teclat Bluetooth s'encen amb retard: ocupa mes de 100 KB i deixaria el
     * heap massa just per llegir la configuracio del Mac (vegeu panel_config.h). */
    if (millis() >= BT_START_DELAY_MS) {
        ensureBt();
    }

    /* Estat del teclat Bluetooth, nomes quan canvia. Serveix per saber si ja
     * es pot enviar res (les proves hi esperen) i per diagnosticar. */
    {
        static int8_t gBtLast = -2;
        const int8_t btNow = Keys::started() ? (Keys::connected() ? 1 : 0) : -1;
        if (btNow != gBtLast) {
            gBtLast = btNow;
            Serial.println(btNow < 0 ? F("[BT] teclat encara no engegat")
                           : (btNow ? F("[BT] teclat connectat al Mac")
                                    : F("[BT] teclat en marxa, esperant connexio")));
        }
    }

    /* El Mac ens diu si te la pantalla encesa (dsp=1/0): la nostra el segueix.
     * Aixi, si el Mac entra en repos, la pantalla tambe; i quan en surt,
     * s'encen sola. */
    if (MacLink::stats().dsp >= 0) {
        Ui::setMacAwake(MacLink::stats().dsp != 0);
    }
    Ui::updateStandby();

    if (millis() - gHeapTimer >= HEAP_LOG_INTERVAL_MS) {
        gHeapTimer = millis();
        Serial.printf("[SYS] up=%lus heap=%u maxAlloc=%u\n",
                      static_cast<unsigned long>(millis() / 1000),
                      static_cast<unsigned>(ESP.getFreeHeap()),
                      static_cast<unsigned>(ESP.getMaxAllocHeap()));
    }

    delay(5);
}
