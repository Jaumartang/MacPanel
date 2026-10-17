"""Model de dades del Mac Panel: cataleg, validacio, migracions i portabilitat.

Aquest modul es l'UNIC lloc on es decideix que es una configuracio valida. Ho
fan servir:

  * el servidor del panell, abans de desar o d'enviar res a la placa;
  * l'editor visual (les mateixes regles al navegador i al Python);
  * les eines de consola i les proves.

Per que existeixi
-----------------
La configuracio va neixer com un JSON implicit: les pantalles tenien `widgets`
(llista de cadenes) i `buttons` (llista d'objectes) i la resta es deduia. Amb un
editor visual a sobre aixo no n'hi ha prou: cal saber QUIN element es cada cosa,
si es visible, on va i com es diu, sense dependre de l'ordre de les llistes.

Com es fa, doncs, sense trencar res
-----------------------------------
La placa i el pont continuen llegint el mateix format de sempre (`widgets` i
`buttons`): es el que viatja pel port serie i no es pot canviar a la lleugera.
El que fem aqui es AFEGIR camps opcionals i una versio, i tenir una funcio que
converteixi entre el model d'editor i el format de la placa:

    configuracio (JSON)  <--elements_de()/desa_elements()-->  elements tipats

Aixi una configuracio vella (sense `version`) continua funcionant i es migra
sola en carregar-la.
"""

import copy
import json
import os

# Versio del format. 1 = el format implicit original (sense camp `version`);
# 2 = amb versio, disposicio de la graella i estat per element.
SCHEMA_VERSION = 2

# --- Cataleg de gadgets ---------------------------------------------------
# `tipus` es el que fa servir el model d'editor; `id` es el nom que enten la
# placa (i que viatja a `widgets`).
GADGETS = {
    "cpu":    {"nom": "CPU",        "unitat": "%",  "color": "cpu"},
    "mem":    {"nom": "RAM",        "unitat": "%",  "color": "mem"},
    "disk":   {"nom": "Disc",       "unitat": "%",  "color": "disk"},
    "bat":    {"nom": "Bateria",    "unitat": "%",  "color": "bat"},
    "net":    {"nom": "Xarxa",      "unitat": "",   "color": "net"},
    "load":   {"nom": "Carrega",    "unitat": "",   "color": "load"},
    "uptime": {"nom": "Temps encès", "unitat": "",  "color": "up"},
    "time":   {"nom": "Hora",       "unitat": "",   "color": "time"},
    "host":   {"nom": "Nom del Mac", "unitat": "",  "color": "host"},
}

# --- Cataleg d'accions de boto --------------------------------------------
# L'accio es guarda com una cadena amb prefix, igual que fa la placa:
#   app:<bundle>   obre o porta al davant una aplicacio del Mac
#   fav:<n>        obre un favorit del navegador
#   tecla:<nom>    envia una tecla pel teclat Bluetooth
#   focus:<n>      porta al davant l'app oberta numero n
#   custom:<n>     executa una ordre externa (cal activar-la a posta)
#   media_play ... accions del sistema (so, escriptori, etc.)
ACCIONS = {
    "app":   {"nom": "Aplicacio",        "descripcio": "Obre o porta al davant una aplicacio del Mac"},
    "fav":   {"nom": "Favorit",          "descripcio": "Obre un favorit dels navegadors"},
    "tecla": {"nom": "Tecles",           "descripcio": "Envia una combinacio de tecles pel Bluetooth"},
    "focus": {"nom": "App oberta",       "descripcio": "Porta al davant una app de les que estan obertes"},
    "custom": {"nom": "Ordre externa",   "descripcio": "Executa una ordre del Mac (opcional, s'ha d'activar)"},
    "media": {"nom": "Multimedia",       "descripcio": "Play, pausa, volum, escriptori..."},
}

# Accions del sistema que no necessiten cap argument.
ACCIONS_SISTEMA = (
    "media_play", "media_playpause", "media_next", "media_prev", "media_mute",
    "vol_up", "vol_down", "screen_lock", "mission_control", "spotlight",
    "desktop", "launchpad", "screenshot",
)

# --- Disposicions de pantalla ---------------------------------------------
DISPOSICIONS = {
    "status":   {"nom": "Gadgets + botons", "gadgets": True},
    "buttons":  {"nom": "Nomes botons",     "gadgets": False},
    "gauges":   {"nom": "Gauges circulars", "gadgets": False},
    "graph":    {"nom": "Grafics (historial)", "gadgets": False},
    "clock":    {"nom": "Rellotge + meteo", "gadgets": False},
    "numpad":   {"nom": "Teclat numeric",   "gadgets": False},
    "launcher": {"nom": "Apps obertes",     "gadgets": False},
    "tabs":     {"nom": "Pestanyes del navegador", "gadgets": False},
    "favs":     {"nom": "Favorits",         "gadgets": False},
}

