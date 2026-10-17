#!/usr/bin/env python3
"""Toolkit Shortcuts — pick toolkit programs and put their launchers on the Desktop. English / ქართული.

Each program gets a clickable launcher (a .desktop file) on the Desktop.  It points to the installed command
(`./install.sh`) when there is one, else straight to the program in this checkout, so it works either way.
Only launchers made for these programs are ever replaced or removed; nothing else on the Desktop is touched.
"""
import os
import shutil
import subprocess
import sys

_here = os.path.dirname(os.path.abspath(__file__))
for _p in reversed((os.path.join(_here, "..", "common"), os.path.join(_here, "..", "lib", "linux-scripts"),
                    "/usr/local/lib/linux-scripts", "/usr/lib/linux-scripts")):   # first entry wins
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
from lscommon import ensure_tkinter, load_lang, save_lang  # noqa: E402

ensure_tkinter()

import tkinter as tk  # noqa: E402
from tkinter import ttk, messagebox  # noqa: E402

LANG = load_lang()

# id, installed command, program inside the checkout, launcher file name, texts, theme icon
TOOLS = [
    {"id": "usb-eject", "cmd": "usb-eject-gui", "script": "usb-eject/usb-eject-gui.py", "file": "usb-eject-gui.desktop",
     "name": {"en": "USB Safe Eject", "ka": "USB უსაფრთხო გამორთვა"},
     "comment": {"en": "Safely unmount and power off a USB drive", "ka": "USB დისკის უსაფრთხო გამორთვა"},
     "icon": "media-eject", "cats": "Utility;System;"},
    {"id": "wifi-hotspot", "cmd": "hotspot-gui", "script": "wifi-hotspot/hotspot-gui.py", "file": "hotspot-gui.desktop",
     "name": {"en": "Wi-Fi Hotspot", "ka": "Wi-Fi Hotspot"},
     "comment": {"en": "Start a Wi-Fi hotspot, QR code, connected devices", "ka": "Wi-Fi Hotspot, QR კოდი, დაკავშირებული მოწყობილობები"},
     "icon": "network-wireless-hotspot", "cats": "Network;Utility;"},
    {"id": "printer-setup", "cmd": "printer-setup", "script": "printer-setup/printer-setup-gui.py", "file": "printer-setup.desktop",
     "name": {"en": "Printer Setup", "ka": "პრინტერის დაყენება"},
     "comment": {"en": "Find a driver and add a printer", "ka": "დრაივერის პოვნა და პრინტერის დამატება"},
     "icon": "printer", "cats": "Settings;HardwareSettings;"},
    {"id": "qgis-installer", "cmd": "qgis-installer", "script": "qgis-installer/qgis-installer-gui.py", "file": "qgis-installer.desktop",
     "name": {"en": "QGIS Installer", "ka": "QGIS-ის დაყენება"},
     "comment": {"en": "Install, update and remove QGIS", "ka": "QGIS-ის დაყენება, განახლება და წაშლა"},
     "icon": "system-software-install", "cats": "System;Utility;"},
    {"id": "bluetooth-setup", "cmd": "bluetooth-setup", "script": "bluetooth-setup/bluetooth-setup-gui.py", "file": "bluetooth-setup.desktop",
     "name": {"en": "Bluetooth Setup", "ka": "Bluetooth-ის მართვა"},
     "comment": {"en": "Check adapters, scan, pair", "ka": "ადაპტერების შემოწმება, ძებნა, დაწყვილება"},
     "icon": "bluetooth", "cats": "Settings;HardwareSettings;"},
    {"id": "balena-etcher", "cmd": "balena-etcher", "script": "", "file": "balena-etcher.desktop",
     "name": {"en": "balenaEtcher", "ka": "balenaEtcher"},
     "comment": {"en": "Write an OS image to a USB stick or SD card", "ka": "OS-ის იმიჯის ჩაწერა USB ფლეშკაზე ან SD ბარათზე"},
     "icon": "balena-etcher", "cats": "Utility;System;"},
    {"id": "claude-desktop", "cmd": "claude-desktop", "script": "", "file": "claude-desktop.desktop",
     "name": {"en": "Claude Desktop", "ka": "Claude Desktop"},
     "comment": {"en": "Claude app: Chat, Cowork, Code", "ka": "Claude-ის აპლიკაცია: Chat, Cowork, Code"},
     "icon": "claude-desktop", "cats": "Utility;Development;"},
    {"id": "brave", "cmd": "brave-browser", "script": "", "file": "brave-browser.desktop",
     "name": {"en": "Brave Browser", "ka": "Brave Browser"},
     "comment": {"en": "Web browser", "ka": "ბრაუზერი"},
     "icon": "brave-browser", "cats": "Network;WebBrowser;"},
    {"id": "brasero", "cmd": "brasero", "script": "", "file": "brasero.desktop",
     "name": {"en": "Brasero", "ka": "Brasero"},
     "comment": {"en": "Burn CDs and DVDs", "ka": "CD და DVD დისკების ჩაწერა"},
     "icon": "brasero", "cats": "AudioVideo;DiscBurning;"},
    {"id": "xfburn", "cmd": "xfburn", "script": "", "file": "xfburn.desktop",
     "name": {"en": "Xfburn", "ka": "Xfburn"},
     "comment": {"en": "Burn CDs and DVDs (light)", "ka": "CD და DVD დისკების ჩაწერა (მსუბუქი)"},
     "icon": "xfburn", "cats": "AudioVideo;DiscBurning;"},
    {"id": "k3b", "cmd": "k3b", "script": "", "file": "k3b.desktop",
     "name": {"en": "K3b", "ka": "K3b"},
     "comment": {"en": "Burn CDs, DVDs and Blu-ray discs", "ka": "CD, DVD და Blu-ray დისკების ჩაწერა"},
     "icon": "k3b", "cats": "AudioVideo;DiscBurning;"},
    {"id": "printhub", "cmd": "printhub", "script": "printhub/printhub-launcher.sh", "file": "printhub.desktop",
     "name": {"en": "PrintHub", "ka": "PrintHub"},
     "comment": {"en": "Print PDFs, images and Office files", "ka": "PDF-ის, სურათებისა და Office ფაილების ბეჭდვა"},
     "icon": "io.printhub.PrintHub", "cats": "Utility;Printing;Office;"},
]

