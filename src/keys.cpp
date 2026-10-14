#include "keys.h"

#include <Arduino.h>
#include <BleKeyboard.h>

#include <string.h>

#include "panel_config.h"

namespace {

BleKeyboard gKb("Mac Panel", "Mac Panel", 100);
bool gStarted = false;

/* La llibreria nomes defineix les tecles especials i els mitjans, aixi que
 * aqui hi teniem els codis HID de la resta. Ja NO calen: per a les tecles
 * normals s'hi passen caracters ASCII i la llibreria els converteix. */

/* La llibreria BleKeyboard espera CARACTERS ASCII per a les tecles normals
 * (ella ja sap quin modificador cal: '+' = shift+equal) i els valors KEY_* per
 * a les especials. NO s'hi poden passar codis HID directament: amb 'write(0x24)'
 * la llibreria ho interpreta com el caracter ASCII '$' i escriu un '$'.
 *
 * Els modificadors si que son els mateixos valors (0x80 = Ctrl, 0x81 = Shift,
 * 0x82 = Alt, 0x83 = Cmd). */
constexpr uint8_t MOD_CTRL  = 0x80;
constexpr uint8_t MOD_SHIFT = 0x81;
constexpr uint8_t MOD_ALT   = 0x82;
constexpr uint8_t MOD_GUI   = 0x83;

/* --- Bloc numeric (teclat numeric) ---------------------------------------- *
 * Els codis HID normals son POSICIONS FISIQUES del teclat, no caracters: la
 * tecla que en un teclat dels EUA es el '-' (0x2D) en un Mac amb distribucio
 * "Spanish - ISO" escriu un apostrof, i la que es el '+' escriu un '¡'.
 *
 * El BLOC NUMERIC no te aquest problema: son un grup de tecles a part i el
 * sistema els tradueix sempre als mateixos caracters (digits i operadors),
 * sigui quina sigui la distribucio. Per aixo el teclat numeric de la pantalla
 * fa servir aquests codis.
 *
 * A la llibreria, un valor >= 136 vol dir "tecla no imprimible": el codi HID
 * real es valor - 136. */
constexpr uint8_t KP_SLASH   = static_cast<uint8_t>(136 + 0x54);   /* / */
constexpr uint8_t KP_STAR    = static_cast<uint8_t>(136 + 0x55);   /* * */
constexpr uint8_t KP_MINUS   = static_cast<uint8_t>(136 + 0x56);   /* - */
constexpr uint8_t KP_PLUS    = static_cast<uint8_t>(136 + 0x57);   /* + */
constexpr uint8_t KP_ENTER   = static_cast<uint8_t>(136 + 0x58);
constexpr uint8_t KP_1       = static_cast<uint8_t>(136 + 0x59);
constexpr uint8_t KP_2       = static_cast<uint8_t>(136 + 0x5A);
constexpr uint8_t KP_3       = static_cast<uint8_t>(136 + 0x5B);
constexpr uint8_t KP_4       = static_cast<uint8_t>(136 + 0x5C);
constexpr uint8_t KP_5       = static_cast<uint8_t>(136 + 0x5D);
constexpr uint8_t KP_6       = static_cast<uint8_t>(136 + 0x5E);
constexpr uint8_t KP_7       = static_cast<uint8_t>(136 + 0x5F);
constexpr uint8_t KP_8       = static_cast<uint8_t>(136 + 0x60);
constexpr uint8_t KP_9       = static_cast<uint8_t>(136 + 0x61);
constexpr uint8_t KP_0       = static_cast<uint8_t>(136 + 0x62);
constexpr uint8_t KP_DOT     = static_cast<uint8_t>(136 + 0x63);   /* . */
constexpr uint8_t KP_EQUAL   = static_cast<uint8_t>(136 + 0x67);   /* = */

/* Compara sense distingir majuscules. */
bool eq(const char* a, const char* b)
{
    return strcasecmp(a, b) == 0;
}

struct SpecialKey {
    const char*           name;
    bool                  media;    /* true = tecla de mitjans (Consumer) */
    uint8_t               code;     /* caracter ASCII o valor KEY_* */
    const MediaKeyReport* report;   /* si media */
};

const SpecialKey kSpecial[] = {
    {"space",     false, ' ',            nullptr},
    {"espai",     false, ' ',            nullptr},
    {"enter",     false, KEY_RETURN,     nullptr},
    {"return",    false, KEY_RETURN,     nullptr},
    {"intro",     false, KEY_RETURN,     nullptr},
    {"tab",       false, KEY_TAB,        nullptr},
    {"esc",       false, KEY_ESC,        nullptr},
    {"escape",    false, KEY_ESC,        nullptr},
    {"backspace", false, KEY_BACKSPACE,  nullptr},
    {"esborrar",  false, KEY_BACKSPACE,  nullptr},
    {"delete",    false, KEY_DELETE,     nullptr},
    {"supr",      false, KEY_DELETE,     nullptr},
    {"up",        false, KEY_UP_ARROW,   nullptr},
    {"dalt",      false, KEY_UP_ARROW,   nullptr},
    {"down",      false, KEY_DOWN_ARROW, nullptr},
    {"baix",      false, KEY_DOWN_ARROW, nullptr},
    {"left",      false, KEY_LEFT_ARROW, nullptr},
    {"esquerra",  false, KEY_LEFT_ARROW, nullptr},
    {"right",     false, KEY_RIGHT_ARROW, nullptr},
    {"dreta",     false, KEY_RIGHT_ARROW, nullptr},
    {"home",      false, KEY_HOME,       nullptr},
    {"end",       false, KEY_END,        nullptr},
    {"pageup",    false, KEY_PAGE_UP,    nullptr},
    {"pagedown",  false, KEY_PAGE_DOWN,  nullptr},
    {"minus",     false, '-',            nullptr},
    {"equal",     false, '=',            nullptr},
    {"comma",     false, ',',            nullptr},
    {"period",    false, '.',            nullptr},
    {"slash",     false, '/',            nullptr},
    {"semicolon", false, ';',            nullptr},
    {"quote",     false, '\'',           nullptr},
    {"f1",  false, KEY_F1,  nullptr}, {"f2",  false, KEY_F2,  nullptr},
    {"f3",  false, KEY_F3,  nullptr}, {"f4",  false, KEY_F4,  nullptr},
    {"f5",  false, KEY_F5,  nullptr}, {"f6",  false, KEY_F6,  nullptr},
    {"f7",  false, KEY_F7,  nullptr}, {"f8",  false, KEY_F8,  nullptr},
    {"f9",  false, KEY_F9,  nullptr}, {"f10", false, KEY_F10, nullptr},
    {"f11", false, KEY_F11, nullptr}, {"f12", false, KEY_F12, nullptr},

    /* Bloc numeric: el mateix caracter a qualsevol distribucio de teclat. */
    {"kp_0", false, KP_0, nullptr}, {"kp_1", false, KP_1, nullptr},
    {"kp_2", false, KP_2, nullptr}, {"kp_3", false, KP_3, nullptr},
    {"kp_4", false, KP_4, nullptr}, {"kp_5", false, KP_5, nullptr},
    {"kp_6", false, KP_6, nullptr}, {"kp_7", false, KP_7, nullptr},
    {"kp_8", false, KP_8, nullptr}, {"kp_9", false, KP_9, nullptr},
    {"kp_dot",   false, KP_DOT,   nullptr},
    {"kp_slash", false, KP_SLASH, nullptr},
    {"kp_star",  false, KP_STAR,  nullptr},
    {"kp_minus", false, KP_MINUS, nullptr},
    {"kp_plus",  false, KP_PLUS,  nullptr},
    {"kp_enter", false, KP_ENTER, nullptr},
    {"kp_equal", false, KP_EQUAL, nullptr},

    /* Tecles de mitjans: son les que fan sortir el requadre del volum. */
    {"media_volumeup",   true, 0, &KEY_MEDIA_VOLUME_UP},
    {"media_volumedown", true, 0, &KEY_MEDIA_VOLUME_DOWN},
    {"media_mute",       true, 0, &KEY_MEDIA_MUTE},
    {"media_playpause",  true, 0, &KEY_MEDIA_PLAY_PAUSE},
    {"media_next",       true, 0, &KEY_MEDIA_NEXT_TRACK},
    {"media_prev",       true, 0, &KEY_MEDIA_PREVIOUS_TRACK},
    {"media_stop",       true, 0, &KEY_MEDIA_STOP},
};

/* Busca una tecla especial pel nom. */
const SpecialKey* findSpecial(const char* name)
{
    for (const SpecialKey& k : kSpecial) {
        if (eq(name, k.name)) {
            return &k;
        }
    }
    return nullptr;
}

}  // namespace

