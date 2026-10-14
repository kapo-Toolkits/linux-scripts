#!/usr/bin/env bash
# Install / uninstall the tools: commands in PREFIX/bin, menu entries in PREFIX/share/applications,
# shared helper in PREFIX/lib/linux-scripts.      ./install.sh --help
set -euo pipefail

PREFIX=/usr/local
ACTION=install
TOOLS=()
here="$(cd "$(dirname "$0")" && pwd)"

# tool -> "source|command-name" ... ; desktop file (or -)
declare -A FILES=(
  [usb-eject]="usb-eject/usb-eject.sh|usb-eject usb-eject/usb-eject-gui.py|usb-eject-gui"
  [wifi-hotspot]="wifi-hotspot/hotspot.sh|hotspot wifi-hotspot/hotspot-gui.py|hotspot-gui"
  [printer-setup]="printer-setup/printer-setup-gui.py|printer-setup"
  [qgis-installer]="qgis-installer/qgis-installer-gui.py|qgis-installer"
)
declare -A DESKTOP=(
  [usb-eject]=usb-eject/usb-eject-gui.desktop
  [wifi-hotspot]=wifi-hotspot/hotspot-gui.desktop
  [printer-setup]=printer-setup/printer-setup.desktop
  [qgis-installer]=qgis-installer/qgis-installer.desktop
)
ALL=(usb-eject wifi-hotspot printer-setup qgis-installer)

usage() {
  cat <<U
Usage: ./install.sh [--prefix DIR] [--uninstall] TOOL...|all
Tools: ${ALL[*]}
  --prefix DIR   install under DIR instead of /usr/local
  --uninstall    remove what install put there
Uses sudo automatically when DIR is not writable.
U
}

while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="$2"; shift 2;;
    --uninstall) ACTION=uninstall; shift;;
    -h|--help) usage; exit 0;;
    all) TOOLS+=("${ALL[@]}"); shift;;
    *) [[ -n "${FILES[$1]:-}" ]] || { echo "Unknown tool: $1"; usage; exit 1; }; TOOLS+=("$1"); shift;;
  esac
done
[ ${#TOOLS[@]} -gt 0 ] || { usage; exit 1; }

SUDO=""
probe="$PREFIX"; while [ ! -e "$probe" ]; do probe="$(dirname "$probe")"; done
[ -w "$probe" ] || SUDO="sudo"

for tool in "${TOOLS[@]}"; do
  for pair in $(echo "${FILES[$tool]}" | tr ' ' '\n' | sed 's/|/,/'); do
    src="${pair%%,*}"; cmd="${pair##*,}"
    if [ "$ACTION" = install ]; then
      $SUDO install -D -m 755 "$here/$src" "$PREFIX/bin/$cmd"; echo "installed $PREFIX/bin/$cmd"
    else
      $SUDO rm -f "$PREFIX/bin/$cmd"; echo "removed $PREFIX/bin/$cmd"
    fi
  done
  d="${DESKTOP[$tool]}"
  if [ "$ACTION" = install ]; then
    $SUDO install -D -m 644 "$here/$d" "$PREFIX/share/applications/$(basename "$d")"
  else
    $SUDO rm -f "$PREFIX/share/applications/$(basename "$d")"
  fi
done

if [ "$ACTION" = install ]; then
  for m in lscommon lsqr; do
    $SUDO install -D -m 644 "$here/common/$m.py" "$PREFIX/lib/linux-scripts/$m.py"
  done
fi
if [ "$ACTION" = uninstall ]; then
  guis=0; for g in usb-eject-gui hotspot-gui printer-setup qgis-installer; do [ -e "$PREFIX/bin/$g" ] && guis=1; done
  [ "$guis" = 0 ] && $SUDO rm -rf "$PREFIX/lib/linux-scripts" && echo "removed shared helper"
fi
command -v update-desktop-database >/dev/null && $SUDO update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true
echo "Done."
