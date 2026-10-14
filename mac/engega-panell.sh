#!/bin/bash
# Engega el panell de control del Mac Panel: arrenca el servidor en segon pla i
# obre el navegador. El fan servir l'acces directe de l'Escriptori i
# mac/EngegaPanell.command.

DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(cd "$DIR/.." && pwd)"
URL="http://127.0.0.1:8770/"
LOG="$DIR/panel.log"

alert() { osascript -e "display alert \"Mac Panel\" message \"$1\"" >/dev/null 2>&1; }

# Si el panell ja funciona, nomes obrim el navegador.
if curl -s --max-time 2 -o /dev/null "$URL"; then
    open "$URL"
    exit 0
fi

# Busca un Python 3 amb pyserial (el Finder no hereta el PATH del terminal).
PY=""
for CAND in \
    "$HOME/miniforge3/bin/python3" \
    "$HOME/anaconda3/bin/python3" \
    "/opt/homebrew/bin/python3" \
    "/usr/local/bin/python3" \
    "$(command -v python3 2>/dev/null)" \
    "/usr/bin/python3"; do
    if [ -n "$CAND" ] && [ -x "$CAND" ] && "$CAND" -c 'import serial' 2>/dev/null; then
        PY="$CAND"
        break
    fi
done

if [ -z "$PY" ]; then
    alert "No s'ha trobat cap Python 3 amb pyserial. Instal.la'l amb: python3 -m pip install -r mac/requirements.txt"
    exit 1
fi

cd "$PROJECT" 2>/dev/null || { alert "No s'ha trobat el projecte a: $PROJECT"; exit 1; }

# Arrenca el servidor en segon pla (sobreviu al tancament d'aquest llancador).
nohup "$PY" mac/panel_server.py --no-browser > "$LOG" 2>&1 < /dev/null &
disown

# Espera que respongui i obre el navegador.
for _ in $(seq 1 25); do
    if curl -s --max-time 1 -o /dev/null "$URL"; then
        open "$URL"
        exit 0
    fi
    sleep 0.4
done

alert "El servidor no ha respost. Revisa el fitxer mac/panel.log"
exit 1
