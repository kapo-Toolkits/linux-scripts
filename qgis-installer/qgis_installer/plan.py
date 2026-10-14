"""Turning a choice (method, channel, packages) into shell steps: [{"root": bool, "sh": str}]. No UI."""
import shutil

from . import system
from .system import SUFFIX


def sources_text(sysinfo, channel):
    uri = f"https://qgis.org/{sysinfo['family']}{SUFFIX[channel]}"
    return (f"Types: deb\nURIs: {uri}\nSuites: {sysinfo['code']}\nArchitectures: amd64\n"
            f"Components: main\nSigned-By: {system.KEYRING}\n")


def build_install(method, sysinfo, channel, pkgs):
    """-> list of steps {root: bool, sh: str}. POSIX sh only."""
    if method == "A":
        names = ["qgis"] + (["qgis-plugin-grass"] if pkgs["grass"] else []) + (["python3-qgis"] if pkgs["python"] else [])
        steps = [
            {"root": True, "sh": f"""set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y wget gnupg ca-certificates
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
wget -qO "$TMP/key.gpg" {system.KEY_URL}
mkdir -m700 "$TMP/gnupg"
FPR=$(gpg --homedir "$TMP/gnupg" --no-default-keyring --keyring "$TMP/key.gpg" --list-keys --with-colons | awk -F: '$1=="fpr"{{print $10; exit}}')
if [ "$FPR" != "{system.KEY_FPR}" ]; then echo "KEY FINGERPRINT MISMATCH: $FPR" >&2; exit 1; fi
echo "Key fingerprint OK: $FPR"
install -m755 -d /etc/apt/keyrings
install -m644 "$TMP/key.gpg" {system.KEYRING}
cat > {system.SOURCES} <<'EOF'
{sources_text(sysinfo, channel)}EOF
apt-get update
apt-get install -y {' '.join(names)}
"""}]
        if pkgs["server"]:
            steps[0]["sh"] += "apt-get install -y --no-install-recommends --no-install-suggests qgis-server\n"
        return steps
    if method == "B":
        steps = []
        if not shutil.which("flatpak"):
            pm = sysinfo["pm"]
            inst = {"apt-get": "apt-get install -y flatpak", "dnf": "dnf install -y flatpak",
                    "pacman": "pacman -S --noconfirm flatpak", "zypper": "zypper --non-interactive install flatpak"}.get(pm)
            if inst:
                steps.append({"root": True, "sh": "set -eu\n" + inst + "\n"})
        steps.append({"root": False, "sh": """set -eu
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user -y flathub org.qgis.qgis
"""})
        return steps
    if method == "D":
        return _container_steps(sysinfo, channel, pkgs)
    if method == "E":
        pkg = "qgis-ltr" if channel == "ltr" else "qgis"
        return [{"root": False, "sh": f"set -eu\nnix-shell -p {pkg} --command qgis\n"}]
    return _distribution_steps(sysinfo, channel, pkgs)


def _dist_names(pm, channel, pkgs):
    """Package names of the distribution's own QGIS, following the installation guide:
    Fedora ``qgis python3-qgis qgis-grass qgis-server``, openSUSE ``qgis qgis-plugin-grass`` (+ ``qgis-ltr``)."""
    if pm == "dnf":
        return ["qgis"] + (["python3-qgis"] if pkgs["python"] else []) + (["qgis-grass"] if pkgs["grass"] else []) \
            + (["qgis-server"] if pkgs["server"] else [])
    if pm == "zypper":
        return ["qgis-ltr" if channel == "ltr" else "qgis"] + (["qgis-plugin-grass"] if pkgs["grass"] else [])
    if pm == "apt-get":
        return ["qgis"] + (["qgis-plugin-grass"] if pkgs["grass"] else []) + (["python3-qgis"] if pkgs["python"] else []) \
            + (["qgis-server"] if pkgs["server"] else [])
    return ["qgis"]


def _distribution_steps(sysinfo, channel, pkgs):
    pm = sysinfo["pm"]
    names = _dist_names(pm, channel, pkgs)
    if sysinfo.get("atomic"):       # Fedora Atomic Desktops: layer the packages (needs a reboot)
        return [{"root": True, "sh": "set -eu\nrpm-ostree install --idempotent " + " ".join(names)
                 + "\necho 'Reboot to use the layered packages (systemctl reboot).'\n"}]
    if pm == "pacman":
        helper = sysinfo.get("aur_helper")
        aur = {"ltr": "qgis-ltr", "nightly": "qgis-git"}.get(channel)
        if aur and helper:          # not in the official repository: AUR, built by the user's helper
            return [{"root": False, "sh": f"set -eu\n{helper} -S --needed {aur}\n"}]
        return [{"root": True, "sh": "set -eu\npacman -S --noconfirm qgis\n"}]
    cmd = {"apt-get": "apt-get install -y ", "dnf": "dnf install -y ",
           "zypper": "zypper --non-interactive install "}.get(pm)
    return [{"root": True, "sh": f"set -eu\n{cmd}{' '.join(names)}\n"}] if cmd else []


def _container_steps(sysinfo, channel, pkgs):
    """Distrobox / Toolbx container with QGIS inside (for immutable systems). Guide: the openSUSE image for
    Distrobox, the Fedora toolbox image for Toolbx; the Fedora image is pinned to the host's release."""
    tool, box = sysinfo.get("container_tool"), system.CONTAINER_BOX
    fedora_host = sysinfo.get("id") == "fedora"
    fimg = system.FEDORA_IMAGE + ":" + (sysinfo.get("version_id") or "latest")
    use_suse = tool == "distrobox" and not fedora_host
    image = system.OPENSUSE_IMAGE if use_suse else fimg
    pm = "zypper" if use_suse else "dnf"
    inst = {"zypper": "sudo zypper --non-interactive install ", "dnf": "sudo dnf install -y "}[pm] \
        + " ".join(_dist_names(pm, channel, pkgs))
    if tool == "distrobox":
        sh = (f"set -eu\ndistrobox list | grep -q '{box}' || distrobox create --yes --name {box} --image {image}\n"
              f"distrobox enter --name {box} -- {inst}\n"
              f"distrobox enter --name {box} -- distrobox-export --app qgis\n")
    elif tool == "toolbox":
        sh = (f"set -eu\ntoolbox list --containers | grep -q '{box}' || toolbox create --container {box} --image {image}\n"
              f"toolbox run --container {box} {inst}\n"
              f"echo 'Start QGIS with: toolbox run --container {box} qgis'\n")
    else:
        return []
    return [{"root": False, "sh": sh}]


def steps_script(steps):
    """All steps as one POSIX shell script (what ``--script`` prints)."""
    out = ["#!/bin/sh"]
    for s in steps:
        out.append("# " + ("run as root" if s["root"] else "run as your user"))
        out.append(s["sh"].rstrip())
        out.append("")
    return "\n".join(out)
