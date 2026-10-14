#!/usr/bin/env bash
# Decode-checks the QR generator with zbar inside a throwaway container (needs docker, downloads zbar-tools).
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
docker run --rm -v "$root":/repo:ro ubuntu:24.04 sh -c \
  "apt-get update -qq >/dev/null && apt-get install -y -qq python3 zbar-tools >/dev/null 2>&1 && python3 /repo/tests/qr_decode_test.py"
