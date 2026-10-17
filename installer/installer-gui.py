#!/usr/bin/env python3
"""Toolkit Installer — a window around ./install.sh: tick programs, choose where, click Install. English / ქართული.

It only builds and runs the same command you could type (`./install.sh --prefix … TOOL…`) and shows it first,
so nothing is hidden.  For yourself (~/.local) no password is needed; for everyone (/usr/local) the window asks for the
administrator password through pkexec.
"""
import os
import shutil
import subprocess
import sys
import threading
import time

_here = os.path.dirname(os.path.abspath(__file__))
for _p in reversed((os.path.join(_here, "..", "common"), os.path.join(_here, "..", "lib", "linux-scripts"),
                    "/usr/local/lib/linux-scripts", "/usr/lib/linux-scripts")):   # first entry wins
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
from lscommon import detect_pm, ensure_tkinter, load_lang, save_lang  # noqa: E402
if _here not in sys.path:
    sys.path.insert(0, _here)
import extras  # noqa: E402  (programs installed from their publishers, see extras.py)
import updater  # noqa: E402  (updates from GitHub, see updater.py)

ensure_tkinter()

import tkinter as tk  # noqa: E402
from tkinter import ttk, messagebox, scrolledtext  # noqa: E402

LANG = load_lang()
ROOT = os.path.dirname(_here)                         # the linux-scripts checkout this file lives in

# id (as install.sh knows it), the commands it installs (first one decides "installed"), texts, extra weight
TOOLS = [
    {"id": "usb-eject", "cmds": ["usb-eject-gui", "usb-eject"],
     "name": {"en": "USB Safe Eject", "ka": "USB უსაფრთხო გამორთვა"},
     "info": {"en": "unmount and power off USB drives", "ka": "USB დისკის უსაფრთხო გამორთვა"}},
    {"id": "wifi-hotspot", "cmds": ["hotspot-gui", "hotspot"],
     "name": {"en": "Wi-Fi Hotspot", "ka": "Wi-Fi Hotspot"},
     "info": {"en": "hotspot, QR code, connected devices", "ka": "Hotspot, QR კოდი, მოწყობილობების სია"}},
    {"id": "printer-setup", "cmds": ["printer-setup"],
     "name": {"en": "Printer Setup", "ka": "პრინტერის დაყენება"},
     "info": {"en": "find a driver, add a printer", "ka": "დრაივერის პოვნა, პრინტერის დამატება"}},
    {"id": "qgis-installer", "cmds": ["qgis-installer", "qgis-installer-cli"],
     "name": {"en": "QGIS Installer", "ka": "QGIS-ის დაყენება"},
     "info": {"en": "install / update / remove QGIS", "ka": "QGIS-ის დაყენება, განახლება, წაშლა"}},
    {"id": "bluetooth-setup", "cmds": ["bluetooth-setup"],
     "name": {"en": "Bluetooth Setup", "ka": "Bluetooth-ის მართვა"},
     "info": {"en": "adapters, scan, pair", "ka": "ადაპტერები, ძებნა, დაწყვილება"}},
    {"id": "shortcuts", "cmds": ["toolkit-shortcuts"],
     "name": {"en": "Desktop Shortcuts", "ka": "იარლიყები სამუშაო მაგიდაზე"},
     "info": {"en": "put these programs on the Desktop", "ka": "პროგრამების დადება სამუშაო მაგიდაზე"}},
    {"id": "printhub", "cmds": ["printhub"], "heavy": True,
     "name": {"en": "PrintHub", "ka": "PrintHub"},
     "info": {"en": "print PDFs, images, Office files (downloads ~200 MB)", "ka": "PDF, სურათები, Office ფაილები (ჩამოტვირთავს ~200 MB)"}},
]

# installed from the publisher (not by install.sh): shown in their own block, never ticked by default
EXTRAS = [
    {"id": "claude",
     "name": {"en": "Claude Desktop (beta)", "ka": "Claude Desktop (ბეტა)"},
     "info": {"en": "the Claude app: Chat, Cowork, Claude Code; Ubuntu / Debian / Mint; from Anthropic's apt repository",
              "ka": "Claude-ის აპლიკაცია: Chat, Cowork, Claude Code; Ubuntu / Debian / Mint; Anthropic-ის apt რეპოზიტორიიდან"}},
    {"id": "etcher",
     "name": {"en": "balenaEtcher", "ka": "balenaEtcher"},
     "info": {"en": "write an OS image to a USB stick / SD card (downloads ~120 MB from the publisher)",
              "ka": "OS-ის იმიჯის ჩაწერა USB ფლეშკაზე / SD ბარათზე (ჩამოტვირთავს ~120 MB გამომცემლისგან)"}},
    {"id": "brave",
     "name": {"en": "Brave Browser", "ka": "Brave Browser"},
     "info": {"en": "web browser; runs Brave's own install script (you see it first), adds Brave's repository",
              "ka": "ბრაუზერი; უშვებს Brave-ის საკუთარ ინსტალაციის სკრიპტს (წინასწარ ნახავთ), ამატებს Brave-ის რეპოზიტორიას"}},
    {"id": "brasero",
     "name": {"en": "Brasero", "ka": "Brasero"},
     "info": {"en": "burn CDs and DVDs (from your distribution's repositories)",
              "ka": "CD და DVD დისკების ჩაწერა (თქვენი დისტრიბუციის რეპოზიტორიიდან)"}},
    {"id": "xfburn",
     "name": {"en": "Xfburn", "ka": "Xfburn"},
     "info": {"en": "light CD/DVD burner (Xfce); from your distribution's repositories",
              "ka": "მსუბუქი CD/DVD ჩამწერი (Xfce); თქვენი დისტრიბუციის რეპოზიტორიიდან"}},
    {"id": "k3b",
     "name": {"en": "K3b", "ka": "K3b"},
     "info": {"en": "full CD/DVD/Blu-ray burner (KDE, brings many KDE libraries); from your distribution's repositories",
              "ka": "სრული CD/DVD/Blu-ray ჩამწერი (KDE, ბევრ KDE ბიბლიოთეკას მოიტანს); თქვენი დისტრიბუციის რეპოზიტორიიდან"}},
]

USER_PREFIX = os.path.join(os.path.expanduser("~"), ".local")
SYSTEM_PREFIX = "/usr/local"

