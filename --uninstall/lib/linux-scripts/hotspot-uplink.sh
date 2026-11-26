#!/bin/sh
# Which network does the Wi-Fi hotspot share?  (NetworkManager's "shared" mode uses whatever the computer's default route is.)
# This sends the hotspot clients' internet traffic through the network you choose (e.g. the cable, or a second Wi-Fi adapter
# connected to another network) by policy routing - the computer's own traffic is not touched.
#
#   sudo sh hotspot-uplink.sh install DEVICE [CONNECTION]   share DEVICE (e.g. eno1, wlx...); CONNECTION defaults to Hotspot
#   sudo sh hotspot-uplink.sh install auto                   back to "whatever the default route is" (removes everything)
#   sh hotspot-uplink.sh status                              what is configured
#
# "install" copies THIS script into NetworkManager's dispatcher folder, where NetworkManager runs it on every network event
# (then $1 is an interface name and $2 an action, so it re-checks the routes). Files: /etc/linux-scripts/hotspot-uplink,
# /etc/NetworkManager/dispatcher.d/90-linux-scripts-hotspot-uplink. Routing table/priority 4242.
CONF="${HOTSPOT_UPLINK_CONF:-/etc/linux-scripts/hotspot-uplink}"
DISPATCH="${HOTSPOT_UPLINK_DISPATCH:-/etc/NetworkManager/dispatcher.d/90-linux-scripts-hotspot-uplink}"
TABLE=4242

clean() { tr -cd 'A-Za-z0-9_.:-' ; }           # an interface name: never anything a shell could misread

remove_rules() {
  while ip rule del priority "$TABLE" 2>/dev/null; do :; done
  ip route flush table "$TABLE" 2>/dev/null
  return 0
}

apply() {   # make the routes match the configuration (called by NetworkManager; safe to run any number of times)
  [ -r "$CONF" ] || exit 0
  dev=$(sed -n 1p "$CONF" | clean)
  con=$(sed -n 2p "$CONF" | tr -cd 'A-Za-z0-9_. -')
  [ -n "$con" ] || con=Hotspot
  ap=$(nmcli -t -f DEVICE,CONNECTION device 2>/dev/null | awk -F: -v c="$con" '$2==c{print $1; exit}')
  if [ -z "$dev" ] || [ "$dev" = auto ] || [ -z "$ap" ] || [ "$ap" = "$dev" ]; then remove_rules; exit 0; fi
  route=$(ip -4 route show default dev "$dev" 2>/dev/null | head -n 1)
  net=$(ip -4 route show dev "$ap" proto kernel scope link 2>/dev/null | awk '{print $1; exit}')
  if [ -z "$route" ] || [ -z "$net" ]; then remove_rules; exit 0; fi       # the chosen network is down: nothing to route
  gw=$(printf '%s\n' "$route" | awk '{for (i = 1; i < NF; i++) if ($i == "via") { print $(i + 1); exit }}')
  ip route replace "$net" dev "$ap" table "$TABLE" || exit 0              # replies of the hotspot itself (DHCP, DNS) stay local
  if [ -n "$gw" ]; then ip route replace default via "$gw" dev "$dev" table "$TABLE"
  else ip route replace default dev "$dev" table "$TABLE"; fi
  while ip rule del priority "$TABLE" 2>/dev/null; do :; done
  ip rule add from "$net" lookup "$TABLE" priority "$TABLE"
  exit 0
}

case "${1:-}" in
  install)
    dev=$(printf '%s' "${2:-}" | clean); con=$(printf '%s' "${3:-Hotspot}" | tr -cd 'A-Za-z0-9_. -')
    [ -n "$dev" ] || { echo "usage: $0 install DEVICE|auto [CONNECTION]" >&2; exit 2; }
    [ "$(id -u)" = 0 ] || [ -n "${HOTSPOT_UPLINK_CONF:-}" ] || { echo "run as root (sudo)" >&2; exit 1; }
    mkdir -p "$(dirname "$CONF")" "$(dirname "$DISPATCH")" || exit 1
    if [ "$dev" = auto ]; then
      rm -f "$DISPATCH"; printf 'auto\n%s\n' "$con" > "$CONF"; remove_rules
      echo "Hotspot now shares the computer's default network (automatic)."
    else
      printf '%s\n%s\n' "$dev" "$con" > "$CONF"
      cp "$0" "$DISPATCH" && chmod 755 "$DISPATCH" || exit 1
      sh "$DISPATCH" "$dev" up
      echo "Hotspot '$con' will share the network on $dev."
    fi
    exit 0 ;;
  status)
    if [ -r "$CONF" ]; then echo "uplink: $(sed -n 1p "$CONF")   connection: $(sed -n 2p "$CONF")"; else echo "uplink: auto (not configured)"; fi
    ip rule show 2>/dev/null | grep "lookup $TABLE" || echo "no policy rule active"
    exit 0 ;;
  "") sed -n '2,12p' "$0"; exit 0 ;;
  *) apply ;;                                   # NetworkManager dispatcher: $1 = interface, $2 = action
esac