STR = {
"en": {
 "title": "Desktop Shortcuts", "lang_btn": "ქართული", "head": "Choose programs, then put their shortcuts on the Desktop",
 "c_name": "Program", "c_src": "Available as", "c_desk": "On Desktop",
 "installed": "installed", "folder": "from this folder", "missing": "not available", "yes": "yes", "no": "no",
 "add": "Put on Desktop", "remove": "Remove from Desktop", "all": "Select all", "none": "Select none",
 "open": "Open Desktop folder", "desk": "Desktop folder:", "nothing": "Tick at least one program first.",
 "added": "Shortcut on the Desktop: {n}", "removed": "Removed from the Desktop: {n}",
 "skipped": "Not available (install it first with ./install.sh): {n}", "foreign": "Left alone, it is not a launcher of this toolkit: {f}",
 "note": "Launchers use the installed command when there is one, otherwise the program in this folder. If the desktop shows “untrusted launcher”, right-click it and choose Allow Launching.",
},
"ka": {
 "title": "იარლიყები სამუშაო მაგიდაზე", "lang_btn": "English", "head": "აირჩიეთ პროგრამები და დააგდეთ მათი იარლიყები სამუშაო მაგიდაზე",
 "c_name": "პროგრამა", "c_src": "ხელმისაწვდომია", "c_desk": "სამუშაო მაგიდაზე",
 "installed": "დაყენებულია", "folder": "ამ საქაღალდიდან", "missing": "არ არის ხელმისაწვდომი", "yes": "კი", "no": "არა",
 "add": "სამუშაო მაგიდაზე დადება", "remove": "სამუშაო მაგიდიდან მოხსნა", "all": "ყველას მონიშვნა", "none": "მონიშვნის მოხსნა",
 "open": "სამუშაო მაგიდის საქაღალდის გახსნა", "desk": "სამუშაო მაგიდა:", "nothing": "ჯერ მონიშნეთ ერთი პროგრამა მაინც.",
 "added": "იარლიყი სამუშაო მაგიდაზეა: {n}", "removed": "სამუშაო მაგიდიდან მოიხსნა: {n}",
 "skipped": "არ არის ხელმისაწვდომი (ჯერ დააყენეთ ./install.sh-ით): {n}", "foreign": "ხელუხლებელია, ეს ამ ხელსაწყოების იარლიყი არ არის: {f}",
 "note": "იარლიყი დაყენებულ ბრძანებას იყენებს, თუ არა — ამ საქაღალდის პროგრამას. თუ სამუშაო მაგიდა წერს „უნდობელი გამშვები“, მარჯვენა კლიკი → „Allow Launching“.",
},
}


def t(k, **kw):
    s = STR[LANG][k]
    return s.format(**kw) if kw else s


