#!/bin/sh
# Starts the Toolkit Installer window - and says WHY, in a window, when it cannot.
#
#   sh installer/start.sh                              open the window
#   sh installer/start.sh --make-launcher              make a double-click icon (start-installer.desktop) for THIS folder
#   sh installer/start.sh --make-launcher --desktop    ... and put a copy on the Desktop
#
# Works from any folder and on a fresh system: it needs nothing but sh and python3 (tkinter is installed on the first run
# by the window itself, with a graphical password prompt). Run it with `sh`, so no executable bit is needed either.
set -u
here="$(dirname "$(readlink -f "$0")")"
root="$(dirname "$here")"
log="${XDG_CACHE_HOME:-$HOME/.cache}/linux-scripts/start.log"

say() {   # a window when there is a display and a tool for it, else the terminal
  if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v zenity >/dev/null 2>&1; then
    zenity --error --width=520 --no-markup --title="Toolkit Installer" --text="$1" 2>/dev/null && return
  fi
  if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v xmessage >/dev/null 2>&1; then
    xmessage -center "$1" 2>/dev/null && return
  fi
  printf '%s\n' "$1" >&2
}

make_launcher() {
  f="$root/start-installer.desktop"
  cat > "$f" <<DESK
[Desktop Entry]
Type=Application
Name=Install apps (Toolkit Installer)
Name[ka]=პროგრამების დაყენება (ხელსაწყოების დამყენებელი)
Comment=Tick programs and install them with one click · მონიშნეთ პროგრამები და დააყენეთ
Exec=sh "$here/start.sh"
Path=$root
Icon=system-software-install
Terminal=false
Categories=System;Utility;
DESK
  chmod 755 "$f"
  command -v gio >/dev/null 2>&1 && gio set "$f" metadata::trusted true 2>/dev/null
  echo "double-click launcher: $f"
  if [ "${1:-}" = "--desktop" ]; then
    desk="$(xdg-user-dir DESKTOP 2>/dev/null || true)"; [ -n "$desk" ] || desk="$HOME/Desktop"
    if [ -d "$desk" ]; then
      cp "$f" "$desk/start-installer.desktop" && chmod 755 "$desk/start-installer.desktop"
      command -v gio >/dev/null 2>&1 && gio set "$desk/start-installer.desktop" metadata::trusted true 2>/dev/null
      echo "copy on the Desktop: $desk/start-installer.desktop"
    fi
  fi
}

if [ "${1:-}" = "--make-launcher" ]; then
  make_launcher "${2:-}"
  exit 0
fi

command -v python3 >/dev/null 2>&1 || {
  say "python3 is not installed.

Open a terminal and run:
  sudo apt install python3"
  exit 1
}
[ -f "$here/installer-gui.py" ] || { say "installer-gui.py was not found next to start.sh ($here). Was the folder copied incompletely?"; exit 1; }

mkdir -p "$(dirname "$log")" 2>/dev/null
if ! python3 "$here/installer-gui.py" "$@" >"$log" 2>&1; then
  say "The installer window could not start.

$(tail -n 12 "$log" 2>/dev/null)

(full log: $log)
Try in a terminal:  python3 $here/installer-gui.py"
  exit 1
fi