# --- Limits del dispositiu (verificats al firmware) -----------------------
# ST7796S 320x480, gira a 480x320 en horitzontal (include/tft_setup.h).
PANTALLA = {"v": (320, 480), "h": (480, 320)}
MAX_PANTALLES = 12          # MAX_PAGES a include/panel_config.h
MAX_GADGETS = 9             # MAX_PAGE_WIDGETS
MAX_BOTONS = 15             # limit de `buttons` a config_payload()
MAX_NOM = 20                # MacLink::Page::name
MAX_ETIQUETA = 23           # Button.label
MAX_ICONA = 19              # Button.icon (vegeu ui.cpp)
MAX_APPS = 3                # Page.apps

TEMES = {
    0: "Fosc", 1: "Clar", 2: "Nit", 3: "Paper", 4: "Solaritzat",
    5: "Fosc suau", 6: "Grafit", 7: "Ocea",
}
ORIENTACIONS = ("v", "h")
NAVEGACIO = ("bar", "swipe", "both", "none")

# Claus que NO s'exporten mai (son d'aquest ordinador, no del disseny).
CLAUS_LOCALS = ("port", "refresh_ms")


# --- Utilitats internes ----------------------------------------------------

def _int(valor, minim, maxim, per_defecte):
    """Enter dins d'un rang. Qualsevol cosa estranya cau al valor per defecte."""
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return per_defecte
    return max(minim, min(maxim, n))


def _bool(valor, per_defecte=False):
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return valor != 0
    if isinstance(valor, str):
        return valor.strip().lower() in ("1", "true", "si", "sí", "yes", "on")
    return per_defecte


def _text(valor, maxim, per_defecte=""):
    if valor is None:
        return per_defecte
    return str(valor)[:maxim]


def _llista(valor):
    return valor if isinstance(valor, list) else []


def _esclau(nom, index=0):
    """Identificador estable a partir d'un nom ('Principal' -> 'principal').

    NO hi posem l'index: si dues pantalles es diuen igual, normalitza() ja els
    hi afegeix un sufix numeric nomes a les que calgui. Aixi l'identificador no
    canvia si l'usuari reordena les pantalles.
    """
    net = "".join(c if c.isalnum() else "-" for c in nom.lower())
    while "--" in net:
        net = net.replace("--", "-")
    return net.strip("-") or "pantalla"


def _enum_int(valor, valids, per_defecte):
    """Enter que ha de ser dins d'un conjunt: si no hi es, el valor per defecte."""
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return per_defecte
    return n if n in valids else per_defecte


def defecte():
    """Configuracio per defecte: una pantalla amb els gadgets basics."""
    return {
        "version": SCHEMA_VERSION,
        "port": "",
        "refresh_ms": 1000,
        "orientation": "v",
        "theme": 1,
        "theme_auto": 0,
        "theme_dark": 5,
        "theme_light": 1,
        "standby_s": 0,
        "idle_min": 0,
        "nav": "both",
        "notif_on": True,
        "favs_max": 15,
        "favs_carpetes": 0,
        "pages": [],
    }


# --- Migracions ------------------------------------------------------------

def _migra_1_a_2(cfg):
    """Del format implicit (sense `version`) a la versio 2.

    No cal inventar res: les pantalles ja porten `widgets` i `buttons`, i la
    posicio es dedueix de l'ordre de les llistes. Nomes hi afegim els camps
    nous amb els valors que ja s'estaven fent servir:
      * `id` estable a cada pantalla (per poder-hi enllacar sense dependre de
        l'index, que canvia en reordenar);
      * `grid` a cada pantalla (com es reparteixen els elements);
      * `on` a cada boto (que es el que ja fa servir la placa per amagar-lo).
    """
    out = copy.deepcopy(cfg)
    pantalles = _llista(out.get("pages"))
    for i, pg in enumerate(pantalles):
        if not isinstance(pg, dict):
            continue
        pg.setdefault("id", _esclau(_text(pg.get("name", ""), MAX_NOM), i))
        pg.setdefault("grid", {"mode": "auto", "cols": 3, "rows": 0})
        for b in _llista(pg.get("buttons")):
            if isinstance(b, dict) and "on" not in b:
                b["on"] = True
    return out


def migra(cfg):
    """Porta una configuracio de qualsevol versio al format actual."""
    if not isinstance(cfg, dict):
        return defecte()
    out = copy.deepcopy(cfg)
    v = out.get("version")
    if not isinstance(v, int) or v < 1:
        v = 1                                  # format implicit original
    if v < 2:
        out = _migra_1_a_2(out)
    out["version"] = SCHEMA_VERSION
    return out