STR = {
"en": {
 "title": "Toolkit Installer", "lang_btn": "ქართული", "head": "Tick the programs you want, choose where, then click Install",
 "c_name": "Program", "c_what": "What it does", "c_state": "Installed",
 "me": "for me", "all": "for everyone", "both": "both", "none": "—", "yes": "installed",
 "c_tools": "Toolkit programs",
 "f_where": "Where", "w_user": "Only for me (~/.local)", "w_user_note": "no password needed", "w_sys": "For everyone (/usr/local)", "w_sys_note": "asks for the administrator password",
 "f_opts": "Also", "o_desk": "launcher on the Desktop", "o_fold": "launchers in the program folders",
 "o_note_sys": "(only in “Only for me” mode)",
 "install": "Install selected", "uninstall": "Uninstall selected", "sel_all": "Select all", "sel_none": "Select none",
 "cmd": "Command:", "log": "Log", "nothing": "Tick at least one program first.",
 "running": "Working… do not close the window.", "done_ok": "Finished successfully.", "done_fail": "Failed (exit code {rc}). See the log.",
 "confirm_un": "Remove the selected programs ({where})?\n\n{names}", "no_pkexec": "pkexec is not available. Run this in a terminal instead:\n\n{cmd}",
 "venv": "PrintHub needs the Python ‘venv’ package (or pip), and neither is installed.\n\nInstall it first:\n\n  sudo apt install python3-venv\n\nthen click Install again.",
 "heavy": "PrintHub downloads about 200 MB (PySide6). Continue?",
 "c_other": "Other programs (from their publishers)", "looking": "Looking up the latest balenaEtcher…",
 "lookup_fail": "Could not look up balenaEtcher (no internet, or GitHub is unreachable):\n{e}",
 "etcher_ask": "Install balenaEtcher {version}?\n\nDownload: {file} ({mb} MB)\nFrom: {source}\nChecked with SHA-256 before installing:\n{sha}\n\nThen installed with the system package manager (administrator password).",
 "etcher_manual": "balenaEtcher has no official package for this system here.\n\nGet it from the publisher:\n{url}",
 "etcher_un": "balenaEtcher",
 "claude_ask": "Install Claude Desktop (beta)?\n\nFrom Anthropic's apt repository:\n{repo}\n\nThe signing key is downloaded and its fingerprint must equal the one Anthropic publishes:\n{fpr}\nIf it does not, nothing is installed.\n\nThen: apt install claude-desktop (administrator password).\n\n{notes}",
 "claude_manual": "Claude Desktop (beta) is published only for Debian-based Linux (Ubuntu 22.04+, Debian 12+, Linux Mint) on x86-64 / arm64.\n\nSee {url}\nOn other systems the vendor points to the Claude Code command line.",
 "settings": "Settings", "set_close": "Close", "upd_head": "Updates from GitHub",
 "upd_current": "This copy: {short} ({branch}, {date})\nFolder: {folder}", "upd_plain": "This folder is a plain copy (it has no link to GitHub).",
 "upd_check": "Check for updates", "upd_now": "Update now", "upd_checking": "Looking at GitHub…", "upd_none": "Up to date.",
 "upd_behind": "{n} new change(s) on GitHub:", "upd_ahead": "(this copy also has {a} change(s) that GitHub does not)",
 "upd_error": "Could not check: {e}", "upd_auto": "Check for updates when the installer starts (at most every 6 hours)",
 "upd_reinstall": "After updating, reinstall the programs I have installed (for me)",
 "upd_adopt_ask": "This folder is a plain copy. Connect it to GitHub and bring it to the latest version?\n\nFiles that git tracks here are replaced by the latest ones; other files (like start-installer.desktop) stay.",
 "upd_done": "Updated. The installer restarts now.", "upd_failed": "Not updated:\n{e}",
 "upd_nogit": "git is not installed on this computer: updating works without it (Python downloads GitHub's snapshot).",
 "upd_archive": "This copy: GitHub commit {short} (updated without git)\nFolder: {folder}",
 "upd_banner": "{n} new change(s) on GitHub", "upd_banner_plain": "This folder is a plain copy. Connect it to GitHub to get updates.",
 "upd_banner_btn": "Update…", "upd_later": "Later", "upd_working": "Updating…",
 "brave_title": "Brave Browser — review the script before it runs",
 "brave_head": "Brave's official install script ({kb} KB, SHA-256 {sha}) from {url}\nwill run as the ADMINISTRATOR. Source: {src}\nIt adds Brave's package repository (signing key + source file) and installs brave-browser.",
 "brave_install": "Run it (administrator password)", "brave_cancel": "Cancel",
 "brave_fail": "Could not get Brave's install script:\n{e}",
 "pkg_ask": "Install {name} from your distribution's repositories?\n\nPackage: {pkg}  ({pm})\n(administrator password)",
 "pkg_unknown": "No known {name} package for this system's package manager ({pm}).",
 "prereq_ask": "PrintHub needs Python's venv / pip, which this computer does not have yet.\n\nInstall it now, then PrintHub, and start PrintHub?\n(asks for the administrator password; command: {cmd})",
 "prereq_run": "Installing what PrintHub needs…", "launching": "Starting PrintHub…",
 "note": "This window only runs ./install.sh for you — the command is shown above the buttons.",
},
"ka": {
 "title": "ხელსაწყოების დამყენებელი", "lang_btn": "English", "head": "მონიშნეთ პროგრამები, აირჩიეთ სად, და დააჭირეთ „დაყენებას“",
 "c_name": "პროგრამა", "c_what": "რას აკეთებს", "c_state": "დაყენებულია",
 "me": "ჩემთვის", "all": "ყველასთვის", "both": "ორივე", "none": "—", "yes": "დაყენებულია",
 "c_tools": "ხელსაწყოების პროგრამები",
 "f_where": "სად", "w_user": "მხოლოდ ჩემთვის (~/.local)", "w_user_note": "პაროლი არ სჭირდება", "w_sys": "ყველასთვის (/usr/local)", "w_sys_note": "ადმინისტრატორის პაროლს მოითხოვს",
 "f_opts": "ასევე", "o_desk": "იარლიყი სამუშაო მაგიდაზე", "o_fold": "იარლიყები საქაღალდეებში",
 "o_note_sys": "(მხოლოდ „ჩემთვის“ რეჟიმში)",
 "install": "მონიშნულის დაყენება", "uninstall": "მონიშნულის წაშლა", "sel_all": "ყველას მონიშვნა", "sel_none": "მონიშვნის მოხსნა",
 "cmd": "ბრძანება:", "log": "ლოგი", "nothing": "ჯერ მონიშნეთ ერთი პროგრამა მაინც.",
 "running": "მუშაობს… ფანჯარა არ დახუროთ.", "done_ok": "წარმატებით დასრულდა.", "done_fail": "ვერ მოხერხდა (კოდი {rc}). იხილეთ ლოგი.",
 "confirm_un": "წავშალო მონიშნული პროგრამები ({where})?\n\n{names}".replace("\\\n", "\n"),
 "no_pkexec": "pkexec არ არის. გაუშვით ტერმინალში:\n\n{cmd}".replace("\\\n", "\n"),
 "venv": "PrintHub-ს სჭირდება Python-ის ‘venv’ პაკეტი (ან pip), მაგრამ არცერთი არ არის დაყენებული.\n\nჯერ დააყენეთ:\n\n  sudo apt install python3-venv\n\nმერე ისევ დააჭირეთ „დაყენებას“.".replace("\\\n", "\n"),
 "heavy": "PrintHub-ი დაახლოებით 200 MB-ს ჩამოტვირთავს (PySide6). გავაგრძელო?",
 "c_other": "სხვა პროგრამები (გამომცემლისგან)", "looking": "ვეძებ balenaEtcher-ის უახლეს ვერსიას…",
 "lookup_fail": "balenaEtcher-ის მოძებნა ვერ მოხერხდა (ინტერნეტი არ არის ან GitHub მიუწვდომელია):\n{e}",
 "etcher_ask": "დავაყენო balenaEtcher {version}?\n\nჩამოტვირთვა: {file} ({mb} MB)\nსაიდან: {source}\nდაყენებამდე შემოწმდება SHA-256-ით:\n{sha}\n\nმერე დაყენდება სისტემის პაკეტ-მენეჯერით (ადმინისტრატორის პაროლი).",
 "etcher_manual": "balenaEtcher-ს ამ სისტემისთვის ოფიციალური პაკეტი აქ არ აქვს.\n\nაიღეთ გამომცემლის გვერდიდან:\n{url}",
 "etcher_un": "balenaEtcher",
 "claude_ask": "დავაყენო Claude Desktop (ბეტა)?\n\nAnthropic-ის apt რეპოზიტორიიდან:\n{repo}\n\nჩამოიტვირთება ხელმოწერის გასაღები და მისი თითის ანაბეჭდი უნდა ემთხვეოდეს იმას, რასაც Anthropic აქვეყნებს:\n{fpr}\nთუ არ ემთხვევა, არაფერი დაყენდება.\n\nშემდეგ: apt install claude-desktop (ადმინისტრატორის პაროლი).\n\n{notes}",
 "claude_manual": "Claude Desktop (ბეტა) ქვეყნდება მხოლოდ Debian-ზე დაფუძნებული Linux-ისთვის (Ubuntu 22.04+, Debian 12+, Linux Mint), x86-64 / arm64.\n\nიხილეთ {url}\nსხვა სისტემებისთვის მწარმოებელი Claude Code-ის ბრძანების ხაზის ვერსიას გვთავაზობს.",
 "settings": "პარამეტრები", "set_close": "დახურვა", "upd_head": "განახლებები GitHub-იდან",
 "upd_current": "ეს ასლი: {short} ({branch}, {date})\nსაქაღალდე: {folder}", "upd_plain": "ეს საქაღალდე უბრალო ასლია (GitHub-თან კავშირი არ აქვს).",
 "upd_check": "განახლებების შემოწმება", "upd_now": "ახლავე განახლება", "upd_checking": "ვუყურებ GitHub-ს…", "upd_none": "ყველაფერი ახალია.",
 "upd_behind": "GitHub-ზე {n} ახალი ცვლილებაა:", "upd_ahead": "(ამ ასლს {a} ისეთი ცვლილებაც აქვს, რაც GitHub-ზე არ არის)",
 "upd_error": "შემოწმება ვერ მოხერხდა: {e}", "upd_auto": "განახლებების შემოწმება ინსტალერის გახსნისას (არაუმეტეს 6 საათში ერთხელ)",
 "upd_reinstall": "განახლების შემდეგ ხელახლა დავაყენო ჩემთვის დაყენებული პროგრამები",
 "upd_adopt_ask": "ეს საქაღალდე უბრალო ასლია. მივაერთო GitHub-ს და გავაახლო ბოლო ვერსიამდე?\n\nფაილები, რასაც git აკონტროლებს, ჩანაცვლდება უახლესით; სხვა ფაილები (მაგ. start-installer.desktop) დარჩება.",
 "upd_done": "განახლდა. ინსტალერი ახლა თავიდან გაიხსნება.", "upd_failed": "ვერ განახლდა:\n{e}",
 "upd_nogit": "ამ კომპიუტერზე git დაყენებული არ არის: განახლება მის გარეშეც მუშაობს (Python ჩამოტვირთავს GitHub-ის ასლს).",
 "upd_archive": "ეს ასლი: GitHub-ის კომიტი {short} (განახლებულია git-ის გარეშე)\nსაქაღალდე: {folder}",
 "upd_banner": "GitHub-ზე {n} ახალი ცვლილებაა", "upd_banner_plain": "ეს საქაღალდე უბრალო ასლია. მიაერთეთ GitHub-ს, რომ განახლებები მიიღოთ.",
 "upd_banner_btn": "განახლება…", "upd_later": "მოგვიანებით", "upd_working": "ვაახლებ…",
 "brave_title": "Brave Browser — გადახედეთ სკრიპტს გაშვებამდე",
 "brave_head": "Brave-ის ოფიციალური ინსტალაციის სკრიპტი ({kb} KB, SHA-256 {sha}) მისამართიდან {url}\nგაეშვება ადმინისტრატორის უფლებით. წყარო: {src}\nის ამატებს Brave-ის პაკეტების რეპოზიტორიას (ხელმოწერის გასაღები + წყაროს ფაილი) და აყენებს brave-browser-ს.",
 "brave_install": "გაშვება (ადმინისტრატორის პაროლი)", "brave_cancel": "გაუქმება",
 "brave_fail": "Brave-ის სკრიპტის მიღება ვერ მოხერხდა:\n{e}",
 "pkg_ask": "დავაყენო {name} თქვენი დისტრიბუციის რეპოზიტორიიდან?\n\nპაკეტი: {pkg}  ({pm})\n(ადმინისტრატორის პაროლი)",
 "pkg_unknown": "ამ სისტემის პაკეტ-მენეჯერისთვის ({pm}) {name}-ის ცნობილი პაკეტი არ არის.",
 "prereq_ask": "PrintHub-ს სჭირდება Python-ის venv / pip, რაც ამ კომპიუტერზე ჯერ არ არის.\n\nდავაყენო ახლა, მერე PrintHub და გავუშვა PrintHub?\n(ადმინისტრატორის პაროლს მოითხოვს; ბრძანება: {cmd})",
 "prereq_run": "ვაყენებ იმას, რაც PrintHub-ს სჭირდება…", "launching": "ვუშვებ PrintHub-ს…",
 "note": "ეს ფანჯარა მხოლოდ ./install.sh-ს უშვებს თქვენთვის — ბრძანება ღილაკების ზემოთ ჩანს.",
},
}


