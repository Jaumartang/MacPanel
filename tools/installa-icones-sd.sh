#!/bin/bash
# Copia les icones .bin a la targeta SD de l'ESP32.
#
#   1) Munta la targeta SD al Mac (apareixera a /Volumes/<NOM>)
#   2) Executa:   bash tools/installa-icones-sd.sh
#
# Si tens mes d'un volum muntat, passa-li el nom:
#   bash tools/installa-icones-sd.sh SDCARD

set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$DIR/Assets/icons/bin"

if [ ! -d "$SRC" ] || [ -z "$(ls -A "$SRC" 2>/dev/null)" ]; then
    echo "No hi ha icones convertides. Executa abans:"
    echo "  python3 tools/gen_sample_icons.py     (opcional: crea icones de mostra)"
    echo "  python3 tools/png2bin.py"
    exit 1
fi

VOL="$1"
if [ -z "$VOL" ]; then
    VOL=$(ls -d /Volumes/* 2>/dev/null | grep -v -E 'Macintosh HD|com\.apple' | head -1)
fi
if [ -z "$VOL" ] || [ ! -d "$VOL" ]; then
    echo "No s'ha trobat cap volum a /Volumes. Munta la targeta SD i torna-ho a provar."
    echo "Volums disponibles:"; ls -d /Volumes/* 2>/dev/null
    exit 1
fi

DEST="$VOL/icons"
mkdir -p "$DEST"
cp -v "$SRC"/*.bin "$DEST"/
sync
echo
echo "Fet! $(ls "$DEST"/*.bin | wc -l | tr -d ' ') icones copiades a $DEST"
echo "Treu la SD del Mac i posa-la a l'ESP32."
