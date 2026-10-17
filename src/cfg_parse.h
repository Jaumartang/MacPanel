#pragma once

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "panel_config.h"

/*
 * cfg_parse.h - Parser del JSON de configuracio, escrit a ma.
 *
 * PER QUE NO ARDUINOJSON
 * ----------------------
 * La configuracio de la pantalla pot fer uns quants kilobytes i ArduinoJson
 * necessita memoria (del heap) per anar-la llegint. El problema es que la pila
 * de Bluetooth de l'ESP32 ocupa mes de 100 KB i, quan ja esta encesa, al heap
 * hi queden uns 20 KB molt fragmentats: la lectura fallava amb 'NoMemory' tot i
 * que el JSON nomes fa 3 KB.
 *
 * Aquest parser no demana NI UN BYTE de memoria: va omplint la configuracio
 * directament. Aixi la configuracio s'aplica SEMPRE, passi el que passi amb la
 * memoria, i podem encendre el Bluetooth quan vulguem.
 *
 * El format el genera el Mac (mac/bridge.py) i sempre es el mateix:
 *
 *   {"o":"v","t":0,"s":120,
 *    "p":[{"n":"Estat","i":"grid","l":"status",
 *          "w":["cpu","mem"],
 *          "b":[["media_play","PLAY","play","media_playpause"]]}]}
 *
 * Les claus desconegudes es salten soles: es pot ampliar el format sense
 * trencar res.
 */

