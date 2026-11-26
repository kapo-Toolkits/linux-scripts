#!/usr/bin/env bash
# Install / uninstall the tools: commands in PREFIX/bin, menu entries in PREFIX/share/applications,
# shared helper in PREFIX/lib/linux-scripts.      ./install.sh --help
set -euo pipefail

PREFIX=/usr/local
ACTION=install
DESKTOP_ICONS=0
DRY=0
FORCE=0
FOLDER_LAUNCHERS=0
TOOLS=()
here="$(cd "$(dirname "$0")" && pwd)"

# tool -> "source|command-name" ... ; desktop file (or -)
declare -A FILES=(
  [usb-eject]="usb-eject/usb-eject.sh|usb-eject usb-eject/usb-eject-gui.py|usb-eject-gui"
  [wifi-hotspot]="wifi-hotspot/hotspot.sh|hotspot wifi-hotspot/hotspot-gui.py|hotspot-gui"
  [printer-setup]="printer-setup/printer-setup-gui.py|printer-setup"
  [qgis-installer]="qgis-installer/qgis-installer-gui.py|qgis-installer qgis-installer/qgis-installer-cli.py|qgis-installer-cli"
  [shortcuts]="shortcuts/shortcuts-gui.py|toolkit-shortcuts"
  [devops-toolbox]="devops-toolbox/devops-toolbox-gui.py|devops-toolbox devops-toolbox/devops-toolbox-web.py|devops-toolbox-web"
  [autostart]="autostart/autostart-gui.py|autostart-manager"
  [printhub]="printhub/printhub-launcher.sh|printhub"   # not part of "all": the app + PySide6 are installed too
)
declare -A GUISCRIPT=(
  [usb-eject]=usb-eject/usb-eject-gui.py
  [wifi-hotspot]=wifi-hotspot/hotspot-gui.py
  [printer-setup]=printer-setup/printer-setup-gui.py
  [qgis-installer]=qgis-installer/qgis-installer-gui.py
  [shortcuts]=shortcuts/shortcuts-gui.py
  [devops-toolbox]=devops-toolbox/devops-toolbox-gui.py
  [autostart]=autostart/autostart-gui.py
  [printhub]=printhub/run.py
)
declare -A DESKTOP=(
  [usb-eject]=usb-eject/usb-eject-gui.desktop
  [wifi-hotspot]=wifi-hotspot/hotspot-gui.desktop
  [printer-setup]=printer-setup/printer-setup.desktop
  [qgis-installer]=qgis-installer/qgis-installer.desktop
  [shortcuts]=shortcuts/shortcuts.desktop
  [devops-toolbox]=devops-toolbox/devops-toolbox.desktop
  [autostart]=autostart/autostart-manager.desktop
  [printhub]=printhub/packaging/linux/printhub.desktop
)
ALL=(usb-eject wifi-hotspot printer-setup qgis-installer shortcuts devops-toolbox autostart)

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
  --dry-run      only print what would be done; nothing is written, removed or run with sudo
  --force        install over / remove files this toolkit did not put there (by default such files are left alone)
Uses sudo automatically when DIR is not writable. What was installed is recorded in PREFIX/share/linux-scripts/install-manifest.
U
}

while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) [ $# -ge 2 ] && [ -n "$2" ] || { echo "--prefix needs a directory"; exit 1; }; PREFIX="$2"; shift 2;;
    --dry-run) DRY=1; shift;;
    --force) FORCE=1; shift;;
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
[ "$DRY" = 1 ] && SUDO=""            # a preview never asks for a password

MANIFEST="$PREFIX/share/linux-scripts/install-manifest"
NEWPATHS=()
GONEPATHS=()

# Do a command, or just say it in a preview.
act() { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else "$@"; fi; }
# SHA-256 of a file ("-" for a folder or anything else): what the manifest remembers about each path it lists.
hash_of() { if [ -f "$1" ]; then sha256sum "$1" 2>/dev/null | cut -d' ' -f1; else echo "-"; fi; }
# Was this path put there by this toolkit? It is in the manifest AND still holds what was installed (or, if you edited it, still
# carries the toolkit's own names). A different program that later took the same name is not ours.
is_ours() {
  [ -f "$MANIFEST" ] || return 1
  local want="" p h
  while IFS=$'\t' read -r p h; do        # plain bash: awk is not installed everywhere
    if [ "$p" = "$1" ]; then want="$h"; break; fi
  done < "$MANIFEST"
  [ -n "$want" ] || return 1
  [ "$want" = "-" ] || [ "$want" = "$(hash_of "$1")" ] || looks_ours "$1"
}
# An installation from before the manifest existed: the file still carries the toolkit's own names.
looks_ours() { [ -f "$1" ] && grep -Eq 'lscommon|linux-scripts|kapo-Toolkits' "$1" 2>/dev/null; }
# May we write to / remove DEST (a command or menu entry)? SRC is the toolkit's own file for it ("" for none).
ours_to_touch() {
  local dest="$1" src="$2"
  [ -e "$dest" ] || [ -L "$dest" ] || return 0
  [ "$FORCE" = 1 ] && return 0
  is_ours "$dest" && return 0
  [ -n "$src" ] && [ -f "$dest" ] && [ "$(hash_of "$src")" = "$(hash_of "$dest")" ] && return 0
  looks_ours "$dest" && return 0
  case "$dest" in *.desktop) grep -q "^Exec=$PREFIX/bin/" "$dest" 2>/dev/null && return 0;; esac
  return 1
}

