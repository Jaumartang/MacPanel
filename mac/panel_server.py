#!/usr/bin/env python3
"""
panel_server.py - Panell de control web del Mac Panel.

Serveix una pagina a http://127.0.0.1:8770 on es pot triar quins widgets surten
a la pantalla de l'ESP32 i quins shortcuts hi ha, a mes de connectar/desconnectar
el port serie i provar les accions.

  python3 mac/panel_server.py             # obre el navegador
  python3 mac/panel_server.py --headless  # nomes el pont (sense web)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from bridge import (ACTIONS, Bridge, WIDGETS, apps_instalades, extreu_icona,
                    list_icons, load_config, save_config)
import panel_model as model

HOST = "127.0.0.1"
DEFAULT_PORT = 8770
APP_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(APP_DIR, "panel.html")
ASSETS_ICONS = os.path.join(os.path.dirname(APP_DIR), "Assets", "icons")

BRIDGE = None  # type: Bridge


def state():
    return {
        "config": BRIDGE.config,
        "stats": BRIDGE.stats,
        "connected": BRIDGE.is_connected(),
        "port": BRIDGE.port,
        "ports": BRIDGE.list_ports(),
        "log": list(BRIDGE.log_lines)[-200:],
        "widgets": WIDGETS,
        "actions": {k: v["label"] for k, v in ACTIONS.items()},
        "actionKeys": {k: v.get("keys", "") for k, v in ACTIONS.items()},
        "icons": list_icons(),
        "link": BRIDGE.config.get("link", "serial"),
        "host": BRIDGE.config.get("host", ""),
        "notifs": list(BRIDGE.notifs.history)[:25],
        "notifError": BRIDGE.notifs.error,
        "notifOn": BRIDGE.notifs_on,
        "app": BRIDGE.app[0],
        "appName": BRIDGE.app[1],
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else str(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False),
                   "application/json; charset=utf-8")

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            try:
                with open(HTML_PATH, "rb") as fh:
                    self._send(200, fh.read(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, "falta panel.html", "text/plain; charset=utf-8")
        elif path == "/api/state":
            self._json(state())
        elif path == "/api/model":
            # Cataleg del model: el que l'editor pot oferir. Aixi el navegador
            # no ha de duplicar les llistes (ni les regles) que ja te el Python.
            self._json({
                "versio": model.SCHEMA_VERSION,
                "gadgets": model.GADGETS,
                "disposicions": model.DISPOSICIONS,
                "accions": model.ACCIONS,
                "accions_sistema": list(model.ACCIONS_SISTEMA),
                "temes": model.TEMES,
                "pantalla": model.PANTALLA,
                "limits": {
                    "pantalles": model.MAX_PANTALLES,
                    "gadgets": model.MAX_GADGETS,
                    "botons": model.MAX_BOTONS,
                    "nom": model.MAX_NOM,
                    "etiqueta": model.MAX_ETIQUETA,
                    "apps": model.MAX_APPS,
                },
            })
        elif path == "/api/exporta":
            # Configuracio portable (sense port ni res d'aquest ordinador).
            self._send(200,
                       json.dumps(model.exporta(BRIDGE.config),
                                  ensure_ascii=False, indent=2),
                       "application/json; charset=utf-8")
        elif path == "/api/elements":
            # Elements tipats d'una pantalla (els fa servir l'editor).
            try:
                idx = int(urlparse(self.path).query.split("=")[-1] or 0)
            except ValueError:
                idx = 0
            self._json({"elements": model.elements_de(BRIDGE.config, idx)})
        elif path == "/api/apps":
            # Apps instal·lades al Mac amb la seva icona (per poder-les
            # assignar a botons). Es un endpoint a part perque recorre les
            # carpetes i llegeix ~150 Info.plist: no el volem a cada /api/state.
            self._json({"apps": apps_instalades()})
        elif path == "/api/captura":
            # Captura de la pantalla de la placa (triga ~40 s: va pel port
            # serie). Serveix per veure de debò com queda.
            png = BRIDGE.captura_png()
            if png:
                self._send(200, png, "image/png")
            else:
                self._json({"ok": False,
                            "error": "no s'ha pogut capturar la pantalla"}, 500)
        elif path.startswith("/icons/"):
            name = os.path.basename(path)      # basename: evita rutes amb ../
            full = os.path.join(ASSETS_ICONS, name)
            if not os.path.isfile(full):
                # Pot ser la icona d'una app instal·lada que encara no s'ha
                # extret mai (el panell en mostra ~70 de cop): la traiem ara
                # mateix, que es rapid, i aixi no surt la icona trencada.
                extreu_icona(os.path.splitext(name)[0])
            if os.path.isfile(full):
                with open(full, "rb") as fh:
                    self._send(200, fh.read(), "image/png")
            else:
                self._send(404, "no trobat", "text/plain; charset=utf-8")
        else:
            self._send(404, "no trobat", "text/plain; charset=utf-8")

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            body = {}

        if path == "/api/config":
            cfg = body.get("config")
            if isinstance(cfg, dict):
                # El model valida, arrodoneix i migra: el que es desa i el que
                # s'envia a la placa es SEMPRE el que torna normalitza().
                ok, problemes = model.valida(cfg)
                desat = save_config(cfg)
                BRIDGE.config = desat
                sent = BRIDGE.send_config()
                if sent:
                    BRIDGE.log("configuracio desada i enviada a la pantalla")
                else:
                    BRIDGE.log("configuracio desada, pero NO s'ha pogut enviar (sense connexio?)")
                self._json({"ok": True, "sent": bool(sent),
                            "avisos": [] if ok else problemes,
                            "connected": BRIDGE.is_connected(), "config": desat})
            else:
                self._json({"ok": False, "error": "config invalid"}, 400)
        elif path == "/api/importa":
            # Configuracio portable: s'importa, es valida i es desa.
            try:
                nou = model.importa(body.get("config"))
            except Exception as exc:
                self._json({"ok": False, "error": "JSON invalid: %s" % exc}, 400)
                return
            ok, problemes = model.valida(nou)
            desat = save_config(nou)
            BRIDGE.config = desat
            BRIDGE.send_config()
            BRIDGE.log("configuracio importada (%d pantalles)" % len(desat["pages"]))
            self._json({"ok": True, "avisos": [] if ok else problemes,
                        "config": desat})
        elif path == "/api/connect":
            ok = BRIDGE.connect(body.get("port") or None)
            self._json({"ok": ok, "port": BRIDGE.port})
        elif path == "/api/disconnect":
            BRIDGE.disconnect()
            self._json({"ok": True})
        elif path == "/api/wifi":
            ok = BRIDGE.set_wifi(body.get("ssid", ""), body.get("pass", ""))
            self._json({"ok": ok})
        elif path == "/api/link":
            ok = BRIDGE.set_link(body.get("link", "serial"), body.get("host") or None)
            save_config(BRIDGE.config)
            self._json({"ok": ok, "connected": BRIDGE.is_connected(),
                        "link": BRIDGE.config.get("link")})
        elif path == "/api/board":
            cmd = str(body.get("cmd", ""))[:80]
            ok = BRIDGE.send_line(cmd) if cmd else False
            if ok:
                BRIDGE.log(f"comanda de placa: {cmd}")
            self._json({"ok": ok})
        elif path == "/api/notify":
            text = body.get("text", "")
            if body.get("app") is not None:
                ok = BRIDGE.send_notice({"app": body.get("app", ""),
                                         "title": body.get("title", text),
                                         "body": body.get("body", "")})
            else:
                ok = BRIDGE.notify(text)
            self._json({"ok": ok})
        elif path == "/api/notifications":
            if "on" in body:
                BRIDGE.notifs_on = bool(body["on"])
                BRIDGE.log("notificacions %s" % ("activades" if BRIDGE.notifs_on
                                                 else "aturades"))
            self._json({"ok": True, "on": BRIDGE.notifs_on,
                        "notifs": list(BRIDGE.notifs.history)[:25]})
        elif path == "/api/icon":
            name = body.get("name", "")
            png_b64 = body.get("png", "")
            try:
                png = base64.b64decode(png_b64)
            except Exception:
                self._json({"ok": False, "error": "PNG invalid"}, 400)
                return
            ok, msg = BRIDGE.upload_icon(name, png)
            self._json({"ok": ok, "error": None if ok else msg, "icons": list_icons()})
        elif path == "/api/icon/delete":
            ok = BRIDGE.delete_icon(body.get("name", ""))
            self._json({"ok": ok, "icons": list_icons()})
        elif path == "/api/test":
            cmd = body.get("cmd")
            if cmd:
                ok = BRIDGE.run_cmd(cmd)
            else:
                ok = BRIDGE.execute(body.get("id", ""))
            self._json({"ok": ok})
        elif path == "/api/send":
            ok = BRIDGE.send_config()
            self._json({"ok": ok})
        else:
            self._send(404, "no trobat", "text/plain; charset=utf-8")


def main():
    global BRIDGE
    ap = argparse.ArgumentParser(description="Mac Panel - panell de control web")
    ap.add_argument("--port", help="port serie (p.ex. /dev/cu.wchusbserial1410)")
    ap.add_argument("--http-port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--headless", action="store_true",
                    help="nomes el pont, sense servidor web")
    ap.add_argument("--no-browser", action="store_true", help="no obrir el navegador")
    args = ap.parse_args()

    cfg = load_config()
    if args.port:
        cfg["port"] = args.port
    BRIDGE = Bridge(cfg)
    BRIDGE.start()

    if args.headless:
        print("Mac Panel en marxa (headless). Ctrl+C per sortir.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            BRIDGE.stop()
        return

    httpd = ThreadingHTTPServer((HOST, args.http_port), Handler)
    url = f"http://{HOST}:{args.http_port}/"
    print(f"Mac Panel - panell de control: {url}")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        BRIDGE.stop()
        print("\nFins aviat.")


if __name__ == "__main__":
    main()
