#!/usr/bin/env bash
# Install / uninstall the tools: commands in PREFIX/bin, menu entries in PREFIX/share/applications,
# shared helper in PREFIX/lib/linux-scripts.      ./install.sh --help
set -euo pipefail

PREFIX=/usr/local
ACTION=install
DESKTOP_ICONS=0
FOLDER_LAUNCHERS=0
TOOLS=()
here="$(cd "$(dirname "$0")" && pwd)"

# tool -> "source|command-name" ... ; desktop file (or -)
declare -A FILES=(
  [usb-eject]="usb-eject/usb-eject.sh|usb-eject usb-eject/usb-eject-gui.py|usb-eject-gui"
  [wifi-hotspot]="wifi-hotspot/hotspot.sh|hotspot wifi-hotspot/hotspot-gui.py|hotspot-gui"
  [printer-setup]="printer-setup/printer-setup-gui.py|printer-setup"
  [qgis-installer]="qgis-installer/qgis-installer-gui.py|qgis-installer qgis-installer/qgis-installer-cli.py|qgis-installer-cli"
  [bluetooth-setup]="bluetooth-setup/bluetooth-setup-gui.py|bluetooth-setup"
  [printhub]="printhub/printhub-launcher.sh|printhub"   # not part of "all": the app + PySide6 are installed too
)
declare -A GUISCRIPT=(
  [usb-eject]=usb-eject/usb-eject-gui.py
  [wifi-hotspot]=wifi-hotspot/hotspot-gui.py
  [printer-setup]=printer-setup/printer-setup-gui.py
  [qgis-installer]=qgis-installer/qgis-installer-gui.py
  [bluetooth-setup]=bluetooth-setup/bluetooth-setup-gui.py
  [printhub]=printhub/run.py
)
declare -A DESKTOP=(
  [usb-eject]=usb-eject/usb-eject-gui.desktop
  [wifi-hotspot]=wifi-hotspot/hotspot-gui.desktop
  [printer-setup]=printer-setup/printer-setup.desktop
  [qgis-installer]=qgis-installer/qgis-installer.desktop
  [bluetooth-setup]=bluetooth-setup/bluetooth-setup.desktop
  [printhub]=printhub/packaging/linux/printhub.desktop
)
ALL=(usb-eject wifi-hotspot printer-setup qgis-installer bluetooth-setup)

usage() {
  cat <<U
Usage: ./install.sh [--prefix DIR] [--uninstall] TOOL...|all
Tools: ${ALL[*]}
       printhub   (print front-end; not part of 'all' - needs PySide6, ~200 MB when the system has none)
  --prefix DIR   install under DIR instead of /usr/local
  --desktop      also put a clickable launcher on your Desktop
  --folders      also put a double-click launcher inside each tool's folder here
                 (runs straight from this checkout; re-run if you move the folder)
  --uninstall    remove what install put there (add --desktop / --folders to remove those launchers too)
Uses sudo automatically when DIR is not writable.
U
}

while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="$2"; shift 2;;
    --uninstall) ACTION=uninstall; shift;;
    --desktop) DESKTOP_ICONS=1; shift;;
    --folders) FOLDER_LAUNCHERS=1; shift;;
    -h|--help) usage; exit 0;;
    all) TOOLS+=("${ALL[@]}"); shift;;
    *) [[ -n "${FILES[$1]:-}" ]] || { echo "Unknown tool: $1"; usage; exit 1; }; TOOLS+=("$1"); shift;;
  esac