def t(k, **kw):
    s = STR[LANG][k]
    return s.format(**kw) if kw else s


# ---------------------------------------------------------------- logic (no UI, unit-tested)
def installed_where(tool, home=None, exists=os.path.exists, system_prefix=SYSTEM_PREFIX):
    """-> set of {'user', 'system'} where the tool's first command is installed."""
    home = home or os.path.expanduser("~")
    cmd = tool["cmds"][0]
    res = set()
    if exists(os.path.join(home, ".local", "bin", cmd)):
        res.add("user")
    if exists(os.path.join(system_prefix, "bin", cmd)):
        res.add("system")
    return res


def build_command(root, tool_ids, action, where, desktop=False, folders=False, home=None):
    """The exact command: ['bash', '<root>/install.sh', '--prefix', P, ('--uninstall'), ('--desktop'), ('--folders'), TOOL…].
    Desktop / folder launchers only for the user prefix (as root they would land in root's home)."""
    prefix = SYSTEM_PREFIX if where == "system" else os.path.join(home or os.path.expanduser("~"), ".local")
    cmd = ["bash", os.path.join(root, "install.sh"), "--prefix", prefix]
    if action == "uninstall":
        cmd.append("--uninstall")
    if where != "system":
        if desktop:
            cmd.append("--desktop")
        if folders:
            cmd.append("--folders")
    return cmd + list(tool_ids)


