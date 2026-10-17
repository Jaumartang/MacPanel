#!/usr/bin/env python3
"""
bridge.py - Motor del pont entre el Mac i l'ESP32 (Mac Panel).

  - Llegeix l'estat del Mac (CPU, RAM, disc, bateria, xarxa, load, uptime...) amb
    ordres natives de macOS (top/ps, vm_stat, df, pmset, netstat, sysctl...).
  - L'envia pel port serie a l'ESP32 en linies 'S clau=valor ...'.
  - Rep les comandes dels botons ('C <id>') i executa l'accio al Mac.
  - Envia la configuracio de la pantalla ('CFG {json}') i la desa al disc.

Nomes depen de pyserial (les estadistiques son totes amb eines del sistema).
"""

from __future__ import annotations

import base64
import io
import json
import os
import plistlib
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime

try:
    import serial
    from serial.tools import list_ports
    HAS_SERIAL = True
except ImportError:  # pragma: no cover
    serial = None
    list_ports = None
    HAS_SERIAL = False

# Pillow: nomes el fa servir l'extraccio d'icones de les apps (i la conversio a
# .bin, que ja el demanava). Si no hi es, les icones d'app no es poden extreure
# i la resta del pont funciona igual.
try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:  # pragma: no cover
    Image = None
    HAS_PILLOW = False

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "panel_config.json")
BAUD = 115200

# Memoria curta de l'estat de la pantalla del Mac (evita cridar 'pmset' cada
# segon): {"t": instant de l'ultima consulta, "v": pantalla encesa}.
_dsp_cache = {"t": 0.0, "v": True}

# Igual per a l'aplicacio que te el focus (consulta cada 1,5 s com a molt).
_front_cache = {"t": 0.0, "v": ("", "")}

# Cataleg de widgets (ha de coincidir amb include/panel_config.h).
WIDGETS = ["cpu", "mem", "disk", "bat", "net", "load", "uptime", "time", "host"]

# Cataleg d'accions d'estoc. 'args' s'executa sense shell (segur); 'shell' amb
# shell. Les accions personalitzades les defineix l'usuari al panell.
# Cataleg d'accions d'estoc. Cada accio pot tenir:
#   "keys": combinacio de tecles que envia la PLACA per Bluetooth (HID). Es el
#           que fa que surti el requadre del volum del macOS i que funcioni a
#           qualsevol aplicacio, sense permisos.
#   "args": comanda que executa el MAC (per a accions que no son tecles).
ACTIONS = {
    # --- Mitjans i volum (tecles de debo, per Bluetooth) ---
    "media_prev":   {"label": "Mitjans: enrere",     "keys": "media_prev"},
    "media_play":   {"label": "Mitjans: play/pausa", "keys": "media_playpause"},
    "media_next":   {"label": "Mitjans: endavant",   "keys": "media_next"},
    "vol_down":     {"label": "Volum -",             "keys": "media_volumedown"},
    "vol_up":       {"label": "Volum +",             "keys": "media_volumeup"},
    "mute":         {"label": "Silenci",             "keys": "media_mute"},

    # --- Edicio (combinacions dins de qualsevol aplicacio) ---
    "edit_copy":    {"label": "Copiar",             "keys": "cmd+c"},
    "edit_paste":   {"label": "Enganxar",           "keys": "cmd+v"},
    "edit_cut":     {"label": "Retallar",           "keys": "cmd+x"},
    "edit_undo":    {"label": "Desfer",             "keys": "cmd+z"},
    "edit_redo":    {"label": "Refer",              "keys": "shift+cmd+z"},
    "edit_all":     {"label": "Seleccionar tot",    "keys": "cmd+a"},
    "edit_find":    {"label": "Cercar",             "keys": "cmd+f"},
    "edit_save":    {"label": "Desar",              "keys": "cmd+s"},
    "edit_dup":     {"label": "Duplicar",           "keys": "cmd+d"},
    "edit_group":   {"label": "Agrupar",            "keys": "cmd+g"},
    "edit_ungroup": {"label": "Desagrupar",         "keys": "shift+cmd+g"},
    "edit_export":  {"label": "Exportar",           "keys": "shift+cmd+e"},
    "edit_import":  {"label": "Importar",           "keys": "shift+cmd+i"},
    "zoom_in":      {"label": "Zoom +",             "keys": "cmd+="},
    "zoom_out":     {"label": "Zoom -",             "keys": "cmd+-"},
    "zoom_fit":     {"label": "Ajustar a la finestra", "keys": "cmd+0"},
    "win_close":    {"label": "Tancar finestra",    "keys": "cmd+w"},
    "win_full":     {"label": "Pantalla completa",  "keys": "ctrl+cmd+f"},

    # --- Espais / escriptoris i finestres ---
    "space_left":   {"label": "Escriptori esquerra", "keys": "ctrl+left"},
    "space_right":  {"label": "Escriptori dreta",    "keys": "ctrl+right"},
    "mission":      {"label": "Mission Control",     "keys": "ctrl+up"},
    "app_windows":  {"label": "Finestres de l'app",  "keys": "ctrl+down"},
    "spotlight":    {"label": "Spotlight (cercar)",  "keys": "cmd+space"},
    "launchpad":    {"label": "Launchpad",           "keys": "f4"},

    # --- Brillantor de la pantalla del Mac (tecles reals del sistema) ---
    "bright_up":    {"label": "Brillantor +",
                     "args": ["osascript", "-e",
                              'tell application "System Events" to key code 145']},
    "bright_down":  {"label": "Brillantor -",
                     "args": ["osascript", "-e",
                              'tell application "System Events" to key code 144']},

    # --- Apps i sistema (comandes al Mac) ---
    "app_terminal": {"label": "Obrir Terminal", "args": ["open", "-a", "Terminal"]},
    "app_safari":   {"label": "Obrir Safari", "args": ["open", "-a", "Safari"]},
    "app_vscode":   {"label": "Obrir VS Code", "args": ["open", "-a", "Visual Studio Code"]},
    "app_music":    {"label": "Obrir Musica", "args": ["open", "-a", "Music"]},
    "app_finder":   {"label": "Obrir Finder", "args": ["open", "-a", "Finder"]},
    "app_calendar": {"label": "Obrir Calendari", "args": ["open", "-a", "Calendar"]},
    "app_facetime": {"label": "Obrir FaceTime", "args": ["open", "-a", "FaceTime"]},
    "app_mail":     {"label": "Obrir Mail", "args": ["open", "-a", "Mail"]},
    "app_notes":    {"label": "Obrir Notes", "args": ["open", "-a", "Notes"]},
    "app_photos":   {"label": "Obrir Fotos", "args": ["open", "-a", "Photos"]},
    "app_messages": {"label": "Obrir Missatges", "args": ["open", "-a", "Messages"]},
    "app_reminders":{"label": "Obrir Recordatoris", "args": ["open", "-a", "Reminders"]},
    "app_settings": {"label": "Ajustos del Sistema", "args": ["open", "-a", "System Settings"]},
    "app_activity": {"label": "Monitor d'activitat", "args": ["open", "-a", "Activity Monitor"]},
    "app_spotify":  {"label": "Obrir Spotify", "args": ["open", "-a", "Spotify"]},
    "app_chrome":   {"label": "Obrir Chrome", "args": ["open", "-a", "Google Chrome"]},
    "app_firefox":  {"label": "Obrir Firefox", "args": ["open", "-a", "Firefox"]},
    "app_brave":    {"label": "Obrir Brave", "args": ["open", "-a", "Brave Browser"]},
    "app_slack":    {"label": "Obrir Slack", "args": ["open", "-a", "Slack"]},
    "app_teams":    {"label": "Obrir Teams", "args": ["open", "-a", "Microsoft Teams"]},
    "app_notion":   {"label": "Obrir Notion", "args": ["open", "-a", "Notion"]},
    "app_dropbox":  {"label": "Obrir Dropbox", "args": ["open", "-a", "Dropbox"]},
    "app_github":   {"label": "Obrir GitHub Desktop", "args": ["open", "-a", "GitHub Desktop"]},
    "app_zoom":     {"label": "Obrir Zoom", "args": ["open", "-a", "zoom.us"]},
    "app_coreldraw":{"label": "Obrir CorelDRAW", "args": ["open", "-a", "CorelDRAW"]},
    "app_photopaint":{"label": "Obrir Photo-Paint", "args": ["open", "-a", "Corel PHOTO-PAINT"]},
    "app_photoshop":{"label": "Obrir Photoshop", "args": ["open", "-a", "Adobe Photoshop 2024"]},
    "app_illustrator":{"label": "Obrir Illustrator", "args": ["open", "-a", "Adobe Illustrator"]},
    "app_indesign": {"label": "Obrir InDesign", "args": ["open", "-a", "Adobe InDesign 2024"]},
    "app_figma":    {"label": "Obrir Figma", "args": ["open", "-a", "Figma"]},
    "app_blender":  {"label": "Obrir Blender", "args": ["open", "-a", "Blender"]},
    "app_davinci":  {"label": "Obrir DaVinci Resolve", "args": ["open", "-a", "DaVinci Resolve"]},
    "app_premiere": {"label": "Obrir Premiere Pro", "args": ["open", "-a", "Adobe Premiere Pro 2024"]},
    "app_quicktime":{"label": "Obrir QuickTime", "args": ["open", "-a", "QuickTime Player"]},
    "app_textedit": {"label": "Obrir TextEdit", "args": ["open", "-a", "TextEdit"]},
    "app_timemachine":{"label": "Time Machine", "args": ["open", "-a", "Time Machine"]},
    "app_appstore": {"label": "Obrir App Store", "args": ["open", "-a", "App Store"]},
    "app_maps":     {"label": "Obrir Mapes", "args": ["open", "-a", "Maps"]},
    "app_airdrop":  {"label": "AirDrop", "args": ["open", "-a", "AirDrop"]},
    "sys_dnd":      {"label": "No molestar",
                     "args": ["osascript", "-e",
                              'tell application "System Events" to key code 61 using {option down, command down}']},
    "sys_eject":    {"label": "Expulsar disc",
                     "args": ["osascript", "-e",
                              'tell application "System Events" to key code 14 using {command down}']},
    "sys_lock":     {"label": "Bloquejar pantalla",
                     "args": ["osascript", "-e",
                              'tell application "System Events" to keystroke "q" using {command down, control down}']},
    "sys_sleep":    {"label": "Dormir el Mac", "args": ["pmset", "sleepnow"]},
    "sys_shot":     {"label": "Captura de pantalla",
                     "args": ["screencapture", "-x",
                              os.path.join(os.path.expanduser("~"), "Desktop",
                                           "macpanel_shot.png")]},
    "sys_dark":     {"label": "Mode clar/fosc",
                     "args": ["osascript", "-e",
                              'tell application "System Events" to tell appearance preferences '
                              'to set dark mode to not dark mode']},
}

DEFAULT_CONFIG = {
    "port": "",
    "refresh_ms": 1000,
    "orientation": "v",          # "v" = 320x480 | "h" = 480x320
    "theme": 5,                  # 0 Fosc | 1 Clar | 2 Neo | 3 Grafite | 4 Pastel | 5 HUD
    "theme_auto": 0,             # 1 = el tema segueix el mode clar/fosc del Mac
    "theme_dark": 5,             # tema amb el Mac en fosc (mode automatic)
    "theme_light": 1,            # tema amb el Mac en clar (mode automatic)
    "standby_s": 0,              # segons sense tocar abans d'apagar la pantalla (0 = mai)
    "idle_min": 5,               # minuts inactiu al Mac -> pantalla de rellotge (0 = mai)
    "nav": "both",               # navegacio: both | bar | swipe | off
    "pages": [
        {"name": "Gauges", "icon": "grid", "layout": "gauges",
         "widgets": ["cpu", "mem", "disk", "bat"],
         "buttons": [
             {"id": "sys_shot", "label": "SHOT", "icon": "shot"},
         ]},
        {"name": "Grafics", "icon": "activity_monitor", "layout": "graph",
         "widgets": ["cpu", "mem", "disk"],
         "buttons": []},
        {"name": "Estat", "icon": "grid", "layout": "status",
         "widgets": ["cpu", "mem", "disk", "bat", "net"],
         "buttons": [
             {"id": "media_play", "label": "PLAY", "icon": "play"},
         ]},
        {"name": "Mitjans", "icon": "play", "layout": "buttons", "widgets": [],
         "buttons": [
             {"id": "media_prev", "label": "PREV", "icon": "prev"},
             {"id": "media_play", "label": "PLAY", "icon": "play"},
             {"id": "media_next", "label": "NEXT", "icon": "next"},
             {"id": "vol_down", "label": "VOL-", "icon": "vol_down"},
             {"id": "vol_up", "label": "VOL+", "icon": "vol_up"},
             {"id": "mute", "label": "MUTE", "icon": "mute"},
         ]},
        {"name": "Eines", "icon": "copy", "layout": "buttons", "widgets": [],
         "buttons": [
             {"id": "edit_copy", "label": "COPY", "icon": "copy"},
             {"id": "edit_paste", "label": "PASTE", "icon": "paste"},
             {"id": "edit_cut", "label": "CUT", "icon": "cut"},
             {"id": "edit_undo", "label": "UNDO", "icon": "undo"},
             {"id": "edit_redo", "label": "REDO", "icon": "redo"},
             {"id": "edit_group", "label": "GROUP", "icon": "group"},
             {"id": "edit_export", "label": "EXPORT", "icon": "export"},
             {"id": "edit_import", "label": "IMPORT", "icon": "import"},
             {"id": "edit_save", "label": "SAVE", "icon": "save"},
         ]},
        {"name": "Sistema", "icon": "system_settings", "layout": "buttons", "widgets": [],
         "buttons": [
             {"id": "sys_lock", "label": "Bloqueja", "icon": "lock"},
             {"id": "sys_sleep", "label": "Dormir", "icon": "sleep"},
             {"id": "sys_shot", "label": "Captura", "icon": "shot"},
             {"id": "sys_dark", "label": "Clar/Fosc", "icon": "dark"},
             {"id": "bright_up", "label": "Bril +", "icon": "brightness_up"},
             {"id": "bright_down", "label": "Bril -", "icon": "brightness_down"},
             {"id": "sys_dnd", "label": "No molestar", "icon": "do_not_disturb"},
             {"id": "spotlight", "label": "Spotlight", "icon": "spotlight"},
             {"id": "sys_eject", "label": "Expulsar", "icon": "eject"},
         ]},
        {"name": "Rellotge", "icon": "clock", "layout": "clock", "widgets": [],
         "buttons": []},
        {"name": "Numpad", "icon": "num", "layout": "numpad", "widgets": [],
         "buttons": []},
        {"name": "Obertes", "icon": "activity_monitor", "layout": "launcher", "widgets": [],
         "buttons": []},
        {"name": "Pestanyes", "icon": "spotlight", "layout": "tabs", "widgets": [],
         "buttons": []},
        {"name": "Apps", "icon": "spotlight", "layout": "buttons", "widgets": [],
         "buttons": [
             {"id": "app_safari", "label": "Safari", "icon": "safari"},
             {"id": "app_mail", "label": "Mail", "icon": "mail"},
             {"id": "app_calendar", "label": "Calendari", "icon": "calendar"},
             {"id": "app_messages", "label": "Missatges", "icon": "messages"},
             {"id": "app_notes", "label": "Notes", "icon": "notes"},
             {"id": "app_music", "label": "Musica", "icon": "music"},
             {"id": "app_photos", "label": "Fotos", "icon": "photos"},
             {"id": "app_terminal", "label": "Terminal", "icon": "terminal"},
             {"id": "app_finder", "label": "Finder", "icon": "finder"},
             {"id": "app_spotify", "label": "Spotify", "icon": "spotify"},
             {"id": "app_vscode", "label": "VS Code", "icon": "vscode"},
             {"id": "app_chrome", "label": "Chrome", "icon": "chrome"},
         ]},
        {"name": "Corel", "icon": "coreldraw", "layout": "buttons", "widgets": [],
         "buttons": [
             {"id": "app_coreldraw", "label": "CorelDRAW", "icon": "coreldraw"},
             {"id": "app_photopaint", "label": "PhotoPaint", "icon": "corel_photopaint"},
             {"id": "app_illustrator", "label": "Illustrator", "icon": "illustrator"},
             {"id": "app_photoshop", "label": "Photoshop", "icon": "photoshop"},
             {"id": "app_indesign", "label": "InDesign", "icon": "indesign"},
             {"id": "app_figma", "label": "Figma", "icon": "figma"},
             {"id": "edit_group", "label": "Agrupar", "icon": "group"},
             {"id": "edit_export", "label": "Exportar", "icon": "export"},
             {"id": "edit_save", "label": "Desar", "icon": "save"},
         ]},
        {"name": "Espais", "icon": "grid", "layout": "buttons", "widgets": [],
         "buttons": [
             {"id": "space_left", "label": "Esq", "icon": "prev"},
             {"id": "space_right", "label": "Dreta", "icon": "next"},
             {"id": "mission", "label": "Mission", "icon": "grid"},
             {"id": "app_windows", "label": "Finestres", "icon": "copy"},
             {"id": "launchpad", "label": "Launchpad", "icon": "app_store"},
             {"id": "app_settings", "label": "Ajustos", "icon": "system_settings"},
             {"id": "app_activity", "label": "Activitat", "icon": "activity_monitor"},
             {"id": "app_timemachine", "label": "Time Mach.", "icon": "time_machine"},
             {"id": "app_quicktime", "label": "QuickTime", "icon": "quicktime"},
         ]},
    ],
}


