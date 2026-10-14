#!/usr/bin/env python3
"""USB Safe Eject — პატარა GUI USB დისკების უსაფრთხო გამოსართავად.

საჭიროა: python3 + tkinter (Debian/Ubuntu: python3-tk, Fedora: python3-tkinter,
Arch: tk) და udisks2 (udisksctl) — თითქმის ყველა დესკტოპ-დისტროზე უკვე არის.
"""
import json
import os
import shutil
import subprocess
import sys
import threading

# პაკეტ-მენეჯერი -> (install ბრძანება, tkinter-ის პაკეტი)
TK_PACKAGES = [
    ("apt-get", ["apt-get", "install", "-y"], "python3-tk"),
    ("dnf", ["dnf", "install", "-y"], "python3-tkinter"),
    ("yum", ["yum", "install", "-y"], "python3-tkinter"),
    ("pacman", ["pacman", "-S", "--noconfirm"], "tk"),
    ("zypper", ["zypper", "--non-interactive", "install"], "python3-tk"),
    ("apk", ["apk", "add"], "py3-tkinter"),
    ("xbps-install", ["xbps-install", "-y"], "python3-tkinter"),
]


def ensure_tkinter():
    """თუ tkinter არ არის, სთხოვს ნებართვას, აყენებს და თავს თავიდან უშვებს."""
    try:
        import tkinter  # noqa: F401
        return
    except ImportError:
        pass
    for mgr, cmd, pkg in TK_PACKAGES:
        if shutil.which(mgr):
            break
    else:
        sys.exit("tkinter ვერ მოიძებნა და პაკეტ-მენეჯერი ვერ ვიცანი. "
                 "დააყენეთ ხელით: python3-tk / python3-tkinter / tk")
    if sys.stdin.isatty():
        if input(f"tkinter არ არის. დავაყენო ({pkg})? [Y/n] ").strip().lower() not in ("", "y", "yes"):
            sys.exit("გაუქმდა.")
    # გრაფიკული პაროლის ფანჯარა თუ შეიძლება (მენიუდან გაშვებისას), სხვაგან sudo
    elevate = ["pkexec"] if shutil.which("pkexec") and os.environ.get("DISPLAY") else ["sudo"]
    if mgr == "apt-get":
        subprocess.run(elevate + ["apt-get", "update"])
    if subprocess.run(elevate + cmd + [pkg]).returncode != 0:
        sys.exit(f"{pkg}-ის დაყენება ვერ მოხერხდა.")
    os.execv(sys.executable, [sys.executable] + sys.argv)


if __name__ == "__main__":
    ensure_tkinter()

import tkinter as tk  # noqa: E402
from tkinter import ttk, messagebox  # noqa: E402


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def mountpoints(node):
    mps = node.get("mountpoints") or [node.get("mountpoint")]
    return [m for m in mps if m]


def walk(node):
    yield node
    for ch in node.get("children") or []:
        yield from walk(ch)


LANG = "en"  # ნაგულისხმევი ენა / default language

STR = {
    "en": {
        "title": "USB Safe Eject",
        "heading": "USB drives",
        "col_disk": "Drive", "col_size": "Size", "col_mount": "Mount point",
        "eject": "⏏  Safely eject", "refresh": "Refresh", "lang_btn": "ქართული",
        "none": "No USB drive found", "working": "Working…",
        "default_name": "USB drive",
        "err_title": "Error", "list_fail": "Could not read drives:\n{e}",
        "unmount_fail": "Could not unmount {p}:\n{m}\n\nA file or folder on it may still be open.",
        "poweroff_fail": "Power-off failed:\n{m}",
        "ok": "The drive was safely ejected. You can unplug it now.",
    },
    "ka": {
        "title": "USB უსაფრთხო გამორთვა",
        "heading": "USB დისკები",
        "col_disk": "დისკი", "col_size": "ზომა", "col_mount": "მიმაუნთების წერტილი",
        "eject": "⏏  უსაფრთხო გამორთვა", "refresh": "განახლება", "lang_btn": "English",
        "none": "USB დისკი ვერ მოიძებნა", "working": "მიმდინარეობს…",
        "default_name": "USB დისკი",
        "err_title": "შეცდომა", "list_fail": "დისკების წაკითხვა ვერ მოხერხდა:\n{e}",
        "unmount_fail": "{p} ვერ გამოიმაუნთა:\n{m}\n\nშესაძლოა ფაილი ან საქაღალდე ღიაა.",
        "poweroff_fail": "გამორთვა ვერ მოხერხდა:\n{m}",
        "ok": "დისკი უსაფრთხოდ გამოირთო. კაბელის გამოძვრა შეიძლება.",
    },
}


def t(key, **kw):
    return STR[LANG][key].format(**kw)


