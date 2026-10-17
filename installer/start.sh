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

# No dialog tool (zenity) and no terminal: open a terminal window and carry on there, so the question is always visible.
reopen_in_terminal() {
  [ "${TOOLKIT_IN_TERMINAL:-}" = 1 ] && return 1
  [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] || return 1
  keep='sh "$0" "$@"; rc=$?; if [ $rc -ne 0 ]; then echo; echo "Press Enter to close / დახურვისთვის დააჭირეთ Enter-ს"; read -r _; fi; exit $rc'
  for t in xfce4-terminal gnome-terminal mate-terminal konsole xterm x-terminal-emulator; do
    command -v "$t" >/dev/null 2>&1 || continue
    case "$t" in
      xfce4-terminal|mate-terminal) flag="-x" ;;
      gnome-terminal)               flag="--" ;;
      *)                            flag="-e" ;;
    esac
    TOOLKIT_IN_TERMINAL=1 "$t" "$flag" sh -c "$keep" "$here/start.sh" "$@" && return 0
  done
  return 1
}

ask() {   # yes/no: a window with a display, else the terminal; TOOLKIT_ASSUME_YES=1 answers yes (tests, scripts)
  [ "${TOOLKIT_ASSUME_YES:-}" = 1 ] && return 0
  if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v zenity >/dev/null 2>&1; then
    zenity --question --width=520 --no-markup --title="Toolkit Installer" --text="$1" 2>/dev/null
    return $?
  fi
  if [ -t 0 ]; then
    printf '%s [Y/n] ' "$1" >&2
    read -r a
    case "$a" in ""|y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
  fi
  if reopen_in_terminal "$@"; then exit 0; fi       # the terminal window took over; this (invisible) copy is done
  return 1
}

progress_start() {   # a pulsing "working..." window while the installation runs (closed by progress_stop)
  { [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v zenity >/dev/null 2>&1; } || return 0
  pf="$(mktemp -u)" && mkfifo "$pf" || return 0
  zenity --progress --pulsate --no-cancel --auto-close --width=420 --title="Toolkit Installer" \
    --text="$1" <"$pf" 2>/dev/null &
  exec 3>"$pf"
  rm -f "$pf"
}
progress_stop() { exec 3>&-; }   # closing the pipe ends the window (zenity --auto-close)

# python3 and tkinter are all the window needs.  If either is missing: ask, install it, and carry on.
install_python() {   # $1 = what is missing: python3 | tkinter
  for m in apt-get dnf pacman zypper apk; do command -v "$m" >/dev/null 2>&1 && pm="$m" && break; done
  case "${pm:-}" in
    apt-get) cmd="apt-get install -y python3 python3-tk || (apt-get update && apt-get install -y python3 python3-tk)" ;;
    dnf)     cmd="dnf install -y python3 python3-tkinter" ;;
    pacman)  cmd="pacman -S --noconfirm python tk" ;;
    zypper)  cmd="zypper --non-interactive install python3 python3-tk" ;;
    apk)     cmd="apk add python3 python3-tkinter" ;;
    *) say "$1 is missing and this system's package manager is unknown. Install Python 3 with tkinter, then start this again."; return 1 ;;
  esac
  if [ "$1" = python3 ]; then what="Python 3 is not installed on this computer, and the installer window needs it.
Python 3 ვერ მოიძებნა; ინსტალერის ფანჯარას ის სჭირდება."
  else what="tkinter (the window toolkit for Python) is missing.
tkinter ვერ მოიძებნა."; fi
  ask "$what

Install it now? (administrator password) / დავაყენო ახლა? (ადმინისტრატორის პაროლი)

$cmd" || { say "Cancelled. It is needed:  $cmd"; return 1; }
  progress_start "Installing... / მიმდინარეობს დაყენება... (this can take a minute)"
  : >"$log.install"
  if [ "$(id -u)" = 0 ]; then
    sh -c "$cmd" >"$log.install" 2>&1
  elif [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v pkexec >/dev/null 2>&1; then
    pkexec sh -c "$cmd" >"$log.install" 2>&1
  elif command -v sudo >/dev/null 2>&1; then
    sudo sh -c "$cmd" 2>&1 | tee "$log.install"
  else
    progress_stop; say "No way to get administrator rights here. Run as root:  $cmd"; return 1
  fi
  progress_stop
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import tkinter' 2>/dev/null; then return 0; fi
  if grep -qiE "could not get lock|dpkg frontend lock|dpkg/lock" "$log.install" 2>/dev/null; then
    say "Another installer or update is running right now (for example the Linux Mint installer or Update Manager).
Wait until it finishes, then start this again.

დაელოდეთ, სანამ მეორე ინსტალაცია/განახლება დასრულდება, და ისევ გაუშვით."
  else
    say "The installation did not work.

$(tail -n 8 "$log.install" 2>/dev/null)

Run in a terminal:  $cmd"
  fi
  return 1
}

mkdir -p "$(dirname "$log")" 2>/dev/null
[ -f "$here/installer-gui.py" ] || { say "installer-gui.py was not found next to start.sh ($here). Was the folder copied incompletely?"; exit 1; }

if ! command -v python3 >/dev/null 2>&1; then
  install_python python3 || exit 1
elif ! python3 -c 'import tkinter' 2>/dev/null; then
  install_python tkinter || exit 1
fi
if [ "${TOOLKIT_IN_TERMINAL:-}" = 1 ]; then
  setsid python3 "$here/installer-gui.py" "$@" >"$log" 2>&1 &
  gui_pid=$!
  sleep 2
  kill -0 "$gui_pid" 2>/dev/null && exit 0          # the window is up: this helper terminal can close
  wait "$gui_pid" 2>/dev/null
  tail -n 12 "$log" >&2
  exit 1
fi
if ! python3 "$here/installer-gui.py" "$@" >"$log" 2>&1; then
  say "The installer window could not start.

$(tail -n 12 "$log" 2>/dev/null)

(full log: $log)
Try in a terminal:  python3 $here/installer-gui.py"
  exit 1
fi
