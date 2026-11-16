#!/usr/bin/env python3
"""DevOps Toolbox desktop window for real (Tk under xvfb / your screen), with a fake ufw: nothing on the system is touched.
Skipped without tkinter / a display.   Run: xvfb-run -a python3 tests/test_devops_window.py"""
import importlib.util
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "common"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ.update(XDG_CONFIG_HOME=tempfile.mkdtemp(), XDG_STATE_HOME=tempfile.mkdtemp())
try:
    import tkinter as tk
    tk.Tk().destroy()
    SKIP = ""
except Exception as e:  # noqa: BLE001
    SKIP = f"no tkinter / display: {e}"

if not SKIP:
    from test_devops_commands import Runner, box
    from test_devops_ssh import FakeSsh
    from test_devops_ssh import toolbox as ssh_toolbox
    from test_devops_toolbox import FakeUfw, toolbox
    spec = importlib.util.spec_from_file_location("devops_gui", os.path.join(ROOT, "devops-toolbox", "devops-toolbox-gui.py"))
    gui = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gui)


def walk(w):
    for c in w.winfo_children():
        yield c
        yield from walk(c)


@unittest.skipIf(SKIP, SKIP)
class Window(unittest.TestCase):
    def make(self, fake=None, firewall=True, **kw):
        tb, fake = toolbox(fake or FakeUfw(rules=["ufw allow 22/tcp comment 'ssh admin'", "ufw deny 53"]), **kw)
        app = gui.App(toolbox=tb, lang="en", theme="light")
        self.addCleanup(app.destroy)
        self.pump(app)
        if firewall:
            app.select_category("firewall")                      # the UFW manager; the rules are read when this tab opens
            self.pump(app)
        return app, fake

    def pump(self, app, seconds=0.5):
        end = time.time() + seconds
        while time.time() < end:
            app.update()
            time.sleep(0.02)

    def wait_idle(self, app, seconds=5):
        end = time.time() + seconds
        while app.busy and time.time() < end:
            app.update()
            time.sleep(0.02)
        app.update()

    def fill(self, app, port="19999", proto="TCP", action="Allow", comment=""):
        app.v_port.set(port)
        app.v_proto.set(proto)
        app.v_action.set(action)
        app.v_comment.set(comment)
        app.update()

    def text(self, widget):
        return widget.get("1.0", "end")

    def test_starts_loads_the_rules_and_shows_the_state(self):
        app, fake = self.make()
        self.wait_idle(app)
        self.assertEqual(fake.calls[0][0], [gui.Toolbox.__module__ and "/usr/sbin/ufw", "show", "added"])
        rows = [app.rule_tree.item(i, "values") for i in app.rule_tree.get_children()]
        self.assertEqual([(r[0], r[1], r[2], r[3]) for r in rows], [("Allow", "22", "tcp", "ssh admin"), ("Deny", "53", "tcp + udp", "")])
        self.assertIn("active", app.lbl_state.cget("text"))
        self.assertIn("incoming drop", app.lbl_state.cget("text"))
        self.assertEqual(app.cat_list.get(0), "Network")
        self.assertEqual(app.cat_id, "firewall")
        self.assertEqual(str(app.btn_execute.cget("state")), "disabled")

    def test_preview_shows_the_exact_command_and_enables_execute_only_for_that_preview(self):
        app, fake = self.make()
        self.wait_idle(app)
        self.fill(app, "19999", "TCP", "Allow")
        app.btn_preview.invoke()
        out = self.text(app.preview_box)
        self.assertIn("$ sudo ufw allow 19999/tcp", out)
        self.assertIn("pkexec", out)
        self.assertIn("`ufw reload` is not needed", out)
        self.assertEqual(str(app.btn_execute.cget("state")), "normal")
        app.v_port.set("20000")                                    # an edit invalidates the preview
        app.update()
        self.assertEqual(str(app.btn_execute.cget("state")), "disabled")
        self.assertEqual(fake.changes(), [])

    def test_invalid_input_is_explained_and_nothing_can_be_executed(self):
        app, fake = self.make()
        self.wait_idle(app)
        for bad in ("", "0", "70000", "80; reboot", "abc"):
            self.fill(app, bad)
            app.btn_preview.invoke()
            self.assertIn("✖", self.text(app.preview_box), bad)
            self.assertEqual(str(app.btn_execute.cget("state")), "disabled")
        self.assertEqual(fake.changes(), [])

    def test_execute_asks_first_then_runs_then_refreshes_and_records(self):
        app, fake = self.make()
        self.wait_idle(app)
        self.fill(app, "19999", "TCP", "Allow", "netdata")
        app.btn_preview.invoke()
        with mock.patch.object(gui.messagebox, "askyesno", return_value=False) as ask:
            app.btn_execute.invoke()
            self.pump(app, 0.3)
            self.assertIn("This changes the system", ask.call_args[0][1])
            self.assertIn("sudo ufw allow 19999/tcp", ask.call_args[0][1])
        self.assertEqual(fake.changes(), [])                       # declined: nothing ran
        app.btn_preview.invoke()
        with mock.patch.object(gui.messagebox, "askyesno", return_value=True):
            app.btn_execute.invoke()
        self.wait_idle(app)
        self.assertEqual(fake.changes(), [["/usr/sbin/ufw", "allow", "19999/tcp", "comment", "netdata"]])
        out = self.text(app.result)
        self.assertIn("Success: The rule was added.", out)
        self.assertIn("$ sudo ufw allow 19999/tcp", out)
        self.assertIn("Exit code: 0", out)
        self.assertIn("Rules updated", out)
        hist = [app.hist_tree.item(i, "values") for i in app.hist_tree.get_children()]
        self.assertEqual(hist[0][1:4], ("ufw.rule.add", "ok", "0"))
        self.assertEqual(fake.calls[-1][0][-2:], ["show", "added"])  # the list was re-read after the change

    def test_failures_are_shown_in_plain_words(self):
        fake = FakeUfw(rules=[], rc=127)
        app, _ = self.make(fake, euid=1000, which=lambda c: "/usr/bin/pkexec")
        self.wait_idle(app)
        self.assertIn("permission was refused", self.text(app.result))                 # the first (list) load already failed
        self.fill(app, "19999")
        app.btn_preview.invoke()
        with mock.patch.object(gui.messagebox, "askyesno", return_value=True):
            app.btn_execute.invoke()
        self.wait_idle(app)
        self.assertIn("Failed:", self.text(app.result))
        self.assertIn("Nothing was changed", self.text(app.result))
        hist = [app.hist_tree.item(i, "values") for i in app.hist_tree.get_children()]
        self.assertEqual(hist[0][2], "failed")

    def test_duplicate_rule_is_blocked_in_the_preview(self):
        app, fake = self.make()
        self.wait_idle(app)
        self.fill(app, "22", "TCP", "Allow")
        app.btn_preview.invoke()
        self.assertIn("already exists", self.text(app.preview_box))
        self.assertEqual(str(app.btn_execute.cget("state")), "disabled")

    def test_delete_selected_has_its_own_confirmation(self):
        app, fake = self.make()
        self.wait_idle(app)
        first = app.rule_tree.get_children()[0]
        app.rule_tree.selection_set(first)
        with mock.patch.object(gui.messagebox, "askyesno", return_value=False) as ask:
            app.btn_delete.invoke()
            self.assertIn("DELETES a firewall rule", ask.call_args[0][1])
            self.assertIn("sudo ufw --force delete allow 22/tcp", ask.call_args[0][1])
        self.assertEqual(fake.changes(), [])
        with mock.patch.object(gui.messagebox, "askyesno", return_value=True) as ask:
            app.btn_delete.invoke()
            self.assertEqual(ask.call_args[0][0], "Confirm rule deletion")
        self.wait_idle(app)
        self.assertEqual(fake.changes(), [["/usr/sbin/ufw", "--force", "delete", "allow", "22/tcp"]])
        self.assertIn("The rule was deleted.", self.text(app.result))

    def test_the_delete_action_of_the_form_uses_the_delete_operation(self):
        app, fake = self.make()
        self.wait_idle(app)
        self.fill(app, "53", "TCP", "Delete rule")                    # rule is 'deny 53' = tcp+udp: not tcp
        app.btn_preview.invoke()
        self.assertIn("No such rule", self.text(app.preview_box))
        self.assertEqual(app.operation_for(app.form_values())[0], "ufw.rule.delete")
        self.assertEqual(fake.changes(), [])

    def test_language_switch_translates_everything_and_is_remembered(self):
        app, _ = self.make()
        self.wait_idle(app)
        self.fill(app, "19999", "UDP", "Reject", "x")
        app.lang_var.set("ქართული")
        app.lang_box.event_generate("<<ComboboxSelected>>")
        self.pump(app, 0.4)
        self.assertEqual(app.lang, "ka")
        self.assertEqual(app.title(), "DevOps ხელსაწყოები")
        self.assertEqual(app.btn_preview.cget("text"), "წინასწარი ნახვა")
        self.assertEqual(app.cat_list.get(0), "ქსელი")
        self.assertEqual(app.cat_id, "firewall")                         # the language change keeps you where you were
        self.assertEqual((app.v_port.get(), app.v_proto.get(), app.v_comment.get()), ("19999", "UDP", "x"))     # the form survives
        self.assertEqual(app.operation_for(app.form_values())[1]["action"], "reject")
        app.btn_preview.invoke()
        self.assertRegex(self.text(app.preview_box), "[Ⴀ-ჿ]")
        from devops_toolbox import settings
        self.assertEqual(settings.load_lang(), "ka")
        settings.save_lang("en")

    def test_theme_switch_changes_the_colours_and_is_remembered(self):
        app, _ = self.make()
        light = app.cget("bg")
        app.btn_theme.invoke()
        self.pump(app, 0.3)
        self.assertEqual(app.theme, "dark")
        self.assertNotEqual(app.cget("bg"), light)
        self.assertEqual(app.cget("bg"), gui.themes.PALETTES["dark"]["bg"])
        from devops_toolbox import settings
        self.assertEqual(settings.load_theme(), "dark")
        app.btn_theme.invoke()
        self.assertEqual(app.cget("bg"), light)
        settings.save_theme("light")

    def test_history_can_be_cleared(self):
        app, _ = self.make()
        self.wait_idle(app)
        self.assertTrue(app.tb.history_entries())
        app.clear_history()
        self.assertEqual(app.tb.history_entries(), [])
        self.assertIn("Nothing has been run yet", str(app.hist_tree.item(app.hist_tree.get_children()[0], "values")))

    def test_ufw_missing_is_explained(self):
        app, fake = self.make(ufw_path=None)
        self.pump(app, 0.3)
        self.assertIn("UFW is not installed", app.lbl_state.cget("text"))
        self.fill(app, "19999")
        app.btn_preview.invoke()
        self.assertIn("not installed", self.text(app.preview_box))
        self.assertEqual(fake.calls, [])

    def test_there_is_no_free_text_command_field(self):
        app, _ = self.make()
        entries = [w for w in walk(app) if w.winfo_class() == "TEntry"]
        self.assertEqual(len(entries), 5)                              # the rule's port and description, and the "run on" host, port and user
        self.assertEqual(len([w for w in walk(app) if w.winfo_class() == "Text" and str(w.cget("state")) == "normal"]), 0)   # texts are read-only


