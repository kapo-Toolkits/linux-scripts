#!/usr/bin/env bash
# Real installs/removals of the "other programs" recipes in a throwaway Ubuntu container. Needs docker and network.
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
"$root/tests/retry-on-network.sh" docker run --rm -v "$root":/repo:ro "${1:-ubuntu:24.04}" sh -c \
  "apt-get update -qq >/dev/null && apt-get install -y -qq python3 >/dev/null && python3 /repo/tests/real_install_container_test.py" || rc=1
# unrar: real 'unrar' on Ubuntu (multiverse), the free fallback on Debian (no non-free), install + command + removal
for img in ubuntu:24.04 debian:12; do
  echo "=================== unrar on $img"
  "$root/tests/retry-on-network.sh" docker run --rm -v "$root":/repo:ro "$img" sh -c \
    "apt-get update -qq >/dev/null && apt-get install -y -qq python3 >/dev/null && python3 /repo/tests/real_unrar_container_test.py" || rc=1
done
# VirtualBox: Oracle's real server - key fingerprint, repository for the release, apt offers 7.2, removal cleans up (Ubuntu + Debian)
for img in ubuntu:24.04 debian:12; do
  echo "=================== VirtualBox on $img"
  "$root/tests/retry-on-network.sh" docker run --rm -v "$root":/repo:ro "$img" sh -c \
    "apt-get update -qq >/dev/null && apt-get install -y -qq python3 >/dev/null && python3 /repo/tests/real_virtualbox_container_test.py" || rc=1
done
# Filee: the real GitHub release (~130 MB): SHA-256 gate, the project's install.sh as the user, upgrade in place, its uninstall.sh
echo "=================== Filee on ubuntu:24.04"
"$root/tests/retry-on-network.sh" docker run --rm -v "$root":/repo:ro ubuntu:24.04 sh -c \
  "apt-get update -qq >/dev/null && apt-get install -y -qq python3 curl ca-certificates >/dev/null && python3 /repo/tests/real_filee_container_test.py" || rc=1
# Codex CLI: the real GitHub release (~120 MB): SHA-256 gate, install as ~/.local/bin/codex, --version, upgrade, foreign codex untouched, removal
echo "=================== Codex on ubuntu:24.04"
"$root/tests/retry-on-network.sh" docker run --rm -v "$root":/repo:ro ubuntu:24.04 sh -c \
  "apt-get update -qq >/dev/null && apt-get install -y -qq python3 curl ca-certificates >/dev/null && python3 /repo/tests/real_codex_container_test.py" || rc=1
# Flutter / Dart against Google's real servers: manifest + archive size, the docs' prerequisites installed by the recipe, standalone Dart
# (repository, the one trusted key, install, --version, removal). The 1.6 GB Flutter download itself is run locally with FLUTTER_FULL=1.
echo "=================== Flutter prerequisites + Dart on ubuntu:24.04"
"$root/tests/retry-on-network.sh" docker run --rm ${FLUTTER_FULL:+-e FLUTTER_FULL=1} -v "$root":/repo:ro ubuntu:24.04 sh -c \
  "apt-get update -qq >/dev/null && apt-get install -y -qq python3 >/dev/null && python3 /repo/tests/real_flutter_container_test.py" || rc=1
# AUR (Arch, Manjaro ...): the real AUR - our package names exist, and a package is fetched, built by makepkg as a normal user
# (dependencies through PACMAN_AUTH), installed with pacman -U and removed again
echo "=================== AUR on archlinux:latest"
"$root/tests/retry-on-network.sh" docker run --rm -v "$root":/repo:ro archlinux:latest sh -c \
  "pacman -Syu --noconfirm --quiet python >/dev/null && python3 /repo/tests/real_aur_container_test.py" || rc=1
exit "${rc:-0}"
