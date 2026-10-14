#include "ui.h"

#include <Arduino.h>
#include <ESP.h>
#include <TFT_eSPI.h>

#include <math.h>
#include <stdlib.h>
#include <string.h>

#include "panel_config.h"
#include "display.h"
#include "history.h"
#include "icons.h"
#include "keys.h"
#include "maclink.h"
#include "net.h"
#include "theme.h"
#include "touch.h"

/* Els colors del tema actual (es canvien des del panell de control). */
#define COL_BG     Th::bg
#define COL_BG2    Th::bg2
#define COL_CARD   Th::card
#define COL_EDGE   Th::edge
#define COL_TEXT   Th::text
#define COL_DIM    Th::dim
#define COL_ACCENT Th::accent
#define COL_OK     Th::ok
#define COL_WARN   Th::warn
#define COL_BAD    Th::bad
#define COL_BTN    Th::btn
#define COL_BTN_P  Th::btnP

/* Fonts suaus (FreeSans): les carrega TFT_eSPI amb LOAD_GFXFF (vegeu
 * include/tft_setup.h). S=petita (com la font 2), M=mitjana, B=gran. */
void setFontS(TFT_eSPI& t) { t.setFreeFont(&FreeSans9pt7b); }
void setFontM(TFT_eSPI& t) { t.setFreeFont(&FreeSansBold12pt7b); }
void setFontL(TFT_eSPI& t) { t.setFreeFont(&FreeSansBold18pt7b); }
void setFontB(TFT_eSPI& t) { t.setFreeFont(&FreeSansBold24pt7b); }

/* Les mateixes, pero triades per numero: 0 = la mes gran. Serveix per anar
 * provant mides fins que un text hi cap. */
void setFontN(TFT_eSPI& t, int n)
{
    switch (n) {
        case 0:  setFontB(t); break;
        case 1:  setFontL(t); break;
        case 2:  setFontM(t); break;
        default: setFontS(t); break;
    }
}

/* Escurça el text amb punts suspensius perque càpiga a 'maxW' pixels. Va
 * caràcter a caràcter per no partir mai un caràcter UTF-8 pel mig. */
void fitText(TFT_eSPI& t, const char* src, char* dst, size_t dstSize, int maxW)
{
    strlcpy(dst, src, dstSize);
    if (t.textWidth(dst) <= maxW) {
        return;
    }
    char tmp[128];
    strlcpy(tmp, src, sizeof(tmp));
    size_t n = strlen(tmp);
    while (n > 1) {
        --n;
        while (n > 0 && (static_cast<uint8_t>(tmp[n]) & 0xC0) == 0x80) {
            --n;                       /* byte de continuacio UTF-8 */
        }
        tmp[n] = '\0';
        snprintf(dst, dstSize, "%s...", tmp);
        if (t.textWidth(dst) <= maxW) {
            return;
        }
    }
}

/* Alcada de la barra de navegacio de baix (el fons tambe la fa servir). */
constexpr int NAV_H = 20;

/* --- Tramat ordenat i conversio a RGB565 ---------------------------------- *
 * La pantalla nomes te 5 bits per canal, aixi que els degradats hi fan
 * esglaons. Amb un tramat ordenat de Bayer (que suma un valor petit diferent
 * a cada pixel abans de quantitzar) el degradat es veu llis. */
namespace {

const uint8_t kBayer[16] = {0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5};

int chanR(uint16_t c) { return ((c >> 11) & 0x1F) << 3; }
int chanG(uint16_t c) { return ((c >> 5) & 0x3F) << 2; }
int chanB(uint16_t c) { return (c & 0x1F) << 3; }

/* 8 bits per canal -> RGB565, amb tramat ordenat. */
uint16_t to565(int r, int g, int b, int x, int y)
{
    const int d = kBayer[((y & 3) << 2) | (x & 3)] - 8;   /* -8..7 */
    r += d >> 1;
    g += d >> 2;
    b += d >> 1;
    if (r < 0) r = 0; else if (r > 255) r = 255;
    if (g < 0) g = 0; else if (g > 255) g = 255;
    if (b < 0) b = 0; else if (b > 255) b = 255;
    return static_cast<uint16_t>(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3));
}

/* pushImage envia els bytes tal com son i la pantalla els vol en big-endian
 * (com les icones de la SD): per aixo girem cada valor. */
inline uint16_t aPantalla(uint16_t v)
{
    return static_cast<uint16_t>((v >> 8) | (v << 8));
}

}  // namespace

/* Fons de la pantalla.
 *
 * Es calcula a mida i s'envia fila a fila amb pushImage: es la manera de tenir
 * degradats de debò en una pantalla de 5 bits per canal.
 *
 * La base son QUATRE LLUMS el·liptiques (dues bandes amples que entren de dalt
 * i de baix, i dues mes que renten els costats) sobre un degradat vertical.
 * A sobre hi van la vinya (les vores mes fosques), un pèl de gra fi, les
 * cantonades de reticle i unes marques de regla a les vores.
 *
 * Tot plegat son uns 30 ms i nomes es fa en canviar de pantalla. */
void drawBackground()
{
    TFT_eSPI& t = Display::driver();
    const int W = Display::width();
    const int H = Display::height();
    if (W > 480 || H > 480) {
        return;                 /* fora de mida: no hi ha buffer */
    }

    const int bgR = chanR(COL_BG),  bgG = chanG(COL_BG),  bgB = chanB(COL_BG);
    const int b2R = chanR(COL_BG2), b2G = chanG(COL_BG2), b2B = chanB(COL_BG2);
    const int acR = chanR(COL_ACCENT), acG = chanG(COL_ACCENT),
              acB = chanB(COL_ACCENT);
    const int waR = chanR(COL_WARN), waG = chanG(COL_WARN), waB = chanB(COL_WARN);

    /* Les quatre llums. Les dues primeres tenen el centre FORA de la pantalla,
     * aixi que entren com una aurora des de dalt i des de baix; les altres
     * dues renten els costats (una d'accent i una de tebia, que es la que
     * trenca la monotonia del blau). */
    struct Llum { int cx, cy, rx, ry, r, g, b, forca; };
    const Llum llums[] = {
        {W / 2,         H * -4 / 100, W * 86 / 100, H * 24 / 100,
         acR, acG, acB, 175},
        {W / 2,         H * 104 / 100, W * 86 / 100, H * 28 / 100,
         acR, acG, acB, 155},
        {W * 106 / 100, H * 52 / 100, W * 52 / 100, H * 52 / 100,
         waR, waG, waB, 48},
        {W * -6 / 100,  H * 46 / 100, W * 46 / 100, H * 50 / 100,
         acR, acG, acB, 50},
    };
    constexpr int NLLUM = sizeof(llums) / sizeof(llums[0]);
    /* Inversos dels radis en format 16.8: aixi tot el calcul de les llums es
     * pot fer amb enters (la coma flotant, a l'ESP32, hi costa molt mes). */
    int invX[NLLUM];
    int invY[NLLUM];
    for (int i = 0; i < NLLUM; ++i) {
        invX[i] = 65536 / llums[i].rx;
        invY[i] = 65536 / llums[i].ry;
    }

    static uint8_t vigX[480];
    for (int x = 0; x < W; ++x) {
        const int dx = x * 2 - W;
        int v = (dx * dx * 58) / (W * W);
        vigX[x] = static_cast<uint8_t>((v > 80) ? 80 : v);
    }

    /* El fons es puja de cop en blocs de FILES files: pushImage reserva un
     * buffer a la pila a cada crida, aixi que com menys crides, millor. (El
     * bloc no pot ser gaire gran: el DRAM de l'ESP32 va just.) */
    constexpr int FILES = 8;
    static uint16_t buf[FILES * 480];

    for (int y0 = 0; y0 < H; y0 += FILES) {
        const int nf = (H - y0 < FILES) ? (H - y0) : FILES;
        for (int fila = 0; fila < nf; fila += 2) {
            const int yy = y0 + fila;
            uint16_t* out = buf + fila * W;

            /* Base: mes fosca al mig, una mica mes clara cap a les vores. */
            const int t2 = (yy * 2 > H) ? (yy * 2 - H) : (H - yy * 2);
            const int f  = 90 + (t2 * 166) / H;
            const int baseR = bgR + (((b2R - bgR) * f) >> 8);
            const int baseG = bgG + (((b2G - bgG) * f) >> 8);
            const int baseB = bgB + (((b2B - bgB) * f) >> 8);

            const int dyv = yy * 2 - H;
            int vy = (dyv * dyv * 58) / (H * H);
            if (vy > 80) {
                vy = 80;
            }

            /* Les llums que passen per aquesta fila (les altres es salten).
             * Les coordenades van normalitzades a -256..256. */
            int actiu[NLLUM];
            int ny2[NLLUM];
            int invx[NLLUM];
            int nact = 0;
            for (int i = 0; i < NLLUM; ++i) {
                const int ny = ((yy - llums[i].cy) * invY[i]) >> 8;
                if (ny > -256 && ny < 256) {
                    ny2[nact]   = ny * ny;
                    invx[nact]  = invX[i];
                    actiu[nact] = i;
                    ++nact;
                }
            }

            /* Cada dos pixels n'hi ha prou: els degradats son molt suaus. */
            for (int x = 0; x < W; x += 2) {
                int r = baseR;
                int g = baseG;
                int b = baseB;

                for (int k = 0; k < nact; ++k) {
                    const Llum& l = llums[actiu[k]];
                    const int nx = ((x - l.cx) * invx[k]) >> 8;
                    const int q  = 256 - ((nx * nx + ny2[k]) >> 8);
                    if (q > 0) {
                        /* Caiguda quadratica: queda molt mes suau que lineal. */
                        const int a = (q * q * l.forca) >> 16;
                        r += ((l.r - r) * a) >> 8;
                        g += ((l.g - g) * a) >> 8;
                        b += ((l.b - b) * a) >> 8;
                    }
                }

                /* Vinya: les vores i els cantons, una mica mes foscos. */
                const int v = vy + vigX[x];
                if (v > 0) {
                    const int k2 = 256 - v;
                    r = (r * k2) >> 8;
                    g = (g * k2) >> 8;
                    b = (b * k2) >> 8;
                }

                /* Gra: un pèl de soroll, perque la superficie no quedi llisa i
                 * per acabar d'amagar els esglaons. */
                const int n = ((x * 73856093) ^ (yy * 19349663)) & 3;
                r += n - 2;
                g += n - 2;
                b += n - 2;

                const uint16_t c = aPantalla(to565(r, g, b, x, yy));
                out[x] = c;
                if (x + 1 < W) {
                    out[x + 1] = c;
                }
            }

            /* La fila de sota es la mateixa: el degradat es tan suau que no es
             * nota, i aixi ens estalviem la meitat del calcul. */
            if (fila + 1 < nf) {
                memcpy(out + W, out, static_cast<size_t>(W) * 2);
            }
        }
        t.pushImage(0, y0, W, nf, buf);
    }

    /* Cantonades de reticle: el detall que dona aire de panell de control. */
    const uint16_t marc = t.alphaBlend(150, COL_ACCENT, COL_BG);
    const int L = 26;
    const int M = 5;
    const int xs[4] = {M, W - 1 - M, M, W - 1 - M};
    const int ys[4] = {M, M, H - 1 - M, H - 1 - M};
    const int sx[4] = {1, -1, 1, -1};
    const int sy[4] = {1, 1, -1, -1};
    for (int i = 0; i < 4; ++i) {
        t.drawFastHLine(sx[i] > 0 ? xs[i] : xs[i] - L + 1, ys[i], L, marc);
        t.drawFastVLine(xs[i], sy[i] > 0 ? ys[i] : ys[i] - L + 1, L, marc);
    }

    /* Marques de regla a les vores, molt fluixes. */
    const uint16_t tick = t.alphaBlend(55, COL_ACCENT, COL_BG);
    for (int yy = HEADER_H + 20; yy < H - NAV_H - 20; yy += 48) {
        t.drawFastHLine(0, yy, 4, tick);
        t.drawFastHLine(W - 4, yy, 4, tick);
    }
}

/* Taronja/groc/vermell segons el percentatge (per a barres i grafics). */
uint16_t barColorFor(int pct);

/*
 * ui.cpp - Interficie en pantalla, dibuixada amb primitives de TFT_eSPI i
 * generada DINAMICAMENT a partir de la configuracio del Mac.
 *
 * Disposicio (vertical 320x480 / horitzontal 480x320):
 *   dalt    capcalera: hora · host · indicador LINK
 *   mig     contingut de la PANTALLA actual:
 *             - files d'estat (gadgets) si la pantalla es de tipus "status"
 *             - graella de botons
 *   baix    barra de PESTANTES per canviar de pantalla
 */

