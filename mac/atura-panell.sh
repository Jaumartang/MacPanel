#!/bin/bash
# Atura el panell de control del Mac Panel.

notify() { osascript -e "display notification \"$1\" with title \"Mac Panel\"" >/dev/null 2>&1; }

PIDS=$(pgrep -f "mac/panel_server.py" 2>/dev/null)
if [ -n "$PIDS" ]; then
    kill $PIDS 2>/dev/null
    sleep 1
    pkill -f "mac/panel_server.py" 2>/dev/null
    notify "El panell del Mac s'ha aturat."
else
    notify "El panell del Mac no estava en marxa."
fi
exit 0
