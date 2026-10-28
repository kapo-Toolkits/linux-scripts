#!/usr/bin/env bash
# Real installs/removals of the "other programs" recipes in a throwaway Ubuntu container. Needs docker and network.
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
docker run --rm -v "$root":/repo:ro "${1:-ubuntu:24.04}" sh -c \
  "apt-get update -qq >/dev/null && apt-get install -y -qq python3 >/dev/null && python3 /repo/tests/real_install_container_test.py" || rc=1
# unrar: real 'unrar' on Ubuntu (multiverse), the free fallback on Debian (no non-free), install + command + removal
for img in ubuntu:24.04 debian:12; do
  echo "=================== unrar on $img"
  docker run --rm -v "$root":/repo:ro "$img" sh -c \
    "apt-get update -qq >/dev/null && apt-get install -y -qq python3 >/dev/null && python3 /repo/tests/real_unrar_container_test.py" || rc=1
done
# VirtualBox: Oracle's real server - key fingerprint, repository for the release, apt offers 7.2, removal cleans up (Ubuntu + Debian)
for img in ubuntu:24.04 debian:12; do
  echo "=================== VirtualBox on $img"
  docker run --rm -v "$root":/repo:ro "$img" sh -c \
    "apt-get update -qq >/dev/null && apt-get install -y -qq python3 >/dev/null && python3 /repo/tests/real_virtualbox_container_test.py" || rc=1
done
# Filee: the real GitHub release (~130 MB): SHA-256 gate, the project's install.sh as the user, upgrade in place, its uninstall.sh
echo "=================== Filee on ubuntu:24.04"
docker run --rm -v "$root":/repo:ro ubuntu:24.04 sh -c \
  "apt-get update -qq >/dev/null && apt-get install -y -qq python3 curl ca-certificates >/dev/null && python3 /repo/tests/real_filee_container_test.py" || rc=1
exit "${rc:-0}"