def elevate(cmd, which=shutil.which, euid=None):
    """Wrap for the administrator password: pkexec (graphical). Returns None when it is impossible."""
    euid = os.geteuid() if euid is None and hasattr(os, "geteuid") else (euid if euid is not None else 1)
    if euid == 0:
        return list(cmd)
    return ["pkexec"] + list(cmd) if which("pkexec") else None


def shell_line(cmd):
    import shlex
    return " ".join(shlex.quote(c) for c in cmd)


def shlex_quote(text):
    import shlex
    return shlex.quote(text)


def venv_ready(which=shutil.which, run=subprocess.run):
    """PrintHub's installer needs PySide6 on the system, or `python3 -m venv` (with ensurepip), or pip."""
    def ok(args):
        try:
            return run(args, capture_output=True, timeout=20).returncode == 0
        except Exception:  # noqa: BLE001
            return False
    return ok(["python3", "-c", "import PySide6"]) or ok(["python3", "-c", "import ensurepip, venv"]) \
        or ok(["python3", "-m", "pip", "--version"])


# what PrintHub needs to create its private Python environment, per package manager (all run as administrator)
PREREQ = {
    "apt-get": "apt-get install -y python3-venv || (apt-get update && apt-get install -y python3-venv)",
    "dnf": "dnf install -y python3-pip",
    "pacman": "pacman -S --noconfirm python-pip",
    "zypper": "zypper --non-interactive install python3-pip",
    "apk": "apk add py3-pip",
}


def prereq_command(pm):
    """['sh', '-c', '…'] installing venv/pip for this package manager, or None when we do not know how."""
    sh = PREREQ.get(pm)
    return ["sh", "-c", sh] if sh else None


def run_jobs(jobs, on_line):
    """Run commands one after another; stop at the first failure. -> exit code of the last one run."""
    rc = 0
    for job in jobs:
        rc = run_command(job, on_line)
        if rc != 0:
            return rc
    return rc


def tool_path(tool_id, where, home=None, exists=os.path.exists):
    """The installed launcher command of a tool for this location, or None."""
    tool = next(x for x in TOOLS if x["id"] == tool_id)
    base = os.path.join(home or os.path.expanduser("~"), ".local") if where != "system" else SYSTEM_PREFIX
    path = os.path.join(base, "bin", tool["cmds"][0])
    return path if exists(path) else None


def run_command(cmd, on_line):
    """Run and stream every output line; returns the exit code (127 when it could not start)."""
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=ROOT)
    except OSError:
        return 127
    with p:
        for line in p.stdout:
            on_line(line)
    return p.wait()


def banner_for(res, settings, now):
    """What the quiet start-up check shows on top of the window: ('behind', n) when GitHub has newer work, ('plain', None) for a
    copied folder that is not linked to GitHub (unless snoozed with "Later"), else None."""
    if not res or res.get("mode") == "error":
        return None
    if res["mode"] in ("git", "archive"):
        if res["mode"] == "archive" and res.get("behind") is None:      # commit unknown (first time without git)
            return ("plain", None) if float(settings.get("update_snooze_until", 0) or 0) <= now else None
        return ("behind", res["behind"]) if res.get("behind") else None
    if res["mode"] == "adopt" and float(settings.get("update_snooze_until", 0) or 0) <= now:
        return ("plain", None)
    return None


def reinstall_ids(tools, installed_fn):
    """The programs the user has installed for themselves (~/.local): after an update these get the new version."""
    return [x["id"] for x in tools if "user" in installed_fn(x)]


def fit_geometry(screen_w, screen_h, want_w=1040, want_h=600):
    """-> (width, height, min_width, min_height): the wanted size, shrunk to leave room on a small screen
    (panel, window frame), never below a size where the three columns still read."""
    w, h = min(want_w, screen_w - 30), min(want_h, screen_h - 80)
    return w, h, min(760, w), min(470, h)


def launcher_text(root):
    """A double-click launcher for this window, placed in the checkout's top folder (absolute paths: %k does not work).
    It goes through installer/start.sh, which shows a message window when the installer cannot start; `sh` means no
    executable bit is needed, so it also works from a copied or unzipped folder."""
    return "\n".join([
        "[Desktop Entry]", "Type=Application",
        "Name=Install apps (Toolkit Installer)", "Name[ka]=პროგრამების დაყენება (ხელსაწყოების დამყენებელი)",
        "Comment=Tick programs and install them with one click · მონიშნეთ პროგრამები და დააყენეთ",
        f'Exec=sh "{os.path.join(root, "installer", "start.sh")}"', f"Path={root}",
        "Icon=system-software-install", "Terminal=false", "Categories=System;Utility;", ""])


def make_launcher(root=ROOT):
    """Write <checkout>/start-installer.desktop (executable, trusted) and return its path."""
    path = os.path.join(root, "start-installer.desktop")
    with open(path, "w") as f:
        f.write(launcher_text(root))
    os.chmod(path, 0o755)
    if shutil.which("gio"):
        subprocess.run(["gio", "set", path, "metadata::trusted", "true"], capture_output=True)
    return path


