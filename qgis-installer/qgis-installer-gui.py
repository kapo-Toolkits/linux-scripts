#!/usr/bin/env python3
"""QGIS Installer — English / ქართული.

Three methods, your choice:
  A  Official QGIS repository (Debian / Ubuntu / Mint…) — latest, LTR or nightly, with the signing key
     verified against the published fingerprint before it is trusted.
  B  Flatpak (Flathub) — any distribution, installed for your user only.
  C  Your distribution's own package (apt / dnf / pacman / zypper) — older, but the simplest.
Every action is shown as a command preview first; nothing runs until you confirm.
Source of method A: https://qgis.org/resources/installation-guide/#debian--ubuntu
"""
import os
import sys
import threading

_here = os.path.dirname(os.path.abspath(__file__))
for _p in reversed((_here, os.path.join(_here, "..", "common"), os.path.join(_here, "..", "lib", "linux-scripts"),
                    "/usr/local/lib/linux-scripts", "/usr/lib/linux-scripts")):   # first entry wins
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
from lscommon import ensure_tkinter, load_lang, save_lang  # noqa: E402

ensure_tkinter()

import tkinter as tk  # noqa: E402
from tkinter import ttk, messagebox, scrolledtext  # noqa: E402

# ---------------------------------------------------------------- logic lives in the qgis_installer package
# (next to this file, or in <prefix>/lib/linux-scripts after ./install.sh); the names below are
# re-exported so existing tests and scripts that load this file keep working.
from qgis_installer import (CHANNELS, METHODS, channels_for, KEY_FPR, KEY_URL, KEYRING, LATEST, LTR, LTR_ONLY_CHANNELS, SOURCES,  # noqa: E402,F401
                            SUFFIX, SUPPORT, USER_DATA, allowed_channels, build_install, build_remove_steps,
                            default_channel, detect, find_installs, installed_qgis, method_available,
                            needs_elevation_fallback, read_os_release, run_steps, sources_text, write_root_script)
from qgis_installer import i18n as _i18n  # noqa: E402

STR = _i18n.STR
LANG = load_lang()


def t(k, **kw):
    return _i18n.t(k, LANG, **kw)


def label_for(it):
    return _i18n.label_for(it, LANG)


def steps_text(steps):
    return _i18n.steps_text(steps, LANG)


