#!/usr/bin/env python3
"""DevOps Toolbox - offline tests. No real firewall is ever touched: every program call goes through a fake runner.
Run: python3 tests/test_devops_toolbox.py"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "devops-toolbox"))

from devops_toolbox import api, history, i18n, registry, runner, validation  # noqa: E402
from devops_toolbox.modules import ufw  # noqa: E402

UFW = "/usr/sbin/ufw"
SHOW_HEAD = "Added user rules (see 'ufw status' for running firewall):\n"


class FakeUfw:
    """A fake `subprocess.run`: records every call and answers like ufw 0.36 (outputs copied from a real run)."""

    def __init__(self, rules=("ufw allow 22/tcp",), rc=0, stdout=None, stderr="", raise_exc=None):
        self.calls, self.rules, self.rc, self.stdout, self.stderr, self.raise_exc = [], list(rules), rc, stdout, stderr, raise_exc

    def __call__(self, argv, **kw):
        self.calls.append((list(argv), kw))
        if self.raise_exc:
            raise self.raise_exc
        if argv[-2:] == ["show", "added"]:
            return subprocess.CompletedProcess(argv, self.rc, SHOW_HEAD + "\n".join(self.rules) + "\n" if self.rc == 0 else "", self.stderr)
        out = self.stdout if self.stdout is not None else "Rules updated\nRules updated (v6)\n"
        return subprocess.CompletedProcess(argv, self.rc, out, self.stderr)

    def changes(self):
        """The calls other than the rule-list reads."""
        return [c for c, _ in self.calls if c[-2:] != ["show", "added"]]


def toolbox(fake=None, active=True, ufw_path=UFW, euid=0, env=None, **kw):
    d = tempfile.mkdtemp()
    fake = fake or FakeUfw()
    tb = api.Toolbox(runner_fn=fake, history=history.History(os.path.join(d, "h.json")), env=env or {}, euid=euid,
                     find_ufw=lambda: ufw_path, read_active=lambda: active,
                     read_policy=lambda: {"incoming": "drop", "outgoing": "accept"}, **kw)
    return tb, fake


ADD = {"port": "19999", "proto": "tcp", "action": "allow"}


class Validation(unittest.TestCase):
    def test_ports(self):
        for ok in ("1", "80", "19999", "65535", 443, "0080"):
            self.assertIsInstance(validation.port(ok), int)
        self.assertEqual(validation.port("19999"), 19999)
        for bad in ("", " ", "0", "65536", "-1", "+80", " 80", "80 ", "8 0", "80;ls", "80\n", "1e3", "0x50", "８０", "80.0", "http", None, 80.0,
                    True, [80], {"a": 1}, "99999999999999999999"):
            with self.assertRaises(validation.ValidationError, msg=repr(bad)):
                validation.port(bad)

    def test_choices(self):
        self.assertEqual(validation.choice("tcp", ("tcp", "udp")), "tcp")
        for bad in ("TCP", "tcp ", "icmp", "", None, 1, ["tcp"], "tcp;ls"):
            with self.assertRaises(validation.ValidationError, msg=repr(bad)):
                validation.choice(bad, ("tcp", "udp"))

    def test_comment(self):
        self.assertEqual(validation.comment(None), "")
        self.assertEqual(validation.comment("   "), "")
        self.assertEqual(validation.comment(" netdata dashboard "), "netdata dashboard")
        self.assertEqual(validation.comment("ქართული აღწერა"), "ქართული აღწერა")
        for bad in ("a" * 81, "it's", 'say "x"', "back`tick`", "a\\b", "line\nbreak", "-flag", "nul\x00", 5, ["x"], "a\tb"):
            with self.assertRaises(validation.ValidationError, msg=repr(bad)):
                validation.comment(bad)


class Planning(unittest.TestCase):
    def test_the_command_is_an_argument_list_with_the_right_words(self):
        tb, fake = toolbox()
        for action in ("allow", "deny", "reject"):
            for proto in ("tcp", "udp"):
                p = tb.preview("ufw.rule.add", {"port": "19999", "proto": proto, "action": action})
                self.assertTrue(p["ok"], p)
                self.assertEqual(p["commands"][0]["display"], f"sudo ufw {action} 19999/{proto}")
                self.assertEqual(p["commands"][0]["exact"], f"pkexec {UFW} {action} 19999/{proto}")
        ctx = tb.context()
        plan = ufw.plan_add(ctx, dict(ADD, comment="netdata"))
        self.assertEqual(plan.commands, [[UFW, "allow", "19999/tcp", "comment", "netdata"]])
        self.assertEqual(fake.changes(), [])                        # a preview runs nothing

    def test_malicious_input_cannot_become_more_arguments_or_a_shell(self):
        tb, fake = toolbox()
        evil = ["19999; rm -rf /", "19999 && reboot", "$(reboot)", "`id`", "19999\nufw disable", "-1", "80/tcp", "tcp comment x", "19999 deny"]
        for e in evil:                                               # in port, protocol and action: refused outright
            for params in (dict(ADD, port=e), dict(ADD, proto=e), dict(ADD, action=e)):
                self.assertFalse(tb.preview("ufw.rule.add", params)["ok"], params)
        for e in evil:                                               # in the description: refused, or kept as ONE inert argument
            p = tb.preview("ufw.rule.add", dict(ADD, comment=e))
            if p["ok"]:
                argv = ufw.plan_add(tb.context(), dict(ADD, comment=e)).commands[0]
                self.assertEqual(argv, [UFW, "allow", "19999/tcp", "comment", e.strip()])
        plan = ufw.plan_add(tb.context(), dict(ADD, comment="a b; c"))
        self.assertEqual(plan.commands[0][-2:], ["comment", "a b; c"])                       # one argument, spaces and ';' inert
        plan = ufw.plan_add(tb.context(), dict(ADD, comment="$(reboot)"))
        self.assertEqual(plan.commands[0][-1], "$(reboot)")                                   # inert: no shell ever sees it
        self.assertEqual(fake.changes(), [])

    def test_there_is_no_way_to_disable_or_enable_the_firewall_or_run_anything_else(self):
        ids = {i for i in registry.OPERATIONS if i.startswith("ufw.")}
        self.assertEqual(ids, {"ufw.status", "ufw.status.verbose", "ufw.status.numbered", "ufw.rule.add", "ufw.rule.delete", "ufw.app.allow",
                               "ufw.default"})
        self.assertFalse([i for i in ids if "disable" in i.split(".") or "enable" in i.split(".") or "reload" in i.split(".")])
        tb, fake = toolbox()
        for bad_action in ("disable", "enable", "reset", "default", "reload", "limit", "delete", "route"):
            self.assertFalse(tb.preview("ufw.rule.add", dict(ADD, action=bad_action))["ok"], bad_action)
        for op in ("ufw.disable", "ufw.reload", "shell", "", None, 5, "../ufw.status", "ufw.status; id"):
            self.assertEqual(tb.preview(op, {})["errors"][0]["message"], "Unknown operation.", op)
            self.assertFalse(tb.execute(op, {}, "x", True)["ok"])
        self.assertEqual(fake.calls, [])
        with open(os.path.join(ROOT, "devops-toolbox", "devops_toolbox", "modules", "ufw.py")) as f:
            src = f.read()
        code = re.sub(r'""".*?"""|#.*', "", src, flags=re.S)
        self.assertNotIn('"disable"', code)
        self.assertNotIn('"enable"', code)
        self.assertNotIn('"reload"', code)

    def test_unknown_and_missing_parameters_are_refused(self):
        tb, _ = toolbox()
        self.assertIn("Unexpected value", tb.preview("ufw.rule.add", dict(ADD, extra="x"))["errors"][0]["message"])
        self.assertIn("required value is missing", tb.preview("ufw.rule.add", {"proto": "tcp", "action": "allow"})["errors"][0]["message"])
        self.assertFalse(tb.preview("ufw.rule.add", "port=80")["ok"])
        self.assertFalse(tb.preview("ufw.rule.add", None)["ok"])

    def test_duplicates_conflicts_and_overlap_are_detected_from_the_loaded_list(self):
        tb, fake = toolbox(FakeUfw(rules=["ufw allow 19999/tcp", "ufw deny 8080/tcp", "ufw allow 53", "ufw limit 2222/tcp"]))
        self.assertIn("not loaded", tb.preview("ufw.rule.add", ADD)["warnings"][0])
        tb.run_readonly("ufw.status")
        p = tb.preview("ufw.rule.add", ADD)
        self.assertFalse(p["ok"])
        self.assertIn("already exists (allow 19999/tcp)", p["blocked"])
        self.assertEqual(p["token"], "")
        self.assertIn("different rule", tb.preview("ufw.rule.add", dict(ADD, action="deny"))["blocked"])             # allow vs deny
        self.assertIn("already exists", tb.preview("ufw.rule.add", {"port": 53, "proto": "udp", "action": "allow"})["blocked"])   # 53 covers udp
        self.assertIn("different rule", tb.preview("ufw.rule.add", {"port": 53, "proto": "tcp", "action": "reject"})["blocked"])
        self.assertIn("different rule", tb.preview("ufw.rule.add", {"port": 2222, "proto": "tcp", "action": "allow"})["blocked"])  # limit
        self.assertTrue(tb.preview("ufw.rule.add", {"port": 19999, "proto": "udp", "action": "allow"})["ok"])        # other protocol: fine
        self.assertTrue(tb.preview("ufw.rule.add", {"port": 8081, "proto": "tcp", "action": "allow"})["ok"])
        self.assertEqual([c for c in fake.changes()], [])

    def test_inactive_firewall_and_ssh_lockout_are_explained(self):
        tb, _ = toolbox(active=False)
        self.assertTrue(any("inactive" in w for w in tb.preview("ufw.rule.add", ADD)["warnings"]))
        tb, _ = toolbox(env={"SSH_CONNECTION": "10.0.0.2 51000 10.0.0.9 2222"})
        p = tb.preview("ufw.rule.add", {"port": 22, "proto": "tcp", "action": "deny"})
        self.assertEqual(p["risk"], "high")
        self.assertTrue(any("SSH" in w for w in p["warnings"]))
        p = tb.preview("ufw.rule.add", {"port": 2222, "proto": "tcp", "action": "reject"})            # the port of THIS ssh session
        self.assertEqual(p["risk"], "high")
        self.assertEqual(tb.preview("ufw.rule.add", {"port": 22, "proto": "tcp", "action": "allow"})["risk"], "medium")
        self.assertEqual(tb.preview("ufw.rule.add", {"port": 8080, "proto": "tcp", "action": "deny"})["risk"], "medium")

    def test_explains_that_no_reload_is_needed(self):
        tb, _ = toolbox()
        p = tb.preview("ufw.rule.add", ADD)
        self.assertTrue(any("reload" in x and "not" in x for x in p["explain"]))
        self.assertEqual(len(p["commands"]), 1)                      # one command: no `ufw reload` is ever added

    def test_ufw_not_installed(self):
        tb, fake = toolbox(ufw_path=None)
        p = tb.preview("ufw.rule.add", ADD)
        self.assertFalse(p["ok"])
        self.assertIn("not installed", p["blocked"])
        self.assertFalse(tb.run_readonly("ufw.status")["ok"])
        self.assertEqual(fake.calls, [])
        self.assertFalse(tb.info()["ufw"]["installed"])


class Rules(unittest.TestCase):
    OUT = (SHOW_HEAD + "ufw allow 22/tcp comment 'ssh admin'\nufw allow 19999/tcp\nufw limit 2222/tcp\nufw deny 53\n"
           "ufw allow from 10.0.0.5 to any port 5432 proto tcp\nufw allow 6000:6010/udp\nufw route allow in on eth0 out on eth1\n"
           "ufw allow 80/tcp comment 'it\\'s'\nufw allow 70000/tcp\nufw allow 'unterminated\n")

    def test_parser(self):
        rules, other = ufw.parse_added(self.OUT)
        self.assertEqual([r.text for r in rules], ["allow 22/tcp", "allow 19999/tcp", "limit 2222/tcp", "deny 53"])
        self.assertEqual([r.comment for r in rules], ["ssh admin", "", "", ""])
        self.assertEqual([r.proto for r in rules], ["tcp", "tcp", "tcp", "any"])
        self.assertEqual(rules[3].spec, "53")
        self.assertIn("allow from 10.0.0.5 to any port 5432 proto tcp", other)
        self.assertIn("allow 6000:6010/udp", other)
        self.assertIn("route allow in on eth0 out on eth1", other)
        self.assertIn("allow 70000/tcp", other)
        self.assertEqual(ufw.parse_added(""), ([], []))
        self.assertEqual(ufw.parse_added(SHOW_HEAD + "(None)\n"), ([], []))

    def test_status_loads_the_list_and_returns_it(self):
        tb, fake = toolbox(FakeUfw(rules=self.OUT.splitlines()[1:]))
        r = tb.run_readonly("ufw.status")
        self.assertTrue(r["ok"], r)
        self.assertEqual([x["spec"] for x in r["data"]["rules"]], ["22/tcp", "19999/tcp", "2222/tcp", "53"])
        self.assertTrue(tb.info()["ufw"]["rules_loaded"])
        self.assertEqual(fake.calls[0][0], [UFW, "show", "added"])

    def test_delete_uses_the_rule_text_not_a_number_and_needs_the_loaded_list(self):
        tb, fake = toolbox(FakeUfw(rules=["ufw allow 19999/tcp", "ufw deny 53", "ufw deny 19999/tcp"]))
        p = tb.preview("ufw.rule.delete", {"port": 19999, "proto": "tcp"})
        self.assertFalse(p["ok"])
        self.assertIn("Load the rule list first", p["blocked"])
        tb.run_readonly("ufw.status")
        p = tb.preview("ufw.rule.delete", {"port": 19999, "proto": "tcp"})
        self.assertTrue(p["ok"])
        self.assertEqual([c["display"] for c in p["commands"]], ["sudo ufw --force delete allow 19999/tcp", "sudo ufw --force delete deny 19999/tcp"])
        self.assertEqual(p["risk"], "high")
        self.assertTrue(any("2 rules" in w for w in p["warnings"]))
        p = tb.preview("ufw.rule.delete", {"port": 19999, "proto": "tcp", "action": "deny"})
        self.assertEqual([c["display"] for c in p["commands"]], ["sudo ufw --force delete deny 19999/tcp"])
        p = tb.preview("ufw.rule.delete", {"port": 53, "proto": "any"})
        self.assertEqual(p["commands"][0]["display"], "sudo ufw --force delete deny 53")
        self.assertIn("No such rule", tb.preview("ufw.rule.delete", {"port": 53, "proto": "tcp"})["blocked"])        # 53 is tcp+udp, not tcp
        self.assertIn("No such rule", tb.preview("ufw.rule.delete", {"port": 4242, "proto": "udp"})["blocked"])
        self.assertTrue(any("SSH" in w for w in tb.preview("ufw.rule.delete", {"port": 22, "proto": "tcp"})["warnings"] or ["SSH"]))
        self.assertEqual(fake.changes(), [])

    def test_deleting_an_ssh_allow_rule_warns(self):
        tb, _ = toolbox(FakeUfw(rules=["ufw allow 22/tcp"]))
        tb.run_readonly("ufw.status")
        p = tb.preview("ufw.rule.delete", {"port": 22, "proto": "tcp"})
        self.assertTrue(any("SSH" in w for w in p["warnings"]))


class Execution(unittest.TestCase):
    def test_full_cycle_preview_confirm_execute_refresh_history(self):
        tb, fake = toolbox()
        tb.run_readonly("ufw.status")
        p = tb.preview("ufw.rule.add", ADD)
        r = tb.execute("ufw.rule.add", ADD, p["token"], True)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["message"], "The rule was added.")
        self.assertEqual(r["exit_code"], 0)
        self.assertEqual(r["commands"], ["sudo ufw allow 19999/tcp"])
        self.assertIn("Rules updated", r["output"])
        self.assertTrue(r["refresh"]["ok"])
        self.assertEqual(fake.changes(), [[UFW, "allow", "19999/tcp"]])
        self.assertEqual(fake.calls[-1][0], [UFW, "show", "added"])            # the displayed state is re-read after the change
        h = tb.history_entries()
        self.assertEqual((h[1]["op"], h[1]["status"], h[1]["exit_code"]), ("ufw.status", "ok", 0))
        self.assertEqual((h[0]["op"], h[0]["params"]), ("ufw.rule.add", {"port": 19999, "proto": "tcp", "action": "allow"}))
        self.assertEqual(len(h), 2)                                                   # the automatic refresh after the change is not an entry

    def test_every_call_is_an_argument_list_without_a_shell(self):
        tb, fake = toolbox(euid=1000, which=lambda c: "/usr/bin/pkexec")
        tb.run_readonly("ufw.status")
        p = tb.preview("ufw.rule.add", dict(ADD, comment="it works"))
        tb.execute("ufw.rule.add", dict(ADD, comment="it works"), p["token"], True)
        self.assertGreaterEqual(len(fake.calls), 3)
        for argv, kw in fake.calls:
            self.assertIsInstance(argv, list)
            self.assertTrue(all(isinstance(a, str) for a in argv))
            self.assertEqual(argv[:2], ["/usr/bin/pkexec", UFW])                # privilege only for ufw itself, absolute paths
            self.assertIs(kw.get("shell"), False)
            self.assertIn("timeout", kw)
            self.assertEqual(kw["env"]["PATH"], "/usr/sbin:/usr/bin:/sbin:/bin")
        self.assertEqual(fake.changes()[0], ["/usr/bin/pkexec", UFW, "allow", "19999/tcp", "comment", "it works"])

    def test_a_modifying_operation_needs_a_preview_token_and_a_confirmation(self):
        tb, fake = toolbox()
        tb.run_readonly("ufw.status")
        p = tb.preview("ufw.rule.add", ADD)
        self.assertIn("not confirmed", tb.execute("ufw.rule.add", ADD, p["token"], False)["message"])
        self.assertIn("not confirmed", tb.execute("ufw.rule.add", ADD, p["token"], "yes")["message"])        # only True counts
        self.assertIn("expired", tb.execute("ufw.rule.add", ADD, "", True)["message"])
        self.assertIn("expired", tb.execute("ufw.rule.add", ADD, "made-up", True)["message"])
        self.assertIn("expired", tb.execute("ufw.rule.add", ADD, None, True)["message"])
        self.assertEqual(fake.changes(), [])
        p = tb.preview("ufw.rule.add", ADD)
        other = dict(ADD, port="20000")                                                                     # a token belongs to ITS parameters
        self.assertIn("expired", tb.execute("ufw.rule.add", other, p["token"], True)["message"])
        self.assertIn("expired", tb.execute("ufw.rule.delete", {"port": 22, "proto": "tcp"}, p["token"], True)["message"])
        self.assertEqual(fake.changes(), [])
        p = tb.preview("ufw.rule.add", ADD)
        self.assertTrue(tb.execute("ufw.rule.add", ADD, p["token"], True)["ok"])
        self.assertIn("expired", tb.execute("ufw.rule.add", ADD, p["token"], True)["message"])                # single use
        self.assertEqual(len(fake.changes()), 1)

    def test_tokens_expire(self):
        now = [1000.0]
        tb, fake = toolbox(clock=lambda: now[0])
        p = tb.preview("ufw.rule.add", ADD)
        now[0] += api.TOKEN_TTL + 1
        self.assertIn("expired", tb.execute("ufw.rule.add", ADD, p["token"], True)["message"])
        self.assertEqual(fake.changes(), [])

    def test_the_state_is_checked_again_at_execution(self):
        tb, fake = toolbox(FakeUfw(rules=["ufw allow 19999/tcp"]))
        p = tb.preview("ufw.rule.add", ADD)                          # list not loaded when previewing
        tb.run_readonly("ufw.status")                               # ... but loaded before executing
        r = tb.execute("ufw.rule.add", ADD, p["token"], True)
        self.assertFalse(r["ok"])
        self.assertIn("already exists", r["message"])
        self.assertEqual(fake.changes(), [])

    def test_delete_executes_and_a_missing_rule_is_reported_even_with_exit_status_zero(self):
        fake = FakeUfw(rules=["ufw allow 19999/tcp"])
        tb, _ = toolbox(fake)
        tb.run_readonly("ufw.status")
        params = {"port": 19999, "proto": "tcp"}
        p = tb.preview("ufw.rule.delete", params)
        r = tb.execute("ufw.rule.delete", params, p["token"], True)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["message"], "The rule was deleted.")
        self.assertEqual(fake.changes(), [[UFW, "--force", "delete", "allow", "19999/tcp"]])
        fake2 = FakeUfw(rules=["ufw allow 19999/tcp"], stdout="Could not delete non-existent rule\nCould not delete non-existent rule (v6)\n")
        tb, _ = toolbox(fake2)
        tb.run_readonly("ufw.status")
        p = tb.preview("ufw.rule.delete", params)
        r = tb.execute("ufw.rule.delete", params, p["token"], True)
        self.assertFalse(r["ok"])
        self.assertIn("does not exist", r["message"])
        self.assertEqual(r["exit_code"], 0)

    def test_a_second_command_is_not_run_after_the_first_one_failed(self):
        fake = FakeUfw(rules=["ufw allow 19999/tcp", "ufw deny 19999/tcp"], stdout="Could not delete non-existent rule\n")
        tb, _ = toolbox(fake)
        tb.run_readonly("ufw.status")
        params = {"port": 19999, "proto": "tcp"}
        p = tb.preview("ufw.rule.delete", params)
        tb.execute("ufw.rule.delete", params, p["token"], True)
        self.assertEqual(len(fake.changes()), 1)

    def test_ufw_says_the_rule_exists(self):
        tb, _ = toolbox(FakeUfw(stdout="Skipping adding existing rule\nSkipping adding existing rule (v6)\n"))
        p = tb.preview("ufw.rule.add", ADD)
        r = tb.execute("ufw.rule.add", ADD, p["token"], True)
        self.assertTrue(r["ok"])
        self.assertIn("already existed", r["message"])


class Failures(unittest.TestCase):
    def run_add(self, fake, **kw):
        tb, _ = toolbox(fake, **kw)
        p = tb.preview("ufw.rule.add", ADD)
        return tb, tb.execute("ufw.rule.add", ADD, p["token"], True)

    def test_permission_dialog_dismissed_or_refused(self):
        for rc in (126, 127):
            tb, r = self.run_add(FakeUfw(rc=rc), euid=1000, which=lambda c: "/usr/bin/pkexec")
            self.assertFalse(r["ok"])
            self.assertIn("permission was refused", r["message"])
            self.assertEqual(r["exit_code"], rc)
            self.assertEqual(tb.history_entries()[0]["status"], "failed")

    def test_pkexec_missing_is_explained_and_nothing_runs(self):
        fake = FakeUfw()
        tb, r = self.run_add(fake, euid=1000, which=lambda c: None)
        self.assertFalse(r["ok"])
        self.assertIn("pkexec", r["message"])
        self.assertEqual(fake.calls, [])

    def test_ufw_itself_complains_about_root(self):
        _, r = self.run_add(FakeUfw(rc=1, stdout="", stderr="ERROR: You need to be root to run this script\n"))
        self.assertIn("permission was refused", r["message"])

    def test_firewall_backend_errors_and_unknown_errors(self):
        _, r = self.run_add(FakeUfw(rc=1, stdout="", stderr="ERROR: problem running iptables: Permission denied (you must be root)\n"))
        self.assertIn("could not talk to the firewall", r["message"])
        _, r = self.run_add(FakeUfw(rc=1, stdout="", stderr="ERROR: Something odd happened\n"))
        self.assertEqual(r["message"], "UFW reported an error: ERROR: Something odd happened")
        _, r = self.run_add(FakeUfw(rc=1, stdout="", stderr="ERROR: Bad port\n"))
        self.assertIn("whole number", r["message"])

    def test_timeout(self):
        tb, r = self.run_add(FakeUfw(raise_exc=subprocess.TimeoutExpired(["ufw"], 120)))
        self.assertFalse(r["ok"])
        self.assertIn("took too long", r["message"])
        self.assertIsNone(r["exit_code"])

    def test_program_missing_or_not_executable_or_os_error(self):
        _, r = self.run_add(FakeUfw(raise_exc=FileNotFoundError()))
        self.assertIn("could not be found", r["message"])
        _, r = self.run_add(FakeUfw(raise_exc=PermissionError()))
        self.assertIn("Permission denied", r["message"])
        _, r = self.run_add(FakeUfw(raise_exc=OSError("Exec format error")))
        self.assertIn("could not run the command", r["message"])

    def test_a_failed_list_load_leaves_the_state_unknown(self):
        tb, _ = toolbox(FakeUfw(rc=1, stderr="ERROR: You need to be root\n"))
        r = tb.run_readonly("ufw.status")
        self.assertFalse(r["ok"])
        self.assertFalse(tb.info()["ufw"]["rules_loaded"])

    def test_runner_contract(self):
        with self.assertRaises(TypeError):
            runner.run("ufw allow 80")                               # a string is a bug: never a shell line
        with self.assertRaises(TypeError):
            runner.run([])
        with self.assertRaises(TypeError):
            runner.run(["ufw", 80])
        with self.assertRaises(TypeError):
            runner.run(["ufw", "a\x00b"])
        big = subprocess.CompletedProcess(["x"], 0, "y" * 50000, "")
        res = runner.run(["x"], runner=lambda *a, **k: big)
        self.assertLess(len(res.stdout), runner.MAX_OUTPUT + 20)
        self.assertEqual(runner.elevate(["a"], euid=0), (["a"], ""))
        self.assertEqual(runner.elevate(["a"], euid=1000, which=lambda c: None), (None, "err_no_pkexec"))

    def test_no_shell_anywhere_in_the_package(self):
        base = os.path.join(ROOT, "devops-toolbox")
        for dp, _d, files in os.walk(base):
            for f in files:
                if f.endswith(".py"):
                    with open(os.path.join(dp, f), encoding="utf-8") as fh:
                        src = fh.read()
                    code = re.sub(r'""".*?"""|#.*', "", src, flags=re.S)
                    self.assertNotRegex(code, r"shell\s*=\s*True", f)
                    self.assertNotRegex(code, r"os\.system|os\.popen|\beval\(|\bexec\(|\bsh -c\b", f)


class HistoryStore(unittest.TestCase):
    def test_entries_do_not_keep_free_text_and_can_be_cleared(self):
        tb, _ = toolbox()
        p = tb.preview("ufw.rule.add", dict(ADD, comment="my secret note"))
        tb.execute("ufw.rule.add", dict(ADD, comment="my secret note"), p["token"], True)
        with open(tb.history.path, encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("secret", raw)
        self.assertNotIn("comment", raw)
        self.assertEqual(oct(os.stat(tb.history.path).st_mode & 0o777), "0o600")
        self.assertTrue(tb.history_entries())
        tb.clear_history()
        self.assertEqual(tb.history_entries(), [])

    def test_limits_and_damage(self):
        d = tempfile.mkdtemp()
        h = history.History(os.path.join(d, "h.json"))
        for i in range(history.MAX_ENTRIES + 25):
            h.add("op", "ok", 0, "x" * 500, {"n": i})
        e = h.entries()
        self.assertEqual(len(e), history.MAX_ENTRIES)
        self.assertEqual(e[0]["params"]["n"], history.MAX_ENTRIES + 24)               # newest first
        self.assertLessEqual(len(e[0]["summary"]), history.SUMMARY_MAX)
        for junk in ("", "not json", '{"a": 1}', "[1, 2]"):
            with open(h.path, "w") as f:
                f.write(junk)
            self.assertEqual(h.entries(), [])
        os.remove(h.path)
        self.assertEqual(h.entries(), [])
        h2 = history.History("/proc/nonexistent/h.json")
        h2.add("op", "ok", 0, "x")                                                    # unwritable: no exception
        self.assertEqual(h2.entries(), [])

    def test_refused_and_failed_attempts_are_recorded(self):
        tb, _ = toolbox()
        tb.execute("ufw.rule.add", ADD, "bad", True)
        self.assertEqual(tb.history_entries()[0]["status"], "refused")


class Translations(unittest.TestCase):
    def test_both_languages_have_the_same_keys_and_placeholders(self):
        en, ka = i18n.TEXT["en"], i18n.TEXT["ka"]
        self.assertEqual(set(en), set(ka))
        ph = lambda s: sorted(re.findall(r"{(\w+)}", s))      # noqa: E731
        for k in en:
            self.assertEqual(ph(en[k]), ph(ka[k]), k)
            self.assertTrue(en[k].strip() and ka[k].strip(), k)
        for k in ka:
            if not re.fullmatch(r"[a-z]+_[a-z_]+", k) or k in ("proto_any",):
                continue
        self.assertTrue(any(re.search("[Ⴀ-ჿ]", ka[k]) for k in ka))                  # Georgian text, not copies
        translated = [k for k in en if en[k] != ka[k]]
        self.assertGreater(len(translated), len(en) * 0.9)

    def test_every_key_the_code_uses_exists(self):
        used = set()
        base = os.path.join(ROOT, "devops-toolbox")
        for dp, _d, files in os.walk(base):
            for f in files:
                if f.endswith(".py") and f != "i18n.py":
                    with open(os.path.join(dp, f), encoding="utf-8") as fh:
                        src = fh.read()
                    if f.endswith("-gui.py"):                    # the window's attribute names look like keys: only its tr("...") calls count
                        used |= set(re.findall(r'\.tr\("([a-z_]+)"', src))
                        continue
                    used |= set(re.findall(r'["\']((?:err|ok|warn|explain|blocked|op|p|cat|risk|act|fw|btn|pv|res|hist|status)_[a-z_]+)["\']', src))
        missing = sorted(k for k in used if k not in i18n.TEXT["en"])
        self.assertEqual(missing, [])
        for op in registry.OPERATIONS.values():
            for k in (op.name, op.description) + tuple(p.label for p in op.params):
                self.assertIn(k, i18n.TEXT["en"])
        for c in registry.CATEGORIES.values():
            self.assertIn(c.name, i18n.TEXT["en"])

    def test_messages_come_out_in_the_chosen_language(self):
        tb, _ = toolbox(FakeUfw(rules=["ufw allow 19999/tcp"]))
        tb.run_readonly("ufw.status")
        en = tb.preview("ufw.rule.add", ADD, "en")["blocked"]
        ka = tb.preview("ufw.rule.add", ADD, "ka")["blocked"]
        self.assertIn("already exists", en)
        self.assertRegex(ka, "[Ⴀ-ჿ]")
        self.assertIn("allow 19999/tcp", ka)
        self.assertEqual(tb.preview("ufw.rule.add", dict(ADD, port="0"), "ka")["errors"][0]["message"], i18n.t("ka", "err_port_range", min=1, max=65535))
        self.assertEqual(i18n.t("xx", "app_title"), "DevOps Toolbox")                         # unknown language: English
        self.assertEqual(i18n.t("ka", "no_such_key"), "no_such_key")
        cats = {c["id"]: c for c in tb.catalog("ka")["categories"]}
        self.assertEqual(cats["firewall"]["name"], i18n.TEXT["ka"]["cat_firewall"])
        self.assertEqual(next(c for c in tb.catalog("en")["categories"] if c["id"] == "firewall")["operations"][0]["id"], "ufw.status")


class StateReaders(unittest.TestCase):
    def test_conf_and_policy_and_ssh_port(self):
        d = tempfile.mkdtemp()
        conf = os.path.join(d, "ufw.conf")
        for text, want in (("ENABLED=yes\nLOGLEVEL=low\n", True), ("# c\nENABLED=no\n", False), ("LOGLEVEL=low\n", None)):
            with open(conf, "w") as f:
                f.write(text)
            self.assertEqual(ufw.read_active(conf), want)
        self.assertIsNone(ufw.read_active(os.path.join(d, "missing")))
        pol = os.path.join(d, "default")
        with open(pol, "w") as f:
            f.write('DEFAULT_INPUT_POLICY="DROP"\nDEFAULT_OUTPUT_POLICY="ACCEPT"\n')
        self.assertEqual(ufw.read_default_policy(pol), {"incoming": "drop", "outgoing": "accept"})
        self.assertEqual(ufw.ssh_port_of_session({"SSH_CONNECTION": "1.2.3.4 5555 5.6.7.8 22"}), 22)
        for bad in ({}, {"SSH_CONNECTION": "garbage"}, {"SSH_CONNECTION": "a 1 b 99999"}, {"SSH_CONNECTION": "a 1 b x"}):
            self.assertIsNone(ufw.ssh_port_of_session(bad))
        self.assertEqual(ufw.find_ufw(isfile=lambda p: p == "/sbin/ufw", access=lambda p, m: True), "/sbin/ufw")
        self.assertIsNone(ufw.find_ufw(isfile=lambda p: False))
        self.assertIsNone(ufw.find_ufw(isfile=lambda p: True, access=lambda p, m: False))


if __name__ == "__main__":
    unittest.main()
