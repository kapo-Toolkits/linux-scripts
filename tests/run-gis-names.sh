#!/usr/bin/env bash
# Every package name in installer/gis.json must exist in the real repositories of its distribution (containers; needs docker + network).
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
names() { python3 - "$1" <<'PY'
import json, sys
pm = sys.argv[1]
data = json.load(open("installer/gis.json"))
seen = []
for sec in data["sections"]:
    for p in sec["programs"]:
        for n in p.get("packages", {}).get(pm, []):
            if n not in seen:
                seen.append(n)
print(" ".join(seen))
PY
}
rc=0
cd "$root" || exit 1
for pair in "apt-get ubuntu:24.04" "apt-get debian:12" "dnf fedora:latest" "pacman archlinux:latest" "zypper opensuse/tumbleweed:latest"; do
  pm=${pair%% *}; img=${pair#* }
  echo "=================== $pm  $img"
  docker run --rm -v "$root/tests/gis_names_check.sh":/c.sh:ro "$img" sh /c.sh "$pm" $(names "$pm") || rc=1
done
exit $rc
