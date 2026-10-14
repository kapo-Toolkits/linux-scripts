#!/usr/bin/env python3
"""QGIS Installer — English / ქართული.

Tell it what you want (stable and long-term / newest / next to the QGIS you have) and it recommends the best way
for your system from the QGIS installation guide: official repository, Flatpak (branch stable or lts), Fedora,
openSUSE, Arch, Mageia, containers... Every way can be picked by hand too.
Every action is shown as a command preview first; nothing runs until you confirm.
Guide: https://qgis.org/resources/installation-guide/#linux
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
from qgis_installer import (CHANNELS, KEY_FPR, KEY_URL, KEYRING, LATEST, LTR, LTR_ONLY_CHANNELS, SOURCES,  # noqa: E402,F401
                            SUFFIX, SUPPORT, USER_DATA, allowed_channels, build_install, build_remove_steps,
                            default_channel, detect, find_installs, installed_qgis, method_available,
                            needs_elevation_fallback, read_os_release, run_steps, sources_text, write_root_script)
from qgis_installer import i18n as _i18n  # noqa: E402
from qgis_installer import recipes  # noqa: E402

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
        self.geometry("820x800")
        self.minsize(780, 760)
        self.sys = detect()
        self.busy = False
        self.channel_key = "ltr"
        self.recipe_id = None
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

        self.goal = tk.StringVar(value="stable")
        self.f_goal = ttk.LabelFrame(tab)
        self.f_goal.pack(fill="x", padx=8, pady=6)
        self.rb = {}
        for g in recipes.GOALS:
            self.rb[g] = ttk.Radiobutton(self.f_goal, variable=self.goal, value=g, command=self.on_goal)
            self.rb[g].pack(anchor="w", padx=8, pady=1)
        self.lbl_rec = ttk.Label(self.f_goal, wraplength=670, justify="left", foreground="#1d4ed8")
        self.lbl_rec.pack(anchor="w", padx=8, pady=(4, 6))

        self.f_recipe = ttk.LabelFrame(tab)
        self.f_recipe.pack(fill="x", padx=8, pady=6)
        self.recipe_ids = []
        self.cmb_recipe = ttk.Combobox(self.f_recipe, state="readonly")
        self.cmb_recipe.pack(fill="x", padx=8, pady=(8, 2))
        self.cmb_recipe.bind("<<ComboboxSelected>>", self.on_recipe)
        self.lbl_vf = ttk.Label(self.f_recipe, wraplength=670, justify="left")
        self.lbl_vf.pack(anchor="w", padx=8, pady=(0, 6))

        self.f_ropts = ttk.LabelFrame(tab)
        self.f_ropts.pack(fill="x", padx=8, pady=6)
        self.lbl_opt, self.cmb = {}, {}
        for name in ("channel", "branch", "scope"):
            self.lbl_opt[name] = ttk.Label(self.f_ropts)
            self.cmb[name] = ttk.Combobox(self.f_ropts, state="readonly")
        self.cmb["channel"].bind("<<ComboboxSelected>>", self.on_channel)
        self.v_geo = tk.BooleanVar(value=False)
        self.cb_grass = ttk.Checkbutton(self.f_ropts, variable=self.v_grass)
        self.cb_python = ttk.Checkbutton(self.f_ropts, variable=self.v_python)
        self.cb_server = ttk.Checkbutton(self.f_ropts, variable=self.v_server)
        self.cb_geo = ttk.Checkbutton(self.f_ropts, variable=self.v_geo)
        self.chan_keys = []
        self.rec_options = {}

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

        self.apply_lang()
        self.on_goal()
        self.rescan()

    # ---- i18n / state
    def recipe_label(self, rid):
        return t("rc_" + rid)

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
        for f, k in ((self.f_sys, "f_sys"), (self.f_goal, "f_goal"), (self.f_recipe, "f_recipe"), (self.f_ropts, "f_ropts")):
            f.config(text=t(k))
        for g in recipes.GOALS:
            self.rb[g].config(text=t("goal_" + g))
        self.lbl_opt["channel"].config(text=t("o_channel"))
        self.lbl_opt["branch"].config(text=t("o_branch"))
        self.lbl_opt["scope"].config(text=t("o_scope"))
        self.cb_grass.config(text=t("p_grass"))
        self.cb_python.config(text=t("p_python"))
        self.cb_server.config(text=t("p_server"))
        self.cb_geo.config(text=t("o_geo"))
        self.btn_inst.config(text=t("preview"))
        self.btn_rm.config(text=t("rm_goto"))
        self.btn_copy.config(text=t("copy"))
        self.lbl_log.config(text=t("log"))

        lines = [t("sys_line", name=s["name"], code=s["code"] or "-", arch=s["arch"], pm=s["pm"] or "-")]
        v = installed_qgis()
        lines.append(t("st_inst", v=v) if v else t("st_none"))
        self.lbl_sys.config(text="\n".join(lines))

        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("end", t("guide"))
        self.txt.config(state="disabled")
        self.show_recommendation()
        self.fill_recipes()

    def toggle_lang(self):
        global LANG
        LANG = "ka" if LANG == "en" else "en"
        save_lang(LANG)
        self.apply_lang()

    # ---- the "what do you want" flow
    def show_recommendation(self):
        rec = recipes.recommend(self.sys, self.goal.get())
        self.rec = rec
        if rec["recipe"] is None:
            self.lbl_rec.config(text=t("why_nothing_fits", url=recipes.GUIDE_URL))
        else:
            self.lbl_rec.config(text=t("recommended", name=self.recipe_label(rec["recipe"])) + " " +
                                t("why_" + rec["why"], url=recipes.GUIDE_URL))

    def on_goal(self):
        self.show_recommendation()
        self.rec_options = dict(self.rec["options"])
        self.fill_recipes(select=self.rec["recipe"])

    def fill_recipes(self, select=None):
        """Combobox of the recipes that fit this system; the recommended one (or the current one) is selected."""
        ids = [a["id"] for a in recipes.available(self.sys) if a["applies"]]
        self.recipe_ids = ids
        self.cmb_recipe["values"] = [self.recipe_label(r) for r in ids]
        want = select or self.recipe_id
        if want not in ids:
            want = ids[0] if ids else None
        self.recipe_id = want
        if want is not None:
            self.cmb_recipe.current(ids.index(want))
        else:
            self.cmb_recipe.set("")
        self.show_options()

    def on_recipe(self, _e=None):
        i = self.cmb_recipe.current()
        if i >= 0:
            self.recipe_id = self.recipe_ids[i]
            self.rec_options = {}
        self.show_options()

    def on_channel(self, _e=None):
        i = self.cmb["channel"].current()
        if 0 <= i < len(self.chan_keys):
            self.channel_key = self.chan_keys[i]

    def allowed_channels(self):
        return allowed_channels(self.sys)

    def channel_label(self, k):
        return t("ch_" + k, v=LATEST if k == "latest" else LTR)

    def channel_choices(self):
        rid = self.recipe_id
        if rid == "apt-official":
            return list(self.allowed_channels()), self.channel_label
        if rid == "aur-helper":
            return list(recipes.AUR_CHANNELS), lambda k: t("aur_" + k)
        return ["latest", "ltr"], lambda k: t("nixch_" + k)          # nix-manual

    def show_options(self):
        """Show only the options of the chosen recipe, preset from the recommendation."""
        for w in list(self.lbl_opt.values()) + list(self.cmb.values()) + [self.cb_grass, self.cb_python, self.cb_server, self.cb_geo]:
            w.pack_forget()
        rid = self.recipe_id
        for b in (self.btn_inst, self.btn_copy):
            b.state(["!disabled"] if rid else ["disabled"])
        if rid is None:
            self.lbl_vf.config(text="")
            return
        r = recipes.RECIPES[rid]
        self.lbl_vf.config(text=t("vf_" + r["verified"]))
        opts = r["options"]

        def combo(name, keys, label):
            self.lbl_opt[name].pack(anchor="w", padx=8, pady=(4, 0))
            self.cmb[name].pack(fill="x", padx=8, pady=(0, 4))
            self.cmb[name]["values"] = [label(k) for k in keys]
            return keys

        if "channel" in opts:
            self.chan_keys, label = self.channel_choices()
            combo("channel", self.chan_keys, label)
            want = self.rec_options.get("channel") or self.channel_key
            if want not in self.chan_keys:
                want = "ltr" if "ltr" in self.chan_keys else self.chan_keys[0]
            self.channel_key = want
            self.cmb["channel"].current(self.chan_keys.index(want))
        if "branch" in opts:
            keys = combo("branch", list(recipes.FLATPAK_BRANCHES), lambda k: t("br_" + k))
            self.cmb["branch"].current(keys.index(self.rec_options.get("branch", "stable")))
        if "scope" in opts:
            combo("scope", ["user", "system"], lambda k: t("sc_" + k))
            self.cmb["scope"].current(0)
        for name, cb in (("grass", self.cb_grass), ("python", self.cb_python), ("server", self.cb_server), ("geo_repo", self.cb_geo)):
            if name in opts:
                cb.pack(anchor="w", padx=8, pady=1)

    def options(self):
        want = recipes.RECIPES[self.recipe_id]["options"]
        o = {}
        if "channel" in want:
            o["channel"] = self.channel_key
        if "branch" in want:
            o["branch"] = recipes.FLATPAK_BRANCHES[self.cmb["branch"].current()]
        if "scope" in want:
            o["scope"] = ("user", "system")[self.cmb["scope"].current()]
        for name, var in (("grass", self.v_grass), ("python", self.v_python), ("server", self.v_server), ("geo_repo", self.v_geo)):
            if name in want:
                o[name] = var.get()
        return o

    # ---- helpers
    def say(self, text):
        self.log.config(state="normal")
        self.log.insert("end", str(text).rstrip("\n") + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def plan(self):
        if not self.recipe_id:
            return None
        return recipes.make_plan(self.recipe_id, self.sys, self.options())

    def plan_text(self, result):
        """Steps, then the manual blocks and the notes: everything the user should read before agreeing."""
        parts = []
        if result["steps"]:
            parts.append(steps_text(result["steps"]))
        for m in result["manual"]:
            parts.append("# " + t("rcm_" + m["title"]) + "\n" + m["text"])
        parts.extend("* " + t("rcw_" + k) for k in result["notes"])
        return "\n\n".join(parts)

    def on_copy(self):
        result = self.plan()
        if result:
            self.clipboard_clear()
            self.clipboard_append(self.plan_text(result))
            self.say(t("copied"))

    def on_install(self):
        result = self.plan()
        if result is None:
            return messagebox.showinfo(t("title"), t("why_nothing_fits", url=recipes.GUIDE_URL))
        self.confirm(result["steps"], t("title"), text=self.plan_text(result))

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

    def confirm(self, steps, title, on_success=None, text=None):
        if not steps and not text:
            return messagebox.showinfo(title, t("no_method"))
        win = tk.Toplevel(self)
        win.title(t("confirm_title"))
        win.geometry("720x520")
        ttk.Label(win, text=t("will_run") if steps else t("rc_manual_only"), font=("", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 4))
        box = scrolledtext.ScrolledText(win, wrap="none")
        box.pack(fill="both", expand=True, padx=10)
        box.insert("end", text or steps_text(steps))
        box.config(state="disabled")
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=10, pady=10)

        def go():
            win.destroy()
            self.run_steps(steps, on_success)
        run = ttk.Button(bar, text=t("run"), command=go)
        run.pack(side="right")
        if not steps:
            run.state(["disabled"])
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
