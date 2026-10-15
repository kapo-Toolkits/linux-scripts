#!/usr/bin/env bash
# Resolves every non-apt install recipe for real (dry runs) inside throw-away containers. Needs docker (or podman as "docker").
# Downloads package indexes, Flathub metadata and the distribution images; installs nothing of QGIS.
# usage: tests/run-recipes-containers.sh                    (all)
#        tests/run-recipes-containers.sh fedora:latest dnf-fedora [--opt key=value ...]
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"

PREP='
if   command -v apt-get >/dev/null; then apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq python3 ca-certificates >/dev/null 2>&1
elif command -v dnf     >/dev/null; then dnf install -y -q python3 >/dev/null 2>&1
elif command -v pacman  >/dev/null; then pacman -Sy --noconfirm python >/dev/null 2>&1
elif command -v zypper  >/dev/null; then zypper -q --non-interactive refresh >/dev/null 2>&1; zypper -q --non-interactive install python3 >/dev/null 2>&1
elif command -v urpmi   >/dev/null; then urpmi.update -a >/dev/null 2>&1; urpmi --auto python3 >/dev/null 2>&1
fi
. /etc/os-release; echo "### $PRETTY_NAME"'

run() {   # image recipe [extra args]
  local img="$1"; shift
  echo "=================== $img  $*"
  docker run --rm -v "$root":/repo:ro "$img" sh -c "$PREP; python3 /repo/tests/qgis_recipes_container_test.py $*"
}

comp() {   # image: install two components for real with the command line and check the system sees them
  echo "=================== $1  components (real install)"
  docker run --rm -v "$root":/repo:ro "$1" sh -c "$PREP; python3 /repo/tests/qgis_components_container_test.py"
}

if [ "${1:-}" = "components" ]; then shift; comp "$@"; exit $?; fi
if [ $# -ge 2 ]; then run "$@"; exit $?; fi
rc=0
run fedora:latest dnf-fedora                            || rc=1
run opensuse/tumbleweed zypper-opensuse                 || rc=1
run archlinux:latest pacman-arch                        || rc=1
run debian:trixie apt-distro                            || rc=1
run debian:trixie flatpak                               || rc=1
run debian:trixie flatpak --opt branch=lts              || rc=1
run mageia:latest urpmi-mageia                          || rc=1
comp debian:trixie                                      || rc=1
comp fedora:latest                                      || rc=1
comp opensuse/tumbleweed                                || rc=1
comp archlinux:latest                                   || rc=1
exit $rc