# PrintHub is an application, not a single script: copy the package, give it PySide6 (system one, else a private
# venv), install the icon.  The launcher and the menu entry go through the generic loop below.
printhub_extra() {
  local app="$PREFIX/lib/printhub" icon="$PREFIX/share/icons/hicolor/256x256/apps/io.printhub.PrintHub.png"
  if [ "$DRY" = 1 ]; then
    echo "[dry-run] PrintHub: ${ACTION} $app (and its icon)$([ "$ACTION" = install ] && echo "; a private PySide6 environment is created when the system has none (~200 MB)")"
    return 0
  fi
  if [ "$ACTION" = install ]; then
    command -v python3 >/dev/null || { echo "python3 is required for PrintHub"; exit 1; }
    $SUDO rm -rf "$app/printhub"; $SUDO mkdir -p "$app"
    $SUDO cp -r "$here/printhub/printhub" "$app/printhub"
    $SUDO find "$app/printhub" -name __pycache__ -prune -exec rm -rf {} +
    if python3 -c 'import PySide6' 2>/dev/null; then
      echo "PySide6 found on the system - no private environment needed"
    else
      echo "Creating a private Python environment with PySide6 (downloads about 200 MB)..."
      $SUDO rm -rf "$app/venv"
      if $SUDO python3 -m venv "$app/venv" >/dev/null 2>&1; then
        $SUDO "$app/venv/bin/pip" install --quiet --disable-pip-version-check "PySide6>=6.6"
      else
        # no python3-venv (Debian/Ubuntu split it out): make the environment without pip and let the system's pip fill it
        $SUDO rm -rf "$app/venv"
        if $SUDO python3 -m venv --without-pip "$app/venv" >/dev/null 2>&1 && python3 -m pip --version >/dev/null 2>&1; then
          $SUDO python3 -m pip --python "$app/venv/bin/python" install --quiet --disable-pip-version-check "PySide6>=6.6"
        else
          $SUDO rm -rf "$app/venv"
          echo "Cannot create the environment: install python3-venv (Debian/Ubuntu: sudo apt install python3-venv) or python3-pip, or PySide6 itself"
          exit 1
        fi
      fi
    fi
    $SUDO install -D -m 644 "$here/printhub/packaging/assets/printhub.png" "$icon"
    echo "installed PrintHub into $app"
    NEWPATHS+=("$app" "$icon")
  else
    if [ -d "$app" ] && [ "$FORCE" != 1 ] && ! is_ours "$app" && [ ! -d "$app/printhub" ]; then
      echo "kept $app (not installed by this toolkit; --force removes it)"
    else
      $SUDO rm -rf "$app"; $SUDO rm -f "$icon"; echo "removed $app"; GONEPATHS+=("$app" "$icon")
    fi
  fi
}

# Before anything is written: refuse to overwrite a file that is not ours (another program with the same command name).
if [ "$ACTION" = install ] && [ "$FORCE" != 1 ]; then
  clash=0
  for tool in "${TOOLS[@]}"; do
    for pair in $(echo "${FILES[$tool]}" | tr ' ' '\n' | sed 's/|/,/'); do
      src="${pair%%,*}"; cmd="${pair##*,}"
      ours_to_touch "$PREFIX/bin/$cmd" "$here/$src" || { echo "refusing to overwrite $PREFIX/bin/$cmd: it is not from this toolkit"; clash=1; }
    done
    dname="$(basename "${DESKTOP[$tool]}")"
    ours_to_touch "$PREFIX/share/applications/$dname" "" || { echo "refusing to overwrite $PREFIX/share/applications/$dname: it is not from this toolkit"; clash=1; }
  done
  if [ "$clash" = 1 ]; then echo "Nothing was installed. Use --force to replace those files anyway, or --prefix to install elsewhere."; exit 1; fi
fi