# ---------------------------------------------------------------- GUI
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.geometry("760x720")
        self.minsize(680, 620)
        self.sys = detect()
        self.busy = False
        self.method = tk.StringVar()
        self.channel_key = "ltr"
        self.v_grass, self.v_server, self.v_python = (tk.BooleanVar(value=True), tk.BooleanVar(value=False),
                                                      tk.BooleanVar(value=True))

        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(10, 0))
        self.btn_lang = ttk.Button(top, width=10, command=self.toggle_lang)
        self.btn_lang.pack(side="right")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=12, pady=8)
        tab, rmtab, guide = ttk.Frame(self.nb), ttk.Frame(self.nb), ttk.Frame(self.nb)
        self.nb.add(tab, text="")
        self.nb.add(rmtab, text="")
        self.nb.add(guide, text="")

        self.f_sys = ttk.LabelFrame(tab)
        self.f_sys.pack(fill="x", padx=8, pady=6)
        self.lbl_sys = ttk.Label(self.f_sys, justify="left", wraplength=690)
        self.lbl_sys.pack(anchor="w", padx=8, pady=6)

        self.f_method = ttk.LabelFrame(tab)
        self.f_method.pack(fill="x", padx=8, pady=6)
        self.rb = {}
        for m in METHODS:
            self.rb[m] = ttk.Radiobutton(self.f_method, variable=self.method, value=m, command=self.sync_state)
            self.rb[m].pack(anchor="w", padx=8, pady=2)

        self.f_ver = ttk.LabelFrame(tab)
        self.f_ver.pack(fill="x", padx=8, pady=6)
        self.cmb = ttk.Combobox(self.f_ver, state="readonly")
        self.cmb.pack(fill="x", padx=8, pady=8)
        self.cmb.bind("<<ComboboxSelected>>", self.on_channel)

        self.f_pkg = ttk.LabelFrame(tab)
        self.f_pkg.pack(fill="x", padx=8, pady=6)
        self.cb_grass = ttk.Checkbutton(self.f_pkg, variable=self.v_grass)
        self.cb_python = ttk.Checkbutton(self.f_pkg, variable=self.v_python)
        self.cb_server = ttk.Checkbutton(self.f_pkg, variable=self.v_server)
        for c in (self.cb_grass, self.cb_python, self.cb_server):
            c.pack(anchor="w", padx=8, pady=1)

        bar = ttk.Frame(tab)
        bar.pack(fill="x", padx=8, pady=8)
        self.btn_inst = ttk.Button(bar, command=self.on_install)
        self.btn_inst.pack(side="left")
        self.btn_rm = ttk.Button(bar, command=lambda: (self.nb.select(1), self.rescan()))
        self.btn_rm.pack(side="left", padx=8)
        self.btn_copy = ttk.Button(bar, command=self.on_copy)
        self.btn_copy.pack(side="left")

        self.lbl_log = ttk.Label(tab)
        self.lbl_log.pack(anchor="w", padx=10)
        self.log = scrolledtext.ScrolledText(tab, height=7, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # ---- uninstall tab
        self.rm_items, self.rm_vars = [], []
        top_rm = ttk.Frame(rmtab)
        top_rm.pack(fill="x", padx=8, pady=8)
        self.btn_scan = ttk.Button(top_rm, command=self.rescan)
        self.btn_scan.pack(side="left")
        self.lbl_found = ttk.Label(rmtab, font=("", 10, "bold"))
        self.lbl_found.pack(anchor="w", padx=10)
        self.rm_box = ttk.Frame(rmtab)
        self.rm_box.pack(fill="x", padx=14, pady=4)
        self.lbl_warn = ttk.Label(rmtab, wraplength=690, foreground="#b42318", justify="left")
        self.lbl_warn.pack(anchor="w", padx=10, pady=(4, 0))
        self.f_opts = ttk.LabelFrame(rmtab)
        self.f_opts.pack(fill="x", padx=8, pady=8)
        self.v_purge, self.v_auto, self.v_next = tk.BooleanVar(value=False), tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        self.cb_purge = ttk.Checkbutton(self.f_opts, variable=self.v_purge)
        self.cb_auto = ttk.Checkbutton(self.f_opts, variable=self.v_auto)
        self.cb_next = ttk.Checkbutton(self.f_opts, variable=self.v_next)
        for c in (self.cb_purge, self.cb_auto, self.cb_next):
            c.pack(anchor="w", padx=8, pady=1)
        self.btn_rm_go = ttk.Button(rmtab, command=self.on_remove_selected)
        self.btn_rm_go.pack(anchor="w", padx=8, pady=6)

        self.txt = scrolledtext.ScrolledText(guide, wrap="word")
        self.txt.pack(fill="both", expand=True, padx=8, pady=8)

        self.method.set("A" if self.avail("A") else "B")
        self.apply_lang()
        self.rescan()

    # ---- i18n / state
    def avail(self, m):
        return method_available(m, self.sys)

    def allowed_channels(self):
        return channels_for(self.method.get(), self.sys)

    def channel_label(self, k):
        if self.method.get() == "A":
            return t("ch_" + k, v=LATEST if k == "latest" else LTR)
        return t("ch_" + k + "_dist")

    def fill_channels(self):
        """The version box follows the method: official repository channels, or what the distro/AUR/Nix offers."""
        keys = self.allowed_channels()
        if keys:
            if self.channel_key not in keys:
                self.channel_key = ("ltr" if self.sys["ltr_only"] else "latest") if self.method.get() == "A" else keys[0]
            self.cmb["values"] = [self.channel_label(k) for k in keys]
            self.cmb.current(keys.index(self.channel_key))
        else:
            self.cmb["values"] = []
            self.cmb.set("")

    def apply_lang(self):
        s = self.sys
        self.title(t("title"))
        self.btn_lang.config(text=t("lang_btn"))
        self.nb.tab(0, text=t("tab_inst"))
        self.nb.tab(1, text=t("tab_rm"))
        self.nb.tab(2, text=t("tab_guide"))
        self.btn_scan.config(text=t("rm_scan")); self.btn_rm_go.config(text=t("rm_sel"))
        self.f_opts.config(text=t("rm_opts")); self.cb_purge.config(text=t("rm_purge"))
        self.cb_auto.config(text=t("rm_auto")); self.cb_next.config(text=t("rm_next"))
        self.lbl_warn.config(text=t("rm_data_warn"))
        self.render_rm()
        for f, k in ((self.f_sys, "f_sys"), (self.f_method, "f_method"), (self.f_ver, "f_ver"), (self.f_pkg, "f_pkg")):
            f.config(text=t(k))
        for m in METHODS:
            self.rb[m].config(text=t("m" + m))
        self.cb_grass.config(text=t("p_grass"))
        self.cb_python.config(text=t("p_python"))
        self.cb_server.config(text=t("p_server"))
        self.btn_inst.config(text=t("preview"))
        self.btn_rm.config(text=t("rm_goto"))
        self.btn_copy.config(text=t("copy"))
        self.lbl_log.config(text=t("log"))

        lines = [t("sys_line", name=s["name"], code=s["code"] or "-", arch=s["arch"], pm=s["pm"] or "-")]
        if not s["family"]:
            lines.append(t("st_nodeb"))
        elif not s["supported"]:
            lines.append(t("st_unsup"))
        else:
            lines.append(t("st_ltr") if s["ltr_only"] else t("st_ok"))
        if s["family"] and s["arch"] != "amd64":
            lines.append(t("st_arch"))
        if s.get("atomic"):
            lines.append(t("st_atomic"))
        if s.get("suse_immutable"):
            lines.append(t("st_suse_imm"))
        if s["pm"] == "pacman":
            lines.append(t("st_aur", h=s["aur_helper"]) if s.get("aur_helper") else t("st_noaur"))
        if s.get("nix"):
            lines.append(t("st_nix"))
        v = installed_qgis()
        lines.append(t("st_inst", v=v) if v else t("st_none"))
        self.lbl_sys.config(text="\n".join(lines))

        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("end", t("guide"))
        self.txt.config(state="disabled")
        self.sync_state()

    def toggle_lang(self):
        global LANG
        LANG = "ka" if LANG == "en" else "en"
        save_lang(LANG)
        self.apply_lang()

    def on_channel(self, _e=None):
        keys = self.allowed_channels()
        if keys and 0 <= self.cmb.current() < len(keys):
            self.channel_key = keys[self.cmb.current()]

    def sync_state(self):
        for m in METHODS:
            self.rb[m].state(["!disabled"] if self.avail(m) else ["disabled"])
        if not self.avail(self.method.get()):
            self.method.set("B")
        self.fill_channels()
        self.cmb.state(["!disabled", "readonly"] if self.allowed_channels() else ["disabled"])
        pk = self.method.get() in ("A", "C", "D")          # the package choices apply to these methods
        for c in (self.cb_grass, self.cb_python, self.cb_server):
            c.state(["!disabled"] if pk else ["disabled"])

    # ---- helpers
    def say(self, text):
        self.log.config(state="normal")
        self.log.insert("end", str(text).rstrip("\n") + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def steps(self):
        m = self.method.get()
        pk = {"grass": self.v_grass.get(), "server": self.v_server.get(), "python": self.v_python.get()}
        return build_install(m, self.sys, self.channel_key, pk)

    def on_copy(self):
        txt = steps_text(self.steps())
        self.clipboard_clear()
        self.clipboard_append(txt)
        self.say(t("copied"))

    def on_install(self):
        self.confirm(self.steps(), t("title"))

    def rescan(self):
        self.rm_items = find_installs(self.sys)
        self.rm_vars = [tk.BooleanVar(value=(it["kind"] != "data")) for it in self.rm_items]
        self.render_rm()

    def render_rm(self):
        for w in self.rm_box.winfo_children():
            w.destroy()
        if not self.rm_items:
            self.lbl_found.config(text=t("rm_none"))
            return
        self.lbl_found.config(text=t("rm_found"))
        for it, var in zip(self.rm_items, self.rm_vars):
            ttk.Checkbutton(self.rm_box, text=label_for(it), variable=var).pack(anchor="w", pady=1)

    def on_remove_selected(self):
        chosen = [it for it, v in zip(self.rm_items, self.rm_vars) if v.get()]
        steps = build_remove_steps(chosen, self.v_purge.get(), self.v_auto.get(), self.sys)
        if not steps:
            return messagebox.showinfo(t("rm_title"), t("rm_nothing"))
        self.confirm(steps, t("rm_title"), on_success=self.after_remove)

    def after_remove(self):
        self.rescan()
        self.apply_lang()
        if self.v_next.get():
            self.nb.select(0)

    def confirm(self, steps, title, on_success=None):
        if not steps:
            return messagebox.showinfo(title, t("no_method"))
        win = tk.Toplevel(self)
        win.title(t("confirm_title"))
        win.geometry("720x520")
        ttk.Label(win, text=t("will_run"), font=("", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 4))
        box = scrolledtext.ScrolledText(win, wrap="none")
        box.pack(fill="both", expand=True, padx=10)
        box.insert("end", steps_text(steps))
        box.config(state="disabled")
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=10, pady=10)

        def go():
            win.destroy()
            self.run_steps(steps, on_success)
        ttk.Button(bar, text=t("run"), command=go).pack(side="right")
        ttk.Button(bar, text=t("cancel"), command=win.destroy).pack(side="right", padx=8)

    def run_steps(self, steps, on_success=None):
        if self.busy:
            return
        self.busy = True
        for b in (self.btn_inst, self.btn_rm, self.btn_copy, self.btn_rm_go, self.btn_scan):
            b.state(["disabled"])
        self.say(t("running"))

        def work():
            return run_steps(steps, on_line=lambda line: self.after(0, self.say, line))

        def done(res):
            rc, s = res
            self.busy = False
            for b in (self.btn_inst, self.btn_rm, self.btn_copy, self.btn_rm_go, self.btn_scan):
                b.state(["!disabled"])
            if rc == 0:
                self.say(t("done_ok"))
                self.apply_lang()
                if on_success:
                    on_success()
            elif needs_elevation_fallback(rc, s):
                path = write_root_script(steps)
                msg = t("elev_fail", cmd=f"sudo sh {path}")
                self.say(msg)
                messagebox.showwarning(t("title"), msg)
            else:
                self.say(t("done_fail", rc=rc))
        threading.Thread(target=lambda: self.after(0, done, work()), daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