def list_usb_disks():
    """Removable/USB disks: [{path, label, size, parts:[(path, mounts)]}]"""
    cols = "NAME,SIZE,MODEL,TRAN,HOTPLUG,TYPE,LABEL,MOUNTPOINTS"
    rc, out = run(["lsblk", "-J", "-o", cols])
    if rc != 0:  # old lsblk has no MOUNTPOINTS
        rc, out = run(["lsblk", "-J", "-o", cols.replace("MOUNTPOINTS", "MOUNTPOINT")])
    if rc != 0:
        raise RuntimeError(out)
    disks = []
    for d in json.loads(out)["blockdevices"]:
        if d.get("type") != "disk":
            continue
        hotplug = str(d.get("hotplug")).lower() in ("1", "true")
        if d.get("tran") != "usb" and not hotplug:
            continue
        parts = [("/dev/" + n["name"], mountpoints(n)) for n in walk(d)
                 if n is not d or mountpoints(n)]
        label = " ".join((d.get("model") or "").split())  # empty -> translated at display time
        disks.append({"path": "/dev/" + d["name"], "label": label,
                      "size": d.get("size", ""), "parts": parts})
    return disks


def eject(disk):
    """unmount all -> sync -> power-off. Returns (ok, message) in the current language."""
    for part, mps in disk["parts"]:
        if not mps:
            continue
        rc, msg = run(["udisksctl", "unmount", "-b", part])
        if rc != 0:
            rc, msg = run(["pkexec", "umount", part])
        if rc != 0:
            return False, t("unmount_fail", p=part, m=msg)
    run(["sync"])
    rc, msg = run(["udisksctl", "power-off", "-b", disk["path"]])
    if rc != 0:
        return False, t("poweroff_fail", m=msg)
    return True, t("ok")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.geometry("540x330")
        self.minsize(440, 240)
        self.disks = []

        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(12, 4))
        self.heading = ttk.Label(top, font=("", 13, "bold"))
        self.heading.pack(side="left")
        self.btn_lang = ttk.Button(top, command=self.toggle_lang, width=10)
        self.btn_lang.pack(side="right")

        self.tree = ttk.Treeview(self, columns=("size", "mount"), selectmode="browse")
        self.tree.column("#0", width=210)
        self.tree.column("size", width=70, anchor="e")
        self.tree.column("mount", width=220)
        self.tree.pack(fill="both", expand=True, padx=12)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=12, pady=10)
        self.btn_eject = ttk.Button(bar, command=self.on_eject)
        self.btn_eject.pack(side="left")
        self.btn_refresh = ttk.Button(bar, command=self.refresh)
        self.btn_refresh.pack(side="left", padx=8)
        self.status = ttk.Label(bar, text="")
        self.status.pack(side="right")

        self.apply_lang()
        self.refresh()

    def toggle_lang(self):
        global LANG
        LANG = "ka" if LANG == "en" else "en"
        self.apply_lang()
        self.refresh()

    def apply_lang(self):
        self.title(t("title"))
        self.heading.config(text=t("heading"))
        self.btn_lang.config(text=t("lang_btn"))
        self.btn_eject.config(text=t("eject"))
        self.btn_refresh.config(text=t("refresh"))
        self.tree.heading("#0", text=t("col_disk"))
        self.tree.heading("size", text=t("col_size"))
        self.tree.heading("mount", text=t("col_mount"))

    def refresh(self):
        try:
            self.disks = list_usb_disks()
        except Exception as e:
            messagebox.showerror(t("err_title"), t("list_fail", e=e))
            return
        self.tree.delete(*self.tree.get_children())
        for i, d in enumerate(self.disks):
            name = d["label"] or t("default_name")
            self.tree.insert("", "end", iid=str(i), text=f"{name} ({d['path']})",
                             values=(d["size"], ""), open=True)
            for part, mps in d["parts"]:
                self.tree.insert(str(i), "end", text=part, values=("", ", ".join(mps) or "—"))
        self.status.config(text="" if self.disks else t("none"))
        if self.disks:
            self.tree.selection_set("0")

    def on_eject(self):
        sel = self.tree.selection()
        if not sel:
            return
        root = sel[0]
        while self.tree.parent(root):
            root = self.tree.parent(root)
        disk = self.disks[int(root)]
        self.btn_eject.state(["disabled"])
        self.status.config(text=t("working"))

        def work():
            ok, msg = eject(disk)
            self.after(0, lambda: self.done(ok, msg))
        threading.Thread(target=work, daemon=True).start()

    def done(self, ok, msg):
        self.btn_eject.state(["!disabled"])
        (messagebox.showinfo if ok else messagebox.showerror)(t("title"), msg)
        self.refresh()


if __name__ == "__main__":
    App().mainloop()
