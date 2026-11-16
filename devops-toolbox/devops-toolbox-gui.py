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
        self.load_rules()

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
        cats = self.tb.catalog(self.lang)["categories"]
        for c in cats:
            self.cat_list.insert("end", c["name"])
        self.cat_list.selection_set(0)
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
        self.build_firewall(main)
        self.status = ttk.Label(self, text=self.tr("status_ready"), padding=(12, 4))
        self.status.pack(side="bottom", fill="x")
        self.refresh_rule_view()

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
        return {"port": self.v_port.get().strip(), "proto": self.v_proto.get().lower(), "action": self.action_from_label(self.v_action.get()),
                "comment": self.v_comment.get()}

    def form_changed(self):
        """Any edit invalidates the last preview: only what was previewed can be executed."""
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

    def show_preview(self, op_id, params):
        p = self.tb.preview(op_id, params, self.lang)
        parts = []
        if p["errors"]:
            for e in p["errors"]:
                parts.append(("✖ " + e["message"] + "\n", "bad"))
        else:
            parts.append((self.tr("pv_title") + ": " + p["name"] + "\n", "head"))
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
        self.set_text(self.preview_box, parts)
        self.pending = (op_id, params, p["token"], p.get("risk"), [c["display"] for c in p["commands"]]) if p["token"] else None
        self.btn_execute.configure(state="normal" if self.pending else "disabled")
        return p

    def execute(self):
        if self.busy or not self.pending:
            return
        op_id, params, token, risk, commands = self.pending
        deleting = op_id == "ufw.rule.delete"
        if not messagebox.askyesno(self.tr("confirm_delete_title" if deleting else "confirm_title"),
                                   self.tr("confirm_delete_text" if deleting else "confirm_text", commands="\n".join(commands)),
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
                                                self.tr("confirm_delete_text", commands="\n".join(c["display"] for c in p["commands"])),
                                                icon="warning", parent=self):
            op_id, params, token, _risk, _cmds = self.pending
            self.pending = None
            self.btn_execute.configure(state="disabled")
            self.run_in_background(lambda: self.tb.execute(op_id, params, token, True, self.lang), self.on_result)

    def load_rules(self):
        if self.busy:
            return
        info = self.tb.info(self.lang)["ufw"]
        if not info["installed"]:
            self.refresh_rule_view()
            return
        self.run_in_background(lambda: self.tb.run_readonly("ufw.status", self.lang), self.on_result)

    def run_in_background(self, fn, done):
        """The administrator-password dialog can stay open for a long time: never block the window."""
        self.busy = True
        self.status.configure(text=self.tr("working"))
        for b in (self.btn_preview, self.btn_refresh, self.btn_delete):
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
                for b in (self.btn_preview, self.btn_refresh, self.btn_delete):
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
        self.refresh_rule_view()
        self.refresh_history()

    # ---------------------------------------------------------------- views
    def refresh_rule_view(self):
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
            self.form = self.form_values()                       # read the form in the OLD language, before the labels change
            self.lang = chosen
            settings.save_lang(chosen)
            self.rebuild()

    def toggle_theme(self):
        self.form = self.form_values()
        self.theme = "dark" if self.theme == "light" else "light"
        settings.save_theme(self.theme)
        self.rebuild()

    def rebuild(self):
        """Draw everything again in the current language and theme; the form values (self.form) were saved by the caller."""
        self.pending = None
        self.build()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