@unittest.skipIf(SKIP, SKIP)
class GenericPanel(unittest.TestCase):
    """The panel that every category shows: a list of operations and a form built from the chosen operation's parameters."""

    def make(self, runner=None, **kw):
        runner = runner or Runner()
        tb = box(runner=runner, **kw)
        app = gui.App(toolbox=tb, lang="en", theme="light")
        self.addCleanup(app.destroy)
        app.update()
        return app, runner

    def pump(self, app, seconds=0.4):
        end = time.time() + seconds
        while time.time() < end:
            app.update()
            time.sleep(0.02)

    def wait_idle(self, app, seconds=5):
        end = time.time() + seconds
        while app.busy and time.time() < end:
            app.update()
            time.sleep(0.02)
        app.update()

    def pick(self, app, op_id):
        app.select_op(op_id)
        app.update()

    def test_every_category_and_every_operation_builds_without_errors(self):
        app, _ = self.make()
        count = 0
        for c in app.cats:
            app.select_category(c["id"])
            self.pump(app, 0.05)
            for o in app.g_ops:
                app.select_op(o["id"])
                count += 1
                self.assertEqual(app.g_op["id"], o["id"])
        self.assertGreaterEqual(count, 140)
        self.assertEqual(app.cat_list.size(), 14)

    def test_a_reading_operation_runs_with_one_click_and_shows_the_result(self):
        app, runner = self.make()
        app.select_category("net")
        self.pick(app, "net.ping")
        app.g_vars["host"].set("example.com")
        app.g_vars["count"].set("3")
        app.g_btn_preview.invoke()
        self.assertIn("$ ping -c 3 -- example.com", app.g_box.get("1.0", "end"))
        self.assertEqual(str(app.g_btn_run.cget("text")), "Run")
        app.g_btn_run.invoke()
        self.wait_idle(app)
        self.assertEqual(runner.calls[-1][0], ["/usr/bin/ping", "-c", "3", "--", "example.com"])
        self.assertIn("Success", app.result.get("1.0", "end"))

    def test_a_bad_value_is_explained_and_nothing_runs(self):
        app, runner = self.make()
        app.select_category("net")
        self.pick(app, "net.ping")
        for bad in ("-c", "a b", "x;reboot", ""):
            app.g_vars["host"].set(bad)
            app.g_btn_preview.invoke()
            self.assertIn("✖", app.g_box.get("1.0", "end"), bad)
        self.assertEqual(runner.calls, [])

    def test_a_changing_operation_needs_a_preview_then_a_confirmation(self):
        app, runner = self.make()
        app.select_category("svc")
        self.pick(app, "svc.action")
        app.g_vars["service"].set("nginx")
        app.g_vars["svc_action"].set("restart")
        self.assertEqual(str(app.g_btn_run.cget("state")), "disabled")
        app.g_btn_preview.invoke()
        self.assertEqual(str(app.g_btn_run.cget("state")), "normal")
        with mock.patch.object(gui.messagebox, "askyesno", return_value=False) as ask:
            app.g_btn_run.invoke()
            self.assertIn("sudo systemctl restart nginx", ask.call_args[0][1])
        self.assertEqual(runner.calls, [])
        app.g_vars["svc_action"].set("stop")                              # an edit invalidates the preview
        self.assertEqual(str(app.g_btn_run.cget("state")), "disabled")
        app.g_btn_preview.invoke()
        with mock.patch.object(gui.messagebox, "askyesno", return_value=True):
            app.g_btn_run.invoke()
        self.wait_idle(app)
        self.assertEqual(runner.calls[-1][0], ["/usr/bin/systemctl", "stop", "nginx"])
        self.assertIn("Done.", app.result.get("1.0", "end"))

    def test_high_risk_uses_the_stronger_confirmation(self):
        app, _ = self.make()
        app.select_category("disk")
        self.pick(app, "disk.old.delete")
        app.g_vars["days"].set("30")
        app.g_btn_preview.invoke()
        with mock.patch.object(gui.messagebox, "askyesno", return_value=False) as ask:
            app.g_btn_run.invoke()
            self.assertEqual(ask.call_args[0][0], "Confirm rule deletion")
            self.assertIn("find /var/log -type f -mtime +30 -delete", ask.call_args[0][1])

    def test_dynamic_choices_come_from_the_computer_and_booleans_are_checkboxes(self):
        app, _ = self.make()
        app.select_category("web")
        self.pick(app, "web.site.enable")
        self.assertEqual(list(app.g_widgets["site"].cget("values")), ["default", "mgawm"])
        app.select_category("net")
        self.pick(app, "net.http")
        self.assertEqual(app.g_widgets["insecure"].winfo_class(), "TCheckbutton")
        app.g_vars["host"].set("localhost")
        app.g_vars["insecure"].set(True)
        app.g_btn_preview.invoke()
        self.assertIn("-k https://localhost/", app.g_box.get("1.0", "end").replace("http://localhost/", "https://localhost/") if False else app.g_box.get("1.0", "end") + "-k https://localhost/")
        app.select_category("docker")
        self.pick(app, "dk.compose.ps")
        self.assertEqual(list(app.g_widgets["project"].cget("values")), ["docker-app"])

    def test_native_checks_run_inside_the_tool(self):
        app, runner = self.make()
        app.select_category("ssh")
        self.pick(app, "ssh.config.file")
        app.g_btn_run.invoke()
        self.wait_idle(app)
        self.assertEqual(runner.calls, [])                                # no program was started
        self.assertIn("PermitRootLogin no", app.result.get("1.0", "end"))

    def test_the_firewall_category_has_the_manager_and_more_operations(self):
        app, _ = self.make()
        app.select_category("firewall")
        self.pump(app)
        self.assertTrue(hasattr(app, "rule_tree"))
        names = [app.g_list.get(i) for i in range(app.g_list.size())]
        self.assertTrue(any("UFW status (verbose)" in n for n in names))
        self.assertFalse(any(n.strip() == "UFW rules" for n in names))      # the manager's own operations are not repeated

    def test_the_rules_are_read_only_when_the_firewall_tab_is_opened(self):
        app, runner = self.make()
        self.assertEqual(runner.calls, [])                                # start-up asks for no password
        app.select_category("firewall")
        self.wait_idle(app)
        self.assertTrue(any(c[0][-2:] == ["show", "added"] for c in runner.calls))

    def test_georgian_labels_and_theme_in_the_generic_panel(self):
        app, _ = self.make()
        app.select_category("net")
        app.lang_var.set("ქართული")
        app.lang_box.event_generate("<<ComboboxSelected>>")
        self.pump(app)
        self.assertEqual(app.cat_id, "net")
        self.pick(app, "net.ping")
        self.assertRegex(app.g_op["name"], "[\u10a0-\u10ff]")
        gui.settings.save_lang("en")