def display_awake():
    """True si la pantalla del Mac esta encesa.

    Fa servir IODisplayWrangler: el seu estat es 4 quan la pantalla es activa i
    0 quan el Mac l'ha apagada (estalvi d'energia o repòs). Amb aixo l'ESP32
    sap quan ha d'apagar la seva pantalla i quan ha de tornar a encendre's.
    """
    now = time.time()
    if now - _dsp_cache["t"] < 2.0:          # no cal preguntar-ho cada segon
        return _dsp_cache["v"]
    awake = True
    try:
        out = subprocess.run(["pmset", "-g", "powerstate", "IODisplayWrangler"],
                             capture_output=True, text=True, timeout=2.0).stdout
        for line in out.splitlines():
            if "IODisplayWrangler" in line:
                parts = line.split()
                # Format: nom, estat actual, estat maxim, descripcio.
                # La pantalla nomes esta ENCESA quan arriba a l'estat maxim
                # (4). Despres de 'pmset displaysleepnow' passa per l'1, i amb
                # un simple "> 0" la placa creuria que el Mac esta despert i no
                # apagaria mai la seva pantalla.
                if len(parts) >= 3:
                    try:
                        actual = int(parts[1])
                        maxim = int(parts[2])
                    except ValueError:
                        actual, maxim = int(parts[1]), 1
                    awake = actual >= maxim
                elif len(parts) >= 2:
                    awake = int(parts[1]) > 0
                break
    except Exception:
        awake = True
    _dsp_cache["t"] = now
    _dsp_cache["v"] = awake
    return awake


def front_app():
    """(bundle_id, nom) de l'aplicacio que te el focus al Mac.

    Fa servir 'lsappinfo', una eina del sistema que no necessita permisos
    d'Accessibilitat (que si caldrien amb AppleScript). Si no se sap, retorna
    ("", "").
    """
    now = time.time()
    if now - _front_cache["t"] < 1.5:         # no cal preguntar-ho cada segon
        return _front_cache["v"]
    res = ("", "")
    try:
        asn = subprocess.run(["lsappinfo", "front"], capture_output=True,
                             text=True, timeout=2.0).stdout.strip()
        if asn.startswith("ASN:"):
            asn = asn.split()[0]
            out = subprocess.run(["lsappinfo", "info", "-only", "name",
                                  "-only", "bundleid", asn],
                                 capture_output=True, text=True,
                                 timeout=2.0).stdout
            mb = re.search(r'"CFBundleIdentifier"="([^"]*)"', out)
            mn = re.search(r'"LSDisplayName"="([^"]*)"', out)
            bundle = mb.group(1) if mb else ""
            name = mn.group(1) if mn else ""
            # Els salvapantalles i el login no son "apps" de veritat.
            if bundle and not bundle.startswith("com.apple.ScreenSaver"):
                res = (bundle, name)
    except Exception:
        res = ("", "")
    _front_cache["t"] = now
    _front_cache["v"] = res
    return res


def idle_seconds():
    """Segons que fa que no es toca ni el teclat ni el ratoli."""
    try:
        out = subprocess.run(["ioreg", "-c", "IOHIDSystem"],
                             capture_output=True, text=True, timeout=2.0).stdout
        m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
        if m:
            return int(m.group(1)) / 1e9
    except Exception:
        pass
    return 0.0


def load_config():
    """Carrega panel_config.json (o els valors per defecte)."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            if isinstance(cfg, dict):
                base = json.loads(json.dumps(DEFAULT_CONFIG))
                base.update(cfg)
                return base
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(cfg):
    """Desa la configuracio a panel_config.json."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)

def list_icons():
    """Noms de les icones disponibles (Assets/icons/*.png i Assets/icons/bin/*.bin)."""
    names = set()
    base = os.path.join(os.path.dirname(APP_DIR), "Assets", "icons")
    for folder, ext in ((base, ".png"), (os.path.join(base, "bin"), ".bin")):
        if os.path.isdir(folder):
            for f in os.listdir(folder):
                if f.lower().endswith(ext):
                    names.add(os.path.splitext(f)[0])
    return sorted(names)


def icons_dir():
    d = os.path.join(os.path.dirname(APP_DIR), "Assets", "icons")
    os.makedirs(d, exist_ok=True)
    return d


_png2bin = None


