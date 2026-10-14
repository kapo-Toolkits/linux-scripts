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

_here = os.path.dirname(os.path.abspath(__file__))
for _p in reversed((os.path.join(_here, "..", "common"), os.path.join(_here, "..", "lib", "linux-scripts"),
                    "/usr/local/lib/linux-scripts", "/usr/lib/linux-scripts")):   # first entry wins
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
from lscommon import ensure_tkinter, load_lang, run, save_lang, warn_missing  # noqa: E402

ensure_tkinter()

import tkinter as tk  # noqa: E402
from tkinter import ttk, messagebox  # noqa: E402




def mountpoints(node):
    mps = node.get("mountpoints") or [node.get("mountpoint")]
    return [m for m in mps if m]


def walk(node):
    yield node
    for ch in node.get("children") or []:
        yield from walk(ch)


LANG = load_lang()

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
        "busy_list": "\n\nIn use by:\n{l}\n\nClose these programs and try again.",
        "busy_none": "\n\nNo process visible (other users' processes need administrator rights).",
        "busy_more": "(+{n} more)",
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
        "busy_list": "\n\nიყენებს:\n{l}\n\nდახურეთ ეს პროგრამები და სცადეთ თავიდან.",
        "busy_none": "\n\nპროცესი არ ჩანს (სხვა მომხმარებლის პროცესებისთვის ადმინისტრატორის უფლება სჭირდება).",
        "busy_more": "(+{n} სხვა)",
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


def find_blockers(mps):
    """Processes with their cwd, an open file or their executable inside the given mount points.
    Reads /proc, so no extra tools are needed; without root only your own processes are visible.
    -> [(pid, name, user, what, path)]"""
    import pwd
    pre = [m.rstrip("/") for m in mps if m]

    def inside(p):
        return any(p == m or p.startswith(m + "/") for m in pre)
    out = []
    for pid in (d for d in os.listdir("/proc") if d.isdigit()):
        base = f"/proc/{pid}"
        hit = None
        for what, link in (("cwd", base + "/cwd"), ("exe", base + "/exe")):
            try:
                tgt = os.readlink(link)
            except OSError:
                continue
            if inside(tgt):
                hit = (what, tgt)
                break
        if not hit:
            try:
                for fd in os.listdir(base + "/fd"):
                    try:
                        tgt = os.readlink(f"{base}/fd/{fd}")
                    except OSError:
                        continue
                    if inside(tgt):
                        hit = ("open", tgt)
                        break
            except OSError:
                pass
        if hit:
            try:
                with open(base + "/comm") as fh:
                    name = fh.read().strip()
                user = pwd.getpwuid(os.stat(base).st_uid).pw_name
            except (OSError, KeyError):
                name, user = "?", "?"
            out.append((int(pid), name, user, hit[0], hit[1]))
    return sorted(out)


def describe_blockers(mps, limit=8):
    rows = find_blockers(mps)
    if not rows:
        return t("busy_none")
    lines = [f"  • {n} (PID {p}, {u}) — {w}: {path}" for p, n, u, w, path in rows[:limit]]
    if len(rows) > limit:
        lines.append("  " + t("busy_more", n=len(rows) - limit))
    return t("busy_list", l="\n".join(lines))


def eject(disk):
    """unmount all -> sync -> power-off. Returns (ok, message) in the current language."""
    for part, mps in disk["parts"]:
        if not mps:
            continue
        rc, msg = run(["udisksctl", "unmount", "-b", part])
        if rc != 0:
            rc, msg = run(["pkexec", "umount", part])
        if rc != 0:
            return False, t("unmount_fail", p=part, m=msg) + describe_blockers(mps)
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
        save_lang(LANG)
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



def main():
    app = App()
    app.after(400, lambda: warn_missing(["udisksctl", "lsblk"], LANG, t("title")))
    app.mainloop()


if __name__ == "__main__":
    main()