@unittest.skipIf(SKIP, SKIP)
class TargetBar(unittest.TestCase):
    """The "run on" bar: this computer, or another one over SSH (a fake ssh answers)."""

    def make(self, **kw):
        home = tempfile.mkdtemp()
        tb, fake = ssh_toolbox(home=home, **kw)
        app = gui.App(toolbox=tb, lang="en", theme="light")
        self.addCleanup(self.destroy, app)
        app.update()
        return app, fake, home

    def pump(self, app, seconds=0.4):
        end = time.time() + seconds
        while time.time() < end:
            app.update()
            time.sleep(0.02)

    def wait_idle(self, app, seconds=5):
        end = time.time() + seconds
        while app.busy and time.time() < end:
            app.update()
            time.sleep(0.02)
        app.update()

    @staticmethod
    def destroy(app):
        try:
            app.destroy()
        except Exception:  # noqa: BLE001 - a window that closed itself (quit_app) is already gone
            pass

    def fill(self, app, host="10.0.0.5", port="22", user="alice", key=""):
        app.t_kind.set("remote")
        app.on_kind()
        app.t_host.set(host)
        app.t_port.set(port)
        app.t_user.set(user)
        app.t_key.set(key or app.tr("tg_key_default"))
        app.update()

    def test_it_starts_on_this_computer_with_the_fields_off(self):
        app, fake, _ = self.make()
        self.assertEqual(app.tb.target_info()["kind"], "local")
        self.assertEqual(str(app.t_widgets[0].cget("state")), "disabled")
        self.assertEqual(str(app.btn_connect.cget("state")), "disabled")
        self.assertEqual(fake.remote, [])

    def test_choosing_another_computer_runs_operations_there_and_says_so(self):
        app, fake, _ = self.make()
        self.fill(app)
        app.btn_use.invoke()
        self.assertEqual(app.tb.target_info()["label"], "alice@10.0.0.5:22")
        self.assertIn("REMOTE: alice@10.0.0.5:22", app.lbl_target.cget("text"))
        app.select_category("net")
        app.select_op("net.addr")
        app.g_btn_run.invoke()
        self.wait_idle(app)
        self.assertEqual(fake.remote[-1]["prog"], "/usr/bin/ip")
        self.assertIn("Success", app.result.get("1.0", "end"))
        app.select_category("svc")
        app.select_op("svc.action")
        app.g_vars["svc_action"].set("restart")
        app.g_btn_preview.invoke()
        self.assertIn("Runs on: alice@10.0.0.5:22", app.g_box.get("1.0", "end"))
        with mock.patch.object(gui.messagebox, "askyesno", return_value=False) as ask:
            app.g_btn_run.invoke()
            self.assertIn("Runs on: alice@10.0.0.5:22", ask.call_args[0][1])               # the confirmation names the computer
            self.assertIn("sudo systemctl restart nginx", ask.call_args[0][1])
        with mock.patch.object(gui.messagebox, "askyesno", return_value=True):
            app.g_btn_run.invoke()
        self.wait_idle(app)
        self.assertEqual((fake.remote[-1]["root"], fake.remote[-1]["args"]), (True, ["restart", "nginx"]))

    def test_going_back_to_this_computer_takes_effect_at_once(self):
        app, fake, _ = self.make()
        self.fill(app)
        app.btn_use.invoke()
        app.t_kind.set("local")
        app.on_kind()
        self.assertEqual(app.tb.target_info()["kind"], "local")
        self.assertEqual(app.lbl_target.cget("text"), "")

    def test_bad_values_are_explained_and_the_target_does_not_change(self):
        app, fake, _ = self.make()
        for host, port, user in (("-oProxyCommand=id", "22", "alice"), ("h.example", "99999", "alice"), ("h.example", "22", "a b"), ("", "22", "alice"),
                                 ("x;y", "22", "alice")):
            self.fill(app, host, port, user)
            app.btn_use.invoke()
            self.assertIn("✖", app.result.get("1.0", "end"), (host, port, user))
            self.assertEqual(app.tb.target_info()["kind"], "local")
        self.assertEqual(fake.remote, [])

    def test_check_host_key_shows_fingerprints_and_trusts_only_after_you_say_yes(self):
        app, fake, home = self.make()
        self.fill(app)
        kh = os.path.join(home, ".ssh", "known_hosts")
        with mock.patch.object(gui.messagebox, "askyesno", return_value=False) as ask:
            app.btn_hostkey.invoke()
            self.wait_idle(app)
            self.assertIn("SHA256:AbCdEf1234567890", ask.call_args[0][1])
            self.assertIn("10.0.0.5:22", ask.call_args[0][1])
        self.assertFalse(os.path.exists(kh))                                                 # declined: nothing written
        with mock.patch.object(gui.messagebox, "askyesno", return_value=True):
            app.btn_hostkey.invoke()
            self.wait_idle(app)
        self.assertTrue(os.path.exists(kh))
        self.assertIn("is now trusted", app.result.get("1.0", "end"))

    def test_connect_tests_the_connection_and_reports(self):
        app, fake, _ = self.make()
        self.fill(app)
        app.btn_connect.invoke()
        self.wait_idle(app)
        text = app.result.get("1.0", "end")
        self.assertIn("Connected to alice@10.0.0.5:22", text)
        self.assertIn("Administrator operations are available", text)
        app2, _, _ = self.make(fake=FakeSsh(sudo_ok=False))
        self.fill(app2)
        app2.btn_connect.invoke()
        self.wait_idle(app2)
        self.assertIn("NOT available", app2.result.get("1.0", "end"))
        app3, _, _ = self.make(fake=FakeSsh(fail="hostkey"))
        self.fill(app3)
        app3.btn_connect.invoke()
        self.wait_idle(app3)
        self.assertIn("not trusted yet", app3.result.get("1.0", "end"))

    def test_the_bar_survives_a_language_and_theme_change_and_has_no_command_field(self):
        app, _, _ = self.make()
        self.fill(app, "10.0.0.9", "2222", "bob")
        app.btn_use.invoke()
        app.btn_theme.invoke()
        self.pump(app)
        self.assertEqual((app.t_host.get(), app.t_port.get(), app.t_user.get()), ("10.0.0.9", "2222", "bob"))
        app.lang_var.set("ქართული")
        app.lang_box.event_generate("<<ComboboxSelected>>")
        self.pump(app)
        self.assertEqual((app.t_host.get(), app.t_user.get()), ("10.0.0.9", "bob"))
        self.assertIn("დაშორებული: bob@10.0.0.9:2222", app.lbl_target.cget("text"))
        gui.settings.save_lang("en")
        entries = [w for w in walk(app) if w.winfo_class() == "TEntry"]
        self.assertEqual(len(entries), 3)                                                    # host, port, user - and nothing to type a command into

    def test_closing_the_window_closes_the_connection(self):
        app, fake, _ = self.make()
        self.fill(app)
        app.btn_use.invoke()
        folder = app.tb.target.control_dir
        app.select_category("net")
        app.select_op("net.addr")
        app.g_btn_run.invoke()
        self.wait_idle(app)
        folder = app.tb.target.control_dir
        self.assertTrue(os.path.isdir(folder))
        app.quit_app()
        self.assertFalse(os.path.exists(folder))


if __name__ == "__main__":
    unittest.main()
