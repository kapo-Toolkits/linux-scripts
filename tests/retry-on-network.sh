#!/bin/bash
# Runs a command; when it fails and its output shows a network / package-mirror problem (not a test failure), runs it
# again, up to 3 times in total. Real failures are reported at once. Usage: tests/retry-on-network.sh CMD [ARGS...]
set -o pipefail
log=$(mktemp)
trap 'rm -f "$log"' EXIT
for attempt in 1 2 3; do
    "$@" 2>&1 | tee "$log"
    rc=$?
    [ "$rc" -eq 0 ] && exit 0
    if [ "$attempt" -lt 3 ] && grep -q -i -E "Unable to fetch some archives|Temporary failure|Could not resolve|Connection (timed out|reset)|Failed to fetch|Hash Sum mismatch|curl: \(6\)|curl: \(28\)|503 Service Unavailable" "$log"; then
        echo "::warning::network problem on attempt $attempt, trying again in 20 s"
        sleep 20
        continue
    fi
    exit "$rc"
done
