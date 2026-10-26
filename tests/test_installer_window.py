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

    def test_the_log_file_gets_what_the_window_says(self):
        app = gui.App()
        try:
            app.say("hello from the window test")
            self.assertIn("hello from the window test", gui.read_log())
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=1)
