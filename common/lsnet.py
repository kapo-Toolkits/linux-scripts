"""Network device discovery shared by the Wi-Fi hotspot window: which Wi-Fi adapters can create a hotspot, and which
connected networks could be shared. Read-only (nmcli, iw, sysfs, ip); nothing is changed here. No UI."""
import os
import re
import subprocess

UPLINK_CONF = "/etc/linux-scripts/hotspot-uplink"           # written by wifi-hotspot/hotspot-uplink.sh


def _run(cmd, timeout=10):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return 1, str(e)


def split_nmcli(line):
    """nmcli -t escapes ':' inside values as '\\:' - split on the unescaped ones only."""
    return [p.replace("\\:", ":").replace("\\\\", "\\") for p in re.split(r"(?<!\\):", line)]


def parse_iw_phy_modes(text):
    """`iw phy` output -> {'phy0': {'managed', 'AP', ...}}: the interface modes each radio supports."""
    modes, phy, inside = {}, None, False
    for line in text.splitlines():
        m = re.match(r"Wiphy (\S+)", line)
        if m:
            phy, inside = m.group(1), False
            modes[phy] = set()
            continue
        if "Supported interface modes:" in line:
            inside = True
            continue
        if inside:
            m = re.match(r"\s+\* (\S+)", line)
            if m and phy:
                modes[phy].add(m.group(1))
            else:
                inside = False
    return modes


def _readlink_name(path):
    try:
        return os.path.basename(os.readlink(path))
    except OSError:
        return ""


def wifi_adapters(run=_run, sysfs="/sys/class/net"):
    """The Wi-Fi adapters NetworkManager knows: [{'dev', 'phy', 'driver', 'bus', 'model', 'ap', 'state', 'connection'}].
    'ap' is True only when the radio lists AP mode (a hotspot needs it); False when it does not; None when unknown."""
    rc, out = run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"])
    devs = []
    if rc == 0:
        for line in out.splitlines():
            f = split_nmcli(line)
            if len(f) >= 4 and f[1] == "wifi":
                devs.append({"dev": f[0], "state": f[2], "connection": f[3] if f[3] != "--" else ""})
    modes = parse_iw_phy_modes(run(["iw", "phy"])[1]) if devs else {}
    for d in devs:
        base = os.path.join(sysfs, d["dev"])
        d["phy"] = _readlink_name(os.path.join(base, "phy80211")) or ""
        if not d["phy"]:                                                   # phy80211 is a symlink to .../ieee80211/phyN
            try:
                d["phy"] = open(os.path.join(base, "phy80211", "name")).read().strip()
            except OSError:
                d["phy"] = ""
        d["driver"] = _readlink_name(os.path.join(base, "device", "driver"))
        d["bus"] = _readlink_name(os.path.join(base, "device", "subsystem"))
        props = run(["udevadm", "info", "-q", "property", "-p", base])[1] if os.path.exists(base) else ""
        vendor = model = ""
        for ln in props.splitlines():
            if ln.startswith("ID_VENDOR_FROM_DATABASE="):
                vendor = ln.split("=", 1)[1]
            elif ln.startswith("ID_MODEL_FROM_DATABASE="):
                model = ln.split("=", 1)[1]
        d["model"] = re.sub(r"\s*\[.*?\]|\s*\(.*\)$", "", (model or vendor or "").strip()).strip()
        d["ap"] = ("AP" in modes[d["phy"]]) if d["phy"] in modes and modes[d["phy"]] else None
    return devs


def adapter_label(a, ap_yes="can host a hotspot", ap_no="cannot host a hotspot", ap_unknown="not sure"):
    """One line for a drop-down: 'wlp3s0 — Intel Centrino Advanced-N 6205 (iwlwifi, PCI) · can host a hotspot'."""
    what = a.get("model") or a.get("driver") or "Wi-Fi"
    extra = ", ".join(x for x in (a.get("driver"), (a.get("bus") or "").upper()) if x)
    flag = ap_yes if a.get("ap") else ap_no if a.get("ap") is False else ap_unknown
    return f"{a['dev']} — {what}" + (f" ({extra})" if extra else "") + f" · {flag}"


def default_routes(run=_run):
    """{device: gateway or ''} for every IPv4 default route (the devices that have a way to the internet)."""
    out = {}
    for line in run(["ip", "-4", "route", "show", "default"])[1].splitlines():
        words = line.split()
        if "dev" in words:
            dev = words[words.index("dev") + 1]
            out.setdefault(dev, words[words.index("via") + 1] if "via" in words else "")
    return out


def uplink_choices(ap_dev, hotspot_con="Hotspot", run=_run):
    """Networks that could be shared with the hotspot: connected devices that have a default route, except the hotspot adapter
    itself. -> [{'dev', 'type', 'connection', 'gateway'}] (cable first, then Wi-Fi, then mobile / other)."""
    routes = default_routes(run)
    rc, out = run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"])
    found = []
    if rc != 0:
        return found
    for line in out.splitlines():
        f = split_nmcli(line)
        if len(f) < 4 or f[0] == ap_dev or f[3] == hotspot_con or not f[2].startswith("connected") or f[0] not in routes:
            continue
        if f[1] in ("loopback", "bridge", "tun", "veth", "bond", "team", "vlan"):
            continue
        found.append({"dev": f[0], "type": f[1], "connection": f[3], "gateway": routes[f[0]]})
    order = {"ethernet": 0, "wifi": 1}
    return sorted(found, key=lambda x: (order.get(x["type"], 2), x["dev"]))


def uplink_label(u, kinds=None):
    kinds = kinds or {"ethernet": "cable", "wifi": "Wi-Fi"}
    return f"{u['dev']} — {kinds.get(u['type'], u['type'])} · {u['connection']}" + (f" → {u['gateway']}" if u["gateway"] else "")


def current_uplink(path=UPLINK_CONF):
    """The device the hotspot is set to share ('' = automatic / not configured)."""
    try:
        with open(path) as f:
            first = f.readline().strip()
    except OSError:
        return ""
    return "" if first in ("", "auto") else first


def helper_path(here, extra=("/usr/local/lib/linux-scripts", "/usr/lib/linux-scripts")):
    """The hotspot-uplink.sh next to the window (checkout) or in the installed lib folder, or ''."""
    for d in (here, os.path.join(here, "..", "lib", "linux-scripts")) + tuple(extra):
        p = os.path.join(d, "hotspot-uplink.sh")
        if os.path.isfile(p):
            return os.path.abspath(p)
    return ""
