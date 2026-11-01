#!/usr/bin/env python3
"""The installer window for real: Tk under a display (xvfb in CI, your screen locally). Nothing is installed or downloaded:
the system and GitHub are stubbed, the buttons are clicked by calling their commands. Skipped without tkinter / a display."""
import importlib.util
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "common"))
sys.path.insert(0, os.path.join(ROOT, "installer"))
TMP = tempfile.mkdtemp()
os.environ.update(XDG_CACHE_HOME=os.path.join(TMP, "cache"), XDG_CONFIG_HOME=os.path.join(TMP, "config"))   # no real logs/settings

try:
    import tkinter as tk
    root = tk.Tk()
    root.destroy()
    SKIP = ""
except Exception as e:  # noqa: BLE001 - no tkinter or no display
    SKIP = f"no tkinter / display: {e}"

if not SKIP:
    spec = importlib.util.spec_from_file_location("installer_gui", os.path.join(ROOT, "installer", "installer-gui.py"))
    gui = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gui)


def small(sw, sh):
    class A(gui.App):
        def winfo_screenwidth(self):
            return sw

        def winfo_screenheight(self):
            return sh
    return A


def labels(frame):
    return [w.cget("text") for w in frame.winfo_children() if w.winfo_class() in ("TLabel", "Label")]


