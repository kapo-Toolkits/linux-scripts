#!/usr/bin/env bash
# Wi-Fi Hotspot (WPA2) via NetworkManager — step by step.
# ეტაპობრივი Wi-Fi Hotspot (WPA2) NetworkManager-ით.
#
# Usage:  ./hotspot.sh <step>        (run without arguments for the list)
# Env:    IFACE=wlp3s0  SSID=MyHotspot  CHANNEL=1  HOTSPOT_PSK=...  CON=Hotspot
#         (IFACE = the Wi-Fi adapter that sends out the hotspot; with two adapters see:  ./hotspot.sh devices)
#
# Tested on: Linux Mint XFCE, Dell Precision M4700, Intel Centrino Advanced-N 6205 (iwlwifi).

set -uo pipefail

CON="${CON:-Hotspot}"
SSID="${SSID:-MyHotspot}"
CHANNEL="${CHANNEL:-1}"
wifi_devices() { nmcli -t -f DEVICE,TYPE device 2>/dev/null | awk -F: '$2=="wifi"{print $1}'; }
# can this adapter's radio create an access point (hotspot)?
can_ap() { local phy; phy=$(cat "/sys/class/net/$1/phy80211/name" 2>/dev/null) || return 1
           iw phy "$phy" info 2>/dev/null | awk '/Supported interface modes/{f=1;next} f&&/^[ \t]+\* /{if($2=="AP")ok=1;next} f{f=0} END{exit ok?0:1}'; }
# the adapter to use: the first that can host a hotspot (a second, USB adapter often cannot), else the first Wi-Fi device
pick_iface() { local d first=""; for d in $(wifi_devices); do [[ -n "$first" ]] || first="$d"; can_ap "$d" && { echo "$d"; return; }; done; echo "$first"; }
IFACE="${IFACE:-$(pick_iface)}"

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die()  { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }
need_iface() { [[ -n "$IFACE" ]] || die "Wi-Fi interface not found. Set it: IFACE=wlp3s0 $0 $step"; }

step_check() {
  say "1/9  nmcli device status"; nmcli device status
  say "rfkill (both must be 'no')"; rfkill list
  say "AP mode support (look for '* AP')"; iw list 2>/dev/null | grep -A10 "Supported interface modes"
  say "dnsmasq-base / network-manager"
  dpkg -l 2>/dev/null | grep -E "dnsmasq-base|network-manager " | awk '{print $2, $3}'
  dpkg -s dnsmasq-base >/dev/null 2>&1 || echo "dnsmasq-base missing → sudo apt install dnsmasq-base"
  say "Detected Wi-Fi interface: ${IFACE:-none}"
  if command -v iptables >/dev/null && sudo -n true 2>/dev/null; then
    say "FORWARD policy (DROP + Docker = no internet for clients → step docker-fix)"
    sudo iptables -S FORWARD | head -3
  fi
}

step_driver() {
  say "2/9  iwlwifi swcrypto=1 (needs reboot)"
  echo "options iwlwifi swcrypto=1" | sudo tee /etc/modprobe.d/iwlwifi-swcrypto.conf
  if command -v update-initramfs >/dev/null; then sudo update-initramfs -u
  elif command -v dracut >/dev/null; then sudo dracut --force
  else echo "No initramfs tool found — rebuild it manually."; fi
  echo "Reboot, then verify:  cat /sys/module/iwlwifi/parameters/swcrypto   (expect 1 or Y)"
}

step_create() {
  need_iface
  say "3/9  Create profile '$CON' (iface=$IFACE ssid=$SSID ch=$CHANNEL, 2.4 GHz, open)"
  nmcli con delete "$CON" 2>/dev/null
  nmcli con add type wifi ifname "$IFACE" con-name "$CON" autoconnect no ssid "$SSID" || die "add failed"
  nmcli con modify "$CON" 802-11-wireless.mode ap 802-11-wireless.band bg \
    802-11-wireless.channel "$CHANNEL" 802-11-wireless.powersave 2 ipv4.method shared
}

