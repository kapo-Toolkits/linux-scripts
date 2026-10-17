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
    ("apk", ["apk", "add"], "python3-tkinter"),
    ("xbps-install", ["xbps-install", "-y"], "python3-tkinter"),
]


# what installer/start.sh installs when the system has no Python (tests/pkgnames_check.py checks these names per distribution)
PYTHON_BOOTSTRAP = {"apt-get": ["python3", "python3-tk"], "dnf": ["python3", "python3-tkinter"],
                    "pacman": ["python", "tk"], "zypper": ["python3", "python3-tk"], "apk": ["python3", "python3-tkinter"]}


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


def tk_prompt(pkg, utf8=True):
    """The question shown to the user. Georgian only where the output can show it (a terminal without UTF-8 prints '???')."""
    en = f"tkinter (the window toolkit for Python) is missing. Install {pkg} now?"
    return en + (f"\ntkinter ვერ მოიძებნა. დავაყენო {pkg} ახლა?" if utf8 else "")


def _gui_available(which=shutil.which, env=os.environ):
    return bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")) and bool(which("zenity"))


def _zenity(kind, text, run=subprocess.run):
    """Show a window; returns True/False for a question, None when no window could be shown."""
    try:
        r = run(["zenity", f"--{kind}", "--no-markup", "--width=520", "--title=Toolkit", f"--text={text}"],
                capture_output=True, timeout=600)
    except Exception:  # noqa: BLE001
        return None
    return r.returncode == 0


def terminal_command(argv, which=shutil.which):
    """A terminal-emulator command line that runs `argv` and keeps the window open if it fails; None when no terminal exists."""
    keep = 'python3 "$0" "$@"; rc=$?; if [ $rc -ne 0 ]; then echo; echo "Press Enter to close"; read -r _; fi; exit $rc'
    for term, flag in (("xfce4-terminal", "-x"), ("gnome-terminal", "--"), ("mate-terminal", "-x"), ("konsole", "-e"),
                       ("xterm", "-e"), ("x-terminal-emulator", "-e")):
        if which(term):
            return [term, flag, "sh", "-c", keep.replace("python3", sys.executable)] + list(argv)
    return None


def lock_hint(output):
    """When the package manager is blocked by another installer (a Linux Mint installation, Update Manager ...)."""
    low = (output or "").lower()
    if "could not get lock" in low or "unable to acquire the dpkg frontend lock" in low or "dpkg/lock" in low:
        return ("Another installer or update is running right now (for example the Linux Mint installer or Update Manager). "
                "Wait until it finishes, then start this again.")
    return ""


def ensure_tkinter():
    """If tkinter is missing, ask (in a window when started from a menu / icon), install it with the system package
    manager and restart the program. A failure is shown in a window too, not only on the invisible stderr."""
    try:
        import tkinter  # noqa: F401
        return
    except ImportError:
        pass
    gui = _gui_available()
    utf8 = (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "") == "utf8" or gui
    for mgr, cmd, pkg in TK_PACKAGES:
        if shutil.which(mgr):
            break
    else:
        msg = "tkinter is missing and no known package manager was found. Install: python3-tk / python3-tkinter / tk"
        if gui:
            _zenity("error", msg)
        sys.exit(msg)
    if sys.stdin.isatty():
        if input(tk_prompt(pkg, utf8) + " [Y/n] ").strip().lower() not in ("", "y", "yes"):
            sys.exit("Cancelled.")
    elif gui:
        if _zenity("question", tk_prompt(pkg, True)) is False:
            sys.exit("Cancelled.")
    elif (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and not os.environ.get("TOOLKIT_IN_TERMINAL"):
        # no dialog tool and no terminal: open a terminal window and ask there, so the question is always visible
        term = terminal_command([os.path.abspath(sys.argv[0])] + sys.argv[1:])
        if term:
            env = dict(os.environ, TOOLKIT_IN_TERMINAL="1")
            subprocess.Popen(term, env=env, start_new_session=True)
            sys.exit(0)
    # administrator: nothing to add when already root, a graphical password prompt from a menu / icon, sudo in a terminal
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        elevate = []
    elif shutil.which("pkexec") and os.environ.get("DISPLAY"):
        elevate = ["pkexec"]
    elif shutil.which("sudo"):
        elevate = ["sudo"]
    else:
        sys.exit("No way to get administrator rights. Run as root:  " + " ".join(cmd + [pkg]))
    out = ""
    ok = True
    steps = ([elevate + ["apt-get", "update"]] if mgr == "apt-get" else []) + [elevate + cmd + [pkg]]
    for step in steps:
        r = subprocess.run(step, capture_output=not sys.stdin.isatty(), text=True)
        out += (r.stdout or "") + (r.stderr or "")
        ok = r.returncode == 0
    if not ok:
        msg = f"Could not install {pkg}." + ("\n" + lock_hint(out) if lock_hint(out) else "")
        if gui:
            _zenity("error", msg + "\n\n" + out[-600:])
        sys.exit(msg)
    if os.environ.get("TOOLKIT_IN_TERMINAL"):          # started by the helper terminal: open the program, let the terminal close
        subprocess.Popen([sys.executable] + sys.argv, start_new_session=True,
                         env={k: v for k, v in os.environ.items() if k != "TOOLKIT_IN_TERMINAL"})
        sys.exit(0)
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
PKG_FOR["xfburn"] = _ALL("xfburn")
PKG_FOR["k3b"] = _ALL("k3b")