namespace {

/* --- Pantalla actual ------------------------------------------------------ */
int gPage = 0;

/* Definides mes avall (les fa servir tambe la capcalera). */
void        clockSync(const char* hhmm);
const char* clockNow();

/* Estat "sense enllac amb el Mac": nomes rellotge i ajustos de la placa.
 * Viu aqui dalt perque el menu i la barra de navegacio tambe l'han de veure. */
bool gNoLink = false;

/* --- Geometria calculada (la comparteixen layout/refresh/hitTest) --------- */
struct RowGeom { int y; int h; };
RowGeom gRows[MAX_PAGE_WIDGETS];
int     gRowCount = 0;

int gBtnCount = 0;
int gBtnTop   = 0;
int gBtnCellW = 0;
int gBtnCellH = 0;
int gBtnCols  = BTN_COLS;
int gBtnRows  = 1;

int gTabCount = 0;
int gTabH     = TABBAR_H;
int gTabW     = 0;

/* Menu de pantalles (pantalla completa). */
bool gMenuOpen = false;
constexpr int MENU_BTN_W  = 30;   /* ample del boto ☰ de la capcalera */

/* --- Navegacio entre pantalles -------------------------------------------- */
constexpr int SWIPE_MIN  = 45;    /* pixels per considerar-ho un lliscament */
constexpr int SWIPE_MAXY = 60;    /* moviment vertical maxim permes */
bool gNavBar      = true;         /* hi ha barra de navegacio? (config) */
bool gNavSwipe    = true;         /* es pot lliscar? (config) */
int  gSwipeX0     = -1;           /* x on ha comencat el toc */
int  gSwipeY0     = 0;
bool gSwipeActive = false;

int gPressed = -1;

/* --- Repos (standby) ------------------------------------------------------ */
bool     gScreenOn    = true;
bool     gMacAwake    = true;
uint32_t gLastTouchMs = 0;
uint32_t gStandbyMs   = STANDBY_DEFAULT_MS;

/* --- Ajustos a la pantalla ------------------------------------------------ */
bool gSettingsOpen = false;
uint8_t gBrightPct = 100;

/* --- Cau de valors (per repintar nomes el que canvia) --------------------- */
char gLastVal[MAX_PAGE_WIDGETS][24];
int  gLastPct[MAX_PAGE_WIDGETS];
char gLastTime[8]  = "";
char gLastHost[24] = "";
int  gLastLink     = -1;
int  gLastPage     = -1;
char gLastSig[48]  = "";

struct WidgetView {
    const char* id;         /* nom del gadget ("cpu", "mem"...) */
    const char* label;
    char        value[24];
    int         pct;        /* -1 = sense barra */
    uint16_t    barColor;
};

uint16_t barColorFor(int pct)
{
    if (pct < 0)   return COL_ACCENT;
    if (pct >= 90) return COL_BAD;
    if (pct >= 70) return COL_WARN;
    return COL_OK;
}

int clampPct(float v)
{
    int p = static_cast<int>(v + 0.5f);
    if (p < 0)   p = 0;
    if (p > 100) p = 100;
    return p;
}

/* Construeix la vista (etiqueta, valor i barra) d'un gadget. */
void buildWidget(const char* id, const MacLink::Stats& s, bool have, WidgetView& v)
{
    v.id  = id;
    v.pct = -1;

    if (!have) {
        v.label = id;
        strlcpy(v.value, "--", sizeof(v.value));
        return;
    }

    if (strcmp(id, "cpu") == 0) {
        v.label = "CPU";  v.pct = clampPct(s.cpu);
        snprintf(v.value, sizeof(v.value), "%d%%", v.pct);
    } else if (strcmp(id, "mem") == 0) {
        v.label = "RAM";  v.pct = clampPct(s.mem);
        snprintf(v.value, sizeof(v.value), "%d%%", v.pct);
    } else if (strcmp(id, "disk") == 0) {
        v.label = "DISC"; v.pct = clampPct(s.disk);
        snprintf(v.value, sizeof(v.value), "%d%%", v.pct);
    } else if (strcmp(id, "bat") == 0) {
        v.label = "BAT";  v.pct = clampPct(s.bat);
        snprintf(v.value, sizeof(v.value), (s.chg == 1) ? "%d%%+" : "%d%%", v.pct);
    } else if (strcmp(id, "net") == 0) {
        v.label = "NET";
        snprintf(v.value, sizeof(v.value), "v%.1f ^%.1f", s.dn, s.up);
    } else if (strcmp(id, "load") == 0) {
        v.label = "LOAD";
        snprintf(v.value, sizeof(v.value), "%.2f", s.load);
    } else if (strcmp(id, "uptime") == 0) {
        v.label = "UP";
        const uint32_t secs = s.uptimeS;
        const uint32_t d = secs / 86400UL, h = (secs % 86400UL) / 3600UL;
        const uint32_t m = (secs % 3600UL) / 60UL;
        if (d > 0) {
            snprintf(v.value, sizeof(v.value), "%lud%luh",
                     static_cast<unsigned long>(d), static_cast<unsigned long>(h));
        } else {
            snprintf(v.value, sizeof(v.value), "%luh%lum",
                     static_cast<unsigned long>(h), static_cast<unsigned long>(m));
        }
    } else if (strcmp(id, "time") == 0) {
        v.label = "HORA";
        strlcpy(v.value, s.timeStr[0] ? s.timeStr : "--:--", sizeof(v.value));
    } else if (strcmp(id, "host") == 0) {
        v.label = "HOST";
        strlcpy(v.value, s.host[0] ? s.host : "?", sizeof(v.value));
    } else {
        v.label = id;
        strlcpy(v.value, "?", sizeof(v.value));
    }

    v.barColor = barColorFor(v.pct);
}

/* --- Trossos de la capcalera ---------------------------------------------- *
 * Estan separats perque la marquesina (mes avall) ha de poder tornar a pintar
 * l'hora i la pastilla A SOBRE del text que vessa fora de la seva zona. */

/* Fons de la capcalera: el color de targeta i les dues linies de sota. */
void drawHeaderChrome(TFT_eSPI& t, int x, int w)
{
    const int H = HEADER_H;
    t.fillRect(x, 0, w, H, COL_CARD);
    t.drawFastHLine(x, H - 1, w, COL_EDGE);
    /* Filet d'accent: lliga amb la resta de la interficie. */
    t.fillRect(x, H - 2, w, 1, t.alphaBlend(120, COL_ACCENT, COL_CARD));
}

/* Boto de menu (☰): tres barretes suaus. */
void drawHeaderMenu(TFT_eSPI& t)
{
    const int H = HEADER_H;
    for (int i = 0; i < 3; ++i) {
        t.fillRoundRect(9, 11 + i * 5, 13, 2, 1, COL_TEXT);
    }
    t.drawFastVLine(MENU_BTN_W - 1, 5, H - 10, COL_EDGE);
}

/* Hora, a l'esquerra. Es la de la placa: va sincronitzada amb el Mac mentre hi
 * ha enllac i segueix comptant tota sola quan no n'hi ha. Retorna on acaba. */
int drawHeaderClock(TFT_eSPI& t)
{
    const int H = HEADER_H;
    char hora[8];
    strlcpy(hora, clockNow(), sizeof(hora));
    const int x = MENU_BTN_W + 8;
    setFontS(t);
    t.setTextDatum(ML_DATUM);
    t.setTextColor(COL_TEXT, COL_CARD);
    t.drawString(hora, x, H / 2);
    return x + t.textWidth(hora);
}

/* On comença la pastilla d'enllac: marca on s'acaba la zona del nom del Mac. */
int headerPillX(TFT_eSPI& t, bool linkUp)
{
    setFontS(t);
    const int tw = t.textWidth(linkUp ? "LINK" : "NO LINK");
    return Display::width() - PAD - (tw + 22);
}

/* Pastilla d'enllac, a la dreta: puntet de color + estat. */
void drawHeaderPill(TFT_eSPI& t, bool linkUp)
{
    const int W = Display::width();
    const int H = HEADER_H;
    const uint16_t c   = linkUp ? COL_OK : COL_BAD;
    const char*    lbl = linkUp ? "LINK" : "NO LINK";
    setFontS(t);
    const int pillW = t.textWidth(lbl) + 22;
    const int pillX = W - PAD - pillW;

    t.fillRoundRect(pillX, 6, pillW, H - 12, (H - 12) / 2, COL_BG);
    t.fillSmoothCircle(pillX + 9, H / 2, 3, c);
    t.setTextDatum(MR_DATUM);
    t.setTextColor(c, COL_BG);
    t.drawString(lbl, pillX + pillW - 8, H / 2);
}

/* --- Marquesina del nom del Mac ------------------------------------------- *
 * Un nom com "MacBook Pro de Jaume" no cap entre l'hora i la pastilla. Abans
 * s'escurçava amb punts suspensius ("MacBook Pr...") i no s'arribava a saber
 * mai com es diu l'equip. Ara, si no hi cap, el text va passant.
 *
 * Com es retalla sense sprites (serien memoria que va i ve): pintem la ratlla
 * buida, hi posem el text desplaçat i, a sobre del que ha vessat, tornem a
 * pintar els dos marges sencers. Com que l'hora i la pastilla son a les dues
 * bandes de la zona, el text queda retallat exactament on toca. */
char     gMarqText[56] = "";
int      gMarqX0   = 0;
int      gMarqX1   = 0;
int      gMarqOff  = 0;              /* pixels desplaçats */
bool     gMarqOn   = false;
bool     gMarqLink = false;          /* enllac, per repintar la pastilla */
uint32_t gMarqNext = 0;              /* quan toca el proper pas */

constexpr int      MARQ_GAP      = 44;    /* buit entre passades */
constexpr int      MARQ_STEP     = 2;     /* pixels per pas */
constexpr uint32_t MARQ_MS       = 50;    /* cada quant es mou */
constexpr uint32_t MARQ_START_MS = 1500;  /* aturada abans d'arrencar */

void drawMarquee()
{
    TFT_eSPI& t = Display::driver();
    const int H = HEADER_H;
    setFontS(t);
    const int period = t.textWidth(gMarqText) + MARQ_GAP;

    /* 1) Buidem la zona del nom. */
    drawHeaderChrome(t, gMarqX0, gMarqX1 - gMarqX0);

    /* 2) El text, desplaçat. El pintem dues vegades (la cua darrere del cap)
     *    perque la passada sigui continua, sense forats. */
    t.setTextDatum(ML_DATUM);
    t.setTextColor(COL_DIM, COL_CARD);
    t.drawString(gMarqText, gMarqX0 - gMarqOff, H / 2);
    if (gMarqOff > 0) {
        t.drawString(gMarqText, gMarqX0 - gMarqOff + period, H / 2);
    }

    /* 3) Retallem el que ha vessat: tornem a pintar els dos marges. */
    drawHeaderChrome(t, 0, gMarqX0);
    drawHeaderMenu(t);
    drawHeaderClock(t);
    drawHeaderChrome(t, gMarqX1, Display::width() - gMarqX1);
    drawHeaderPill(t, gMarqLink);
}

/* Arrenca la marquesina amb un text que no hi cap. */
void marqueeStart(TFT_eSPI& t, const char* text, int x0, int x1, bool linkUp)
{
    strlcpy(gMarqText, text, sizeof(gMarqText));
    gMarqX0   = x0;
    gMarqX1   = x1;
    gMarqOff  = 0;
    gMarqOn   = true;
    gMarqLink = linkUp;
    gMarqNext = millis() + MARQ_START_MS;
    Serial.printf("[UI] capcalera: '%s' (%d px en %d) -> marquesina\n",
                  gMarqText, t.textWidth(gMarqText), x1 - x0);
}

/* Cridada al bucle: fa avançar la marquesina quan toca. */
void updateMarquee()
{
    if (!gMarqOn) {
        return;
    }
    const uint32_t now = millis();
    if (static_cast<int32_t>(now - gMarqNext) < 0) {
        return;
    }
    TFT_eSPI& t = Display::driver();
    setFontS(t);
    const int period = t.textWidth(gMarqText) + MARQ_GAP;

    gMarqOff += MARQ_STEP;
    if (gMarqOff >= period) {
        gMarqOff  = 0;                     /* torna a començar... */
        gMarqNext = now + MARQ_START_MS;   /* ...i s'hi està una estona */
    } else {
        gMarqNext = now + MARQ_MS;
    }
    drawMarquee();
}

void drawHeader(bool linkUp, const MacLink::Stats& s, bool have)
{
    TFT_eSPI& t = Display::driver();
    drawHeaderChrome(t, 0, Display::width());
    drawHeaderMenu(t);

    const int horaEnd = drawHeaderClock(t);
    const int pillX   = headerPillX(t, linkUp);

    /* --- Host, al mig ---------------------------------------------------- *
     * El Mac el pot enviar amb guions baixos ("MacBook_Pro"), que es llegeixen
     * millor com a espais. Si no hi cap entre l'hora i la pastilla, en lloc
     * d'escurçar-lo amb punts suspensius el fem passar (marquesina). */
    bool marq = false;
    const int x0 = horaEnd + 10;
    const int x1 = pillX - 8;
    if (x1 > x0 + 16) {
        char host[48];
        strlcpy(host, (have && s.host[0]) ? s.host : "Mac", sizeof(host));
        for (char* p = host; *p != '\0'; ++p) {
            if (*p == '_') {
                *p = ' ';
            }
        }
        setFontS(t);
        if (t.textWidth(host) <= x1 - x0) {
            t.setTextDatum(MC_DATUM);
            t.setTextColor(COL_DIM, COL_CARD);
            t.drawString(host, (x0 + x1) / 2, HEADER_H / 2);
        } else {
            /* Si ja estava en marxa amb el mateix text, no el tornem a
             * començar: nomes actualitzem la zona. (L'hora pot canviar de mida
             * en passar d'un minut a un altre, i reiniciar la passada cada cop
             * es notaria molt.) */
            if (!gMarqOn || strcmp(gMarqText, host) != 0) {
                marqueeStart(t, host, x0, x1, linkUp);
            } else {
                gMarqX0   = x0;
                gMarqX1   = x1;
                gMarqLink = linkUp;
            }
            marq = true;
        }
    }
    if (!marq) {
        gMarqOn = false;        /* el nom hi cap: prou marquesina */
    }

    drawHeaderPill(t, linkUp);
    if (gMarqOn) {
        drawMarquee();      /* el text va a sobre: el tornem a retallar */
    }
}

/* Barra SEGMENTADA (estil LED): cada segment es una marca i els que arriben al
 * valor s'encenen. Queda molt mes "panell de control" que una barra llisa. */
void drawSegBar(int x, int y, int w, int h, int pct, uint16_t color)
{
    const int segs = 22;
    const int gap  = 1;
    const int sw = (w - (segs - 1) * gap) / segs;
    if (sw < 2) {
        return;
    }
    TFT_eSPI& t = Display::driver();
    const int lit = (pct * segs + 50) / 100;
    for (int i = 0; i < segs; ++i) {
        const int sx = x + i * (sw + gap);
        t.fillRect(sx, y, sw, h, (i < lit) ? color : COL_EDGE);
    }
}

/* Mini-grafic (sparkline) de l'historial d'una serie. Nomes es pot veure el
 * dibuix (sense eixos ni numeros): serveix per veure la forma d'un cop d'ull.
 *
 * IMPORTANT: no s'esborra res abans. Cada columna es pinta un sol cop (la
 * barra i, a sobre, el buit). Aixi no hi ha parpelleig. */
void drawSparkline(int series, int x, int y, int w, int h, uint16_t color)
{
    const int n = History::count(series);
    if (n < 2 || w < 6 || h < 4) {
        return;
    }
    TFT_eSPI& t = Display::driver();

    float hi = History::isPercent(series) ? 100.0f
                                          : History::maxValue(series) * 1.25f;
    if (hi < 0.001f) {
        hi = 1.0f;
    }

    /* Una barra vertical per columna de pixels, amb el maxim de les mostres
     * que hi cauen: aixi els pics es veuen encara que hi hagi mes mostres que
     * pixels. */
    for (int gx = 0; gx < w; ++gx) {
        const float f0 = static_cast<float>(gx) * (n - 1) / (w - 1);
        const float f1 = static_cast<float>(gx + 1) * (n - 1) / (w - 1);
        int i0 = static_cast<int>(f0);
        int i1 = static_cast<int>(f1);
        if (i1 >= n) {
            i1 = n - 1;
        }
        float v = History::value(series, i0);
        for (int k = i0 + 1; k <= i1; ++k) {
            const float vk = History::value(series, k);
            if (vk > v) {
                v = vk;
            }
        }
        if (v < 0.0f) v = 0.0f;
        if (v > hi)   v = hi;
        int bh = static_cast<int>(v * h / hi);
        if (bh < 1) {
            bh = 1;
        }
        /* El buit de dalt amb el color de la targeta: esborra la barra
         * anterior sense cap flaix (cada columna es pinta un sol cop). */
        if (bh < h) {
            t.drawFastVLine(x + gx, y, h - bh, COL_CARD);
        }
        t.drawFastVLine(x + gx, y + h - bh, bh, color);
    }
}

/* Actualitza NOMES el que canvia d'una fila (valor, mini-grafic i barra). El
 * marc de la targeta, el puntet i l'etiqueta no es toquen: aixi no hi ha cap
 * flaix. */
void updateRow(int i, const WidgetView& v)
{
    TFT_eSPI& t = Display::driver();
    const int W  = Display::width();
    const int x  = PAD;
    const int w  = W - 2 * PAD;
    const int ry = gRows[i].y;
    const int rh = gRows[i].h;
    const bool withBar = (v.pct >= 0);
    const int  cy = ry + rh / 2 - (withBar ? 5 : 0);

    /* Valor: esborrem exactament el text anterior (i una mica mes, pel cas
     * que el nou sigui mes llarg). */
    setFontM(t);
    const int nw = t.textWidth(v.value);
    const int ow = t.textWidth(gLastVal[i]);
    const int ew = (nw > ow) ? nw : ow;
    if (ew > 0) {
        t.fillRect(x + w - 10 - ew - 2, cy - 10, ew + 4, 20, COL_CARD);
    }
    t.setTextDatum(MR_DATUM);
    t.setTextColor(COL_TEXT, COL_CARD);
    t.drawString(v.value, x + w - 10, cy);

    /* Mini-grafic. */
    const int series = History::seriesFor(v.id);
    if (series >= 0) {
        const int spX = x + 74;
        const int spW = (x + w - 76) - spX;
        if (spW >= 24) {
            drawSparkline(series, spX, cy - 9, spW, 18, v.barColor);
        }
    }

    /* Barra segmentada. */
    if (withBar) {
        drawSegBar(x + 11, ry + rh - 12, w - 22, 4, v.pct, v.barColor);
    }
}

void drawRowFull(int i, const WidgetView& v)
{
    TFT_eSPI& t = Display::driver();
    const int W  = Display::width();
    const int x  = PAD;
    const int w  = W - 2 * PAD;
    const int ry = gRows[i].y;
    const int rh = gRows[i].h;

    t.fillRoundRect(x, ry + 2, w, rh - 4, 8, COL_CARD);
    t.drawRoundRect(x, ry + 2, w, rh - 4, 8, COL_EDGE);

    /* Amb barra: puntet de color + etiqueta i valor una mica mes amunt. */
    const bool withBar = (v.pct >= 0);
    const int  cy = ry + rh / 2 - (withBar ? 5 : 0);

    t.fillSmoothCircle(x + 13, cy, 3, withBar ? v.barColor : COL_ACCENT);

    t.setTextDatum(ML_DATUM);
    setFontS(t);
    t.setTextColor(COL_DIM, COL_CARD);
    t.drawString(v.label, x + 23, cy);

    updateRow(i, v);
}

void buttonRect(int i, int& x, int& y, int& w, int& h)
{
    const int col = i % gBtnCols;
    const int row = i / gBtnCols;
    x = PAD + col * (gBtnCellW + BTN_GAP);
    y = gBtnTop + row * (gBtnCellH + BTN_GAP);
    w = gBtnCellW;
    h = gBtnCellH;
}

/* Botons de la PANTALLA actual. */
const MacLink::Button* pageButton(int i);

/* --- Teclat numeric: botons sintetics (no venen de la configuracio) ------- */
constexpr int NUMPAD_COUNT = 16;
MacLink::Button gNumpad[NUMPAD_COUNT];
void buildNumpad()
{
    /* Fem servir el BLOC NUMERIC: son les uniques tecles que donen el mateix
     * caracter a qualsevol distribucio de teclat. Amb els codis HID normals,
     * en un Mac en castella el '-' escrivia un apostrof i el '+' un '¡'.
     *
     * Compte amb el punt: macOS tradueix el punt del bloc numeric al separador
     * decimal de la distribucio (en castella, una coma). Per aixo el punt va
     * amb el caracter normal, que si que es un punt a tot arreu. */
    static const char* const kKeys[NUMPAD_COUNT] = {
        "kp_7", "kp_8", "kp_9", "kp_minus",
        "kp_4", "kp_5", "kp_6", "kp_plus",
        "kp_1", "kp_2", "kp_3", "kp_star",
        "backspace", "kp_0", ".", "kp_enter",
    };
    static const char* const kLabs[NUMPAD_COUNT] = {
        "7", "8", "9", "-",
        "4", "5", "6", "+",
        "1", "2", "3", "*",
        "DEL", "0", ".", "OK",
    };
    for (int i = 0; i < NUMPAD_COUNT; ++i) {
        strlcpy(gNumpad[i].id, "num", sizeof(gNumpad[i].id));
        strlcpy(gNumpad[i].label, kLabs[i], sizeof(gNumpad[i].label));
        gNumpad[i].icon[0] = '\0';
        strlcpy(gNumpad[i].keys, kKeys[i], sizeof(gNumpad[i].keys));
    }
}

bool pageIsNumpad()
{
    const MacLink::Config& cfg = MacLink::config();
    if (gPage < 0 || gPage >= cfg.pageCount) {
        return false;
    }
    return strcmp(cfg.pages[gPage].layout, "numpad") == 0;
}

/* --- Tema: manual o automatic (clar/fosc segons el Mac) ------------------- *
 * La configuracio que arriba del Mac mana, pero la pantalla tambe pot canviar
 * el tema. Com que el canvi ha de viatjar fins al Mac i tornar (i sense enllac
 * no tornaria mai), la UI se'n guarda una copia mentre el canvi es a cami. */
constexpr uint32_t THEME_PENDENT_MS = 3000;   /* marge perque arribi la resposta */

struct ThemePref {
    uint8_t theme;      /* tema manual */
    uint8_t autoMode;   /* 1 = segons el Mac */
    uint8_t dark;       /* tema amb el Mac en fosc */
    uint8_t light;      /* tema amb el Mac en clar */
};

ThemePref gThemePref = {0, 0, 0, 1};
bool     gThemeVist    = false;   /* ja hem copiat alguna configuracio? */
bool     gThemePendent = false;   /* hem demanat un canvi i esperem resposta */
uint32_t gThemePendentMs = 0;

/* Posicions de 'gThemePref'. */
enum { TP_MANUAL = 0, TP_DARK, TP_LIGHT };

/* Marca que acabem de demanar un canvi de tema al Mac. */
void themePrefPendent()
{
    gThemePendent   = true;
    gThemePendentMs = millis();
}

/* Copia la configuracio del Mac... quan toca:
 *  - Sense enllac no hi ha qui confirmi res, aixi que mana el que hagi triat
 *    l'usuari des de la pantalla.
 *  - Just despres de tocar un boto, el canvi encara va de cami cap al Mac:
 *    mentrestant pintem el que ha triat l'usuari (aixi es veu a l'instant i no
 *    cal esperar el viatge d'anada i tornada).
 *  - En qualsevol altre cas mana la configuracio del Mac. */
void themePrefSync(const MacLink::Config& cfg)
{
    if (gThemeVist && !MacLink::linkUp()) {
        return;
    }
    if (gThemeVist && gThemePendent &&
        (millis() - gThemePendentMs) < THEME_PENDENT_MS) {
        return;
    }
    gThemeVist    = true;
    gThemePendent = false;
    gThemePref.theme    = cfg.theme;
    gThemePref.autoMode = cfg.themeAuto;
    gThemePref.dark     = cfg.themeDark;
    gThemePref.light    = cfg.themeLight;
}

/* Quin dels tres temes s'esta veient (i per tant quin canvien els botons
 * 'Tema <' i 'Tema >'). Amb el tema automatic mana el mode clar/fosc del Mac;
 * mentre no sapiguem com el te (sense enllac no ho podem saber), el manual. */
int themePrefSlot()
{
    if (!gThemePref.autoMode || !MacLink::linkUp() || MacLink::stats().dark < 0) {
        return TP_MANUAL;
    }
    return MacLink::stats().dark ? TP_DARK : TP_LIGHT;
}

uint8_t themePrefGet(int slot)
{
    return (slot == TP_DARK)  ? gThemePref.dark
         : (slot == TP_LIGHT) ? gThemePref.light
                              : gThemePref.theme;
}

void themePrefSet(int slot, uint8_t v)
{
    if      (slot == TP_DARK)  { gThemePref.dark  = v; }
    else if (slot == TP_LIGHT) { gThemePref.light = v; }
    else                       { gThemePref.theme = v; }
}

/* Claus que enten el Mac per a cada tema. */
const char* themePrefKey(int slot)
{
    return (slot == TP_DARK)  ? "tdark"
         : (slot == TP_LIGHT) ? "tlight"
                              : "theme";
}

/* El tema que toca pintar ara mateix. */
uint8_t themeFor()
{
    const uint8_t v = themePrefGet(themePrefSlot());
    /* Proteccio: si la configuracio portes un index que no existeix, no ens hi
     * encallariem (refresh() compara aquest valor amb el tema actual i, si no
     * coincidissin mai, repintaria sense parar). */
    return (v < Th::count()) ? v : 0;
}

/* --- Ajustos: opcions de temps -------------------------------------------- */
const uint32_t kStandbyOpts[] = {0, 30000, 60000, 120000, 300000, 600000, 1800000};
constexpr int  kStandbyCount  = 7;

/* Minuts que pot estar el Mac inactiu abans que la placa passi al rellotge
 * (0 = mai). Es canvien des de la fila 'Rellotge si inactiu' del menu. */
const uint16_t kIdleOpts[] = {0, 1, 2, 5, 10, 20, 30, 60};
constexpr int  kIdleCount  = 8;

const char* standbyLabel()
{
    static char buf[12];
    if (gStandbyMs == 0) {
        return "mai";
    }
    if (gStandbyMs < 60000) {
        snprintf(buf, sizeof(buf), "%us", static_cast<unsigned>(gStandbyMs / 1000));
    } else {
        snprintf(buf, sizeof(buf), "%umin", static_cast<unsigned>(gStandbyMs / 60000));
    }
    return buf;
}

/* --- Launcher: botons sintetics amb les apps obertes al Mac --------------- */
constexpr int LAUNCH_MAX = MacLink::MAX_APPS;
MacLink::Button gLaunch[LAUNCH_MAX];
int gLaunchCount = 0;

void buildLauncher()
{
    gLaunchCount = MacLink::appCount();
    if (gLaunchCount > LAUNCH_MAX) gLaunchCount = LAUNCH_MAX;
    for (int i = 0; i < gLaunchCount; ++i) {
        snprintf(gLaunch[i].id, sizeof(gLaunch[i].id), "focus:%d", i);
        strlcpy(gLaunch[i].label, MacLink::appName(i), sizeof(gLaunch[i].label));
        gLaunch[i].keys[0] = '\0';

        /* La icona la tria el Mac (sap de quina app es). Si la icona no hi es
         * a la SD, el boto surt nomes amb el nom, com abans. */
        const char* ic = MacLink::appIcon(i);
        if (ic[0] != '\0' && Icons::exists(ic)) {
            strlcpy(gLaunch[i].icon, ic, sizeof(gLaunch[i].icon));
        } else {
            gLaunch[i].icon[0] = '\0';
        }
    }
}

bool pageIsLauncher()
{
    const MacLink::Config& cfg = MacLink::config();
    if (gPage < 0 || gPage >= cfg.pageCount) {
        return false;
    }
    return strcmp(cfg.pages[gPage].layout, "launcher") == 0;
}

/* --- Pestanyes del navegador: botons sintetics amb les pestanyes obertes --- */
constexpr int TABS_MAX = MacLink::MAX_TABS;
MacLink::Button gTabs[TABS_MAX];
int gTabsCount = 0;

void buildTabs()
{
    /* El Mac ja filtra: nomes envia les pestanyes del navegador que te el
     * focus. Es una sola llista, com les apps del launcher. Si encara no han
     * arribat, no hi ha res a mostrar i el Mac les tornarà a enviar. */
    gTabsCount = MacLink::tabCount();
    if (gTabsCount > TABS_MAX) gTabsCount = TABS_MAX;
    for (int i = 0; i < gTabsCount; ++i) {
        /* L'id va 1-based: el Mac activa la pestanya pel seu numero (1..N),
         * igual que envia els titols. */
        snprintf(gTabs[i].id, sizeof(gTabs[i].id), "tab:%d", i + 1);
        strlcpy(gTabs[i].label, MacLink::tabName(i), sizeof(gTabs[i].label));
        gTabs[i].keys[0] = '\0';
        const char* ic = MacLink::tabIcon(i);
        if (ic[0] != '\0' && Icons::exists(ic)) {
            strlcpy(gTabs[i].icon, ic, sizeof(gTabs[i].icon));
        } else {
            gTabs[i].icon[0] = '\0';
        }
    }
}

bool pageIsTabs()
{
    const MacLink::Config& cfg = MacLink::config();
    if (gPage < 0 || gPage >= cfg.pageCount) {
        return false;
    }
    return strcmp(cfg.pages[gPage].layout, "tabs") == 0;
}

/* Demana al Mac que reenviï les pestanyes de la pantalla actual ('R tabs').
 * S'usa quan s'enta a una pantalla "tabs" i encara no tenim la seva llista. */
void requestTabs()
{
    MacLink::sendCommand("refresh:tabs");
}

const MacLink::Button* pageButton(int i)
{
    if (pageIsNumpad()) {
        return (i >= 0 && i < NUMPAD_COUNT) ? &gNumpad[i] : nullptr;
    }
    if (pageIsLauncher()) {
        return (i >= 0 && i < gLaunchCount) ? &gLaunch[i] : nullptr;
    }
    if (pageIsTabs()) {
        return (i >= 0 && i < gTabsCount) ? &gTabs[i] : nullptr;
    }
    const MacLink::Config& cfg = MacLink::config();
    if (gPage < 0 || gPage >= cfg.pageCount) {
        return nullptr;
    }
    const MacLink::Page& p = cfg.pages[gPage];
    if (i < 0 || i >= p.buttonCount) {
        return nullptr;
    }
    return &p.buttons[i];
}

/* Els botons de llista (launcher d'apps i pestanyes) porten icona gran i el
 * títol en lletra més grossa, perquè es reconeguin d'un cop d'ull. */
bool esBotoLlista(const char* id)
{
    return strncmp(id, "focus:", 6) == 0 || strncmp(id, "tab:", 4) == 0;
}

void drawButton(int i, bool pressed)
{
    const MacLink::Button* b = pageButton(i);
    if (b == nullptr) {
        return;
    }

    TFT_eSPI& t = Display::driver();
    int x = 0, y = 0, w = 0, h = 0;
    buttonRect(i, x, y, w, h);

    const uint16_t bg = pressed ? COL_BTN_P : COL_BTN;
    t.fillRoundRect(x, y, w, h, 12, bg);
    /* Filet clar a dalt: dona un aire de relleu sense gastar colors nous. */
    t.drawFastHLine(x + 10, y + 1, w - 20, COL_EDGE);
    t.drawRoundRect(x, y, w, h, 12, pressed ? COL_ACCENT : COL_EDGE);

    /* Els operadors del teclat numeric (+ - * / = C) es destaquen en accent. */
    const bool esOperador = (b->label[1] == '\0') &&
                            (strchr("+-*/=C", b->label[0]) != nullptr);

    setFontS(t);
    t.setTextColor(pressed ? COL_ACCENT
                           : (esOperador ? COL_ACCENT : COL_TEXT), bg);

    /* Amb icona: icona a dalt i text a sota. Sense icona: nomes el text centrat. */
    if (b->icon[0] != '\0') {
        /* Al launcher i a les pestanyes la icona es una mica mes gran: son les
         * icones de les apps i els favicons, i es reconeixen millor. */
        const bool esLlista = esBotoLlista(b->id);
        const int  maxPx = esLlista ? 56 : ICON_BTN_PX;

        int isz = h - 22;
        if (isz > maxPx) isz = maxPx;
        if (isz < 12)    isz = 12;

        /* Placa darrere la icona: la fa destacar del boto (queda com una tecla
         * amb la icona incrustada). */
        const int plate = isz + 10;
        const int pcx = x + w / 2;
        const int pcy = y + 4 + isz / 2;
        t.fillRoundRect(pcx - plate / 2, pcy - plate / 2, plate, plate,
                        plate / 3, COL_BG);
        t.drawRoundRect(pcx - plate / 2, pcy - plate / 2, plate, plate,
                        plate / 3, pressed ? COL_ACCENT : COL_EDGE);

        if (Icons::drawCentered(b->icon, pcx, pcy, isz, COL_BG)) {
            char txt[24];
            fitText(t, b->label, txt, sizeof(txt), w - 8);
            t.setTextDatum(BC_DATUM);
            t.drawString(txt, x + w / 2, y + h - 4);
            return;
        }
    }

    t.setTextDatum(MC_DATUM);
    /* Un sol caracter (teclat numeric): el fem gran. */
    if (b->label[1] == '\0' && b->label[0] != '\0' && h > 34) {
        setFontL(t);
        t.setTextColor(pressed ? COL_ACCENT
                               : (esOperador ? COL_ACCENT : COL_TEXT), bg);
    } else if (esBotoLlista(b->id)) {
        /* Launcher (apps obertes) i pestanyes: el nom en lletra mes gran. */
        setFontM(t);
        t.setTextColor(pressed ? COL_ACCENT : COL_TEXT, bg);
    }

    /* El nom d'una app pot ser llarg ("Visual Studio Code"): si no hi cap, el
     * retallem amb punts suspensius perque no surti del boto. */
    const char* out = b->label;
    char txt[24];
    if (esBotoLlista(b->id)) {
        fitText(t, b->label, txt, sizeof(txt), w - 8);
        out = txt;
    }
    t.drawString(out, x + w / 2, y + h / 2);
}

void drawAllButtons()
{
    for (int i = 0; i < gBtnCount; ++i) {
        drawButton(i, i == gPressed);
    }
}

/* --- Rellotge circular (gauge) estil HUD -----------------------------------
 * Anells concentrics, marques radials, un halo de llum darrere l'arc del valor
 * i el numero gran al mig.
 *
 * IMPORTANT: quan canvia el valor NO es repinta tot el rellotge (aixo feia un
 * flaix molt visible). Nomes es repinta el tros d'arc que ha canviat i el
 * numero. (drawSmoothArc: angle 0 = baix i sentit horari.)
 */

/* Color de l'arc per a un angle: degradat del color de la serie (a 45 graus)
 * cap al color d'alerta (a 315). Depen de l'ANGLE i no del valor, aixi que
 * repintar nomes un tros queda sempre del mateix color. */
/* --- Geometria dels gauges ------------------------------------------------ *
 * El gruix de l'anell i el disc del mig s'adapten a la mida del gauge. Amb una
 * geometria fixa, un gauge petit (r=37) deixava un disc de nomes 14 px de radi
 * i el numero, que en demana 44, se'n sortia i tapava l'anell. */
struct GaugeGeom {
    int rOut;    /* radi exterior de l'arc de valor */
    int rIn;     /* radi interior de l'arc de valor */
    int halo;    /* gruix del ressplendor que envolta l'arc */
    int inner;   /* radi del disc lliure del mig (per al numero) */
};

GaugeGeom gaugeGeom(int r)
{
    GaugeGeom g;
    if (r >= 60)      { g.rOut = r - 14; g.halo = 5; }
    else if (r >= 46) { g.rOut = r - 11; g.halo = 3; }
    else              { g.rOut = r - 8;  g.halo = 2; }

    const int gruix = (r >= 60) ? 9 : ((r >= 46) ? 7 : 6);
    g.rIn   = g.rOut - gruix;
    g.inner = g.rIn - g.halo - 1;
    if (g.inner < 9) {
        g.inner = 9;
    }
    return g;
}

uint16_t gaugeArcColor(TFT_eSPI& t, int angle, uint16_t fg)
{
    int k = (angle - 45) * 255 / 270;
    if (k < 0)   k = 0;
    if (k > 255) k = 255;
    return t.alphaBlend(static_cast<uint8_t>(k), COL_BAD, fg);
}

/* Part fixa: disc, anells, marques, pista de fons, etiqueta i min-max. */
void drawGaugeFrame(int cx, int cy, int r, int series, const char* label)
{
    TFT_eSPI& t = Display::driver();
    const GaugeGeom g = gaugeGeom(r);

    t.fillSmoothCircle(cx, cy, r, COL_CARD, COL_BG);
    t.drawSmoothArc(cx, cy, r, r - 1, 0, 360, COL_EDGE, COL_CARD, false);
    if (r > 48) {
        t.drawSmoothArc(cx, cy, r - 11, r - 12, 0, 360, COL_EDGE, COL_CARD, false);
    }

    /* Marques radials cada 15 graus (mes llargues cada 45). Nomes si hi caben
     * entre la vora del disc i l'arc: en un gauge petit no hi son i farien
     * una taca. */
    const int tickOut = r - 3;
    const int tickLen = (r >= 60) ? 8 : 5;
    if (tickOut - tickLen > g.rOut + 2) {
        for (int a = 45; a <= 315; a += 15) {
            const float rad = static_cast<float>(a) * 3.14159265f / 180.0f;
            const bool gran = ((a - 45) % 45) == 0;
            const int tickIn = tickOut - (gran ? tickLen : tickLen - 3);
            t.drawLine(cx - static_cast<int>(tickOut * sinf(rad)),
                       cy + static_cast<int>(tickOut * cosf(rad)),
                       cx - static_cast<int>(tickIn * sinf(rad)),
                       cy + static_cast<int>(tickIn * cosf(rad)),
                       gran ? COL_DIM : COL_EDGE);
        }
    }

    /* Pista de fons de l'arc (270 graus, amb l'obertura a la dreta). */
    if (g.rOut > g.rIn + 2) {
        t.drawSmoothArc(cx, cy, g.rOut, g.rIn, 45, 315, COL_EDGE, COL_CARD, false);
    }

    /* Etiqueta i min-max. */
    setFontS(t);
    t.setTextDatum(MC_DATUM);
    t.setTextColor(COL_DIM, COL_CARD);
    t.drawString(label, cx, cy + r + 10);
    if (series >= 0 && r > 34 && History::count(series) > 1) {
        char mm[24];
        snprintf(mm, sizeof(mm), "%d-%d",
                 clampPct(History::minValue(series)),
                 clampPct(History::maxValue(series)));
        t.drawString(mm, cx, cy + r + 24);
    }
}

/* Pinta (o esborra) el tros d'arc entre dos percentatges. */
void drawGaugeArcRange(int cx, int cy, int r, int fromPct, int toPct,
                       uint16_t fg, bool esborrar)
{
    const GaugeGeom g = gaugeGeom(r);
    if (g.rOut <= g.rIn + 2 || toPct <= fromPct) {
        return;
    }
    TFT_eSPI& t = Display::driver();
    const int a0 = 45 + (270 * fromPct) / 100;
    const int a1 = 45 + (270 * toPct) / 100;

    /* Halo del tros (mes ample i fluix). */
    t.drawSmoothArc(cx, cy, g.rOut + g.halo, g.rIn - g.halo, a0, a1,
                    esborrar ? COL_CARD : t.alphaBlend(60, fg, COL_CARD),
                    COL_CARD, false);

    /* L'arc, a trossos, per poder fer el degradat. */
    for (int a = a0; a < a1; a += 12) {
        const int b = (a + 12 < a1) ? (a + 12) : a1;
        t.drawSmoothArc(cx, cy, g.rOut, g.rIn, a, b,
                        esborrar ? COL_EDGE : gaugeArcColor(t, a, fg),
                        COL_CARD, false);
    }
}

/* Numero al mig de l'anell.
 *
 * La lletra s'adapta a la mida del gauge i, si el signe '%' no hi cap, es deixa
 * fora. Abans es dibuixava sempre a 18 pt i amb un gauge petit (r=37, disc de
 * 28 px) el numero en demanava 44: se'n sortia i tapava l'anell.
 *
 * La mida es tria pensant en el pitjor cas (3 xifres, "100") perque el numero
 * no balli en passar de 2 a 3 xifres. */
void drawGaugeNumber(int cx, int cy, int r, int oldPct, int pct, uint16_t fg)
{
    TFT_eSPI& t = Display::driver();
    const GaugeGeom g = gaugeGeom(r);
    const int room = 2 * g.inner;          /* ample del disc del mig */

    char v[10];
    snprintf(v, sizeof(v), "%d", pct);

    setFontS(t);
    const int pw = t.textWidth("%");

    /* Triem la lletra mes gran amb la que hi càpiguen el numero I el signe: el
     * '%' forma part de la lectura del gauge, aixi que el mantenim sempre que
     * hi càpiga. */
    int triat = -1;
    for (int k = 0; k <= 3; ++k) {
        setFontN(t, k);
        if (t.textWidth("100") + 2 + pw <= room) {
            triat = k;
            break;
        }
    }

    /* Si ni amb la lletra mes petita hi cap el signe, el deixem fora i
     * aprofitem per fer el numero el mes gran possible: es mes important que
     * el numero es llegeixi be que no pas el signe. */
    bool signe = (triat >= 0);
    if (triat < 0) {
        for (int k = 0; k <= 3; ++k) {
            setFontN(t, k);
            if (t.textWidth("100") <= room) {
                triat = k;
                break;
            }
        }
    }
    if (triat < 0) {
        triat = 3;                       /* ni aixi: la mes petita igualment */
    }

    setFontN(t, triat);

    const int nw   = t.textWidth(v);
    const int bigH = t.fontHeight();
    setFontS(t);
    const int smallH = t.fontHeight();

    const int total = nw + (signe ? 2 + pw : 0);
    const int x0    = cx - total / 2;
    const int yNum  = cy + 2;

    /* Esborrem NOMES el disc del mig: aixi mai no toquem l'anell ni el halo. */
    t.fillCircle(cx, cy, g.inner, COL_CARD);

    setFontN(t, triat);
    t.setTextDatum(ML_DATUM);
    t.setTextColor(COL_TEXT, COL_CARD);
    t.drawString(v, x0, yNum);

    if (signe) {
        setFontS(t);
        t.setTextDatum(ML_DATUM);
        t.setTextColor(fg, COL_CARD);
        t.drawString("%", x0 + nw + 2, yNum - (bigH - smallH) / 2);
    }
}

/* Marca del maxim de l'historial, sobre l'anell. */
void drawGaugeMaxMark(int cx, int cy, int r, int series, int oldMax)
{
    if (series < 0 || History::count(series) <= 4) {
        return;
    }
    TFT_eSPI& t = Display::driver();
    const int nowMax = clampPct(History::maxValue(series));
    const int rr = gaugeGeom(r).rOut + 4;   /* entre l'arc i les marques */

    /* Esborrem la marca anterior (cau entre les marques radials, aixi que un
     * puntet del color de la targeta no es nota). */
    if (oldMax >= 0 && oldMax != nowMax) {
        const float rad0 = static_cast<float>(45 + (270 * oldMax) / 100)
                           * 3.14159265f / 180.0f;
        t.fillSmoothCircle(cx - static_cast<int>(rr * sinf(rad0)),
                           cy + static_cast<int>(rr * cosf(rad0)), 3,
                           COL_CARD, COL_CARD);
    }
    const float rad = static_cast<float>(45 + (270 * nowMax) / 100)
                      * 3.14159265f / 180.0f;
    t.fillSmoothCircle(cx - static_cast<int>(rr * sinf(rad)),
                       cy + static_cast<int>(rr * cosf(rad)), 3,
                       COL_TEXT, COL_CARD);
}

/* Dibuixa el gauge sencer (primera vegada o en canviar de pantalla). */
void drawGauge(int cx, int cy, int r, int series, int pct, const char* label)
{
    drawGaugeFrame(cx, cy, r, series, label);
    const uint16_t fg = barColorFor(pct);
    if (pct > 0) {
        drawGaugeArcRange(cx, cy, r, 0, pct, fg, false);
    }
    drawGaugeNumber(cx, cy, r, -1, pct, fg);
    drawGaugeMaxMark(cx, cy, r, series, -1);
}

/* Actualitza NOMES el que ha canviat: el tros d'arc nou i el numero. */
void updateGauge(int cx, int cy, int r, int series, int oldPct, int pct,
                 int oldMax)
{
    if (pct == oldPct) {
        return;
    }
    const uint16_t fg = barColorFor(pct);
    if (pct > oldPct) {
        drawGaugeArcRange(cx, cy, r, oldPct, pct, fg, false);
    } else {
        drawGaugeArcRange(cx, cy, r, pct, oldPct, fg, true);
    }
    drawGaugeNumber(cx, cy, r, oldPct, pct, fg);
    drawGaugeMaxMark(cx, cy, r, series, oldMax);
}

/* Icona de la meteo segons el codi WMO. */
const char* weatherIcon(int code, bool day)
{
    if (code == 0)  return day ? "sun" : "moon";
    if (code <= 2)  return day ? "sun" : "moon";
    if (code == 3)  return "cloud";
    if (code >= 45 && code <= 48) return "fog";
    if (code >= 51 && code <= 67) return "rain";
    if (code >= 80 && code <= 82) return "rain";
    if (code >= 71 && code <= 86) return "snow";
    if (code >= 95) return "storm";
    return "cloud";
}

/* --- Menu (Pantalles · Ajustos · Sobre) ----------------------------------- *
 * Es una pantalla sencera amb TRES PESTANYES a dalt:
 *   - Pantalles: la llista de pantalles, per saltar-hi
 *   - Ajustos:   tot el que es pot configurar des de la placa
 *   - Sobre:     informacio del firmware i de l'estat
 * Cada pestanya es una llista de files que tambe es pot arrossegar amb el dit.
 */
enum MenuTab { TAB_PANTALLES = 0, TAB_AJUSTOS, TAB_SOBRE, TAB_COUNT };

const char* kTabNames[TAB_COUNT] = {"Pantalles", "Ajustos", "Sobre"};

int  gMenuTab    = TAB_PANTALLES;
int  gMenuScroll = 0;         /* primera fila visible */
int  gMenuRows   = 1;         /* files que hi caben */
int  gMenuRowH   = 38;
int  gMenuItems  = 0;         /* files de la pestanya actual */
int  gMenuDragY  = -1;        /* y on s'ha comencat a lliscar */
int  gMenuDragS  = 0;         /* scroll quan s'ha comencat */
bool gMenuMoved  = false;
/* El menu s'obre amb el mateix toc del boto ☰: aquell toc s'ha de consumir del
 * tot. Si no, en aixecar el dit (que encara es a sobre de la capcalera) cauria
 * a la zona de "tanca" i el menu es tancaria tot seguit. */
bool gMenuJustOpened = false;
/* Hi ha un dit a la pantalla ara mateix? El bucle principal crida touch() a
 * cada volta, tambe quan no es toca res (i aleshores les coordenades son les
 * de l'ultim toc, o (0,0)). Sense aixo, aquell "fals aixecament" tancava el
 * menu tot sol. */
bool gTouchDown = false;

constexpr int MENU_FOOT_H = 26;
constexpr int MENU_TAB_H  = 32;   /* barra de pestanyes */

/* Files de la pestanya d'ajustos. 'id' es el que enten settingsAction(). */
struct MenuRow {
    const char* id;
    const char* label;
    const char* icon;
};
const MenuRow kSetupRows[] = {
    {"bright",    "Brillantor",            "brightness_up"},
    {"theme",     "Tema",                  "system_settings"},
    {"themeauto", "Tema automatic",        "dark"},
    {"orient",    "Orientacio",            "grid"},
    {"standby",   "Repos de pantalla",     "sleep"},
    {"idle",      "Rellotge si inactiu",   "clock"},
    {"nav",       "Navegacio",             "next"},
    {"reset",     "Configuracio de fabrica", "undo"},
    {"restart",   "Reinicia la placa",     "eject"},
    {"close",     "Tanca el menu",         "lock"},
};
constexpr int SETUP_ROWS = sizeof(kSetupRows) / sizeof(kSetupRows[0]);

/* Files de la pestanya 'Sobre' (nomes informacio). */
enum AboutRow {
    AB_VERSIO = 0, AB_PLACA, AB_MEMORIA, AB_ENLLAC, AB_XARXA, AB_SD,
    AB_APPS, AB_PANTALLES, AB_HORA, AB_ENCESA, ABOUT_ROWS
};

/* Calcula quantes files hi caben i ajusta l'scroll. */
void menuLayout()
{
    const MacLink::Config& cfg = MacLink::config();
    const int H = Display::height();

    switch (gMenuTab) {
        case TAB_AJUSTOS:
            gMenuItems = SETUP_ROWS;
            break;
        case TAB_SOBRE:
            gMenuItems = ABOUT_ROWS;
            break;
        default:
            /* Sense enllac no hi ha cap pantalla on saltar. */
            gMenuItems = gNoLink ? 0 : cfg.pageCount;
            break;
    }
    const int area = H - HEADER_H - MENU_TAB_H - MENU_FOOT_H;

    gMenuRowH = 38;
    if (gMenuItems > 6 && area / gMenuRowH < 6) {
        gMenuRowH = area / 6;                   /* pantalles baixes */
        if (gMenuRowH < 24) {
            gMenuRowH = 24;
        }
    }
    gMenuRows = area / gMenuRowH;
    if (gMenuRows < 1) {
        gMenuRows = 1;
    }
    if (gMenuScroll > gMenuItems - gMenuRows) {
        gMenuScroll = gMenuItems - gMenuRows;
    }
    if (gMenuScroll < 0) {
        gMenuScroll = 0;
    }
}

/* Valor actual d'un ajust, per ensenyar-lo a la dreta de la fila. */
void setupValue(const char* id, char* out, size_t n)
{
    const MacLink::Config& cfg = MacLink::config();
    out[0] = '\0';
    if (strcmp(id, "bright") == 0) {
        snprintf(out, n, "%u%%", static_cast<unsigned>(gBrightPct));
    } else if (strcmp(id, "theme") == 0) {
        strlcpy(out, Th::name(themeFor()), n);
    } else if (strcmp(id, "themeauto") == 0) {
        strlcpy(out, gThemePref.autoMode ? "si" : "no", n);
    } else if (strcmp(id, "orient") == 0) {
        strlcpy(out, (cfg.orientation[0] == 'h') ? "horitzontal" : "vertical", n);
    } else if (strcmp(id, "standby") == 0) {
        strlcpy(out, standbyLabel(), n);
    } else if (strcmp(id, "idle") == 0) {
        if (cfg.idleMin == 0) {
            strlcpy(out, "mai", n);
        } else if (cfg.idleMin < 60) {
            snprintf(out, n, "%u min", static_cast<unsigned>(cfg.idleMin));
        } else {
            snprintf(out, n, "%u h", static_cast<unsigned>(cfg.idleMin / 60));
        }
    } else if (strcmp(id, "nav") == 0) {
        const char* v = cfg.nav;
        strlcpy(out, (strcmp(v, "bar") == 0)   ? "nomes barra"
                   : (strcmp(v, "swipe") == 0) ? "nomes lliscar"
                   : (strcmp(v, "off") == 0)   ? "sense navegacio"
                                               : "barra + lliscar", n);
    }
}

/* Pestanya 'Pantalles': la llista de pantalles. */
void drawMenuPages(int y0, int rows, int rowH)
{
    TFT_eSPI& t = Display::driver();
    const MacLink::Config& cfg = MacLink::config();
    const int W = Display::width();

    for (int i = 0; i < rows; ++i) {
        const int idx = gMenuScroll + i;
        if (idx >= gMenuItems) {
            break;
        }
        const int y = y0 + i * rowH;
        const bool cur = (idx == gPage);
        const uint16_t rowBg = cur ? COL_BTN_P : COL_BG;

        if (cur) {
            t.fillRoundRect(6, y + 2, W - 12, rowH - 4, 8, COL_BTN_P);
            t.fillRoundRect(10, y + 8, 3, rowH - 16, 1, COL_ACCENT);
        }
        if (cfg.pages[idx].icon[0] != '\0') {
            Icons::drawCentered(cfg.pages[idx].icon, 30, y + rowH / 2,
                                rowH - 14, rowBg);
        }
        setFontM(t);
        t.setTextDatum(ML_DATUM);
        t.setTextColor(cur ? COL_TEXT : COL_DIM, rowBg);
        t.drawString(cfg.pages[idx].name, 54, y + rowH / 2);

        setFontS(t);
        t.setTextDatum(MR_DATUM);
        t.setTextColor(COL_DIM, rowBg);
        t.drawString(cfg.pages[idx].layout, W - 16, y + rowH / 2);
    }
}

/* Pestanya 'Ajustos': cada fila es un ajust i el seu valor actual. */
void drawMenuSetup(int y0, int rows, int rowH)
{
    TFT_eSPI& t = Display::driver();
    const int W = Display::width();

    for (int i = 0; i < rows; ++i) {
        const int idx = gMenuScroll + i;
        if (idx >= gMenuItems) {
            break;
        }
        const int y = y0 + i * rowH;
        const MenuRow& r = kSetupRows[idx];
        /* Les que no es poden desfer es destaquen en groc. */
        const bool perill = (strcmp(r.id, "reset") == 0 ||
                             strcmp(r.id, "restart") == 0);

        t.drawFastHLine(PAD, y + rowH - 1, W - 2 * PAD, COL_EDGE);
        if (r.icon[0] != '\0') {
            Icons::drawCentered(r.icon, 30, y + rowH / 2, rowH - 16, COL_BG);
        }
        setFontM(t);
        t.setTextDatum(ML_DATUM);
        t.setTextColor(perill ? COL_WARN : COL_TEXT, COL_BG);
        t.drawString(r.label, 54, y + rowH / 2);

        char val[20];
        setupValue(r.id, val, sizeof(val));
        if (val[0] != '\0') {
            setFontS(t);
            t.setTextDatum(MR_DATUM);
            t.setTextColor(COL_ACCENT, COL_BG);
            t.drawString(val, W - 16, y + rowH / 2);
        }
    }
}

/* Pestanya 'Sobre': informacio del firmware i de l'estat. Nomes es mira. */
void drawMenuAbout(int y0, int rows, int rowH)
{
    TFT_eSPI& t = Display::driver();
    const MacLink::Stats& s = MacLink::stats();
    const int W = Display::width();

    /* Els valors es calculen un sol cop: son deu files. */
    char vals[ABOUT_ROWS][28];
    const char* labs[ABOUT_ROWS] = {
        "Firmware", "Placa", "Memoria", "Enllac", "Xarxa",
        "Targeta SD", "Apps obertes", "Pantalles", "Hora", "Encesa",
    };

    strlcpy(vals[AB_VERSIO], MP_VERSION, sizeof(vals[AB_VERSIO]));
    snprintf(vals[AB_PLACA], sizeof(vals[AB_PLACA]), "%s", ESP.getChipModel());
    snprintf(vals[AB_MEMORIA], sizeof(vals[AB_MEMORIA]), "%u KB lliures",
             static_cast<unsigned>(ESP.getFreeHeap() / 1024));
    strlcpy(vals[AB_ENLLAC],
            MacLink::linkUp() ? (s.host[0] ? s.host : "Mac") : "sense enllac",
            sizeof(vals[AB_ENLLAC]));
    strlcpy(vals[AB_XARXA], (Net::ip() != nullptr && Net::ip()[0])
                            ? Net::ip() : "sense WiFi",
            sizeof(vals[AB_XARXA]));
    snprintf(vals[AB_SD], sizeof(vals[AB_SD]), "%d icones", Icons::count());
    snprintf(vals[AB_APPS], sizeof(vals[AB_APPS]), "%d", MacLink::appCount());
    snprintf(vals[AB_PANTALLES], sizeof(vals[AB_PANTALLES]), "%d",
             MacLink::config().pageCount);
    strlcpy(vals[AB_HORA], clockNow(), sizeof(vals[AB_HORA]));
    {
        const uint32_t up = millis() / 1000UL;
        if (up < 3600UL) {
            snprintf(vals[AB_ENCESA], sizeof(vals[AB_ENCESA]), "%u min",
                     static_cast<unsigned>(up / 60));
        } else {
            snprintf(vals[AB_ENCESA], sizeof(vals[AB_ENCESA]), "%u h %u min",
                     static_cast<unsigned>(up / 3600),
                     static_cast<unsigned>((up / 60) % 60));
        }
    }

    for (int i = 0; i < rows; ++i) {
        const int idx = gMenuScroll + i;
        if (idx >= gMenuItems) {
            break;
        }
        const int y = y0 + i * rowH;

        t.drawFastHLine(PAD, y + rowH - 1, W - 2 * PAD, COL_EDGE);
        setFontS(t);
        t.setTextDatum(ML_DATUM);
        t.setTextColor(COL_DIM, COL_BG);
        t.drawString(labs[idx], 14, y + rowH / 2);

        setFontM(t);
        t.setTextDatum(MR_DATUM);
        t.setTextColor(COL_TEXT, COL_BG);
        t.drawString(vals[idx], W - 14, y + rowH / 2);
    }
}

void drawMenu()
{
    TFT_eSPI& t = Display::driver();
    const MacLink::Config& cfg = MacLink::config();
    const int W = Display::width();
    const int H = Display::height();

    menuLayout();
    Serial.printf("[UI] menu: %s, %d files de %d px\n",
                  kTabNames[gMenuTab], gMenuItems, gMenuRowH);

    drawBackground();

    /* Capcalera. */
    t.fillRect(0, 0, W, HEADER_H, COL_CARD);
    t.fillRoundRect(9, 8, 4, 15, 2, COL_ACCENT);
    setFontM(t);
    t.setTextDatum(ML_DATUM);
    t.setTextColor(COL_TEXT, COL_CARD);
    t.drawString("Menu", 21, HEADER_H / 2);
    setFontS(t);
    t.setTextDatum(MR_DATUM);
    t.setTextColor(COL_DIM, COL_CARD);
    t.drawString("tanca", W - 14, HEADER_H / 2);
    t.drawFastHLine(0, HEADER_H - 1, W, COL_EDGE);

    /* Barra de pestanyes. */
    const int ty = HEADER_H;
    t.fillRect(0, ty, W, MENU_TAB_H, COL_CARD);
    t.drawFastHLine(0, ty + MENU_TAB_H - 1, W, COL_EDGE);
    const int tw = W / TAB_COUNT;
    for (int i = 0; i < TAB_COUNT; ++i) {
        const bool actiu = (i == gMenuTab);
        const int tx = i * tw;
        setFontS(t);
        t.setTextDatum(MC_DATUM);
        t.setTextColor(actiu ? COL_TEXT : COL_DIM, COL_CARD);
        t.drawString(kTabNames[i], tx + tw / 2, ty + MENU_TAB_H / 2 - 3);
        if (actiu) {
            t.fillRoundRect(tx + tw / 2 - 24, ty + MENU_TAB_H - 5, 48, 3, 2,
                            COL_ACCENT);
        }
    }

    /* Contingut de la pestanya. */
    const int y0 = HEADER_H + MENU_TAB_H;
    if (gMenuItems == 0) {
        setFontS(t);
        t.setTextDatum(MC_DATUM);
        t.setTextColor(COL_DIM, COL_BG);
        t.drawString("(no hi ha res a mostrar)", W / 2, y0 + 40);
    } else if (gMenuTab == TAB_AJUSTOS) {
        drawMenuSetup(y0, gMenuRows, gMenuRowH);
    } else if (gMenuTab == TAB_SOBRE) {
        drawMenuAbout(y0, gMenuRows, gMenuRowH);
    } else {
        drawMenuPages(y0, gMenuRows, gMenuRowH);
    }

    /* Peu: fletxes i, a la pestanya de pantalles, quina es la actual. */
    const int fy = H - MENU_FOOT_H;
    t.fillRect(0, fy, W, MENU_FOOT_H, COL_CARD);
    t.drawFastHLine(0, fy, W, COL_EDGE);
    setFontS(t);
    t.setTextDatum(MC_DATUM);
    t.setTextColor(gMenuScroll > 0 ? COL_TEXT : COL_EDGE, COL_CARD);
    t.drawString("▲", 22, fy + MENU_FOOT_H / 2);
    t.setTextColor((gMenuScroll + gMenuRows < gMenuItems) ? COL_TEXT : COL_EDGE,
                   COL_CARD);
    t.drawString("▼", W - 22, fy + MENU_FOOT_H / 2);
    if (gMenuTab == TAB_PANTALLES) {
        char pos[28];
        snprintf(pos, sizeof(pos), "pantalla %d de %d", gPage + 1, cfg.pageCount);
        t.setTextColor(COL_DIM, COL_CARD);
        t.drawString(pos, W / 2, fy + MENU_FOOT_H / 2);
    }
}

/* Que hi ha sota el dit dins del menu? */
enum MenuZone { MZ_NONE, MZ_ITEM, MZ_TAB, MZ_CLOSE, MZ_UP, MZ_DOWN };

MenuZone menuZone(int16_t x, int16_t y, int& item, int& tab)
{
    item = -1;
    tab  = -1;
    const int W = Display::width();
    const int H = Display::height();

    if (y < HEADER_H) {
        return MZ_CLOSE;
    }
    if (y < HEADER_H + MENU_TAB_H) {           /* barra de pestanyes */
        tab = x / (W / TAB_COUNT);
        if (tab >= TAB_COUNT) {
            tab = TAB_COUNT - 1;
        }
        return MZ_TAB;
    }
    if (y >= H - MENU_FOOT_H) {
        if (x < W / 3)     return MZ_UP;
        if (x > W * 2 / 3) return MZ_DOWN;
        return MZ_NONE;
    }
    const int i = (y - HEADER_H - MENU_TAB_H) / gMenuRowH;
    const int idx = gMenuScroll + i;
    if (i >= 0 && i < gMenuRows && idx < gMenuItems) {
        item = idx;
        return MZ_ITEM;
    }
    return MZ_NONE;
}

/* --- Pantalla de rellotges circulars (gauges) ----------------------------- */
int  gGaugeCount = 0;
char gGaugeIds[MAX_GAUGES][12];
int  gGaugeCx[MAX_GAUGES];
int  gGaugeCy[MAX_GAUGES];
int  gGaugeR = 40;
int  gGaugeRArr[MAX_GAUGES];   /* radi de cada gauge (poden ser diferents) */
int  gGaugeLastPct[MAX_GAUGES];
int  gGaugeLastMax[MAX_GAUGES];   /* ultim maxim de l'historial dibuixat */

void drawGauges()
{
    const MacLink::Config& cfg = MacLink::config();
    const MacLink::Page& p = cfg.pages[gPage];
    const MacLink::Stats& s = MacLink::stats();
    const bool have = s.valid;

    const int W = Display::width();
    const int top = HEADER_H;
    const int bot = (gBtnCount > 0) ? (gBtnTop - PAD) : Display::height();

    gGaugeCount = 0;
    for (int i = 0; i < p.widgetCount && gGaugeCount < MAX_GAUGES; ++i) {
        const char* w = p.widgets[i];
        if (strcmp(w, "cpu") == 0 || strcmp(w, "mem") == 0 ||
            strcmp(w, "disk") == 0 || strcmp(w, "bat") == 0) {
            strlcpy(gGaugeIds[gGaugeCount], w, sizeof(gGaugeIds[0]));
            ++gGaugeCount;
        }
    }
    if (gGaugeCount == 0) {
        strlcpy(gGaugeIds[gGaugeCount++], "cpu", sizeof(gGaugeIds[0]));
        if (gGaugeCount < MAX_GAUGES) {
            strlcpy(gGaugeIds[gGaugeCount++], "mem", sizeof(gGaugeIds[0]));
        }
    }

    /* Repartiment. Amb 4 gauges fem com els panells de control dels PCs: un
     * anell gran a dalt i la resta petits en una fila a sota. */
    if (gGaugeCount == 4) {
        const int H = bot - top;

        int heroR = W / 2 - 34;
        const int maxHero = (H * 46) / 100 / 2;
        if (heroR > maxHero) heroR = maxHero;
        if (heroR < 32) heroR = 32;
        gGaugeCx[0] = W / 2;
        gGaugeCy[0] = top + heroR + 18;
        gGaugeRArr[0] = heroR;

        const int cell = W / 3;
        int smallR = cell / 2 - 10;
        const int maxSmall = (H * 26) / 100 / 2;
        if (smallR > maxSmall) smallR = maxSmall;
        if (smallR < 20) smallR = 20;
        const int smallCy = bot - smallR - 30;
        for (int i = 1; i < 4; ++i) {
            gGaugeCx[i] = (i - 1) * cell + cell / 2;
            gGaugeCy[i] = smallCy;
            gGaugeRArr[i] = smallR;
        }
        gGaugeR = heroR;
    } else {
        /* 1, 2 o 3 gauges: graella simple (1 = gran, 3 = en fila). */
        const int cols = (gGaugeCount == 1) ? 1 : ((gGaugeCount == 3) ? 3 : 2);
        const int rows = (gGaugeCount + cols - 1) / cols;
        const int cw = W / cols;
        const int ch = (bot - top) / rows;
        const int maxR = (gGaugeCount == 1) ? 108 : 72;
        int r = ((cw < ch) ? cw : ch) / 2 - 10;
        if (r < 24) r = 24;
        if (r > maxR) r = maxR;
        gGaugeR = r;
        for (int i = 0; i < gGaugeCount; ++i) {
            gGaugeCx[i] = (i % cols) * cw + cw / 2;
            gGaugeCy[i] = top + (i / cols) * ch + ch / 2 - 8;
            gGaugeRArr[i] = r;
        }
    }

    for (int i = 0; i < gGaugeCount; ++i) {
        WidgetView v;
        buildWidget(gGaugeIds[i], s, have, v);
        const int pct = (v.pct < 0) ? 0 : v.pct;
        const int series = History::seriesFor(gGaugeIds[i]);
        gGaugeLastPct[i] = pct;
        gGaugeLastMax[i] = (series >= 0 && History::count(series) > 4)
                           ? clampPct(History::maxValue(series)) : -1;
        drawGauge(gGaugeCx[i], gGaugeCy[i], gGaugeRArr[i], series, pct, v.label);
    }
}

/* Redibuixa nomes els gauges que han canviat (sense parpelleig). */
void refreshGauges()
{
    const MacLink::Stats& s = MacLink::stats();
    for (int i = 0; i < gGaugeCount; ++i) {
        WidgetView v;
        buildWidget(gGaugeIds[i], s, s.valid, v);
        const int pct = (v.pct < 0) ? 0 : v.pct;
        const int series = History::seriesFor(gGaugeIds[i]);
        const int mx = (series >= 0 && History::count(series) > 4)
                       ? clampPct(History::maxValue(series)) : -1;

        if (pct != gGaugeLastPct[i] || mx != gGaugeLastMax[i]) {
            /* Nomes repinta el tros d'arc que ha canviat: sense flaix. */
            updateGauge(gGaugeCx[i], gGaugeCy[i], gGaugeRArr[i], series,
                        gGaugeLastPct[i], pct, gGaugeLastMax[i]);
            gGaugeLastPct[i] = pct;
            gGaugeLastMax[i] = mx;
        }
    }
}

/* --- Pantalla de grafics (historial de CPU, RAM...) ----------------------- */
int   gGraphCount = 0;
int   gGraphSeries[MAX_GAUGES];
int   gGraphX[MAX_GAUGES];
int   gGraphY[MAX_GAUGES];
int   gGraphW[MAX_GAUGES];
int   gGraphH[MAX_GAUGES];
float gGraphLast[MAX_GAUGES];

/* Color de cada serie. */
uint16_t chartColorFor(int series)
{
    switch (series) {
        case History::CPU:  return COL_ACCENT;
        case History::MEM:  return COL_OK;
        case History::DISK: return COL_WARN;
        case History::BAT:  return COL_OK;
        case History::LOAD: return COL_WARN;
        default:            return COL_ACCENT;
    }
}

/* Marca fixa del grafic (targeta, titol i filet de color). Nomes es dibuixa
 * un cop, aixi quan s'actualitza el grafic no parpelleja tota la targeta. */
void drawChartFrame(int x, int y, int w, int h, int series)
{
    TFT_eSPI& t = Display::driver();
    t.fillRoundRect(x, y, w, h, 10, COL_CARD);
    t.drawRoundRect(x, y, w, h, 10, COL_EDGE);

    t.fillRoundRect(x + 8, y + 9, 4, 15, 2, chartColorFor(series));

    setFontM(t);
    t.setTextDatum(ML_DATUM);
    t.setTextColor(COL_TEXT, COL_CARD);
    t.drawString(History::name(series), x + 18, y + 17);
}

/* Part viva del grafic: quadricula, area, linia, valor actual i estadistiques.
 * Es repinta a cada mostra nova. */
void drawChartPlot(int x, int y, int w, int h, int series)
{
    TFT_eSPI& t = Display::driver();
    const uint16_t line = chartColorFor(series);
    const uint16_t fill = t.alphaBlend(80, line, COL_CARD);

    const int px = x + 12;
    const int py = y + 36;
    const int pw = w - 24;
    const int ph = h - 36 - 26;
    if (pw < 16 || ph < 12) {
        return;
    }

    /* Valor actual, gran i del color de la serie. */
    const float cur = History::lastValue(series);
    char val[20];
    if (History::isPercent(series)) {
        snprintf(val, sizeof(val), "%d%%", static_cast<int>(cur + 0.5f));
    } else {
        snprintf(val, sizeof(val), "%.2f", cur);
    }
    t.fillRect(x + w - 86, y + 4, 78, 26, COL_CARD);
    setFontM(t);
    t.setTextDatum(TR_DATUM);
    t.setTextColor(line, COL_CARD);
    t.drawString(val, x + w - 12, y + 17);

    /* Escala vertical: percentatges sempre de 0 a 100; la resta s'adapta. */
    float lo = 0.0f;
    float hi = 100.0f;
    if (!History::isPercent(series)) {
        hi = History::maxValue(series);
        if (hi < 1.0f) {
            hi = 1.0f;
        }
        hi *= 1.2f;
    }
    const float span = (hi - lo) > 0.001f ? (hi - lo) : 1.0f;

    /* Cada columna es pinta UN SOL COP: primer el buit de dalt (amb el color de
     * la targeta, que esborra la linia anterior), despres l'area i el punt de la
     * linia. Aixi no cal esborrar tota la zona abans i no hi ha cap flaix. */
    const int n = History::count(series);
    if (n >= 2) {
        float vals[History::SAMPLES];
        for (int i = 0; i < n; ++i) {
            vals[i] = History::value(series, i);
        }

        for (int gx = px; gx < px + pw; ++gx) {
            const float f = static_cast<float>(gx - px) * (n - 1) / (pw - 1);
            const int   i0 = static_cast<int>(f);
            const int   i1 = (i0 + 1 < n) ? (i0 + 1) : i0;
            const float fr = f - static_cast<float>(i0);
            float v = vals[i0] * (1.0f - fr) + vals[i1] * fr;
            if (v < lo) v = lo;
            if (v > hi) v = hi;
            const int gy = py + ph - static_cast<int>((v - lo) * ph / span);

            if (gy > py) {
                t.drawFastVLine(gx, py, gy - py, COL_CARD);      /* buit */
            }
            if (gy < py + ph) {
                t.drawFastVLine(gx, gy, py + ph - gy, fill);     /* area */
            }
            t.drawPixel(gx, gy, line);                           /* linia */
            if (gy + 1 < py + ph) {
                t.drawPixel(gx, gy + 1, line);
            }
        }
    }

    /* Quadricula, A SOBRE (puntets discrets): es veu tambe sobre l'area i, com
     * que es sempre al mateix lloc, no parpelleja. */
    for (int i = 1; i < 4; ++i) {
        const int gy = py + (ph * i) / 4;
        for (int gx = px; gx < px + pw - 4; gx += 9) {
            t.drawPixel(gx, gy, COL_EDGE);
        }
    }
    for (int i = 1; i < 4; ++i) {
        const int gx = px + (pw * i) / 4;
        for (int gy = py; gy < py + ph - 4; gy += 9) {
            t.drawPixel(gx, gy, COL_EDGE);
        }
    }

    /* Puntet de "ara mateix", amb un anell al seu voltant. */
    {
        const int n2 = History::count(series);
        if (n2 >= 2) {
            float v = History::value(series, n2 - 1);
            if (v < lo) v = lo;
            if (v > hi) v = hi;
            const int dx = px + pw - 1;
            const int dy = py + ph - static_cast<int>((v - lo) * ph / span);
            t.fillSmoothCircle(dx, dy, 4, line, COL_CARD);
            t.fillSmoothCircle(dx, dy, 2, COL_CARD, line);
        }
    }

    /* min / mitjana / max. */
    char st[56];
    const float mn = History::minValue(series);
    const float mx = History::maxValue(series);
    const float av = History::avgValue(series);
    if (History::isPercent(series)) {
        snprintf(st, sizeof(st), "min %d    mitjana %d    max %d",
                 static_cast<int>(mn + 0.5f), static_cast<int>(av + 0.5f),
                 static_cast<int>(mx + 0.5f));
    } else {
        snprintf(st, sizeof(st), "min %.2f   mitjana %.2f   max %.2f", mn, av, mx);
    }
    t.fillRect(x + 8, y + h - 22, w - 16, 20, COL_CARD);
    setFontS(t);
    t.setTextDatum(MC_DATUM);
    t.setTextColor(COL_DIM, COL_CARD);
    t.drawString(st, x + w / 2, y + h - 12);
}

/* Calcula la disposicio dels grafics (1 a 4) dins de l'espai disponible. */
void layoutGraphs(int top, int bot)
{
    const MacLink::Config& cfg = MacLink::config();
    const MacLink::Page& p = cfg.pages[gPage];
    const int W = Display::width();

    gGraphCount = 0;
    for (int i = 0; i < p.widgetCount && gGraphCount < MAX_GAUGES; ++i) {
        const int s = History::seriesFor(p.widgets[i]);
        if (s >= 0) {
            gGraphSeries[gGraphCount++] = s;
        }
    }
    if (gGraphCount == 0) {                  /* per defecte: CPU i RAM */
        gGraphSeries[gGraphCount++] = History::CPU;
        if (gGraphCount < MAX_GAUGES) {
            gGraphSeries[gGraphCount++] = History::MEM;
        }
    }

    /* En horitzontal i amb 3 o 4 grafics, els posem en 2 columnes. */
    const bool wide = (Display::width() > Display::height());
    const int cols = (wide && gGraphCount >= 3) ? 2 : 1;
    const int rows = (gGraphCount + cols - 1) / cols;
    const int cw = W - 2 * PAD;
    const int ch = (bot - top) / rows;

    for (int i = 0; i < gGraphCount; ++i) {
        const int col = i % cols;
        const int row = i / cols;
        const int cellW = (cols == 1) ? cw : (cw - PAD) / 2;
        gGraphX[i] = PAD + col * (cellW + PAD);
        gGraphY[i] = top + row * ch + PAD / 2;
        gGraphW[i] = cellW;
        gGraphH[i] = ch - PAD;
    }
}

void drawGraphs()
{
    for (int i = 0; i < gGraphCount; ++i) {
        drawChartFrame(gGraphX[i], gGraphY[i], gGraphW[i], gGraphH[i], gGraphSeries[i]);
        drawChartPlot(gGraphX[i], gGraphY[i], gGraphW[i], gGraphH[i], gGraphSeries[i]);
        gGraphLast[i] = History::lastValue(gGraphSeries[i]);
    }
}

/* Repinta NOMES els grafics que han rebut una mostra nova. */
void refreshGraphs()
{
    for (int i = 0; i < gGraphCount; ++i) {
        const float v = History::lastValue(gGraphSeries[i]);
        if (v != gGraphLast[i]) {
            gGraphLast[i] = v;
            drawChartPlot(gGraphX[i], gGraphY[i], gGraphW[i], gGraphH[i],
                          gGraphSeries[i]);
        }
    }
}

/* --- Temperatura amb el simbol de graus ----------------------------------- *
 * Les fonts FreeSans que fa servir TFT_eSPI nomes cobreixen ASCII (0x20..0x7E),
 * aixi que el simbol de graus no hi es: si l'escrivissim sortiria buit. El
 * dibuixem nosaltres amb un cerclet prim, que a mes queda mes fi.
 *
 * 'yBase' es la linia on seuen els numeros (datum L_BASELINE). Amb la font L
 * (18 pt) els digits van de yBase-24 a yBase+1; amb la S (9 pt) la 'C' fa 12
 * d'alçada, i la posem amb la part de dalt alineada amb la dels numeros. */
void drawTemp(TFT_eSPI& t, float temp, int cx, int yBase, uint16_t colNum,
              uint16_t colSym)
{
    char num[12];
    snprintf(num, sizeof(num), "%.0f", temp);

    setFontL(t);
    const int wNum = t.textWidth(num);
    setFontS(t);
    const int wC = t.textWidth("C");

    constexpr int kGap  = 6;   /* numeros -> cerclet */
    constexpr int kRad  = 3;   /* radi del cerclet de graus */
    constexpr int kGap2 = 2;   /* cerclet -> 'C' */
    const int total = wNum + kGap + 2 * kRad + kGap2 + wC;
    const int xNum  = cx - total / 2;

    /* Numeros, grans. */
    setFontL(t);
    t.setTextDatum(L_BASELINE);
    t.setTextColor(colNum, COL_BG);
    t.drawString(num, xNum, yBase);

    /* Cerclet de graus, arran de dalt dels numeros. */
    const int gx = xNum + wNum + kGap + kRad;
    t.drawCircle(gx, yBase - 20, kRad, colSym);

    /* 'C' petita, a la dreta del cerclet. */
    setFontS(t);
    t.setTextDatum(L_BASELINE);
    t.setTextColor(colSym, COL_BG);
    t.drawString("C", gx + kRad + kGap2, yBase - 12);
}

/* --- Pantalla de rellotge + data + meteo + previsio + agenda -------------- */
void drawClock()
{
    TFT_eSPI& t = Display::driver();
    const MacLink::Stats& s = MacLink::stats();
    const int W = Display::width();
    const int top = HEADER_H;
    const int bot = (gBtnCount > 0) ? (gBtnTop - PAD) : Display::height();
    const int h = bot - top;

    t.setTextDatum(MC_DATUM);

    /* Hora gran. */
    setFontB(t);
    t.setTextColor(COL_TEXT, COL_BG);
    t.drawString(clockNow(), W / 2, top + h * 15 / 100);

    /* Data + dia de la setmana, dins d'una pastilla suau. */
    char dt[28];
    snprintf(dt, sizeof(dt), "%s %s", s.wday, s.dateStr);
    setFontS(t);
    const int dw = t.textWidth(dt);
    const int dy = top + h * 29 / 100;
    t.fillRoundRect(W / 2 - dw / 2 - 12, dy - 12, dw + 24, 24, 12, COL_CARD);
    t.setTextColor(COL_DIM, COL_CARD);
    t.drawString(dt, W / 2, dy);

    /* Meteo actual: icona gran + temperatura amb el seu simbol de graus. */
    if (s.valid) {
        const int iy = top + h * 48 / 100;
        Icons::drawCentered(weatherIcon(s.wcode, s.isDay != 0), W / 2, iy, 48, COL_BG);
        drawTemp(t, s.temp, W / 2, iy + 58, COL_TEXT, COL_DIM);
    }

    /* Previsio de 3 dies, en targetes arrodonides. */
    const int nf = MacLink::forecastCount();
    if (nf > 0) {
        const int fy = top + h * 85 / 100;
        const int cw = (W - 2 * PAD) / nf;
        const int cy0 = fy - 30;
        for (int i = 0; i < nf; ++i) {
            const MacLink::ForecastDay& d = MacLink::forecast(i);
            const int cx = PAD + i * cw + cw / 2;
            const int cwd = cw - 6;
            t.fillRoundRect(cx - cwd / 2, cy0, cwd, 62, 9, COL_CARD);
            t.drawRoundRect(cx - cwd / 2, cy0, cwd, 62, 9, COL_EDGE);

            Icons::drawCentered(weatherIcon(d.code, true), cx, cy0 + 19, 24, COL_CARD);

            char tt[16];
            snprintf(tt, sizeof(tt), "%d/%d", d.tmax, d.tmin);
            setFontS(t);
            t.setTextDatum(MC_DATUM);
            t.setTextColor(COL_DIM, COL_CARD);
            t.drawString(tt, cx, cy0 + 47);
        }
    }

    /* Agenda: proper esdeveniment del Mac. */
    const char* ev = MacLink::nextEvent();
    if (ev != nullptr && ev[0] != '\0') {
        setFontS(t);
        t.setTextDatum(MC_DATUM);
        t.setTextColor(COL_ACCENT, COL_BG);
        t.drawString(ev, W / 2, bot - 12);
    }
}

/* --- Hora local de la placa ----------------------------------------------- *
 * Quan hi ha enllac, l'hora ve del Mac i se sincronitza cada segon. Quan no
 * n'hi ha (el Mac dorm, esta apagat o s'ha desendollat), la seguim comptant
 * nosaltres amb millis(): aixi el rellotge no es queda congelat a l'ultima
 * hora rebuda. El cristall de l'ESP32 va sobrat per a unes quantes hores. */
uint16_t gClockMin  = 0xFFFF;   /* minuts des de mitjanit (0xFFFF = encara no) */
uint32_t gClockBase = 0;        /* millis() d'aquell moment */

void clockSync(const char* hhmm)
{
    if (hhmm == nullptr || hhmm[0] == '\0') {
        return;
    }
    int h = 0;
    int m = 0;
    if (sscanf(hhmm, "%d:%d", &h, &m) != 2) {
        return;
    }
    gClockMin  = static_cast<uint16_t>((h % 24) * 60 + (m % 60));
    gClockBase = millis();
}

/* Hora actual "HH:MM" (extrapolada si no hi ha enllac). */
const char* clockNow()
{
    static char buf[8];
    if (gClockMin == 0xFFFF) {
        return "--:--";
    }
    const uint32_t mins = gClockMin + (millis() - gClockBase) / 60000UL;
    snprintf(buf, sizeof(buf), "%02u:%02u",
             static_cast<unsigned>((mins / 60) % 24),
             static_cast<unsigned>(mins % 60));
    return buf;
}

/* --- Pantalla de repòs: rellotge + previsio ------------------------------- */
/* Surt tota sola quan el Mac fa estona que no rep cap input: es com el
 * salvapantalles del Mac, pero amb informacio util (hora, data, temps d'ara i
 * la previsio dels proxims dies) i sense cap boto. Qualsevol toc la treu. */
bool gIdleMode = false;
char gIdleSig[56] = "";

void drawIdleScreen()
{
    TFT_eSPI& t = Display::driver();
    const MacLink::Stats& s = MacLink::stats();
    const int W = Display::width();
    const int H = Display::height();
    const bool have = s.valid;

    drawBackground();
    /* Aquesta pantalla no te capcalera: si la marquesina estava engegada,
     * s'aturaria a sobre. */
    gMarqOn = false;
    t.setTextDatum(MC_DATUM);

    /* Indicador de dalt: per que som aqui (inactiu o sense enllac). */
    setFontS(t);
    t.setTextDatum(TC_DATUM);
    t.setTextColor(COL_EDGE, COL_BG);
    char info[44];
    snprintf(info, sizeof(info), "%s · %s", have ? s.host : "Mac Panel",
             gNoLink ? "sense enllac" : "en repos");
    t.drawString(info, W / 2, 12);

    /* Hora enorme (la de la placa: segueix comptant si el Mac no hi es). */
    setFontB(t);
    t.setTextDatum(MC_DATUM);
    t.setTextColor(COL_TEXT, COL_BG);
    t.drawString(clockNow(), W / 2, H * 28 / 100);

    /* Data i dia de la setmana, dins d'una pastilla. */
    char dt[28];
    snprintf(dt, sizeof(dt), "%s %s", s.wday, s.dateStr);
    setFontM(t);
    const int dw = t.textWidth(dt);
    const int dy = H * 28 / 100 + 46;
    t.fillRoundRect(W / 2 - dw / 2 - 14, dy - 15, dw + 28, 30, 15, COL_CARD);
    t.setTextColor(COL_DIM, COL_CARD);
    t.drawString(dt, W / 2, dy);

    /* Temps d'ara: icona gran + temperatura amb el seu simbol de graus. */
    if (have) {
        const int iy = H * 55 / 100;
        Icons::drawCentered(weatherIcon(s.wcode, s.isDay != 0),
                            W / 2 - 40, iy, 54, COL_BG);
        drawTemp(t, s.temp, W / 2 + 36, iy + 13, COL_TEXT, COL_DIM);
    }

    /* Previsio dels proxims dies, en targetes. */
    const int nf = MacLink::forecastCount();
    if (nf > 0) {
        const int cw  = (W - 2 * PAD) / nf;
        const int cy0 = H * 78 / 100;
        for (int i = 0; i < nf; ++i) {
            const MacLink::ForecastDay& d = MacLink::forecast(i);
            const int cx  = PAD + i * cw + cw / 2;
            const int cwd = cw - 6;
            t.fillRoundRect(cx - cwd / 2, cy0, cwd, 66, 10, COL_CARD);
            t.drawRoundRect(cx - cwd / 2, cy0, cwd, 66, 10, COL_EDGE);
            Icons::drawCentered(weatherIcon(d.code, true), cx, cy0 + 20, 26, COL_CARD);
            char tt[16];
            snprintf(tt, sizeof(tt), "%d/%d", d.tmax, d.tmin);
            setFontS(t);
            t.setTextDatum(MC_DATUM);
            t.setTextColor(COL_DIM, COL_CARD);
            t.drawString(tt, cx, cy0 + 50);
        }
    }
}

}  // namespace