# --- Normalitzacio ---------------------------------------------------------

def _normalitza_boto(b, index):
    """Un boto valid. L'`id` es l'accio (app:..., fav:..., tecla:...)."""
    if not isinstance(b, dict):
        return None
    bid = _text(b.get("id"), 64).strip()
    if not bid:
        return None
    out = {
        "id": bid,
        "label": _text(b.get("label"), MAX_ETIQUETA).strip() or bid,
        "on": _bool(b.get("on"), True),
        "icon": _text(b.get("icon"), MAX_ICONA),
        "keys": _text(b.get("keys"), 40),
    }
    if "cmd" in b:
        out["cmd"] = _text(b.get("cmd"), 200)
    pos = b.get("pos")
    if isinstance(pos, dict):          # posicio fixada a ma (opcional)
        out["pos"] = {
            "col": _int(pos.get("col"), 0, 7, 0),
            "row": _int(pos.get("row"), 0, 15, 0),
            "w":   _int(pos.get("w"), 1, 8, 1),
            "h":   _int(pos.get("h"), 1, 8, 1),
        }
    return out


def _normalitza_pantalla(pg, index):
    """Una pantalla valida, amb el que la placa sap pintar."""
    if not isinstance(pg, dict):
        return None
    nom = _text(pg.get("name"), MAX_NOM).strip() or "Pantalla %d" % (index + 1)
    dispo = str(pg.get("layout", "buttons"))
    if dispo not in DISPOSICIONS:
        dispo = "buttons"

    gadgets = []
    for w in _llista(pg.get("widgets")):
        w = str(w)
        if w in GADGETS and w not in gadgets:
            gadgets.append(w)
        if len(gadgets) >= MAX_GADGETS:
            break

    botons = []
    for i, b in enumerate(_llista(pg.get("buttons"))):
        nb = _normalitza_boto(b, i)
        if nb is not None:
            botons.append(nb)
        if len(botons) >= MAX_BOTONS:
            break

    g = pg.get("grid") if isinstance(pg.get("grid"), dict) else {}
    grid = {
        "mode": g.get("mode") if g.get("mode") in ("auto", "manual") else "auto",
        "cols": _int(g.get("cols"), 1, 4, 3),
        "rows": _int(g.get("rows"), 0, 8, 0),
    }

    apps = []
    for a in _llista(pg.get("apps")):
        a = _text(a, 64).strip()
        if a and a not in apps:
            apps.append(a)
        if len(apps) >= MAX_APPS:
            break

    return {
        "id": _text(pg.get("id"), 32).strip() or _esclau(nom, index),
        "name": nom,
        "icon": _text(pg.get("icon"), MAX_ICONA),
        "layout": dispo,
        "grid": grid,
        "widgets": gadgets,
        "buttons": botons,
        "apps": apps,
    }



def normalitza(cfg):
    """Valida i arrodoneix una configuracio. Sempre torna una copia valida.

    Es tolerant a proposit: si arriba una configuracio d'una versio anterior, o
    amb un valor espatllat, el que fem es arreglar-ho o deixar el valor per
    defecte en lloc de rebutjar-ho tot. Aixi un camp dolent no deixa el panell
    sense poder desar res.
    """
    if not isinstance(cfg, dict):
        return defecte()
    out = migra(cfg)

    net = defecte()
    net["port"] = _text(out.get("port"), 200)
    net["refresh_ms"] = _int(out.get("refresh_ms"), 200, 10000, 1000)
    ori = str(out.get("orientation", "v"))[:1].lower()
    net["orientation"] = ori if ori in ORIENTACIONS else "v"
    net["theme"] = _enum_int(out.get("theme"), set(TEMES), 1)
    net["theme_auto"] = 1 if _bool(out.get("theme_auto"), False) else 0
    net["theme_dark"] = _enum_int(out.get("theme_dark"), set(TEMES), 5)
    net["theme_light"] = _enum_int(out.get("theme_light"), set(TEMES), 1)
    net["standby_s"] = _int(out.get("standby_s"), 0, 86400, 0)
    net["idle_min"] = _int(out.get("idle_min"), 0, 240, 0)
    nav = str(out.get("nav", "both"))
    net["nav"] = nav if nav in NAVEGACIO else "both"
    net["notif_on"] = _bool(out.get("notif_on"), True)
    net["favs_max"] = _int(out.get("favs_max"), 0, 30, 15)
    net["favs_carpetes"] = _bool(out.get("favs_carpetes"), False)

    pantalles = []
    vists = set()
    for i, pg in enumerate(_llista(out.get("pages"))):
        npg = _normalitza_pantalla(pg, i)
        if npg is None:
            continue
        # Els identificadors han de ser unics: si no, l'editor no sabria a
        # quina pantalla es refereix un enllac.
        base = npg["id"]
        n = 2
        while npg["id"] in vists:
            npg["id"] = "%s-%d" % (base, n)
            n += 1
        vists.add(npg["id"])
        pantalles.append(npg)
        if len(pantalles) >= MAX_PANTALLES:
            break
    net["pages"] = pantalles
    return net



