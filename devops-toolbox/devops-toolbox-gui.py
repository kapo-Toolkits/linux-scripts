#!/usr/bin/env python3
"""DevOps Toolbox - desktop window (English / ქართული, light / dark).

Pick a category, fill in the inputs, press Preview (the exact command is shown), confirm, execute. Everything it can do is an
allowlisted operation of the `devops_toolbox` package - there is no command line to type into. The window itself never runs
as root: an operation that needs administrator rights goes through pkexec (a system password dialog)."""
import os
import queue
import sys
import threading

_here = os.path.dirname(os.path.abspath(__file__))
for _p in reversed((_here, os.path.join(_here, "..", "common"), os.path.join(_here, "..", "lib", "linux-scripts"),
                    "/usr/local/lib/linux-scripts", "/usr/lib/linux-scripts")):      # first entry wins
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
from lscommon import ensure_tkinter  # noqa: E402

ensure_tkinter()

import tkinter as tk  # noqa: E402
from tkinter import messagebox, ttk  # noqa: E402

from devops_toolbox import i18n, settings, themes  # noqa: E402
from devops_toolbox.api import Toolbox  # noqa: E402

LANG_NAMES = {"en": "English", "ka": "ქართული"}
ACTIONS_FORM = ("allow", "deny", "reject", "delete")          # the form's Action list; 'delete' uses the delete operation
CORE_UFW = ("ufw.status", "ufw.rule.add", "ufw.rule.delete")   # shown by the UFW manager itself; the other firewall operations are listed


def t(lang, key, **kw):
    return i18n.t(lang, key, **kw)