for tool in "${TOOLS[@]}"; do
  [ "$tool" = printhub ] && printhub_extra
  for pair in $(echo "${FILES[$tool]}" | tr ' ' '\n' | sed 's/|/,/'); do
    src="${pair%%,*}"; cmd="${pair##*,}"
    if [ "$ACTION" = install ]; then
      act $SUDO install -D -m 755 "$here/$src" "$PREFIX/bin/$cmd"; [ "$DRY" = 1 ] || echo "installed $PREFIX/bin/$cmd"; NEWPATHS+=("$PREFIX/bin/$cmd")
    elif ours_to_touch "$PREFIX/bin/$cmd" "$here/$src"; then
      act $SUDO rm -f "$PREFIX/bin/$cmd"; [ "$DRY" = 1 ] || echo "removed $PREFIX/bin/$cmd"; GONEPATHS+=("$PREFIX/bin/$cmd")
    else
      echo "kept $PREFIX/bin/$cmd (not from this toolkit; --force removes it)"
    fi
  done
  d="${DESKTOP[$tool]}"; dname="$(basename "$d")"
  if [ "$ACTION" = install ]; then
    # absolute Exec= so a menu/desktop click works even when PREFIX/bin is not in the session's PATH
    # (a plain loop, not sed: a prefix containing '#', '&' or '\\' must come out unchanged)
    tmp="$(mktemp)"
    while IFS= read -r line || [ -n "$line" ]; do
      case "$line" in Exec=*) printf 'Exec=%s/bin/%s\n' "$PREFIX" "${line#Exec=}";; *) printf '%s\n' "$line";; esac
    done < "$here/$d" > "$tmp"
    act $SUDO install -D -m 644 "$tmp" "$PREFIX/share/applications/$dname"; NEWPATHS+=("$PREFIX/share/applications/$dname")
    if [ "$DESKTOP_ICONS" = 1 ] && [ -d "$DESKDIR" ]; then
      act install -m 755 "$tmp" "$DESKDIR/$dname"
      if [ "$DRY" = 0 ]; then
        command -v gio >/dev/null && gio set "$DESKDIR/$dname" metadata::trusted true 2>/dev/null || true
      fi
      echo "launcher on Desktop: $DESKDIR/$dname"
    fi
    rm -f "$tmp"
  else
    if ours_to_touch "$PREFIX/share/applications/$dname" ""; then
      act $SUDO rm -f "$PREFIX/share/applications/$dname"; GONEPATHS+=("$PREFIX/share/applications/$dname")
    else
      echo "kept $PREFIX/share/applications/$dname (not from this toolkit; --force removes it)"
    fi
    [ "$DESKTOP_ICONS" = 1 ] && act rm -f "$DESKDIR/$dname"
  fi
  # double-click launcher in the tool's own folder (absolute path to this checkout)
  flaunch="$here/$(dirname "$d")/start-${dname%.desktop}.desktop"
  if [ "$ACTION" = install ] && [ "$FOLDER_LAUNCHERS" = 1 ] && [ "$DRY" = 1 ]; then
    echo "[dry-run] would write the double-click launcher $flaunch"
  elif [ "$ACTION" = install ] && [ "$FOLDER_LAUNCHERS" = 1 ]; then
    {
      sed -n '/^\[Desktop Entry\]/,$p' "$here/$d" | grep -v -E '^(Exec|Path)='
      echo "Exec=python3 ${here}/${GUISCRIPT[$tool]}"
      echo "Path=$here/$(dirname "$d")"
    } > "$flaunch"
    chmod 755 "$flaunch"
    command -v gio >/dev/null && gio set "$flaunch" metadata::trusted true 2>/dev/null || true
    echo "double-click launcher: $flaunch"
  elif [ "$ACTION" = uninstall ] && [ "$FOLDER_LAUNCHERS" = 1 ]; then
    act rm -f "$flaunch"
  fi
done

if [ "$ACTION" = install ] && [ "$(id -u)" != 0 ] && [ "$DRY" = 0 ]; then
  # lets toolkit-shortcuts find programs of this checkout that are not installed
  mkdir -p "$HOME/.config/linux-scripts" && printf '%s\n' "$here" > "$HOME/.config/linux-scripts/root"
