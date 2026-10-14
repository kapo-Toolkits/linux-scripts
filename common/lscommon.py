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