namespace Keys {

void begin()
{
    if (gStarted) {
        return;
    }
    gKb.begin();
    gStarted = true;
    Serial.println(F("[BT] teclat Bluetooth 'Mac Panel' en marxa"));
    Serial.println(F("[BT] emparella'l un cop a: Preferencies del Sistema > Bluetooth"));
}

bool started()   { return gStarted; }
bool connected() { return gStarted && gKb.isConnected(); }

/* Escriu pel port serie tots els noms de tecles que entenem. */
void printList()
{
    Serial.println(F("[BT] noms de tecles disponibles:"));
    Serial.print(F("[BT]   "));
    int n = 0;
    for (const SpecialKey& k : kSpecial) {
        Serial.printf("%s  ", k.name);
        if (++n % 7 == 0) {
            Serial.print(F("\n[BT]   "));
        }
    }
    Serial.println();
    Serial.println(F("[BT] tambe: qualsevol caracter sol ('a', '7', '+') i"));
    Serial.println(F("[BT] combinacions amb modificadors: cmd+c, shift+cmd+z..."));
}

void send(const char* spec)
{
    if (!gStarted || spec == nullptr || spec[0] == '\0') {
        return;
    }
    if (!gKb.isConnected()) {
        Serial.println(F("[BT] teclat no connectat: emparella 'Mac Panel' al Mac"));
        return;
    }

    char buf[40];
    strlcpy(buf, spec, sizeof(buf));

    uint8_t mods[4];
    int modCount = 0;
    char* last = nullptr;

    /* Un especificador d'UN SOL caracter (com "*", "+" o "-") no pot passar pel
     * separador '+': strtok_r el faria desaparèixer, perquè tota la cadena
     * serien delimitadors i retornaria NULL (i no s'enviava res). */
    if (buf[1] == '\0') {
        last = buf;
    } else {
        char* save = nullptr;
        for (char* tok = strtok_r(buf, "+", &save); tok != nullptr;
             tok = strtok_r(nullptr, "+", &save)) {
            if      (eq(tok, "cmd") || eq(tok, "gui") || eq(tok, "command")) mods[modCount++] = MOD_GUI;
            else if (eq(tok, "shift") || eq(tok, "maj"))                     mods[modCount++] = MOD_SHIFT;
            else if (eq(tok, "alt") || eq(tok, "option") || eq(tok, "opt"))  mods[modCount++] = MOD_ALT;
            else if (eq(tok, "ctrl") || eq(tok, "control"))                  mods[modCount++] = MOD_CTRL;
            else last = tok;
            if (modCount > 3) modCount = 3;
        }
    }
    if (last == nullptr) {
        return;
    }

    const SpecialKey* sp = findSpecial(last);

    /* Si no es una tecla especial, ha de ser un sol caracter imprimible: la
     * llibreria ja sap quin modificador necessita ('+', '*', '?', majuscules...). */
    if (sp == nullptr && (last[0] < 32 || last[0] > 126 || last[1] != '\0')) {
        Serial.printf("[BT] tecla desconeguda: %s\n", last);
        return;
    }
    const uint8_t code = (sp != nullptr) ? sp->code
                                         : static_cast<uint8_t>(last[0]);

    if (sp != nullptr && sp->media) {
        /* Les tecles de mitjans no porten modificadors. */
        gKb.write(*sp->report);
    } else {
        for (int i = 0; i < modCount; ++i) {
            gKb.press(mods[i]);
        }
        gKb.write(code);
        for (int i = modCount - 1; i >= 0; --i) {
            gKb.release(mods[i]);
        }
    }

    /* Registre util per diagnosticar: digues exactament que s'ha enviat. */
    if (sp != nullptr) {
        Serial.printf("[BT] '%s' -> tecla HID 0x%02X (%s)%s\n", spec,
                      static_cast<unsigned>(code - 136), sp->name,
                      modCount > 0 ? " amb modificadors" : "");
    } else {
        Serial.printf("[BT] '%s' -> caracter '%c'%s\n", spec, last[0],
                      modCount > 0 ? " amb modificadors" : "");
    }
}

}  // namespace Keys
