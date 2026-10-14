#!/usr/bin/env bash
# Wi-Fi Hotspot (WPA2) via NetworkManager — step by step.
# ეტაპობრივი Wi-Fi Hotspot (WPA2) NetworkManager-ით.
#
# Usage:  ./hotspot.sh <step>        (run without arguments for the list)
# Env:    IFACE=wlp3s0  SSID=MyHotspot  CHANNEL=1  HOTSPOT_PSK=...  CON=Hotspot
#
# Tested on: Linux Mint XFCE, Dell Precision M4700, Intel Centrino Advanced-N 6205 (iwlwifi).

set -uo pipefail

CON="${CON:-Hotspot}"
SSID="${SSID:-MyHotspot}"
CHANNEL="${CHANNEL:-1}"
IFACE="${IFACE:-$(nmcli -t -f DEVICE,TYPE device 2>/dev/null | awk -F: '$2=="wifi"{print $1; exit}')}"

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
  logs              last wpa_supplicant log lines (real error reasons)

Detected: IFACE=${IFACE:-none}  SSID=$SSID  CHANNEL=$CHANNEL  CON=$CON
EOT
}

step="${1:-}"; shift || true
case "$step" in
  check) step_check;; driver) step_driver;; create) step_create;; test-open) step_test_open;;
  secure) step_secure;; setup) step_setup;; up) step_up;; down) step_down;; status) step_status;;
  passwd) step_passwd;; ssid) step_ssid "$@";; docker-fix) step_docker_fix;;
  autostart-on) step_autostart_on;; autostart-off) step_autostart_off;;
  service-on) step_service_on;; logs) step_logs;;
  *) usage;;
esac