@unittest.skipIf(SKIP, SKIP)
class Window(unittest.TestCase):
    def setUp(self):
        gui.LANG = "en"
        self.msgs = []
        self.patches = [
            mock.patch.object(gui.messagebox, "showinfo", lambda *a, **k: self.msgs.append(("info", a))),
            mock.patch.object(gui.messagebox, "showwarning", lambda *a, **k: self.msgs.append(("warn", a))),
            mock.patch.object(gui.messagebox, "askyesno", lambda *a, **k: self.msgs.append(("ask", a)) or True),
            mock.patch.object(gui.updater, "check", lambda *a, **k: {"mode": "git", "behind": 0, "ahead": 0, "commits": [],
                                                                      "local": {"git": True, "short": "abc1234", "branch": "main", "date": "2026-10-17", "dirty": []}}),
            mock.patch.object(gui.extras, "outdated", lambda *a, **k: ([{"id": "rustdesk", "name": "RustDesk", "installed": "1.4.0", "latest": "1.5.0"}], [])),
            mock.patch.object(gui.App, "start_quiet_check", lambda self: None),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def pump(self, app, secs=0.3):
        """Stand-in for mainloop(): run Tk events and the calls that worker threads hand to the window via app.ui()."""
        if not hasattr(app, "_queue"):
            app._queue = []
            app.ui = lambda fn, *a: app._queue.append((fn, a))       # after() from a thread needs a running mainloop
        end = time.time() + secs
        while time.time() < end:
            while app._queue:
                fn, a = app._queue.pop(0)
                fn(*a)
            app.update()
            time.sleep(0.02)

    def test_both_languages_build_and_switch(self):
        app = gui.App()
        try:
            self.pump(app)
            en = app.f_extra_box.cget("text")
            app.toggle_lang()
            self.pump(app)
            self.assertNotEqual(en, app.f_extra_box.cget("text"))
            app.toggle_lang()
            self.pump(app)
            self.assertEqual(en, app.f_extra_box.cget("text"))
        finally:
            gui.save_lang("en")
            app.destroy()

    def test_search_narrows_the_list_and_keeps_ticks(self):
        app = gui.App()
        try:
            self.pump(app)
            everything = sum(1 for w in app.f_extra.winfo_children() if w.winfo_class() == "TCheckbutton")
            self.assertEqual(everything, len(gui.EXTRAS))
            app.extra_vars["discord"].set(True)
            app.v_search.set("disc")
            self.pump(app)
            names = [w.cget("text") for w in app.f_extra.winfo_children() if w.winfo_class() == "TCheckbutton"]
            self.assertEqual(names, ["Discord"])
            app.v_search.set("zzzz-nothing")
            self.pump(app)
            self.assertIn(gui.t("no_match"), labels(app.f_extra))
            app.v_search.set("")
            self.pump(app)
            self.assertTrue(app.extra_vars["discord"].get())              # still ticked after filtering
        finally:
            app.destroy()

    def row_of(self, app, name):
        """(checkbox widget, state text, description text) of a program row in the 'other programs' list."""
        kids = app.f_extra.winfo_children()
        for i, w in enumerate(kids):
            if w.winfo_class() == "TCheckbutton" and w.cget("text") == name:
                return w, kids[i + 1].cget("text"), kids[i + 2].cget("text")
        self.fail(f"no row {name}")

    def test_the_list_says_what_this_system_can_install(self):
        osr = {"PRETTY_NAME": "Manjaro Linux", "ID": "manjaro", "ID_LIKE": "arch"}
        with mock.patch.object(gui, "detect_pm", lambda: "pacman"), mock.patch("platform.machine", lambda: "x86_64"), \
                mock.patch.object(gui.extras, "os_release", lambda *a: osr), \
                mock.patch.object(gui.extras, "aur_installed", lambda p: None), \
                mock.patch.object(gui.extras, "flatpak_scopes", lambda i: set()), \
                mock.patch.object(gui.extras.shutil, "which", lambda c: None):
            app = gui.App()
            try:
                self.pump(app)
                self.assertEqual(app.lbl_sys.cget("text"), "This system: Manjaro Linux - pacman, x86_64")
                box, state, info = self.row_of(app, "Claude Desktop (beta)")
                self.assertEqual(state, gui.t("na"))
                self.assertTrue(box.instate(["disabled"]))
                self.assertIn("Debian / Ubuntu / Mint", info)
                box, state, info = self.row_of(app, "Tabby")
                self.assertEqual(state, "AUR")
                self.assertFalse(box.instate(["disabled"]))
                self.assertIn("AUR", info)
                self.assertEqual(self.row_of(app, "Discord")[1], "Flatpak")
                self.assertEqual(self.row_of(app, "Brave Browser")[1], gui.t("none"))
                app.toggle_lang()
                self.pump(app)
                self.assertEqual(self.row_of(app, next(x for x in gui.EXTRAS if x["id"] == "claude")["name"]["ka"])[1], gui.t("na"))
                self.assertIn("ეს სისტემა", app.lbl_sys.cget("text"))
            finally:
                gui.save_lang("en")
                app.destroy()

    def test_a_program_that_is_installed_can_still_be_removed_where_nothing_new_installs(self):
        with mock.patch.object(gui, "detect_pm", lambda: "dnf"), mock.patch("platform.machine", lambda: "x86_64"), \
                mock.patch.object(gui.App, "ex_native_state", lambda self, i: "1.2" if i == "claude" else None):
            app = gui.App()
            try:
                self.pump(app)
                box, state, _ = self.row_of(app, "Claude Desktop (beta)")
                self.assertEqual(state, "1.2")
                self.assertFalse(box.instate(["disabled"]))
            finally:
                app.destroy()

    def test_aur_install_shows_the_pkgbuild_and_builds_only_after_yes(self):
        info = {"dir": "/c/aur/tabby-bin", "meta": {"Version": "1-1", "Maintainer": "m", "NumVotes": 3},
                "files": {"PKGBUILD": "pkgname=tabby-bin\n"}, "sha256": "f" * 64}
        with mock.patch.object(gui, "detect_pm", lambda: "pacman"), mock.patch("platform.machine", lambda: "x86_64"), \
                mock.patch.object(gui.extras, "aur_fetch", lambda pkg: info), mock.patch.object(gui.extras, "aur_installed", lambda p: None), \
                mock.patch.object(gui, "elevate", lambda cmd: ["pkexec"] + cmd), mock.patch.object(gui.extras.shutil, "which", lambda c: None), \
                mock.patch.object(gui.os, "geteuid", lambda: 1000):
            app = gui.App()
            try:
                self.pump(app)
                with mock.patch.object(gui.App, "confirm_aur", lambda self, name, pkg, i: False):
                    self.assertEqual(app.aur_jobs("install", "tabby"), (True, None))
                shown = {}
                with mock.patch.object(gui.App, "confirm_aur", lambda self, name, pkg, i: shown.update(name=name, pkg=pkg) or True):
                    handled, jobs = app.aur_jobs("install", "tabby")
                self.assertTrue(handled)
                self.assertEqual(shown, {"name": "Tabby", "pkg": "tabby-bin"})
                self.assertEqual([j[0] == "pkexec" for j in jobs], [True, False, True, False])
                self.assertEqual(app.aur_jobs("install", "brave"), (False, []))          # no AUR entry: the normal route
                with mock.patch.object(gui.os, "geteuid", lambda: 0):                    # makepkg refuses root: say so, build nothing
                    self.assertEqual(app.aur_jobs("install", "tabby"), (True, None))
                self.assertEqual(self.msgs[-1][0], "warn")
                with mock.patch.object(gui.extras, "aur_installed", lambda p: "1-1"):
                    handled, jobs = app.aur_jobs("uninstall", "tabby")
                self.assertTrue(handled)
                self.assertIn("pacman -R --noconfirm tabby-bin", jobs[0][-1])
            finally:
                app.destroy()

    def test_aur_is_never_used_where_flathub_or_the_publisher_already_serve(self):
        with mock.patch.object(gui, "detect_pm", lambda: "apt-get"), mock.patch("platform.machine", lambda: "x86_64"):
            app = gui.App()
            try:
                self.pump(app)
                self.assertEqual(app.aur_jobs("install", "tabby"), (False, []))
                self.assertEqual(app.aur_jobs("install", "discord"), (False, []))
            finally:
                app.destroy()

    def test_the_review_window_shows_the_pkgbuild_and_the_answer_is_the_button(self):
        info = {"meta": {"Version": "1-1", "Maintainer": "m", "NumVotes": 3, "OutOfDate": 1700000000},
                "files": {"PKGBUILD": "pkgname=tabby-bin\n", "x.install": "post_install() { :; }\n"}, "sha256": "f" * 64}
        app = gui.App()
        try:
            self.pump(app)
            seen = {}

            def press(button_text):
                def fake_wait(win):
                    texts = [w for w in win.winfo_children()]

                    def find(widget, cls):
                        for c in widget.winfo_children():
                            if c.winfo_class() == cls:
                                return c
                            hit = find(c, cls)
                            if hit:
                                return hit
                    seen["head"] = [w.cget("text") for w in texts if w.winfo_class() == "TLabel"][0]
                    seen["body"] = find(win, "Text").get("1.0", "end")
                    bar = [w for w in texts if w.winfo_class() == "TFrame"][0]
                    next(b for b in bar.winfo_children() if b.cget("text") == gui.t(button_text)).invoke()
                return fake_wait
            with mock.patch.object(app, "wait_window", press("aur_install")):
                self.assertTrue(app.confirm_aur("Tabby", "tabby-bin", info))
            self.assertIn("pkgname=tabby-bin", seen["body"])
            self.assertIn("post_install", seen["body"])
            self.assertIn("OUT OF DATE", seen["head"])
            self.assertIn("f" * 64, seen["head"])
            with mock.patch.object(app, "wait_window", press("aur_cancel")):
                self.assertFalse(app.confirm_aur("Tabby", "tabby-bin", info))
        finally:
            app.destroy()

    def test_groups_headings_are_shown(self):
        app = gui.App()
        try:
            self.pump(app)
            heads = labels(app.f_extra)
            for g in gui.GROUP_TEXT.values():
                self.assertIn(gui.t(g), heads)
        finally:
            app.destroy()

    def test_ticking_shows_what_will_run(self):
        app = gui.App()
        try:
            self.pump(app)
            app.pick(False)
            app.extra_vars["vscode"].set(True)
            app.sync()
            self.assertIn("Visual Studio Code", app.lbl_cmd.cget("text"))
        finally:
            app.destroy()

    def test_it_fits_small_screens(self):
        for sw, sh in ((1024, 600), (1366, 768), (1280, 720)):
            app = small(sw, sh)()
            try:
                self.pump(app, 0.2)
                self.assertLessEqual(app.winfo_width(), sw)
                self.assertLessEqual(app.winfo_height(), sh)
            finally:
                app.destroy()

    def test_settings_window_opens_checks_and_ticks_programs(self):
        app = gui.App()
        try:
            self.pump(app)
            app.open_settings()
            self.pump(app, 0.6)
            top = [w for w in app.winfo_children() if w.winfo_class() == "Toplevel"]
            self.assertEqual(len(top), 1)

            def buttons(w):
                out = []
                for c in w.winfo_children():
                    if c.winfo_class() == "TButton":
                        out.append(c)
                    out += buttons(c)
                return out
            texts = {b.cget("text"): b for b in buttons(top[0])}
            self.assertIn(gui.t("prog_check"), texts)
            self.assertTrue(any(k.startswith("GitHub") for k in texts))
            texts[gui.t("prog_check")].invoke()
            self.pump(app, 1.0)
            tick = texts[gui.t("prog_tick")]
            self.assertEqual(str(tick.cget("state")), "normal")             # RustDesk is "outdated" in the stub
            tick.invoke()
            self.pump(app, 0.3)
            self.assertTrue(app.extra_vars["rustdesk"].get())
        finally:
            app.destroy()

    def test_progress_and_cancel_of_a_running_job(self):
        app = gui.App()
        try:
            self.pump(app)
            jobs = [["sh", "-c", "echo '#### 40.0%'; sleep 30"], ["sh", "-c", "echo NEVER"]]
            seen, pcts, result = [], [], {}
            app.busy = True
            app.run_ctl = {"cancel": False}
            app.runbar.pack(side="bottom", fill="x", before=app.lbl_status)
            app.prog.start(12)

            def on_line(ln):                       # what go() does, minus Tk's after(): the worker only queues values
                pct = gui.progress_percent(ln)
                (seen if pct is None else pcts).append(ln if pct is None else pct)

            def work():
                result["rc"] = gui.run_jobs(jobs, on_line, app.run_ctl)
            th = threading.Thread(target=work)
            th.start()
            t0 = time.time()
            while time.time() - t0 < 5 and not pcts:
                self.pump(app, 0.1)
            self.assertEqual(pcts, [40.0])
            app.show_progress(pcts[0])
            self.assertEqual(str(app.prog.cget("mode")), "determinate")        # the percentage reached the bar
            self.assertIn("40%", app.lbl_status.cget("text"))
            app.cancel_run()
            th.join(10)
            self.assertFalse(th.is_alive())
            self.assertEqual(result["rc"], 130)
            self.assertNotIn("NEVER\n", seen)
            app.finish(result["rc"])
            self.pump(app)
            self.assertEqual(app.lbl_status.cget("text"), gui.t("cancelled"))
            self.assertFalse(app.runbar.winfo_ismapped())
        finally:
            app.destroy()

    def test_gis_window_lists_both_projects_lists_and_installs_ticked_packages(self):
        app = gui.App()
        try:
            self.pump(app)
            started = {}
            with mock.patch.object(gui, "detect_pm", lambda: "apt-get"), \
                    mock.patch.object(gui.extras, "gis_installed", lambda *a, **k: False), \
                    mock.patch.object(gui, "elevate", lambda cmd: ["pkexec"] + cmd), \
                    mock.patch.object(app, "start_jobs", lambda jobs, **k: started.update(jobs=jobs, **k)):
                app.open_gis()
                self.pump(app, 0.5)
                top = [w for w in app.winfo_children() if w.winfo_class() == "Toplevel"][0]

                def find(w, cls):
                    out = []
                    for c in w.winfo_children():
                        if c.winfo_class() == cls:
                            out.append(c)
                        out += find(c, cls)
                    return out
                tabs = find(top, "TNotebook")[0]
                self.assertEqual([tabs.tab(i, "text") for i in range(tabs.index("end"))], ["OSGeo Projects", "Community projects"])
                texts = [w.cget("text") for w in find(top, "TCheckbutton")]
                self.assertIn("Marble", texts)
                self.assertIn("GDAL/OGR", texts)
                self.assertNotIn("GeoServer", texts)                           # link-only: no checkbox
                self.assertIn("Desktop Applications", [w.cget("text") for w in find(top, "TLabel")])
                app.gis_vars["marble"].set(True)
                app.gis_vars["mapserver"].set(True)
                buttons = {b.cget("text"): b for b in find(top, "TButton")}
                buttons[gui.t("gis_install")].invoke()
                self.pump(app, 0.3)
            self.assertEqual(len(started["jobs"]), 2)
            self.assertIn("apt-get install -y marble", " ".join(started["jobs"][0]))
            self.assertIn("mapserver-bin cgi-mapserver", " ".join(started["jobs"][1]))
            self.assertIn("Marble", started["shown"])
        finally:
            app.destroy()

    def test_gis_window_in_georgian(self):
        gui.LANG = "ka"
        app = gui.App()
        try:
            self.pump(app)
            app.open_gis()
            self.pump(app, 0.4)
            top = [w for w in app.winfo_children() if w.winfo_class() == "Toplevel"][0]
            self.assertEqual(top.title(), gui.t("gis_title"))
        finally:
            gui.save_lang("en")
            app.destroy()

    def test_opengeos_window_cards_search_filter_and_click(self):
        app = gui.App()
        try:
            self.pump(app)
            opened = []
            with mock.patch("webbrowser.open", lambda url: opened.append(url) or True):
                app.open_opengeos()
                self.pump(app, 0.6)
                top = [w for w in app.winfo_children() if w.winfo_class() == "Toplevel"][0]

                def walk(w):
                    for c in w.winfo_children():
                        yield c
                        yield from walk(c)
                counts = lambda: [w.cget("text") for w in walk(top) if w.winfo_class() == "TLabel" and w.cget("text").endswith("projects")]   # noqa: E731
                self.assertEqual(counts(), ["82 projects"])
                entry = next(w for w in walk(top) if w.winfo_class() == "TEntry")
                combo = next(w for w in walk(top) if w.winfo_class() == "TCombobox")
                entry.insert(0, "leafmap")
                self.pump(app, 0.5)
                names = [w.cget("text") for w in walk(top) if w.winfo_class() == "Label" and w.cget("fg") == "#1a5fb4"]
                self.assertIn("leafmap", names)
                self.assertLess(len(names), 10)
                entry.delete(0, "end")
                combo.set("R Packages")
                combo.event_generate("<<ComboboxSelected>>")
                self.pump(app, 0.5)
                names = [w.cget("text") for w in walk(top) if w.winfo_class() == "Label" and w.cget("fg") == "#1a5fb4"]
                self.assertEqual(names, ["whiteboxR"])
                card = next(w for w in walk(top) if w.winfo_class() == "Label" and w.cget("text") == "whiteboxR")
                card.event_generate("<Button-1>")
                self.pump(app, 0.2)
            self.assertEqual(opened, ["https://github.com/opengeos/whiteboxR"])
        finally:
            app.destroy()

    def test_opengeos_window_in_georgian_and_the_header_button(self):
        gui.LANG = "ka"
        app = gui.App()
        try:
            self.pump(app)
            self.assertEqual(app.btn_og.cget("text"), "OpenGeos")
            app.open_opengeos()
            self.pump(app, 0.4)
            top = [w for w in app.winfo_children() if w.winfo_class() == "Toplevel"][0]
            labels_ = [w.cget("text") for w in top.winfo_children()[0].winfo_children() + top.winfo_children()
                       if w.winfo_class() in ("TLabel", "Label")]
            self.assertTrue(any("გეოსივრცული" in x for x in labels_))
        finally:
            gui.save_lang("en")
            app.destroy()

    def test_the_log_file_gets_what_the_window_says(self):
        app = gui.App()
        try:
            app.say("hello from the window test")
            self.assertIn("hello from the window test", gui.read_log())
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=1)
