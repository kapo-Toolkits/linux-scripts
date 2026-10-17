#!/usr/bin/env bash
# Real installs/removals of the "other programs" recipes in a throwaway Ubuntu container. Needs docker and network.
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
docker run --rm -v "$root":/repo:ro "${1:-ubuntu:24.04}" sh -c \
  "apt-get update -qq >/dev/null && apt-get install -y -qq python3 >/dev/null && python3 /repo/tests/real_install_container_test.py"