# ---------------------------------------------------------------- logic (no UI, unit-tested)
def find_root(env=None, here=_here, home=None):
    """The linux-scripts checkout: $TOOLKIT_ROOT, the folder around this file, or the path install.sh remembered."""
    env = os.environ if env is None else env
    home = home or os.path.expanduser("~")
    cands = [env.get("TOOLKIT_ROOT", ""), os.path.dirname(here)]
    try:
        with open(os.path.join(env.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"), "linux-scripts", "root")) as f:
            cands.append(f.read().strip())
    except OSError:
        pass
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "install.sh")):
            return os.path.abspath(c)
    return None


def resolve_exec(tool, root, which=shutil.which, exists=os.path.exists, home=None, bin_dirs=None):
    """-> ('installed', '/abs/cmd') | ('folder', 'python3 /abs/script') | (None, None).
    The user's own install (~/.local/bin) wins over a system-wide one (/usr/local/bin)."""
    home = home or os.path.expanduser("~")
    bin_dirs = bin_dirs or (os.path.join(home, ".local", "bin"), "/usr/local/bin", "/usr/bin")
    found = None
    for d in bin_dirs:
        c = os.path.join(d, tool["cmd"])
        if exists(c) and os.access(c, os.X_OK):
            found = c
            break
    found = found or which(tool["cmd"])
    if found:
        return "installed", os.path.abspath(found)
    if root and tool["script"]:
        script = os.path.join(root, tool["script"])
        if exists(script):
            return "folder", ("sh " if script.endswith(".sh") else "python3 ") + script
    return None, None


def desktop_dir(run=subprocess.run, home=None):
    home = home or os.path.expanduser("~")
    try:
        out = run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=5).stdout.strip()
        if out and out != home:
            return out
    except Exception:  # noqa: BLE001
        pass
    return os.path.join(home, "Desktop")


def entry_text(tool, exec_line, workdir=None):
    lines = ["[Desktop Entry]", "Type=Application", f"Name={tool['name']['en']}", f"Name[ka]={tool['name']['ka']}",
             f"Comment={tool['comment']['en']}", f"Comment[ka]={tool['comment']['ka']}", f"Exec={exec_line}",
             f"Icon={tool['icon']}", "Terminal=false", f"Categories={tool['cats']}", f"X-Toolkit-Id={tool['id']}"]
    if workdir:
        lines.append(f"Path={workdir}")
    return "\n".join(lines) + "\n"


def is_ours(path, tool):
    """Only launchers of this toolkit are replaced/removed: our marker, or the command / program of this tool in Exec."""
    try:
        with open(path, errors="replace") as f:
            text = f.read()
    except OSError:
        return False
    if f"X-Toolkit-Id={tool['id']}" in text:
        return True
    execs = [ln[5:].strip() for ln in text.splitlines() if ln.startswith("Exec=")]
    names = (tool["cmd"], os.path.basename(tool["script"]))
    return any(os.path.basename(e.split()[-1] if e.split() else "") in names or
               any(n in e for n in names) for e in execs)


def add_shortcut(tool, root, deskdir, **kw):
    """-> ('added', path) | ('missing', None) | ('foreign', path)"""
    kind, exec_line = resolve_exec(tool, root, **kw)
    if not kind:
        return "missing", None
    path = os.path.join(deskdir, tool["file"])
    if os.path.exists(path) and not is_ours(path, tool):
        return "foreign", path
    os.makedirs(deskdir, exist_ok=True)
    workdir = os.path.dirname(os.path.join(root, tool["script"])) if kind == "folder" else None
    with open(path, "w") as f:
        f.write(entry_text(tool, exec_line, workdir))
    os.chmod(path, 0o755)
    if shutil.which("gio"):
        subprocess.run(["gio", "set", path, "metadata::trusted", "true"], capture_output=True)
    return "added", path


def remove_shortcut(tool, deskdir):
    """-> 'removed' | 'absent' | 'foreign'"""
    path = os.path.join(deskdir, tool["file"])
    if not os.path.exists(path):
        return "absent"
    if not is_ours(path, tool):
        return "foreign"
    os.remove(path)
    return "removed"


