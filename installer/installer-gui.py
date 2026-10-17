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

_here = os.path.dirname(os.path.abspath(__file__))
for _p in reversed((os.path.join(_here, "..", "common"), os.path.join(_here, "..", "lib", "linux-scripts"),
                    "/usr/local/lib/linux-scripts", "/usr/lib/linux-scripts")):   # first entry wins
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
from lscommon import detect_pm, ensure_tkinter, load_lang, save_lang  # noqa: E402
if _here not in sys.path:
    sys.path.insert(0, _here)
import extras  # noqa: E402  (programs installed from their publishers, see extras.py)

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
    {"id": "etcher",
     "name": {"en": "balenaEtcher", "ka": "balenaEtcher"},
     "info": {"en": "write an OS image to a USB stick / SD card (downloads ~120 MB from the publisher)",
              "ka": "OS-ის იმიჯის ჩაწერა USB ფლეშკაზე / SD ბარათზე (ჩამოტვირთავს ~120 MB გამომცემლისგან)"}},
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
 "me": "for me", "all": "for everyone", "both": "me + everyone", "none": "—", "yes": "installed",
 "f_where": "Where", "w_user": "Only for me (~/.local) — no password needed", "w_sys": "For everyone (/usr/local) — asks for the administrator password",
 "f_opts": "Also", "o_desk": "put a launcher on the Desktop", "o_fold": "put a double-click launcher inside each program's folder",
 "o_note_sys": "(Desktop and folder launchers are only available for “Only for me”)",
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
 "pkg_ask": "Install {name} from your distribution's repositories?\n\nPackage: {pkg}  ({pm})\n(administrator password)",
 "pkg_unknown": "No known {name} package for this system's package manager ({pm}).",
 "prereq_ask": "PrintHub needs Python's venv / pip, which this computer does not have yet.\n\nInstall it now, then PrintHub, and start PrintHub?\n(asks for the administrator password; command: {cmd})",
 "prereq_run": "Installing what PrintHub needs…", "launching": "Starting PrintHub…",
 "note": "This window only runs ./install.sh for you — the command is shown above the buttons.",
},
"ka": {
 "title": "ხელსაწყოების დამყენებელი", "lang_btn": "English", "head": "მონიშნეთ პროგრამები, აირჩიეთ სად, და დააჭირეთ „დაყენებას“",
 "c_name": "პროგრამა", "c_what": "რას აკეთებს", "c_state": "დაყენებულია",
 "me": "ჩემთვის", "all": "ყველასთვის", "both": "ჩემთვის + ყველასთვის", "none": "—", "yes": "დაყენებულია",
 "f_where": "სად", "w_user": "მხოლოდ ჩემთვის (~/.local) — პაროლი არ სჭირდება", "w_sys": "ყველასთვის (/usr/local) — ადმინისტრატორის პაროლს მოითხოვს",
 "f_opts": "ასევე", "o_desk": "იარლიყი სამუშაო მაგიდაზე", "o_fold": "ორმაგი დაწკაპების იარლიყი თითოეული პროგრამის საქაღალდეში",
 "o_note_sys": "(სამუშაო მაგიდისა და საქაღალდის იარლიყები მხოლოდ „ჩემთვის“ რეჟიმშია)",
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


def launcher_text(root):
    """A double-click launcher for this window, placed in the checkout's top folder (absolute paths: %k does not work)."""
    return "\n".join([
        "[Desktop Entry]", "Type=Application",
        "Name=Install apps (Toolkit Installer)", "Name[ka]=პროგრამების დაყენება (ხელსაწყოების დამყენებელი)",
        "Comment=Tick programs and install them with one click · მონიშნეთ პროგრამები და დააყენეთ",
        f"Exec=python3 {os.path.join(root, 'installer', 'installer-gui.py')}", f"Path={root}",
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
        self.geometry("760x720")
        self.minsize(680, 640)
        self.busy = False
        self.vars = {x["id"]: tk.BooleanVar(value=not x.get("heavy")) for x in TOOLS}
        self.extra_vars = {x["id"]: tk.BooleanVar(value=False) for x in EXTRAS}
        self.where = tk.StringVar(value="user")
        self.v_desk, self.v_fold = tk.BooleanVar(value=True), tk.BooleanVar(value=False)

        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(10, 4))
        self.lbl_head = ttk.Label(top, font=("", 12, "bold"), wraplength=560, justify="left")
        self.lbl_head.pack(side="left")
        self.btn_lang = ttk.Button(top, width=10, command=self.toggle_lang)
        self.btn_lang.pack(side="right")

        self.box = ttk.Frame(self)
        self.box.pack(fill="x", padx=12, pady=6)

        self.f_where = ttk.LabelFrame(self)
        self.f_where.pack(fill="x", padx=12, pady=4)
        self.rb_user = ttk.Radiobutton(self.f_where, variable=self.where, value="user", command=self.sync)
        self.rb_sys = ttk.Radiobutton(self.f_where, variable=self.where, value="system", command=self.sync)
        self.rb_user.pack(anchor="w", padx=8, pady=2)
        self.rb_sys.pack(anchor="w", padx=8, pady=2)

        self.f_opts = ttk.LabelFrame(self)
        self.f_opts.pack(fill="x", padx=12, pady=4)
        self.cb_desk = ttk.Checkbutton(self.f_opts, variable=self.v_desk, command=self.sync)
        self.cb_fold = ttk.Checkbutton(self.f_opts, variable=self.v_fold, command=self.sync)
        self.cb_desk.pack(anchor="w", padx=8, pady=1)
        self.cb_fold.pack(anchor="w", padx=8, pady=1)
        self.lbl_optnote = ttk.Label(self.f_opts, foreground="#777777")
        self.lbl_optnote.pack(anchor="w", padx=8, pady=(0, 4))

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=12, pady=6)
        self.b_inst = ttk.Button(bar, command=lambda: self.go("install"))
        self.b_un = ttk.Button(bar, command=lambda: self.go("uninstall"))
        self.b_all = ttk.Button(bar, command=lambda: self.pick(True))
        self.b_none = ttk.Button(bar, command=lambda: self.pick(False))
        for b in (self.b_inst, self.b_un, self.b_all, self.b_none):
            b.pack(side="left", padx=(0, 6))

        self.lbl_cmdh = ttk.Label(self, font=("", 9, "bold"))
        self.lbl_cmdh.pack(anchor="w", padx=12)
        self.lbl_cmd = ttk.Label(self, wraplength=720, justify="left", foreground="#555555", font=("TkFixedFont", 9))
        self.lbl_cmd.pack(anchor="w", padx=12)
        self.lbl_log = ttk.Label(self)
        self.lbl_log.pack(anchor="w", padx=12, pady=(8, 0))
        self.log = scrolledtext.ScrolledText(self, height=9, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 4))
        self.lbl_status = ttk.Label(self, foreground="#555555")
        self.lbl_status.pack(anchor="w", padx=12, pady=(0, 8))
        self.apply_lang()

    # ---- UI helpers
    def apply_lang(self):
        self.title(t("title"))
        self.lbl_head.config(text=t("head"))
        self.btn_lang.config(text=t("lang_btn"))
        self.f_where.config(text=t("f_where"))
        self.rb_user.config(text=t("w_user"))
        self.rb_sys.config(text=t("w_sys"))
        self.f_opts.config(text=t("f_opts"))
        self.cb_desk.config(text=t("o_desk"))
        self.cb_fold.config(text=t("o_fold"))
        self.b_inst.config(text=t("install"))
        self.b_un.config(text=t("uninstall"))
        self.b_all.config(text=t("sel_all"))
        self.b_none.config(text=t("sel_none"))
        self.lbl_cmdh.config(text=t("cmd"))
        self.lbl_log.config(text=t("log"))
        self.lbl_status.config(text=t("note"))
        self.render()
        self.sync()

    def render(self):
        for w in self.box.winfo_children():
            w.destroy()
        for i, h in enumerate((t("c_name"), t("c_what"), t("c_state"))):
            ttk.Label(self.box, text=h, font=("", 9, "bold")).grid(row=0, column=i + 1, sticky="w", padx=8, pady=(0, 3))
        for r, tool in enumerate(TOOLS, start=1):
            where = installed_where(tool)
            state = t("both") if where == {"user", "system"} else t("me") if where == {"user"} else t("all") if where else t("none")
            ttk.Checkbutton(self.box, variable=self.vars[tool["id"]], command=self.sync).grid(row=r, column=0, sticky="w", pady=1)
            ttk.Label(self.box, text=tool["name"][LANG]).grid(row=r, column=1, sticky="w", padx=8)
            ttk.Label(self.box, text=tool["info"][LANG], foreground="#555555").grid(row=r, column=2, sticky="w", padx=8)
            ttk.Label(self.box, text=state, foreground="#1a7f37" if where else "#888888").grid(row=r, column=3, sticky="w", padx=8)
        r = len(TOOLS) + 1
        ttk.Label(self.box, text=t("c_other"), font=("", 9, "bold")).grid(row=r, column=1, columnspan=3, sticky="w", padx=8, pady=(8, 2))
        for r, ex in enumerate(EXTRAS, start=r + 1):
            ver = extras.etcher_installed() if ex["id"] == "etcher" else (
                t("yes") if extras.package_installed(ex["id"]) else None)
            ttk.Checkbutton(self.box, variable=self.extra_vars[ex["id"]], command=self.sync).grid(row=r, column=0, sticky="w", pady=1)
            ttk.Label(self.box, text=ex["name"][LANG]).grid(row=r, column=1, sticky="w", padx=8)
            ttk.Label(self.box, text=ex["info"][LANG], foreground="#555555").grid(row=r, column=2, sticky="w", padx=8)
            ttk.Label(self.box, text=(ver or t("none")), foreground="#1a7f37" if ver else "#888888").grid(row=r, column=3, sticky="w", padx=8)

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
                t("title"), t("confirm_un", where=t("w_sys" if system else "w_user").split(" — ")[0], names=names)):
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
            jobs_for = self.etcher_jobs(action) if ex_id == "etcher" else self.package_jobs(action, ex_id)
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
