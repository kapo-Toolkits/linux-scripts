#!/bin/bash
# Runs a command; when it fails and its output shows a network / package-mirror problem (not a test failure), runs it
# again, up to 3 times in total. Real failures are reported at once. Usage: tests/retry-on-network.sh CMD [ARGS...]
# The test scripts call it around EACH container (docker run ...), so one flaky mirror costs one container, not the whole run.
# RETRY_DELAY (seconds, default 20) is the pause between attempts.
set -o pipefail
log=$(mktemp)
trap 'rm -f "$log"' EXIT
delay="${RETRY_DELAY:-20}"
# the last two are how the qgis.org tests show an unreachable qgis.org index (apt then offers Debian's own qgis): the symptom, not
# the cause, is all they print - a genuine regression fails all three tries anyway
# what a mirror / network hiccup looks like in apt, dnf, pacman, zypper, curl and git output (and in what our tests print from it)
patterns="Some index files failed to download|Unable to fetch some archives|Err:[0-9]+ https?://|Temporary failure|Could not resolve|Connection (timed out|reset|failed|refused)|Failed to fetch|Hash Sum mismatch|File has unexpected size|curl: \\((6|7|18|28|35|52|56)\\)|50[234] (Service Unavailable|Bad Gateway|Gateway)|TLS handshake|Mirror sync in progress|Failed to download metadata|Failed retrieving file|Download failed|could not resolve host|RPC failed|early EOF|FAIL apt item lists qgis-common and its origin +\\[http|FAIL qgis candidate comes from qgis.org +\\[Candidate"
for attempt in 1 2 3; do
    "$@" 2>&1 | tee "$log"
    rc=$?
    [ "$rc" -eq 0 ] && exit 0
    if [ "$attempt" -lt 3 ] && grep -q -i -E "$patterns" "$log"; then
        echo "::warning::network problem on attempt $attempt of $*, trying again in ${delay} s"
        sleep "$delay"
        continue
    fi
    exit "$rc"
done
