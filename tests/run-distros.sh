#!/usr/bin/env bash
# Portability matrix in throwaway containers (needs docker): unit tests, install.sh round-trip, and that the
# package names we suggest for missing tools really exist in each distribution.
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
rc=0
probe='
. /etc/os-release; echo "### $PRETTY_NAME"
if   command -v apt-get >/dev/null; then apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq python3 >/dev/null 2>&1
elif command -v dnf     >/dev/null; then dnf install -y -q python3 >/dev/null 2>&1
elif command -v pacman  >/dev/null; then pacman -Sy --noconfirm python >/dev/null 2>&1
elif command -v zypper  >/dev/null; then zypper -q --non-interactive refresh >/dev/null 2>&1; zypper -q --non-interactive install python3 >/dev/null 2>&1
elif command -v apk     >/dev/null; then apk add -q python3 bash >/dev/null 2>&1
fi
python3 --version
cp -r /repo /work && cd /work
python3 tests/test_units.py 2>&1 | tail -1 | grep -q "^OK" && echo "PASS unit tests" || { echo "FAIL unit tests"; exit 1; }
python3 tests/test_qgis_distros.py 2>&1 | tail -1 | grep -q "^OK" && echo "PASS qgis distribution tests" || { echo "FAIL qgis distribution tests"; python3 tests/test_qgis_distros.py 2>&1 | tail -15; exit 1; }
python3 tests/test_qgis_installer.py 2>&1 | tail -1 | grep -q "^OK" && echo "PASS qgis-installer tests" || { echo "FAIL qgis-installer tests"; python3 tests/test_qgis_installer.py 2>&1 | tail -15; exit 1; }
bash ./install.sh --prefix /tmp/pfx all >/dev/null 2>&1 || { echo "FAIL install.sh"; exit 1; }
n=$(python3 -c "import os;print(sum(len(f) for _,_,f in os.walk(\"/tmp/pfx\")))"); [ "$n" = 26 ] && echo "PASS install.sh ($n files)" || { echo "FAIL install.sh ($n files)"; exit 1; }
bash ./install.sh --prefix /tmp/pfx --uninstall all >/dev/null 2>&1
n=$(python3 -c "import os;print(sum(len(f) for _,_,f in os.walk(\"/tmp/pfx\")))"); [ "$n" = 0 ] && echo "PASS uninstall" || { echo "FAIL uninstall ($n left)"; exit 1; }
python3 tests/pkgnames_check.py
'
for img in debian:12 ubuntu:22.04 ubuntu:24.04 fedora:latest archlinux:latest opensuse/tumbleweed alpine:latest; do
  docker run --rm -v "$root":/repo:ro "$img" sh -c "$probe" 2>&1 || rc=1
done
exit $rc