def png_to_bin(png_bytes, size=32, nom=None):
    """Converteix un PNG a bytes RGB565 big-endian amb el fons transparent.

    Fa servir la MATEIXA conversio que tools/png2bin.py: aixi el panell web i
    l'eina de linia d'ordres donen exactament el mateix resultat (abans hi
    havia dues implementacions i no coincidien).

    size=32 ha de coincidir amb ICON_PX (include/panel_config.h) i amb SIZE de
    png2bin.py: la placa rebutja qualsevol .bin que no faci 32*32*2 = 2048 B.

    Si 'nom' es una icona d'app (Assets/icons/apps.txt), es queda sencera.
    """
    global _png2bin
    if _png2bin is None:
        tools = os.path.join(os.path.dirname(APP_DIR), "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import png2bin as mod
        _png2bin = mod
    return _png2bin.png_bytes_to_bin(png_bytes, size, nom)


def clean_icon_name(name):
    """Deixa el nom en minuscules i nomes [a-z0-9_] (max. 19 caracters)."""
    return re.sub(r"[^a-z0-9_]", "", (name or "").lower())[:19]


def nom_icona_app(bundle):
    """Nom d'icona per a una app, derivat del seu bundle id.

    El limit son 19 caracters: es el que cap a Button.icon[20] de la placa, i
    si ens passessim la placa retallaria el nom i dues apps diferents podrien
    acabar compartint icona. Per aixo, quan el bundle id es llarg, hi posem un
    hash curt al final en lloc de tallar-lo a seques.
    """
    net = re.sub(r"[^a-z0-9_]", "", (bundle or "").lower())
    if not net:
        return ""
    if len(net) <= 19:
        return net
    import hashlib
    h = hashlib.sha1(bundle.encode("utf-8")).hexdigest()[:4]
    return net[:14] + "_" + h          # 14 + 1 + 4 = 19


def _run(cmd, timeout=2.0):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


# --- Estadistiques del Mac -------------------------------------------------

# Caches de valors que canvien poc. Cada subprocess extra al bucle de stats es
# una oportunitat que el Mac es trabi un moment de càrrega (i la placa, en no
# rebre cap linia S durant 3 s, perd l'enllac i apaga la pantalla). Amb
# aixi passem de ~8 subprocessos per segon a 2-3.
_boot_epoch = None     # hora d'arrencada del Mac (per l'uptime, un sol cop)
_memsize = 0           # RAM total (un sol cop: mai no canvia)
_hostname_c = ""       # nom del Mac (un sol cop: mai no canvia)
_disk_c = (0.0, 0.0)   # (moment, %) del disc, refrescat cada 30 s
_bat_c = (0.0, (None, -1))   # (moment, (%, carregant)), cada 10 s
_dark_c = (0.0, 0)     # (moment, mode fosc), cada 10 s

# --- CPU -------------------------------------------------------------------
# Els comptadors del nucli (Mach) donen el consum REAL entre dues lectures. Amb
# 'ps -o %cpu' sortia un valor molt mes baix, perque cada proces hi porta la
# MITJANA des que va arrencar, no el que està consumint ara.
_cpu_prev = None

try:
    import ctypes
    import ctypes.util

    _libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    _libc.mach_host_self.restype = ctypes.c_uint
    _libc.host_statistics.argtypes = [ctypes.c_uint, ctypes.c_int,
                                      ctypes.c_void_p, ctypes.c_void_p]
    _libc.host_statistics.restype = ctypes.c_int
    _HAS_MACH = True
except Exception:
    _HAS_MACH = False

_HOST_CPU_LOAD_INFO = 3


def _cpu_ticks():
    """(usada, total) de ticks de CPU des de l'arrencada, o None si no es pot."""
    info = (ctypes.c_uint32 * 4)()          # user, system, idle, nice
    count = ctypes.c_uint(4)
    rc = _libc.host_statistics(_libc.mach_host_self(), _HOST_CPU_LOAD_INFO,
                               ctypes.byref(info), ctypes.byref(count))
    if rc != 0:
        return None
    used = info[0] + info[1] + info[3]      # user + system + nice
    return used, used + info[2]             # + idle


def cpu_percent():
    """% de CPU global (0-100), de la diferencia entre aquesta lectura i
    l'anterior: o sigui, el consum real d'aquest instant."""
    global _cpu_prev

    if _HAS_MACH:
        t = _cpu_ticks()
        if t is not None:
            used, total = t
            prev, _cpu_prev = _cpu_prev, t
            if prev is None:
                return 0.0                  # primera lectura: encara no hi ha delta
            d_used = used - prev[0]
            d_total = total - prev[1]
            if d_total > 0:
                return max(0.0, min(100.0, 100.0 * d_used / d_total))
            return 0.0

    # Pla B: 'top' (nomes el segon mostreig, que es l'instantani).
    out = _run(["top", "-l", "2", "-n", "0", "-s", "1"], timeout=6.0)
    val = None
    for line in out.splitlines():
        if line.startswith("CPU usage"):
            m = re.search(r"([\d.]+)%\s*idle", line)
            if m:
                val = 100.0 - float(m.group(1))
    return max(0.0, min(100.0, val)) if val is not None else 0.0


def mem_percent():
    """% de memoria usada = (active + wired + compressor) / total."""
    global _memsize
    out = _run(["vm_stat"])
    page = 4096
    m = re.search(r"page size of (\d+)", out)
    if m:
        page = int(m.group(1))

    def pages(name):
        mm = re.search(re.escape(name) + r":\s+(\d+)", out)
        return int(mm.group(1)) if mm else 0

    active = pages("Pages active")
    wired = pages("Pages wired down")
    comp = pages("Pages occupied by compressor")

    if _memsize <= 0:                 # la RAM total mai no canvia: un sol cop
        try:
            _memsize = int(_run(["sysctl", "-n", "hw.memsize"]).strip() or 0)
        except ValueError:
            _memsize = 0
    total_b = _memsize
    if total_b <= 0:
        return 0.0
    used = (active + wired + comp) * page
    return max(0.0, min(100.0, used * 100.0 / total_b))


def disk_percent():
    """% de disc usat a '/' (refrescat cada 30 s: canvia molt a poc a poc)."""
    global _disk_c
    now = time.time()
    if now - _disk_c[0] < 30.0:
        return _disk_c[1]
    val = 0.0
    out = _run(["df", "-k", "/"])
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    if len(lines) >= 2:
        for part in lines[-1].split():
            if part.endswith("%"):
                try:
                    val = float(part[:-1])
                except ValueError:
                    val = 0.0
                break
    _disk_c = (now, val)
    return val


def battery():
    """(percentatge, carregant) o (None, -1) si no hi ha bateria.

    Refrescat cada 10 s: el % canvia com a molt 1 cada molts segons.
    """
    global _bat_c
    now = time.time()
    if now - _bat_c[0] < 10.0:
        return _bat_c[1]
    out = _run(["pmset", "-g", "batt"])
    m = re.search(r"(\d+)%", out)
    if not m:
        _bat_c = (now, (None, -1))
        return (None, -1)
    pct = float(m.group(1))
    chg = 1 if re.search(r"\bcharging\b|\bcharged\b|finishing charge", out) else 0
    _bat_c = (now, (pct, chg))
    return (pct, chg)


def uptime_seconds():
    """Segons des de l'arrencada. Pregunta 'sysctl' un sol cop i despres calcula."""
    global _boot_epoch
    if _boot_epoch is None:
        out = _run(["sysctl", "-n", "kern.boottime"])
        m = re.search(r"sec = (\d+)", out)
        if not m:
            return 0
        _boot_epoch = int(m.group(1))
    return max(0, int(time.time() - _boot_epoch))


def hostname():
    """Nom del Mac: com que mai no canvia, es pregunta un sol cop."""
    global _hostname_c
    if _hostname_c:
        return _hostname_c
    out = _run(["scutil", "--get", "ComputerName"]).strip()
    if not out:
        out = socket.gethostname()
    _hostname_c = re.sub(r"\s+", "_", out)
    return _hostname_c


def mac_dark_mode():
    """El Mac te l'aparenca fosca? Ho diu AppleInterfaceStyle.

    Amb l'aparenca clara la clau no existeix i 'defaults' peta: aleshores la
    sortida es buida i ho interpretem com a clar. Refrescat cada 10 s.
    """
    global _dark_c
    now = time.time()
    if now - _dark_c[0] < 10.0:
        return _dark_c[1]
    out = _run(["defaults", "read", "-g", "AppleInterfaceStyle"]).strip()
    val = 1 if out.lower() == "dark" else 0
    _dark_c = (now, val)
    return val


THEMES = ["Fosc", "Clar", "Neo", "Grafite", "Pastel", "HUD"]


def theme_name(i):
    """Nom del tema (per als registres)."""
    return THEMES[i] if 0 <= i < len(THEMES) else str(i)


def running_apps():
    """Apps amb finestra oberta (per al launcher de la pantalla)."""
    out = _run(["osascript", "-e",
                'tell application "System Events" to get name of every '
                'process whose background only is false'], timeout=4.0)
    apps = [a.strip() for a in out.replace("\n", ",").split(",") if a.strip()]
    return apps[:15]


# --- Icona de la placa per a cada app del Mac ------------------------------
# El launcher ensenya les apps obertes amb la seva icona. La placa no sap res
# de les apps del Mac, aixi que la correspondencia es fa aqui. Si una app no
# hi es a la llista, es prova de trobar una icona que es digui igual.
APP_ICONS = {
    "finder": "finder",
    "safari": "safari",
    "google chrome": "chrome",
    "chromium": "chrome",
    "microsoft edge": "chrome",
    "firefox": "firefox",
    "brave browser": "brave",
    "terminal": "terminal",
    "iterm2": "terminal",
    "visual studio code": "vscode",
    "code": "vscode",
    "xcode": "vscode",
    "notes": "notes",
    "calendar": "calendar",
    "mail": "mail",
    "messages": "messages",
    "music": "music",
    "photos": "photos",
    "preview": "preview",
    "quicktime player": "quicktime",
    "reminders": "reminders",
    "system settings": "system_settings",
    "system preferences": "system_settings",
    "app store": "app_store",
    "activity monitor": "activity_monitor",
    "time machine": "time_machine",
    "console": "console",
    "slack": "slack",
    "spotify": "spotify",
    "zoom": "zoom",
    "zoom.us": "zoom",
    "microsoft teams": "teams",
    "microsoft outlook": "outlook",
    "microsoft word": "word",
    "microsoft excel": "excel",
    "microsoft powerpoint": "powerpoint",
    "microsoft onenote": "onenote",
    "onenote": "onenote",
    "notion": "notion",
    "figma": "figma",
    "adobe photoshop": "photoshop",
    "adobe illustrator": "illustrator",
    "adobe indesign": "indesign",
    "adobe premiere pro": "premiere_pro",
    "davinci resolve": "davinci_resolve",
    "blender": "blender",
    "textedit": "textedit",
    "dropbox": "dropbox",
    "google drive": "google_drive",
    "coreldraw": "coreldraw",
    "corel photopaint": "corel_photopaint",
}


def _clau(nom):
    """Nom comparables: sense espais, accents ni puntuacio."""
    return re.sub(r"[^a-z0-9]", "", (nom or "").lower())


def app_icon(nom):
    """Nom de la icona de la placa que li toca a una app del Mac ("" = cap)."""
    n = (nom or "").strip()
    if not n:
        return ""
    icon = APP_ICONS.get(n.lower())
    if icon:
        return icon
    # Segona passada: comparacio sense espais ni puntuacio ("Zoom.us" = "zoom").
    k = _clau(n)
    for app, ic in APP_ICONS.items():
        if _clau(app) == k:
            return ic
    # Tercera: alguna icona de la placa es diu igual que l'app?
    for ic in list_icons():
        if _clau(ic) == k:
            return ic
    return ""


# --- Icones REALS de les apps del Mac --------------------------------------
# En lloc de dependre d'una taula fixa, llegim la icona de debo de cada .app
# instal·lada: aixi qualsevol app surt amb la seva icona (no nomes les que
# coneixiem d'antic). APP_ICONS queda com a xarxa de seguretat per a les apps
# que no sapiguem resoldre.
#
# D'on surt la icona:
#   1. <App>.app/Contents/Resources/<CFBundleIconFile>.icns (Pillow la llegeix)
#   2. Si no hi ha .icns (apps recents amb Assets.car, com Calendari):
#      NSWorkspace.iconForFile via PyObjC. Es opcional: si PyObjC no hi es,
#      aquella app simplement surt sense icona (degradacio elegant).

APP_DIRS = (
    "/Applications",
    "/System/Applications",
    "/System/Applications/Utilities",
    "/System/Library/CoreServices",          # Finder
    os.path.expanduser("~/Applications"),
)

ICON_CACHE_DIR = os.path.expanduser("~/Library/Caches/MacPanel")
APP_INDEX_JSON = os.path.join(ICON_CACHE_DIR, "apps.json")

# Cache inversa {nom_icona: bundle}: es fa quan cal i es buida cada cop que
# l'index d'apps es refresca (aixi no queda mai desincronitzada).
_icona_a_bundle = None

# Limit d'icones d'app a la placa. Cada .bin son 2 KB i la SD en te de sobres,
# pero no val la pena tenir-hi apps que no s'obren mai: amb LRU, les que no
# s'usen cauen.
APP_ICON_MAX = 48

_APP_INDEX_TTL = 300.0        # tornar a mirar les carpetes cada 5 min
_app_index = None             # {bundle_id: {"path","name","icns","mtime"}}
_app_index_t = 0.0

# El Bridge hi enganxa el seu log() perque els errors d'aqui tambe es vegin al
# panell (en comptes d'empassar-los).
_error_sink = None


def _error(msg):
    """Registra un error (mai s'empassa en silenci)."""
    if _error_sink is not None:
        try:
            _error_sink(msg)
            return
        except Exception:
            pass
    print("[MacPanel] " + str(msg), file=sys.stderr)


def _llegeix_info(app_path):
    """(bundle_id, nom, ruta_icns, mtime) d'un .app, o None si no te bundle id."""
    pl = os.path.join(app_path, "Contents", "Info.plist")
    try:
        with open(pl, "rb") as fh:
            info = plistlib.load(fh)
    except Exception as exc:
        _error(f"Info.plist il·legible a '{app_path}': {exc}")
        return None

    bundle = str(info.get("CFBundleIdentifier", "") or "").strip()
    if not bundle:
        return None
    nom = (info.get("CFBundleDisplayName") or info.get("CFBundleName")
           or os.path.splitext(os.path.basename(app_path))[0])

    # Icona .icns (la que sap llegir Pillow). Si no hi es, el nom de la icona
    # queda buit i ja ho resoldra NSWorkspace (Assets.car).
    icns = ""
    icon_file = str(info.get("CFBundleIconFile", "") or "")
    if icon_file:
        f = icon_file if icon_file.lower().endswith(".icns") else icon_file + ".icns"
        cand = os.path.join(app_path, "Contents", "Resources", f)
        if os.path.isfile(cand):
            icns = cand
    if not icns:
        icon_name = str(info.get("CFBundleIconName", "") or "")
        if icon_name:
            cand = os.path.join(app_path, "Contents", "Resources",
                                icon_name + ".icns")
            if os.path.isfile(cand):
                icns = cand

    try:
        mtime = int(os.path.getmtime(app_path))
    except OSError:
        mtime = 0

    # Una app "de debò" es la que surt al Dock o es pot activar. Els agents de
    # fons (LSUIElement / LSBackgroundOnly) son ajudants invisibles que l'usuari
    # no veu enlloc: no tenen cap sentit com a boto de la pantalla.
    visible = not (info.get("LSUIElement") or info.get("LSBackgroundOnly"))
    return (bundle, str(nom), icns, mtime, bool(visible))


def app_index(force=False):
    """{bundle_id: fitxa} de les apps instal·lades.

    Es fa un sol cop cada 5 minuts i es guarda a memoria (i a disc): recorre 5
    carpetes i llegeix ~150 Info.plist, i aixo no es pot fer a cada crida.
    """
    global _app_index, _app_index_t
    ara = time.time()
    if _app_index is not None and not force and (ara - _app_index_t) < _APP_INDEX_TTL:
        return _app_index

    idx = {}
    for d in APP_DIRS:
        try:
            noms = os.listdir(d)
        except OSError:
            continue                       # carpeta que no hi es: cap problema
        for n in noms:
            if not n.endswith(".app"):
                continue
            p = os.path.join(d, n)
            info = _llegeix_info(p)
            if info is None:
                continue
            bundle, nom, icns, mtime, visible = info
            idx.setdefault(bundle, {"path": p, "name": nom, "icns": icns,
                                    "mtime": mtime, "visible": visible})

    if idx:
        _app_index = idx
        _app_index_t = ara
        global _icona_a_bundle
        _icona_a_bundle = None            # l'index ha canviat: la cache inversa ja no val
        try:
            os.makedirs(ICON_CACHE_DIR, exist_ok=True)
            with open(APP_INDEX_JSON, "w", encoding="utf-8") as fh:
                json.dump(idx, fh, ensure_ascii=False)
        except Exception as exc:
            _error(f"no s'ha pogut desar l'index d'apps: {exc}")
    else:
        _error("l'index d'apps ha sortit buit (cap carpeta llegible)")
    return _app_index or {}


def bundle_for_name(nom):
    """Bundle id d'una app pel seu nom (el nom de System Events sol coincidir
    amb el CFBundleDisplayName). Retorna "" si no la trobem."""
    if not nom:
        return ""
    k = _clau(nom)
    idx = app_index()
    for bundle, info in idx.items():
        if _clau(info["name"]) == k:
            return bundle
    # Segona passada: el nom del fitxer .app (a vegades el display name difereix)
    for bundle, info in idx.items():
        base = os.path.splitext(os.path.basename(info["path"]))[0]
        if _clau(base) == k:
            return bundle
    return ""


def _png_icns(ruta):
    """PNG (>=128 px) de la icona d'un .icns, o None."""
    if Image is None:
        _error("cal Pillow per extreure les icones de les apps "
               "(python3 -m pip install Pillow)")
        return None
    try:
        im = Image.open(ruta)
        im.load()
    except Exception as exc:
        _error(f"no s'ha pogut llegir l'icns '{ruta}': {exc}")
        return None
    im = im.convert("RGBA")
    if max(im.size) > 128:                 # sempre reduim, mai ampliem
        im = im.resize((128, 128), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _png_nsworkspace(app_path):
    """PNG de la icona d'una app via NSWorkspace (per a les que no tenen .icns:
    son les que porten la icona dins d'Assets.car).

    PyObjC es opcional: si no hi es, es retorna None i l'app surt sense icona
    (degradacio elegant, sense petar).
    """
    try:
        import AppKit
    except ImportError:
        return None
    try:
        img = AppKit.NSWorkspace.sharedWorkspace().iconForFile_(app_path)
        if img is None:
            return None
        tiff = img.TIFFRepresentation()
        if tiff is None:
            return None
        rep = AppKit.NSBitmapImageRep.imageRepWithData_(tiff)
        if rep is None:
            return None
        data = rep.representationUsingType_properties_(
            AppKit.NSBitmapImageFileTypePNG, {})
        return bytes(data) if data else None
    except Exception as exc:
        _error(f"NSWorkspace ha fallat amb '{app_path}': {exc}")
        return None


def _png_icona_app(app_path, icns):
    """PNG de la icona d'una app: primer l'.icns, i si no, NSWorkspace."""
    if icns:
        png = _png_icns(icns)
        if png:
            return png
    return _png_nsworkspace(app_path)


def icona_app_png(bundle, info):
    """PNG de la icona d'una app, amb cau a ~/Library/Caches/MacPanel.

    La cau es valida amb el mtime del .app: si l'app s'ha actualitzat, es
    torna a extreure. Retorna None si no se n'ha pogut treure cap.
    """
    nom = nom_icona_app(bundle)
    if not nom:
        return None
    try:
        os.makedirs(ICON_CACHE_DIR, exist_ok=True)
    except Exception as exc:
        _error(f"no s'ha pogut crear la cau '{ICON_CACHE_DIR}': {exc}")
        return None

    dst = os.path.join(ICON_CACHE_DIR, nom + ".png")
    stamp = os.path.join(ICON_CACHE_DIR, nom + ".stamp")
    mtime = str(info.get("mtime", 0))
    try:
        with open(stamp, "r", encoding="utf-8") as fh:
            if fh.read().strip() == mtime and os.path.isfile(dst):
                with open(dst, "rb") as fh:
                    return fh.read()
    except OSError:
        pass

    png = _png_icona_app(info["path"], info.get("icns", ""))
    if not png:
        return None
    try:
        with open(dst, "wb") as fh:
            fh.write(png)
        with open(stamp, "w", encoding="utf-8") as fh:
            fh.write(mtime)
    except Exception as exc:
        _error(f"no s'ha pogut desar la icona de '{bundle}': {exc}")
    return png


def app_icon_name(bundle, nom):
    """Nom de la icona de la placa que li toca a una app ("" = cap).

    El resolutor NOU: si l'app es a l'index, la seva icona es la REAL (extreta
    del .app del Mac). Pero si per aquella app ja teniem una icona curada a la
    taula, es reutilitza: es la mateixa app, ja es a la placa i aixi no hi pugem
    una segona copia identica. Les apps que NO son a la taula (la majoria!) son
    les que guanyen icona amb aixo.

    Si l'app no es a l'index (no la trobem enlloc), es cau a la taula de sempre.
    """
    if bundle:
        info = app_index().get(bundle)
        if info is not None:
            curt = app_icon(info["name"])
            if curt:
                return curt
            ic = nom_icona_app(bundle)
            if ic:
                return ic
    return app_icon(nom)


def _mapa_icones():
    """{nom_icona: bundle} de les apps instal·lades.

    Serveix per saber de quina app es una icona pel seu nom (el panell les
    demana per nom, i encara no les hem extretes totes). Es recalcula quan
    l'index d'apps es refresca.
    """
    global _icona_a_bundle
    if _icona_a_bundle is None:
        _icona_a_bundle = {}
        for bundle in app_index():
            n = nom_icona_app(bundle)
            if n:
                _icona_a_bundle.setdefault(n, bundle)
    return _icona_a_bundle


def extreu_icona(nom):
    """Assegura que el PNG d'una icona d'app existeixi al disc.

    El panell mostra les ~70 apps instal·lades amb la seva icona: extreure-les
    TOTES d'entrada seria molt lent (descomprimir icns, NSWorkspace...). En
    canvi, quan el navegador demana '/icons/<nom>.png' i el fitxer no hi es, el
    traiem en aquell moment: es rapid i nomes es fa per les que es veuen.
    """
    if not nom or Image is None:
        return False
    desti = os.path.join(icons_dir(), nom + ".png")
    if os.path.isfile(desti):
        return True
    bundle = _mapa_icones().get(nom)
    if not bundle:
        return False
    info = app_index().get(bundle)
    if info is None:
        return False
    png = icona_app_png(bundle, info)
    if not png:
        return False
    try:
        with open(desti, "wb") as fh:
            fh.write(png)
        return True
    except OSError as exc:
        _error(f"no s'ha pogut desar la icona '{nom}': {exc}")
        return False


def apps_instalades():
    """Llista d'apps instal·lades per al panell web: nom, bundle i icona.

    Nomes les apps "de debò" (les que surten al Dock i es poden obrir): els
    agents de fons no es poden ni activar, aixi que no tenen cap sentit com a
    boto de la pantalla.
    """
    out = []
    for bundle, info in sorted(app_index().items(),
                               key=lambda kv: kv[1]["name"].lower()):
        if not info.get("visible", True):
            continue
        out.append({"bundle": bundle,
                    "name": info["name"],
                    "icon": nom_icona_app(bundle)})
    return out


# --- Politica LRU de les icones d'app a la placa ---------------------------
# La placa no ens pot dir quines icones hi te (no hi ha ordre per llistar-les),
# aixi que ho portem nosaltres: un JSON amb el nom de cada icona d'app pujada i
# quan s'ha usat per ultim cop. Quan se supera APP_ICON_MAX, les que fa mes
# temps que no es toquen s'esborren de la placa (ICONDEL).

APP_LRU_JSON = os.path.join(ICON_CACHE_DIR, "icons_lru.json")


def lru_load():
    """{nom_icona: instant de l'ultim us} de les icones d'app pujades."""
    try:
        with open(APP_LRU_JSON, "r", encoding="utf-8") as fh:
            d = json.load(fh)
    except OSError:
        return {}
    except ValueError as exc:
        _error(f"la LRU d'icones esta feta malbé: {exc}")
        return {}
    if not isinstance(d, dict):
        return {}
    out = {}
    for k, v in d.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def lru_save(d):
    try:
        os.makedirs(ICON_CACHE_DIR, exist_ok=True)
        with open(APP_LRU_JSON, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
    except Exception as exc:
        _error(f"no s'ha pogut desar la LRU d'icones: {exc}")


def launcher_line(apps):
    """Linia 'L nom=icona|nom=icona' amb les apps obertes i la seva icona.

    Les apps sense icona van sense el '=' (la placa els posa el nom i prou).
    La icona surt de la icona REAL de l'app al Mac (pel bundle id); si no la
    sabem resoldre, es cau a la taula de sempre.
    """
    parts = []
    for a in apps:
        nom = re.sub(r"[|=]", " ", a).strip()
        if not nom:
            continue
        ic = app_icon_name(bundle_for_name(nom), nom)
        parts.append("%s=%s" % (nom, ic) if ic else nom)
    return "L " + "|".join(parts)


# --- Pestanyes dels navegadors ---------------------------------------------
# Les pantalles de tipus "tabs" mostren les PESTANYES obertes del navegador que
# esta al davant, com a botons amb el seu favicon. En tocar-ne una, la placa
# envia 'C tab:N' (N, 0-based) i el Mac posa aquella pestanya al davant.
#
# El Mac envia la llista amb una linia global (una per a tota la placa):
#   T Titol1=favicon1|Titol2=favicon2|...
# El titol va netejat (sense '|' ni '=') perque no es confongui amb els
# separadors. Les pestanyes sense favicon a la SD van nomes amb el titol.

# Navegadors que sabem llegir: nom d'AppleScript -> com es diu la propietat del
# titol. (Safari fa servir 'name'; Chrome/Edge/Brave fan servir 'title'.)
BROWSERS = {
    "Safari": "name",
    "Google Chrome": "title",
    "Google Chrome Dev": "title",
    "Google Chrome Canary": "title",
    "Microsoft Edge": "title",
    "Microsoft Edge Beta": "title",
    "Brave Browser": "title",
    "Chromium": "title",
    "Vivaldi": "title",
    "Opera": "title",
}


def osa(script, timeout=3.0):
    """Executa un tros d'AppleScript i torna la sortida (o '' si falla)."""
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def browser_running():
    """Nom d'AppleScript del primer navegador obert que sabem llegir (o '')."""
    out = osa('tell application "System Events" to get name of every '
              'process whose background only is false', timeout=4.0)
    oberts = {a.strip() for a in out.replace("\n", ",").split(",") if a.strip()}
    for nom in BROWSERS:
        if nom in oberts:
            return nom
    return ""


def _domini_net(url):
    """Domini d'una URL, curt i llegible (per si hem de mostrar-lo)."""
    try:
        from urllib.parse import urlparse
        h = urlparse(url).netloc or url
        return re.sub(r"^www\.", "", h).split(":")[0] or url
    except Exception:
        return url


def browser_tabs(navegador, maxim=15):
    """Llista de (titol, url) de les pestanyes obertes del navegador.

    Llegeix titols i URLs per separat i els emparella. La llista de URLs sempre
    te exactament un element per pestanya (les URLs no porten ', '). Els titols
    tambe venen separats per ', ', pero aixo es feble: un titol pot contenir una
    coma (sobre tot a Chrome). Per no desalliniar cap titol amb la seva URL,
    nomes confiem en els titols si en tenim EXACTAMENT tants com URLs; si no,
    mostrem el domini de cada URL (clar i curt) com a titol.
    """
    prop = BROWSERS.get(navegador, "title")
    titols = osa(f'tell application "{navegador}" to get {prop} of tabs of '
                 f'front window', timeout=3.0)
    urls = osa(f'tell application "{navegador}" to get URL of tabs of front '
               f'window', timeout=3.0)
    if not urls:
        return []
    ll_t = [t.strip() for t in titols.split(", ")] if titols else []
    ll_u = [u.strip() for u in urls.split(", ")]
    # Nomes ens refiem dels titols si quadren exactament amb les URLs.
    titols_fiables = (len(ll_t) == len(ll_u))
    tabs = []
    for i, u in enumerate(ll_u):
        t = ll_t[i] if (titols_fiables and ll_t[i]) else _domini_net(u)
        tabs.append((t, u))
        if len(tabs) >= maxim:
            break
    return tabs


def activate_tab(navegador, index):
    """Porta al davant la pestanya 'index' (1-based) del navegador."""
    nav = navegador or browser_running()
    if not nav:
        return False
    if nav == "Safari":
        # A Safari s'ha de triar la pestanya concreta amb 'current tab'.
        osa(f'tell application "{nav}" to set current tab of front window to '
            f'tab {index} of front window', timeout=3.0)
    else:
        # Chrome i la resta: per index (1-based).
        osa(f'tell application "{nav}" to set active tab index of front window '
            f'to {index}', timeout=3.0)
    osa(f'tell application "{nav}" to activate', timeout=3.0)
    return True


# --- Favorits dels navegadors (pantalles "favs") ---------------------------
# Els favorits son FITXERS AL DISC, no cal AppleScript: es poden llegir sempre,
# encara que el navegador estigui tancat (que es just el que vols en una pagina
# de favorits: tenir-los a ma sense obrir res).
#
# El Mac envia la llista amb una linia global, com les pestanyes:
#   F Titol1=favicon1|Titol2=favicon2|...
# En tocar-ne un, la placa envia 'C fav:N' (N, 0-based) i el Mac obre la URL.
#
# Suportem els tres formats que hi ha al mercat:
#   - Safari i WebKit          -> Bookmarks.plist (plist binari d'Apple)
#   - Chrome i familia Chromium -> <perfil>/Bookmarks (JSON)
#   - Firefox                  -> places.sqlite (SQLite)

FAV_MAX_BOOKMARKS = 15      # els que caben a la placa (MAX_FAVS del firmware)

# Familia Chromium: nom llegible -> carpeta dins ~/Library/Application Support.
# Mirem tots els perfils del navegador i ens quedem amb el que te els favorits
# mes recents ('Default' i 'Profile N').
CHROMIUM_BOOKMARKS = [
    ("Chrome",        "Google/Chrome"),
    ("Chrome Beta",   "Google/Chrome Beta"),
    ("Chrome Dev",    "Google/Chrome Dev"),
    ("Chrome Canary", "Google/Chrome Canary"),
    ("Chromium",      "Chromium"),
    ("Brave",         "BraveSoftware/Brave-Browser"),
    ("Edge",          "Microsoft Edge"),
    ("Vivaldi",       "Vivaldi"),
]

# Nom d'AppleScript del navegador -> clau de la taula de dalt. Serveix per
# posar els favorits del navegador que tens al davant els primers de la llista.
NAV_A_FAV = {
    "Safari": "Safari",
    "Google Chrome": "Chrome",
    "Google Chrome Beta": "Chrome Beta",
    "Google Chrome Dev": "Chrome Dev",
    "Google Chrome Canary": "Chrome Canary",
    "Chromium": "Chromium",
    "Brave Browser": "Brave",
    "Microsoft Edge": "Edge",
    "Vivaldi": "Vivaldi",
}

# Safari ve de fabrica amb aquests favorits a la barra. Si no els traguessim,
# omplirien la pagina sencera (i a mes hi son duplicats: la versio '.es' i la
# '.com'). Son sempre els mateixos a qualsevol Mac, aixi que els saltem: el que
# queda a la barra es el que l'usuari hi ha posat de debo.
SAFARI_DE_FABRICA = {
    "http://www.apple.com/es/", "http://es.yahoo.com/",
    "http://maps.google.es/", "http://es.youtube.com/",
    "http://www.apple.com/", "http://www.yahoo.com/",
    "http://maps.google.com/", "http://www.youtube.com/",
    "http://es.wikipedia.org/", "http://www.wikipedia.org/",
}


def _mtime(fitxer):
    """Data de modificacio d'un fitxer (0.0 si no existeix)."""
    try:
        return os.path.getmtime(fitxer)
    except OSError:
        return 0.0


def _troba_barra(node, fons=0):
    """Node de la barra de favorits dins l'arbre de Bookmarks.plist."""
    for c in node.get("Children", []):
        if c.get("Title") in ("BookmarksBar", "Favorites", "Favorits"):
            return c
        if fons < 3:
            r = _troba_barra(c, fons + 1)
            if r is not None:
                return r
    return None


def _fulles_plist(node, fons, carpetes, maxim):
    """(titol, url) de les fulles d'un node de Bookmarks.plist, en ordre.

    El titol d'un favorit de Safari es a URIDictionary.title; 'Title' nomes el
    fan servir les carpetes (les fulles el tenen buit).
    """
    out = []
    for c in node.get("Children", []):
        if len(out) >= maxim:
            break
        url = (c.get("URLString") or "").strip()
        if url:
            if url in SAFARI_DE_FABRICA:
                continue
            titol = ((c.get("URIDictionary") or {}).get("title")
                     or c.get("Title") or "").strip()
            out.append((titol, url))
        elif carpetes and fons < 2:
            out.extend(_fulles_plist(c, fons + 1, carpetes, maxim - len(out)))
    return out


def _favorits_safari(carpetes=False, maxim=FAV_MAX_BOOKMARKS):
    """Favorits de la barra de Safari, en l'ordre que els te l'usuari."""
    from pathlib import Path
    for p in (Path.home() / "Library/Safari/Bookmarks.plist",
              Path.home() / "Library/Containers/com.apple.Safari/Data/"
                            "Library/Safari/Bookmarks.plist"):
        try:
            if not p.is_file():
                continue
            arrel = plistlib.loads(p.read_bytes())
        except Exception:
            continue
        barra = _troba_barra(arrel)
        if barra is not None:
            return _fulles_plist(barra, 0, carpetes, maxim)
    return []


def _fulles_json(node, fons, carpetes, maxim):
    """(titol, url) de les fulles d'un node de 'Bookmarks' de Chromium."""
    out = []
    for c in node.get("children", []):
        if len(out) >= maxim:
            break
        if c.get("type") == "url" and c.get("url"):
            out.append(((c.get("name") or "").strip(), c["url"].strip()))
        elif carpetes and c.get("children") and fons < 2:
            out.extend(_fulles_json(c, fons + 1, carpetes, maxim - len(out)))
    return out


def _favorits_chromium(carpeta, carpetes=False, maxim=FAV_MAX_BOOKMARKS):
    """Favorits de la barra d'un navegador de la familia Chromium."""
    from pathlib import Path
    if not carpeta:
        return []
    base = Path.home() / "Library/Application Support" / carpeta
    if not base.is_dir():
        return []
    perfils = []
    try:
        for f in base.iterdir():
            if f.is_dir() and (f.name == "Default" or f.name.startswith("Profile")):
                perfils.append(f)
    except Exception:
        return []
    # El perfil que s'ha fet servir mes recentment es el que ens interessa.
    perfils.sort(key=lambda p: -_mtime(p / "Bookmarks"))
    for perfil in perfils:
        fitxer = perfil / "Bookmarks"
        try:
            if not fitxer.is_file():
                continue
            dades = json.loads(fitxer.read_text(encoding="utf-8",
                                                errors="replace"))
        except Exception:
            continue
        out = _fulles_json(((dades.get("roots") or {}).get("bookmark_bar") or {}),
                           0, carpetes, maxim)
        if out:
            return out
    return []


def _favorits_firefox(maxim=FAV_MAX_BOOKMARKS):
    """Favorits de la barra de Firefox (places.sqlite).

    Firefox te la base de dades oberta i bloquejada mentre corre, aixi que en
    fem una copia a un fitxer temporal i llegim la copia. Si no hi ha Firefox
    (o falla), es torna una llista buida i la resta de navegadors segueixen.
    """
    import shutil
    import sqlite3
    import tempfile
    from pathlib import Path
    arrel = Path.home() / "Library/Application Support/Firefox/Profiles"
    if not arrel.is_dir():
        return []
    for places in sorted(arrel.glob("*/places.sqlite"), key=lambda p: -_mtime(p)):
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
                tmp = f.name
            shutil.copyfile(places, tmp)
            con = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True, timeout=3.0)
            files = con.execute(
                "SELECT b.title, p.url FROM moz_bookmarks b "
                "JOIN moz_places p ON p.id = b.fk "
                "WHERE b.type = 1 AND p.url LIKE 'http%' "
                "AND b.parent = (SELECT id FROM moz_bookmarks "
                "                WHERE guid = 'toolbar_____') "
                "ORDER BY b.position").fetchall()
            con.close()
            out = [((t or "").strip(), u.strip()) for t, u in files if u]
            if out:
                return out[:maxim]
        except Exception:
            continue
        finally:
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
    return []


def bookmarks(navegador="", maxim=FAV_MAX_BOOKMARKS, carpetes=False):
    """Favorits de tots els navegadors: [(titol, url, navegador)].

    Els favorits del navegador que te el focus van primers (son els que acabes
    de fer servir); la resta segueixen un ordre fix. Dins de cada navegador es
    respecta l'ordre de la seva barra. Es treuen els repetits exactes (mateixa
    URL) perque la pagina no surti amb el mateix lloc dues vegades.
    """
    ordre = ["Safari"] + [n for n, _ in CHROMIUM_BOOKMARKS] + ["Firefox"]
    clau = NAV_A_FAV.get(navegador, "")
    if clau in ordre:
        ordre.remove(clau)
        ordre.insert(0, clau)

    carpetes_chromium = dict(CHROMIUM_BOOKMARKS)
    out, vistos = [], set()
    for nom in ordre:
        try:
            if nom == "Safari":
                ll = _favorits_safari(carpetes, maxim)
            elif nom == "Firefox":
                ll = _favorits_firefox(maxim)
            else:
                ll = _favorits_chromium(carpetes_chromium.get(nom, ""),
                                        carpetes, maxim)
        except Exception:
            ll = []
        for titol, url in ll:
            if url in vistos:
                continue
            vistos.add(url)
            out.append((titol, url, nom))
            if len(out) >= maxim:
                return out
    return out


def favs_line(favs, favicons_ok):
    """Linia 'B Titol=favicon|...' amb els favorits i els seus favicons.

    La lletra es 'B' (bookmarks) perque la 'F' ja es la previsio del temps. Si
    un favorit no te titol (passa en algunes barres importades) es mostra el
    domini, que sempre es mes util que una casella buida.
    """
    parts = []
    for titol, url, _nav in favs:
        nom = re.sub(r"[|=]", " ", titol or "").strip()[:27]
        if not nom:
            nom = _domini_net(url)[:27]
        ic = favicon_icon(url)
        if ic and ic in favicons_ok:
            parts.append(f"{nom}={ic}")
        else:
            parts.append(nom)
    return "B " + "|".join(parts)


# --- Favicons: cada pestanya porta el favicon del seu lloc web -------------
# El favicon es descarrega (Google s2, 64 px), es converteix a .bin com qualsevol
# icona i es puja a la SD. Es guarden en una memoria curta per no descarregar
# ni pujar el mateix favicon cada cop. El nom de la icona surt del DOMINI de la
# URL: aixi totes les pestanyes d'un mateix lloc comparteixen favicon (i el nom
# es estable: 'account.ultimaker.com' -> 'accountultimakercom').
FAV_CACHE = {}        # domini -> nom d'icona (o "" si no s'ha pogut)
FAV_MAX = 40          # maxim de favicons diferents (la SD es petita)


def favicon_icon(url):
    """Nom de la icona (favicon) d'una URL, o "" si no se'n pot treure."""
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).netloc or urlparse(url).path.split("/")[0]).lower()
        if not host:
            return ""
        host = host.split(":")[0]            # treu el port
    except Exception:
        return ""
    if not host or host in ("127.0.0.1", "localhost"):
        return ""                            # les locals no tenen favicon util
    if host not in FAV_CACHE:
        FAV_CACHE[host] = clean_icon_name(host.replace(".", ""))[:19]
    return FAV_CACHE[host]


