#!/usr/bin/env bash
# The offline copy of QGIS for real, with the command line of this project: export in a container that has a network, install in a
# fresh container that has NONE. Downloads about 1.2 GB of Flatpak (QGIS LTS and its runtime) once. Needs docker (or podman as "docker").
# usage: tests/run-offline-containers.sh [stable|lts]
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
branch="${1:-lts}"
img=debian:trixie
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
rc=0
ok()  { echo "  ok   $1"; }
bad() { echo "  FAIL $1"; rc=1; }

echo "=================== image with Flatpak (the only step besides the export that needs a network)"
docker rm -f offline-base >/dev/null 2>&1
docker run --name offline-base --privileged "$img" sh -c 'apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq python3 ca-certificates flatpak curl >/dev/null 2>&1' || exit 1
docker commit -q offline-base offline-base:1 >/dev/null; docker rm -f offline-base >/dev/null

echo "=================== export (network on)"
docker run --rm --privileged -v "$root":/repo:ro -v "$out":/out offline-base:1 sh -c \
  "cd /repo/qgis-installer && python3 -m qgis_installer offline export /out --branch $branch --yes 2>&1 | tail -4"
[ -d "$out/.ostree/repo" ] && ok "the copy has an ostree repo" || bad "no .ostree/repo in the copy"
[ -s "$out/flathub.flatpakrepo" ] && ok "the Flathub repo file is in the copy" || bad "no repo file in the copy"

echo "=================== install (NO network)"
docker run --rm --privileged --network none -v "$root":/repo:ro -v "$out":/out:ro offline-base:1 sh -c "
  cd /repo/qgis-installer
  if getent hosts dl.flathub.org >/dev/null 2>&1; then echo 'FAIL the container still has a network'; exit 9; fi
  python3 -m qgis_installer offline install /out --branch $branch --yes 2>&1 | tail -3
  echo '--- flatpak list'; flatpak list --app --columns=application,branch,installation
  echo '--- our list';     python3 -m qgis_installer list
  echo '--- the app is really there'; flatpak info --system org.qgis.qgis//$branch | head -3
" | tee "$out.log"
grep -q "org.qgis.qgis.*$branch.*system" "$out.log" && ok "QGIS $branch is installed from the copy, with no network" || bad "QGIS is not installed"
grep -q "Flatpak (system, $branch) org.qgis.qgis" "$out.log" && ok "the installer finds it" || bad "the installer does not find it"
grep -q "FAIL the container" "$out.log" && bad "the second container had a network"
rm -f "$out.log"
exit $rc
