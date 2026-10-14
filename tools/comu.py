#!/usr/bin/env python3
"""comu.py - utilitats compartides per als tools de prova.

El mes important es `Enllac`: des que la placa nomes ensenya el rellotge i els
ajustos quan no te enllac, les proves de pantalles necessiten que algu els hi
enviï linies 'S' (com fa el pont del Mac). Sense aixo les proves passarien pero
no provarien res, perque la placa dibuixaria el rellotge en lloc de la pantalla.

Tambe porta el pany d'escriptura, perque les linies 'S' del fil de fons i les
comandes de la prova no es barregin pel port.
"""
import glob
import threading
import time

MINUT_INICIAL = 12


def troba_port():
    """Primer port USB-serie que trobi (o None)."""
    for pat in ("/dev/cu.usbserial-*", "/dev/cu.wchusbserial*"):
        candidats = sorted(glob.glob(pat))
        if candidats:
            return candidats[0]
    return None


def linia_stats(minut=0, host="Mac", dark=None):
    """Una linia d'estadistiques com les que envia el pont del Mac.

    'host' es pot canviar per provar noms llargs (la capcalera fa marquesina) i
    'dark' (0 o 1) per provar el tema automatic (si es None no s'hi posa).
    """
    dk = "" if dark is None else "dk=%d " % dark
    return ("S cpu=10 mem=20 disk=30 bat=80 chg=1 host=%s "
            "time=%02d:%02d date=01/01 wc=1 isd=1 dsp=1 %sidl=0 temp=20 "
            "up=0 dn=0 load=1 uptime=100\n"
            % (host, (MINUT_INICIAL + minut // 60) % 24, minut % 60, dk))


class Enllac:
    """Mante l'enllac viu enviant linies 'S' cada 'periode' segons."""
    def __init__(self, ser, periode=0.6, host="Mac", dark=None):
        self.ser = ser
        self.periode = periode
        self.host = host
        self.dark = dark
        self.lock = threading.Lock()
        self._fi = False
        self._fil = None
        self.minut = 0

    def _bucle(self):
        while not self._fi:
            try:
                with self.lock:
                    self.ser.write(linia_stats(self.minut, self.host,
                                               self.dark).encode())
                self.minut += 1
            except Exception:
                return
            time.sleep(self.periode)

    def comenca(self):
        """Engega (o torna a engegar) el fil de fons."""
        self._fi = False                  # permet tornar-lo a engegar
        self._fil = threading.Thread(target=self._bucle, daemon=True)
        self._fil.start()
        return self

    def atura(self):
        self._fi = True

    def envia(self, cmd):
        """Escriu una comanda sense que es barregi amb les linies 'S'."""
        if isinstance(cmd, str):
            cmd = cmd.encode()
        with self.lock:
            self.ser.write(cmd)


def mida_pantalla(enllac, drain):
    """(W, H) de la placa segons la seva orientacio.

    Les proves que toquen coordenades ho han de saber: en horitzontal la
    pantalla es 480x320 i tot es reparteix diferent.
    """
    enllac.envia("cfg\n")
    ori = "v"
    for l in drain(1.2):
        if "orientacio=" in l:
            ori = l.split("orientacio=")[1].split()[0]
    return (480, 320) if ori[:1] == "h" else (320, 480)

