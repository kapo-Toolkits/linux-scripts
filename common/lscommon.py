"""Shared helpers for the linux-scripts GUIs (tkinter bootstrap, subprocess runner, remembered language).

Found next to the tools (../common) when run from the repo, or in /usr/local/lib/linux-scripts after ./install.sh.
"""
import os
import shutil
import subprocess
import sys

LANG_FILE = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
                         "linux-scripts", "lang")

# package manager -> (install command, tkinter package)
TK_PACKAGES = [
    ("apt-get", ["apt-get", "install", "-y"], "python3-tk"),
    ("dnf", ["dnf", "install", "-y"], "python3-tkinter"),
    ("yum", ["yum", "install", "-y"], "python3-tkinter"),
    ("pacman", ["pacman", "-S", "--noconfirm"], "tk"),
    ("zypper", ["zypper", "--non-interactive", "install"], "python3-tk"),
    ("apk", ["apk", "add"], "py3-tkinter"),
    ("xbps-install", ["xbps-install", "-y"], "python3-tkinter"),
]


def load_lang(default="en"):
    """Language chosen last time in any tool ('en' or 'ka'); English if never chosen."""
    try:
        with open(LANG_FILE) as f:
            v = f.read().strip()
        return v if v in ("en", "ka") else default
    except OSError:
        return default


def save_lang(lang):
    try:
        os.makedirs(os.path.dirname(LANG_FILE), exist_ok=True)
        with open(LANG_FILE, "w") as f:
            f.write(lang)
    except OSError:
        pass


def run(cmd, timeout=None):
    """-> (returncode, stdout+stderr stripped). Never raises."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:
        return 1, str(e)


def ensure_tkinter():
    """If tkinter is missing, ask, install it with the system package manager and restart the program."""
    try:
        import tkinter  # noqa: F401
        return
    except ImportError:
        pass
    for mgr, cmd, pkg in TK_PACKAGES:
        if shutil.which(mgr):
            break
    else:
        sys.exit("tkinter is missing and no known package manager was found. Install: "
                 "python3-tk / python3-tkinter / tk\n"
                 "tkinter ვერ მოიძებნა; დააყენეთ ხელით: python3-tk / python3-tkinter / tk")
    if sys.stdin.isatty():
        if input(f"tkinter is missing. Install {pkg}? / დავაყენო {pkg}? [Y/n] ").strip().lower() not in ("", "y", "yes"):
            sys.exit("Cancelled. / გაუქმდა.")
    # graphical password prompt when launched from a menu, sudo in a terminal
    elevate = ["pkexec"] if shutil.which("pkexec") and os.environ.get("DISPLAY") else ["sudo"]
    if mgr == "apt-get":
        subprocess.run(elevate + ["apt-get", "update"])
    if subprocess.run(elevate + cmd + [pkg]).returncode != 0:
        sys.exit(f"Could not install {pkg}. / {pkg}-ის დაყენება ვერ მოხერხდა.")
    os.execv(sys.executable, [sys.executable] + sys.argv)


# ---------------------------------------------------------------- missing-tool hints (any distribution)
PM_ORDER = ("apt-get", "dnf", "yum", "pacman", "zypper", "apk", "xbps-install")

# command -> package providing it, per package manager
_ALL = lambda p: {pm: p for pm in PM_ORDER}   # noqa: E731
PKG_FOR = {
    "udisksctl": _ALL("udisks2"),
    "lsblk": {"apt-get": "util-linux", "dnf": "util-linux", "yum": "util-linux", "pacman": "util-linux",
              "zypper": "util-linux", "apk": "lsblk", "xbps-install": "util-linux"},
    "nmcli": {"apt-get": "network-manager", "dnf": "NetworkManager", "yum": "NetworkManager",
              "pacman": "networkmanager", "zypper": "NetworkManager", "apk": "networkmanager-cli",
              "xbps-install": "NetworkManager"},
    "iw": _ALL("iw"),
    "ip": {"apt-get": "iproute2", "dnf": "iproute", "yum": "iproute", "pacman": "iproute2",
           "zypper": "iproute2", "apk": "iproute2", "xbps-install": "iproute2"},
    "lpinfo": _ALL("cups"),
    "lpadmin": _ALL("cups"),
    "lp": _ALL("cups"),
}
_INSTALL_FMT = {"apt-get": "sudo apt install {p}", "dnf": "sudo dnf install {p}", "yum": "sudo yum install {p}",
                "pacman": "sudo pacman -S {p}", "zypper": "sudo zypper install {p}",
                "apk": "doas apk add {p}   (or: sudo apk add {p})", "xbps-install": "sudo xbps-install {p}"}
DEPS_TEXT = {
    "en": "Missing programs: {names}\n\nInstall them with:\n{cmd}\n\nThe app keeps running, but these functions will not work until then.",
    "ka": "აკლია პროგრამები: {names}\n\nდააყენეთ ბრძანებით:\n{cmd}\n\nაპი გაგრძელებს მუშაობას, მაგრამ ამ ფუნქციები დაყენებამდე არ იმუშავებს.",
}


def detect_pm():
    return next((m for m in PM_ORDER if shutil.which(m)), "")


def missing_tools(cmds, pm=None):
    """-> [(command, package or None)] for commands not on PATH."""
    pm = detect_pm() if pm is None else pm
    return [(c, PKG_FOR.get(c, {}).get(pm)) for c in cmds if not shutil.which(c)]


def install_command(missing, pm=None):
    pm = detect_pm() if pm is None else pm
    pkgs = sorted({p for _, p in missing if p})
    if not pkgs or pm not in _INSTALL_FMT:
        return ""
    return _INSTALL_FMT[pm].format(p=" ".join(pkgs))


def warn_missing(cmds, lang, title):
    """Show a bilingual 'install these' hint if any command is absent. Returns True if something was missing."""
    miss = missing_tools(cmds)
    if not miss:
        return False
    from tkinter import messagebox
    cmd = install_command(miss) or ("(see your distribution's documentation)" if lang == "en" else "(იხილეთ თქვენი დისტრიბუციის დოკუმენტაცია)")
    messagebox.showwarning(title, DEPS_TEXT.get(lang, DEPS_TEXT["en"]).format(names=", ".join(c for c, _ in miss), cmd=cmd))
    return True
PKG_FOR["bluetoothctl"] = {"apt-get": "bluez", "dnf": "bluez", "yum": "bluez", "pacman": "bluez-utils",
                           "zypper": "bluez", "apk": "bluez", "xbps-install": "bluez"}
PKG_FOR["brasero"] = _ALL("brasero")          # CD/DVD burner, in every major distribution's own repositories
