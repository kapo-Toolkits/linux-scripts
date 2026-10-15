#!/usr/bin/env bash
# Build PrintHub .deb and .rpm on Linux.
#
# Requires: python3, pip, and fpm (https://fpm.readthedocs.io).
#   gem install --no-document fpm     # fpm itself
#   # rpm building also needs the `rpmbuild` tool (rpm package)
#
# Usage:  packaging/linux/build-deb-rpm.sh [version]
set -euo pipefail

VERSION="${1:-0.2.1}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo ">> Building standalone bundle with PyInstaller"
python3 -m pip install --upgrade pyinstaller PySide6
pyinstaller --noconfirm packaging/printhub.spec   # -> dist/PrintHub/

echo ">> Staging file tree"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

install -d "$STAGE/opt/printhub"
cp -r dist/PrintHub/. "$STAGE/opt/printhub/"
install -d "$STAGE/usr/bin"
ln -sf /opt/printhub/PrintHub "$STAGE/usr/bin/printhub"
install -Dm644 packaging/linux/printhub.desktop \
    "$STAGE/usr/share/applications/io.printhub.PrintHub.desktop"
install -Dm644 packaging/assets/printhub.png \
    "$STAGE/usr/share/icons/hicolor/256x256/apps/io.printhub.PrintHub.png"
install -Dm644 packaging/linux/io.printhub.PrintHub.metainfo.xml \
    "$STAGE/usr/share/metainfo/io.printhub.PrintHub.metainfo.xml"

COMMON=(
  -s dir -n printhub -v "$VERSION" --license MIT
  --description "Universal cross-platform print front-end (PDF, images, Office)."
  --url "https://github.com/printhub/printhub"
  --category utils -a native
)

echo ">> Packaging .deb"
# LibreOffice is only needed for Office files -> a Recommends, not a hard dep.
fpm "${COMMON[@]}" -t deb --deb-recommends libreoffice-core -C "$STAGE" .

echo ">> Packaging .rpm"
fpm "${COMMON[@]}" -t rpm -C "$STAGE" .

echo ">> Done:"
ls -1 ./*.deb ./*.rpm