class App(tk.Tk):
    def __init__(self, toolbox=None, lang=None, theme=None):
        super().__init__()
        self.tb = toolbox or Toolbox()
        self.lang = lang or settings.load_lang()
        self.theme = theme or settings.load_theme()
        self.q = queue.Queue()
        self.busy = False
        self.pending = None                      # the last successful preview: (op_id, params, token, risk, commands)
        self.cat_id = None                       # the category shown
        self.g_op, self.g_vars, self.g_pending = None, {}, None   # the generic operation panel
        self.tform = {"kind": "local", "host": "", "port": "22", "user": "", "key": ""}   # the "run on" bar (kept while the window is redrawn)
        self.form = {"port": "", "proto": "tcp", "action": "allow", "comment": ""}
        self.minsize(820, 640)
        self.geometry("1040x800")
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.build()
        self.after(120, self._poll)

    # ---------------------------------------------------------------- helpers
    def tr(self, key, **kw):
        return t(self.lang, key, **kw)

    def colors(self):
        return themes.PALETTES[self.theme]

    def apply_theme(self):
        c = self.colors()
        self.configure(bg=c["bg"])
        s = self.style
        s.configure(".", background=c["bg"], foreground=c["text"], fieldbackground=c["field"], bordercolor=c["border"],
                    lightcolor=c["bg"], darkcolor=c["bg"], troughcolor=c["bg"], font=("", 10))
        s.configure("TFrame", background=c["bg"])
        s.configure("Panel.TFrame", background=c["panel"])
        s.configure("Side.TFrame", background=c["side"])
        s.configure("TLabel", background=c["bg"], foreground=c["text"])
        s.configure("Panel.TLabel", background=c["panel"], foreground=c["text"])
        s.configure("Muted.TLabel", background=c["panel"], foreground=c["muted"])
        s.configure("Side.TLabel", background=c["side"], foreground=c["text"])
        s.configure("Title.TLabel", background=c["bg"], foreground=c["text"], font=("", 14, "bold"))
        s.configure("Small.TLabel", background=c["panel"], foreground=c["muted"], font=("", 9))
        s.configure("Head.TLabel", background=c["panel"], foreground=c["text"], font=("", 11, "bold"))
        s.configure("TButton", background=c["panel"], foreground=c["text"], bordercolor=c["border"], padding=(10, 4))
        s.map("TButton", background=[("active", c["select"]), ("disabled", c["bg"])], foreground=[("disabled", c["muted"])])
        s.configure("Accent.TButton", background=c["accent"], foreground=c["accent_text"], padding=(12, 5), font=("", 10, "bold"))
        s.map("Accent.TButton", background=[("active", c["accent"]), ("disabled", c["border"])],
              foreground=[("disabled", c["muted"])])
        s.configure("TEntry", fieldbackground=c["field"], foreground=c["text"], insertcolor=c["text"])
        s.configure("TCombobox", fieldbackground=c["field"], foreground=c["text"], background=c["panel"], arrowcolor=c["text"])
        s.map("TCombobox", fieldbackground=[("readonly", c["field"])], foreground=[("readonly", c["text"])])
        s.configure("Treeview", background=c["field"], fieldbackground=c["field"], foreground=c["text"], rowheight=24)
        s.map("Treeview", background=[("selected", c["select"])], foreground=[("selected", c["text"])])
        s.configure("Treeview.Heading", background=c["side"], foreground=c["text"], bordercolor=c["border"])
        s.configure("TNotebook", background=c["bg"], bordercolor=c["border"])
        s.configure("TNotebook.Tab", background=c["side"], foreground=c["text"], padding=(12, 4))
        s.map("TNotebook.Tab", background=[("selected", c["panel"])])
        s.configure("TCheckbutton", background=c["panel"], foreground=c["text"])
        self.option_add("*TCombobox*Listbox.background", c["field"])
        self.option_add("*TCombobox*Listbox.foreground", c["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", c["select"])

    def text_widget(self, parent, height):
        c = self.colors()
        w = tk.Text(parent, height=height, wrap="word", bg=c["field"], fg=c["text"], insertbackground=c["text"], relief="flat",
                    highlightthickness=1, highlightbackground=c["border"], padx=8, pady=6, font=("TkFixedFont", 10))
        w.tag_configure("ok", foreground=c["ok"])
        w.tag_configure("warn", foreground=c["warn"])
        w.tag_configure("bad", foreground=c["bad"])
        w.tag_configure("head", font=("", 10, "bold"))
        w.tag_configure("cmd", font=("TkFixedFont", 11, "bold"))
        return w

    def set_text(self, widget, parts):
        """parts: [(text, tag or None)]"""
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        for text, tag in parts:
            widget.insert("end", text, tag) if tag else widget.insert("end", text)
        widget.configure(state="disabled")

    # ---------------------------------------------------------------- layout
    def build(self):
        for w in self.winfo_children():
            w.destroy()
        self.apply_theme()
        self.title(self.tr("app_title"))
        # top bar
        top = ttk.Frame(self, padding=(12, 8))
        top.pack(fill="x")
        ttk.Label(top, text=self.tr("app_title"), style="Title.TLabel").pack(side="left")
        ttk.Label(top, text="  " + self.tr("app_subtitle")).pack(side="left")
        self.btn_theme = ttk.Button(top, text=self.tr("theme_dark") if self.theme == "light" else self.tr("theme_light"),
                                    command=self.toggle_theme)
        self.btn_theme.pack(side="right")
        self.lang_var = tk.StringVar(value=LANG_NAMES[self.lang])
        box = ttk.Combobox(top, textvariable=self.lang_var, values=[LANG_NAMES[x] for x in i18n.LANGS], state="readonly", width=10)
        box.pack(side="right", padx=8)
        box.bind("<<ComboboxSelected>>", self.on_language)
        self.lang_box = box
        ttk.Label(top, text=self.tr("language") + ":").pack(side="right")
        self.build_target_bar()
        # body: sidebar | main
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        side = ttk.Frame(body, style="Side.TFrame", padding=8, width=210)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        ttk.Label(side, text=self.tr("categories"), style="Side.TLabel", font=("", 10, "bold")).pack(anchor="w", pady=(0, 6))
        self.cat_list = tk.Listbox(side, activestyle="none", exportselection=False, relief="flat", highlightthickness=0,
                                   bg=self.colors()["side"], fg=self.colors()["text"], selectbackground=self.colors()["select"],
                                   selectforeground=self.colors()["text"], font=("", 11))
        self.cat_list.pack(fill="both", expand=True)
        self.cats = self.tb.catalog(self.lang)["categories"]
        for c in self.cats:
            self.cat_list.insert("end", c["name"])
        if self.cat_id not in [c["id"] for c in self.cats]:
            self.cat_id = self.cats[0]["id"]
        self.cat_list.selection_set([c["id"] for c in self.cats].index(self.cat_id))
        self.cat_list.bind("<<ListboxSelect>>", self.on_category)
        main = ttk.Frame(body, padding=(10, 0, 10, 10))
        main.pack(side="left", fill="both", expand=True)
        # bottom: result / history (packed first so a small window never cuts it off)
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(side="bottom", fill="x", pady=(8, 0))
        res = ttk.Frame(self.notebook, padding=4)
        self.notebook.add(res, text=self.tr("res_title"))
        self.result = self.text_widget(res, 4)
        self.result.pack(fill="both", expand=True)
        self.set_text(self.result, [(self.tr("status_ready"), "head")])
        hist = ttk.Frame(self.notebook, padding=4)
        self.notebook.add(hist, text=self.tr("hist_title"))
        cols = ("time", "op", "status", "exit", "summary")
        self.hist_tree = ttk.Treeview(hist, columns=cols, show="headings", height=4)
        for col, key, w in (("time", "hist_time", 140), ("op", "hist_operation", 150), ("status", "hist_status", 70),
                            ("exit", "hist_exit", 50), ("summary", "hist_summary", 380)):
            self.hist_tree.heading(col, text=self.tr(key))
            self.hist_tree.column(col, width=w, anchor="w")
        self.hist_tree.pack(side="left", fill="both", expand=True)
        ttk.Button(hist, text=self.tr("btn_clear_history"), command=self.clear_history).pack(side="right", anchor="n", padx=6)
        self.refresh_history()
        self.panel = ttk.Frame(main)
        self.panel.pack(fill="both", expand=True)
        self.status = ttk.Label(self, text=self.tr("status_ready"), padding=(12, 4))
        self.status.pack(side="bottom", fill="x")
        self.build_panel()

    # ---------------------------------------------------------------- where operations run: this computer or another one over SSH
    def build_target_bar(self):
        bar = ttk.Frame(self, style="Side.TFrame", padding=(12, 6))
        bar.pack(fill="x")
        f = self.tform
        self.t_kind = tk.StringVar(value=f["kind"])
        self.t_host, self.t_port = tk.StringVar(value=f["host"]), tk.StringVar(value=f["port"])
        self.t_user, self.t_key = tk.StringVar(value=f["user"]), tk.StringVar(value=f["key"] or self.tr("tg_key_default"))
        ttk.Label(bar, text=self.tr("tg_title") + ":", style="Side.TLabel", font=("", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(bar, text=self.tr("tg_local"), value="local", variable=self.t_kind, command=self.on_kind).grid(row=0, column=1, padx=(8, 4))
        ttk.Radiobutton(bar, text=self.tr("tg_remote"), value="remote", variable=self.t_kind, command=self.on_kind).grid(row=0, column=2, padx=4)
        self.t_widgets = []
        col = 3
        for label, var, width in (("tg_host", self.t_host, 18), ("tg_port", self.t_port, 6), ("tg_user", self.t_user, 12)):
            ttk.Label(bar, text=self.tr(label), style="Side.TLabel").grid(row=0, column=col, padx=(10, 2))
            e = ttk.Entry(bar, textvariable=var, width=width)
            e.grid(row=0, column=col + 1)
            self.t_widgets.append(e)
            col += 2
        ttk.Label(bar, text=self.tr("tg_key"), style="Side.TLabel").grid(row=0, column=col, padx=(10, 2))
        self.t_keybox = ttk.Combobox(bar, textvariable=self.t_key, state="readonly", width=18,
                                     values=[self.tr("tg_key_default")] + self.tb.target_info()["keys"])
        self.t_keybox.grid(row=0, column=col + 1)
        self.t_widgets.append(self.t_keybox)
        self.btn_hostkey = ttk.Button(bar, text=self.tr("tg_hostkey"), command=self.check_hostkey)
        self.btn_hostkey.grid(row=0, column=col + 2, padx=(10, 2))
        self.btn_connect = ttk.Button(bar, text=self.tr("tg_connect"), style="Accent.TButton", command=self.connect)
        self.btn_connect.grid(row=0, column=col + 3, padx=2)
        self.btn_use = ttk.Button(bar, text=self.tr("tg_use"), command=self.apply_target)
        self.btn_use.grid(row=0, column=col + 4, padx=2)
        info = self.tb.target_info()
        self.lbl_target = tk.Label(bar, text=self.tr("tg_remote_banner", label=info["label"]) if info["kind"] == "remote" else "",
                                   bg=self.colors()["bad"], fg="#ffffff", font=("", 10, "bold"), padx=8)
        if info["kind"] == "remote":
            self.lbl_target.grid(row=1, column=0, columnspan=col + 5, sticky="we", pady=(6, 0))
        ttk.Label(bar, text=self.tr("tg_note"), style="Side.TLabel", font=("", 9), wraplength=900, justify="left").grid(
            row=2, column=0, columnspan=col + 5, sticky="w", pady=(4, 0))
        self.on_kind(redraw=False)

    def on_kind(self, redraw=True):
        remote = self.t_kind.get() == "remote"
        for w in self.t_widgets:
            w.configure(state=("readonly" if w is self.t_keybox else "normal") if remote else "disabled")
        self.btn_hostkey.configure(state="normal" if remote else "disabled")
        self.btn_connect.configure(state="normal" if remote else "disabled")
        if redraw and not remote and self.tb.target_info()["kind"] == "remote":
            self.apply_target()                                      # going back to this computer takes effect at once

    def target_values(self):
        key = self.t_key.get()
        return {"kind": self.t_kind.get(), "host": self.t_host.get().strip(), "port": self.t_port.get().strip() or "22", "user": self.t_user.get().strip(),
                "key": "" if key == self.tr("tg_key_default") else key}

    def confirm_text(self, commands):
        """The commands for a confirmation dialog - and on which computer they will run, when it is another one."""
        info = self.tb.target_info()
        text = "\n".join(commands)
        return text + ("\n\n" + self.tr("tg_running_on") + ": " + info["label"]) if info["kind"] == "remote" else text

    def apply_target(self, quiet=False):
        """Switch to the chosen computer (nothing connects yet). -> True when it was accepted."""
        v = self.target_values()
        self.tform = dict(v)
        res = self.tb.set_target(v["kind"], v["host"], v["port"], v["user"], v["key"], self.lang)
        if not res["ok"]:
            self.set_text(self.result, [("✖ " + e["message"] + "\n", "bad") for e in res["errors"]])
            self.notebook.select(0)
            return False
        self.pending, self.g_pending = None, None
        self.rebuild()
        return True

    def connect(self):
        if self.busy or not self.apply_target():
            return
        self.run_in_background(lambda: self.tb.target_test(self.lang), self.on_target_test)

    def on_target_test(self, res):
        parts = [(("✔ " if res["ok"] else "✖ ") + res["message"] + "\n", "ok" if res["ok"] and res.get("sudo") is not False else "bad" if not res["ok"] else "warn")]
        self.set_text(self.result, parts)
        self.notebook.select(0)

    def check_hostkey(self):
        v = self.target_values()
        if self.busy:
            return
        if not v["host"]:
            self.set_text(self.result, [("✖ " + self.tr("tg_unknown_host") + "\n", "bad")])
            return
        self.run_in_background(lambda: self.tb.hostkey_scan(v["host"], v["port"], self.lang), lambda r: self.on_hostkey(r, v))

    def on_hostkey(self, res, v):
        if not res["ok"]:
            self.set_text(self.result, [("✖ " + res["message"] + "\n", "bad")])
            self.notebook.select(0)
            return
        if res.get("trusted"):
            self.set_text(self.result, [("✔ " + self.tr("tg_trusted_already", host=res["host"]) + "\n", "ok")] + [(p + "\n", None) for p in res["fingerprints"]])
            self.notebook.select(0)
            return
        if messagebox.askyesno(self.tr("tg_trust_title"), self.tr("tg_trust_text", host=res["host"], port=res["port"], prints="\n".join(res["fingerprints"])),
                               icon="warning", parent=self):
            done = self.tb.hostkey_trust(res["token"], True, self.lang)
            self.set_text(self.result, [(("✔ " if done["ok"] else "✖ ") + done["message"] + "\n", "ok" if done["ok"] else "bad")])
            self.notebook.select(0)

    # ---------------------------------------------------------------- categories and the generic operation panel
    def on_category(self, _event=None):
        sel = self.cat_list.curselection()
        if sel:
            self.select_category(self.cats[sel[0]]["id"])

    def select_category(self, cid):
        if cid == self.cat_id and hasattr(self, "panel") and self.panel.winfo_children():
            return
        self.cat_id = cid
        if hasattr(self, "cat_list"):
            ids = [c["id"] for c in self.cats]
            self.cat_list.selection_clear(0, "end")
            self.cat_list.selection_set(ids.index(cid))
        self.build_panel()

    def category_ops(self):
        return next(c["operations"] for c in self.cats if c["id"] == self.cat_id)

    def build_panel(self):
        """The area to the right of the sidebar for the chosen category."""
        for w in self.panel.winfo_children():
            w.destroy()
        for name in ("rule_tree", "btn_preview", "btn_execute", "btn_refresh", "btn_delete", "lbl_state", "lbl_other"):
            if hasattr(self, name):
                delattr(self, name)
        self.pending = None
        if self.cat_id == "firewall":
            nb = ttk.Notebook(self.panel)
            nb.pack(fill="both", expand=True)
            manager = ttk.Frame(nb)
            nb.add(manager, text=self.tr("tab_manager"))
            self.build_firewall(manager)
            more = ttk.Frame(nb)
            nb.add(more, text=self.tr("tab_more"))
            self.build_generic(more, [o for o in self.category_ops() if o["id"] not in CORE_UFW])
            self.refresh_rule_view()
            if self.tb.info(self.lang)["ufw"]["installed"] and not self.tb.info(self.lang)["ufw"]["rules_loaded"]:
                self.load_rules()                                 # the list is read when the firewall tab is opened, not at start-up
        else:
            self.build_generic(self.panel, self.category_ops())

    def build_generic(self, parent, ops):
        """A list of operations, and for the chosen one a form made from its parameters, Preview and Run / Execute."""
        card = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        card.pack(fill="both", expand=True)
        left = ttk.Frame(card, style="Panel.TFrame")
        left.pack(side="left", fill="y")
        ttk.Label(left, text=self.tr("ops_list"), style="Head.TLabel").pack(anchor="w")
        c = self.colors()
        lb = tk.Listbox(left, activestyle="none", exportselection=False, relief="flat", highlightthickness=1, highlightbackground=c["border"],
                        bg=c["field"], fg=c["text"], selectbackground=c["select"], selectforeground=c["text"], width=34, height=16)
        lb.pack(fill="y", expand=True, pady=(4, 0))
        self.g_ops = list(ops)
        for o in self.g_ops:
            lb.insert("end", ("⚠ " if o["risk"] == "high" else "✎ " if o["risk"] in ("low", "medium") else "   ") + o["name"])
        lb.bind("<<ListboxSelect>>", self.on_op)
        self.g_list = lb
        self.g_right = ttk.Frame(card, style="Panel.TFrame", padding=(12, 0, 0, 0))
        self.g_right.pack(side="left", fill="both", expand=True)
        ttk.Label(self.g_right, text=self.tr("ops_hint"), style="Muted.TLabel").pack(anchor="w")
        self.g_op, self.g_vars, self.g_pending = None, {}, None
        if self.g_ops:
            lb.selection_set(0)
            self.select_op(self.g_ops[0]["id"])

    def on_op(self, _event=None):
        sel = self.g_list.curselection()
        if sel:
            self.select_op(self.g_ops[sel[0]]["id"])

    def select_op(self, op_id):
        op = next(o for o in self.g_ops if o["id"] == op_id)
        self.g_op, self.g_pending = op, None
        for w in self.g_right.winfo_children():
            w.destroy()
        ttk.Label(self.g_right, text=op["name"], style="Head.TLabel", font=("", 13, "bold")).pack(anchor="w")
        ttk.Label(self.g_right, text=op["description"], style="Muted.TLabel", wraplength=560, justify="left").pack(anchor="w", pady=(2, 6))
        form = ttk.Frame(self.g_right, style="Panel.TFrame")
        form.pack(fill="x")
        self.g_vars, self.g_widgets = {}, {}
        for r, p in enumerate(op["params"]):
            ttk.Label(form, text=self.tr(p["label"]), style="Panel.TLabel").grid(row=r, column=0, sticky="w", padx=(0, 10), pady=2)
            if p["kind"] == "bool":
                var = tk.BooleanVar(value=False)
                w = ttk.Checkbutton(form, variable=var)
            elif p["kind"] == "choice":
                values = list(p["choices"]) if not p["dynamic"] else self.tb.choices(op["id"], p["name"])
                var = tk.StringVar(value=p["default"] if p["default"] in values else (values[0] if values else ""))
                w = ttk.Combobox(form, textvariable=var, values=values or [self.tr("choice_none")], state="readonly", width=32)
            else:
                var = tk.StringVar(value=str(p["default"] or ""))
                w = ttk.Entry(form, textvariable=var, width=34)
            w.grid(row=r, column=1, sticky="w", pady=2)
            var.trace_add("write", lambda *_: self.g_changed())
            self.g_vars[p["name"]] = var
            self.g_widgets[p["name"]] = w
        if not op["params"]:
            ttk.Label(form, text=self.tr("no_input"), style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        bar = ttk.Frame(self.g_right, style="Panel.TFrame")
        bar.pack(fill="x", pady=(10, 4))
        self.g_btn_preview = ttk.Button(bar, text=self.tr("btn_preview"), command=self.g_preview)
        self.g_btn_preview.pack(side="left")
        info = op["risk"] == "info"
        self.g_btn_run = ttk.Button(bar, text=self.tr("btn_run" if info else "btn_execute"), style="Accent.TButton", command=self.g_run,
                                    state="normal" if info else "disabled")
        self.g_btn_run.pack(side="left", padx=8)
        self.g_box = self.text_widget(self.g_right, 8)
        self.g_box.pack(fill="both", expand=True, pady=(4, 0))
        self.set_text(self.g_box, [])

    def g_params(self):
        out = {}
        for p in self.g_op["params"]:
            v = self.g_vars[p["name"]].get()
            if p["kind"] == "bool":
                out[p["name"]] = bool(v)
            elif isinstance(v, str) and v.strip() and v != self.tr("choice_none"):
                out[p["name"]] = v.strip() if p["kind"] != "text" else v
        return out

    def g_changed(self):
        self.g_pending = None
        if getattr(self, "g_op", None) and self.g_op["risk"] != "info" and hasattr(self, "g_btn_run"):
            try:
                self.g_btn_run.configure(state="disabled")
            except tk.TclError:
                pass

    def g_preview(self):
        if self.busy or not self.g_op:
            return
        p = self.tb.preview(self.g_op["id"], self.g_params(), self.lang)
        self.set_text(self.g_box, self.preview_parts(p))
        self.g_pending = (self.g_op["id"], self.g_params(), p["token"], p.get("risk"), [c["display"] for c in p["commands"]]) if p["token"] else None
        if self.g_op["risk"] != "info":
            self.g_btn_run.configure(state="normal" if self.g_pending else "disabled")
        return p

    def g_run(self):
        if self.busy or not self.g_op:
            return
        op = self.g_op
        if op["risk"] == "info":
            params = self.g_params()
            self.run_in_background(lambda: self.tb.run_readonly(op["id"], self.lang, params=params), self.on_result)
            return
        if not self.g_pending:
            return
        op_id, params, token, risk, commands = self.g_pending
        deleting = risk == "high"
        if not messagebox.askyesno(self.tr("confirm_delete_title" if deleting else "confirm_title"),
                                   self.tr("confirm_delete_text" if deleting else "confirm_text", commands=self.confirm_text(commands) or op["name"]),
                                   icon="warning", parent=self):
            return
        self.g_pending = None
        self.g_btn_run.configure(state="disabled")
        self.run_in_background(lambda: self.tb.execute(op_id, params, token, True, self.lang), self.on_result)

    def build_firewall(self, parent):
        card = ttk.Frame(parent, style="Panel.TFrame", padding=12)
        card.pack(fill="both", expand=True)
        ttk.Label(card, text=self.tr("fw_title"), style="Head.TLabel", font=("", 13, "bold")).pack(anchor="w")
        self.lbl_state = ttk.Label(card, text="", style="Panel.TLabel")
        self.lbl_state.pack(anchor="w", pady=(4, 0))
        ttk.Label(card, text=self.tr("no_reload_note"), style="Small.TLabel", wraplength=760, justify="left").pack(anchor="w", pady=(2, 0))
        ttk.Label(card, text=self.tr("off_note"), style="Small.TLabel", wraplength=760, justify="left").pack(anchor="w", pady=(2, 6))
        # rules
        rules_head = ttk.Frame(card, style="Panel.TFrame")
        rules_head.pack(fill="x")
        ttk.Label(rules_head, text=self.tr("fw_rules"), style="Head.TLabel").pack(side="left")
        self.btn_refresh = ttk.Button(rules_head, text=self.tr("btn_refresh"), command=self.load_rules)
        self.btn_refresh.pack(side="right")
        self.btn_delete = ttk.Button(rules_head, text=self.tr("btn_delete_selected"), command=self.delete_selected)
        self.btn_delete.pack(side="right", padx=6)
        cols = ("action", "port", "proto", "comment")
        self.rule_tree = ttk.Treeview(card, columns=cols, show="headings", height=3, selectmode="browse")
        for col, key, w in (("action", "fw_col_action", 100), ("port", "fw_col_port", 80), ("proto", "fw_col_proto", 90),
                            ("comment", "fw_col_comment", 360)):
            self.rule_tree.heading(col, text=self.tr(key))
            self.rule_tree.column(col, width=w, anchor="w")
        self.rule_tree.pack(fill="x", pady=(4, 0))
        self.lbl_other = ttk.Label(card, text="", style="Muted.TLabel", wraplength=720, justify="left")
        self.lbl_other.pack(anchor="w")
        # form
        form = ttk.Frame(card, style="Panel.TFrame")
        form.pack(fill="x", pady=(10, 0))
        self.v_port = tk.StringVar(value=self.form["port"])
        self.v_proto = tk.StringVar(value=self.form["proto"].upper())
        self.v_action = tk.StringVar(value=self.action_label(self.form["action"]))
        self.v_comment = tk.StringVar(value=self.form["comment"])
        ttk.Label(form, text=self.tr("p_port"), style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(form, text=self.tr("p_proto"), style="Panel.TLabel").grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(form, text=self.tr("p_action"), style="Panel.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Label(form, text=self.tr("p_comment"), style="Panel.TLabel").grid(row=0, column=3, sticky="w", padx=8)
        self.ent_port = ttk.Entry(form, textvariable=self.v_port, width=10)
        self.ent_port.grid(row=1, column=0, sticky="w")
        self.cmb_proto = ttk.Combobox(form, textvariable=self.v_proto, values=["TCP", "UDP"], state="readonly", width=8)
        self.cmb_proto.grid(row=1, column=1, sticky="w", padx=8)
        self.cmb_action = ttk.Combobox(form, textvariable=self.v_action, values=[self.action_label(a) for a in ACTIONS_FORM],
                                       state="readonly", width=14)
        self.cmb_action.grid(row=1, column=2, sticky="w")
        self.ent_comment = ttk.Entry(form, textvariable=self.v_comment, width=34)
        self.ent_comment.grid(row=1, column=3, sticky="we", padx=8)
        form.columnconfigure(3, weight=1)
        buttons = ttk.Frame(card, style="Panel.TFrame")
        buttons.pack(fill="x", pady=(10, 4))
        self.btn_preview = ttk.Button(buttons, text=self.tr("btn_preview"), command=self.preview)
        self.btn_preview.pack(side="left")
        self.btn_execute = ttk.Button(buttons, text=self.tr("btn_execute"), style="Accent.TButton", command=self.execute, state="disabled")
        self.btn_execute.pack(side="left", padx=8)
        self.preview_box = self.text_widget(card, 7)
        self.preview_box.pack(fill="both", expand=True, pady=(4, 0))
        self.set_text(self.preview_box, [])
        for var in (self.v_port, self.v_proto, self.v_action, self.v_comment):
            var.trace_add("write", lambda *_: self.form_changed())

    # ---------------------------------------------------------------- form
    def action_label(self, action):
        return self.tr("act_delete" if action == "delete" else "act_" + action)

    def action_from_label(self, label):
        for a in ACTIONS_FORM:
            if self.action_label(a) == label:
                return a
        return "allow"

    def form_values(self):
        if not hasattr(self, "v_port"):                      # the firewall tab is not the one shown: keep what was typed there
            return self.form
        return {"port": self.v_port.get().strip(), "proto": self.v_proto.get().lower(), "action": self.action_from_label(self.v_action.get()),
                "comment": self.v_comment.get()}

    def form_changed(self):
        """Any edit invalidates the last preview: only what was previewed can be executed."""
        if not hasattr(self, "btn_execute"):
            return
        self.pending = None
        if hasattr(self, "btn_execute"):
            self.btn_execute.configure(state="disabled")
        self.form = self.form_values()

    def operation_for(self, v):
        """The operation and parameters the form means. 'Delete rule' is the delete operation (every rule on that port/protocol)."""
        if v["action"] == "delete":
            return "ufw.rule.delete", {"port": v["port"], "proto": v["proto"]}
        params = {"port": v["port"], "proto": v["proto"], "action": v["action"]}
        if v["comment"].strip():
            params["comment"] = v["comment"]
        return "ufw.rule.add", params

    # ---------------------------------------------------------------- actions
    def preview(self):
        if self.busy:
            return
        op_id, params = self.operation_for(self.form_values())
        self.show_preview(op_id, params)

    def preview_parts(self, p):
        """What a preview says, as coloured text parts (shared by the UFW manager and the generic panel)."""
        parts = []
        if p["errors"]:
            for e in p["errors"]:
                parts.append(("✖ " + e["message"] + "\n", "bad"))
        else:
            parts.append((self.tr("pv_title") + ": " + p["name"] + "\n", "head"))
            if p.get("remote"):
                parts.append((self.tr("tg_running_on") + ": " + p["target"] + "\n", "warn"))
            for cmd in p["commands"]:
                parts.append(("$ " + cmd["display"] + "\n", "cmd"))
                parts.append(("  " + self.tr("pv_exact") + ": " + cmd["exact"] + "\n", None))
            if not p["commands"] and not p["blocked"]:
                parts.append((self.tr("pv_nothing") + "\n", None))
            parts.append((self.tr("pv_risk") + ": " + p["level_text"] + "\n", "bad" if p["risk"] == "high" else None))
            parts.append((self.tr("pv_root") + ": " + self.tr("pv_root_yes" if p["needs_root"] else "pv_root_no") + "\n", None))
            if p["blocked"]:
                parts.append(("✖ " + p["blocked"] + "\n", "bad"))
            for line in p["warnings"]:                       # what can go wrong first: the box is small
                parts.append(("⚠ " + line + "\n", "warn"))
            for line in p["explain"]:
                parts.append(("• " + line + "\n", None))
        return parts

    def show_preview(self, op_id, params):
        p = self.tb.preview(op_id, params, self.lang)
        self.set_text(self.preview_box, self.preview_parts(p))
        self.pending = (op_id, params, p["token"], p.get("risk"), [c["display"] for c in p["commands"]]) if p["token"] else None
        self.btn_execute.configure(state="normal" if self.pending else "disabled")
        return p

    def execute(self):
        if self.busy or not self.pending:
            return
        op_id, params, token, risk, commands = self.pending
        deleting = op_id == "ufw.rule.delete"
        if not messagebox.askyesno(self.tr("confirm_delete_title" if deleting else "confirm_title"),
                                   self.tr("confirm_delete_text" if deleting else "confirm_text", commands=self.confirm_text(commands)),
                                   icon="warning", parent=self):
            return
        self.pending = None
        self.btn_execute.configure(state="disabled")
        self.run_in_background(lambda: self.tb.execute(op_id, params, token, True, self.lang), self.on_result)

    def delete_selected(self):
        if self.busy:
            return
        sel = self.rule_tree.selection()
        if not sel:
            return
        rule = self.rules_by_item.get(sel[0])
        if not rule:
            return
        params = {"port": rule["port"], "proto": rule["proto"], "action": rule["action"]}
        p = self.show_preview("ufw.rule.delete", params)
        if self.pending and messagebox.askyesno(self.tr("confirm_delete_title"),
                                                self.tr("confirm_delete_text", commands=self.confirm_text([c["display"] for c in p["commands"]])),
                                                icon="warning", parent=self):
            op_id, params, token, _risk, _cmds = self.pending
            self.pending = None
            self.btn_execute.configure(state="disabled")
            self.run_in_background(lambda: self.tb.execute(op_id, params, token, True, self.lang), self.on_result)

    def load_rules(self):
        if self.busy or not hasattr(self, "rule_tree"):
            return
        info = self.tb.info(self.lang)["ufw"]
        if not info["installed"]:
            self.refresh_rule_view()
            return
        self.run_in_background(lambda: self.tb.run_readonly("ufw.status", self.lang), self.on_result)

    def _buttons(self):
        """The buttons to switch off while something runs (only the ones that exist in the tab shown)."""
        names = ("btn_preview", "btn_refresh", "btn_delete", "g_btn_preview")
        return [getattr(self, n) for n in names if hasattr(self, n) and getattr(self, n).winfo_exists()]

    def run_in_background(self, fn, done):
        """The administrator-password dialog can stay open for a long time: never block the window."""
        self.busy = True
        self.status.configure(text=self.tr("working"))
        for b in self._buttons():
            b.configure(state="disabled")

        def work():
            try:
                self.q.put((done, fn()))
            except Exception as e:  # noqa: BLE001 - never let a thread die silently
                self.q.put((done, {"ok": False, "message": str(e), "status": "failed", "exit_code": None, "commands": [], "output": ""}))
        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                done, res = self.q.get_nowait()
                self.busy = False
                for b in self._buttons():
                    b.configure(state="normal")
                self.status.configure(text=self.tr("status_ready"))
                done(res)
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def on_result(self, res):
        parts = [((self.tr("res_ok") if res["ok"] else self.tr("res_failed")) + ": " + res["message"] + "\n", "ok" if res["ok"] else "bad")]
        if res.get("status") == "refused":
            parts[0] = (self.tr("res_refused") + ": " + res["message"] + "\n", "bad")
        for cmd in res.get("commands", []):
            parts.append(("$ " + cmd + "\n", "cmd"))
        if res.get("exit_code") is not None:
            parts.append((self.tr("res_exit") + ": " + str(res["exit_code"]) + "\n", None))
        if res.get("output"):
            parts.append((self.tr("res_output") + ":\n" + res["output"] + "\n", None))
        self.set_text(self.result, parts)
        self.notebook.select(0)
        if hasattr(self, "rule_tree"):
            self.refresh_rule_view()
        self.refresh_history()

    # ---------------------------------------------------------------- views
    def refresh_rule_view(self):
        if not hasattr(self, "rule_tree"):
            return
        info = self.tb.info(self.lang)["ufw"]
        if not info["installed"]:
            self.lbl_state.configure(text=self.tr("fw_not_installed"))
        else:
            state = {True: "fw_active", False: "fw_inactive", None: "fw_unknown"}[info["active"]]
            text = self.tr("fw_state") + ": " + self.tr(state)
            pol = info["policy"]
            if pol.get("incoming") or pol.get("outgoing"):
                text += "   |   " + self.tr("fw_policy", incoming=pol.get("incoming") or "?", outgoing=pol.get("outgoing") or "?")
            self.lbl_state.configure(text=text)
        self.rules_by_item = {}
        self.rule_tree.delete(*self.rule_tree.get_children())
        for r in info["rules"]:
            proto = self.tr("proto_any") if r["proto"] == "any" else r["proto"]
            iid = self.rule_tree.insert("", "end", values=(self.tr("act_" + r["action"]), r["port"], proto, r["comment"]))
            self.rules_by_item[iid] = r
        if not info["rules_loaded"]:
            self.rule_tree.insert("", "end", values=("", "", "", self.tr("fw_rules_not_loaded")))
        elif not info["rules"]:
            self.rule_tree.insert("", "end", values=("", "", "", self.tr("fw_no_rules")))
        self.lbl_other.configure(text=(self.tr("fw_other") + ": " + "; ".join(info["other"])) if info["other"] else "")
        self.btn_delete.configure(state="normal" if info["rules"] and not self.busy else "disabled")

    def refresh_history(self):
        self.hist_tree.delete(*self.hist_tree.get_children())
        entries = self.tb.history_entries()
        if not entries:
            self.hist_tree.insert("", "end", values=("", "", "", "", self.tr("hist_empty")))
        for e in entries:
            self.hist_tree.insert("", "end", values=(e.get("time", ""), e.get("op", ""), e.get("status", ""),
                                                     "" if e.get("exit_code") is None else e["exit_code"], e.get("summary", "")))

    def clear_history(self):
        self.tb.clear_history()
        self.refresh_history()
        self.status.configure(text=self.tr("hist_cleared"))

    # ---------------------------------------------------------------- language / theme
    def on_language(self, _event=None):
        chosen = next((k for k, v in LANG_NAMES.items() if v == self.lang_var.get()), self.lang)
        if chosen != self.lang:
            self.tform = self.target_values() if hasattr(self, "t_kind") else self.tform
            self.form = self.form_values()                       # read the form in the OLD language, before the labels change
            self.lang = chosen
            settings.save_lang(chosen)
            self.rebuild()

    def toggle_theme(self):
        self.tform = self.target_values() if hasattr(self, "t_kind") else self.tform
        self.form = self.form_values()
        self.theme = "dark" if self.theme == "light" else "light"
        settings.save_theme(self.theme)
        self.rebuild()

    def quit_app(self):
        """Close the connection to another computer (if any), then the window."""
        try:
            self.tb.close()
        finally:
            self.destroy()

    def rebuild(self):
        """Draw everything again in the current language and theme; the form values (self.form) were saved by the caller."""
        self.pending = None
        self.build()


def main():
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.quit_app)
    app.mainloop()


if __name__ == "__main__":
    main()
