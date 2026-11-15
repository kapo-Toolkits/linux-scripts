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
elif [ -z "${LS_SNAPSHOT:-}" ]; then                    # a local snapshot (tests) needs no downloader
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

# The snapshot must hold plain files and folders only: no links, no absolute paths, nothing that climbs out with '..'.
tar -tzf "$TMP/snap.tar.gz" > "$TMP/names" 2>/dev/null || die "the download is not a valid archive"
if grep -Eq '^/|(^|/)\.\.(/|$)' "$TMP/names"; then die "the download contains unsafe file names - nothing was installed"; fi
if tar -tvzf "$TMP/snap.tar.gz" 2>/dev/null | grep -q '^[lh]'; then die "the download contains links - nothing was installed"; fi
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

# True when REL inside DEST is, or lies behind, a symbolic link (or is a folder where a file belongs): never written through.
blocked() {
    cur="$DEST"; oldifs=$IFS; IFS=/; set -f
    for part in $1; do
        cur="$cur/$part"
        if [ -L "$cur" ]; then IFS=$oldifs; set +f; return 0; fi
        [ -e "$cur" ] || break
    done
    IFS=$oldifs; set +f
    [ -d "$DEST/$1" ]
}
# Copy every file of the snapshot over DEST: each one is written next to its place and renamed into it (an atomic step), and a
# symbolic link of yours is kept exactly as it is instead of being followed to wherever it points.
copy_in() {
    # the file list comes from the archive itself (find is not installed everywhere); folders end with '/'
    sed 's#^\./##; s#^[^/]*/##' "$TMP/names" | grep -v '/$' | grep -v '^$' | while IFS= read -r rel; do
        [ -f "$TMP/x/$rel" ] || continue
        if blocked "$rel"; then say "kept (symbolic link here): $rel"; continue; fi
        mkdir -p "$DEST/$(dirname "$rel")"
        cp -p "$TMP/x/$rel" "$DEST/$rel.new-$$" && mv -f "$DEST/$rel.new-$$" "$DEST/$rel"
    done
}
if ! copy_in; then
    [ -n "${BAK:-}" ] && die "copying stopped half-way. Your previous copy is untouched in $BAK (restore it: rm -rf '$DEST' && mv '$BAK' '$DEST')"
    die "copying stopped half-way"
fi
printf '%s\n' "$SHA" > "$DEST/.installed-sha"
say "Toolkit is in $DEST"

sh "$DEST/installer/start.sh" --make-launcher --desktop || say "(could not make the desktop launcher; start it with: sh $DEST/installer/start.sh)"
if [ "$START" = 1 ]; then
    exec sh "$DEST/installer/start.sh"
fi
