"""System detection and the data about QGIS channels / supported distributions (no UI)."""
import os
import platform
import shutil
import subprocess

# ---------------------------------------------------------------- data
LATEST, LTR = "4.2.x", "3.44.x"           # per the QGIS installation guide (2026-10)
KEY_URL = "https://download.qgis.org/downloads/qgis-archive-keyring.gpg"
KEY_FPR = "2D7E3441A707FDB3E7059441D155B8E6A419C5BE"   # expires 2027-08-08
KEYRING = "/etc/apt/keyrings/qgis-archive-keyring.gpg"
SOURCES = "/etc/apt/sources.list.d/qgis.sources"

METHODS = "ABCDE"   # A official apt repository, B Flatpak, C distribution package, D container (Distrobox/Toolbx), E Nix

# immutable systems (the installation guide: Fedora Atomic Desktops, openSUSE MicroOS / Aeon / Kalpa)
ATOMIC_VARIANTS = {"silverblue", "kinoite", "sericea", "onyx", "cosmic", "budgie", "iot", "coreos"}
SUSE_IMMUTABLE_IDS = {"opensuse-microos", "opensuse-aeon", "opensuse-kalpa"}
AUR_HELPERS = ("yay", "paru")                 # the guide says "an AUR-capable helper" (yaourt is dead)
CONTAINER_BOX = "qgis-box"
OPENSUSE_IMAGE = "registry.opensuse.org/opensuse/toolbox:latest"          # from the guide (Distrobox example)
FEDORA_IMAGE = "registry.fedoraproject.org/fedora-toolbox"                # + ":<release>" (the guide shows rawhide)

# supported codenames -> LTR only?
SUPPORT = {
    "debian": {"bookworm": True, "trixie": False, "sid": False},
    "ubuntu": {"resolute": False, "questing": False, "plucky": False, "noble": True, "jammy": True},
}
# channel key -> repository suffix
SUFFIX = {"latest": "", "ltr": "-ltr", "nightly-release": "-nightly-release",
          "nightly-ltr": "-nightly-ltr", "nightly": "-nightly"}
CHANNELS = ["latest", "ltr", "nightly-release", "nightly-ltr", "nightly"]
LTR_ONLY_CHANNELS = ["ltr", "nightly-ltr"]


# ---------------------------------------------------------------- system detection
def read_os_release(path="/etc/os-release"):
    d = {}
    try:
        with open(path) as f:
            for line in f:
                if "=" in line:
                    k, v = line.rstrip("\n").split("=", 1)
                    d[k] = v.strip('"')
    except OSError:
        pass
    return d


def detect(os_release=None, pm=None, arch=None, which=None, exists=None):
    """Describe this system. ``os_release`` / ``pm`` / ``arch`` override the real values
    (used by tests and by ``--os-release`` to preview what would happen on another system);
    ``which`` / ``exists`` replace ``shutil.which`` / ``os.path.exists`` so tests are independent of the host."""
    which = which or shutil.which
    exists = exists or os.path.exists
    o = read_os_release(os_release or "/etc/os-release")
    like = (o.get("ID", "") + " " + o.get("ID_LIKE", "")).lower()
    family, code = None, o.get("VERSION_CODENAME", "")
    if o.get("UBUNTU_CODENAME"):
        family, code = "ubuntu", o["UBUNTU_CODENAME"]
    elif o.get("DEBIAN_CODENAME"):
        family, code = "debian", o["DEBIAN_CODENAME"]
    elif "ubuntu" in like:
        family = "ubuntu"
    elif "debian" in like:
        family = "debian"
    if pm is None:
        pm = next((m for m in ("apt-get", "dnf", "pacman", "zypper") if which(m)), "")
    if arch is None:
        if which("dpkg"):
            arch = subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True).stdout.strip()
        else:
            arch = platform.machine()
    supported, ltr_only = False, False
    if family and code in SUPPORT.get(family, {}):
        supported, ltr_only = True, SUPPORT[family][code]
    oid = o.get("ID", "")
    atomic = bool(exists("/run/ostree-booted")) or o.get("VARIANT_ID", "") in ATOMIC_VARIANTS
    tool = "distrobox" if which("distrobox") else ("toolbox" if which("toolbox") else "")
    return {"name": o.get("PRETTY_NAME", "Linux"), "family": family, "code": code, "pm": pm,
            "arch": arch, "supported": supported, "ltr_only": ltr_only,
            "apt": family is not None and pm == "apt-get",
            "id": oid, "version_id": o.get("VERSION_ID", ""),
            "atomic": atomic and "fedora" in like,          # rpm-ostree layering is the Fedora Atomic way
            "suse_immutable": oid in SUSE_IMMUTABLE_IDS,
            "aur_helper": next((h for h in AUR_HELPERS if which(h)), "") if pm == "pacman" else "",
            "container_tool": tool,
            "nix": bool(which("nix-shell")) or oid == "nixos"}


def installed_qgis():
    if not shutil.which("dpkg-query"):
        return None
    r = subprocess.run(["dpkg-query", "-W", "-f=${Status} ${Version}", "qgis"], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.startswith("install ok installed"):
        return r.stdout.split()[-1]
    return None


def method_available(method, sysinfo):
    """Is install method usable here? A official apt repository, B Flatpak, C distribution package,
    D container (Distrobox / Toolbx), E Nix (``nix-shell``)."""
    if method == "A":
        return bool(sysinfo["apt"] and sysinfo["supported"] and sysinfo["arch"] == "amd64")
    if method == "B":
        return True
    if method == "C":
        return bool(sysinfo["pm"]) or bool(sysinfo.get("atomic"))
    if method == "D":
        return bool(sysinfo.get("container_tool"))
    if method == "E":
        return bool(sysinfo.get("nix"))
    return False


def allowed_channels(sysinfo):
    """Channels the official repository offers for this system (LTR only on older bases)."""
    return LTR_ONLY_CHANNELS if sysinfo["ltr_only"] else CHANNELS


def default_channel(sysinfo):
    return "ltr" if sysinfo["ltr_only"] else "latest"


def channels_for(method, sysinfo):
    """Channels the chosen method can offer on this system ([] = the method has no channel choice).

    A: the official repository (LTR only on older bases).  C: Arch has ``qgis`` in the official repository and
    ``qgis-ltr`` / ``qgis-git`` in the AUR (needs an AUR helper), openSUSE has ``qgis`` and ``qgis-ltr``.
    D: the openSUSE image has both, the Fedora image only ``qgis``.  E: nixpkgs has ``qgis`` and ``qgis-ltr``."""
    if method == "A":
        return list(allowed_channels(sysinfo))
    if method == "C":
        if sysinfo.get("pm") == "pacman" and sysinfo.get("aur_helper"):
            return ["latest", "ltr", "nightly"]
        if sysinfo.get("pm") == "zypper" and not sysinfo.get("atomic"):
            return ["latest", "ltr"]
        return []
    if method == "D":
        return ["latest", "ltr"] if _container_is_suse(sysinfo) else []
    if method == "E":
        return ["latest", "ltr"]
    return []


def _container_is_suse(sysinfo):
    """The Distrobox example in the guide uses the openSUSE image; Fedora hosts get the Fedora toolbox image."""
    return sysinfo.get("container_tool") == "distrobox" and sysinfo.get("id") != "fedora"