# ---------------------------------------------------------------- GUI
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.geometry("640x520")
        self.minsize(560, 460)
        self.root_dir = find_root()
        self.desk = desktop_dir()
        self.vars = {x["id"]: tk.BooleanVar(value=False) for x in TOOLS}

        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(10, 4))
        self.lbl_head = ttk.Label(top, font=("", 12, "bold"), wraplength=480, justify="left")
        self.lbl_head.pack(side="left")
        self.btn_lang = ttk.Button(top, width=10, command=self.toggle_lang)
        self.btn_lang.pack(side="right")

        self.box = ttk.Frame(self)
        self.box.pack(fill="x", padx=12, pady=6)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=12, pady=(2, 6))
        self.b_all = ttk.Button(bar, command=lambda: self.pick(True))
        self.b_none = ttk.Button(bar, command=lambda: self.pick(False))
        self.b_add = ttk.Button(bar, command=self.on_add)
        self.b_rm = ttk.Button(bar, command=self.on_remove)
        for b in (self.b_add, self.b_rm, self.b_all, self.b_none):
            b.pack(side="left", padx=(0, 6))

        row = ttk.Frame(self)
        row.pack(fill="x", padx=12)
        self.lbl_desk = ttk.Label(row)
        self.lbl_desk.pack(side="left")
        self.val_desk = ttk.Label(row, foreground="#555555")
        self.val_desk.pack(side="left", padx=6)
        self.b_open = ttk.Button(row, command=self.on_open)
        self.b_open.pack(side="right")

        self.lbl_msg = ttk.Label(self, wraplength=600, justify="left")
        self.lbl_msg.pack(fill="x", padx=12, pady=(10, 2))
        self.lbl_note = ttk.Label(self, wraplength=600, justify="left", foreground="#777777")
        self.lbl_note.pack(fill="x", padx=12, pady=(2, 10))
        self.msgs = []
        self.apply_lang()

    def apply_lang(self):
        self.title(t("title"))
        self.lbl_head.config(text=t("head"))
        self.btn_lang.config(text=t("lang_btn"))
        self.b_add.config(text=t("add"))
        self.b_rm.config(text=t("remove"))
        self.b_all.config(text=t("all"))
        self.b_none.config(text=t("none"))
        self.b_open.config(text=t("open"))
        self.lbl_desk.config(text=t("desk"))
        self.val_desk.config(text=self.desk)
        self.lbl_note.config(text=t("note"))
        self.render()

    def render(self):
        for w in self.box.winfo_children():
            w.destroy()
        heads = (t("c_name"), t("c_src"), t("c_desk"))
        for i, h in enumerate(heads):
            ttk.Label(self.box, text=h, font=("", 9, "bold")).grid(row=0, column=i + 1, sticky="w", padx=8, pady=(0, 4))
        for r, tool in enumerate(TOOLS, start=1):
            kind, _ = resolve_exec(tool, self.root_dir)
            on = os.path.exists(os.path.join(self.desk, tool["file"]))
            cb = ttk.Checkbutton(self.box, variable=self.vars[tool["id"]])
            cb.grid(row=r, column=0, sticky="w", pady=2)
            ttk.Label(self.box, text=tool["name"][LANG]).grid(row=r, column=1, sticky="w", padx=8)
            ttk.Label(self.box, text=t(kind or "missing"),
                      foreground="#1a7f37" if kind == "installed" else ("#555555" if kind else "#b42318")
                      ).grid(row=r, column=2, sticky="w", padx=8)
            ttk.Label(self.box, text=t("yes") if on else t("no")).grid(row=r, column=3, sticky="w", padx=8)
        self.lbl_msg.config(text="\n".join(self.msgs))

    def toggle_lang(self):
        global LANG
        LANG = "ka" if LANG == "en" else "en"
        save_lang(LANG)
        self.apply_lang()

    def pick(self, value):
        for v in self.vars.values():
            v.set(value)

    def chosen(self):
        sel = [x for x in TOOLS if self.vars[x["id"]].get()]
        if not sel:
            messagebox.showinfo(t("title"), t("nothing"))
        return sel

    def on_add(self):
        sel = self.chosen()
        if not sel:
            return
        self.msgs = []
        for tool in sel:
            res, path = add_shortcut(tool, self.root_dir, self.desk)
            if res == "added":
                self.msgs.append(t("added", n=tool["name"][LANG]))
            elif res == "missing":
                self.msgs.append(t("skipped", n=tool["name"][LANG]))
            else:
                self.msgs.append(t("foreign", f=path))
        self.render()

    def on_remove(self):
        sel = self.chosen()
        if not sel:
            return
        self.msgs = []
        for tool in sel:
            res = remove_shortcut(tool, self.desk)
            if res == "removed":
                self.msgs.append(t("removed", n=tool["name"][LANG]))
            elif res == "foreign":
                self.msgs.append(t("foreign", f=os.path.join(self.desk, tool["file"])))
        self.render()

    def on_open(self):
        if shutil.which("xdg-open") and os.path.isdir(self.desk):
            subprocess.Popen(["xdg-open", self.desk], start_new_session=True)


if __name__ == "__main__":
    App().mainloop()