/* Omple 'cfg' a partir del JSON. Retorna true si s'ha llegit be. */
inline bool parseConfigJson(const char* json, MacLink::Config& cfg)
{
    class Parser {
    public:
        Parser(const char* s, MacLink::Config& c) : p_(s), cfg_(c), ok_(true) {}

        bool ok() const { return ok_; }

        void parse()
        {
            cfg_.pageCount = 0;
            cfg_.orientation[0] = 'v';
            cfg_.orientation[1] = '\0';
            cfg_.theme = 0;
            cfg_.themeAuto = 0;
            cfg_.themeDark = 0;      /* Fosc */
            cfg_.themeLight = 1;     /* Clar */
            cfg_.standbyS = 120;
            cfg_.idleMin = IDLE_CLOCK_DEFAULT_MIN;
            strlcpy(cfg_.nav, "both", sizeof(cfg_.nav));

            skipWs();
            if (!accept('{')) { ok_ = false; return; }
            parseRoot();
        }

    private:
        /* --- eines basiques ---------------------------------------------- */
        void skipWs()
        {
            while (*p_ == ' ' || *p_ == '\n' || *p_ == '\r' || *p_ == '\t') {
                ++p_;
            }
        }

        bool accept(char c)
        {
            skipWs();
            if (*p_ == c) {
                ++p_;
                return true;
            }
            return false;
        }

        /* Llegeix una cadena ("...") cap a 'out' (la trunca si no hi cap, pero
         * sempre consumeix la cadena sencera del JSON). */
        bool readString(char* out, size_t outSize)
        {
            skipWs();
            if (*p_ != '"') {
                ok_ = false;
                return false;
            }
            ++p_;
            size_t n = 0;
            while (*p_ != '\0' && *p_ != '"') {
                char c = *p_++;
                if (c == '\\') {
                    const char e = *p_;
                    if (e == '\0') {
                        break;
                    }
                    ++p_;
                    switch (e) {
                        case 'n': c = '\n'; break;
                        case 't': c = '\t'; break;
                        case 'r': c = '\r'; break;
                        case 'b': c = '\b'; break;
                        case 'f': c = '\f'; break;
                        case 'u': {
                            /* \uXXXX: nomes ens cal l'ASCII basic. */
                            unsigned code = 0;
                            for (int i = 0; i < 4; ++i) {
                                const char h = *p_;
                                if (h >= '0' && h <= '9')      code = code * 16 + (h - '0');
                                else if (h >= 'a' && h <= 'f') code = code * 16 + (h - 'a' + 10);
                                else if (h >= 'A' && h <= 'F') code = code * 16 + (h - 'A' + 10);
                                else break;
                                ++p_;
                            }
                            c = (code < 0x80) ? static_cast<char>(code) : '?';
                            break;
                        }
                        default: c = e; break;      /* \" \\ \/ */
                    }
                }
                if (outSize > 0 && n + 1 < outSize) {
                    out[n++] = c;
                }
            }
            if (*p_ == '"') {
                ++p_;
            }
            if (outSize > 0) {
                out[n] = '\0';
            }
            return true;
        }

        int readInt()
        {
            skipWs();
            bool neg = false;
            if (*p_ == '-') {
                neg = true;
                ++p_;
            }
            long v = 0;
            while (*p_ >= '0' && *p_ <= '9') {
                v = v * 10 + (*p_ - '0');
                ++p_;
            }
            if (*p_ == '.') {                     /* decimals: els saltem */
                ++p_;
                while (*p_ >= '0' && *p_ <= '9') {
                    ++p_;
                }
            }
            return static_cast<int>(neg ? -v : v);
        }

        /* Salta un valor que no ens interessa (clau desconeguda). */
        bool skipValue()
        {
            skipWs();
            if (*p_ == '"') {
                char dummy[2];
                return readString(dummy, sizeof(dummy));
            }
            if (*p_ == '{' || *p_ == '[') {
                int depth = 0;
                while (*p_ != '\0') {
                    if (*p_ == '"') {
                        char dummy[2];
                        if (!readString(dummy, sizeof(dummy))) {
                            return false;
                        }
                        continue;
                    }
                    if (*p_ == '{' || *p_ == '[') {
                        ++depth;
                    } else if (*p_ == '}' || *p_ == ']') {
                        --depth;
                        if (depth <= 0) {
                            ++p_;
                            return true;
                        }
                    }
                    ++p_;
                }
                ok_ = false;
                return false;
            }
            while (*p_ != '\0' && *p_ != ',' && *p_ != '}' && *p_ != ']') {
                ++p_;
            }
            return true;
        }

        /* --- estructura --------------------------------------------------- */
        void parseRoot()
        {
            for (;;) {
                skipWs();
                if (accept('}')) {
                    return;
                }
                char key[8];
                if (!readString(key, sizeof(key)) || !accept(':')) {
                    ok_ = false;
                    return;
                }
                if (strcmp(key, "o") == 0) {
                    char v[4];
                    if (!readString(v, sizeof(v))) return;
                    cfg_.orientation[0] = (v[0] == 'h' || v[0] == 'H') ? 'h' : 'v';
                } else if (strcmp(key, "t") == 0) {
                    cfg_.theme = static_cast<uint8_t>(readInt());
                } else if (strcmp(key, "ta") == 0) {
                    cfg_.themeAuto = static_cast<uint8_t>(readInt() != 0);
                } else if (strcmp(key, "td") == 0) {
                    cfg_.themeDark = static_cast<uint8_t>(readInt());
                } else if (strcmp(key, "tl") == 0) {
                    cfg_.themeLight = static_cast<uint8_t>(readInt());
                } else if (strcmp(key, "s") == 0) {
                    cfg_.standbyS = static_cast<uint16_t>(readInt());
                } else if (strcmp(key, "ic") == 0) {
                    cfg_.idleMin = static_cast<uint16_t>(readInt());
                } else if (strcmp(key, "nv") == 0) {
                    if (!readString(cfg_.nav, sizeof(cfg_.nav))) return;
                } else if (strcmp(key, "p") == 0) {
                    if (!parsePages()) return;
                } else if (!skipValue()) {
                    return;
                }
                if (accept(',')) continue;
                if (accept('}')) return;
                ok_ = false;
                return;
            }
        }

        bool parsePages()
        {
            if (!accept('[')) { ok_ = false; return false; }
            for (;;) {
                skipWs();
                if (accept(']')) return true;
                if (cfg_.pageCount >= MAX_PAGES) {
                    if (!skipValue()) return false;      /* ja no n'hi caben */
                } else if (!parsePage()) {
                    return false;
                }
                if (accept(',')) continue;
                if (accept(']')) return true;
                ok_ = false;
                return false;
            }
        }

        bool parsePage()
        {
            MacLink::Page& p = cfg_.pages[cfg_.pageCount];
            strlcpy(p.name, "?", sizeof(p.name));
            p.icon[0] = '\0';
            strlcpy(p.layout, "buttons", sizeof(p.layout));
            p.appCount = 0;
            p.widgetCount = 0;
            p.buttonCount = 0;

            if (!accept('{')) { ok_ = false; return false; }
            for (;;) {
                skipWs();
                if (accept('}')) break;
                char key[8];
                if (!readString(key, sizeof(key)) || !accept(':')) {
                    ok_ = false;
                    return false;
                }
                if (strcmp(key, "n") == 0) {
                    if (!readString(p.name, sizeof(p.name))) return false;
                } else if (strcmp(key, "i") == 0) {
                    if (!readString(p.icon, sizeof(p.icon))) return false;
                } else if (strcmp(key, "l") == 0) {
                    if (!readString(p.layout, sizeof(p.layout))) return false;
                } else if (strcmp(key, "ap") == 0) {
                    if (!parseApps(p)) return false;
                } else if (strcmp(key, "w") == 0) {
                    if (!parseWidgets(p)) return false;
                } else if (strcmp(key, "b") == 0) {
                    if (!parseButtons(p)) return false;
                } else if (!skipValue()) {
                    return false;
                }
                if (accept(',')) continue;
                if (accept('}')) break;
                ok_ = false;
                return false;
            }
            ++cfg_.pageCount;
            return true;
        }

        /* Llista d'apps que obren aquesta pantalla: "ap":["com.apple.Safari",...] */
        bool parseApps(MacLink::Page& p)
        {
            if (!accept('[')) { ok_ = false; return false; }
            for (;;) {
                skipWs();
                if (accept(']')) return true;
                if (p.appCount < MAX_PAGE_APPS) {
                    if (!readString(p.apps[p.appCount], APP_ID_MAX)) return false;
                    ++p.appCount;
                } else if (!skipValue()) {
                    return false;
                }
                if (accept(',')) continue;
                if (accept(']')) return true;
                ok_ = false;
                return false;
            }
        }

        bool parseWidgets(MacLink::Page& p)
        {
            if (!accept('[')) { ok_ = false; return false; }
            for (;;) {
                skipWs();
                if (accept(']')) return true;
                char w[12];
                if (!readString(w, sizeof(w))) return false;
                if (p.widgetCount < MAX_PAGE_WIDGETS) {
                    strlcpy(p.widgets[p.widgetCount], w, sizeof(p.widgets[0]));
                    ++p.widgetCount;
                }
                if (accept(',')) continue;
                if (accept(']')) return true;
                ok_ = false;
                return false;
            }
        }

        bool parseButtons(MacLink::Page& p)
        {
            if (!accept('[')) { ok_ = false; return false; }
            for (;;) {
                skipWs();
                if (accept(']')) return true;
                MacLink::Button b;
                b.id[0] = '\0';
                b.label[0] = '\0';
                b.icon[0] = '\0';
                b.keys[0] = '\0';
                b.col = -1;                  /* posicio automatica */
                b.row = -1;
                b.w = 1;
                b.h = 1;
                if (!parseButton(b)) return false;
                if (p.buttonCount < MAX_PAGE_BUTTONS) {
                    p.buttons[p.buttonCount] = b;
                    ++p.buttonCount;
                }
                if (accept(',')) continue;
                if (accept(']')) return true;
                ok_ = false;
                return false;
            }
        }

        /* Un boto es ["id","text","icona","tecles"] (poden faltar camps) i,
         * opcionalment, un cinque camp amb la posicio fixa: "col,row,w,h".
         * Els botons de sempre no el porten i es reparteixen sols. */
        bool parseButton(MacLink::Button& b)
        {
            if (!accept('[')) { ok_ = false; return false; }
            char*  dest[4]  = { b.id, b.label, b.icon, b.keys };
            size_t sizes[4] = { sizeof(b.id), sizeof(b.label),
                                sizeof(b.icon), sizeof(b.keys) };
            for (int i = 0; i < 4; ++i) {
                skipWs();
                if (accept(']')) return true;
                if (!readString(dest[i], sizes[i])) return false;
                if (accept(',')) continue;
                if (accept(']')) return true;
                ok_ = false;
                return false;
            }
            skipWs();
            if (accept(']')) {
                return true;
            }
            char pos[16];
            if (!readString(pos, sizeof(pos))) return false;
            int c = -1, r = -1, w = 1, h = 1;
            if (sscanf(pos, "%d,%d,%d,%d", &c, &r, &w, &h) >= 2) {
                b.col = static_cast<int8_t>((c < 0 || c > 7) ? -1 : c);
                b.row = static_cast<int8_t>((r < 0 || r > 15) ? -1 : r);
                b.w   = static_cast<int8_t>((w < 1 || w > 8) ? 1 : w);
                b.h   = static_cast<int8_t>((h < 1 || h > 8) ? 1 : h);
                if (b.col < 0 || b.row < 0) {
                    b.col = -1;              /* si falta un dels dos, automatic */
                    b.row = -1;
                }
            }
            skipWs();
            if (!accept(']')) {
                ok_ = false;
                return false;
            }
            return true;
        }

        const char*      p_;
        MacLink::Config& cfg_;
        bool             ok_;
    };

    Parser parser(json, cfg);
    parser.parse();
    return parser.ok();
}