fi
if [ "$ACTION" = install ]; then
  for m in lscommon lsqr lsnet; do
    act $SUDO install -D -m 644 "$here/common/$m.py" "$PREFIX/lib/linux-scripts/$m.py"
  done
  # the hotspot's "which network to share" helper (the window runs it with administrator rights when you choose a network)
  case " ${TOOLS[*]} " in
    *" wifi-hotspot "*) act $SUDO install -D -m 755 "$here/wifi-hotspot/hotspot-uplink.sh" "$PREFIX/lib/linux-scripts/hotspot-uplink.sh";;
  esac
  # the qgis_installer package (logic shared by qgis-installer and qgis-installer-cli)
  case " ${TOOLS[*]} " in
    *" qgis-installer "*)
      for f in "$here"/qgis-installer/qgis_installer/*.py; do
        act $SUDO install -D -m 644 "$f" "$PREFIX/lib/linux-scripts/qgis_installer/$(basename "$f")"
      done;;
  esac
  # the devops_toolbox package (backend shared by the window and the web app)
  case " ${TOOLS[*]} " in
    *" devops-toolbox "*)
      for f in "$here"/devops-toolbox/devops_toolbox/*.py "$here"/devops-toolbox/devops_toolbox/modules/*.py; do
        sub="${f#"$here"/devops-toolbox/}"
        act $SUDO install -D -m 644 "$f" "$PREFIX/lib/linux-scripts/$sub"
      done;;
  esac
fi
if [ "$ACTION" = uninstall ]; then
  case " ${TOOLS[*]} " in
    *" wifi-hotspot "*)
      # a chosen "network to share" lives in /etc (routing rule + NetworkManager dispatcher): take it away with the tool
      if [ -e /etc/NetworkManager/dispatcher.d/90-linux-scripts-hotspot-uplink ] && [ -f "$PREFIX/lib/linux-scripts/hotspot-uplink.sh" ]; then
        act $SUDO sh "$PREFIX/lib/linux-scripts/hotspot-uplink.sh" install auto || true
      fi
      act $SUDO rm -f "$PREFIX/lib/linux-scripts/hotspot-uplink.sh";;
  esac
  case " ${TOOLS[*]} " in *" qgis-installer "*) act $SUDO rm -rf "$PREFIX/lib/linux-scripts/qgis_installer";; esac
  case " ${TOOLS[*]} " in *" devops-toolbox "*) act $SUDO rm -rf "$PREFIX/lib/linux-scripts/devops_toolbox";; esac
  # the shared helper goes only when no command of the toolkit is left (in a preview: none left after the ones listed above)
  guis=0
  for g in usb-eject-gui hotspot-gui printer-setup qgis-installer qgis-installer-cli bluetooth-setup toolkit-shortcuts devops-toolbox devops-toolbox-web autostart-manager; do
    gone=0; for x in "${GONEPATHS[@]+"${GONEPATHS[@]}"}"; do [ "$x" = "$PREFIX/bin/$g" ] && gone=1; done
    [ -e "$PREFIX/bin/$g" ] && [ "$gone" = 0 ] && guis=1
  done
  if [ "$guis" = 0 ]; then act $SUDO rm -rf "$PREFIX/lib/linux-scripts"; [ "$DRY" = 1 ] || echo "removed shared helper"; fi
fi

# the record of what this toolkit put under PREFIX (so an uninstall removes only that, and an install knows what is its own)
if [ "$DRY" = 0 ]; then
  if [ "$ACTION" = install ] && [ ${#NEWPATHS[@]} -gt 0 ]; then
    mf="$(mktemp)"
    : > "$mf"
    for x in "${NEWPATHS[@]}"; do printf '%s\t%s\n' "$x" "$(hash_of "$x")" >> "$mf"; done
    if [ -f "$MANIFEST" ]; then          # keep the older records of paths that were not installed again now
      while IFS= read -r line; do
        old="${line%%$'\t'*}"
        grep -Fq -- "$old"$'\t' "$mf" || printf '%s\n' "$line" >> "$mf"
      done < "$MANIFEST"
    fi
    sort -u "$mf" -o "$mf"
    $SUDO install -D -m 644 "$mf" "$MANIFEST"; rm -f "$mf"
  elif [ "$ACTION" = uninstall ] && [ -f "$MANIFEST" ]; then
    mf="$(mktemp)"
    cp "$MANIFEST" "$mf"
    for x in "${GONEPATHS[@]+"${GONEPATHS[@]}"}"; do grep -Fv -- "$x"$'\t' "$mf" > "$mf.n" || true; mv "$mf.n" "$mf"; done
    if [ -s "$mf" ]; then $SUDO install -D -m 644 "$mf" "$MANIFEST"; else $SUDO rm -f "$MANIFEST"; $SUDO rmdir "$(dirname "$MANIFEST")" 2>/dev/null || true; fi
    rm -f "$mf"
  fi
fi
# bluetooth-setup moved to its own repository; a copy installed by an earlier version is not touched
if [ "$ACTION" = uninstall ] && [ -e "$PREFIX/bin/bluetooth-setup" ]; then
  echo "note: $PREFIX/bin/bluetooth-setup was installed by an older version and is left in place; the tool now lives at"
  echo "      https://github.com/kapo-Toolkits/bluetooth-setup  (remove the old copy with: $SUDO rm -f $PREFIX/bin/bluetooth-setup $PREFIX/share/applications/bluetooth-setup.desktop)"
fi
[ "$DRY" = 1 ] || { command -v update-desktop-database >/dev/null && $SUDO update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true; }
[ "$DRY" = 1 ] && echo "Preview only - nothing was changed." || echo "Done."
