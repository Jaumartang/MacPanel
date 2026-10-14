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
                if len(parts) >= 2:
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


def png_to_bin(png_bytes, size=64, nom=None):
    """Converteix un PNG a bytes RGB565 big-endian amb el fons transparent.

    Fa servir la MATEIXA conversio que tools/png2bin.py: aixi el panell web i
    l'eina de linia d'ordres donen exactament el mateix resultat (abans hi
    havia dues implementacions i no coincidien).

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


def _run(cmd, timeout=2.0):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


# --- Estadistiques del Mac -------------------------------------------------

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

    total_b = 0
    try:
        total_b = int(_run(["sysctl", "-n", "hw.memsize"]).strip() or 0)
    except ValueError:
        total_b = 0
    if total_b <= 0:
        return 0.0
    used = (active + wired + comp) * page
    return max(0.0, min(100.0, used * 100.0 / total_b))


def disk_percent():
    """% de disc usat a '/'."""
    out = _run(["df", "-k", "/"])
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return 0.0
    for part in lines[-1].split():
        if part.endswith("%"):
            try:
                return float(part[:-1])
            except ValueError:
                return 0.0
    return 0.0


def battery():
    """(percentatge, carregant) o (None, -1) si no hi ha bateria."""
    out = _run(["pmset", "-g", "batt"])
    m = re.search(r"(\d+)%", out)
    if not m:
        return (None, -1)
    pct = float(m.group(1))
    chg = 1 if re.search(r"\bcharging\b|\bcharged\b|finishing charge", out) else 0
    return (pct, chg)


def uptime_seconds():
    out = _run(["sysctl", "-n", "kern.boottime"])
    m = re.search(r"sec = (\d+)", out)
    if not m:
        return 0
    return max(0, int(time.time() - int(m.group(1))))


def hostname():
    out = _run(["scutil", "--get", "ComputerName"]).strip()
    if not out:
        out = socket.gethostname()
    return re.sub(r"\s+", "_", out)


def mac_dark_mode():
    """El Mac te l'aparenca fosca? Ho diu AppleInterfaceStyle.

    Amb l'aparenca clara la clau no existeix i 'defaults' peta: aleshores la
    sortida es buida i ho interpretem com a clar.
    """
    out = _run(["defaults", "read", "-g", "AppleInterfaceStyle"]).strip()
    return 1 if out.lower() == "dark" else 0


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


def launcher_line(apps):
    """Linia 'L nom=icona|nom=icona' amb les apps obertes i la seva icona.

    Les apps sense icona van sense el '=' (la placa els posa el nom i prou).
    """
    parts = []
    for a in apps:
        nom = re.sub(r"[|=]", " ", a).strip()
        if not nom:
            continue
        ic = app_icon(nom)
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


def favicon_png(url, px=64):
    """Bytes PNG del favicon d'una URL (Google s2) o None si no hi e'.

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
        # La LECTURA es fa en un fil propi (run_tabs_loop): els AppleScript dels
        # navegadors poden trigar segons i, si es fan al bucle d'estadistiques,
        # la placa perd l'enllac i apaga la pantalla. Aqui nomes hi ha memoria.
        self._tabs_llegides = []              # ultimes pestanyes llegides [(titol,url)]
        self._tabs_req = threading.Event()    # la placa acaba de demanar-les

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
        """Converteix un PNG, el desa al projecte i el puja a la SD de la placa."""
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
                return True, "ok"
            self.log(f"reintent de la icona '{name}' ({intent})...")

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
                subprocess.Popen(["osascript", "-e",
                                  f'tell application "{name}" to activate'])
                return True
            self.log(f"index d'app invalid: {idx}")
            return False

        # La placa demana que reenviem les pestanyes (acaba d'entrar a una
        # pantalla "tabs"). Envia de seguida l'ultima llista que tenim (sense
        # esperar el proper cicle del fil) i li demanem rellegir-la.
        if action_id == "refresh:tabs":
            self._tabs_clau = None
            self._tabs_req.set()
            self.send_tabs_if_changed()
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
        tabs = self._tabs_llegides
        # Envia la linia nomes si les pestanyes han canviat (titol o favicon).
        clau = tuple((t, favicon_icon(u)) for t, u in tabs)
        if clau == self._tabs_clau:
            return
        self._tabs_clau = clau
        icones_sd = set(list_icons())
        self.send_line(tabs_line(tabs, icones_sd))
        self.log(f"pestanyes: {len(tabs)} de {self._tabs_nav or 'cap navegador'}")

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
                            self.send_line(launcher_line(apps))
                            self.log(f"launcher: {len(apps)} apps obertes")
                if self.tab_pages():
                    nav = browser_running()
                    tabs = browser_tabs(nav) if nav else []
                    self._tabs_nav = nav
                    self._tabs_llegides = tabs
                    self._tabs_req.clear()
                    # Un favicon per volta: la pujada va amb ack per la UART i
                    # tambe triga (per aixo es fora del bucle de stats).
                    self._push_one_favicon(tabs)
            except Exception as exc:
                self.log(f"error de pestanyes: {exc}")
            time.sleep(3.0)

    def _push_one_favicon(self, tabs):
        """Puja com a MAXIM un favicon per cridada (descarrega + conversio + ack).

        Retorna despres de la primera pujada intentada: aixi una sola icona
        per volta i l'enllac no es veu afectat.
        """
        if self.ser is None or self._busy.is_set():
            return
        icones_sd = set(list_icons())
        for _titol, url in tabs:
            ic = favicon_icon(url)
            if not ic or ic in icones_sd or ic in self._fav_done:
                continue
            if len(self._fav_done) >= FAV_MAX:
                return
            self._fav_done.add(ic)
            png = favicon_png(url)
            if png and self.upload_icon(ic, png):
                icones_sd.add(ic)
            return

    def run_stats_loop(self):
        t_conn = time.time()
        while self.running:
            t0 = time.time()

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
                self.stats = self.collect_stats()
                if (self.ser is not None and self._ready
                        and not self._busy.is_set()):
                    self.send_line(self.stats_line())
            except Exception as exc:
                self.log(f"error d'estadistiques: {exc}")

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
                    self.send_tabs_if_changed()
                except Exception as exc:
                    self.log(f"error de pestanyes: {exc}")

            # Notificacions del macOS -> baner a la pantalla (cada 2 s).
            if self.notifs_on and time.time() - self._notif_t > 2.0:
                self._notif_t = time.time()
                for n in self.notifs.poll():
                    if (self.ser is not None or self.sock is not None) \
                            and self._ready and not self._busy.is_set():
                        self.send_notice(n)
            # Aplicacio que te el focus: l'enviem nomes quan canvia. Si no en
            # detectem cap (salvapantalles, sessio bloquejada...) ens quedem
            # amb l'ultima que sabiem: aixi la placa no torna a la primera
            # pantalla tot sol.
            if time.time() - self._app_t > 1.0:
                self._app_t = time.time()
                bundle, name = front_app()
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

            # Agenda: proper esdeveniment (cada 5 min).
            if time.time() - self._event_t > 300:
                self._event_t = time.time()
                ev = next_event()
                if ev != self._event:
                    self._event = ev
                    if (self.ser is not None and self._ready
                            and not self._busy.is_set()):
                        self.send_line("E " + ev)
                        self.log(f"agenda: {ev}" if ev else "agenda: sense esdeveniments")
            interval = max(0.2, float(self.config.get("refresh_ms", 1000)) / 1000.0)
            time.sleep(max(0.05, interval - (time.time() - t0)))

    def run_read_loop(self):
        buf = b""
        while self.running:
            sock = self.sock
            ser = self.ser

            if sock is None and ser is None:
                # Auto-reconnexio amb espera creixent. Compte: obrir el port
                # reinicia la placa (DTR/RTS), aixi que si alguna cosa va malament
                # no ens hi podem posar en bucle: cada reintent l'hi tornaria a
                # fer. Els primers van de seguida (per si s'ha desendollat i
                # tornat a endollar) i despres s'esperen mes.
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
                if line:
                    self.handle_line(line)

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