namespace Ui {

/* Definida mes avall (la crida layout()). */
void drawNavBar();

void refresh(const MacLink::Stats& s, bool linkUp)
{
    const bool have = s.valid;
    const MacLink::Config& cfg = MacLink::config();

    /* L'hora del Mac es la bona: la prenem com a referencia de la nostra. */
    if (have) {
        clockSync(s.timeStr);
    }

    /* Amb el menu obert no repintem res: el menu tapa tota la pantalla i, si
     * redibuixessim les files de gadgets, hi apareixerien a sobre. */
    if (gMenuOpen) {
        return;
    }

    /* Tema automatic: si el Mac ha canviat de clar a fosc (o al reves), tornem a
     * pintar-ho tot amb l'altre tema. */
    if (themeFor() != Th::current()) {
        Serial.printf("[UI] el Mac es %s: tema automatic\n",
                      (s.dark != 0) ? "fosc" : "clar");
        gIdleSig[0] = '\0';
        layout();
        return;                     /* layout() ja ho ha pintat tot */
    }

    /* Sense enllac amb el Mac no hi ha dades noves ni cap boto que pugui fer
     * res: nomes te sentit el rellotge i els ajustos de la placa. */
    if (gNoLink != !linkUp) {
        gNoLink = !linkUp;
        gIdleSig[0] = '\0';
        Serial.printf("[UI] %s\n", gNoLink
                      ? "sense enllac: nomes rellotge i ajustos de la placa"
                      : "enllac recuperat: pantalles normals");
        layout();
        return;                        /* layout() ja ho ha pintat tot */
    }

    /* Pantalla de repòs: nomes la repintem quan canvia alguna cosa. */
    if (gIdleMode || gNoLink) {
        char sig[56];
        snprintf(sig, sizeof(sig), "%s|%s|%.0f|%d|%d|%d",
                 clockNow(), have ? s.dateStr : "",
                 have ? s.temp : 0.0, have ? static_cast<int>(s.wcode) : 0,
                 MacLink::forecastCount(), gNoLink ? 1 : 0);
        if (strcmp(sig, gIdleSig) != 0) {
            strlcpy(gIdleSig, sig, sizeof(gIdleSig));
            drawIdleScreen();
        }
        return;
    }

    /* Marquesina de la capcalera: si el nom del Mac no hi cap, va passant. */
    updateMarquee();

    if (strcmp(gLastTime, have ? s.timeStr : "") != 0 ||
        strcmp(gLastHost, have ? s.host : "") != 0 ||
        gLastLink != (linkUp ? 1 : 0)) {
        drawHeader(linkUp, s, have);
        strlcpy(gLastTime, have ? s.timeStr : "", sizeof(gLastTime));
        strlcpy(gLastHost, have ? s.host : "", sizeof(gLastHost));
        gLastLink = linkUp ? 1 : 0;
    }

    if (gPage < 0 || gPage >= cfg.pageCount) {
        return;
    }
    const MacLink::Page& p = cfg.pages[gPage];

    /* Pantalles de gauges, grafics i rellotge: actualitzem nomes el que canvia. */
    if (strcmp(p.layout, "gauges") == 0) {
        refreshGauges();
        return;
    }
    if (strcmp(p.layout, "graph") == 0) {
        refreshGraphs();
        return;
    }
    if (strcmp(p.layout, "clock") == 0) {
        char sig[48];
        snprintf(sig, sizeof(sig), "%s|%s|%.0f|%d",
                 clockNow(), s.dateStr, s.temp, static_cast<int>(s.wcode));
        if (strcmp(sig, gLastSig) != 0) {
            strlcpy(gLastSig, sig, sizeof(gLastSig));
            drawClock();
        }
        return;
    }

    for (int i = 0; i < gRowCount && i < p.widgetCount; ++i) {
        WidgetView v;
        buildWidget(p.widgets[i], s, have, v);
        if (strcmp(v.value, gLastVal[i]) != 0 || v.pct != gLastPct[i]) {
            updateRow(i, v);          /* nomes el que canvia: sense flaix */
            strlcpy(gLastVal[i], v.value, sizeof(gLastVal[i]));
            gLastPct[i] = v.pct;
        }
    }
}

void layout()
{
    TFT_eSPI& t = Display::driver();
    const MacLink::Config& cfg = MacLink::config();

    /* Orientacio (vertical / horitzontal) — display I tactil. */
    const uint8_t rot = (cfg.orientation[0] == 'h') ? 1 : 0;
    Display::setRotation(rot);
    Touch::setRotation(rot);
    const int W = Display::width();
    const int H = Display::height();

    if (gPage >= cfg.pageCount) gPage = 0;
    if (gPage < 0)               gPage = 0;

    /* Tema de colors (manual o segons el Mac). */
    themePrefSync(cfg);
    Th::set(themeFor());

    /* Si el menu es obert, el repinta ell (pot haver canviat l'orientacio o el
     * tema) i no hi ha res mes a fer. */
    if (gMenuOpen) {
        drawMenu();
        return;
    }

    /* La pantalla de repòs (rellotge) te prioritat sobre qualsevol pantalla:
     * o perque el Mac esta inactiu, o perque no hi ha enllac i no hi ha res
     * mes a fer. */
    if (gIdleMode || gNoLink) {
        gIdleSig[0] = '\0';
        drawIdleScreen();
        return;
    }

    /* Navegacio: la configura el Mac ("both" | "bar" | "swipe" | "off"). Sense
     * enllac no hi ha pantalles a les quals navegar, aixi que no hi ha barra. */
    gTabCount = cfg.pageCount;
    gMenuOpen = false;
    gNavBar   = !gNoLink &&
                (strcmp(cfg.nav, "bar") == 0 || strcmp(cfg.nav, "both") == 0);
    gNavSwipe = !gNoLink &&
                (strcmp(cfg.nav, "swipe") == 0 || strcmp(cfg.nav, "both") == 0);

    const int contentTop = HEADER_H;
    /* La barra de navegacio de baix es reserva AQUI: aixi els botons i els
     * gadgets mai no hi queden a sota. */
    const int contentBot = H - (gNavBar ? NAV_H : 0);

    const MacLink::Page* pg = (cfg.pageCount > 0) ? &cfg.pages[gPage] : nullptr;
    const bool isNumpad   = pg && strcmp(pg->layout, "numpad") == 0;
    const bool isGauges   = pg && strcmp(pg->layout, "gauges") == 0;
    const bool isClock    = pg && strcmp(pg->layout, "clock")  == 0;
    const bool isStatus   = pg && strcmp(pg->layout, "status") == 0;
    const bool isLauncher = pg && strcmp(pg->layout, "launcher") == 0;
    const bool isGraph    = pg && strcmp(pg->layout, "graph")  == 0;
    const bool isTabs     = pg && strcmp(pg->layout, "tabs")   == 0;

    /* Botons (el teclat numeric, el launcher i les pestanyes en generen de propis). */
    gBtnCols = isNumpad ? 4 : ((isLauncher || isTabs) ? 2 : BTN_COLS);
    if (isNumpad) {
        buildNumpad();
        gBtnCount = NUMPAD_COUNT;
    } else if (isLauncher) {
        buildLauncher();
        gBtnCount = gLaunchCount;
    } else if (isTabs) {
        buildTabs();
        gBtnCount = gTabsCount;
    } else if (pg) {
        gBtnCount = pg->buttonCount;
    } else {
        gBtnCount = 0;
    }

    gBtnRows = (gBtnCount + gBtnCols - 1) / gBtnCols;
    if (gBtnRows < 1) {
        gBtnRows = 1;
    }
    gBtnCellW = (W - PAD * (gBtnCols + 1)) / gBtnCols;

    const int gapTotal = (gBtnRows - 1) * BTN_GAP;
    const int minBtnH  = 20;

    /* Files de gadgets (nomes a la disposicio "status"). Primer reservem
     * l'espai dels botons i la resta es per als gadgets: aixi MAI se
     * solapen. */
    gRowCount = isStatus ? pg->widgetCount : 0;
    int rowH = WIDGET_ROW_H;
    if (gRowCount > 0 && gBtnCount > 0) {
        const int btnNeed = gBtnRows * minBtnH + gapTotal + 2 * PAD;
        while (rowH > 20 &&
               ((contentBot - contentTop) - gRowCount * rowH) < btnNeed) {
            rowH -= 2;
        }
    }

    int y = contentTop;
    for (int i = 0; i < gRowCount; ++i) {
        gRows[i].y = y;
        gRows[i].h = rowH;
        y += rowH;
    }

    /* Geometria dels botons, sempre dins de la pantalla. */
    if (isGauges || isClock || isGraph) {
        /* Els botons van a baix de tot; els gauges/rellotge omplen la resta. */
        gBtnCellH = 50;
        gBtnTop = (gBtnCount > 0) ? (contentBot - (gBtnRows * (gBtnCellH + BTN_GAP)))
                                  : (contentBot - 1);
    } else if (gBtnCount > 0) {
        gBtnTop = y + PAD;
        if (gBtnTop > contentBot - minBtnH - PAD) {
            gBtnTop = contentBot - minBtnH - PAD;
        }
        const int availH = contentBot - gBtnTop - PAD;
        gBtnCellH = (availH - gapTotal) / gBtnRows;
        if (gBtnCellH < minBtnH) gBtnCellH = minBtnH;
        if (gBtnCellH > 90)      gBtnCellH = 90;
    } else {
        gBtnTop = contentBot - 1;
        gBtnCellH = minBtnH;
    }

    /* Pantalla fosca mentre es pinta: no es veu res a mig fer. */
    const uint8_t bl = Display::backlight();
    Display::setBacklight(0);

    /* Fons amb un degradat vertical molt suau (en lloc d'un color pla): dona
     * profunditat i fa que no sembli tan "de casa". */
    drawBackground();
    gPressed = -1;

    if (isGauges) {
        drawGauges();
    } else if (isGraph) {
        layoutGraphs(contentTop, (gBtnCount > 0) ? (gBtnTop - PAD) : contentBot);
        drawGraphs();
    } else if (isClock) {
        drawClock();
    } else {
        for (int i = 0; i < gRowCount; ++i) {
            WidgetView v;
            buildWidget(pg->widgets[i], MacLink::stats(), MacLink::stats().valid, v);
            drawRowFull(i, v);
            strlcpy(gLastVal[i], v.value, sizeof(gLastVal[i]));
            gLastPct[i] = v.pct;
        }
    }

    drawAllButtons();
    drawNavBar();

    invalidate();
    refresh(MacLink::stats(), MacLink::linkUp());

    Display::setBacklight(bl);
}

void begin()
{
    layout();
}

int currentPage()
{
    return gPage;
}

void setPage(int index)
{
    const MacLink::Config& cfg = MacLink::config();
    if (index < 0 || index >= cfg.pageCount || index == gPage) {
        return;
    }
    gPage = index;
    layout();
}

/* --- Pantalla de repòs (rellotge) ----------------------------------------- */

void setIdleMode(bool on)
{
    if (on == gIdleMode) {
        return;
    }
    gIdleMode = on;
    gIdleSig[0] = '\0';
    Serial.printf("[UI] pantalla de repòs %s\n", on ? "activada" : "desactivada");
    layout();
}

bool idleMode()
{
    return gIdleMode;
}

/* Pantalla assignada a aquesta aplicacio (bundle id), o -1 si cap. */
int pageForApp(const char* bundle)
{
    if (bundle == nullptr || bundle[0] == '\0') {
        return -1;
    }
    const MacLink::Config& cfg = MacLink::config();
    for (int i = 0; i < cfg.pageCount; ++i) {
        for (int j = 0; j < cfg.pages[i].appCount; ++j) {
            if (strcasecmp(cfg.pages[i].apps[j], bundle) == 0) {
                return i;
            }
        }
    }
    return -1;
}

int hitTest(int16_t x, int16_t y)
{
    /* Sense enllac els botons no poden fer res (cada un envia una comanda o una
     * tecla al Mac), aixi que no es poden pitjar. */
    if (gNoLink) {
        return -1;
    }
    for (int i = 0; i < gBtnCount; ++i) {
        int bx = 0, by = 0, bw = 0, bh = 0;
        buttonRect(i, bx, by, bw, bh);
        if (x >= bx && x < bx + bw && y >= by && y < by + bh) {
            return i;
        }
    }
    return -1;
}

const MacLink::Button* buttonAt(int index)
{
    return pageButton(index);
}

/* --- Barra de navegacio de baix ------------------------------------------- */
bool gNavLatched = false;
bool gMenuBtnLatched = false;     /* el boto ☰ nomes actua un cop per toc */

void drawNavBar()
{
    if (!gNavBar || gMenuOpen) {
        return;
    }
    const MacLink::Config& cfg = MacLink::config();
    TFT_eSPI& t = Display::driver();
    const int W = Display::width();
    const int H = Display::height();
    const int y = H - NAV_H;

    t.fillRect(0, y, W, NAV_H, COL_CARD);
    t.drawFastHLine(0, y, W, COL_EDGE);

    const bool multi = (cfg.pageCount > 1);
    setFontS(t);
    t.setTextDatum(MC_DATUM);
    t.setTextColor(multi ? COL_TEXT : COL_EDGE, COL_CARD);
    t.drawString("<", 16, y + NAV_H / 2);
    t.drawString(">", W - 16, y + NAV_H / 2);

    /* Puntets (un per pantalla) o el numero, si n'hi ha moltes. */
    if (cfg.pageCount <= 12) {
        const int gap = 12;
        const int x0 = W / 2 - (cfg.pageCount - 1) * gap / 2;
        for (int i = 0; i < cfg.pageCount; ++i) {
            const bool cur = (i == gPage);
            t.fillSmoothCircle(x0 + i * gap, y + NAV_H / 2, cur ? 3 : 2,
                               cur ? COL_ACCENT : COL_EDGE);
        }
    } else {
        char pos[16];
        snprintf(pos, sizeof(pos), "%d/%d", gPage + 1, cfg.pageCount);
        t.setTextColor(COL_DIM, COL_CARD);
        t.drawString(pos, W / 2, y + NAV_H / 2);
    }
}

/* -1 = enrere, +1 = endavant, 0 = al mig (res), -2 = no s'hi ha tocat. */
int navBarHit(int16_t x, int16_t y)
{
    if (!gNavBar || gMenuOpen) {
        return -2;
    }
    const MacLink::Config& cfg = MacLink::config();
    if (cfg.pageCount <= 1) {
        return -2;
    }
    const int W = Display::width();
    const int H = Display::height();
    if (y < H - NAV_H) {
        return -2;
    }
    if (x < W / 4)     return -1;
    if (x > W * 3 / 4) return +1;
    return 0;
}

/* Canvia de pantalla amb salt circular. */
void gotoPage(int delta)
{
    const MacLink::Config& cfg = MacLink::config();
    if (cfg.pageCount <= 1) {
        return;
    }
    int p = gPage + delta;
    if (p < 0)              p = cfg.pageCount - 1;
    if (p >= cfg.pageCount) p = 0;
    Ui::setPage(p);
    Serial.printf("[UI] pantalla -> %d\n", p);
}

bool hitMenuButton(int16_t x, int16_t y)
{
    return (x >= 0 && x < MENU_BTN_W && y >= 0 && y < HEADER_H);
}

bool menuOpen()
{
    return gMenuOpen;
}

void setMenuOpen(bool open)
{
    if (open == gMenuOpen) {
        return;
    }
    gMenuOpen = open;
    /* Els 'ajustos' ara son una pestanya del menu: aquesta bandera nomes diu si
     * el menu esta obert ensenyant-la. */
    gSettingsOpen = open && (gMenuTab == TAB_AJUSTOS);
    if (open) {
        gMenuScroll = 0;
        gMenuDragY  = -1;
        gMenuMoved  = false;
        drawMenu();
    } else {
        layout();          /* repinta tot (esborra el menu) */
    }
}

/* --- Gestio dels tocs ------------------------------------------------------
 * Retorna true si la UI ja ha consumit el toc (menu, barra de navegacio o
 * lliscament). Si retorna false, el cridador pot mirar si hi ha un boto.
 */
/* Estat del boto que hi ha sota el dit ara mateix. */
int  gPressedBtn = -1;
bool gWasPressed = false;

bool touch(bool pressed, int16_t x, int16_t y)
{
    /* Nomes tractem l'aixecament si abans hi havia hagut un toc de veritat. */
    if (!pressed && !gTouchDown) {
        return false;
    }
    gTouchDown = pressed;

    /* --- 1) Menu obert: se'l menja tot ----------------------------------- */
    if (gMenuOpen) {
        /* Si s'acaba d'obrir amb aquest mateix toc, no el processem mes. */
        if (gMenuJustOpened) {
            if (!pressed) {
                gMenuJustOpened = false;
            }
            return true;
        }
        if (pressed) {
            if (gMenuDragY < 0) {              /* primer contacte */
                gMenuDragY = y;
                gMenuDragS = gMenuScroll;
                gMenuMoved = false;
            } else if (abs(y - gMenuDragY) > 12) {
                gMenuMoved = true;             /* s'esta lliscant la llista */
                int s = gMenuDragS - (y - gMenuDragY) / gMenuRowH;
                if (s < 0) s = 0;
                if (s > gMenuItems - gMenuRows) s = gMenuItems - gMenuRows;
                if (s != gMenuScroll) {
                    gMenuScroll = s;
                    drawMenu();
                }
            }
            return true;
        }

        const bool moved = gMenuMoved;
        gMenuDragY = -1;
        gMenuMoved = false;
        if (!moved) {                          /* era un toc, no un lliscament */
            int item = -1;
            int tab  = -1;
            const MenuZone z = menuZone(x, y, item, tab);
            if (z == MZ_TAB) {
                if (tab != gMenuTab) {
                    gMenuTab      = tab;
                    gMenuScroll   = 0;
                    gSettingsOpen = (tab == TAB_AJUSTOS);
                    drawMenu();
                }
            } else if (z == MZ_ITEM) {
                if (gMenuTab == TAB_PANTALLES) {
                    setMenuOpen(false);
                    if (item != gPage) {
                        Ui::setPage(item);
                        Serial.printf("[UI] pantalla -> %d\n", item);
                    }
                } else if (gMenuTab == TAB_AJUSTOS) {
                    /* Cada fila es un ajust: es canvia el seu valor. */
                    char id[28];
                    snprintf(id, sizeof(id), "cfg:%s", kSetupRows[item].id);
                    Ui::settingsAction(id);
                }
                /* A 'Sobre' no hi ha res a tocar: nomes es mira. */
            } else if (z == MZ_CLOSE) {
                setMenuOpen(false);
            } else if (z == MZ_UP) {
                if (gMenuScroll > 0) {
                    --gMenuScroll;
                    drawMenu();
                }
            } else if (z == MZ_DOWN) {
                if (gMenuScroll + gMenuRows < gMenuItems) {
                    ++gMenuScroll;
                    drawMenu();
                }
            }
        }
        return true;
    }

    /* --- 2) Boto de menu (☰) de la capcalera ----------------------------- */
    if (pressed) {
        if (hitMenuButton(x, y)) {
            if (!gMenuBtnLatched) {
                gMenuBtnLatched = true;
                if (gMenuOpen) {
                    setMenuOpen(false);       /* el ☰ tambe tanca el menu */
                } else {
                    setMenuOpen(true);
                    gMenuJustOpened = true;
                }
            }
            return true;
        }
    } else {
        gMenuBtnLatched = false;
    }

    /* --- 3) Barra de navegacio de baix ----------------------------------- */
    if (pressed) {
        if (navBarHit(x, y) != -2) {
            gNavLatched = true;
            return true;
        }
    } else if (gNavLatched) {
        gNavLatched = false;
        const int nav = navBarHit(x, y);
        if (nav == -1 || nav == +1) {
            gotoPage(nav);
        }
        return true;
    }

    /* --- 4) Lliscament horitzontal per canviar de pantalla --------------- *
     * Nomes MARQUEM que hi ha lliscament; no tornem aqui dalt. Si tornessim,
     * el codi dels botons (que es a sota) no s'executaria mai en el moment de
     * prémer, i cap boto no s'activaria. */
    if (gNavSwipe && !gMenuOpen) {
        if (pressed) {
            if (gSwipeX0 < 0) {
                gSwipeX0 = x;
                gSwipeY0 = y;
            } else if (!gSwipeActive &&
                       abs(x - gSwipeX0) > SWIPE_MIN &&
                       abs(y - gSwipeY0) < SWIPE_MAXY) {
                /* Ja es un lliscament: el boto que hi hagues queda cancel·lat. */
                gSwipeActive = true;
                cancelPress();
            }
        } else {
            const bool wasSwipe = gSwipeActive;
            const int  dx = (gSwipeX0 >= 0) ? (x - gSwipeX0) : 0;
            gSwipeActive = false;
            gSwipeX0 = -1;
            if (wasSwipe) {
                gotoPage((dx < 0) ? +1 : -1);
                return true;
            }
        }
    }

    /* --- 5) Botons de la pantalla ----------------------------------------- *
     * Aixo abans era a main.cpp, pero llavors el toc simulat ('toca x y') no
     * arribava mai als botons i no es podien provar. Ara el toc de debò i el
     * simulat passen exactament pel mateix cami. */
    if (pressed) {
        /* Si el dit s'esta movent (lliscament), cap boto: s'anul·la tot. */
        const int idx = gSwipeActive ? -1 : hitTest(x, y);
        if (idx != gPressedBtn) {
            if (gPressedBtn >= 0) {
                setPressed(gPressedBtn, false);
            }
            gPressedBtn = idx;
            if (gPressedBtn >= 0) {
                setPressed(gPressedBtn, true);
                const MacLink::Button* b = buttonAt(gPressedBtn);
                Serial.printf("[UI] tocant (%d,%d) -> boto '%s'\n",
                              x, y, b ? b->label : "?");
            }
        }
    } else {
        if (gWasPressed && gPressedBtn >= 0) {
            const MacLink::Button* b = buttonAt(gPressedBtn);
            if (b != nullptr) {
                if (settingsAction(b->id)) {
                    /* Accio local dels ajustos: ja s'ha fet. */
                } else if (b->keys[0] != '\0') {
                    Keys::send(b->keys);      /* tecles de debò per Bluetooth */
                    Serial.printf("[UI] boto -> tecles '%s'\n", b->keys);
                } else {
                    MacLink::sendCommand(b->id);
                    Serial.printf("[UI] boto -> %s\n", b->id);
                }
            }
            setPressed(gPressedBtn, false);
        }
        gPressedBtn = -1;
    }
    gWasPressed = pressed;
    return true;
}

void cancelPress()
{
    if (gPressedBtn >= 0) {
        setPressed(gPressedBtn, false);
    }
    gPressedBtn = -1;
    gWasPressed = true;
}

void setPressed(int index, bool down)
{
    if (index < 0 || index >= gBtnCount) {
        return;
    }
    gPressed = down ? index : -1;
    drawButton(index, down);
}

/* --- Baner de notificacio (les envia el Mac) ------------------------------ */
/* Es dibuixa com el baner del macOS: una targeta arrodonida a dalt de tot amb
 * el nom de l'aplicacio, el titol en negreta i una linia del cos. */
MacLink::Notice gBanner = {"", "", ""};
uint32_t gBannerUntil = 0;
bool     gBannerOn = false;

void drawBanner()
{
    TFT_eSPI& t = Display::driver();
    const int W = Display::width();
    const int m = 8;                                   /* marge exterior */
    const int hasBody = (gBanner.body[0] != '\0');
    const int h = hasBody ? 92 : 62;
    const int x = m + 16;
    const int maxW = W - 2 * m - 26;

    /* Sombra + targeta. */
    t.fillRoundRect(m + 2, m + 3, W - 2 * m, h, 12,
                    t.alphaBlend(70, TFT_BLACK, COL_BG));
    t.fillRoundRect(m, m, W - 2 * m, h, 12, COL_CARD);
    t.drawRoundRect(m, m, W - 2 * m, h, 12, COL_EDGE);

    /* Banda d'accent a l'esquerra, com el color de l'app al macOS. */
    t.fillRoundRect(m, m, 5, h, 3, COL_ACCENT);

    char buf[96];
    t.setTextDatum(TL_DATUM);

    /* Nom de l'aplicacio (a dalt, petit i en accent). */
    if (gBanner.app[0] != '\0') {
        setFontS(t);
        t.setTextColor(COL_ACCENT, COL_CARD);
        fitText(t, gBanner.app, buf, sizeof(buf), maxW);
        t.drawString(buf, x, m + 9);
    }

    /* Titol en negreta. */
    setFontM(t);
    t.setTextColor(COL_TEXT, COL_CARD);
    fitText(t, gBanner.title, buf, sizeof(buf), maxW);
    t.drawString(buf, x, m + (gBanner.app[0] != '\0' ? 30 : 14));

    /* Cos (una linia). */
    if (hasBody) {
        setFontS(t);
        t.setTextColor(COL_DIM, COL_CARD);
        fitText(t, gBanner.body, buf, sizeof(buf), maxW);
        t.drawString(buf, x, m + 58);
    }
}

void showBanner(const MacLink::Notice& n)
{
    gBanner = n;
    gBannerUntil = millis() + 8000;
    gBannerOn = true;
    gMarqOn = false;    /* el baner tapa la capcalera: prou marquesina */
    drawBanner();
    Serial.printf("[UI] avis de '%s': %s\n", gBanner.app, gBanner.title);
}

void showBanner(const char* text)
{
    if (text == nullptr || text[0] == '\0') {
        return;
    }
    MacLink::Notice n = {"", "", ""};
    strlcpy(n.title, text, sizeof(n.title));
    showBanner(n);
}

void updateBanner()
{
    if (gBannerOn && millis() > gBannerUntil) {
        gBannerOn = false;
        invalidate();
        refresh(MacLink::stats(), MacLink::linkUp());
    }
}

/* El baner tapa part de la pantalla: el primer toc nomes el treu. */
bool bannerOn()
{
    return gBannerOn;
}

void dismissBanner()
{
    if (!gBannerOn) {
        return;
    }
    gBannerOn = false;
    gBannerUntil = 0;
    invalidate();
    refresh(MacLink::stats(), MacLink::linkUp());
}

void onAppsChanged()
{
    if (pageIsLauncher()) {
        layout();
    }
}

void onTabsChanged()
{
    if (pageIsTabs()) {
        layout();
    }
}

void invalidate()
{
    gLastTime[0] = '\0';
    gLastHost[0] = '\0';
    gLastLink   = -1;
    gLastPage   = gPage;
    for (int i = 0; i < MAX_PAGE_WIDGETS; ++i) {
        gLastVal[i][0] = '\0';
        gLastPct[i]    = -999;
    }
}

/* --- Repos (standby) ------------------------------------------------------ */

void setScreenOn(bool on)
{
    if (on == gScreenOn) {
        return;
    }
    gScreenOn = on;
    if (on) {
        Display::setBacklight(gBrightPct);
        gLastTouchMs = millis();
        Serial.println("[UI] pantalla encesa");
        layout();                       /* repinta tot per si de cas */
    } else {
        Display::setBacklight(0);
        Serial.println("[UI] pantalla en repos");
    }
}

bool screenOn()
{
    return gScreenOn;
}

void setMacAwake(bool awake)
{
    if (awake == gMacAwake) {
        return;
    }
    gMacAwake = awake;
    Serial.printf("[UI] el Mac %s\n", awake ? "s'ha despertat" : "ha entrat en repos");

    /* Si el Mac s'ha despertat i la pantalla era apagada, l'encem. */
    if (awake && !gScreenOn) {
        setScreenOn(true);
    }
}

void setStandbyMs(uint32_t ms)
{
    gStandbyMs = ms;
}

uint32_t standbyMs()
{
    return gStandbyMs;
}

void touchActivity()
{
    gLastTouchMs = millis();
    if (!gScreenOn) {
        setScreenOn(true);
    }
}

void updateStandby()
{
    /* Amb el rellotge a la pantalla (el Mac inactiu o sense enllac) volem que
     * es vegi: si no ho fem aixi, en apagar-se la pantalla del Mac tambe
     * s'apagaria la nostra i el rellotge no es veuria mai. Tot i aixi, si
     * l'usuari ha configurat un repos per inactivitat, tambe mana. */
    if (gIdleMode || gNoLink) {
        if (gStandbyMs > 0 && (millis() - gLastTouchMs) > gStandbyMs) {
            if (gScreenOn) {
                setScreenOn(false);
            }
            return;
        }
        if (!gScreenOn) {
            setScreenOn(true);
        }
        return;
    }

    if (!gScreenOn) {
        return;
    }
    const uint32_t idle = millis() - gLastTouchMs;

    /* El Mac te la pantalla dormida -> nosaltres tambe. */
    if (!gMacAwake && idle > 3000) {
        setScreenOn(false);
        return;
    }
    /* Fa estona que no sabem res del Mac (ha dormit o s'ha apagat). */
    if (!MacLink::linkUp() && idle > LINK_SLEEP_MS) {
        setScreenOn(false);
        return;
    }
    /* Inactivitat del tactil. */
    if (gStandbyMs > 0 && idle > gStandbyMs) {
        setScreenOn(false);
    }
}

/* --- Ajustos (ara son una pestanya del menu) ------------------------------ */

bool settingsOpen()
{
    return gMenuOpen && (gMenuTab == TAB_AJUSTOS);
}

void openSettings()
{
    gMenuTab     = TAB_AJUSTOS;
    gMenuScroll  = 0;
    gSettingsOpen = true;
    gLastTouchMs = millis();
    Serial.println("[UI] menu -> Ajustos");
    if (!gMenuOpen) {
        gMenuJustOpened = false;
        setMenuOpen(true);
    } else {
        drawMenu();
    }
}

void closeSettings()
{
    setMenuOpen(false);
}

bool settingsAction(const char* id)
{
    if (id == nullptr || strncmp(id, "cfg:", 4) != 0) {
        return false;
    }
    const char* k = id + 4;
    gLastTouchMs = millis();

    /* Despres de canviar un ajust, es repinta: si som al menu, el menu; si no,
     * la pantalla de sota. */
    auto repinta = []() {
        if (gMenuOpen) {
            drawMenu();
        } else {
            layout();
        }
    };

    if (strcmp(k, "close") == 0) {
        closeSettings();
        return true;
    }

    if (strcmp(k, "bright") == 0 || strcmp(k, "bright-") == 0 ||
        strcmp(k, "bright+") == 0) {
        const int pas = (strcmp(k, "bright-") == 0) ? -10 : +10;
        int v = static_cast<int>(gBrightPct) + pas;
        if (v > 100) v = 10;            /* dona la volta */
        if (v < 10)  v = 100;
        gBrightPct = static_cast<uint8_t>(v);
        Display::setBacklight(gBrightPct);
        char val[8];
        snprintf(val, sizeof(val), "%d", v);
        MacLink::sendSet("bright", val);
        repinta();
        return true;
    }

    if (strcmp(k, "theme") == 0 || strcmp(k, "theme-") == 0 ||
        strcmp(k, "theme+") == 0) {
        /* Amb el tema automatic, aquesta fila canvia el tema de l'aparenca que
         * te el Mac ARA (si esta en fosc, el tema fosc). Aixi el canvi es veu a
         * l'instant i queda desat al lloc que toca. */
        const int n    = Th::count();
        const int slot = themePrefSlot();
        const int pas  = (strcmp(k, "theme-") == 0) ? -1 : +1;
        int v = static_cast<int>(themePrefGet(slot)) + pas;
        if (v < 0)  v = n - 1;
        if (v >= n) v = 0;
        themePrefSet(slot, static_cast<uint8_t>(v));
        themePrefPendent();                 /* el canvi va de cami al Mac */
        char val[8];
        snprintf(val, sizeof(val), "%d", v);
        MacLink::sendSet(themePrefKey(slot), val);
        Serial.printf("[UI] tema %s -> %u (%s)\n",
                      (slot == TP_DARK) ? "fosc" : (slot == TP_LIGHT) ? "clar"
                                                                      : "manual",
                      static_cast<unsigned>(v), Th::name(static_cast<uint8_t>(v)));
        repinta();
        return true;
    }

    if (strcmp(k, "themeauto") == 0) {
        gThemePref.autoMode = gThemePref.autoMode ? 0 : 1;
        themePrefPendent();                 /* el canvi va de cami al Mac */
        MacLink::sendSet("themeauto", gThemePref.autoMode ? "1" : "0");
        Serial.printf("[UI] tema automatic %s\n",
                      gThemePref.autoMode ? "activat" : "desactivat");
        repinta();
        return true;
    }

    if (strcmp(k, "orient") == 0) {
        const MacLink::Config& cfg = MacLink::config();
        const char* nou = (cfg.orientation[0] == 'h') ? "v" : "h";
        MacLink::sendSet("orient", nou);
        Serial.printf("[UI] orientacio -> %s\n",
                      (nou[0] == 'h') ? "horitzontal" : "vertical");
        return true;
    }

    if (strcmp(k, "standby") == 0) {
        int idx = 0;
        for (int i = 0; i < kStandbyCount; ++i) {
            if (kStandbyOpts[i] == gStandbyMs) {
                idx = i;
                break;
            }
        }
        idx = (idx + 1) % kStandbyCount;
        gStandbyMs = kStandbyOpts[idx];
        char val[12];
        snprintf(val, sizeof(val), "%u",
                 static_cast<unsigned>(gStandbyMs / 1000));
        MacLink::sendSet("standby", val);
        repinta();
        return true;
    }

    if (strcmp(k, "idle") == 0) {
        const MacLink::Config& cfg = MacLink::config();
        int idx = 0;
        for (int i = 0; i < kIdleCount; ++i) {
            if (kIdleOpts[i] == cfg.idleMin) {
                idx = i;
                break;
            }
        }
        idx = (idx + 1) % kIdleCount;
        char val[8];
        snprintf(val, sizeof(val), "%u", static_cast<unsigned>(kIdleOpts[idx]));
        MacLink::sendSet("idle", val);
        Serial.printf("[UI] rellotge si inactiu -> %u min\n",
                      static_cast<unsigned>(kIdleOpts[idx]));
        return true;
    }

    if (strcmp(k, "nav") == 0) {
        static const char* const kNv[] = {"both", "bar", "swipe", "off"};
        const char* cur = MacLink::config().nav;
        int idx = 0;
        for (int i = 0; i < 4; ++i) {
            if (strcmp(kNv[i], cur) == 0) {
                idx = i;
                break;
            }
        }
        idx = (idx + 1) % 4;
        MacLink::sendSet("nav", kNv[idx]);
        Serial.printf("[UI] navegacio -> %s\n", kNv[idx]);
        return true;
    }

    if (strcmp(k, "reset") == 0) {
        Serial.println("[UI] configuracio de fabrica");
        MacLink::resetConfig();       /* torna la per defecte i la desa */
        repinta();
        return true;
    }

    if (strcmp(k, "restart") == 0) {
        Serial.println("[UI] reiniciant la placa...");
        delay(120);
        ESP.restart();
        return true;
    }

    return false;
}

/* --- Pantalla d'inici (splash) -------------------------------------------- *
 * Surt mentre la placa s'engega: el fons HUD, un logo, el nom del producte i
 * una barra de carrega que va avançant a cada pas de la inicialitzacio.
 *
 * El dibuix viu aqui (i no a main.cpp) perque aixi pot fer servir les mateixes
 * eines que la resta de la interficie: el fons, les fonts i els colors del
 * tema. */
namespace {

constexpr uint32_t SPLASH_STEP_MS = 10;     /* animacio de cada 1% de barra */
constexpr uint32_t SPLASH_MIN_MS  = 1100;   /* estona minima a pantalla */

uint32_t gSplashBase  = 0;
int      gSplashPct   = -1;
char     gSplashPas[28] = "";               /* text del xip (per no repetir-lo) */
int      gSplashFillW = 0;                  /* pixels de barra ja pintats */

/* Geometria de la barra: la comparteixen el xip i la barra. */
int splashBarW(int W) { return (W * 66) / 100; }
int splashBarX(int W) { return (W - splashBarW(W)) / 2; }
int splashBarY(int H) { return H - 62; }

/* Text amb les lletres separades 'extra' pixels: queda mes de logo. Nomes s'hi
 * fan servir lletres ASCII, aixi que anar caràcter a caràcter es segur. */
void drawSpaced(TFT_eSPI& t, const char* s, int cx, int y, int extra)
{
    int w = 0;
    for (const char* p = s; *p != '\0'; ++p) {
        char ch[2] = {*p, '\0'};
        w += t.textWidth(ch) + extra;
    }
    if (w > 0) {
        w -= extra;
    }
    int x = cx - w / 2;
    t.setTextDatum(ML_DATUM);
    for (const char* p = s; *p != '\0'; ++p) {
        char ch[2] = {*p, '\0'};
        t.drawString(ch, x, y);
        x += t.textWidth(ch) + extra;
    }
}

/* Logo: una placa arrodonida (com les icones d'app) amb 'MP' a dins, envoltada
 * d'un anell d'HUD amb marques. Fa joc amb el fons de la resta de pantalles. */
void drawSplashLogo(int cx, int cy, int size)
{
    TFT_eSPI& t = Display::driver();
    const int half = size / 2;
    const int r    = size / 5;               /* cantonades ben rodones */
    const int rOut = half + 15;

    /* Anell exterior amb marques radials (com un visor). */
    t.drawCircle(cx, cy, rOut, t.alphaBlend(90, COL_ACCENT, COL_BG));
    t.drawCircle(cx, cy, rOut + 5, t.alphaBlend(45, COL_ACCENT, COL_BG));
    const uint16_t tick = t.alphaBlend(150, COL_ACCENT, COL_BG);
    for (int i = 0; i < 24; ++i) {
        const float a = static_cast<float>(i) * 15.0f * 0.01745329f;
        const int   l = (i % 6 == 0) ? 9 : 4;   /* mes llargues cada 90 graus */
        const int   x1 = cx + static_cast<int>(cosf(a) * (rOut + 2));
        const int   y1 = cy + static_cast<int>(sinf(a) * (rOut + 2));
        const int   x2 = cx + static_cast<int>(cosf(a) * (rOut + 2 + l));
        const int   y2 = cy + static_cast<int>(sinf(a) * (rOut + 2 + l));
        t.drawLine(x1, y1, x2, y2, tick);
    }

    /* Halo: uns quants marcs, cada cop mes fluixos. */
    for (int i = 7; i >= 1; --i) {
        const uint8_t a = static_cast<uint8_t>(9 * i);
        t.drawRoundRect(cx - half - i, cy - half - i, size + 2 * i, size + 2 * i,
                        r + i, t.alphaBlend(a, COL_ACCENT, COL_BG));
    }

    /* Placa. */
    t.fillRoundRect(cx - half, cy - half, size, size, r, COL_CARD);
    t.drawRoundRect(cx - half, cy - half, size, size, r, COL_ACCENT);
    t.drawRoundRect(cx - half + 2, cy - half + 2, size - 4, size - 4, r - 2,
                    t.alphaBlend(110, COL_ACCENT, COL_CARD));

    /* 'MP' a dins, amb una mica d'aire entre les lletres. */
    setFontB(t);
    t.setTextColor(COL_TEXT, COL_CARD);
    drawSpaced(t, "MP", cx, cy, 2);
}

/* Xip amb el nom del pas (nomes es repinta quan el text canvia). */
void drawSplashChip(int W, int H, const char* pas)
{
    if (strcmp(pas, gSplashPas) == 0) {
        return;
    }
    strlcpy(gSplashPas, pas, sizeof(gSplashPas));

    TFT_eSPI& t = Display::driver();
    const int chipH = 24;
    const int chipW = (W * 54) / 100;
    const int chipX = (W - chipW) / 2;
    const int chipY = splashBarY(H) - 34;

    /* El text va dins d'una pastilla opaca: aixi es repinta sencer i no queden
     * restes del text anterior sobre el degradat del fons. */
    t.fillRoundRect(chipX, chipY, chipW, chipH, chipH / 2, COL_CARD);
    t.drawRoundRect(chipX, chipY, chipW, chipH, chipH / 2, COL_EDGE);
    setFontS(t);
    t.setTextDatum(MC_DATUM);
    t.setTextColor(COL_DIM, COL_CARD);
    t.drawString(pas, W / 2, chipY + chipH / 2);
}

/* Barra de carrega. La pista es pinta un sol cop i, despres, nomes el tros nou:
 * pintar-la sencera 100 cops costaria molt mes del que sembla. */
void drawSplashBar(int W, int H, int pct)
{
    TFT_eSPI& t = Display::driver();
    const int bh = 14;
    const int bw = splashBarW(W);
    const int bx = splashBarX(W);
    const int by = splashBarY(H);

    if (gSplashFillW < 0) {                 /* primer cop: pista sencera */
        t.fillRoundRect(bx, by, bw, bh, bh / 2, COL_EDGE);
        gSplashFillW = 0;
    }

    const int fw = (bw * pct) / 100;
    if (fw <= gSplashFillW) {
        return;
    }
    if (gSplashFillW == 0) {
        t.fillSmoothCircle(bx + bh / 2, by + bh / 2, bh / 2 - 1, COL_ACCENT);
    }
    const int x0 = bx + gSplashFillW;
    const int x1 = bx + fw;
    if (x1 - x0 > 1) {
        t.fillRect(x0, by + 1, x1 - x0, bh - 2, COL_ACCENT);
    }
    t.fillSmoothCircle(x1 - 1, by + bh / 2, bh / 2 - 1, COL_ACCENT);
    gSplashFillW = fw;
}

}  // namespace

void splashBegin()
{
    TFT_eSPI& t = Display::driver();
    const int W = Display::width();
    const int H = Display::height();

    gSplashBase   = millis();
    gSplashPct    = 0;
    gSplashPas[0] = '\0';
    gSplashFillW  = -1;

    /* La pantalla d'inici tapa tota la pantalla: si hi havia el menu o els
     * ajustos oberts, els tanquem perque no quedin a mitges. */
    if (gMenuOpen) {
        setMenuOpen(false);
    }
    if (gMenuOpen) {
        setMenuOpen(false);            /* la pantalla d'inici ho tapa tot */
    }

    drawBackground();

    /* Logo, nom del producte i reclam. */
    const int cx   = W / 2;
    const int size = (H * 30 / 100 < 104) ? (H * 30 / 100) : 104;
    const int cy   = H * 36 / 100;
    drawSplashLogo(cx, cy, size);

    setFontL(t);
    t.setTextColor(COL_TEXT, COL_BG);
    drawSpaced(t, "MAC PANEL", cx, cy + size / 2 + 36, 3);

    setFontS(t);
    t.setTextDatum(MC_DATUM);
    t.setTextColor(COL_DIM, COL_BG);
    t.drawString("pantalla d'estat del Mac", cx, cy + size / 2 + 62);

    drawSplashChip(W, H, "engegant");
    drawSplashBar(W, H, 0);
    Serial.println(F("[UI] pantalla d'inici"));
}

void splashStep(int pct, const char* pas)
{
    if (gSplashPct < 0) {
        splashBegin();              /* encara no s'havia dibuixat res */
    }
    if (pct < 0) {
        pct = 0;
    }
    if (pct > 100) {
        pct = 100;
    }
    const int W = Display::width();
    const int H = Display::height();

    drawSplashChip(W, H, pas);
    /* Anima la barra del valor actual al nou: aixi no fa salts. */
    while (gSplashPct < pct) {
        ++gSplashPct;
        drawSplashBar(W, H, gSplashPct);
        delay(SPLASH_STEP_MS);
    }
    Serial.printf("[UI] engegant: %d%% %s\n", pct, pas);
}

void splashEnd()
{
    if (gSplashPct < 100) {
        splashStep(100, "a punt");
    }
    /* Que s'hi estigui una estona: si no, amb el poc que triga l'ESP32 a
     * inicialitzar-se no la veuries. */
    const uint32_t passat = millis() - gSplashBase;
    if (passat < SPLASH_MIN_MS) {
        delay(SPLASH_MIN_MS - passat);
    }
}

}  // namespace Ui