# ---------------------------------------------------------------- GUI
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        w, h, mw, mh = fit_geometry(self.winfo_screenwidth(), self.winfo_screenheight())
        self.geometry(f"{w}x{h}")
        self.minsize(mw, mh)
        self.wrap = max(150, (w - 40) // 3 - 80)          # width of the grey description lines
        self.busy = False
        self.vars = {x["id"]: tk.BooleanVar(value=not x.get("heavy")) for x in TOOLS}
        self.extra_vars = {x["id"]: tk.BooleanVar(value=False) for x in EXTRAS}
        self.where = tk.StringVar(value="user")
        self.v_desk, self.v_fold = tk.BooleanVar(value=True), tk.BooleanVar(value=False)

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=(8, 2))
        self.lbl_head = ttk.Label(top, font=("", 11, "bold"), wraplength=max(300, w - 160), justify="left")
        self.lbl_head.pack(side="left")
        self.btn_lang = ttk.Button(top, width=9, command=self.toggle_lang)
        self.btn_lang.pack(side="right")
        self.btn_set = ttk.Button(top, width=3, text="⚙", command=self.open_settings)
        self.btn_set.pack(side="right", padx=(0, 6))
        self.top = top
        self.banner = ttk.Frame(self)                           # shown only when GitHub has something new (see start_quiet_check)
        self.lbl_banner = ttk.Label(self.banner, foreground="#1a5fb4", font=("", 9, "bold"))
        self.lbl_banner.pack(side="left", padx=(12, 8))
        self.btn_banner = ttk.Button(self.banner, command=self.open_settings)
        self.btn_banner.pack(side="left")
        self.btn_later = ttk.Button(self.banner, command=self.snooze_banner)
        self.btn_later.pack(side="left", padx=6)

        # three columns side by side: toolkit programs | other programs | where, options, buttons
        main = ttk.Frame(self)
        main.pack(fill="x", padx=8)
        main.columnconfigure(0, weight=5, uniform="col")
        main.columnconfigure(1, weight=5, uniform="col")
        main.columnconfigure(2, weight=5, uniform="col")
        self.f_tools = ttk.LabelFrame(main)
        self.f_tools.grid(row=0, column=0, sticky="nsew", padx=3, pady=3)
        self.f_extra = ttk.LabelFrame(main)
        self.f_extra.grid(row=0, column=1, sticky="nsew", padx=3, pady=3)
        side = ttk.Frame(main)
        side.grid(row=0, column=2, sticky="nsew", padx=3, pady=3)
        self.box = self.f_tools                                 # kept for older callers

        self.f_where = ttk.LabelFrame(side)
        self.f_where.pack(fill="x")
        self.rb_user = ttk.Radiobutton(self.f_where, variable=self.where, value="user", command=self.sync)
        self.rb_sys = ttk.Radiobutton(self.f_where, variable=self.where, value="system", command=self.sync)
        self.note_user = ttk.Label(self.f_where, foreground="#777777", font=("", 8), wraplength=250, justify="left")
        self.note_sys = ttk.Label(self.f_where, foreground="#777777", font=("", 8), wraplength=250, justify="left")
        self.rb_user.pack(anchor="w", padx=6, pady=(2, 0))
        self.note_user.pack(anchor="w", padx=26)
        self.rb_sys.pack(anchor="w", padx=6, pady=(4, 0))
        self.note_sys.pack(anchor="w", padx=26, pady=(0, 2))

        self.f_opts = ttk.LabelFrame(side)
        self.f_opts.pack(fill="x", pady=(4, 0))
        self.cb_desk = ttk.Checkbutton(self.f_opts, variable=self.v_desk, command=self.sync)
        self.cb_fold = ttk.Checkbutton(self.f_opts, variable=self.v_fold, command=self.sync)
        self.cb_desk.pack(anchor="w", padx=6, pady=0)
        self.cb_fold.pack(anchor="w", padx=6, pady=0)
        self.lbl_optnote = ttk.Label(self.f_opts, foreground="#777777", wraplength=200, justify="left")
        self.lbl_optnote.pack(anchor="w", padx=6)

        self.b_inst = ttk.Button(side, command=lambda: self.go("install"))
        self.b_un = ttk.Button(side, command=lambda: self.go("uninstall"))
        self.b_all = ttk.Button(side, command=lambda: self.pick(True))
        self.b_none = ttk.Button(side, command=lambda: self.pick(False))
        self.b_inst.pack(fill="x", pady=(6, 1))
        self.b_un.pack(fill="x", pady=1)
        self.b_all.pack(fill="x", pady=1)
        self.b_none.pack(fill="x", pady=1)

        self.lbl_cmd = ttk.Label(self, wraplength=w - 30, justify="left", foreground="#555555", font=("TkFixedFont", 8))
        self.lbl_cmd.pack(anchor="w", padx=12, pady=(2, 0))
        self.lbl_log = ttk.Label(self)                           # (heading kept for older callers; the log has no caption)
        # the status line is packed first, from the bottom, so a small window shortens the log and never cuts the status
        self.lbl_status = ttk.Label(self, foreground="#555555", wraplength=w - 30)
        self.lbl_status.pack(side="bottom", anchor="w", padx=12, pady=(0, 6))
        self.log = scrolledtext.ScrolledText(self, height=3, state="disabled", wrap="word", font=("TkFixedFont", 9))
        self.log.pack(fill="both", expand=True, padx=10, pady=(2, 2))
        self.apply_lang()
        self.after(1500, self.start_quiet_check)

    # ---- UI helpers
    def apply_lang(self):
        self.title(t("title"))
        self.lbl_head.config(text=t("head"))
        self.btn_lang.config(text=t("lang_btn"))
        self.btn_banner.config(text=t("upd_banner_btn"))
        self.btn_later.config(text=t("upd_later"))
        self.f_tools.config(text=t("c_tools"))
        self.f_extra.config(text=t("c_other"))
        self.f_where.config(text=t("f_where"))
        self.rb_user.config(text=t("w_user"))
        self.rb_sys.config(text=t("w_sys"))
        self.note_user.config(text=t("w_user_note"))
        self.note_sys.config(text=t("w_sys_note"))
        self.f_opts.config(text=t("f_opts"))
        self.cb_desk.config(text=t("o_desk"))
        self.cb_fold.config(text=t("o_fold"))
        self.b_inst.config(text=t("install"))
        self.b_un.config(text=t("uninstall"))
        self.b_all.config(text=t("sel_all"))
        self.b_none.config(text=t("sel_none"))
        self.lbl_status.config(text=t("note"))
        self.render()
        self.sync()

    def item_row(self, parent, r, var, title, info, state, good):
        """Two lines per program: [checkbox] name ... state / grey description. Narrow enough for three columns."""
        parent.columnconfigure(0, weight=1)
        ttk.Checkbutton(parent, text=title, variable=var, command=self.sync).grid(row=2 * r, column=0, sticky="w", padx=(4, 0))
        ttk.Label(parent, text=state, foreground="#1a7f37" if good else "#888888", font=("", 8)).grid(
            row=2 * r, column=1, sticky="e", padx=(4, 6))
        ttk.Label(parent, text=info, foreground="#666666", font=("", 8), wraplength=self.wrap, justify="left").grid(
            row=2 * r + 1, column=0, columnspan=2, sticky="w", padx=(24, 4), pady=(0, 2))

    def render(self):
        for frame in (self.f_tools, self.f_extra):
            for w in frame.winfo_children():
                w.destroy()
        for r, tool in enumerate(TOOLS):
            where = installed_where(tool)
            state = t("both") if where == {"user", "system"} else t("me") if where == {"user"} else t("all") if where else t("none")
            self.item_row(self.f_tools, r, self.vars[tool["id"]], tool["name"][LANG], tool["info"][LANG], state, bool(where))
        for r, ex in enumerate(EXTRAS):
            if ex["id"] == "etcher":
                ver = extras.etcher_installed()
            elif ex["id"] == "brave":
                ver = t("yes") if extras.brave_installed() else None
            elif ex["id"] == "claude":
                ver = t("yes") if extras.claude_installed() else None
            else:
                ver = t("yes") if extras.package_installed(ex["id"]) else None
            self.item_row(self.f_extra, r, self.extra_vars[ex["id"]], ex["name"][LANG], ex["info"][LANG], ver or t("none"), bool(ver))

    def sync(self):
        system = self.where.get() == "system"
        for cb in (self.cb_desk, self.cb_fold):
            cb.state(["disabled"] if system else ["!disabled"])
        self.lbl_optnote.config(text=t("o_note_sys") if system else "")
        ids = self.selected_ids()
        shown = shell_line(build_command(ROOT, ids or ["…"], "install", self.where.get(),
                                         self.v_desk.get(), self.v_fold.get())) if ids or not self.selected_extras() else ""
        for ex_id in self.selected_extras():
            note = ("balenaEtcher: curl (HTTPS) → sha256sum -c → apt/dnf install (shown in full before it runs)" if ex_id == "etcher"
                    else "Brave: download Brave's install script (HTTPS), show it, run it as administrator after you agree" if ex_id == "brave"
                    else "Claude Desktop: Anthropic's apt repository, key fingerprint checked, apt install claude-desktop" if ex_id == "claude"
                    else f"{ex_id}: the distribution's package manager (install {extras.package_name(ex_id, detect_pm()) or ex_id})")
            shown = (shown + "\n" if shown else "") + note
        self.lbl_cmd.config(text=shown)

    def toggle_lang(self):
        global LANG
        LANG = "ka" if LANG == "en" else "en"
        save_lang(LANG)
        self.apply_lang()

    def pick(self, value):
        for v in self.vars.values():
            v.set(value)
        for v in self.extra_vars.values():
            v.set(False)                          # the publisher's programs are never ticked by "select all"
        self.sync()

    def selected_ids(self):
        return [x["id"] for x in TOOLS if self.vars[x["id"]].get()]

    def selected_extras(self):
        return [x["id"] for x in EXTRAS if self.extra_vars[x["id"]].get()]

    def say(self, text):
        self.log.config(state="normal")
        self.log.insert("end", str(text).rstrip("\n") + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # ---- run
    def go(self, action):
        if self.busy:
            return
        ids = self.selected_ids()
        extra_ids = self.selected_extras()
        if not ids and not extra_ids:
            return messagebox.showinfo(t("title"), t("nothing"))
        system = self.where.get() == "system"
        names = "\n".join("• " + x["name"][LANG] for x in TOOLS if x["id"] in ids)
        for ex in EXTRAS:
            if ex["id"] in extra_ids:
                names += ("\n" if names else "") + "• " + ex["name"][LANG]
        if action == "uninstall" and not messagebox.askyesno(
                t("title"), t("confirm_un", where=t("w_sys" if system else "w_user").split("\n")[0], names=names)):
            return
        prereq = None
        if action == "install" and "printhub" in ids:
            if not venv_ready():
                pc = prereq_command(detect_pm())
                if pc is None:
                    return messagebox.showwarning(t("title"), t("venv"))
                if not messagebox.askyesno(t("title"), t("prereq_ask", cmd=pc[-1])):
                    return
                prereq = elevate(pc)
                if prereq is None:
                    return messagebox.showwarning(t("title"), t("no_pkexec", cmd="sudo " + shell_line(pc)))
            elif not messagebox.askyesno(t("title"), t("heavy")):
                return
        extra_jobs = []
        for ex_id in extra_ids:
            jobs_for = (self.etcher_jobs(action) if ex_id == "etcher" else
                        self.brave_jobs(action) if ex_id == "brave" else
                        self.claude_jobs(action) if ex_id == "claude" else self.package_jobs(action, ex_id))
            if jobs_for is None:
                return
            extra_jobs += jobs_for
        cmd, shown = None, ""
        if ids:
            cmd = build_command(ROOT, ids, action, self.where.get(), self.v_desk.get(), self.v_fold.get())
            shown = shell_line(cmd)
            if system:
                cmd = elevate(cmd)
                if cmd is None:
                    return messagebox.showwarning(t("title"), t("no_pkexec", cmd="sudo " + shown))
        jobs = ([prereq] if prereq else []) + ([cmd] if cmd else []) + extra_jobs
        self.start_printhub = action == "install" and "printhub" in ids
        self.busy = True
        for b in (self.b_inst, self.b_un):
            b.state(["disabled"])
        self.lbl_status.config(text=t("running"))
        if prereq:
            self.say("$ " + shell_line(prereq))
            self.say(t("prereq_run"))
        if shown:
            self.say("$ " + shown)

        def to_ui(fn, *a):
            try:
                self.after(0, fn, *a)
            except (RuntimeError, tk.TclError):       # the window was closed while the install was still running
                pass

        def work():
            rc = run_jobs(jobs, lambda ln: to_ui(self.say, ln))
            to_ui(self.finish, rc)
        threading.Thread(target=work, daemon=True).start()

    def confirm_script(self, info):
        """Show the downloaded script in full and ask. True = run it. (A window of its own: nothing runs unseen.)"""
        win = tk.Toplevel(self)
        win.title(t("brave_title"))
        win.geometry("760x560")
        win.transient(self)
        ttk.Label(win, wraplength=720, justify="left", font=("", 9, "bold"),
                  text=t("brave_head", kb=max(1, round(info["bytes"] / 1024)), sha=info["sha256"],
                         url=extras.BRAVE_SCRIPT_URL, src=extras.BRAVE_SOURCE)).pack(anchor="w", padx=10, pady=(10, 4))
        box = scrolledtext.ScrolledText(win, wrap="none", font=("TkFixedFont", 9))
        box.pack(fill="both", expand=True, padx=10)
        box.insert("end", info["text"])
        box.config(state="disabled")
        answer = {"ok": False}
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=10, pady=10)

        def go():
            answer["ok"] = True
            win.destroy()
        ttk.Button(bar, text=t("brave_install"), command=go).pack(side="right")
        ttk.Button(bar, text=t("brave_cancel"), command=win.destroy).pack(side="right", padx=8)
        win.grab_set()
        self.wait_window(win)
        return answer["ok"]

    def brave_jobs(self, action):
        """Brave: remove through the package manager, or download the vendor's script, show it, run it as administrator."""
        pm = detect_pm()
        if action == "uninstall":
            steps = extras.brave_remove_steps(pm)
            if not steps:
                messagebox.showinfo(t("title"), t("pkg_unknown", name="Brave", pm=pm or "?"))
                return None
        else:
            self.lbl_status.config(text=t("looking"))
            self.update_idletasks()
            try:
                info = extras.brave_fetch_script()
            except Exception as e:  # noqa: BLE001 - offline, changed URL, an error page: say it, do not run anything
                self.lbl_status.config(text=t("note"))
                messagebox.showwarning(t("title"), t("brave_fail", e=e))
                return None
            self.lbl_status.config(text=t("note"))
            if not self.confirm_script(info):
                return None
            import tempfile
            d = os.path.join(os.path.expanduser("~"), ".cache", "linux-scripts", "downloads")
            os.makedirs(d, exist_ok=True)
            fd, path = tempfile.mkstemp(prefix="brave-install-", suffix=".sh", dir=d)
            with os.fdopen(fd, "w") as f:
                f.write(info["text"])                  # exactly the text that was shown
            os.chmod(path, 0o644)
            steps = extras.brave_steps(path)
        jobs = []
        for st in steps:
            job = ["sh", "-c", st["sh"]]
            if st["root"]:
                job = elevate(job)
                if job is None:
                    messagebox.showwarning(t("title"), t("no_pkexec", cmd="sudo sh -c " + shlex_quote(st["sh"])))
                    return None
            jobs.append(job)
        return jobs

    def claude_jobs(self, action):
        """Claude Desktop: Anthropic's apt repository (Debian-based only), the key fingerprint is checked inside the script."""
        import platform
        pm = detect_pm()
        if action == "uninstall":
            steps = extras.claude_remove_steps(pm)
            if not steps:
                messagebox.showinfo(t("title"), t("claude_manual", url=extras.CLAUDE_PAGE))
                return None
        else:
            steps, info = extras.claude_steps(pm, platform.machine())
            if not steps:
                messagebox.showinfo(t("title"), t("claude_manual", url=info["manual"]))
                return None
            if not messagebox.askyesno(t("title"), t("claude_ask", repo=info["repo"], fpr=info["fingerprint"],
                                                      notes=extras.CLAUDE_NOTES)):
                return None
        jobs = []
        for st in steps:
            job = elevate(["sh", "-c", st["sh"]])
            if job is None:
                messagebox.showwarning(t("title"), t("no_pkexec", cmd="sudo sh -c " + shlex_quote(st["sh"])))
                return None
            jobs.append(job)
        return jobs

    # ---- updates from GitHub (Settings; a quiet check at start)
    def ui(self, fn, *a):
        try:
            self.after(0, fn, *a)
        except (RuntimeError, tk.TclError):          # the window was closed meanwhile
            pass

    def start_quiet_check(self):
        """Once the window is up: look at GitHub in the background (at most every few hours) and show a banner if there is news."""
        if not os.path.isfile(os.path.join(ROOT, "install.sh")):
            return
        settings = updater.load_settings()
        if not updater.should_check(settings):
            return

        def work():
            res = updater.check(ROOT)
            st = updater.load_settings()
            st["last_update_check"] = time.time()
            updater.save_settings(st)
            found = banner_for(res, st, time.time())
            if found:
                self.ui(self.show_banner, found)
        threading.Thread(target=work, daemon=True).start()

    def show_banner(self, found):
        kind, n = found
        self.lbl_banner.config(text=t("upd_banner", n=n) if kind == "behind" else t("upd_banner_plain"))
        self.banner.pack(fill="x", after=self.top, pady=(0, 2))

    def snooze_banner(self):
        st = updater.load_settings()
        st["update_snooze_until"] = time.time() + 7 * 86400
        updater.save_settings(st)
        self.banner.pack_forget()

    def open_settings(self):
        win = tk.Toplevel(self)
        win.title(t("settings"))
        win.geometry("560x520")
        win.transient(self)
        ttk.Label(win, text=t("upd_head"), font=("", 11, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        lbl_cur = ttk.Label(win, justify="left", wraplength=520)
        lbl_cur.pack(anchor="w", padx=12)
        lbl_res = ttk.Label(win, justify="left", wraplength=520, foreground="#1a5fb4")
        lbl_res.pack(anchor="w", padx=12, pady=(6, 2))
        box = scrolledtext.ScrolledText(win, height=9, wrap="word", state="disabled", font=("TkFixedFont", 9))
        box.pack(fill="both", expand=True, padx=12, pady=4)
        settings = updater.load_settings()
        v_auto = tk.BooleanVar(value=settings.get("auto_update_check", True))
        v_re = tk.BooleanVar(value=settings.get("reinstall_after_update", True))

        def persist():
            st = updater.load_settings()
            st["auto_update_check"], st["reinstall_after_update"] = v_auto.get(), v_re.get()
            updater.save_settings(st)
        ttk.Checkbutton(win, text=t("upd_auto"), variable=v_auto, command=persist).pack(anchor="w", padx=12)
        ttk.Checkbutton(win, text=t("upd_reinstall"), variable=v_re, command=persist).pack(anchor="w", padx=12)
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=12, pady=10)
        b_check = ttk.Button(bar, text=t("upd_check"))
        b_now = ttk.Button(bar, text=t("upd_now"), state="disabled")
        b_check.pack(side="left")
        b_now.pack(side="left", padx=8)
        ttk.Button(bar, text=t("set_close"), command=win.destroy).pack(side="right")
        state = {"res": None}

        def show(res):
            state["res"] = res
            info = res.get("local", {})
            lbl_cur.config(text=t("upd_current", short=info.get("short", "?"), branch=info.get("branch", "?"),
                                  date=info.get("date", "?"), folder=ROOT) if info.get("git") else
                           (t("upd_nogit") + "\n" if info.get("git_missing") else "") +
                           (t("upd_archive", short=info["short"], folder=ROOT) if info.get("short") else t("upd_plain") + "\n" + ROOT))
            lines, can = [], False
            if res["mode"] == "error":
                lbl_res.config(text=t("upd_error", e=res["error"]))
            elif res["mode"] == "adopt" or (res["mode"] == "archive" and res["behind"] is None):
                lbl_res.config(text=t("upd_banner_plain"))
                can = True
            elif res["behind"]:
                lbl_res.config(text=t("upd_behind", n=res["behind"]) + (" " + t("upd_ahead", a=res["ahead"]) if res.get("ahead") else ""))
                lines = [f"{sha}  {title}" for sha, title in res["commits"]]
                can = True
            else:
                lbl_res.config(text=t("upd_none"))
            box.config(state="normal")
            box.delete("1.0", "end")
            box.insert("end", "\n".join(lines))
            box.config(state="disabled")
            b_now.config(state="normal" if can else "disabled")
            b_check.config(state="normal")

        def do_check():
            lbl_res.config(text=t("upd_checking"))
            b_check.config(state="disabled")
            b_now.config(state="disabled")

            def work():
                res = updater.check(ROOT)
                st = updater.load_settings()
                st["last_update_check"] = time.time()
                updater.save_settings(st)
                self.ui(show, res)
            threading.Thread(target=work, daemon=True).start()

        def do_now():
            res = state["res"]
            if not res or (res["mode"] in ("adopt", "archive") and res.get("behind") is None and not messagebox.askyesno(t("settings"), t("upd_adopt_ask"), parent=win)):
                return
            lbl_res.config(text=t("upd_working"))
            b_now.config(state="disabled")
            b_check.config(state="disabled")
            win.destroy()
            self.busy = True
            self.lbl_status.config(text=t("upd_working"))
            threading.Thread(target=self.do_update, args=(res, v_re.get()), daemon=True).start()
        b_check.config(command=do_check)
        b_now.config(command=do_now)
        do_check()

    def do_update(self, res, reinstall):
        """Worker thread: update (or adopt), reinstall the installed programs, then restart. Every UI touch goes through ui()."""
        ok, msg = updater.apply(ROOT, res)
        say = lambda text: self.ui(self.say, text)    # noqa: E731
        if not ok:
            self.ui(self.update_failed, msg)
            return
        say(msg)
        if reinstall:
            ids = reinstall_ids(TOOLS, installed_where)
            if ids:
                cmd = build_command(ROOT, ids, "install", "user")
                say("$ " + shell_line(cmd))
                run_command(cmd, say)
        self.ui(self.restart)

    def update_failed(self, msg):
        self.busy = False
        self.lbl_status.config(text=t("note"))
        self.say(t("upd_failed", e=msg))
        messagebox.showerror(t("settings"), t("upd_failed", e=msg))

    def restart(self):
        messagebox.showinfo(t("settings"), t("upd_done"))
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def package_jobs(self, action, app_id):
        """Commands for a program that comes from the distribution's repositories, or None (cancelled / impossible)."""
        pm = detect_pm()
        name = next(x["name"][LANG] for x in EXTRAS if x["id"] == app_id)
        steps = extras.package_steps(app_id, pm, remove=(action == "uninstall"))
        if not steps:
            messagebox.showinfo(t("title"), t("pkg_unknown", name=name, pm=pm or "?"))
            return None
        if action == "install" and not messagebox.askyesno(
                t("title"), t("pkg_ask", name=name, pkg=extras.package_name(app_id, pm), pm=pm)):
            return None
        jobs = []
        for st in steps:
            job = elevate(["sh", "-c", st["sh"]])
            if job is None:
                messagebox.showwarning(t("title"), t("no_pkexec", cmd="sudo sh -c " + shlex_quote(st["sh"])))
                return None
            jobs.append(job)
        return jobs

    def etcher_jobs(self, action):
        """Commands for balenaEtcher, or None when the user cancelled / it cannot be done (a message was shown)."""
        import platform
        pm = detect_pm()
        if action == "uninstall":
            steps = extras.etcher_remove_steps(pm)
            if not steps:
                messagebox.showinfo(t("title"), t("etcher_manual", url=extras.ETCHER_PAGE))
                return None
        else:
            self.lbl_status.config(text=t("looking"))
            self.update_idletasks()
            try:
                release = extras.etcher_release()
            except Exception as e:  # noqa: BLE001 - offline, rate limit, changed API: say it, do not crash
                self.lbl_status.config(text=t("note"))
                messagebox.showwarning(t("title"), t("lookup_fail", e=e))
                return None
            self.lbl_status.config(text=t("note"))
            steps, info = extras.etcher_steps(release, pm, platform.machine())
            if not steps:
                messagebox.showinfo(t("title"), t("etcher_manual", url=info["manual"]))
                return None
            if not messagebox.askyesno(t("title"), t("etcher_ask", version=info["version"], file=info["file"], mb=info["mb"],
                                                      source=info["source"], sha=info["sha256"])):
                return None
        jobs = []
        for st in steps:
            job = ["sh", "-c", st["sh"]]
            if st["root"]:
                job = elevate(job)
                if job is None:
                    messagebox.showwarning(t("title"), t("no_pkexec", cmd="sudo sh -c " + shlex_quote(st["sh"])))
                    return None
            jobs.append(job)
        return jobs

    def finish(self, rc):
        self.busy = False
        for b in (self.b_inst, self.b_un):
            b.state(["!disabled"])
        self.say(t("done_ok") if rc == 0 else t("done_fail", rc=rc))
        self.lbl_status.config(text=t("done_ok") if rc == 0 else t("done_fail", rc=rc))
        self.render()
        if rc == 0 and getattr(self, "start_printhub", False):       # "install it and it runs"
            path = tool_path("printhub", self.where.get())
            if path:
                self.say(t("launching"))
                subprocess.Popen([path], start_new_session=True)
        self.start_printhub = False


def main(argv):
    if "--make-launcher" in argv:
        print(make_launcher())
        return
    app = App()
    if "--select" in argv:                       # e.g. --select printhub: open with only these programs ticked
        ids = argv[argv.index("--select") + 1:]
        app.pick(False)
        for i in ids:
            if i in app.vars:
                app.vars[i].set(True)
        app.sync()
    app.mainloop()


if __name__ == "__main__":
    main(sys.argv[1:])