step_test_open() {
  need_iface
  say "4/9  Open-network test (diagnostic only — do not leave it running!)"
  nmcli con up "$CON" || die "Failed. Check: journalctl -u wpa_supplicant -b --no-pager | tail -30"
  iw dev "$IFACE" info | grep -E "type|channel"
  ip -4 addr show "$IFACE"
  echo "Expect: type AP, channel $CHANNEL, 10.42.0.1/24. Then run: $0 secure"
}

step_secure() {
  need_iface
  local psk="${HOTSPOT_PSK:-}"
  if [[ -z "$psk" ]]; then
    read -r -s -p "WPA2 password (Latin, 8-63 chars): " psk; echo
    read -r -s -p "Repeat: " psk2; echo
    [[ "$psk" == "$psk2" ]] || die "Passwords differ."
  fi
  [[ ${#psk} -ge 8 && ${#psk} -le 63 && "$psk" =~ ^[[:print:]]+$ && ! "$psk" =~ [^[:ascii:]] ]] \
    || die "Password must be 8-63 printable Latin/ASCII characters."
  say "5/9  WPA2-PSK"
  nmcli con modify "$CON" wifi-sec.key-mgmt wpa-psk wifi-sec.proto rsn wifi-sec.pairwise ccmp \
    wifi-sec.group ccmp wifi-sec.psk "$psk" || die "modify failed"
  nmcli con modify "$CON" 802-11-wireless-security.psk-flags 0
  nmcli con modify "$CON" 802-11-wireless-security.pmf 1
  nmcli con down "$CON" 2>/dev/null
  nmcli con up "$CON" || die "Failed. Check: journalctl -u wpa_supplicant -b --no-pager | tail -30"
  iw dev "$IFACE" info | grep -E "type|channel"
  nmcli -f 802-11-wireless-security.key-mgmt,802-11-wireless-security.pmf,802-11-wireless-security.psk-flags con show "$CON"
}

step_up()     { say "Hotspot ON";  nmcli con up "$CON"; }
step_down()   { say "Hotspot OFF"; nmcli con down "$CON"; }
step_status() { need_iface; nmcli con show --active; iw dev "$IFACE" info | grep type; }

step_passwd() {
  read -r -s -p "New WPA2 password (Latin, 8-63 chars): " psk; echo
  [[ ${#psk} -ge 8 && ${#psk} -le 63 && ! "$psk" =~ [^[:print:]] && ! "$psk" =~ [^[:ascii:]] ]] || die "Invalid password."
  nmcli con modify "$CON" wifi-sec.psk "$psk" && nmcli con down "$CON"; nmcli con up "$CON"
}

step_ssid() {
  local new="${1:-}"; [[ -n "$new" ]] || die "Usage: $0 ssid <new name>"
  nmcli con modify "$CON" 802-11-wireless.ssid "$new" && nmcli con down "$CON"; nmcli con up "$CON"
}

step_docker_fix() {
  say "7/9  Docker FORWARD DROP → ACCEPT (persistent)"
  sudo mkdir -p /etc/systemd/system/docker.service.d
  sudo tee /etc/systemd/system/docker.service.d/forward-accept.conf >/dev/null <<'EOT'
[Service]
ExecStartPost=/usr/sbin/iptables -P FORWARD ACCEPT
EOT
  sudo systemctl daemon-reload && sudo systemctl restart docker
  sudo iptables -S FORWARD | head -2
}

step_autostart_on() {
  say "9/9  Autostart: NetworkManager autoconnect"
  nmcli con modify "$CON" connection.autoconnect yes
  nmcli -f connection.autoconnect con show "$CON"
  echo "Reboot and verify. If it does not come up, use: $0 service-on"
}

step_autostart_off() {
  nmcli con modify "$CON" connection.autoconnect no
  sudo systemctl disable hotspot.service 2>/dev/null || true
  echo "Autostart disabled."
}

step_service_on() {
  say "Autostart: systemd service (waits 10 s for Wi-Fi)"
  sudo tee /etc/systemd/system/hotspot.service >/dev/null <<EOT
[Unit]
Description=Start Wi-Fi Hotspot
After=NetworkManager.service network-online.target
Wants=NetworkManager.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=/usr/bin/sleep 10
ExecStart=/usr/bin/nmcli con up id $CON

[Install]
WantedBy=multi-user.target
EOT
  sudo systemctl daemon-reload && sudo systemctl enable hotspot.service
  nmcli con modify "$CON" connection.autoconnect no
  echo "Enabled. Logs: journalctl -u hotspot.service -b --no-pager | tail -20"
}

step_clients() {
  need_iface
  iw dev "$IFACE" info 2>/dev/null | grep -q "type AP" || die "Hotspot is not running (interface not in AP mode). Run: $0 up"
  local leases neigh
  leases=$(cat "${HOTSPOT_LEASES:-/var/lib/NetworkManager/dnsmasq-$IFACE.leases}" /var/lib/misc/dnsmasq.leases 2>/dev/null || true)
  neigh=$(ip neigh show dev "$IFACE" 2>/dev/null || true)
  iw dev "$IFACE" station dump | LC_ALL=C awk -v neigh="$neigh" -v leases="$leases" '
    function secs(s,  h, m) { h=int(s/3600); m=int((s%3600)/60); return h ? h "h " m "m" : (m ? m "m " (s%60) "s" : s "s") }
    function mb(b) { return b >= 1048576 ? sprintf("%.1f MB", b/1048576) : sprintf("%.0f KB", b/1024) }
    function out() { if (mac == "") return; n++
      printf "%-17s %-15s %-16s %8s %9s %10s %10s\n", mac, (mac in ip ? ip[mac] : "-"), (mac in host ? host[mac] : "-"), (sig == "" ? "-" : sig " dBm"), secs(ct), mb(rx), mb(tx) }
    BEGIN {
      m = split(neigh, nl, "\n")
      for (i = 1; i <= m; i++) { k = split(nl[i], f, " "); for (j = 2; j < k; j++) if (f[j] == "lladdr") { mc = tolower(f[j+1]); if (!(mc in ip) || index(ip[mc], ":")) ip[mc] = f[1] } }
      m = split(leases, ll, "\n")
      for (i = 1; i <= m; i++) { k = split(ll[i], f, " "); if (k >= 4) { mc = tolower(f[2]); ip[mc] = f[3]; if (f[4] != "*") host[mc] = f[4] } }
      printf "%-17s %-15s %-16s %8s %9s %10s %10s\n", "MAC", "IP", "NAME", "SIGNAL", "CONNECTED", "DOWN", "UP"
    }
    /^Station / { out(); mac = tolower($2); sig = ""; ct = 0; rx = 0; tx = 0 }
    /signal:/ && !/avg/ { sig = $2 }
    /connected time:/ { ct = $3 }
    /rx bytes:/ { rx = $3 }
    /tx bytes:/ { tx = $3 }
    END { out(); if (n == 0) print "(no devices connected)" }'
}

step_qr() {
  local ssid psk lsqr="" d here
  ssid=$(nmcli -e no -g 802-11-wireless.ssid con show "$CON" 2>/dev/null) || die "Profile '$CON' not found. Run: $0 create"
  psk=$(nmcli -e no -s -g 802-11-wireless-security.psk con show "$CON" 2>/dev/null || true)
  here="$(dirname "$(readlink -f "$0")")"
  for d in "$here/../common" "$here/../lib/linux-scripts" /usr/local/lib/linux-scripts /usr/lib/linux-scripts; do
    if [[ -f "$d/lsqr.py" ]]; then lsqr="$d/lsqr.py"; break; fi
  done
  [[ -n "$lsqr" ]] || die "lsqr.py not found — use the repository checkout or ./install.sh wifi-hotspot"
  command -v python3 >/dev/null || die "python3 is required for the QR code"
  echo "SSID: $ssid   (scan with the phone camera; anyone who sees this gets the password)"
  python3 "$lsqr" --wifi "$ssid" "$psk"
}

step_devices() {
  say "Wi-Fi adapters (the hotspot is sent out by ONE of them: IFACE=<name> $0 setup)"
  local d phy drv ap
  for d in $(wifi_devices); do
    phy=$(cat "/sys/class/net/$d/phy80211/name" 2>/dev/null || echo "?")
    drv=$(basename "$(readlink -f "/sys/class/net/$d/device/driver" 2>/dev/null)" 2>/dev/null)
    can_ap "$d" && ap="can host a hotspot" || ap="cannot host a hotspot (no AP mode)"
    printf '  %-18s %-6s %-12s %s%s\n' "$d" "$phy" "${drv:-?}" "$ap" "$([[ "$d" == "$IFACE" ]] && echo '   <- selected')"
  done
  say "Networks that could be shared (connected, with a default route)"
  ip -4 route show default | awk '{for(i=1;i<NF;i++){if($i=="dev")d=$(i+1); if($i=="via")g=$(i+1)} print "  " d "  gateway " g}'
  say "Currently shared network"; helper status
}

hotspot_helper() {
  local here d; here="$(dirname "$(readlink -f "$0")")"
  for d in "$here" "$here/../lib/linux-scripts" /usr/local/lib/linux-scripts /usr/lib/linux-scripts; do
    [[ -f "$d/hotspot-uplink.sh" ]] && { echo "$d/hotspot-uplink.sh"; return; }
  done
}
helper() { local h; h=$(hotspot_helper); [[ -n "$h" ]] || die "hotspot-uplink.sh not found - use the repository checkout or ./install.sh wifi-hotspot"; sh "$h" "$@"; }

step_uplink() {   # ./hotspot.sh uplink eno1   |   uplink auto   |   uplink (show)
  local dev="${1:-}"
  if [[ -z "$dev" ]]; then helper status; return; fi
  local h; h=$(hotspot_helper); [[ -n "$h" ]] || die "hotspot-uplink.sh not found"
  say "Sending the hotspot's internet through: $dev  (needs administrator rights)"
  sudo sh "$h" install "$dev" "$CON"
}

step_logs() { journalctl -u wpa_supplicant -b --no-pager | tail -30; }

step_setup() { step_create && step_secure; }

usage() {
  cat <<EOT
Hotspot steps (run in this order on a fresh install):

  check          1  inspect interface, rfkill, AP support, dnsmasq
  driver         2  iwlwifi swcrypto=1 + initramfs   (reboot afterwards)
  create         3  create the profile (2.4 GHz, ch $CHANNEL, shared/NAT)
  test-open      4  bring it up as an OPEN network to verify AP works
  secure         5  set WPA2 password and bring it up
  setup             = create + secure
  up | down | status      daily use
  passwd | ssid <name>    change password / network name
  docker-fix     7  persistent fix if Docker blocks forwarding
  autostart-on   9  start at boot via NetworkManager   (autostart-off to undo)
  service-on        start at boot via systemd service   (fallback)
  clients           list devices connected to the running hotspot (IP, signal, time, traffic)
  devices           list Wi-Fi adapters (which can host a hotspot) and the networks that could be shared
  uplink [dev|auto] choose which network the hotspot shares (e.g. eno1 = cable, or a second Wi-Fi adapter); no argument = show
  qr                show a QR code to join the hotspot (phone camera)
  logs              last wpa_supplicant log lines (real error reasons)

Detected: IFACE=${IFACE:-none}  SSID=$SSID  CHANNEL=$CHANNEL  CON=$CON
EOT
}

step="${1:-}"; shift || true
case "$step" in
  check) step_check;; driver) step_driver;; create) step_create;; test-open) step_test_open;;
  secure) step_secure;; qr) step_qr;; clients) step_clients;; setup) step_setup;; up) step_up;; down) step_down;; status) step_status;;
  passwd) step_passwd;; ssid) step_ssid "$@";; docker-fix) step_docker_fix;;
  autostart-on) step_autostart_on;; autostart-off) step_autostart_off;;
  service-on) step_service_on;; logs) step_logs;; devices) step_devices;; uplink) step_uplink "$@";;
  *) usage;;
esac