# Mida a la qual es demana el favicon a Google s2. Es la MATEIXA que ICON_PX:
# si es demanes mes gran, Google l'ampliaria ell (i quedaria borros) i despres
# l'hauriem de tornar a reduir nosaltres. A 32 va 1:1 amb la placa.
FAVICON_PX = 32

# I la mida "de treball": demanem la icona mes gran que sapigueu donar i deixem
# que png2bin la redueixi. Reduir nosaltres amb LANCZOS dona mes detall que la
# reduccio que fa Google pel seu compte (es nota molt a Google, Apple, Spotify
# o Wikipedia, que tenen icones de 128 px o mes).
FAVICON_BAIXA = 128


def _mida_png(data):
    """Amplada del PNG (llegeix la capcalera IHDR). 0 si no es pot saber."""
    try:
        if len(data) >= 24 and data[12:16] == b"IHDR":
            return int.from_bytes(data[16:20], "big")
    except Exception:
        pass
    return 0


def _urls_favicon(url):
    """URLs on provar el favicon, en ordre: la de debo i, si falla, el domini pare.

    Alguns llocs amb subdomini (p.ex. es.yahoo.com) no tenen favicon propi a
    Google s2, pero el domini pare (yahoo.com) si. El nom de la icona segueix
    sortint del host original, aixi que cada adreça te la seva entrada.
    """
    yield url
    try:
        host = (urllib.parse.urlparse(url).netloc or "").split(":")[0]
        parts = host.split(".")
        if len(parts) > 2:
            yield "https://" + ".".join(parts[-2:]) + "/"
    except Exception:
        pass


