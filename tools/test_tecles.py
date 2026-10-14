#!/usr/bin/env python3
"""test_tecles.py - comprova DE VERITAT quines tecles escriu la placa al Mac.

Els codis HID de Bluetooth son POSICIONS FISIQUES del teclat, no caracters, i
per tant el resultat depen de la distribucio de teclat del Mac. Aquesta prova
ho mesura de debò:

  1. Obre un fitxer buit amb TextEdit (que te el focus).
  2. Envia les tecles des de la placa per la consola ('tecla <nom>').
  3. Selecciona-ho tot (cmd+a) i ho copia (cmd+c).
  4. Llegeix el porta-retalls amb 'pbpaste'.

Aixi veiem EXACTAMENT quin caracter ha escrit cada tecla amb la distribucio real
del Mac. No cal cap permis especial (cmd+c es una tecla normal).

Us:
    python3 tools/test_tecles.py [/dev/cu.usbserial-XXXX]
"""
import os
import re
import subprocess
import sys
import time

import serial

from comu import troba_port

FITXER = "/tmp/macpanel_tecles.txt"

# (nom de la tecla, caracter que hi hauria d'escriure)
# Son EXACTAMENT les que envia el teclat numeric de la pantalla.
PROVES = [
    ("kp_7", "7"), ("kp_8", "8"), ("kp_9", "9"), ("kp_minus", "-"),
    ("kp_4", "4"), ("kp_5", "5"), ("kp_6", "6"), ("kp_plus", "+"),
    ("kp_1", "1"), ("kp_2", "2"), ("kp_3", "3"), ("kp_star", "*"),
    ("kp_0", "0"), (".", "."), ("kp_slash", "/"),
]

SUBR = {
    "SmartQuotes": "false",
    "SmartDashes": "false",
    "SmartLinks": "false",
    "CorrectSpellingAutomatically": "false",
}


def sh(cmd, **kw):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=10, **kw).stdout
    except Exception:
        return ""


def frontmost():
    """Nom de l'aplicacio que te el focus."""
    asn = sh(["lsappinfo", "front"]).strip()
    if not asn.startswith("ASN:"):
        return ""
    out = sh(["lsappinfo", "info", "-only", "name", asn.split()[0]])
    m = re.search(r'"LSDisplayName"="([^"]*)"', out)
    return m.group(1) if m else ""


def restaura(previs):
    """Torna les preferencies del TextEdit que haviem canviat."""
    for k, v in previs.items():
        if v is None:
            sh(["defaults", "delete", "com.apple.TextEdit", k])
        else:
            sh(["defaults", "write", "com.apple.TextEdit", k, "-bool",
                "true" if v == "1" else "false"])
    sh(["killall", "TextEdit"])          # que les torni a llegir
    try:
        os.remove(FITXER)
    except OSError:
        pass


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else (troba_port() or
                                                  "/dev/cu.usbserial-1420")
    print("port:", port)

    # --- TextEdit sense substitucions "intel·ligents" ---------------------
    # Si no, TextEdit converteix el '-' en un guio llarg i la prova enganyaria.
    # Desem els valors que tenia per tornar-los al final.
    previs = {}
    for k in SUBR:
        v = sh(["defaults", "read", "com.apple.TextEdit", k]).strip()
        previs[k] = v if v in ("0", "1") else None
        sh(["defaults", "write", "com.apple.TextEdit", k, "-bool",
            SUBR[k]])

    open(FITXER, "w").close()
    sh(["killall", "TextEdit"])
    time.sleep(1)
    sh(["open", "-a", "TextEdit", FITXER])
    time.sleep(3)

    qui = frontmost()
    if "TextEdit" not in qui:
        # Molt important: si no te el focus, les tecles s'escriurien al
        # TERMINAL i podrien executar una ordre. Val mes no enviar res.
        print("!! TextEdit no te el focus (ara el te: '%s')." % (qui or "?"))
        print("!! No envio cap tecla, per seguretat.")
        return 2
    print("TextEdit te el focus, endavant")

    # --- La placa ---------------------------------------------------------
    ser = serial.Serial(port, 115200, timeout=0.2)
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass
    ser.reset_input_buffer()

    def llegeix(segons):
        fi = time.time() + segons
        out = ""
        while time.time() < fi:
            d = ser.read(4096)
            if d:
                out += d.decode("utf-8", "replace")
        return out

    llegeix(8)                       # que arrenqui i s'encengui el Bluetooth

    # --- Comprovem que el teclat Bluetooth esta a punt --------------------
    # Si enviem tecles abans que el Bluetooth estigui connectat, les primeres
    # es perden i la prova dona un resultat fals.
    ser.reset_input_buffer()
    ser.write(b"tecles\n")
    txt = llegeix(2)
    if "noms de tecles" not in txt:
        print("!! la placa no respon a la comanda 'tecles'")
        ser.close()
        restaura(previs)
        return 1
    print("la placa respon OK")

    print("espero que el teclat Bluetooth estigui connectat...")
    connectat = False
    for _ in range(20):
        ser.reset_input_buffer()
        ser.write(b"bt\n")
        txt = llegeix(1.5)
        if "connectat al Mac" in txt:
            connectat = True
            break
        if "encara no engegat" in txt:
            time.sleep(1.5)
            continue
        time.sleep(1.5)
    if not connectat:
        print("!! el teclat Bluetooth no s'ha connectat al Mac.")
        print("   Emparella 'Mac Panel' a Preferencies > Bluetooth i torna-ho a provar.")
        ser.close()
        restaura(previs)
        return 3
    print("teclat Bluetooth connectat")
    time.sleep(1.0)

    # --- Enviem les tecles ------------------------------------------------
    print("\n>>> envio %d tecles des de la placa..." % len(PROVES))
    registre = ""
    for nom, _ in PROVES:
        ser.write(("tecla %s\n" % nom).encode())
        time.sleep(0.25)
        registre += llegeix(0.15)
    time.sleep(0.5)

    # --- Ho copiem al porta-retalls --------------------------------------
    for tecla in ("cmd+a", "cmd+c"):
        ser.write(("tecla %s\n" % tecla).encode())
        time.sleep(0.4)
    time.sleep(1.0)

    escrit = sh(["pbpaste"])
    ser.close()
    restaura(previs)

    print("\n--- que ha dit la placa ---")
    for l in registre.splitlines():
        if "[BT]" in l:
            print("   ", l.strip())

    esperat = "".join(c for _, c in PROVES)
    print("\nesperat: %r" % esperat)
    print("escrit : %r" % escrit)
    print()
    if escrit.strip() == esperat:
        print("=== RESULTAT: CORRECTE (les %d tecles escriuen el que toca) ==="
              % len(PROVES))
        print()
        print("Nota: 'kp_dot' (el punt DEL BLOC NUMERIC) dona ',' en aquesta")
        print("distribucio, perque macOS el tradueix al separador decimal.")
        print("Per aixo el teclat numeric de la pantalla fa servir '.' normal.")
        return 0
    print("=== RESULTAT: HI HA DIFERENCIES ===")
    for i, (nom, c) in enumerate(PROVES):
        real = escrit[i] if i < len(escrit) else "(res)"
        if real != c:
            print("   %-10s esperava %r i ha escrit %r" % (nom, c, real))
    return 1


if __name__ == "__main__":
    sys.exit(main())
