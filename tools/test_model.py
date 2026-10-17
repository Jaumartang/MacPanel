#!/usr/bin/env python3
"""test_model.py - proves del model de dades del panell (mac/panel_model.py).

No cal la placa ni el pont: son proves pures de validacio, migracions i
portabilitat. Es poden executar sempre.

Us:
    python3 tools/test_model.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "mac"))

import panel_model as M          # noqa: E402

fallades = []


def comprova(nom, condicio, detall=""):
    if condicio:
        print("  ok    %s" % nom)
    else:
        print("  FALLA %s  %s" % (nom, detall))
        fallades.append(nom)


def igual(nom, obtingut, esperat):
    comprova(nom, obtingut == esperat, "obtingut=%r esperat=%r" % (obtingut, esperat))


# --- Configuracio de prova (el format vell, sense `version`) ---------------

VELLA = {
    "port": "/dev/cu.usbserial-1420",
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
    "pages": [
        {"name": "Principal", "icon": "", "layout": "gauges",
         "widgets": ["cpu", "mem", "disk", "bat"],
         "buttons": [{"id": "app_safari", "label": "Safari", "on": False,
                      "icon": "safari", "keys": ""},
                     {"id": "app:com.apple.Safari", "label": "Safari 2",
                      "on": True, "icon": "comapplesafari", "keys": ""}],
         "apps": ["com.apple.Safari"]},
        {"name": "Favorits", "icon": "github", "layout": "favs",
         "widgets": [], "buttons": [], "apps": []},
    ],
}


def prova_migracio():
    print("migracio del format vell (sense version):")
    net = M.normalitza(VELLA)
    igual("la versio puja a la actual", net["version"], M.SCHEMA_VERSION)
    igual("hi ha les dues pantalles", len(net["pages"]), 2)
    comprova("cada pantalla te identificador",
             all(p["id"] for p in net["pages"]))
    igual("l'identificador es estable", net["pages"][0]["id"], "principal")
    igual("la segona pantalla tambe", net["pages"][1]["id"], "favorits")
    igual("cada pantalla te graella", net["pages"][0]["grid"],
          {"mode": "auto", "cols": 3, "rows": 0})
    igual("els gadgets es conserven", net["pages"][0]["widgets"],
          ["cpu", "mem", "disk", "bat"])
    igual("els botons es conserven (2)", len(net["pages"][0]["buttons"]), 2)
    comprova("el boto desactivat segueix desactivat",
             net["pages"][0]["buttons"][0]["on"] is False)
    igual("l'accio del boto es conserva",
          net["pages"][0]["buttons"][1]["id"], "app:com.apple.Safari")


def prova_normalitzacio():
    print("normalitzacio de valors espatllats:")
    net = M.normalitza({
        "orientation": "X", "theme": 99, "standby_s": -5, "nav": "inventat",
        "favs_max": 999, "refresh_ms": 5, "pages": "aixo no es una llista",
    })
    igual("orientacio dolenta -> v", net["orientation"], "v")
    igual("tema fora de rang -> el de defecte", net["theme"], 1)
    igual("repos negatiu -> 0", net["standby_s"], 0)
    igual("navegacio desconeguda -> both", net["nav"], "both")
    igual("favs_max limitat", net["favs_max"], 30)
    igual("refresc minim", net["refresh_ms"], 200)
    igual("pages que no es llista -> cap", net["pages"], [])

    net = M.normalitza({"pages": [
        {"name": "X" * 60, "layout": "inventada",
         "widgets": ["cpu", "cpu", "noexisteix", "mem"],
         "buttons": [{"label": "sense accio"},
                     {"id": "media_play", "label": "P" * 90}]},
    ]})
    igual("disposicio desconeguda -> buttons", net["pages"][0]["layout"], "buttons")
    igual("gadget desconegut i duplicat fora", net["pages"][0]["widgets"],
          ["cpu", "mem"])
    igual("boto sense accio descartat", len(net["pages"][0]["buttons"]), 1)
    igual("etiqueta retallada", len(net["pages"][0]["buttons"][0]["label"]),
          M.MAX_ETIQUETA)
    igual("nom retallat", len(net["pages"][0]["name"]), M.MAX_NOM)



def prova_limits():
    print("limits del dispositiu:")
    net = M.normalitza({"pages": [{"name": "P%d" % i, "layout": "buttons"}
                                  for i in range(40)]})
    igual("maxim de pantalles", len(net["pages"]), M.MAX_PANTALLES)
    net = M.normalitza({"pages": [{"name": "P", "widgets":
                                   ["cpu", "mem", "disk", "bat", "net", "load",
                                    "uptime", "time", "host", "cpu"]}]})
    igual("maxim de gadgets", len(net["pages"][0]["widgets"]), M.MAX_GADGETS)
    net = M.normalitza({"pages": [{"name": "P", "buttons":
                                   [{"id": "media_play"} for _ in range(40)]}]})
    igual("maxim de botons", len(net["pages"][0]["buttons"]), M.MAX_BOTONS)


def prova_identificadors():
    print("identificadors unics:")
    net = M.normalitza({"pages": [{"id": "igual", "name": "A"},
                                  {"id": "igual", "name": "B"},
                                  {"id": "igual", "name": "C"}]})
    ids = [p["id"] for p in net["pages"]]
    igual("no es repeteixen", len(set(ids)), 3)
    igual("el primer es queda igual", ids[0], "igual")


def prova_valida():
    print("valida() avisa sense bloquejar:")
    ok, problemes = M.valida(M.normalitza(VELLA))
    comprova("una configuracio bona passa", ok, str(problemes))
    ok, problemes = M.valida({"pages": []})
    comprova("sense pantalles avisa", not ok)
    comprova("i diu per que", any("cap pantalla" in p for p in problemes))
    ok, _ = M.valida({"pages": [{"id": "a", "name": "A", "layout": "nop"}]})
    comprova("disposicio desconeguda avisa", not ok)
    ok, _ = M.valida({"pages": [{"id": "a", "name": "A", "layout": "buttons"},
                                {"id": "a", "name": "B", "layout": "buttons"}]})
    comprova("identificador repetit avisa", not ok)


def prova_elements():
    print("vista d'elements de l'editor:")
    net = M.normalitza(VELLA)
    els = M.elements_de(net, 0)
    igual("4 gadgets + 2 botons", len(els), 6)
    igual("el primer es un gadget", els[0]["tipus"], "gadget")
    igual("el primer gadget es la CPU", els[0]["gadget"], "cpu")
    igual("te etiqueta llegible", els[0]["etiqueta"], "CPU")
    comprova("te posicio", isinstance(els[0]["pos"], int))
    igual("el primer boto porta la seva accio", els[4]["accio"], "app_safari")
    igual("i la seva visibilitat", els[4]["visible"], False)
    igual("pantalla inexistent -> cap element", M.elements_de(net, 99), [])


def prova_portabilitat():
    print("exportar i importar:")
    net = M.normalitza(VELLA)
    exp = M.exporta(net)
    comprova("no exporta el port", "port" not in exp)
    comprova("no exporta el refresc", "refresh_ms" not in exp)
    comprova("si exporta el disseny", "pages" in exp and len(exp["pages"]) == 2)
    text = json.dumps(exp, ensure_ascii=False)
    comprova("no hi ha rutes locals al text", "/Users/" not in text)
    tornat = M.importa(text)
    igual("tornar a importar dona el mateix",
          [p["id"] for p in tornat["pages"]], ["principal", "favorits"])
    igual("i els mateixos botons", len(tornat["pages"][0]["buttons"]), 2)
    vella_text = json.dumps(VELLA, ensure_ascii=False)
    igual("importa una configuracio sense versio",
          len(M.importa(vella_text)["pages"]), 2)
    comprova("i li posa la versio",
             M.importa(vella_text)["version"] == M.SCHEMA_VERSION)


def prova_disc():
    print("desar i carregar del disc:")
    with tempfile.TemporaryDirectory() as tmp:
        cami = os.path.join(tmp, "config.json")
        net = M.normalitza(VELLA)
        M.desa(cami, net)
        comprova("el fitxer existeix", os.path.exists(cami))
        comprova("i no deixa temporals", not os.path.exists(cami + ".tmp"))
        igual("es torna a llegir igual", M.carrega(cami), net)
        with open(cami, "w", encoding="utf-8") as fh:
            fh.write("{aixo no es json")
        igual("un fitxer espatllat no peta", M.carrega(cami), M.defecte())
        igual("un fitxer que no hi es dona el defecte",
              M.carrega(os.path.join(tmp, "no-existeix.json")), M.defecte())


def main():
    print("=== proves del model de dades ===")
    prova_migracio()
    prova_normalitzacio()
    prova_limits()
    prova_identificadors()
    prova_valida()
    prova_elements()
    prova_portabilitat()
    prova_disc()
    print()
    if fallades:
        print("=== HI HA %d PROBLEMES: %s ===" % (len(fallades), ", ".join(fallades)))
        return 1
    print("=== TOT OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