def _descarrega_favicon(url, px):
    """Bytes PNG del favicon d'una URL (Google s2) o None si no n'hi ha.

    Fa servir 'curl' en comptes d'urllib: alguns Python (p.ex. el de
    miniforge) no tenen els certificats SSL del sistema i urllib falla, mentre
    que curl (que va amb els certificats de macOS) va be.
    """
    try:
        q = urllib.parse.quote(url, safe="")
        url_api = f"https://www.google.com/s2/favicons?sz={px}&domain_url={q}"
        r = subprocess.run(["curl", "-sL", "--max-time", "6",
                            "-A", "Mozilla/5.0", url_api],
                           capture_output=True, timeout=8.0)
        data = r.stdout
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return data
    except Exception:
        pass
    return None


def favicon_png(url, px=FAVICON_PX):
    """Bytes PNG del favicon d'una URL, provant tambe el domini pare.

    Es demana la icona a FAVICON_BAIXA (mes gran que la final) perque reduir-la
    nosaltres amb LANCZOS dona mes detall. Pero alguns llocs nomes tenen una
    icona de 16 px: llavors Google, a la mida gran, torna el fitxer petit de
    debo (i l'hauriem d'ampliar nosaltres, que queda pitjor). En aquest cas es
    torna a demanar a la mida final, que Google ja torna ampliada.
    """
    for u in _urls_favicon(url):
        data = _descarrega_favicon(u, FAVICON_BAIXA)
        if data is None:
            continue
        if _mida_png(data) >= px:
            return data
        alt = _descarrega_favicon(u, px)
        return alt or data
    return None


def clau_llista(items, icones_sd):
    """Clau per saber si una llista (pestanyes o favorits) ha canviat.

    Inclou si el favicon de cada element ja es a la placa: aixi, quan en pugem
    un de nou, la linia es reenvia i la placa li pot posar la icona. Sense
    aixo, la pestanya es quedaria sense favicon fins que canviés la llista.
    """
    out = []
    for it in items:
        titol, url = it[0], it[1]
        ic = favicon_icon(url)
        out.append((titol, ic if ic in icones_sd else ""))
    return tuple(out)


def _icona_fluixa(nom):
    """La icona local existeix pero te menys pixels dels que volem?

    Serveix per repescar automaticament les icones que es van baixar quan
    demanavem els favicons mes petits: a la placa es veien borroses i no hi
    havia manera d'arreglar-les sense esborrar-les a ma.
    """
    try:
        from PIL import Image
        with Image.open(os.path.join(icons_dir(), nom + ".png")) as im:
            return min(im.size) < FAVICON_PX
    except Exception:
        return False


def tabs_line(tabs, favicons_ok):
    """Linia 'T Titol=favicon|...' amb les pestanyes i els seus favicons.

    'favicons_ok' es el conjunt de noms d'icona ja presents a la SD (nomes
    d'aquests posem el '='; la resta surten nomes amb el titol).
    """
    parts = []
    for titol, url in tabs:
        nom = re.sub(r"[|=]", " ", titol or "").strip()[:27] or "..."
        ic = favicon_icon(url)
        if ic and ic in favicons_ok:
            parts.append(f"{nom}={ic}")
        else:
            parts.append(nom)
    return "T " + "|".join(parts)


def next_event():

    """Proper esdeveniment de l'agenda del Mac (o ""). Pot trigar una mica."""
    script = ('tell application "Calendar"\n'
              'set n to current date\n'
              'repeat with c in calendars\n'
              'try\n'
              'set evs to (every event of c whose start date > n)\n'
              'if (count of evs) > 0 then return summary of item 1 of evs\n'
              'end try\n'
              'end repeat\n'
              'return ""\n'
              'end tell')
    out = _run(["osascript", "-e", script], timeout=8.0).strip()
    return out[:42]


# --- Notificacions del macOS -----------------------------------------------
# El Centre de Notificacions desa cada avis en una base de dades SQLite dins del
# contenidor de l'usuari. Cada fila de la taula 'record' porta un bplist amb
# l'aplicacio i el text (titol, subtitol i cos). Llegim les files noves (per
# rec_id) i les enviem a la pantalla com un baner, igual que fa el macOS.
NOTIF_DB_GLOB = "/private/var/folders/*/*/0/com.apple.notificationcenter/db2/db"

# Noms macos de les apps que mes surten. Si no hi es, traiem el nom del paquet.
NOTIF_APPS = {
    "com.apple.mail": "Correu",
    "com.apple.MobileSMS": "Missatges",
    "com.apple.mobilesms": "Missatges",
    "com.apple.ical": "Calendari",
    "com.apple.iCal": "Calendari",
    "com.apple.reminders": "Recordatoris",
    "com.apple.facetime": "FaceTime",
    "com.apple.Safari": "Safari",
    "com.apple.systempreferences": "Ajustos",
    "com.apple.systemsettings": "Ajustos",
    "com.apple.AppStore": "App Store",
    "com.apple.Music": "Musica",
    "com.apple.Photos": "Fotos",
    "com.apple.finder": "Finder",
    "com.apple.Terminal": "Terminal",
    "com.apple.ActivityMonitor": "Activitat",
    "com.apple.dt.Xcode": "Xcode",
    "com.apple.ScreenTimeNotifications": "Temps d'us",
    "com.apple.focus": "Concentracio",
    "com.apple.news": "Noticies",
    "com.tinyspeck.slackmacgap": "Slack",
    "com.microsoft.VSCode": "VS Code",
    "com.google.Chrome": "Chrome",
    "org.mozilla.firefox": "Firefox",
    "com.microsoft.Outlook": "Outlook",
    "com.microsoft.teams2": "Teams",
    "com.microsoft.teams": "Teams",
    "com.spotify.client": "Spotify",
    "com.hnc.Discord": "Discord",
    "net.whatsapp.WhatsApp": "WhatsApp",
    "com.google.Gmail": "Gmail",
    "com.apple.MobileSMS": "Missatges",
    "com.apple.Passbook": "Cartera",
    "com.apple.ScriptEditor2": "Editor de scripts",
    "com.apple.Shortcuts": "Dreceres",
    "com.apple.systemevents": "Sistema",
    "com.apple.Photos": "Fotos",
    "com.apple.Maps": "Mapes",
    "com.apple.Preview": "Previsualitzacio",
    "com.apple.TextEdit": "TextEdit",
    "com.apple.QuickTimePlayerX": "QuickTime",
    "com.apple.Terminal": "Terminal",
    "com.googlecode.iterm2": "iTerm",
    "com.jetbrains.intellij": "IntelliJ",
    "com.jetbrains.pycharm": "PyCharm",
    "com.sublimetext.4": "Sublime Text",
    "com.apple.dt.Xcode": "Xcode",
    "com.figma.Desktop": "Figma",
    "notion.id": "Notion",
    "com.tinyspeck.slackmacgap": "Slack",
}


def app_display_name(identifier):
    """Nom maco d'una app a partir del seu bundle id."""
    if not identifier:
        return "Mac"
    if identifier in NOTIF_APPS:
        return NOTIF_APPS[identifier]
    if identifier.startswith("_system_center_:"):   # avisos interns del sistema
        identifier = identifier.split(":", 1)[1]
    return identifier.split(".")[-1]


def notification_db():
    """Ruta de la base de dades del Centre de Notificacions (o None)."""
    import glob
    for p in glob.glob(NOTIF_DB_GLOB):
        if os.path.isfile(p):
            return p
    return None


def _clean_text(t):
    """Treiem salts de linia i espais rars dels textos de les notificacions."""
    if t is None:
        return ""
    t = str(t).replace("\n", " ").replace("\r", " ")
    t = t.replace("\u00a0", " ").replace("\u200b", "")
    return re.sub(r"\s+", " ", t).strip()


class NotifReader:
    """Llegeix les notificacions NOVES del Centre de Notificacions del macOS.

    La primera vegada nomes apunta l'ultima (per no enviar de cop tot l'historial)
    i a partir d'aqui va retornant les que van arribant.
    """

    def __init__(self):
        self.last_id = None
        self.history = deque(maxlen=25)
        self.error = None
        self.total = 0

    def poll(self):
        """Retorna la llista de notificacions noves des de l'ultima crida."""
        import sqlite3

        db = notification_db()
        if db is None:
            self.error = "no trobo el Centre de Notificacions"
            return []

        try:
            con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=1.5)
            rows = con.execute(
                "select r.rec_id, a.identifier, r.data "
                "from record r left join app a on a.app_id = r.app_id "
                "where r.presented = 1 order by r.rec_id desc limit 40"
            ).fetchall()
            con.close()
        except Exception as exc:
            self.error = str(exc)
            return []

        self.error = None
        if not rows:
            return []

        newest = rows[0][0]
        if self.last_id is None:        # primera lectura: no enviem res antic
            self.last_id = newest
            return []

        noves = []
        for rec_id, ident, data in reversed(rows):
            if rec_id <= self.last_id:
                continue
            n = self._parse(rec_id, ident, data)
            if n is not None:
                noves.append(n)

        self.last_id = max(self.last_id, newest)
        for n in noves:
            self.history.appendleft(n)
            self.total += 1
        return noves

    @staticmethod
    def _parse(rec_id, ident, data):
        """Converteix una fila de 'record' en un diccionari, o None si no val."""
        import plistlib

        if ident and ident.startswith("_system_center_:"):
            return None                       # avisos interns: no son per a nosaltres
        try:
            req = (plistlib.loads(data) or {}).get("req", {}) or {}
        except Exception:
            return None

        titl = _clean_text(req.get("titl"))
        subt = _clean_text(req.get("subt"))
        body = _clean_text(req.get("body"))
        if not (titl or body):
            return None
        # Alguns avisos porten llistes de Python al text (Temps d'us...): fora.
        if titl.startswith("[") or body.startswith("["):
            return None

        return {
            "id": rec_id,
            "app": app_display_name(ident),
            "bundle": ident or "",
            "title": titl,
            "subtitle": subt,
            "body": body,
            "time": datetime.now().strftime("%H:%M"),
        }


class Weather:
    """Meteo actual i previsio de 3 dies (Open-Meteo, sense clau d'API)."""

    def __init__(self, lat=41.39, lon=2.17):   # Barcelona per defecte
        self.lat = lat
        self.lon = lon
        self.data = {"temp": 0.0, "wc": 0, "isd": 1}
        self.forecast = []      # [(codi, tmax, tmin), ...]
        self.last = 0.0

    def fetch(self):
        try:
            url = ("https://api.open-meteo.com/v1/forecast"
                   f"?latitude={self.lat}&longitude={self.lon}"
                   "&current=temperature_2m,weather_code,is_day"
                   "&daily=weather_code,temperature_2m_max,temperature_2m_min"
                   "&forecast_days=3&timezone=auto")
            with urllib.request.urlopen(url, timeout=8) as r:
                j = json.load(r)

            cur = j.get("current", {})
            self.data = {
                "temp": float(cur.get("temperature_2m", 0)),
                "wc": int(cur.get("weather_code", 0)),
                "isd": int(cur.get("is_day", 1)),
            }

            day = j.get("daily", {})
            codes = day.get("weather_code", [])
            tmax = day.get("temperature_2m_max", [])
            tmin = day.get("temperature_2m_min", [])
            self.forecast = []
            for i in range(min(3, len(codes), len(tmax), len(tmin))):
                self.forecast.append((int(codes[i]), round(tmax[i]), round(tmin[i])))
            self.last = time.time()
        except Exception:
            pass
        return self.data

    def get(self):
        return self.data

    def forecast_line(self):
        """Linia 'F codi,max,min|...' o None si no hi ha previsio."""
        if not self.forecast:
            return None
        return "F " + "|".join(f"{c},{mx},{mn}" for (c, mx, mn) in self.forecast)


class NetMeter:
    """Velocitat de xarxa (MB/s) calculada a partir de netstat -ib."""

    def __init__(self):
        self.prev = None
        self.t = None

    def rates(self):
        out = _run(["netstat", "-ib"])
        rx = tx = 0
        for line in out.splitlines()[1:]:
            p = line.split()
            if len(p) < 10:
                continue
            if p[0] == "lo0" or not p[2].startswith("<Link"):
                continue
            try:
                rx += int(p[6])
                tx += int(p[9])
            except ValueError:
                pass

        now = time.time()
        if self.prev is None or self.t is None:
            self.prev = (rx, tx)
            self.t = now
            return (0.0, 0.0)

        dt = now - self.t
        if dt <= 0:
            return (0.0, 0.0)
        d_rx = (rx - self.prev[0]) / dt / 1e6
        d_tx = (tx - self.prev[1]) / dt / 1e6
        self.prev = (rx, tx)
        self.t = now
        return (max(0.0, d_rx), max(0.0, d_tx))


