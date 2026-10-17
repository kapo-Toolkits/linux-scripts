#!/bin/sh
# Get the linux-scripts toolkit onto this computer and open its installer window.
#   sh get.sh [FOLDER] [--no-start]          FOLDER defaults to ~/linux-scripts
# Read it first, then run it (it is short):   curl -fsSLO https://raw.githubusercontent.com/kapo-Toolkits/linux-scripts/main/get.sh
# What it does: asks GitHub for the newest commit of main, downloads exactly that snapshot over HTTPS, unpacks it into FOLDER
# (an existing copy is backed up first, files that are not part of the toolkit stay), makes the desktop launcher and starts the
# installer. No git needed. Root is never used here; the installer asks for it only for what you tick.
set -eu

REPO="kapo-Toolkits/linux-scripts"
DEST=""
START=1
for a in "$@"; do
    case "$a" in
        --no-start) START=0 ;;
        -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
        *) DEST="$a" ;;
    esac
done
[ -n "$DEST" ] || DEST="$HOME/linux-scripts"

say() { printf '%s\n' "$*"; }
die() { printf 'get.sh: %s\n' "$*" >&2; exit 1; }

if command -v curl >/dev/null 2>&1; then
    fetch() { curl -fsSL --proto '=https' --tlsv1.2 "$@"; }
elif command -v wget >/dev/null 2>&1; then
    fetch() { url=""; for x in "$@"; do case "$x" in http*) url="$x" ;; esac; done; wget -qO- --https-only "$url"; }
else
    die "curl or wget is needed (Debian/Ubuntu: sudo apt install curl)"
fi
command -v tar >/dev/null 2>&1 || die "tar is needed"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

if [ -n "${LS_SNAPSHOT:-}" ]; then                     # for tests only: a local tar.gz instead of GitHub
    cp "$LS_SNAPSHOT" "$TMP/snap.tar.gz"
    SHA="${LS_SHA:-0000000000000000000000000000000000000000}"
else
    say "Asking GitHub for the newest version..."
    SHA=$(fetch -H 'Accept: application/vnd.github.sha' "https://api.github.com/repos/$REPO/commits/main") || die "could not reach GitHub (no internet?)"
    printf '%s' "$SHA" | grep -Eq '^[0-9a-f]{40}$' || die "GitHub returned something unexpected instead of a commit id"
    say "Downloading $SHA ..."
    fetch "https://codeload.github.com/$REPO/tar.gz/$SHA" > "$TMP/snap.tar.gz" || die "download failed"
fi

mkdir "$TMP/x"
tar -xzf "$TMP/snap.tar.gz" -C "$TMP/x" --strip-components=1 || die "the download is not a valid archive"
[ -f "$TMP/x/install.sh" ] && [ -f "$TMP/x/installer/start.sh" ] || die "the download does not look like the linux-scripts toolkit"

if [ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
    [ -f "$DEST/install.sh" ] || die "$DEST exists and is not a toolkit folder - choose another folder (sh get.sh FOLDER)"
    BAK="$DEST.backup-$(date +%Y%m%d-%H%M%S)"
    cp -a "$DEST" "$BAK"
    say "Existing copy saved to $BAK"
fi
mkdir -p "$DEST"
cp -a "$TMP/x/." "$DEST/"
printf '%s\n' "$SHA" > "$DEST/.installed-sha"
say "Toolkit is in $DEST"

sh "$DEST/installer/start.sh" --make-launcher --desktop || say "(could not make the desktop launcher; start it with: sh $DEST/installer/start.sh)"
if [ "$START" = 1 ]; then
    exec sh "$DEST/installer/start.sh"
fi
