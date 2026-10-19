#!/usr/bin/env bash
# Real kernel routing test of wifi-hotspot/hotspot-uplink.sh in a privileged container (needs docker, network for iproute2).
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
docker run --rm --privileged -v "$root":/repo:ro ubuntu:24.04 sh /repo/tests/hotspot_uplink_container_test.sh
