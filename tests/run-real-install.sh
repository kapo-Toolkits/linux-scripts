#!/usr/bin/env bash
# Real installs/removals of the "other programs" recipes in a throwaway Ubuntu container. Needs docker and network.
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
docker run --rm -v "$root":/repo:ro "${1:-ubuntu:24.04}" sh -c \
  "apt-get update -qq >/dev/null && apt-get install -y -qq python3 >/dev/null && python3 /repo/tests/real_install_container_test.py" || rc=1
for img in ubuntu:24.04 debian:12; do
  echo "=================== VirtualBox on $img"
  docker run --rm -v "$root":/repo:ro "$img" sh -c \
    "apt-get update -qq >/dev/null && apt-get install -y -qq python3 >/dev/null && python3 /repo/tests/real_virtualbox_container_test.py" || rc=1
done
exit "${rc:-0}"
