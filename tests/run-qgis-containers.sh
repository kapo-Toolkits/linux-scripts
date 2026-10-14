#!/usr/bin/env bash
# Runs qgis_container_test.py in throwaway containers. Needs docker. Downloads images + packages from qgis.org.
# usage: tests/run-qgis-containers.sh            (all)   |   tests/run-qgis-containers.sh ubuntu:24.04 ltr
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
run() { # image channel
  echo "=================== $1  channel=$2"
  docker run --rm -v "$root":/repo:ro "$1" sh -c \
    "apt-get update -qq >/dev/null && apt-get install -y -qq python3 >/dev/null && python3 /repo/tests/qgis_container_test.py $2"
}
if [ $# -eq 2 ]; then run "$1" "$2"; exit $?; fi
rc=0
run ubuntu:24.04 ltr   || rc=1     # noble: LTR only (what Linux Mint 22 maps to)
run debian:trixie latest || rc=1
run debian:trixie ltr  || rc=1
exit $rc
