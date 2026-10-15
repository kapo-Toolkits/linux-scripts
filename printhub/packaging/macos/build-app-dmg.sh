#!/usr/bin/env bash
# Build PrintHub.app and a .dmg on macOS.
#
# Requires: python3, and (for the .dmg) either `create-dmg` (brew install
# create-dmg) or the built-in hdiutil fallback below.
#
# Usage:  packaging/macos/build-app-dmg.sh [version]
set -euo pipefail

VERSION="${1:-0.2.1}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo ">> Preparing .icns icon"
ICONSET="$(mktemp -d)/printhub.iconset"
mkdir -p "$ICONSET"
for s in 16 32 64 128 256 512; do
  sips -z $s $s packaging/assets/printhub.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) packaging/assets/printhub.png \
       --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o packaging/assets/printhub.icns

echo ">> Building PrintHub.app with PyInstaller"
python3 -m pip install --upgrade pyinstaller PySide6
pyinstaller --noconfirm packaging/printhub.spec    # -> dist/PrintHub.app

echo ">> Creating disk image"
if command -v create-dmg >/dev/null 2>&1; then
  create-dmg --volname "PrintHub $VERSION" --app-drop-link 480 170 \
    "dist/PrintHub-$VERSION.dmg" "dist/PrintHub.app"
else
  hdiutil create -volname "PrintHub $VERSION" -srcfolder "dist/PrintHub.app" \
    -ov -format UDZO "dist/PrintHub-$VERSION.dmg"
fi

echo ">> Done: dist/PrintHub-$VERSION.dmg"
echo "   (unsigned; for distribution, codesign + notarize the .app first)"