class Bridge:
    """Pont serie + estadistiques + execucio d'accions."""

    def __init__(self, config=None):
        self.config = config or load_config()
        self.ser = None
        self.sock = None
        self.port = None
        self.lock = threading.RLock()
        self.running = False
        self.threads = []
        self.stats = {}
        self.net = NetMeter()
        self.weather = Weather()
        self.log_lines = deque(maxlen=200)
        self._ack_chunk = threading.Event()   # resposta 'K' (tros d'icona)
        self._ack_icon = threading.Event()    # resposta 'I' (icona/esborrat)
        self._busy = threading.Event()        # pujant una icona: no enviem stats
        # Icones d'app (les treiem de les .app del Mac): LRU de les que hi ha a
        # la placa i memoria de les que no s'han pogut extreure (per no tornar-hi
        # cada volta).
        global _error_sink
        _error_sink = self.log               # els errors del modul es veuen aqui
        self._app_lru = lru_load()           # {nom_icona: ultim us}
        self._app_fail = set()               # apps sense icona extraïble
        # Fins que la placa no ens saluda ('H'), no li enviem res.
        self._ready = False
        # Reintents de connexio seguits (per no reiniciar la placa en bucle).
        self._retries = 0
        self._apps = []                       # apps obertes (launcher)
        self._apps_t = 0.0
        self._bat_warned = False
        self._event = ""
        self._event_t = 0.0
        self.notifs = NotifReader()           # notificacions del macOS
        self._notif_t = 0.0
        self.notifs_on = True                 # es pot aturar des del panell
        self.app = ("", "")                   # app que te el focus
        self._app_t = 0.0
        # Pestanyes dels navegadors (pantalles "tabs"): llista i temporitzador.
        self._tabs_nav = ""                   # navegador que mirem ara
        self._tabs_clau = None                # ultima llista enviada (per no repetir)
        self._tabs_t = 0.0                    # ultima vegada que les hem enviat
        self._fav_done = set()                # favicons que ja hem pujat
        self._fav_repas = set()               # favicons borrosos que ja hem repescat
        # Captura de pantalla (comanda 'captura'): la placa l'envia en franges.
        self._shot = {}                       # frange -> base64
        self._shot_mida = None                # (amplada, alcada, franges)
        self._shot_fi = False
        # Mentre hi ha una captura en curs no pugem icones: es menjarien
        # l'amplada de banda del port i la captura no arribaria sencera.
        self._captura_en_curs = False
        # Pausa de les pujades d'icones despres de diversos errors seguits (per
        # no inundar el port i deixar el pont sord a la resta).
        self._icon_fails = 0
        self._icon_pausa_fins = 0.0
        # La LECTURA es fa en un fil propi (run_tabs_loop): els AppleScript dels
        # navegadors poden trigar segons i, si es fan al bucle d'estadistiques,
        # la placa perd l'enllac i apaga la pantalla. Aqui nomes hi ha memoria.
        self._tabs_llegides = []              # ultimes pestanyes llegides [(titol,url)]
        self._tabs_req = threading.Event()    # la placa acaba de demanar-les
        # Favorits dels navegadors (pantalles "favs"): es llegeixen del DISC (no
        # cal AppleScript) i canvien molt poc, aixi que n'hi ha prou de mirar-los
        # de tant en tant. Els del navegador que te el focus van primers.
        self._favs = []                       # ultims favorits llegits
        self._favs_clau = None                # ultima llista enviada (per no repetir)
        self._favs_t = 0.0                    # ultima vegada que els hem llegit
        self._favs_llegit = False             # ja els hem llegit del disc (almenys un cop)
        self._tabs_llegit = False             # ja hem llegit les pestanyes (almenys un cop)

    # -- utilitats --------------------------------------------------------
    def log(self, msg):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_lines.append(f"{stamp}  {msg}")

    def list_ports(self):
        if not HAS_SERIAL:
            return []
        return [{"device": p.device, "desc": p.description or ""}
                for p in list_ports.comports()]

    def autodetect_port(self):
        for p in self.list_ports():
            dev = p["device"]
            if any(k in dev for k in ("wchusbserial", "usbserial", "SLAB", "usbmodem")):
                return dev
        return None

    # -- connexio ---------------------------------------------------------
    def connect(self, port=None):
        # Mode WiFi: connectem pel TCP en comptes del port serie.
        if self.config.get("link") == "wifi":
            return self.connect_tcp()
        if not HAS_SERIAL:
            self.log("pyserial no instal.lat: pip install pyserial")
            return False
        with self.lock:
            self.disconnect()
            port = port or self.config.get("port") or self.autodetect_port()
            if not port:
                self.log("cap port serie trobat")
                return False
            try:
                # Obrim en mode exclusiu (nomes nosaltres) i sense tocar DTR/RTS,
                # que en alguns xips USB-serie provoquen talls de connexio.
                self.ser = serial.Serial()
                self.ser.port = port
                self.ser.baudrate = BAUD
                self.ser.timeout = 0.3
                try:
                    self.ser.exclusive = True
                except Exception:
                    pass
                self.ser.open()
                try:
                    self.ser.dtr = False
                    self.ser.rts = False
                except Exception:
                    pass
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
            except Exception as exc:
                self.log(f"no s'ha pogut obrir {port}: {exc}")
                self.ser = None
                return False
            self.port = port
            self.config["port"] = port
        self.log(f"connectat a {port}")
        # NO enviem res encara: obrir el port reinicia la placa (DTR/RTS) i tot
        # el que hi enviem mentre arrenca es perd. Esperem que ella ens saludí
        # amb 'H'; aleshores li enviem la configuracio (vegeu resend_all()).
        self._ready = False
        return True

    def try_reconnect(self):
        """Auto-reconnexio: si el cable s'ha desendollat i tornat a endollar,
        tornem a obrir el port tot sol."""
        if self.config.get("link") == "wifi":
            return self.connect_tcp()
        port = self.config.get("port") or self.autodetect_port()
        if not port or not os.path.exists(port):
            return False
        self.log(f"reintent de connexio a {port}...")
        return self.connect(port)

    def disconnect(self):
        with self.lock:
            if self.ser is not None:
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None
                self.port = None
            self.close_tcp()

    def close_tcp(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def is_connected(self):
        return self.ser is not None or self.sock is not None

    # -- connexio per WiFi (TCP) ------------------------------------------
    def connect_tcp(self, host=None, port=8771):
        host = host or self.config.get("host") or "macpanel.local"
        self.close_tcp()
        try:
            self.sock = socket.create_connection((host, port), timeout=4)
            self.sock.settimeout(0.3)
        except Exception as exc:
            self.log(f"no s'ha pogut connectar per WiFi a {host}:{port} ({exc})")
            self.sock = None
            return False
        self.log(f"connectat per WiFi a {host}:{port}")
        # Com pel cable: esperem el 'H' de la placa abans d'enviar res.
        self._ready = False
        return True

    # -- serie ------------------------------------------------------------
    def send_line(self, line):
        with self.lock:
            if self.sock is not None:
                try:
                    self.sock.sendall((line + "\n").encode("utf-8"))
                    return True
                except Exception as exc:
                    self.log(f"error d'escriptura WiFi: {exc}")
                    self.close_tcp()
                    return False
            if self.ser is None:
                return False
            try:
                self.ser.write((line + "\n").encode("utf-8"))
                return True
            except Exception as exc:
                self.log(f"error d'escriptura: {exc}")
                self.disconnect()
                return False

    def config_payload(self):
        pages = []
        for pg in self.config.get("pages", [])[:12]:
            widgets = [str(w) for w in pg.get("widgets", [])][:9]
            buttons = []
            for b in pg.get("buttons", []):
                if b.get("on", True) is False:
                    continue
                if len(buttons) >= 15:
                    break
                bid = str(b.get("id", ""))[:23]
                label = str(b.get("label", bid))[:12]
                icon = str(b.get("icon", ""))[:19]
                # Les tecles: les del boto o, si no, les de l'accio d'estoc.
                keys = str(b.get("keys", "")) or ACTIONS.get(bid, {}).get("keys", "")
                buttons.append([bid, label, icon, keys[:23]])
            pages.append({
                "n": str(pg.get("name", "?"))[:15],
                "i": str(pg.get("icon", ""))[:19],
                "l": str(pg.get("layout", "buttons"))[:9],
                "ap": [str(a)[:39] for a in pg.get("apps", [])][:3],
                "w": widgets,
                "b": buttons,
            })
        return {"o": str(self.config.get("orientation", "v"))[:1],
                "t": int(self.config.get("theme", 0) or 0),
                "ta": 1 if self.config.get("theme_auto") else 0,
                "td": int(self.config.get("theme_dark", 0) or 0),
                "tl": int(self.config.get("theme_light", 1) or 0),
                "s": int(self.config.get("standby_s", 0) or 0),
                "ic": int(self.config.get("idle_min", 5) or 0),
                "nv": str(self.config.get("nav", "both"))[:7],
                "p": pages}

    def set_wifi(self, ssid, password):
        """Envia les credencials WiFi a la placa (per l'enllac actual)."""
        if self.ser is None and self.sock is None:
            self.log("cal estar connectat per enviar les credencials WiFi")
            return False
        ok = self.send_line(f"W {ssid}|{password}")
        if ok:
            self.config["ssid"] = ssid
            self.log(f"credencials WiFi enviades ({ssid}); la placa s'hi connectara")
        return ok

    def set_link(self, link, host=None):
        """Canvia el mode d'enllac (serial / wifi) i reconecta."""
        self.config["link"] = link
        if host:
            self.config["host"] = host
        self.log(f"canvi d'enllac a '{link}'...")
        self.disconnect()
        return self.connect()

    def notify(self, text):
        """Mostra un avis a la pantalla de la placa."""
        if self.ser is None and self.sock is None:
            return False
        ok = self.send_line("N " + str(text)[:110])
        if ok:
            self.log(f"avis enviat: {text}")
        return ok

    @staticmethod
    def _camp(text, maxim):
        """Neteja un camp perque no trenqui el format 'app|titol|cos'."""
        t = re.sub(r"[|\x00-\x1f]", " ", str(text or ""))
        return re.sub(r"\s+", " ", t).strip()[:maxim]

    def send_notice(self, n):
        """Envia una notificacio del Mac com a baner: 'N app|titol|cos'."""
        app = self._camp(n.get("app"), 18)
        title = self._camp(n.get("title"), 38)
        body = self._camp(n.get("subtitle") or n.get("body"), 74)
        if not (title or body):
            return False
        ok = self.send_line(f"N {app}|{title}|{body}")
        if ok:
            self.log(f"notificacio de {app}: {title or body}")
        return ok

    def send_config(self):
        payload = self.config_payload()
        line = "CFG " + json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        return self.send_line(line)

    # -- icones (pujada a la SD de la placa) ------------------------------
    def send_icon(self, name, data, chunk=256):
        """Envia una icona (bytes RGB565 big-endian) a la SD, per trossos amb ack.

        Trossos petits + una petita pausa: l'ESP32 escriu a la SD i, si li
        arriben gaires bytes mentre esta enfeinat, pot perdre'n (la FIFO de la
        UART es petita).
        """
        if self.ser is None:
            return False

        self._busy.set()          # mentre pugem una icona, no enviem estadistiques
        try:
            self._ack_chunk.clear()
            if not self.send_line(f"ICONPUT {name} {len(data)}"):
                return False
            if not self._ack_chunk.wait(3.0):
                self.log(f"sense resposta a ICONPUT ({name})")
                return False

            b64 = base64.b64encode(data).decode("ascii")
            for i in range(0, len(b64), chunk):
                self._ack_chunk.clear()
                if not self.send_line("ICONCHUNK " + b64[i:i + chunk]):
                    return False
                if not self._ack_chunk.wait(3.0):
                    self.log(f"sense resposta al tros {i // chunk} de '{name}'")
                    return False
                time.sleep(0.005)   # deixa respirar l'ESP32 (SD + UART)

            self._ack_icon.clear()
            if not self.send_line("ICONDONE"):
                return False
            return self._ack_icon.wait(8.0)
        finally:
            self._busy.clear()

    def upload_icon(self, name, png_bytes):
        """Converteix un PNG, el desa al projecte i el puja a la SD de la placa.

        Si les pujades fallen diverses vegades seguides, parem una estona: si
        no, el pont ho reintenta sense parar i inunda el port, i llavors ni les
        estadistiques ni cap altra comanda (com una captura de pantalla) hi
        caben.
        """
        if time.time() < self._icon_pausa_fins:
            return False, "pausa: massa errors seguits pujant icones"
        name = clean_icon_name(name)
        if not name:
            return False, "nom invalid (nomes lletres, numeros i _)"
        try:
            data = png_to_bin(png_bytes, nom=name)
        except Exception as exc:
            return False, str(exc)

        try:
            with open(os.path.join(icons_dir(), name + ".png"), "wb") as fh:
                fh.write(png_bytes)
        except Exception:
            pass

        if self.ser is None:
            return False, "la placa no esta connectada (mira la barra de dalt)"

        for intent in (1, 2):
            if self.send_icon(name, data):
                self.log(f"icona '{name}' pujada a la pantalla")
                self._icon_fails = 0
                return True, "ok"
            self.log(f"reintent de la icona '{name}' ({intent})...")

        self._icon_fails += 1
        if self._icon_fails >= 3:
            self._icon_pausa_fins = time.time() + 60.0
            self.log(f"{self._icon_fails} errors seguits pujant icones: "
                     f"paro un minut per no inundar el port")
        self.log(f"ERROR pujant la icona '{name}'")
        return False, "no s'ha pogut pujar (comprova la connexio i la SD)"

    def delete_icon(self, name):
        name = clean_icon_name(name)
        if not name or self.ser is None:
            return False
        self._ack_icon.clear()
        if not self.send_line(f"ICONDEL {name}"):
            return False
        ok = self._ack_icon.wait(3.0)
        self.log(f"icona '{name}' esborrada de la pantalla" if ok
                 else f"no s'ha pogut esborrar '{name}'")
        return ok

    # -- estadistiques ----------------------------------------------------
    def collect_stats(self):
        rx, tx = self.net.rates()
        bat, chg = battery()
        w = self.weather.get()
        now = datetime.now()
        st = {
            "cpu": round(cpu_percent(), 1),
            "mem": round(mem_percent(), 1),
            "disk": round(disk_percent(), 1),
            "up": round(tx, 2),
            "dn": round(rx, 2),
            "load": round(os.getloadavg()[0], 2),
            "uptime": uptime_seconds(),
            "host": hostname(),
            "time": now.strftime("%H:%M"),
            "date": now.strftime("%d/%m"),
            "wd": ["dg", "dl", "dt", "dc", "dj", "dv", "ds"][int(now.strftime("%w"))],
            "temp": round(w["temp"], 1),
            "wc": w["wc"],
            "isd": w["isd"],
            "dsp": 1 if display_awake() else 0,
            "dk": mac_dark_mode(),
            "idl": int(idle_seconds()),
        }
        if bat is not None:
            st["bat"] = round(bat, 1)
            st["chg"] = chg
        return st

    def stats_line(self):
        s = self.stats
        parts = [
            f"cpu={s.get('cpu', 0)}", f"mem={s.get('mem', 0)}",
            f"disk={s.get('disk', 0)}", f"up={s.get('up', 0)}",
            f"dn={s.get('dn', 0)}", f"load={s.get('load', 0)}",
            f"uptime={s.get('uptime', 0)}", f"host={s.get('host', 'mac')}",
            f"time={s.get('time', '--:--')}", f"date={s.get('date', '')}",
            f"wd={s.get('wd', '')}", f"temp={s.get('temp', 0)}",
            f"wc={s.get('wc', 0)}", f"isd={s.get('isd', 1)}",
            f"dsp={s.get('dsp', 1)}", f"dk={s.get('dk', 0)}",
            f"idl={s.get('idl', 0)}",
        ]
        if "bat" in s:
            parts.append(f"bat={s['bat']}")
            parts.append(f"chg={s.get('chg', 0)}")
        return "S " + " ".join(parts)

    # -- accions ----------------------------------------------------------
    def run_cmd(self, cmd):
        """Executa una ordre de shell (accions personalitzades / proves)."""
        if not cmd:
            return False
        self.log(f"executo: {cmd}")
        try:
            subprocess.Popen(cmd, shell=True)
            return True
        except Exception as exc:
            self.log(f"error: {exc}")
            return False

    def execute(self, action_id):
        action_id = (action_id or "").strip()
        if not action_id:
            return False

        # Launcher: activar l'app numero N de la llista.
        if action_id.startswith("focus:"):
            try:
                idx = int(action_id.split(":", 1)[1])
            except ValueError:
                return False
            apps = self._apps or running_apps()
            if 0 <= idx < len(apps):
                name = apps[idx]
                self.log(f"activo l'aplicacio: {name}")
                try:
                    subprocess.Popen(["osascript", "-e",
                                      f'tell application "{name}" to activate'])
                except Exception as exc:
                    # Si no es pot llançar l'ordre, es registra i prou: una
                    # excepcio aqui mataria el fil de lectura del port (i el
                    # pont es quedaria sord del tot).
                    self.log(f"error activant '{name}': {exc}")
                    return False
                return True
            self.log(f"index d'app invalid: {idx}")
            return False

        # La placa demana que despertem la pantalla del Mac: ho fa quan l'usuari
        # toca el panell i el Mac te la pantalla dormida (si no, la placa
        # s'apagaria al cap d'una estona i semblaria espatllada).
        if action_id == "wake":
            self.log("desperto la pantalla del Mac")
            try:
                # 'caffeinate -u' simula activitat d'usuari: es la manera
                # estandard de despertar la pantalla sense moure el ratoli.
                subprocess.Popen(["caffeinate", "-u", "-t", "3"])
                return True
            except Exception as exc:
                self.log(f"error: {exc}")
                return False

        # Aplicacio INSTAL·LADA: obrir-la (o portar-la al davant) pel bundle id.
        # Es el que fan els botons d'app del panell: 'app:com.apple.Safari'.
        if action_id.startswith("app:"):
            bundle = action_id[4:].strip()
            if not bundle:
                return False
            info = app_index().get(bundle)
            if info is None:
                # Pot ser una app instal·lada fora de les carpetes habituals:
                # ho provem igualment, pero ho deixem dit al registre.
                self.log(f"l'aplicacio '{bundle}' no es a l'index; ho provo igualment")
            else:
                self.log(f"obro l'aplicacio: {info.get('name', bundle)}")
            try:
                # 'open -b' la llança si esta tancada i l'activa si ja hi es.
                subprocess.Popen(["open", "-b", bundle])
                return True
            except Exception as exc:
                self.log(f"error: {exc}")
                return False

        # La placa demana que reenviem les pestanyes (acaba d'entrar a una
        # pantalla "tabs"). Envia de seguida l'ultima llista que tenim (sense
        # esperar el proper cicle del fil) i li demanem rellegir-la.
        if action_id == "refresh:tabs":
            self._tabs_clau = None
            self._tabs_req.set()
            self.send_tabs_if_changed()
            return True

        # Igual, pero per als favorits de les pantalles "favs". Com que els
        # favorits son fitxers del disc (no cal AppleScript), els podem
        # rellegir aqui mateix: son uns 50 ms i la placa no es queda mai amb
        # una pagina buida esperant el proper cicle.
        if action_id == "refresh:favs":
            self.llegeix_favs()
            self._favs_clau = None
            self.send_favs_if_changed()
            return True

        # Pestanyes: activar la pestanya N del navegador obert.
        if action_id.startswith("tab:"):
            try:
                idx = int(action_id.split(":", 1)[1])
            except ValueError:
                return False
            ok = activate_tab(self._tabs_nav, idx + 1)  # la placa envia 0-based
            self.log(f"activo la pestanya {idx} de "
                     f"{self._tabs_nav or 'el navegador'}")
            return ok

        # Favorits: obrir la URL del favorit N amb el navegador de sempre.
        if action_id.startswith("fav:"):
            try:
                idx = int(action_id.split(":", 1)[1])
            except ValueError:
                return False
            if not (0 <= idx < len(self._favs)):
                self.log(f"index de favorit invalid: {idx}")
                return False
            titol, url, _nav = self._favs[idx]
            self.log(f"obro el favorit: {titol or url}")
            try:
                subprocess.Popen(["open", url])
                return True
            except Exception as exc:
                self.log(f"error: {exc}")
                return False

        if action_id.startswith("custom:"):
            cmd = None
            for b in self.config.get("buttons", []):
                if str(b.get("id")) == action_id:
                    cmd = b.get("cmd")
                    break
            if not cmd:
                self.log(f"accio personalitzada sense ordre: {action_id}")
                return False
            return self.run_cmd(cmd)

        act = ACTIONS.get(action_id)
        if not act:
            self.log(f"accio desconeguda: {action_id}")
            return False
        if "keys" in act and "args" not in act:
            # Aquestes accions les envia la PLACA com a tecles Bluetooth.
            self.log(f"'{action_id}' envia les tecles {act['keys']} (des de la pantalla)")
            return True
        self.log(f"executo: {act['label']}")
        try:
            subprocess.Popen(act["args"])
            return True
        except Exception as exc:
            self.log(f"error: {exc}")
            return False

    # -- bucles -----------------------------------------------------------
    def tab_pages(self):
        """Indexos de les pantalles de tipus 'tabs' (les que mostren pestanyes)."""
        return [i for i, pg in enumerate(self.config.get("pages", []))
                if str(pg.get("layout", "")) == "tabs"]

    def te_layout(self, nom):
        """Hi ha alguna pantalla amb aquesta disposicio?"""
        return any(str(pg.get("layout", "")) == nom
                   for pg in self.config.get("pages", []))

    def te_launcher(self):
        """Hi ha alguna pantalla de tipus 'launcher' (apps obertes)?

        Nomes en aquest cas val la pena extreure i pujar icones d'app: si no hi
        ha cap pantalla que les ensenyi, seria feina per no res.
        """
        return self.te_layout("launcher")

    def te_favs(self):
        """Hi ha alguna pantalla de favorits dels navegadors ('favs')?

        Com al launcher: si no hi ha cap pantalla que els ensenyi, no cal
        llegir res ni descarregar cap favicon.
        """
        return self.te_layout("favs")

    def favs_opcions(self):
        """Com vols que es llegeixin els favorits (de la configuracio).

        'favs_max'   quants favorits mostrar (1..MAX_FAVS de la placa)
        'favs_carpetes' 1 = entra tambe dins de les carpetes de la barra
        """
        try:
            maxim = int(self.config.get("favs_max", FAV_MAX_BOOKMARKS))
        except (TypeError, ValueError):
            maxim = FAV_MAX_BOOKMARKS
        maxim = max(1, min(FAV_MAX_BOOKMARKS, maxim))
        carpetes = str(self.config.get("favs_carpetes", "0")).strip() in ("1", "true", "si", "sí")
        return maxim, carpetes

    def send_tabs_if_changed(self):
        """Envia a la placa les pestanyes ja LLEGIDES, si han canviat.

        No fa cap crida AppleScript (la lectura es fa a run_tabs_loop, en un
        fil propi). Aquesta funcio es crida des del bucle d'estadistiques i
        des de l'acció 'refresh:tabs'; com que nomes toca memoria i la UART,
        mai no bloqueja el bucle (si el bloqueges, la placa perd l'enllac i
        apagaria la pantalla: es el que passava abans).
        """
        if not self.tab_pages():
            return
        if not (self.ser is not None and self._ready
                and not self._busy.is_set()):
            return
        # Igual que amb els favorits: no enviem mai una llista buida abans
        # d'haver-ne llegit cap (la placa esborraria la pantalla).
        if not self._tabs_llegit:
            return
        tabs = self._tabs_llegides
        icones_sd = set(list_icons())
        # Envia la linia nomes si les pestanyes han canviat (titol o favicon).
        clau = clau_llista(tabs, icones_sd)
        if clau == self._tabs_clau:
            return
        self._tabs_clau = clau
        self.send_line(tabs_line(tabs, icones_sd))
        self.log(f"pestanyes: {len(tabs)} de {self._tabs_nav or 'cap navegador'}")

    def llegeix_favs(self):
        """Llegeix els favorits dels navegadors (nomes fitxers del disc).

        Es fa al fil de pestanyes, com la resta de lectures "lentes": el bucle
        d'estadistiques nomes ha de tocar memoria i la UART. En aquest cas son
        uns 50 ms, pero si el disc esta ocupat podria ser mes.
        """
        if not self.te_favs():
            return
        maxim, carpetes = self.favs_opcions()
        try:
            self._favs = bookmarks(self._tabs_nav, maxim, carpetes)
        except Exception as exc:
            self.log(f"error llegint els favorits: {exc}")
            self._favs = []
        self._favs_llegit = True

    def send_favs_if_changed(self):
        """Envia a la placa els favorits ja LLEGITS, si han canviat.

        Igual que amb les pestanyes: aqui no es toca el disc ni s'obre cap
        proces, nomes es mira si la llista es diferent de l'ultima que vam
        enviar (aixi no omplim la UART repetint el mateix cada segon).
        """
        if not self.te_favs():
            return
        if not (self.ser is not None and self._ready
                and not self._busy.is_set()):
            return
        # Fins que no haguem llegit res, no enviem una llista buida: la placa
        # esborraria la pantalla i es veuria un parpelleig a l'arrencar.
        if not self._favs_llegit:
            return
        favs = self._favs
        icones_sd = set(list_icons())
        clau = clau_llista(favs, icones_sd)
        if clau == self._favs_clau:
            return
        self._favs_clau = clau
        self.send_line(favs_line(favs, icones_sd))
        self.log(f"favorits: {len(favs)} de "
                 f"{favs[0][2] if favs else 'cap navegador'}")

    def run_tabs_loop(self):
        """Fil propi: llegeix les pestanyes del navegador cada 3 s (i les apps).

        Els AppleScript dels navegadors poden trigar segons quan l'aplicacio
        esta ocupada. Si els féssim al bucle d'estadistiques, la placa no
        rebria cap 'S' durant aquest temps, diria 'enllac perdut' i apagaria
        la pantalla. Aqui nomes es toca memoria; l'enviament el fa
        send_tabs_if_changed() (i, per a les apps, directament aqui, amb la
        mateixa proteccio d'enllac que abans).
        """
        t_apps = 0.0
        t_ev = 0.0
        t_nav = 0.0
        t_ico = 0.0
        while self.running:
            try:
                # Apps obertes per al launcher: mateixa raó que les pestanyes
                # (System Events pot trigar fins a 4 s).
                if time.time() - t_apps > 5.0:
                    t_apps = time.time()
                    apps = running_apps()
                    if apps != self._apps:
                        self._apps = apps
                        if (self.ser is not None and self._ready
                                and not self._busy.is_set()):
                            # Primer assegurem les icones que faltin (una per
                            # volta): aixi, quan la placa repinti el launcher,
                            # ja hi son. Nomes si hi ha alguna pantalla launcher.
                            if self.te_launcher():
                                self._push_one_app_icon(apps)
                            self.send_line(launcher_line(apps))
                            self.log(f"launcher: {len(apps)} apps obertes")
                # Agenda (proper esdeveniment): l'AppleScript de Calendar pot
                # trigar 8 s (i obrir l'app si esta tancada); abans es feia al
                # bucle de stats i, cada 5 minuts, la placa perdia l'enllac.
                if time.time() - t_ev > 300.0:
                    t_ev = time.time()
                    ev = next_event()
                    if ev != self._event:
                        self._event = ev
                        if (self.ser is not None and self._ready
                                and not self._busy.is_set()):
                            self.send_line("E " + ev)
                            self.log(f"agenda: {ev}" if ev
                                     else "agenda: sense esdeveniments")
                # Icones de les apps INSTAL·LADES que surten als botons (id
                # 'app:<bundle>'): s'extreuen i es pugen d'una en una, encara
                # que l'app no estigui oberta. Sense aixo, un boto d'app
                # instal·lada es quedaria sense icona.
                if time.time() - t_ico > 8.0:
                    t_ico = time.time()
                    bundles = self.bundles_de_botons()
                    if bundles:
                        self._push_icona_per_bundles(bundles)

                if self.tab_pages() or self.te_favs():
                    # El navegador del davant fa falta per a les pestanyes i,
                    # tambe, per posar els favorits d'aquell navegador primers.
                    # Amb pantalles de pestanyes es mira cada volta (cal per
                    # saber qui te el focus); amb nomes favorits, cada 15 s (a
                    # l'usuari no li canvia l'ordre de la pagina cada 3 s).
                    if self.tab_pages() or time.time() - t_nav > 15.0:
                        t_nav = time.time()
                        self._tabs_nav = browser_running()
                    nav = self._tabs_nav
                    if self.tab_pages():
                        tabs = browser_tabs(nav) if nav else []
                        self._tabs_llegides = tabs
                        self._tabs_llegit = True
                        self._tabs_req.clear()
                        # Un favicon per volta: la pujada va amb ack per la
                        # UART i tambe triga (per aixo es fora de stats).
                        self._push_one_favicon(tabs)
                    # Favorits: es llegeixen del disc (rapid) i queden a
                    # memoria fins que send_favs_if_changed() els envii.
                    self.llegeix_favs()
                    self._push_one_favicon(self._favs)
            except Exception as exc:
                self.log(f"error de pestanyes: {exc}")
            time.sleep(3.0)

    def _push_icona_per_bundles(self, bundles):
        """Puja com a MAXIM una icona d'app per cridada, donats els bundle ids.

        L'extraccio (descomprimir l'icns, NSWorkspace, reduir a 32 px) i la
        pujada amb ack per la UART triguen: es fa una per volta i fora del bucle
        d'estadistiques, perque l'enllac no se'n ressenti.

        Amb politica LRU: quan se supera APP_ICON_MAX, s'esborren de la placa
        les icones d'app que fa mes temps que no s'usen.
        """
        if self.ser is None or self._busy.is_set() or self._captura_en_curs:
            return
        idx = app_index()
        for bundle in bundles:
            info = idx.get(bundle)
            if info is None:
                continue
            ic = nom_icona_app(bundle)
            if not ic or ic in self._app_fail:
                continue
            if ic in self._app_lru:
                self._app_lru[ic] = time.time()   # marca d'us (es desa al final)
                continue

            png = icona_app_png(bundle, info)
            if not png:
                # No se n'ha pogut treure cap: no ho tornem a provar en bucle.
                self._app_fail.add(ic)
                self.log(f"sense icona per a '{info.get('name', bundle)}' ({bundle})")
                continue

            if len(self._app_lru) >= APP_ICON_MAX:
                self._app_icon_evict()
            # upload_icon() torna (ok, missatge): compte, una tupla sempre es
            # certa! Si no desempaquetessim, el pont es pensaria que la icona
            # s'ha pujat sempre i no ho tornaria a provar mai.
            ok, _msg = self.upload_icon(ic, png)
            if ok:
                self._app_lru[ic] = time.time()
                lru_save(self._app_lru)
                self.log(f"icona de l'app '{info.get('name', bundle)}' a la placa")
            return

    def bundles_de_botons(self):
        """Bundle ids de les apps que surten als botons (id 'app:<bundle>').

        Serveix per pujar la icona de debò d'aquella app encara que no estigui
        oberta: es una app INSTAL·LADA, i el boto l'obre.
        """
        out = []
        for pg in self.config.get("pages", []):
            for b in pg.get("buttons", []):
                bid = str(b.get("id", ""))
                if bid.startswith("app:"):
                    bundle = bid[4:].strip()
                    if bundle and bundle not in out:
                        out.append(bundle)
        return out

    def _push_one_app_icon(self, apps):
        """Puja com a MAXIM una icona d'app per cridada (les que estan obertes).

        Nomes es fan servir per al launcher.
        """
        bundles = []
        for nom in apps:
            bundle = bundle_for_name(nom)
            if bundle:
                bundles.append(bundle)
        self._push_icona_per_bundles(bundles)

    def _app_icon_evict(self):
        """Esborra de la placa la icona d'app que fa mes temps que no s'usa."""
        if not self._app_lru:
            return
        vell = min(self._app_lru.items(), key=lambda kv: kv[1])[0]
        self._app_lru.pop(vell, None)
        lru_save(self._app_lru)
        if self.delete_icon(vell):
            self.log(f"icona '{vell}' fora de la placa (LRU)")

    def _push_one_favicon(self, items):
        """Puja com a MAXIM un favicon per cridada (descarrega + conversio + ack).

        Retorna despres de la primera pujada intentada: aixi una sola icona
        per volta i l'enllac no es veu afectat. Serveix tant per a les
        pestanyes com per als favorits (tots dos son llistes (titol, url, ...)).
        """
        if self.ser is None or self._busy.is_set() or self._captura_en_curs:
            return
        icones_sd = set(list_icons())
        for _titol, url, *_ in items:
            ic = favicon_icon(url)
            if not ic or ic in self._fav_done:
                continue
            if ic in icones_sd:
                # Ja hi es. Pero si es de baixa resolucio (d'una epoca en que
                # les demanavem mes petites), la tornem a baixar un cop: a la
                # placa es veia borrosa i no hi havia manera d'arreglar-ho.
                if ic not in self._fav_repas and _icona_fluixa(ic):
                    self._fav_repas.add(ic)
                    png = favicon_png(url)
                    if png and self.upload_icon(ic, png)[0]:
                        return
                continue
            if len(self._fav_done) >= FAV_MAX:
                return
            self._fav_done.add(ic)
            png = favicon_png(url)
            if png and self.upload_icon(ic, png)[0]:
                icones_sd.add(ic)
            return

    def run_stats_loop(self):
        t_conn = time.time()
        t_prev = None          # fi de l'iteracio anterior (diagnòstic)
        while self.running:
            t0 = time.time()
            # Diagnòstic: entre dues iteracions nomes hi hauria de passar el
            # sleep (~1 s). Si es molt mes, el temps es perd FORA del bucle
            # (no es cap dels passes mesurats de dins).
            if t_prev is not None and (t0 - t_prev) > 2.5:
                self.log(f"[DIAG] gap entre iteracions: {t0 - t_prev:.1f}s "
                         f"(el sleep hauria de ser ~1 s)")
            dt_c = dt_n = dt_a = dt_t = 0.0   # diagnòstic: temps de cada part

            # No enviem res fins que la placa ens hagi saludat amb 'H': mentre
            # arrenca, el seu port no esta a punt i els primers bytes es perden
            # (arribaven linies trencades, com ara 'chg=1').
            if not self._ready and time.time() - t_conn > 12.0:
                self._ready = True          # per si no arriba cap 'H'
                self.log("la placa no ha saludat: li envio la configuracio igualment")
                self.send_config()
            if not self.running:
                return
            if self.ser is None:
                self._ready = False
                t_conn = time.time()

            try:
                t_c = time.time()
                self.stats = self.collect_stats()
                if (self.ser is not None and self._ready
                        and not self._busy.is_set()):
                    self.send_line(self.stats_line())
                dt_c = time.time() - t_c
            except Exception as exc:
                self.log(f"error d'estadistiques: {exc}")
                dt_c = 0.0

            # Llista d'apps per al launcher: la llegeix run_tabs_loop (fil
            # propi); aqui no es fa res (System Events pot trigar 4 s i
            # trencaria l'enllac si ho féssim aqui).

            # Pestanyes dels navegadors per a les pantalles "tabs" (cada 3 s).
            # NOMES enviem: la lectura (AppleScript) la fa run_tabs_loop en un
            # fil propi, perque si es féssim aqui i l'app triga, la placa no
            # rebria stats, perdria l'enllac i apagaria la pantalla.
            if time.time() - self._tabs_t > 3.0:
                self._tabs_t = time.time()
                try:
                    t_t = time.time()
                    self.send_tabs_if_changed()
                    # Favorits dels navegadors (pantalles "favs"): mateixa idea,
                    # la lectura la fa run_tabs_loop.
                    self.send_favs_if_changed()
                    dt_t = time.time() - t_t
                except Exception as exc:
                    self.log(f"error de pestanyes: {exc}")
                    dt_t = 0.0

            # Notificacions del macOS -> baner a la pantalla (cada 2 s).
            if self.notifs_on and time.time() - self._notif_t > 2.0:
                self._notif_t = time.time()
                t_n = time.time()
                for n in self.notifs.poll():
                    if (self.ser is not None or self.sock is not None) \
                            and self._ready and not self._busy.is_set():
                        self.send_notice(n)
                dt_n = time.time() - t_n
            # Aplicacio que te el focus: l'enviem nomes quan canvia. Si no en
            # detectem cap (salvapantalles, sessio bloquejada...) ens quedem
            # amb l'ultima que sabiem: aixi la placa no torna a la primera
            # pantalla tot sol.
            if time.time() - self._app_t > 1.0:
                self._app_t = time.time()
                t_a = time.time()
                bundle, name = front_app()
                dt_a = time.time() - t_a
                if bundle and (bundle, name) != self.app:
                    self.app = (bundle, name)
                    self.stats["app"] = bundle
                    self.stats["appname"] = name
                    if (self.ser is not None or self.sock is not None) \
                            and self._ready and not self._busy.is_set():
                        self.send_line(f"A {bundle}|{self._camp(name, 24)}")
                        self.log(f"app activa: {name or bundle}")

            # Avis automatic: bateria baixa.
            b = self.stats.get("bat")
            if b is not None and self.ser is not None:
                if b < 20 and not self._bat_warned:
                    self._bat_warned = True
                    self.send_line(f"N Bateria baixa: {int(b)}%")
                elif b > 25:
                    self._bat_warned = False

            # Agenda del proper esdeveniment: la llegeix run_tabs_loop (fil
            # propi); l'AppleScript de Calendar pot trigar 8 s i, si es feia
            # aqui, la placa perdia l'enllac cada 5 minuts.
            # Diagnòstic d'inestabilitat: si una iteracio triga gaire (la placa
            # perd l'enllac als 3 s sense stats i apaga la pantalla), loguem
            # QUINA part ha sigut lenta. Les normals son ~1 s.
            dt_all = time.time() - t0
            if dt_all > 1.5:
                parts = {"stats": dt_c, "tabs": dt_t, "notifs": dt_n, "app": dt_a}
                pit = max(parts, key=parts.get)
                self.log(f"[DIAG] iteracio lenta: total {dt_all:.1f}s | pitjor: "
                         f"{pit} {parts[pit]:.1f}s | "
                         + " ".join(f"{k}={v:.1f}" for k, v in parts.items()))
            interval = max(0.2, float(self.config.get("refresh_ms", 1000)) / 1000.0)
            t_prev = time.time()
            time.sleep(max(0.05, interval - (time.time() - t0)))

    def run_read_loop(self):
        """Llegeix el que diu la placa (port serie o WiFi) i ho processa.

        IMPORTANT: aquest fil NO es pot morir mai. Si moria, el pont quedava
        SORD (continuava enviant estadistiques pero no llegia cap resposta) i
        tot plegat semblava que la placa s'hagues penjat: no responia a cap
        comanda, ni al 'restart', i la pantalla es quedava congelada. Per aixo
        tot el cos va dins d'un try/except: una linia dolenta es registra i
        es descarta, pero el fil continua.
        """
        buf = b""
        while self.running:
            try:
                sock = self.sock
                ser = self.ser

                if sock is None and ser is None:
                    # Auto-reconnexio amb espera creixent. Compte: obrir el port
                    # reinicia la placa (DTR/RTS), aixi que si alguna cosa va
                    # malament no ens hi podem posar en bucle: cada reintent
                    # l'hi tornaria a fer. Els primers van de seguida (per si
                    # s'ha desendollat i tornat a endollar) i despres mes.
                    self._retries += 1
                    wait = 2.0 if self._retries <= 3 else min(2.0 * self._retries, 15.0)
                    time.sleep(wait)
                    if self.running and self.sock is None and self.ser is None:
                        if self.try_reconnect():
                            self._retries = 0
                    continue

                if sock is not None:
                    try:
                        raw = sock.recv(512)
                    except socket.timeout:
                        continue
                    except Exception as exc:
                        self.log(f"error de lectura WiFi: {exc}")
                        self.close_tcp()
                        buf = b""
                        continue
                    if not raw:
                        self.log("el client WiFi s'ha desconnectat")
                        self.close_tcp()
                        buf = b""
                        continue
                else:
                    try:
                        # readline() torna de seguida quan arriba un '\n'.
                        raw = ser.readline()
                    except Exception as exc:
                        self.log(f"error de lectura: {exc}")
                        self.disconnect()
                        buf = b""
                        continue
                    if not raw:
                        continue

                buf += raw
                while b"\n" in buf:
                    line_raw, buf = buf.split(b"\n", 1)
                    line = line_raw.decode("utf-8", "replace").strip()
                    if not line:
                        continue
                    try:
                        self.handle_line(line)
                    except Exception as exc:
                        # Una linia no pot matar el fil (mira la nota de dalt).
                        self.log(f"error processant '{line[:40]}': {exc}")
            except Exception as exc:
                # Xarxa de seguretat: cap error inesperat no ha de deixar el
                # pont sord. Es registra i es continua.
                self.log(f"error greu al fil de lectura: {exc}")
                time.sleep(0.2)

    def resend_all(self, delay=2.5):
        """Reenvia a la placa tot el que necessita: configuracio, previsio del
        temps, apps obertes i agenda.

        Es fa amb una mica de retard a posta: la placa envia 'H' tot just
        arrencar i encara triga un segon a tenir el port a punt; si li enviem
        bytes abans d'hora es perden (i, amb ells, el prefix de la linia).
        """
        def _job():
            time.sleep(delay)
            if not self.running:
                return
            self.send_config()
            line = self.weather.forecast_line()
            if line:
                self.send_line(line)
            apps = running_apps()
            self._apps = apps
            if apps:
                self.send_line(launcher_line(apps))
            ev = next_event()
            self._event = ev
            if ev:
                self.send_line("E " + ev)
            self.log("estat complet reenviat a la placa")

        threading.Thread(target=_job, daemon=True).start()

    def _shot_linia(self, cos):
        """Reb una linia de la captura de pantalla de la placa ('captura')."""
        if cos == "FI":
            self._shot_fi = True
            return
        parts = cos.split(" ", 1)
        if len(parts) == 1:
            nums = parts[0].split()
            if len(nums) == 3:
                self._shot_mida = tuple(int(x) for x in nums)
                self._shot = {}
                self.log(f"captura: la placa diu {self._shot_mida}")
            else:
                self.log(f"captura: linia estranya '{cos[:40]}'")
            return
        try:
            self._shot[int(parts[0])] = parts[1]
        except ValueError:
            pass

    def captura_pantalla(self, timeout=90.0):
        """Demanem una captura de la pantalla i l'esperem.

        La placa envia la pantalla en franges (RGB565 en base64). Retorna
        (amplada, alcada, bytes) o None si no arriba sencera.

        Com que va pel MATEIX port que les estadistiques, mentre dura la captura
        no s'hi pot enviar res mes; la placa tambe esta enfeinada llegint la
        pantalla, aixi que les linies 'S' que li arribin s'acumulen al seu
        buffer (no passa res: son descartables).
        """
        self._shot = {}
        self._shot_mida = None
        self._shot_fi = False
        self._captura_en_curs = True
        try:
            return self._captura_intent(timeout)
        finally:
            self._captura_en_curs = False

    def _captura_intent(self, timeout):
        if not self.send_line("captura"):
            self.log("no s'ha pogut demanar la captura (port?)")
            return None
        self.log("demanant una captura de pantalla (triga ~40 s)...")
        fi = time.time() + timeout
        while time.time() < fi and not self._shot_fi:
            time.sleep(0.2)
        if self._shot_mida is None:
            self.log("la captura no ha arribat (cap frange)")
            return None
        w, h, franges = self._shot_mida
        self.log(f"captura: {len(self._shot)} franges de {franges}")
        dades = bytearray()
        for f in range(franges):
            tros = self._shot.get(f)
            if tros is None:
                self.log(f"falta la frange {f} de la captura")
                return None
            try:
                dades += base64.b64decode(tros, validate=True)
            except Exception:
                return None
        if len(dades) < w * h * 2:
            return None
        return w, h, bytes(dades[:w * h * 2])

    def captura_png(self):
        """La captura de la pantalla, com a PNG (bytes) o None."""
        if Image is None:
            return None
        r = self.captura_pantalla()
        if r is None:
            return None
        w, h, dades = r
        im = Image.new("RGB", (w, h))
        px = im.load()
        for i in range(w * h):
            v = (dades[i * 2] << 8) | dades[i * 2 + 1]
            px[i % w, i // w] = (((v >> 11) & 0x1F) * 255 // 31,
                                 ((v >> 5) & 0x3F) * 255 // 63,
                                 (v & 0x1F) * 255 // 31)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()

    def handle_set(self, payload):
        """Ajust canviat des de la pantalla de l'ESP32: 'clau=valor'.

        La pantalla pot canviar el tema, l'orientacio, la brillantor i el
        temps de repos. Aqui ho desem i, si cal, tornem a enviar la
        configuracio perque quedi guardada a la placa.
        """
        if "=" not in payload:
            return
        key, value = payload.split("=", 1)
        key = key.strip().lower()
        value = value.strip()

        if key == "theme":
            try:
                self.config["theme"] = max(0, min(5, int(value)))
            except ValueError:
                return
            save_config(self.config)
            self.send_config()
            self.log(f"tema canviat des de la pantalla -> "
                     f"{self.config['theme']} ({theme_name(self.config['theme'])})")

        elif key in ("themeauto", "tdark", "tlight"):
            # Ajustos del tema automatic (seguir el clar/fosc del Mac).
            if key == "themeauto":
                self.config["theme_auto"] = 1 if value[:1] in ("1", "s", "o") else 0
                self.log("tema automatic -> "
                         + ("si" if self.config["theme_auto"] else "no"))
            else:
                try:
                    v = max(0, min(5, int(value)))
                except ValueError:
                    return
                self.config["theme_dark" if key == "tdark" else "theme_light"] = v
                self.log(f"tema {'fosc' if key == 'tdark' else 'clar'} "
                         f"des de la pantalla -> {v} ({theme_name(v)})")
            save_config(self.config)
            self.send_config()

        elif key == "orient":
            self.config["orientation"] = "h" if value[:1].lower() == "h" else "v"
            save_config(self.config)
            self.send_config()
            self.log(f"orientacio canviada des de la pantalla -> "
                     f"{self.config['orientation']}")

        elif key == "standby":
            try:
                self.config["standby_s"] = max(0, int(value))
            except ValueError:
                return
            save_config(self.config)
            self.log(f"repos canviat des de la pantalla -> "
                     f"{self.config['standby_s']} s")

        elif key == "idle":
            # Minuts d'inactivitat al Mac abans de passar al rellotge.
            try:
                self.config["idle_min"] = max(0, int(value))
            except ValueError:
                return
            save_config(self.config)
            self.send_config()          # la placa ho necessita per decidir
            self.log(f"rellotge si inactiu -> {self.config['idle_min']} min")

        elif key == "nav":
            v = value.strip().lower()
            self.config["nav"] = v if v in ("both", "bar", "swipe", "off") \
                                 else "both"
            save_config(self.config)
            self.send_config()
            self.log(f"navegacio -> {self.config['nav']}")

        elif key == "bright":
            self.log(f"brillantor canviada des de la pantalla -> {value}%")

    def handle_line(self, line):
        if line == "H":
            self.log("ESP32 demana handshake")
            self._ready = True
            self.send_line("OK Mac-Panel v1")
            self.resend_all()
        elif line.startswith("C "):
            self.execute(line[2:])
        elif line.startswith("X "):
            self.handle_set(line[2:])
        elif line == "A":
            self.log("configuracio confirmada per l'ESP32")
        elif line == "K":
            self._ack_chunk.set()
        elif line == "I":
            self._ack_icon.set()
        elif line == "E":
            self._ack_chunk.set()
            self._ack_icon.set()
            self.log("l'ESP32 ha retornat un error")
        elif line.startswith("[SHOT] "):
            self._shot_linia(line[7:])
        elif line.startswith("[SYS] up="):
            pass   # informe periodic de memoria: no embussem el registre
        else:
            self.log(f"ESP32: {line}")

    # -- cicle de vida ----------------------------------------------------
    def start(self):
        if self.running:
            return
        self.running = True
        self.connect()
        t1 = threading.Thread(target=self.run_stats_loop, daemon=True)
        t2 = threading.Thread(target=self.run_read_loop, daemon=True)
        t3 = threading.Thread(target=self.run_weather_loop, daemon=True)
        # Fil dels AppleScript lents (pestanyes del navegador i apps obertes):
        # aixi el bucle d'estadistiques mai no es queda sense enviar stats.
        t4 = threading.Thread(target=self.run_tabs_loop, daemon=True)
        t1.start()
        t2.start()
        t3.start()
        t4.start()
        self.threads = [t1, t2, t3, t4]

    def run_weather_loop(self):
        """Refresca la meteo cada 20 min (en un fil propi, per no bloquejar)."""
        t_start = time.time()
        while self.running:
            self.weather.fetch()
            line = self.weather.forecast_line()
            # No enviem la previsio fins que la placa fa una estona que arrenca:
            # els primers bytes que li arriben es perden (i amb ells el prefix
            # 'F '). Ja la reenviem tota des de resend_all() en el handshake.
            if (line and time.time() - t_start > 10.0
                    and self.ser is not None and not self._busy.is_set()):
                self.send_line(line)
                self.log(f"previsio de {len(self.weather.forecast)} dies enviada")
            for _ in range(1200):          # 20 min en trossos de 1 s
                if not self.running:
                    return
                time.sleep(1)

    def stop(self):
        self.running = False
        self.disconnect()


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Mac Panel - pont serie (sense GUI)")
    ap.add_argument("--port", help="port serie (p.ex. /dev/cu.wchusbserial1410)")
    args = ap.parse_args()

    cfg = load_config()
    if args.port:
        cfg["port"] = args.port
    bridge = Bridge(cfg)
    bridge.start()
    print("Mac Panel en marxa (headless). Ctrl+C per sortir.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.stop()


if __name__ == "__main__":
    main()

