#!/bin/bash
# Crea (o refa) els accessos directes de l'Escriptori per engegar i aturar el
# panell de control. Nomes cal tornar-lo a executar si mous el projecte.
#
#   bash mac/crea-llancadors.sh

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
DESK="$HOME/Desktop"

crea_app() {
    # $1 = nom del paquet .app ; $2 = nom de l'executable
    # $3 = bundle identifier ; $4 = script a executar
    local APP="$DESK/$1"
    local EXE="$2"
    mkdir -p "$APP/Contents/MacOS"

    cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>$1</string>
    <key>CFBundleDisplayName</key><string>$1</string>
    <key>CFBundleIdentifier</key><string>$3</string>
    <key>CFBundleExecutable</key><string>$EXE</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleVersion</key><string>1.0</string>
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>LSMinimumSystemVersion</key><string>10.13</string>
    <key>LSUIElement</key><true/>
    <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

    printf 'APPL????' > "$APP/Contents/PkgInfo"

    cat > "$APP/Contents/MacOS/$EXE" <<RUN
#!/bin/bash
exec "$4"
RUN

    chmod +x "$APP/Contents/MacOS/$EXE"
    chmod 755 "$APP"
    echo "creat: $APP"
}

crea_app "Mac Panel.app"       "MacPanel" "local.macpanel.launcher" "$DIR/engega-panell.sh"
crea_app "Atura Mac Panel.app" "Atura"    "local.macpanel.stop"     "$DIR/atura-panell.sh"

echo
echo "Fet! Ja pots fer doble clic a \"Mac Panel\" a l'Escriptori."