def valida(cfg):
    """Comprova una configuracio i torna (ok, llista de problemes).

    Serveix per avisar l'usuari ABANS de desar, no per bloquejar: normalitza()
    ja arregla el que pot.
    """
    problemes = []
    if not isinstance(cfg, dict):
        return False, ["la configuracio no es un objecte"]
    pantalles = _llista(cfg.get("pages"))
    if not pantalles:
        problemes.append("no hi ha cap pantalla")
    if len(pantalles) > MAX_PANTALLES:
        problemes.append("hi ha mes de %d pantalles" % MAX_PANTALLES)
    vists = set()
    for i, pg in enumerate(pantalles):
        if not isinstance(pg, dict):
            problemes.append("la pantalla %d no es valida" % (i + 1))
            continue
        nom = pg.get("name", i + 1)
        pid = str(pg.get("id", ""))
        if not pid:
            problemes.append("la pantalla '%s' no te identificador" % nom)
        elif pid in vists:
            problemes.append("l'identificador '%s' esta repetit" % pid)
        vists.add(pid)
        if str(pg.get("layout", "")) not in DISPOSICIONS:
            problemes.append("la pantalla '%s' te una disposicio desconeguda" % nom)
        if len(_llista(pg.get("widgets"))) > MAX_GADGETS:
            problemes.append("la pantalla '%s' te massa gadgets" % nom)
        if len(_llista(pg.get("buttons"))) > MAX_BOTONS:
            problemes.append("la pantalla '%s' te massa botons" % nom)
        for b in _llista(pg.get("buttons")):
            if isinstance(b, dict) and not str(b.get("id", "")).strip():
                problemes.append("hi ha un boto sense accio a '%s'" % nom)
    return (not problemes), problemes


# --- Elements (la vista que fa servir l'editor) ----------------------------

def elements_de(cfg, index):
    """Els elements d'una pantalla com a llista tipada.

    Cada element te SEMPRE els mateixos camps, tant si es un gadget com un
    boto: es el que permet que l'editor els tracti igual (seleccionar,
    arrossegar, editar propietats) sense saber detalls de la placa.
    """
    pages = _llista(cfg.get("pages"))
    if index < 0 or index >= len(pages):
        return []
    pg = pages[index]
    els = []
    for i, w in enumerate(_llista(pg.get("widgets"))):
        info = GADGETS.get(str(w), {})
        els.append({
            "id": "gadget:%s" % w,
            "tipus": "gadget",
            "gadget": str(w),
            "etiqueta": info.get("nom", str(w)),
            "icona": "",
            "visible": True,
            "pos": i,
            "accio": "",
            "tecles": "",
        })
    for i, b in enumerate(_llista(pg.get("buttons"))):
        if not isinstance(b, dict):
            continue
        els.append({
            "id": "boto:%d" % i,
            "tipus": "boto",
            "gadget": "",
            "etiqueta": _text(b.get("label"), MAX_ETIQUETA),
            "icona": _text(b.get("icon"), MAX_ICONA),
            "visible": _bool(b.get("on"), True),
            "pos": i,
            "accio": _text(b.get("id"), 64),
            "tecles": _text(b.get("tecles"), 40),
        })
    return els


# --- Desament i portabilitat ----------------------------------------------

def exporta(cfg):
    """Configuracio portable: sense res d'aquest ordinador.

    Fora el port serie i la frequencia de refresc (son preferencies locals) i
    cap ruta absoluta. El que queda es el DISSENY, que es pot passar a un altre
    usuari o ordinador.
    """
    net = normalitza(cfg)
    out = copy.deepcopy(net)
    for k in CLAUS_LOCALS:
        out.pop(k, None)
    out["version"] = SCHEMA_VERSION
    return out


def importa(dades):
    """Carrega una configuracio exportada (o d'una versio anterior)."""
    if isinstance(dades, (str, bytes, bytearray)):
        dades = json.loads(dades)
    return normalitza(dades)


def carrega(cami):
    """Llegeix la configuracio del disc (o la per defecte si no hi es)."""
    if not os.path.exists(cami):
        return defecte()
    try:
        with open(cami, "r", encoding="utf-8") as fh:
            return normalitza(json.load(fh))
    except (OSError, ValueError):
        return defecte()


def desa(cami, cfg):
    """Desa la configuracio de manera atomica (mai a mig escriure)."""
    net = normalitza(cfg)
    tmp = cami + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(net, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, cami)
    return net

