#!/bin/sh
# Runs INSIDE a privileged container: real kernel routing with dummy interfaces and a fake nmcli (no NetworkManager here).
# eth1 = "cable" (gw 10.1.0.254), wlx2 = "second Wi-Fi" (gw 10.2.0.254), ap0 = the hotspot interface (10.42.0.1/24).
set -u
fail=0
ok()  { echo "PASS $1"; }
bad() { echo "FAIL $1"; fail=1; }
apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq iproute2 >/dev/null 2>&1 || { echo "FAIL could not install iproute2"; exit 1; }
for d in eth1 wlx2 ap0; do ip link add "$d" type dummy; ip link set "$d" up; done
ip addr add 10.1.0.2/24 dev eth1; ip addr add 10.2.0.2/24 dev wlx2; ip addr add 10.42.0.1/24 dev ap0
ip route add default via 10.1.0.254 dev eth1 metric 100
ip route add default via 10.2.0.254 dev wlx2 metric 200
mkdir -p /fake; cat > /fake/nmcli <<'N'
#!/bin/sh
# only: nmcli -t -f DEVICE,CONNECTION device
[ -n "${FAKE_AP:-}" ] && printf 'ap0:Hotspot\neth1:Wired\nwlx2:Home\n' || printf 'eth1:Wired\nwlx2:Home\n'
N
chmod +x /fake/nmcli
export PATH="/fake:$PATH" HOTSPOT_UPLINK_CONF=/tmp/uplink.conf HOTSPOT_UPLINK_DISPATCH=/tmp/dispatch.sh
S=/repo/wifi-hotspot/hotspot-uplink.sh

own_before=$(ip route get 8.8.8.8 | awk '{for(i=1;i<NF;i++) if($i=="dev"){print $(i+1);exit}}')
FAKE_AP=1 sh $S install wlx2 >/dev/null || bad "install returns 0"
[ -x /tmp/dispatch.sh ] && ok "dispatcher copied and executable" || bad "dispatcher copied"
ip rule show | grep -q "from 10.42.0.0/24 lookup 4242" && ok "policy rule for the hotspot subnet" || bad "policy rule"
ip route show table 4242 | grep -q "default via 10.2.0.254 dev wlx2" && ok "table 4242 default goes through the chosen network" || bad "table default"
ip route show table 4242 | grep -q "10.42.0.0/24 dev ap0" && ok "table 4242 keeps the hotspot subnet local (DHCP/DNS replies)" || bad "local route in table"
[ "$(ip route get 8.8.8.8 | awk '{for(i=1;i<NF;i++) if($i=="dev"){print $(i+1);exit}}')" = "$own_before" ] && ok "the computer's own traffic is not re-routed" || bad "own traffic unchanged"
[ "$(ip route get 8.8.8.8 from 10.42.0.5 iif ap0 | awk '{for(i=1;i<NF;i++) if($i=="dev"){print $(i+1);exit}}')" = wlx2 ] && ok "a hotspot client's traffic goes out through wlx2" || bad "client traffic path"

FAKE_AP=1 sh /tmp/dispatch.sh wlx2 dhcp4-change; FAKE_AP=1 sh /tmp/dispatch.sh wlx2 up
[ "$(ip rule show | grep -c 'lookup 4242')" = 1 ] && ok "running it again does not pile up rules" || bad "idempotent"

ip route del default via 10.2.0.254 dev wlx2 metric 200
FAKE_AP=1 sh /tmp/dispatch.sh wlx2 down
ip rule show | grep -q "lookup 4242" && bad "rule removed when the chosen network has no route" || ok "no rule while the chosen network is down"

ip route add default via 10.2.0.254 dev wlx2 metric 200
FAKE_AP=1 sh /tmp/dispatch.sh wlx2 up
ip rule show | grep -q "lookup 4242" && ok "rule is back when the network returns" || bad "rule returns"

sh /tmp/dispatch.sh wlx2 up        # hotspot not running (fake nmcli shows no ap0)
ip rule show | grep -q "lookup 4242" && bad "rule removed when the hotspot is off" || ok "nothing routed while the hotspot is off"

FAKE_AP=1 sh $S install eth1 >/dev/null; ip route show table 4242 | grep -q "default via 10.1.0.254 dev eth1" && ok "switching to the cable re-routes" || bad "switch to eth1"
FAKE_AP=1 sh $S install auto >/dev/null
{ ip rule show | grep -q "lookup 4242" || [ -e /tmp/dispatch.sh ]; } && bad "auto removes everything" || ok "auto removes rule and dispatcher"

printf 'wlx2;touch /tmp/pwned\n' | sh $S install "wlx2;touch /tmp/pwned" >/dev/null 2>&1
[ ! -e /tmp/pwned ] && ok "a hostile device name runs nothing" || bad "injection"
exit $fail