done
[ ${#TOOLS[@]} -gt 0 ] || { usage; exit 1; }

case "$PREFIX" in /*) ;; *) PREFIX="$PWD/$PREFIX" ;; esac   # portable (busybox realpath has no -m)
PREFIX="${PREFIX%/}"
DESKDIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
SUDO=""
probe="$PREFIX"; while [ ! -e "$probe" ]; do probe="$(dirname "$probe")"; done
[ -w "$probe" ] || SUDO="sudo"

# PrintHub is an application, not a single script: copy the package, give it PySide6 (system one, else a private
# venv), install the icon.  The launcher and the menu entry go through the generic loop below.
printhub_extra() {
  local app="$PREFIX/lib/printhub" icon="$PREFIX/share/icons/hicolor/256x256/apps/io.printhub.PrintHub.png"
  if [ "$ACTION" = install ]; then
    command -v python3 >/dev/null || { echo "python3 is required for PrintHub"; exit 1; }
    $SUDO rm -rf "$app/printhub"; $SUDO mkdir -p "$app"
    $SUDO cp -r "$here/printhub/printhub" "$app/printhub"
    $SUDO find "$app/printhub" -name __pycache__ -prune -exec rm -rf {} +
    if python3 -c 'import PySide6' 2>/dev/null; then
      echo "PySide6 found on the system - no private environment needed"
    else
      echo "Creating a private Python environment with PySide6 (downloads about 200 MB)..."
      $SUDO python3 -m venv "$app/venv" || { echo "python3-venv is missing (Debian/Ubuntu: sudo apt install python3-venv)"; exit 1; }
      $SUDO "$app/venv/bin/pip" install --quiet --disable-pip-version-check "PySide6>=6.6"
    fi
    $SUDO install -D -m 644 "$here/printhub/packaging/assets/printhub.png" "$icon"
    echo "installed PrintHub into $app"
  else
    $SUDO rm -rf "$app"; $SUDO rm -f "$icon"; echo "removed $app"
  fi
}

for tool in "${TOOLS[@]}"; do
  [ "$tool" = printhub ] && printhub_extra
  for pair in $(echo "${FILES[$tool]}" | tr ' ' '\n' | sed 's/|/,/'); do
    src="${pair%%,*}"; cmd="${pair##*,}"
    if [ "$ACTION" = install ]; then
      $SUDO install -D -m 755 "$here/$src" "$PREFIX/bin/$cmd"; echo "installed $PREFIX/bin/$cmd"
    else
      $SUDO rm -f "$PREFIX/bin/$cmd"; echo "removed $PREFIX/bin/$cmd"
    fi
  done
  d="${DESKTOP[$tool]}"; dname="$(basename "$d")"
  if [ "$ACTION" = install ]; then
    # absolute Exec= so a menu/desktop click works even when PREFIX/bin is not in the session's PATH
    tmp="$(mktemp)"; sed "s#^Exec=#Exec=$PREFIX/bin/#" "$here/$d" > "$tmp"
    $SUDO install -D -m 644 "$tmp" "$PREFIX/share/applications/$dname"
    if [ "$DESKTOP_ICONS" = 1 ] && [ -d "$DESKDIR" ]; then
      install -m 755 "$tmp" "$DESKDIR/$dname"
      command -v gio >/dev/null && gio set "$DESKDIR/$dname" metadata::trusted true 2>/dev/null || true
      echo "launcher on Desktop: $DESKDIR/$dname"
    fi
    rm -f "$tmp"
  else
    $SUDO rm -f "$PREFIX/share/applications/$dname"
    [ "$DESKTOP_ICONS" = 1 ] && rm -f "$DESKDIR/$dname"
  fi
  # double-click launcher in the tool's own folder (absolute path to this checkout)
  flaunch="$here/$(dirname "$d")/start-${dname%.desktop}.desktop"
  if [ "$ACTION" = install ] && [ "$FOLDER_LAUNCHERS" = 1 ]; then
    {
      sed -n '/^\[Desktop Entry\]/,$p' "$here/$d" | grep -v -E '^(Exec|Path)='
      echo "Exec=python3 ${here}/${GUISCRIPT[$tool]}"
      echo "Path=$here/$(dirname "$d")"
    } > "$flaunch"
    chmod 755 "$flaunch"
    command -v gio >/dev/null && gio set "$flaunch" metadata::trusted true 2>/dev/null || true
    echo "double-click launcher: $flaunch"
  elif [ "$ACTION" = uninstall ] && [ "$FOLDER_LAUNCHERS" = 1 ]; then
    rm -f "$flaunch"
  fi
done

if [ "$ACTION" = install ]; then
  for m in lscommon lsqr; do
    $SUDO install -D -m 644 "$here/common/$m.py" "$PREFIX/lib/linux-scripts/$m.py"
  done
  # the qgis_installer package (logic shared by qgis-installer and qgis-installer-cli)
  case " ${TOOLS[*]} " in
    *" qgis-installer "*)
      for f in "$here"/qgis-installer/qgis_installer/*.py; do
        $SUDO install -D -m 644 "$f" "$PREFIX/lib/linux-scripts/qgis_installer/$(basename "$f")"
      done;;
  esac
fi
if [ "$ACTION" = uninstall ]; then
  case " ${TOOLS[*]} " in *" qgis-installer "*) $SUDO rm -rf "$PREFIX/lib/linux-scripts/qgis_installer";; esac
  guis=0; for g in usb-eject-gui hotspot-gui printer-setup qgis-installer qgis-installer-cli bluetooth-setup; do [ -e "$PREFIX/bin/$g" ] && guis=1; done
  [ "$guis" = 0 ] && $SUDO rm -rf "$PREFIX/lib/linux-scripts" && echo "removed shared helper"
fi
command -v update-desktop-database >/dev/null && $SUDO update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true
echo "Done."
