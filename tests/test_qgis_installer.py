#!/usr/bin/env python3
"""Offline tests of the qgis_installer core package and its command line (no root, no network, no display).

    python3 tests/test_qgis_installer.py

The distribution matrix comes from tests/fixtures/os-release/*; the real apt/qgis.org behaviour is covered by
tests/qgis_container_test.py (run in throw-away containers).
"""
import contextlib
import datetime
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "qgis-installer"))

import qgis_installer as qi  # noqa: E402
qi.simulate._run = lambda *a, **k: (1, "")          # nothing in this file asks the host's package manager: simulations get "cannot tell"
qi.versions._run = lambda *a, **k: (1, "")
from qgis_installer import cli as qcli, i18n, plan, recipes, requirements, runner, system, uninstall  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "os-release")
HAVE_SH = shutil.which("sh") is not None


def fx(name, pm="apt-get", arch="amd64"):
    return qi.detect(os.path.join(FIX, name), pm, arch, tools={}, immutable="none")


def sh_syntax_ok(script):
    """`sh -n` (parse only, nothing runs)."""
    return subprocess.run(["sh", "-n", "-c", script], capture_output=True, text=True).returncode == 0


class Detect(unittest.TestCase):
    # fixture, pm, expected (family, code, supported, ltr_only, apt)
    MATRIX = [
        ("ubuntu-noble", "apt-get", ("ubuntu", "noble", True, True, True)),
        ("ubuntu-questing", "apt-get", ("ubuntu", "questing", True, False, True)),
        ("ubuntu-focal", "apt-get", ("ubuntu", "focal", False, False, True)),
        ("mint-22", "apt-get", ("ubuntu", "noble", True, True, True)),          # Mint maps to its Ubuntu base
        ("debian-bookworm", "apt-get", ("debian", "bookworm", True, True, True)),
        ("debian-trixie", "apt-get", ("debian", "trixie", True, False, True)),
        ("fedora-43", "dnf", (None, "", False, False, False)),
        ("arch", "pacman", (None, "", False, False, False)),
        ("opensuse-tumbleweed", "zypper", (None, "", False, False, False)),
    ]

    def test_matrix(self):
        for name, pm, want in self.MATRIX:
            d = fx(name, pm)
            got = (d["family"], d["code"], d["supported"], d["ltr_only"], d["apt"])
            self.assertEqual(got, want, name)

    def test_missing_os_release_is_not_an_error(self):
        d = qi.detect("/nonexistent/os-release", "", "amd64")
        self.assertEqual((d["name"], d["family"], d["supported"]), ("Linux", None, False))

    def test_method_availability(self):
        noble, fedora, arm = fx("ubuntu-noble"), fx("fedora-43", "dnf"), fx("ubuntu-noble", arch="arm64")
        self.assertEqual([qi.method_available(m, noble) for m in "ABC"], [True, True, True])
        self.assertEqual([qi.method_available(m, fedora) for m in "ABC"], [False, True, True])
        self.assertFalse(qi.method_available("A", arm))                   # the official repository is amd64 only
        self.assertTrue(qi.method_available("B", arm))
        self.assertFalse(qi.method_available("C", fx("arch", pm="")))     # no package manager at all

    def test_channels_follow_the_base(self):
        self.assertEqual(qi.allowed_channels(fx("ubuntu-noble")), qi.LTR_ONLY_CHANNELS)
        self.assertEqual(qi.allowed_channels(fx("debian-trixie")), qi.CHANNELS)
        self.assertEqual(qi.default_channel(fx("ubuntu-noble")), "ltr")
        self.assertEqual(qi.default_channel(fx("debian-trixie")), "latest")

    def test_every_channel_has_a_repository_suffix(self):
        self.assertEqual(set(qi.CHANNELS), set(qi.SUFFIX))
        self.assertTrue(set(qi.LTR_ONLY_CHANNELS) <= set(qi.CHANNELS))

    def test_key_constants_are_well_formed(self):
        self.assertRegex(qi.KEY_FPR, r"^[0-9A-F]{40}$")
        self.assertTrue(qi.KEY_URL.startswith("https://"))
        self.assertTrue(qi.KEYRING.startswith("/etc/apt/keyrings/") and qi.SOURCES.startswith("/etc/apt/sources.list.d/"))


@unittest.skipUnless(HAVE_SH, "needs sh")
class Plans(unittest.TestCase):
    PK = {"grass": True, "python": True, "server": False}

    def test_every_generated_script_parses(self):
        for name, pm, _ in Detect.MATRIX:
            d = fx(name, pm)
            for method in "ABC":
                if not qi.method_available(method, d):
                    continue
                for channel in (qi.allowed_channels(d) if method == "A" else ["ltr"]):
                    for server in (False, True):
                        pk = dict(self.PK, server=server)
                        with mock.patch.object(plan.shutil, "which", return_value=None):
                            steps = qi.build_install(method, d, channel, pk)
                        self.assertTrue(steps, (name, method))
                        for s in steps:
                            self.assertTrue(sh_syntax_ok(s["sh"]), (name, method, channel, s["sh"][:80]))
        self.assertTrue(sh_syntax_ok(qi.steps_script(qi.build_install("A", fx("ubuntu-noble"), "ltr", self.PK))))

    def test_method_a_gate_precedes_the_sources_file(self):
        sh = qi.build_install("A", fx("ubuntu-noble"), "ltr", self.PK)[0]["sh"]
        self.assertIn(qi.KEY_FPR, sh)
        self.assertLess(sh.index("exit 1"), sh.index("cat > " + qi.SOURCES))
        self.assertIn("Suites: noble", sh)
        self.assertIn("qgis.org/ubuntu-ltr", sh)
        self.assertEqual(sh.count("apt-get install -y wget gnupg ca-certificates"), 1)

    def test_package_choices(self):
        d = fx("debian-trixie")
        sh = qi.build_install("A", d, "latest", {"grass": False, "python": False, "server": False})[0]["sh"]
        self.assertIn("apt-get install -y qgis\n", sh)
        self.assertNotIn("qgis-plugin-grass", sh)
        self.assertNotIn("python3-qgis", sh)
        self.assertNotIn("qgis-server", sh)

    def test_flatpak_steps(self):
        d = fx("fedora-43", "dnf")
        with mock.patch.object(plan.shutil, "which", return_value=None):
            steps = qi.build_install("B", d, "ltr", self.PK)
        self.assertEqual([s["root"] for s in steps], [True, False])
        self.assertIn("dnf install -y flatpak", steps[0]["sh"])
        self.assertIn("flatpak install --user -y flathub org.qgis.qgis", steps[1]["sh"])
        with mock.patch.object(plan.shutil, "which", return_value="/usr/bin/flatpak"):
            steps = qi.build_install("B", d, "ltr", self.PK)
        self.assertEqual([s["root"] for s in steps], [False])

    def test_distribution_package_per_manager(self):
        for name, pm, needle in (("ubuntu-noble", "apt-get", "apt-get install -y qgis qgis-plugin-grass"),
                                 ("fedora-43", "dnf", "dnf install -y qgis"),
                                 ("arch", "pacman", "pacman -S --noconfirm qgis"),
                                 ("opensuse-tumbleweed", "zypper", "zypper --non-interactive install qgis")):
            steps = qi.build_install("C", fx(name, pm), "ltr", self.PK)
            self.assertEqual(len(steps), 1)
            self.assertTrue(steps[0]["root"])
            self.assertIn(needle, steps[0]["sh"])
        self.assertEqual(qi.build_install("C", fx("arch", pm=""), "ltr", self.PK), [])

    def test_the_fingerprint_is_read_at_call_time(self):
        with mock.patch.object(system, "KEY_FPR", "0" * 40):
            sh = qi.build_install("A", fx("ubuntu-noble"), "ltr", self.PK)[0]["sh"]
        self.assertIn("0" * 40, sh)
        self.assertNotIn(qi.KEY_FPR, sh)


class Removal(unittest.TestCase):
    HOME = os.path.expanduser("~")

    def _steps(self, items, purge=False, auto=False):
        return qi.build_remove_steps(items, purge, auto, fx("ubuntu-noble"))

    def test_only_the_known_user_folders_can_be_deleted(self):
        items = [{"kind": "data", "path": p, "sz": "1"} for p in (
            self.HOME + "/.local/share/QGIS", self.HOME + "/Documents", "/etc", self.HOME, "/",
            self.HOME + "/.local/share/QGIS/../../Documents", "~/.config/QGIS")]
        text = " ".join(s["sh"] for s in self._steps(items))
        self.assertIn(".local/share/QGIS", text)
        for bad in ("Documents", "rm -rf -- /etc", "rm -rf -- /\n"):
            self.assertNotIn(bad, text)
        self.assertEqual(text.count("rm -rf"), 1)

    @unittest.skipUnless(HAVE_SH, "needs sh")
    def test_awkward_file_names_are_quoted(self):
        nasty = "/etc/apt/sources.list.d/q gis; rm -rf x $(id).sources"
        steps = self._steps([{"kind": "repo", "files": [nasty], "c": "", "root": True},
                             {"kind": "apt", "pkgs": ["qgis", "python3-qgis; evil"], "v": "1", "o": "", "root": True}])
        for s in steps:
            self.assertTrue(sh_syntax_ok(s["sh"]))
        sh = steps[0]["sh"]
        self.assertIn("'" + nasty + "'", sh)                       # one quoted word
        self.assertIn("'python3-qgis; evil'", sh)

    def test_one_root_step_so_the_password_is_asked_once(self):
        items = [{"kind": "apt", "pkgs": ["qgis"], "v": "1", "o": "x", "root": True},
                 {"kind": "repo", "files": ["/etc/apt/sources.list.d/qgis.sources"], "c": "", "root": True},
                 {"kind": "snap", "v": "1", "root": True},
                 {"kind": "flatpak", "i": "system", "v": "1", "root": True},
                 {"kind": "flatpak", "i": "user", "v": "1", "root": False}]
        steps = self._steps(items, purge=True, auto=True)
        self.assertEqual([s["root"] for s in steps], [True, False])
        root = steps[0]["sh"]
        for needle in ("apt-get purge -y qgis", "rm -f /etc/apt/sources.list.d/qgis.sources", "snap remove qgis",
                       "flatpak uninstall --system -y org.qgis.qgis", "apt-get autoremove -y", "apt-get update"):
            self.assertIn(needle, root)
        self.assertIn("flatpak uninstall --user -y org.qgis.qgis", steps[1]["sh"])

    def test_remove_not_purge_by_default(self):
        steps = self._steps([{"kind": "apt", "pkgs": ["qgis"], "v": "1", "o": "", "root": True}])
        self.assertIn("apt-get remove -y qgis", steps[0]["sh"])
        self.assertNotIn("autoremove", steps[0]["sh"])

    def test_nothing_selected_means_no_steps(self):
        self.assertEqual(self._steps([]), [])

    def test_default_selection_never_includes_user_data(self):
        items = [{"kind": "apt"}, {"kind": "data"}, {"kind": "repo"}]
        self.assertEqual([i["kind"] for i in uninstall.default_selection(items)], ["apt", "repo"])


class Texts(unittest.TestCase):
    FIELD = re.compile(r"\{(\w+)\}")

    def test_both_languages_have_the_same_keys_and_placeholders(self):
        en, ka = i18n.STR["en"], i18n.STR["ka"]
        self.assertEqual(set(en), set(ka), set(en) ^ set(ka))
        for k in en:
            self.assertEqual(set(self.FIELD.findall(en[k])), set(self.FIELD.findall(ka[k])), k)

    def test_every_format_call_in_the_package_has_its_text(self):
        for k in i18n.STR["en"]:
            fields = set(self.FIELD.findall(i18n.STR["en"][k]))
            if fields and k != "guide":
                kw = {f: "x" for f in fields}
                self.assertTrue(i18n.t(k, "en", **kw) and i18n.t(k, "ka", **kw), k)

    def test_unknown_language_falls_back_to_english(self):
        self.assertEqual(i18n.t("run", "xx"), i18n.t("run", "en"))

    def test_the_guide_names_the_real_fingerprint_and_paths(self):
        for lang in ("en", "ka"):
            g = i18n.STR[lang]["guide"]
            self.assertIn(qi.KEY_FPR, g)
            self.assertIn(qi.KEYRING, g)
            self.assertIn(qi.SOURCES, g)

    def test_labels_and_preview_in_both_languages(self):
        item = {"kind": "apt", "pkgs": ["qgis", "qgis-common"], "v": "3.44", "o": "", "root": True}
        self.assertIn("qgis 3.44", i18n.label_for(item, "en"))
        self.assertNotEqual(i18n.label_for(item, "en"), i18n.label_for(item, "ka"))
        steps = [{"root": True, "sh": "echo hi\n"}, {"root": False, "sh": "echo you\n"}]
        text_en, text_ka = i18n.steps_text(steps, "en"), i18n.steps_text(steps, "ka")
        self.assertIn("administrator", text_en)
        self.assertIn("echo hi", text_ka)
        self.assertNotEqual(text_en, text_ka)


@unittest.skipUnless(HAVE_SH, "needs sh")
class Runner(unittest.TestCase):
    def test_success_collects_output_in_order(self):
        lines = []
        rc, failed = runner.run_steps([{"root": False, "sh": "echo one; echo two >&2\n"},
                                       {"root": False, "sh": "echo three\n"}], on_line=lines.append)
        self.assertEqual((rc, failed), (0, None))
        self.assertEqual([x.strip() for x in lines], ["one", "two", "three"])

    def test_stops_at_the_first_failure(self):
        lines = []
        steps = [{"root": False, "sh": "echo a\nexit 3\n"}, {"root": False, "sh": "echo never\n"}]
        rc, failed = runner.run_steps(steps, on_line=lines.append)
        self.assertEqual(rc, 3)
        self.assertIs(failed, steps[0])
        self.assertNotIn("never", "".join(lines))

    def test_root_steps_go_through_the_elevator_unless_already_root(self):
        step = {"root": True, "sh": "echo ok\n"}
        rc, failed = runner.run_steps([step], elevate=("no-such-elevator-xyz",), geteuid=lambda: 1000)
        self.assertEqual(rc, 127)
        self.assertTrue(runner.needs_elevation_fallback(rc, failed))
        rc, failed = runner.run_steps([step], elevate=("no-such-elevator-xyz",), geteuid=lambda: 0)
        self.assertEqual((rc, failed), (0, None))
        self.assertFalse(runner.needs_elevation_fallback(1, step))
        self.assertFalse(runner.needs_elevation_fallback(127, {"root": False, "sh": ""}))

    def test_elevator_choice(self):
        both = lambda name: "/usr/bin/" + name  # noqa: E731
        self.assertEqual(runner.default_elevator({"DISPLAY": ":0"}, both), ["pkexec"])
        self.assertEqual(runner.default_elevator({"WAYLAND_DISPLAY": "wayland-0"}, both), ["pkexec"])
        self.assertEqual(runner.default_elevator({}, both), ["sudo"])               # a terminal: sudo
        self.assertEqual(runner.default_elevator({"DISPLAY": ":0"}, lambda n: "/x/sudo" if n == "sudo" else None), ["sudo"])
        self.assertEqual(runner.default_elevator({}, lambda n: None), ["pkexec"])

    @unittest.skipIf(os.name != "posix", "file modes")
    def test_fallback_script_is_private_and_holds_only_root_steps(self):
        with tempfile.TemporaryDirectory() as d:
            path = runner.write_root_script([{"root": True, "sh": "echo root\n"}, {"root": False, "sh": "echo user\n"}], d)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o700)
            with open(path) as f:
                text = f.read()
            self.assertIn("echo root", text)
            self.assertNotIn("echo user", text)
        p1 = runner.write_root_script([{"root": True, "sh": "x"}])
        p2 = runner.write_root_script([{"root": True, "sh": "x"}])
        self.assertNotEqual(os.path.dirname(p1), os.path.dirname(p2))               # a fresh private folder each time
        shutil.rmtree(os.path.dirname(p1))
        shutil.rmtree(os.path.dirname(p2))


class Cli(unittest.TestCase):
    NOBLE = ["--os-release", os.path.join(FIX, "ubuntu-noble"), "--pm", "apt-get", "--arch", "amd64", "--tools", ""]
    FEDORA = ["--os-release", os.path.join(FIX, "fedora-43"), "--pm", "dnf", "--arch", "amd64", "--tools", ""]

    def call(self, *argv, stdin_tty=False):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch("sys.stdin.isatty", return_value=stdin_tty):
            try:
                rc = qcli.main(list(argv))
            except SystemExit as e:           # argparse errors
                rc = e.code
        return rc, out.getvalue(), err.getvalue()

    def test_info_json(self):
        rc, out, _ = self.call("--lang", "en", "--json", *self.NOBLE, "info")
        doc = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(doc["schema"], qcli.SCHEMA)
        self.assertEqual({m: doc["methods"][m] for m in "ABC"}, {"A": True, "B": True, "C": True})
        self.assertEqual(sorted(doc["methods"]), ["A", "B", "C"])
        self.assertEqual(doc["channels"], qi.LTR_ONLY_CHANNELS)
        self.assertEqual(doc["default_channel"], "ltr")
        rc, out, _ = self.call("--json", *self.FEDORA, "info")
        doc = json.loads(out)
        self.assertEqual((doc["methods"]["A"], doc["channels"]), (False, []))

    def test_info_text_in_georgian(self):
        rc, out, _ = self.call("--lang", "ka", *self.NOBLE, "info")
        self.assertEqual(rc, 0)
        self.assertIn(i18n.STR["ka"]["st_ltr"], out)

    def test_plan_json_and_script(self):
        rc, out, _ = self.call("--json", *self.NOBLE, "plan", "--method", "A", "--channel", "ltr")
        doc = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertTrue(doc["steps"][0]["root"])
        self.assertIn(qi.KEY_FPR, doc["steps"][0]["sh"])
        rc, out, _ = self.call(*self.NOBLE, "plan", "--script")
        self.assertTrue(out.startswith("#!/bin/sh"))

    def test_plan_defaults_to_the_official_repository_when_possible(self):
        rc, out, _ = self.call("--json", *self.NOBLE, "plan")
        self.assertIn("qgis.org/ubuntu-ltr", json.loads(out)["steps"][0]["sh"])
        rc, out, _ = self.call("--json", *self.FEDORA, "plan")          # Fedora: its own package (was: Flatpak)
        self.assertIn("dnf install -y qgis python3-qgis qgis-grass", "".join(s["sh"] for s in json.loads(out)["steps"]))

    def test_impossible_requests_exit_2_and_say_why(self):
        rc, _, err = self.call(*self.FEDORA, "plan", "--method", "A")
        self.assertEqual(rc, 2)
        self.assertIn("not available", err)
        rc, _, err = self.call(*self.NOBLE, "plan", "--method", "A", "--channel", "latest")
        self.assertEqual(rc, 2)
        self.assertIn("allowed: ltr, nightly-ltr", err)
        self.assertEqual(self.call("plan", "--method", "Z")[0], 2)      # argparse rejects it

    def test_install_needs_confirmation(self):
        with mock.patch.object(runner, "run_steps", side_effect=AssertionError("must not run")):
            rc, _, err = self.call(*self.NOBLE, "install", "--method", "C")          # no tty, no --yes
            self.assertEqual(rc, 3)
            self.assertIn("--yes", err)
            rc, out, _ = self.call(*self.NOBLE, "install", "--method", "C", "--dry-run")
            self.assertEqual(rc, 0)
            self.assertIn("apt-get install -y qgis", out)
            with mock.patch("builtins.input", return_value="n"):
                rc, _, _ = self.call(*self.NOBLE, "install", "--method", "C", stdin_tty=True)
            self.assertEqual(rc, 3)

    def test_install_runs_after_yes_and_reports_failures(self):
        with mock.patch.object(runner, "run_steps", return_value=(0, None)) as run:
            rc, out, _ = self.call("--lang", "en", *self.NOBLE, "install", "--method", "C", "--yes")
        self.assertEqual(rc, 0)
        self.assertEqual(len(run.call_args[0][0]), 1)
        self.assertIn(i18n.STR["en"]["done_ok"], out)
        step = {"root": True, "sh": "x"}
        with mock.patch.object(runner, "run_steps", return_value=(5, step)):
            rc, _, err = self.call("--lang", "en", *self.NOBLE, "install", "--method", "C", "--yes")
        self.assertEqual(rc, 5)
        self.assertIn("exit code 5", err)
        with mock.patch.object(runner, "run_steps", return_value=(127, step)), \
                mock.patch.object(runner, "write_root_script", return_value="/tmp/x/qgis-installer-root.sh"):
            rc, _, err = self.call("--lang", "en", *self.NOBLE, "install", "--method", "C", "--yes")
        self.assertEqual(rc, 127)
        self.assertIn("sudo sh /tmp/x/qgis-installer-root.sh", err)

    ITEMS = [{"kind": "apt", "pkgs": ["qgis"], "v": "3.44", "o": "qgis.org", "root": True},
             {"kind": "repo", "files": ["/etc/apt/sources.list.d/qgis.sources"], "c": "", "root": True},
             {"kind": "data", "path": os.path.expanduser("~/.local/share/QGIS"), "sz": "9 MB", "root": False}]

    def test_list(self):
        with mock.patch.object(uninstall, "find_installs", return_value=self.ITEMS):
            rc, out, _ = self.call("--json", *self.NOBLE, "list")
            self.assertEqual([i["kind"] for i in json.loads(out)["items"]], ["apt", "repo", "data"])
            rc, out, _ = self.call("--lang", "en", *self.NOBLE, "list")
            self.assertEqual(out.count("- "), 3)
        with mock.patch.object(uninstall, "find_installs", return_value=[]):
            rc, out, _ = self.call("--lang", "en", *self.NOBLE, "list")
            self.assertIn(i18n.STR["en"]["rm_none"], out)

    def test_uninstall_keeps_user_data_unless_asked(self):
        with mock.patch.object(uninstall, "find_installs", return_value=self.ITEMS), \
                mock.patch.object(runner, "run_steps", side_effect=AssertionError("must not run")):
            rc, out, _ = self.call("--json", *self.NOBLE, "uninstall", "--dry-run")
            sh = "".join(s["sh"] for s in json.loads(out)["steps"])
            self.assertEqual(rc, 0)
            self.assertIn("apt-get remove -y qgis", sh)
            self.assertNotIn("rm -rf", sh)
            rc, out, _ = self.call("--json", *self.NOBLE, "uninstall", "--kinds", "data", "--dry-run")
            self.assertIn("rm -rf -- ", "".join(s["sh"] for s in json.loads(out)["steps"]))
            rc, out, _ = self.call("--json", *self.NOBLE, "uninstall", "--purge", "--no-autoremove", "--dry-run")
            sh = "".join(s["sh"] for s in json.loads(out)["steps"])
            self.assertIn("apt-get purge -y qgis", sh)
            self.assertNotIn("autoremove", sh)
            rc, _, err = self.call(*self.NOBLE, "uninstall", "--kinds", "everything", "--dry-run")
            self.assertEqual(rc, 2)
            self.assertIn("unknown kind", err)
            rc, _, _ = self.call(*self.NOBLE, "uninstall")                           # not confirmed
            self.assertEqual(rc, 3)

    def test_uninstall_with_nothing_found(self):
        with mock.patch.object(uninstall, "find_installs", return_value=[]):
            rc, out, _ = self.call("--lang", "en", *self.NOBLE, "uninstall", "--yes")
        self.assertEqual(rc, 0)
        self.assertIn(i18n.STR["en"]["rm_nothing"], out)

    def test_module_entry_point_runs(self):
        p = subprocess.run([sys.executable, "-m", "qgis_installer", "--lang", "en", "--json", *self.NOBLE, "info"],
                           capture_output=True, text=True, cwd=os.path.join(ROOT, "qgis-installer"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["system"]["code"], "noble")


class Requirements(unittest.TestCase):
    def test_table_is_consistent(self):
        for rid, spec in requirements.REQ.items():
            self.assertIn(spec["kind"], ("module", "tool"), rid)
            self.assertTrue(spec.get("module") if spec["kind"] == "module" else spec.get("tools"), rid)
            self.assertTrue(spec["label"]["en"] and spec["label"]["ka"], rid)
            self.assertTrue(set(spec["pkgs"]) <= set(requirements.INSTALL_CMD), rid)
            for names in spec["pkgs"].values():
                self.assertTrue(names is None or (isinstance(names, list) and all(isinstance(n, str) and n for n in names)), rid)
        for plugin, reqs in requirements.PLUGIN_REQUIREMENTS.items():
            for rid, optional in reqs:
                self.assertIn(rid, requirements.REQ, plugin)
                self.assertIsInstance(optional, bool)

    def test_is_present_for_modules_and_tools(self):
        self.assertTrue(requirements.is_present("psycopg2", find_spec=lambda m: object()))
        self.assertFalse(requirements.is_present("psycopg2", find_spec=lambda m: None))
        self.assertFalse(requirements.is_present("psycopg2", find_spec=mock.Mock(side_effect=ImportError)))
        every = lambda t: "/usr/bin/" + t  # noqa: E731
        self.assertTrue(requirements.is_present("pgclient", which=every))
        self.assertFalse(requirements.is_present("pgclient", which=lambda t: None if t == "psql" else "/x"))   # all must exist

    def test_status_for_a_plugin(self):
        rows = requirements.status("postgis_manager", which=lambda t: None, find_spec=lambda m: None)
        self.assertEqual([(r["id"], r["optional"], r["present"]) for r in rows],
                         [("psycopg2", False, False), ("pgclient", False, False), ("geopandas", True, False)])
        self.assertEqual(requirements.status("calculate_geometry"), [])

    def test_packages_resolve_per_package_manager(self):
        self.assertEqual(requirements.packages_for(["psycopg2", "pgclient"], "apt-get"),
                         (["python3-psycopg2", "postgresql-client"], []))
        self.assertEqual(requirements.packages_for(["psycopg2", "geopandas"], "zypper", pyver="313"),
                         (["python313-psycopg2", "python313-geopandas"], []))
        pk, manual = requirements.packages_for(["saga", "windninja", "grass"], "dnf")
        self.assertEqual((pk, manual), (["grass"], ["saga", "windninja"]))
        self.assertEqual(requirements.packages_for(["psycopg2"], "unknown-pm"), ([], ["psycopg2"]))
        self.assertRegex(requirements.python_tag(), r"^3\d+$")

    @unittest.skipUnless(HAVE_SH, "needs sh")
    def test_install_steps(self):
        steps, manual = requirements.install_steps(["psycopg2", "windninja", "pgclient"], "pacman")
        self.assertEqual(manual, ["windninja"])
        self.assertEqual([s["root"] for s in steps], [True])
        self.assertIn("pacman -S --noconfirm python-psycopg2 postgresql", steps[0]["sh"])
        self.assertTrue(sh_syntax_ok(steps[0]["sh"]))
        self.assertEqual(requirements.install_steps(["windninja"], "apt-get"), ([], ["windninja"]))
        self.assertEqual(requirements.install_steps(["psycopg2"], "emerge"), ([], ["psycopg2"]))
        self.assertEqual(requirements.install_steps([], "apt-get"), ([], []))

    def test_runtime_detection(self):
        no = lambda p: False  # noqa: E731
        self.assertEqual(requirements.qgis_runtime({}, no), "native")
        self.assertEqual(requirements.qgis_runtime({"FLATPAK_ID": "org.qgis.qgis"}, no), "flatpak")
        self.assertEqual(requirements.qgis_runtime({}, lambda p: p == "/.flatpak-info"), "flatpak")
        self.assertEqual(requirements.qgis_runtime({"SNAP": "/snap/qgis/1"}, no), "snap")


class RequirementsCli(unittest.TestCase):
    NOBLE = Cli.NOBLE
    call = Cli.call

    def present(self, missing):
        return lambda rid, **kw: rid not in missing

    def test_check_json_and_text(self):
        with mock.patch.object(requirements, "is_present", self.present({"pgclient"})):
            rc, out, _ = self.call("--json", *self.NOBLE, "requirements", "check", "--plugin", "postgis_manager")
            doc = json.loads(out)
            rows = {r["id"]: r for r in doc["plugins"]["postgis_manager"]}
            self.assertEqual(rc, 0)
            self.assertEqual(doc["package_manager"], "apt-get")
            self.assertFalse(rows["pgclient"]["present"])
            self.assertEqual(rows["pgclient"]["packages"], ["postgresql-client"])
            self.assertTrue(rows["psycopg2"]["present"])
            rc, out, _ = self.call("--lang", "en", *self.NOBLE, "requirements", "check")
            self.assertIn("[missing]", out)
            self.assertIn("-> postgresql-client", out)
            for plugin in requirements.PLUGIN_REQUIREMENTS:
                self.assertIn(plugin, out)

    def test_check_names_what_has_no_package(self):
        with mock.patch.object(requirements, "is_present", self.present({"windninja"})):
            rc, out, _ = self.call("--lang", "en", *self.NOBLE, "requirements", "check", "--plugin", "geoeco")
        self.assertIn("no package for your system: install WindNinja", out)

    def test_install_dry_run_and_filters(self):
        with mock.patch.object(requirements, "is_present", self.present({"pgclient", "geopandas"})), \
                mock.patch.object(runner, "run_steps", side_effect=AssertionError("must not run")):
            rc, out, _ = self.call("--json", *self.NOBLE, "requirements", "install", "--plugin", "postgis_manager", "--dry-run")
            sh = json.loads(out)["steps"][0]["sh"]
            self.assertEqual(rc, 0)
            self.assertIn("apt-get install -y postgresql-client", sh)
            self.assertNotIn("geopandas", sh)                     # optional: only with --optional
            rc, out, _ = self.call("--json", *self.NOBLE, "requirements", "install", "--plugin", "postgis_manager",
                                   "--optional", "--dry-run")
            self.assertIn("python3-geopandas", json.loads(out)["steps"][0]["sh"])
            rc, _, err = self.call(*self.NOBLE, "requirements", "install", "--plugin", "postgis_manager")  # no tty, no --yes
            self.assertEqual(rc, 3)

    def test_install_when_nothing_is_missing(self):
        with mock.patch.object(requirements, "is_present", self.present(set())), \
                mock.patch.object(runner, "run_steps", side_effect=AssertionError("must not run")):
            rc, out, _ = self.call("--lang", "en", *self.NOBLE, "requirements", "install", "--plugin", "postgis_manager", "--yes")
        self.assertEqual(rc, 0)
        self.assertIn(i18n.STR["en"]["rq_all_ok"], out)
        rc, out, _ = self.call("--lang", "en", *self.NOBLE, "requirements", "install", "--plugin", "calculate_geometry", "--yes")
        self.assertEqual(rc, 2)                                   # unknown to the table: say so
        self.assertIn("Unknown plugin", self.call("--lang", "en", *self.NOBLE, "requirements", "check", "--plugin", "x")[2])

    def test_install_runs_after_yes_and_manual_only_is_refused(self):
        with mock.patch.object(requirements, "is_present", self.present({"saga", "grass", "windninja"})):
            with mock.patch.object(runner, "run_steps", return_value=(0, None)) as run:
                rc, out, _ = self.call("--lang", "en", *self.NOBLE, "requirements", "install", "--plugin", "geoeco", "--yes")
            self.assertEqual(rc, 0)
            self.assertIn("apt-get install -y saga grass", run.call_args[0][0][0]["sh"])
            fedora = ["--os-release", os.path.join(FIX, "fedora-43"), "--pm", "dnf", "--arch", "amd64"]
            with mock.patch.object(runner, "run_steps", return_value=(0, None)) as run:
                rc, _, err = self.call("--lang", "en", *fedora, "requirements", "install", "--plugin", "geoeco",
                                       "--optional", "--yes")
            self.assertEqual(rc, 0)                               # grass has a Fedora package; saga/windninja are manual
            self.assertEqual(run.call_args[0][0][0]["sh"], "set -eu\ndnf install -y grass\n")
            self.assertIn("install SAGA GIS", err)
        with mock.patch.object(requirements, "is_present", self.present({"windninja"})), \
                mock.patch.object(runner, "run_steps", side_effect=AssertionError("must not run")):
            rc, _, err = self.call("--lang", "en", *self.NOBLE, "requirements", "install", "--plugin", "geoeco",
                                   "--optional", "--yes")
        self.assertEqual(rc, 2)
        self.assertIn("install WindNinja", err)


# --------------------------------------------------------------------------- recipes (the installation guide, Linux)
def fxt(name, pm, tools=(), immutable=None, arch="amd64"):
    """A system description with exactly these tools present and no look at the real machine."""
    return qi.detect(os.path.join(FIX, name), pm, arch, tools={t: True for t in tools},
                     immutable=immutable or "none", exists=lambda p: False)


def applying(sysinfo):
    return {a["id"] for a in recipes.available(sysinfo) if a["applies"]}


class MoreDistros(unittest.TestCase):
    def test_classification(self):
        for name, pm, want in (("ubuntu-noble", "apt-get", "ubuntu"), ("debian-trixie", "apt-get", "debian"),
                               ("mint-22", "apt-get", "ubuntu"), ("fedora-43", "dnf", "fedora"),
                               ("fedora-silverblue", "dnf", "fedora"), ("almalinux-9", "dnf", "rhel"),
                               ("mageia-9", "", "mageia"), ("opensuse-tumbleweed", "zypper", "opensuse"),
                               ("opensuse-microos", "zypper", "opensuse"), ("arch", "pacman", "arch"),
                               ("manjaro", "pacman", "arch"), ("nixos", "", "nixos"), ("slackware", "", "slackware")):
            self.assertEqual(fxt(name, pm)["distro"], want, name)

    def test_immutable_detection(self):
        ostree = lambda p: p == "/run/ostree-booted"  # noqa: E731
        d = qi.detect(os.path.join(FIX, "fedora-silverblue"), "dnf", "amd64", tools={}, exists=ostree)
        self.assertEqual(d["immutable"], "ostree")
        d = qi.detect(os.path.join(FIX, "fedora-43"), "dnf", "amd64", tools={}, exists=lambda p: False)
        self.assertIsNone(d["immutable"])
        d = qi.detect(os.path.join(FIX, "opensuse-microos"), "zypper", "amd64", tools={"transactional-update": True},
                      exists=lambda p: False)
        self.assertEqual(d["immutable"], "transactional")
        d = qi.detect(os.path.join(FIX, "opensuse-microos"), "zypper", "amd64", tools={}, exists=lambda p: False)
        self.assertIsNone(d["immutable"])                   # no transactional-update: a normal system as far as we can tell
        d = qi.detect(os.path.join(FIX, "opensuse-tumbleweed"), "zypper", "amd64", tools={"transactional-update": True},
                      exists=lambda p: False)
        self.assertIsNone(d["immutable"])

    def test_tools_are_booleans_for_every_known_tool(self):
        d = qi.detect(os.path.join(FIX, "arch"), "pacman", "amd64")
        self.assertEqual(set(d["tools"]), set(system.TOOLS))
        self.assertTrue(all(isinstance(v, bool) for v in d["tools"].values()))
        self.assertEqual(qi.detect(os.path.join(FIX, "arch"), "pacman", "amd64", tools={"yay": 1})["tools"]["yay"], True)

    def test_urpmi_is_found_when_no_other_manager_is(self):
        self.assertEqual(qi.detect(os.path.join(FIX, "mageia-9"), "", "amd64", tools={"urpmi": True})["pm"], "urpmi")


class Recipes(unittest.TestCase):
    def test_which_recipes_apply_where(self):
        cases = [
            (fxt("ubuntu-noble", "apt-get"), {"apt-official", "apt-distro", "flatpak"}),
            (fxt("debian-trixie", "apt-get"), {"apt-official", "apt-distro", "flatpak"}),
            (fxt("ubuntu-focal", "apt-get"), {"apt-distro", "flatpak"}),                       # not in the guide's table
            (fxt("ubuntu-noble", "apt-get", arch="arm64"), {"apt-distro", "flatpak"}),
            (fxt("fedora-43", "dnf"), {"dnf-fedora", "flatpak"}),
            (fxt("fedora-silverblue", "dnf", ["rpm-ostree"], "ostree"), {"rpm-ostree-fedora", "flatpak"}),
            (fxt("almalinux-9", "dnf"), {"flatpak"}),                                          # RHEL clones: not in the guide
            (fxt("opensuse-tumbleweed", "zypper"), {"zypper-opensuse", "flatpak"}),
            (fxt("opensuse-microos", "zypper", ["transactional-update"], "transactional"), {"flatpak"}),
            (fxt("arch", "pacman"), {"pacman-arch", "flatpak"}),
            (fxt("manjaro", "pacman", ["yay"]), {"pacman-arch", "aur-helper", "flatpak"}),
            (fxt("mageia-9", "", ["urpmi"]), {"urpmi-mageia"}),
            (fxt("nixos", "", ["flatpak"]), {"nix-manual", "flatpak"}),
            (fxt("slackware", ""), {"slackware-manual"}),
            (fxt("fedora-43", "dnf", ["distrobox", "toolbox", "spack"]), {"dnf-fedora", "flatpak", "distrobox", "toolbx", "spack"}),
        ]
        for d, want in cases:
            self.assertEqual(applying(d), want, d["name"])

    def test_every_recipe_has_texts_and_a_known_verification_level(self):
        for rid, r in recipes.RECIPES.items():
            for lang in ("en", "ka"):
                self.assertIn("rc_" + rid, i18n.STR[lang])
            self.assertIn("vf_" + r["verified"], i18n.STR["en"])
            self.assertIn(r["kind"], ("run", "manual"))
        systems = [fxt(n, pm, ["flatpak", "distrobox", "toolbox", "spack", "yay", "urpmi", "rpm-ostree", "transactional-update"])
                   for n, pm in (("ubuntu-focal", "apt-get"), ("fedora-43", "dnf"), ("opensuse-tumbleweed", "zypper"),
                                 ("arch", "pacman"), ("mageia-9", "urpmi"), ("nixos", ""), ("slackware", ""))]
        reasons = set()
        for d in systems:
            for a in recipes.available(d):
                if a["reason"]:
                    reasons.add(a["reason"])
        for key in reasons:
            self.assertIn("rcn_" + key, i18n.STR["en"], key)

    def test_notes_and_manual_titles_have_texts(self):
        seen_notes, seen_titles = set(), set()
        full = {"grass": True, "python": True, "server": True}
        for rid in recipes.RECIPES:
            for d in (fxt("ubuntu-noble", "apt-get", ["flatpak"]), fxt("fedora-43", "dnf", ["distrobox", "toolbox", "spack"]),
                      fxt("fedora-silverblue", "dnf", ["rpm-ostree"], "ostree"), fxt("opensuse-tumbleweed", "zypper"),
                      fxt("arch", "pacman", ["yay"]), fxt("mageia-9", "", ["urpmi"]), fxt("nixos", ""), fxt("slackware", "")):
                if recipes.applicability(rid, d)[0]:
                    for opts in (dict(full), dict(full, branch="lts"), dict(full, channel="ltr")):
                        try:
                            result = recipes.make_plan(rid, d, opts)
                        except ValueError:
                            continue
                        seen_notes |= set(result["notes"])
                        seen_titles |= {m["title"] for m in result["manual"]}
        self.assertTrue(seen_notes and seen_titles)
        for k in seen_notes:
            for lang in ("en", "ka"):
                self.assertIn("rcw_" + k, i18n.STR[lang], k)
        for k in seen_titles:
            self.assertIn("rcm_" + k, i18n.STR["en"], k)

    def test_unknown_or_inapplicable_recipes_raise(self):
        with self.assertRaises(ValueError):
            recipes.make_plan("nope", fxt("ubuntu-noble", "apt-get"))
        with self.assertRaises(ValueError):
            recipes.make_plan("dnf-fedora", fxt("ubuntu-noble", "apt-get"))
        with self.assertRaises(ValueError):
            recipes.make_plan("flatpak", fxt("ubuntu-noble", "apt-get", ["flatpak"]), {"branch": "nightly"})
        with self.assertRaises(ValueError):
            recipes.make_plan("flatpak", fxt("ubuntu-noble", "apt-get", ["flatpak"]), {"scope": "galaxy"})
        with self.assertRaises(ValueError):
            recipes.make_plan("aur-helper", fxt("arch", "pacman", ["yay"]), {"channel": "stable"})

    def test_method_names_still_map(self):
        d = fxt("ubuntu-noble", "apt-get")
        self.assertEqual(recipes.recipe_for_method("A", d), "apt-official")
        self.assertEqual(recipes.recipe_for_method("B", d), "flatpak")
        self.assertEqual(recipes.recipe_for_method("C", fxt("arch", "pacman")), "pacman-arch")


@unittest.skipUnless(HAVE_SH, "needs sh")
class RecipePlans(unittest.TestCase):
    def sh(self, rid, d, **opts):
        result = recipes.make_plan(rid, d, opts)
        for s in result["steps"]:
            self.assertTrue(sh_syntax_ok(s["sh"]), (rid, s["sh"]))
        return result

    def text(self, result):
        return "\n".join(s["sh"] for s in result["steps"])

    def test_flatpak_names_a_branch_so_a_non_interactive_install_works(self):
        d = fxt("ubuntu-noble", "apt-get", ["flatpak"])
        stable = self.sh("flatpak", d)
        self.assertIn("flatpak install --user -y flathub org.qgis.qgis//stable", self.text(stable))
        lts = self.sh("flatpak", d, branch="lts")
        self.assertIn("org.qgis.qgis//lts", self.text(lts))
        self.assertIn("flatpak_lts_eol", lts["notes"])
        self.assertNotIn("flatpak_lts_eol", stable["notes"])
        system_wide = self.sh("flatpak", d, scope="system")
        self.assertEqual([s["root"] for s in system_wide["steps"]], [True])
        self.assertIn("--system", self.text(system_wide))
        self.assertEqual([s["root"] for s in stable["steps"]], [False])

    def test_the_old_method_b_installs_a_branch_too(self):
        steps = qi.build_install("B", fxt("fedora-43", "dnf", ["flatpak"]), "ltr", {"grass": 1, "python": 1, "server": 0})
        self.assertIn("org.qgis.qgis//stable", steps[-1]["sh"])
        steps = qi.build_install("B", fxt("fedora-43", "dnf", ["flatpak"]), "ltr", {"branch": "lts"})
        self.assertIn("org.qgis.qgis//lts", steps[-1]["sh"])

    def test_flatpak_installs_itself_first_when_missing(self):
        steps = self.sh("flatpak", fxt("fedora-43", "dnf"))["steps"]
        self.assertEqual([s["root"] for s in steps], [True, False])
        self.assertIn("dnf install -y flatpak", steps[0]["sh"])

    def test_fedora_packages(self):
        d = fxt("fedora-43", "dnf")
        self.assertIn("dnf install -y qgis python3-qgis qgis-grass\n", self.text(self.sh("dnf-fedora", d)))
        self.assertIn("qgis-server", self.text(self.sh("dnf-fedora", d, server=True)))
        self.assertNotIn("qgis-grass", self.text(self.sh("dnf-fedora", d, grass=False)))
        atomic = fxt("fedora-silverblue", "dnf", ["rpm-ostree"], "ostree")
        r = self.sh("rpm-ostree-fedora", atomic)
        self.assertIn("rpm-ostree install --idempotent qgis python3-qgis qgis-grass", self.text(r))
        self.assertIn("ostree_reboot", r["notes"])

    def test_opensuse_uses_only_packages_that_exist(self):
        d = fxt("opensuse-tumbleweed", "zypper")
        plain = self.text(self.sh("zypper-opensuse", d))
        self.assertIn("zypper --non-interactive install qgis qgis-plugin-grass", plain)
        for bad in ("qgis-ltr", "python3-qgis", "addrepo"):
            self.assertNotIn(bad, plain)
        geo = self.text(self.sh("zypper-opensuse", d, geo_repo=True))
        self.assertIn("addrepo --refresh " + recipes.GEO_REPO + " geo", geo)
        self.assertLess(geo.index("addrepo"), geo.index("install qgis"))
        self.assertIn("suse_no_ltr", self.sh("zypper-opensuse", d)["notes"])

    def test_arch_official_and_aur(self):
        self.assertIn("pacman -S --noconfirm qgis", self.text(self.sh("pacman-arch", fxt("arch", "pacman"))))
        yay = self.sh("aur-helper", fxt("arch", "pacman", ["yay"]))
        self.assertEqual((yay["steps"][0]["root"], "yay -S --noconfirm qgis-ltr" in yay["steps"][0]["sh"]), (False, True))
        self.assertIn("aur_build", yay["notes"])
        paru = self.sh("aur-helper", fxt("arch", "pacman", ["paru"]), channel="testing")
        self.assertIn("paru -S --noconfirm qgis-git", paru["steps"][0]["sh"])
        both = self.sh("aur-helper", fxt("arch", "pacman", ["yay", "paru"]))
        self.assertIn("yay -S", both["steps"][0]["sh"])

    def test_mageia_uses_the_names_that_exist(self):
        r = self.sh("urpmi-mageia", fxt("mageia-9", "", ["urpmi"]))
        self.assertIn("urpmi --auto qgis qgis-grass", self.text(r))
        self.assertNotIn("qgis-python", self.text(r))

    def test_debian_distribution_package(self):
        r = self.sh("apt-distro", fxt("ubuntu-noble", "apt-get"), server=True)
        self.assertIn("apt-get install -y qgis python3-qgis qgis-plugin-grass qgis-server", self.text(r))

    def test_containers_and_spack(self):
        box = self.sh("distrobox", fxt("fedora-43", "dnf", ["distrobox"]))
        t = self.text(box)
        self.assertIn("distrobox create --yes --name qgis-box --image " + recipes.DISTROBOX_IMAGE, t)
        self.assertIn("zypper --non-interactive install qgis qgis-plugin-grass", t)
        self.assertIn("distrobox-export --app qgis", t)
        self.assertFalse(box["steps"][0]["root"])
        tb = self.text(self.sh("toolbx", fxt("fedora-43", "dnf", ["toolbox"])))
        self.assertIn("toolbox create --assumeyes --image " + recipes.TOOLBX_IMAGE + " qgis-box", tb)
        self.assertIn("dnf install -y qgis qgis-grass python3-qgis", tb)
        weird = self.text(self.sh("distrobox", fxt("fedora-43", "dnf", ["distrobox"]), image="x; rm -rf ~ #"))
        self.assertIn("'x; rm -rf ~ #'", weird)                                      # quoted, never executed
        self.assertIn("spack install qgis", self.text(self.sh("spack", fxt("fedora-43", "dnf", ["spack"]))))

    def test_manual_recipes_run_nothing(self):
        nix = recipes.make_plan("nix-manual", fxt("nixos", ""), {})
        self.assertEqual(nix["steps"], [])
        self.assertIn("nix-shell -p qgis --command qgis", nix["manual"][0]["text"])
        self.assertIn("pkgs.qgis\n", nix["manual"][1]["text"] + "\n")
        ltr = recipes.make_plan("nix-manual", fxt("nixos", ""), {"channel": "ltr"})
        self.assertIn("qgis-ltr", ltr["manual"][0]["text"])
        sl = recipes.make_plan("slackware-manual", fxt("slackware", ""), {})
        self.assertEqual((sl["steps"], sl["manual"][0]["text"]), ([], "https://slackbuilds.org/result/?search=qgis"))

    def test_apt_official_is_the_old_method_a(self):
        d = fxt("ubuntu-noble", "apt-get")
        a = self.sh("apt-official", d, channel="ltr", grass=True, python=True, server=False)["steps"]
        b = qi.build_install("A", d, "ltr", {"grass": True, "python": True, "server": False})
        self.assertEqual(a, b)


class Recommendation(unittest.TestCase):
    def pick(self, d, goal):
        r = recipes.recommend(d, goal)
        return r["recipe"], r["options"]

    def test_stable(self):
        self.assertEqual(self.pick(fxt("ubuntu-noble", "apt-get"), "stable"), ("apt-official", {"channel": "ltr"}))
        self.assertEqual(self.pick(fxt("debian-trixie", "apt-get"), "stable"), ("apt-official", {"channel": "ltr"}))
        self.assertEqual(self.pick(fxt("fedora-43", "dnf"), "stable")[0], "dnf-fedora")
        self.assertEqual(self.pick(fxt("mageia-9", "", ["urpmi"]), "stable")[0], "urpmi-mageia")
        self.assertEqual(self.pick(fxt("arch", "pacman"), "stable"), ("flatpak", {"branch": "lts"}))        # Arch has no LTR
        self.assertEqual(self.pick(fxt("opensuse-tumbleweed", "zypper"), "stable"), ("flatpak", {"branch": "lts"}))
        self.assertEqual(self.pick(fxt("fedora-silverblue", "dnf", ["rpm-ostree"], "ostree"), "stable"),
                         ("flatpak", {"branch": "lts"}))                                                  # the guide: Flatpak on Atomic

    def test_latest(self):
        self.assertEqual(self.pick(fxt("debian-trixie", "apt-get"), "latest"), ("apt-official", {"channel": "latest"}))
        self.assertEqual(self.pick(fxt("ubuntu-noble", "apt-get"), "latest"), ("flatpak", {"branch": "stable"}))   # apt: LTR only
        self.assertEqual(self.pick(fxt("arch", "pacman"), "latest")[0], "pacman-arch")
        self.assertEqual(self.pick(fxt("opensuse-tumbleweed", "zypper"), "latest")[0], "zypper-opensuse")
        self.assertEqual(self.pick(fxt("fedora-43", "dnf"), "latest"), ("flatpak", {"branch": "stable"}))

    def test_alongside_never_touches_the_installed_qgis(self):
        for name, pm in (("ubuntu-noble", "apt-get"), ("fedora-43", "dnf"), ("arch", "pacman"), ("opensuse-tumbleweed", "zypper")):
            rid, opts = self.pick(fxt(name, pm), "alongside")
            self.assertEqual((rid, opts), ("flatpak", {"branch": "stable"}), name)
        self.assertEqual(self.pick(fxt("nixos", "", ["distrobox"]), "alongside")[0], "distrobox")
        self.assertEqual(self.pick(fxt("slackware", "", ["toolbox"]), "alongside")[0], "toolbx")

    def test_nothing_fits_says_so(self):
        for goal in recipes.GOALS:
            r = recipes.recommend(fxt("slackware", ""), goal)
            self.assertEqual((r["recipe"], r["why"]), (None, "nothing_fits"), goal)
        self.assertEqual(recipes.recommend(fxt("slackware", ""), "latest")["alternatives"], ["slackware-manual"])

    def test_alternatives_are_the_other_recipes_that_apply(self):
        r = recipes.recommend(fxt("ubuntu-noble", "apt-get"), "stable")
        self.assertEqual(sorted(r["alternatives"]), ["apt-distro", "flatpak"])
        with self.assertRaises(ValueError):
            recipes.recommend(fxt("ubuntu-noble", "apt-get"), "fastest")

    def test_every_reason_has_text(self):
        for name, pm, tools in (("ubuntu-noble", "apt-get", []), ("arch", "pacman", []), ("slackware", "", [])):
            for goal in recipes.GOALS:
                r = recipes.recommend(fxt(name, pm, tools), goal)
                for lang in ("en", "ka"):
                    self.assertIn("why_" + r["why"], i18n.STR[lang])
            self.assertIn("goal_" + goal, i18n.STR["ka"])


class RecipeCli(unittest.TestCase):
    call = Cli.call

    def args(self, name, pm, tools=""):
        return ["--lang", "en", "--os-release", os.path.join(FIX, name), "--pm", pm, "--arch", "amd64", "--tools", tools]

    def test_recipes_listing(self):
        rc, out, _ = self.call("--json", *self.args("fedora-43", "dnf", "flatpak"), "recipes")
        rows = {r["id"]: r for r in json.loads(out)["recipes"]}
        self.assertEqual(rc, 0)
        self.assertTrue(rows["dnf-fedora"]["applies"] and rows["flatpak"]["applies"])
        self.assertFalse(rows["pacman-arch"]["applies"])
        self.assertEqual(rows["pacman-arch"]["reason_text"], i18n.STR["en"]["rcn_not_arch"])
        self.assertEqual(rows["dnf-fedora"]["verified"], "container")
        rc, out, _ = self.call(*self.args("fedora-43", "dnf", "flatpak"), "recipes")
        self.assertIn("[yes] Fedora package (dnf)", out)
        self.assertIn("[no ] Arch Linux package (pacman)  - needs Arch Linux", out)

    def test_recommend(self):
        rc, out, _ = self.call("--json", *self.args("arch", "pacman"), "recommend", "--goal", "stable")
        doc = json.loads(out)
        self.assertEqual((rc, doc["recipe"], doc["options"]), (0, "flatpak", {"branch": "lts"}))
        self.assertIn("long-term QGIS 3 line", doc["why_text"])
        rc, out, _ = self.call(*self.args("arch", "pacman"), "recommend", "--goal", "latest")
        self.assertIn("Arch Linux package (pacman)", out)
        rc, _, _ = self.call(*self.args("slackware", ""), "recommend", "--goal", "stable")
        self.assertEqual(rc, 2)

    def test_plan_by_goal_recipe_and_old_method(self):
        rc, out, _ = self.call("--json", *self.args("arch", "pacman"), "plan", "--goal", "latest")
        self.assertIn("pacman -S --noconfirm qgis", json.loads(out)["steps"][0]["sh"])
        rc, out, _ = self.call("--json", *self.args("ubuntu-noble", "apt-get", "flatpak"), "plan", "--recipe", "flatpak", "--branch", "lts")
        doc = json.loads(out)
        self.assertIn("org.qgis.qgis//lts", doc["steps"][-1]["sh"])
        self.assertEqual(doc["verified"], "flathub")
        self.assertTrue(any("end-of-life" in n["text"] for n in doc["notes"]))
        rc, out, _ = self.call("--json", *self.args("ubuntu-noble", "apt-get", "flatpak"), "plan", "--method", "B")
        self.assertIn("//stable", json.loads(out)["steps"][-1]["sh"])             # the old B no longer fails non-interactively
        rc, out, _ = self.call("--json", *self.args("fedora-43", "dnf", "flatpak"), "plan", "--recipe", "flatpak", "--scope", "system")
        self.assertTrue(json.loads(out)["steps"][-1]["root"])

    def test_not_applicable_and_bad_options_say_why(self):
        rc, _, err = self.call(*self.args("ubuntu-noble", "apt-get"), "plan", "--recipe", "dnf-fedora")
        self.assertEqual(rc, 2)
        self.assertIn("does not apply here: needs Fedora", err)
        rc, _, err = self.call(*self.args("ubuntu-noble", "apt-get"), "plan", "--recipe", "apt-official", "--channel", "latest")
        self.assertEqual(rc, 2)
        self.assertIn("allowed: ltr, nightly-ltr", err)
        rc, _, err = self.call(*self.args("arch", "pacman", "yay"), "plan", "--recipe", "aur-helper", "--channel", "stable")
        self.assertEqual(rc, 2)
        rc, _, err = self.call(*self.args("slackware", ""), "plan", "--goal", "stable")
        self.assertEqual(rc, 2)
        self.assertIn("installation guide", err)

    def test_manual_recipes_print_instructions_and_install_runs_nothing(self):
        with mock.patch.object(runner, "run_steps", side_effect=AssertionError("must not run")):
            rc, out, _ = self.call(*self.args("nixos", "", ""), "install", "--recipe", "nix-manual", "--channel", "ltr", "--yes")
        self.assertEqual(rc, 0)
        self.assertIn("nix-shell -p qgis-ltr --command qgis", out)
        self.assertIn(i18n.STR["en"]["rc_manual_only"], out)

    def test_install_goes_through_the_normal_confirmation(self):
        with mock.patch.object(runner, "run_steps", side_effect=AssertionError("must not run")):
            rc, _, err = self.call(*self.args("fedora-43", "dnf"), "install", "--recipe", "dnf-fedora")
            self.assertEqual(rc, 3)
            self.assertIn("--yes", err)
        with mock.patch.object(runner, "run_steps", return_value=(0, None)) as run:
            rc, out, _ = self.call(*self.args("fedora-43", "dnf"), "install", "--recipe", "dnf-fedora", "--server", "--yes")
        self.assertEqual(rc, 0)
        self.assertIn("qgis-server", run.call_args[0][0][0]["sh"])

    def test_georgian_output(self):
        rc, out, _ = self.call("--lang", "ka", "--os-release", os.path.join(FIX, "arch"), "--pm", "pacman", "--arch", "amd64",
                               "--tools", "", "recommend", "--goal", "latest")
        self.assertIn(i18n.STR["ka"]["goal_latest"], out)
        self.assertIn(i18n.STR["ka"]["why_rolling_latest"], out)


# --------------------------------------------------------------------------- update
class UpdatePlans(unittest.TestCase):
    D = fxt("ubuntu-noble", "apt-get")

    def plan(self, *items, d=None):
        return qi.update.plan(list(items), d or self.D)

    def sh(self, result):
        return "\n".join(s["sh"] for s in result["steps"])

    def test_apt_upgrades_exactly_the_installed_packages_and_asks_to_close_qgis(self):
        r = self.plan({"kind": "apt", "pkgs": ["python3-qgis", "qgis", "qgis-plugin-grass"], "v": "3.44", "o": "", "root": True})
        self.assertEqual(len(r["steps"]), 1)
        self.assertTrue(r["steps"][0]["root"])
        self.assertIn("apt-get update\napt-get install -y --only-upgrade python3-qgis qgis qgis-plugin-grass\n", self.sh(r))
        self.assertEqual(r["notes"][0], "upd_close_qgis")

    def test_flatpak_user_needs_no_root_and_system_does(self):
        u = self.plan({"kind": "flatpak", "i": "user", "v": "4.2", "root": False})
        self.assertEqual((u["steps"][0]["root"], "flatpak update --user -y org.qgis.qgis" in self.sh(u)), (False, True))
        sy = self.plan({"kind": "flatpak", "i": "system", "v": "4.2", "root": True})
        self.assertEqual((sy["steps"][0]["root"], "flatpak update --system -y org.qgis.qgis" in self.sh(sy)), (True, True))

    def test_distribution_packages(self):
        dnf = self.plan({"kind": "dist", "pm": "dnf", "pkgs": ["qgis"], "v": "3.44", "root": True})
        self.assertIn("dnf upgrade -y qgis\n", self.sh(dnf))
        zy = self.plan({"kind": "dist", "pm": "zypper", "pkgs": ["qgis"], "v": "3.44", "root": True})
        self.assertIn("zypper --non-interactive update qgis\n", self.sh(zy))
        ot = self.plan({"kind": "dist", "pm": "rpm-ostree", "pkgs": ["qgis"], "v": "3.44", "root": True})
        self.assertIn("rpm-ostree upgrade\n", self.sh(ot))
        self.assertIn("upd_ostree", ot["notes"])
        self.assertIn("snap refresh qgis\n", self.sh(self.plan({"kind": "snap", "v": "3.44", "root": True})))

    def test_arch_is_never_a_partial_upgrade(self):
        r = self.plan({"kind": "dist", "pm": "pacman", "pkgs": ["qgis", "qgis-ltr"], "v": "3.44", "root": True})
        self.assertEqual(r["steps"], [])                                   # nothing runs: the user decides when to update the system
        self.assertEqual([m["text"].split()[0:2] for m in r["manual"]], [["sudo", "pacman"], ["yay", "-S"]])
        self.assertIn("pacman -Syu", r["manual"][0]["text"])
        self.assertNotIn("pacman -S ", self.sh(r) + " ".join(m["text"] for m in r["manual"]).replace("-Syu", ""))
        self.assertIn("upd_arch_full", r["notes"])

    def test_container_repository_files_and_user_data_are_not_updated(self):
        r = self.plan({"kind": "container", "tool": "distrobox", "name": "qgis-box", "root": False},
                      {"kind": "repo", "files": ["/etc/apt/sources.list.d/qgis.sources"], "root": True},
                      {"kind": "data", "path": "/home/x/.local/share/QGIS", "sz": "1 MB", "root": False})
        self.assertEqual((r["steps"], r["manual"]), ([], []))
        self.assertEqual(r["notes"], ["upd_container"])                      # told how, without running anything

    def test_nothing_found_says_so(self):
        r = self.plan()
        self.assertEqual((r["steps"], r["notes"]), ([], ["upd_none"]))

    def test_every_update_script_parses_and_every_note_has_text(self):
        items = [{"kind": "apt", "pkgs": ["qgis"], "root": True}, {"kind": "flatpak", "i": "user", "root": False},
                 {"kind": "snap", "root": True}, {"kind": "dist", "pm": "dnf", "pkgs": ["qgis"], "root": True},
                 {"kind": "dist", "pm": "zypper", "pkgs": ["qgis-ltr"], "root": True},
                 {"kind": "dist", "pm": "rpm-ostree", "pkgs": ["qgis"], "root": True},
                 {"kind": "dist", "pm": "pacman", "pkgs": ["qgis-git"], "root": True},
                 {"kind": "dist", "pm": "urpmi", "pkgs": ["qgis"], "root": True},
                 {"kind": "container", "tool": "toolbox", "name": "qgis-box", "root": False}]
        r = self.plan(*items)
        self.assertGreaterEqual(len(r["steps"]), 6)
        for st in r["steps"]:
            self.assertTrue(sh_syntax_ok(st["sh"]), st["sh"])
        for lang in ("en", "ka"):
            for n in r["notes"]:
                self.assertIn("rcw_" + n, i18n.STR[lang])
            for m in r["manual"]:
                self.assertIn("rcm_" + m["title"], i18n.STR[lang])
        self.assertIn("upd_unknown", r["notes"])                              # a package manager we have no command for


class SideBySide(unittest.TestCase):
    def test_only_the_recipes_that_live_apart_from_the_system_qgis_are_marked(self):
        self.assertEqual({r for r, v in recipes.RECIPES.items() if v["side_by_side"]},
                         {"flatpak", "distrobox", "toolbx", "spack", "nix-manual"})
        rows = {a["id"]: a for a in recipes.available(fxt("fedora-43", "dnf", ("flatpak",)))}
        self.assertTrue(rows["flatpak"]["side_by_side"])
        self.assertFalse(rows["dnf-fedora"]["side_by_side"])

    def test_the_alongside_goal_only_ever_recommends_a_side_by_side_recipe(self):
        for name, pm, tools in (("ubuntu-noble", "apt-get", ()), ("fedora-43", "dnf", ()), ("arch", "pacman", ()),
                                ("opensuse-tumbleweed", "zypper", ("distrobox",)), ("fedora-43", "dnf", ("toolbox",))):
            rec = recipes.recommend(fxt(name, pm, tools), "alongside")
            self.assertTrue(recipes.RECIPES[rec["recipe"]]["side_by_side"], (name, rec))


class UpdateCli(unittest.TestCase):
    call = Cli.call

    def test_update_shows_the_commands_and_dry_run_runs_nothing(self):
        items = [{"kind": "flatpak", "i": "user", "v": "4.2", "root": False}]
        with mock.patch.object(uninstall, "find_installs", lambda s: items), mock.patch.object(runner, "run_steps") as run:
            rc, out, _ = self.call("--lang", "en", "--os-release", os.path.join(FIX, "fedora-43"), "--pm", "dnf", "--arch", "amd64",
                                   "--tools", "", "update", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("flatpak update --user -y org.qgis.qgis", out)
        self.assertIn("Close QGIS before updating", out)
        run.assert_not_called()

    def test_update_json_and_georgian(self):
        items = [{"kind": "dist", "pm": "pacman", "pkgs": ["qgis"], "v": "3.44", "root": True}]
        with mock.patch.object(uninstall, "find_installs", lambda s: items):
            rc, out, _ = self.call("--lang", "ka", "--json", "--os-release", os.path.join(FIX, "arch"), "--pm", "pacman", "--arch", "amd64",
                                   "--tools", "", "update")
        doc = json.loads(out)
        self.assertEqual((rc, doc["steps"]), (0, []))
        self.assertIn("pacman -Syu", doc["manual"][0]["text"])
        self.assertIn("დახურეთ QGIS", doc["notes"][0]["text"])

    def test_nothing_to_update(self):
        with mock.patch.object(uninstall, "find_installs", lambda s: []):
            rc, out, _ = self.call("--lang", "en", "--os-release", os.path.join(FIX, "fedora-43"), "--pm", "dnf", "--arch", "amd64",
                                   "--tools", "", "update")
        self.assertEqual(rc, 0)
        self.assertIn("Nothing to update", out)


# --------------------------------------------------------------------------- components (the OSGeo4W-like chooser, Linux form)
class Components(unittest.TestCase):
    def rows(self, pm, present=()):
        return requirements.components(pm, which=lambda t: "/x/" + t if t in present else None,
                                       find_spec=lambda m: object() if m in present else None)

    def test_every_component_is_listed_once_in_its_category_in_order(self):
        rows = self.rows("apt-get")
        ids = [r["id"] for r in rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), set(requirements.REQ))                   # nothing in the table is hidden
        cats = [r["cat"] for r in rows]
        self.assertEqual(cats, sorted(cats, key=requirements.CATEGORIES.index))
        self.assertEqual(set(cats), set(requirements.CATEGORIES))
        for lang in ("en", "ka"):
            for c in requirements.CATEGORIES:
                self.assertIn("cat_" + c, i18n.STR[lang])

    def test_a_tool_in_a_perl_directory_that_a_plain_path_lacks_still_counts_as_installed(self):
        real = shutil.which
        with mock.patch.object(requirements.shutil, "which", lambda t: None),                 mock.patch.object(requirements.os, "access", lambda p, m: p == "/usr/bin/vendor_perl/exiftool"),                 mock.patch.object(requirements.os.path, "isfile", lambda p: p == "/usr/bin/vendor_perl/exiftool"):
            self.assertTrue(requirements.is_present("exiftool", which=requirements.shutil.which))
            self.assertFalse(requirements.is_present("saga", which=requirements.shutil.which))      # saga_cmd is nowhere
        self.assertFalse(requirements.is_present("exiftool", which=lambda t: None))                  # an injected `which` decides alone
        del real

    def test_present_follows_the_tools_and_modules_found(self):
        rows = {r["id"]: r for r in self.rows("apt-get", present=("gdalinfo", "ogr2ogr", "numpy"))}
        self.assertTrue(rows["gdal"]["present"] and rows["numpy"]["present"])
        self.assertFalse(rows["proj"]["present"])
        half = {r["id"]: r for r in self.rows("apt-get", present=("gdalinfo",))}
        self.assertFalse(half["gdal"]["present"])                              # all of its tools are needed

    def test_package_names_per_package_manager_and_the_python_tag_of_opensuse(self):
        apt = {r["id"]: r for r in self.rows("apt-get")}
        self.assertEqual((apt["gdal"]["packages"], apt["numpy"]["packages"]), (["gdal-bin"], ["python3-numpy"]))
        arch = {r["id"]: r for r in self.rows("pacman")}
        self.assertEqual(arch["numpy"]["packages"], ["python-numpy"])
        self.assertTrue(arch["rasterio"]["manual"] and arch["rasterio"]["packages"] == [])
        suse = {r["id"]: r for r in requirements.components("zypper", pyver="312")}
        self.assertEqual(suse["numpy"]["packages"], ["python312-numpy"])
        self.assertEqual(suse["gdal-python"]["packages"], ["python312-GDAL"])
        self.assertEqual(self.rows("")[0]["packages"], [])                      # no package manager: nothing to install, nothing raised

    def test_install_steps_are_one_root_step_and_parse(self):
        for pm in ("apt-get", "dnf", "pacman", "zypper", "apk"):
            ids = [r["id"] for r in self.rows(pm) if r["packages"]]
            steps, manual = requirements.install_steps(ids, pm)
            self.assertEqual(len(steps), 1)
            self.assertTrue(steps[0]["root"] and sh_syntax_ok(steps[0]["sh"]))


class ComponentsCli(unittest.TestCase):
    call = Cli.call

    def args(self, name="ubuntu-noble", pm="apt-get"):
        return ["--lang", "en", "--os-release", os.path.join(FIX, name), "--pm", pm, "--arch", "amd64"]

    def present(self, *ids):
        real = requirements.is_present
        return mock.patch.object(requirements, "is_present", lambda rid, **kw: rid in ids), real

    def test_list_groups_by_category_and_marks_what_is_present(self):
        patch, _ = self.present("gdal")
        with patch:
            rc, out, _ = self.call(*self.args(), "components")
        self.assertEqual(rc, 0)
        self.assertLess(out.index("Command line tools"), out.index("GIS engines"))
        self.assertLess(out.index("GIS engines"), out.index("Python libraries"))
        self.assertRegex(out, r"\[x\] gdal +GDAL command line tools")
        self.assertRegex(out, r"\[ \] numpy +NumPy +-> python3-numpy")
        with patch:
            rc, out, _ = self.call(*self.args(), "components", "list", "--category", "db")
        self.assertIn("Database clients", out)
        self.assertNotIn("numpy", out)

    def test_list_json(self):
        patch, _ = self.present("numpy")
        with patch:
            rc, out, _ = self.call("--json", *self.args(), "components")
        doc = json.loads(out)
        self.assertEqual((rc, doc["package_manager"]), (0, "apt-get"))
        rows = {r["id"]: r for r in doc["components"]}
        self.assertTrue(rows["numpy"]["present"] and not rows["scipy"]["present"])
        self.assertEqual(rows["scipy"]["packages"], ["python3-scipy"])

    def test_install_shows_the_commands_and_skips_what_is_there(self):
        patch, _ = self.present("numpy")
        with patch, mock.patch.object(runner, "run_steps") as run:
            rc, out, _ = self.call(*self.args(), "components", "install", "numpy", "scipy", "gdal", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("NumPy: already installed.", out)
        self.assertIn("apt-get install -y gdal-bin python3-scipy", out)
        self.assertNotIn("python3-numpy", out)
        run.assert_not_called()

    def test_install_of_nothing_new_unknown_ids_and_no_package(self):
        patch, _ = self.present("numpy")
        with patch:
            rc, out, _ = self.call(*self.args(), "components", "install", "numpy")
            self.assertEqual((rc, out.strip()), (0, "NumPy: already installed."))
            rc, _, err = self.call(*self.args(), "components", "install", "nonsense")
            self.assertEqual(rc, 2)
            self.assertIn("Unknown component 'nonsense'. Known: ", err)
            rc, _, err = self.call(*self.args("arch", "pacman"), "components", "install", "rasterio")
        self.assertEqual(rc, 2)                                                   # Arch has no package for it: said, not guessed
        self.assertIn("no package for your system", err)

    def test_georgian(self):
        patch, _ = self.present()
        with patch:
            rc, out, _ = self.call("--lang", "ka", "--os-release", os.path.join(FIX, "ubuntu-noble"), "--pm", "apt-get",
                                   "--arch", "amd64", "components", "--category", "python")
        self.assertIn("Python-ის ბიბლიოთეკები", out)


# --------------------------------------------------------------------------- instances: start any installed QGIS, is a newer build waiting
APT = {"kind": "apt", "pkgs": ["python3-qgis", "qgis"], "v": "3.44.5", "o": "qgis.org", "root": True}
FP_STABLE = {"kind": "flatpak", "i": "user", "v": "4.2.2", "br": "stable", "root": False}
FP_LTS = {"kind": "flatpak", "i": "system", "v": "3.44.5", "br": "lts", "root": True}
SNAP = {"kind": "snap", "v": "3.44", "root": True}
DIST_AUR = {"kind": "dist", "pm": "pacman", "pkgs": ["qgis-ltr"], "v": "3.44.1", "root": True}
BOX = {"kind": "container", "tool": "distrobox", "name": "qgis-box", "root": False}


def have(*names):
    return lambda c: "/usr/bin/" + c if c in names else None


class Instances(unittest.TestCase):
    def test_every_kind_has_its_own_start_command(self):
        rows = {r["id"]: r for r in qi.instances.list_instances(
            [APT, FP_STABLE, FP_LTS, SNAP, DIST_AUR, BOX, {"kind": "repo", "files": [], "c": ""}, {"kind": "data", "path": "/x", "sz": "1"}],
            which=have("qgis", "flatpak", "snap", "qgis-ltr", "distrobox"))}
        self.assertEqual(sorted(rows), ["apt", "container-distrobox", "dist-pacman-qgis-ltr", "flatpak-system-lts", "flatpak-user-stable", "snap"])
        self.assertEqual(rows["apt"]["launch"], ["qgis"])
        self.assertEqual(rows["flatpak-user-stable"]["launch"], ["flatpak", "run", "--branch=stable", "org.qgis.qgis"])
        self.assertEqual(rows["flatpak-system-lts"]["launch"], ["flatpak", "run", "--branch=lts", "org.qgis.qgis"])
        self.assertEqual(rows["snap"]["launch"], ["snap", "run", "qgis"])
        self.assertEqual(rows["dist-pacman-qgis-ltr"]["launch"], ["qgis-ltr"])          # the package's own binary when it exists
        self.assertEqual(rows["container-distrobox"]["launch"], ["distrobox", "enter", "qgis-box", "--", "qgis"])
        self.assertEqual(rows["flatpak-system-lts"]["version"], "3.44.5")

    def test_toolbox_and_the_fallback_binary_name(self):
        r = qi.instances.list_instances([dict(BOX, tool="toolbox")], which=have("toolbox"))[0]
        self.assertEqual(r["launch"], ["toolbox", "run", "--container", "qgis-box", "qgis"])
        r = qi.instances.list_instances([DIST_AUR], which=have("qgis"))[0]
        self.assertEqual(r["launch"], ["qgis"])                                         # no qgis-ltr binary: the plain one

    def test_what_cannot_be_started_is_listed_but_not_launchable(self):
        rows = qi.instances.list_instances([APT, FP_STABLE, BOX], which=have())
        self.assertEqual([r["launchable"] for r in rows], [False, False, False])
        self.assertTrue(all(r["launch"] is None for r in rows))
        with self.assertRaises(ValueError):
            qi.instances.launch(rows[0])

    def test_only_the_programs_that_share_the_profile_are_flagged(self):
        rows = {r["kind"]: r["shared_profile"] for r in qi.instances.list_instances([APT, FP_STABLE, SNAP, BOX, DIST_AUR], which=have())}
        self.assertEqual(rows, {"apt": True, "flatpak": False, "snap": False, "container": True, "dist": True})

    def test_launch_is_detached_and_silent(self):
        calls = []

        class P:
            pid = 4242

        def popen(argv, **kw):
            calls.append((argv, kw))
            return P()
        row = qi.instances.list_instances([FP_LTS], which=have("flatpak"))[0]
        self.assertEqual(qi.instances.launch(row, popen=popen), 4242)
        argv, kw = calls[0]
        self.assertEqual(argv[:3], ["flatpak", "run", "--branch=lts"])
        self.assertTrue(kw["start_new_session"])
        self.assertEqual((kw["stdout"], kw["stderr"], kw["stdin"]), (subprocess.DEVNULL,) * 3)

    def test_find(self):
        rows = qi.instances.list_instances([APT, SNAP], which=have())
        self.assertEqual(qi.instances.find(rows, "snap")["kind"], "snap")
        self.assertIsNone(qi.instances.find(rows, "nope"))


class CheckUpdates(unittest.TestCase):
    def fake(self, table):
        calls = []

        def run(cmd, timeout=120):
            calls.append(cmd)
            for prefix, answer in table:
                if cmd[:len(prefix)] == prefix:
                    return answer
            return 1, ""
        run.calls = calls
        return run

    def one(self, item, table):
        rows = qi.instances.check_updates([item], run=self.fake(table))
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_apt_compares_installed_with_the_candidate_and_says_it_is_cached(self):
        pol = "qgis:\n  Installed: 3.44.5+24noble\n  Candidate: 3.44.6+24noble\n  Version table:\n"
        r = self.one(APT, [(["apt-cache", "policy", "qgis"], (0, pol))])
        self.assertEqual((r["update"], r["candidate"], r["source"]), (True, "3.44.6+24noble", "cached"))
        same = pol.replace("3.44.6", "3.44.5")
        self.assertIs(self.one(APT, [(["apt-cache", "policy", "qgis"], (0, same))])["update"], False)
        none = "qgis:\n  Installed: 3.44.5\n  Candidate: (none)\n"
        self.assertIsNone(self.one(APT, [(["apt-cache", "policy", "qgis"], (0, none))])["update"])      # not "up to date"

    def test_flatpak_looks_for_its_own_branch_only(self):
        listing = "org.qgis.qgis\tlts\norg.gnome.Platform\t48\n"
        t = [(["flatpak", "remote-ls", "--updates", "--system"], (0, listing))]
        self.assertIs(self.one(FP_LTS, t)["update"], True)
        t = [(["flatpak", "remote-ls", "--updates", "--user"], (0, listing))]
        self.assertIs(self.one(FP_STABLE, t)["update"], False)                    # the lts update is not the stable one
        self.assertEqual(self.one(FP_STABLE, t)["source"], "network")

    def test_no_network_is_unknown_never_up_to_date(self):
        for item in (FP_STABLE, SNAP, dict(DIST_AUR, pm="dnf", pkgs=["qgis"])):
            self.assertIsNone(self.one(item, [])["update"], item["kind"])           # every command failed

    def test_snap_and_dnf_and_zypper_and_pacman(self):
        self.assertIs(self.one(SNAP, [(["snap", "refresh", "--list"], (0, "Name  Version\nqgis  3.44.6  1234  latest/stable\n"))])["update"], True)
        self.assertIs(self.one(SNAP, [(["snap", "refresh", "--list"], (0, ""))])["update"], False)
        dnf = dict(DIST_AUR, pm="dnf", pkgs=["qgis"])
        self.assertIs(self.one(dnf, [(["dnf", "-q", "check-update"], (100, "qgis.x86_64 3.44.6\n"))])["update"], True)
        self.assertIs(self.one(dnf, [(["dnf", "-q", "check-update"], (0, ""))])["update"], False)
        self.assertIsNone(self.one(dnf, [(["dnf", "-q", "check-update"], (1, ""))])["update"])
        zy = dict(DIST_AUR, pm="zypper", pkgs=["qgis"])
        out = "S | Repository | Name | Current | Available\nv | repo-oss | qgis | 3.44.1 | 3.44.2\n"
        self.assertIs(self.one(zy, [(["zypper", "--non-interactive", "list-updates"], (0, out))])["update"], True)
        self.assertIs(self.one(zy, [(["zypper", "--non-interactive", "list-updates"], (0, "No updates found.\n"))])["update"], False)
        pac = dict(DIST_AUR, pm="pacman", pkgs=["qgis"])
        self.assertIs(self.one(pac, [(["pacman", "-Qu", "qgis"], (0, "qgis 3.44.1-1 -> 3.44.2-1\n"))])["update"], True)
        self.assertIs(self.one(pac, [(["pacman", "-Qu", "qgis"], (1, ""))])["update"], False)

    def test_it_only_reads(self):
        run = self.fake([])
        qi.instances.check_updates([APT, FP_STABLE, SNAP, DIST_AUR, dict(DIST_AUR, pm="dnf"), dict(DIST_AUR, pm="zypper"), BOX], run=run)
        self.assertGreaterEqual(len(run.calls), 6)
        for c in run.calls:
            self.assertFalse({"install", "upgrade", "remove", "uninstall", "-S", "-Syu"} & set(c), c)
            if c[0] == "snap":
                self.assertEqual(c, ["snap", "refresh", "--list"])                 # the only snap command, and it just lists


class FlatpakBranches(unittest.TestCase):
    def test_removal_names_the_branch_so_both_can_live_together(self):
        d = fx("fedora-43", "dnf")
        steps = uninstall.build_remove_steps([FP_STABLE, FP_LTS], False, False, d)
        text = "\n".join(st["sh"] for st in steps)
        self.assertIn("flatpak uninstall --user -y org.qgis.qgis//stable", text)
        self.assertIn("flatpak uninstall --system -y org.qgis.qgis//lts", text)
        old = uninstall.build_remove_steps([{"kind": "flatpak", "i": "user", "v": "4", "root": False}], False, False, d)
        self.assertIn("flatpak uninstall --user -y org.qgis.qgis\n", old[0]["sh"])          # no branch known: as before
        evil = uninstall.build_remove_steps([dict(FP_STABLE, br="x; rm -rf ~")], False, False, d)
        self.assertNotIn("rm -rf", evil[0]["sh"])

    def test_find_installs_reads_the_branch_column(self):
        def fake_run(cmd):
            if cmd[:2] == ["flatpak", "list"]:
                self.assertIn("--columns=application,version,installation,branch", cmd)
                return 0, "org.qgis.qgis\t4.2.2\tuser\tstable\norg.qgis.qgis\t3.44.5\tsystem\tlts\norg.other\t1\tuser\tstable\n"
            return 1, ""
        with mock.patch.object(uninstall, "_run", fake_run), mock.patch.object(uninstall.shutil, "which", lambda c: "/usr/bin/" + c if c == "flatpak" else None), \
                mock.patch.object(uninstall.os.path, "isdir", return_value=False):
            items = uninstall.find_installs(fx("fedora-43", "dnf"))
        fp = [i for i in items if i["kind"] == "flatpak"]
        self.assertEqual([(i["i"], i["br"], i["v"]) for i in fp], [("user", "stable", "4.2.2"), ("system", "lts", "3.44.5")])
        self.assertIn("user, stable", i18n.label_for(fp[0], "en"))
        self.assertIn("system, lts", i18n.label_for(fp[1], "ka"))


class InstancesCli(unittest.TestCase):
    call = Cli.call
    BASE = ["--lang", "en", "--os-release", os.path.join(FIX, "fedora-43"), "--pm", "dnf", "--arch", "amd64", "--tools", ""]

    def run_cmd(self, items, *argv, which=("flatpak",)):
        with mock.patch.object(uninstall, "find_installs", lambda s: items), \
                mock.patch.object(qi.instances.shutil, "which", have(*which)):
            return self.call(*self.BASE, *argv)

    def test_instances_lists_how_to_start_each(self):
        rc, out, _ = self.run_cmd([FP_STABLE, FP_LTS], "instances")
        self.assertEqual(rc, 0)
        self.assertIn("[flatpak-user-stable]", out)
        self.assertIn("flatpak run --branch=lts org.qgis.qgis", out)
        rc, out, _ = self.run_cmd([FP_STABLE], "--json", "instances")
        doc = json.loads(out)["instances"]
        self.assertEqual((doc[0]["id"], doc[0]["launch"][0], doc[0]["shared_profile"]), ("flatpak-user-stable", "flatpak", False))
        rc, out, _ = self.run_cmd([], "instances")
        self.assertIn("No QGIS installation that can be started", out)

    def test_launch_asks_unless_yes_and_warns_about_a_shared_profile(self):
        started = []
        with mock.patch.object(qi.instances, "launch", lambda row, popen=None: started.append(row["id"]) or 77):
            rc, out, err = self.run_cmd([APT], "launch", "apt", "--yes", which=("qgis",))
            self.assertEqual((rc, started), (0, ["apt"]))
            self.assertIn("share your profile folder", out)
            self.assertIn("Started (process 77).", out)
            started.clear()
            rc, out, err = self.run_cmd([FP_STABLE], "launch", "flatpak-user-stable", "--yes")
            self.assertEqual((rc, started), (0, ["flatpak-user-stable"]))
            self.assertNotIn("share your profile", out)                              # Flatpak has its own profile
            started.clear()
            rc, _, err = self.run_cmd([APT], "launch", "apt", which=("qgis",))                 # not a terminal, no --yes
            self.assertEqual((rc, started), (3, []))
            self.assertIn("pass --yes", err)

    def test_launch_unknown_and_unlaunchable(self):
        rc, _, err = self.run_cmd([APT], "launch", "nope", which=("qgis",))
        self.assertEqual(rc, 2)
        self.assertIn("Unknown installation 'nope'. Known: apt", err)
        rc, _, err = self.run_cmd([APT], "launch", "apt", "--yes", which=())
        self.assertEqual(rc, 2)
        self.assertIn("No way to start this one is known", err)

    def test_check_updates_text_and_json(self):
        pol = "qgis:\n  Installed: 3.44.5\n  Candidate: 3.44.6\n"
        run = lambda cmd, timeout=120: (0, pol) if cmd[:2] == ["apt-cache", "policy"] else (1, "")  # noqa: E731
        with mock.patch.object(qi.instances, "_run", run):
            rc, out, _ = self.run_cmd([APT, FP_STABLE], "check-updates", which=("qgis",))
            rc2, out2, _ = self.run_cmd([APT, FP_STABLE], "--json", "check-updates", which=("qgis",))
        self.assertEqual(rc, 0)
        self.assertIn("newer build available (3.44.6) - as of the last refresh of the package index", out)
        self.assertIn("could not tell - asked online", out)                          # flatpak failed: unknown, not "up to date"
        rows = {r["id"]: r for r in json.loads(out2)["instances"]}
        self.assertIs(rows["apt"]["updates"]["update"], True)
        self.assertIsNone(rows["flatpak-user-stable"]["updates"]["update"])


# --------------------------------------------------------------------------- simulation: what would the package manager do
APT_SIM = """Reading package lists...
Inst libexpat1 (2.8.3-1 Debian:13/stable [amd64])
Inst poppler-data (0.4.12-1 Debian:13/stable [all])
Inst proj-bin [9.5.0-1] (9.6.0-1 Debian:13/stable [amd64])
0 upgraded, 2 newly installed, 0 to remove and 1 not upgraded.
"""
APT_URIS = """'http://deb.debian.org/debian/pool/main/e/expat/libexpat1_2.8.3-1_amd64.deb' libexpat1_2.8.3-1_amd64.deb 122672 MD5Sum:d02b
'http://deb.debian.org/debian/pool/main/p/poppler-data/poppler-data_0.4.12-1_all.deb' poppler-data_0.4.12-1_all.deb 1601364 MD5Sum:a5fd
"""
DNF5_SIM = """Transaction Summary:
 Installing:       422 packages
 Removing:           2 packages

Total size of inbound packages is 1 GiB. Need to download 1 GiB.
After this operation, 2 GiB extra will be used (install 2 GiB, remove 0 B).
Operation aborted by the user.
"""
DNF4_SIM = """Transaction Summary
================
Install  3 Packages
Upgrade  1 Package

Total download size: 12 M
Installed size: 40 M
Operation aborted.
"""
ZYP_SIM = """158 new packages to install.

Package download size:   140.6 MiB

Package install size change:
              |     554.8 MiB  required by packages that will be installed
   554.8 MiB  |  -      0 B    released by packages that will be removed
"""
PAC_SIM = "snappy|1.3.1-1|40127\nblosc|1.21.6-2|48520\ngeos|3.15.0-1|2019454\n"
APK_SIM = "(1/2) Installing gdal (3.11.5-r2)\n(2/2) Installing gdal-tools (3.11.5-r2)\nOK: 263.4 MiB in 113 packages\n"
FLAT_INFO = "        ID: org.qgis.qgis\n       Ref: app/org.qgis.qgis/x86_64/stable\n  Download: 1.4 GB\n Installed: 4.1 GB\n   Runtime: org.kde.Platform/x86_64/6.11\n"
FLAT_INFO_NBSP = FLAT_INFO.replace("1.4 GB", "592.6\u00a0MB").replace("4.1 GB", "1.6?GB")


def answers(table):
    calls = []

    def run(cmd, timeout=180):
        calls.append(cmd)
        for prefix, answer in table:
            if cmd[:len(prefix)] == prefix:
                return answer
        return 1, ""
    run.calls = calls
    return run


class SimulateParse(unittest.TestCase):
    def test_install_upgrade_remove_lines_of_every_tool(self):
        P = qi.simulate.parse_line
        self.assertEqual(P("apt-get install -y gdal-bin python3-numpy"), {"tool": "apt", "verb": "install", "names": ["gdal-bin", "python3-numpy"], "opts": ["-y"]})
        self.assertEqual(P("apt-get install -y --only-upgrade qgis")["opts"], ["-y", "--only-upgrade"])
        self.assertEqual(P("apt-get purge -y qgis")["verb"], "remove")
        self.assertEqual(P("dnf upgrade -y qgis")["verb"], "upgrade")
        self.assertEqual(P("zypper --non-interactive update qgis")["verb"], "upgrade")
        self.assertEqual((P("pacman -S --noconfirm qgis")["tool"], P("pacman -S --noconfirm qgis")["verb"]), ("pacman", "install"))
        self.assertEqual(P("pacman -R --noconfirm qgis")["verb"], "remove")
        self.assertEqual(P("apk add gdal")["verb"], "install")
        fp = P("flatpak install --system -y flathub org.qgis.qgis//lts")
        self.assertEqual((fp["tool"], fp["remote"], fp["names"], fp["opts"]), ("flatpak", "flathub", ["org.qgis.qgis//lts"], ["--system"]))

    def test_other_lines_are_not_simulated(self):
        for line in ("set -eu", "apt-get update", "wget -q https://x", "rpm-ostree install qgis", "flatpak remote-add --user flathub x",
                     "apt-get install -y", "echo apt-get install qgis", "snap refresh qgis"):
            self.assertIsNone(qi.simulate.parse_line(line), line)

    def test_human_sizes(self):
        self.assertEqual((qi.simulate.human(512), qi.simulate.human(1536), qi.simulate.human(1723364)), ("512 B", "1.5 KiB", "1.6 MiB"))


class SimulateTools(unittest.TestCase):
    def one(self, line, table):
        return qi.simulate.simulate_line(line, run=answers(table))

    def test_apt_counts_upgrades_apart_and_sums_the_download(self):
        r = self.one("apt-get install -y gdal-bin", [(["apt-get", "-s", "install"], (0, APT_SIM)), (["apt-get", "-qq", "--print-uris"], (0, APT_URIS))])
        self.assertEqual((r["installs"], r["upgrades"], r["removes"], r["download"]), (2, 1, [], "1.6 MiB"))

    def test_an_older_version_is_a_downgrade_not_an_upgrade(self):
        out = "Inst tzdata [2026e-0ubuntu0.24.04.1] (2024a-2ubuntu1 Ubuntu:24.04/noble [all])\nInst other [1.0] (2.0 Ubuntu:24.04/noble [all])\n"
        r = self.one("apt-get install -y tzdata=2024a-2ubuntu1", [(["apt-get", "-s", "install"], (0, out))])
        self.assertEqual((r["installs"], r["upgrades"], r["downgrades"]), (0, 1, 1))
        text = qi.simulate.format_text({"items": [r], "unsimulated": 0, "warnings": []}, "en")
        self.assertIn("1 to upgrade, 1 to go back to an older version", text)
        self.assertIn("ძველ ვერსიას დაუბრუნდება: 1", qi.simulate.format_text({"items": [r], "unsimulated": 0, "warnings": []}, "ka"))

    def test_apt_remove_lists_what_goes_with_it(self):
        out = "Remv python3-scipy [1.15.3-1]\nRemv python3-numpy [1:2.2.4]\n0 upgraded, 0 newly installed, 2 to remove\n"
        r = self.one("apt-get remove -y python3-numpy", [(["apt-get", "-s", "remove"], (0, out))])
        self.assertEqual((r["removes"], r["remove_count"], r["download"]), (["python3-scipy", "python3-numpy"], 2, None))

    def test_apt_that_cannot_look_is_none_not_zero(self):
        self.assertIsNone(self.one("apt-get install -y x", [(["apt-get", "-s"], (100, "E: Unable to locate package x"))]))

    def test_dnf5_and_dnf4(self):
        r = self.one("dnf install -y gdal", [(["dnf", "install", "--assumeno"], (1, DNF5_SIM))])
        self.assertEqual((r["installs"], r["remove_count"], r["download"], r["disk"]), (422, 2, "1 GiB", "2 GiB"))
        r = self.one("dnf upgrade -y qgis", [(["dnf", "upgrade", "--assumeno"], (1, DNF4_SIM))])
        self.assertEqual((r["installs"], r["upgrades"], r["download"], r["disk"]), (3, 1, "12 M", "40 M"))
        self.assertIsNone(self.one("dnf install -y x", [(["dnf"], (1, "Error: no match"))]))

    def test_zypper(self):
        r = self.one("zypper --non-interactive install gdal", [(["zypper", "--non-interactive", "install", "--dry-run"], (0, ZYP_SIM))])
        self.assertEqual((r["installs"], r["download"], r["disk"]), (158, "140.6 MiB", "554.8 MiB"))
        r = self.one("zypper --non-interactive update qgis", [(["zypper", "--non-interactive", "update", "--dry-run"], (0, "Nothing to do.\n"))])
        self.assertIsNone(r)                                                       # not "0 changes": nothing was understood

    def test_pacman_install_and_remove(self):
        r = self.one("pacman -S --noconfirm gdal", [(["pacman", "-S", "--print"], (0, PAC_SIM))])
        self.assertEqual((r["installs"], r["download"]), (3, "2.0 MiB"))
        r = self.one("pacman -R --noconfirm numpy", [(["pacman", "-R", "--print"], (0, "python-scipy\npython-numpy\n"))])
        self.assertEqual(r["removes"], ["python-scipy", "python-numpy"])

    def test_apk_and_flatpak(self):
        r = self.one("apk add gdal-tools", [(["apk", "add", "--simulate"], (0, APK_SIM))])
        self.assertEqual((r["installs"], r["download"]), (2, None))
        r = self.one("flatpak install --user -y flathub org.qgis.qgis//stable", [(["flatpak", "remote-info", "--user", "flathub"], (0, FLAT_INFO))])
        self.assertEqual((r["download"], r["disk"]), ("1.4 GB", "4.1 GB"))
        r = self.one("flatpak install --user -y flathub org.qgis.qgis//stable", [(["flatpak", "remote-info"], (0, FLAT_INFO_NBSP))])
        self.assertEqual((r["download"], r["disk"]), ("592.6 MB", "1.6 GB"))               # the no-break space (or its '?') is not part of the size
        self.assertIsNone(self.one("flatpak install --user -y flathub x//y", [(["flatpak"], (1, "error: Remote not found"))]))

    def test_simulation_never_runs_anything_but_the_simulating_forms(self):
        run = answers([])
        for line in ("apt-get install -y a", "apt-get remove -y a", "dnf install -y a", "dnf remove -y a", "zypper --non-interactive install a",
                     "pacman -S --noconfirm a", "pacman -R --noconfirm a", "apk add a", "apk del a", "flatpak install --user -y flathub a"):
            qi.simulate.simulate_line(line, run=run)
        self.assertGreaterEqual(len(run.calls), 10)
        for c in run.calls:
            if c[0] == "apt-get":
                self.assertTrue("-s" in c or "--print-uris" in c, c)
            elif c[0] == "dnf":
                self.assertIn("--assumeno", c)
            elif c[0] == "zypper":
                self.assertIn("--dry-run", c)
            elif c[0] == "pacman":
                self.assertIn("--print", c)
            elif c[0] == "apk":
                self.assertIn("--simulate", c)
            elif c[0] == "flatpak":
                self.assertEqual(c[1], "remote-info")


class SimulateExplain(unittest.TestCase):
    def test_a_plan_is_explained_line_by_line_and_the_unsimulatable_is_counted(self):
        steps = [{"root": True, "sh": "set -eu\napt-get update\napt-get install -y gdal-bin\napt-get install -y nothing-here\n"}]
        run = answers([(["apt-get", "-s", "install", "gdal-bin"], (0, APT_SIM)), (["apt-get", "-qq", "--print-uris"], (0, APT_URIS))])
        res = qi.simulate.explain(steps, run=run)
        self.assertEqual((len(res["items"]), res["unsimulated"], res["warnings"]), (1, 1, []))
        text = qi.simulate.format_text(res, "en")
        self.assertIn("2 to install, 1 to upgrade, download 1.6 MiB", text)
        self.assertIn("1 command(s) could not be simulated", text)
        self.assertIn("nothing is claimed about them", text)

    def test_an_install_that_removes_something_warns(self):
        run = answers([(["apt-get", "-s", "install"], (0, "Remv libold [1]\nInst libnew (2 x [amd64])\n"))])
        res = qi.simulate.explain([{"root": True, "sh": "apt-get install -y libnew\n"}], run=run)
        self.assertEqual(res["warnings"], [("sim_removes_by_install", {"n": 1, "names": "libold"})])
        self.assertIn("! This would also REMOVE 1 package(s): libold", qi.simulate.format_text(res, "en"))

    def test_a_removal_that_drags_qgis_along_is_the_loudest_warning(self):
        run = answers([(["apt-get", "-s", "remove"], (0, "Remv qgis [3.44]\nRemv python3-qgis [3.44]\nRemv python3-numpy [2]\n"))])
        res = qi.simulate.explain([{"root": True, "sh": "apt-get remove -y python3-numpy\n"}], run=run)
        keys = [k for k, _ in res["warnings"]]
        self.assertEqual(keys, ["sim_removes_dependents", "sim_qgis_dragged"])
        self.assertIn("qgis, python3-qgis", res["warnings"][1][1]["names"])
        self.assertIn("This would take QGIS along", qi.simulate.format_text(res, "ka") and qi.simulate.format_text(res, "en"))
        self.assertIn("QGIS-საც წაიღებს", qi.simulate.format_text(res, "ka"))

    def test_removing_exactly_what_was_asked_does_not_warn_and_removing_qgis_itself_is_not_dragging(self):
        run = answers([(["apt-get", "-s", "remove"], (0, "Remv qgis [3.44]\nRemv python3-qgis [3.44]\n"))])
        res = qi.simulate.explain([{"root": True, "sh": "apt-get remove -y qgis python3-qgis\n"}], run=run)
        self.assertEqual(res["warnings"], [])

    def test_nothing_to_say_is_an_empty_text(self):
        self.assertEqual(qi.simulate.format_text(qi.simulate.explain([{"root": True, "sh": "echo hi\n"}]), "en"), "")

    def test_every_text_exists_in_both_languages(self):
        for key in ("sim_head", "sim_install", "sim_upgrade", "sim_remove", "sim_download", "sim_disk", "sim_nothing", "sim_unsimulated",
                    "sim_removes_by_install", "sim_removes_dependents", "sim_qgis_dragged"):
            for lang in ("en", "ka"):
                self.assertIn(key, i18n.STR[lang])


class SimulateCli(unittest.TestCase):
    call = Cli.call
    BASE = ["--lang", "en", "--os-release", os.path.join(FIX, "ubuntu-noble"), "--pm", "apt-get", "--arch", "amd64", "--tools", ""]

    def fake(self):
        return answers([(["apt-get", "-s", "install"], (0, APT_SIM)), (["apt-get", "-qq", "--print-uris"], (0, APT_URIS))])

    def test_the_dry_run_shows_the_simulation_after_the_commands(self):
        with mock.patch.object(qi.simulate, "_run", self.fake()), mock.patch.object(requirements, "is_present", lambda rid, **kw: False):
            rc, out, _ = self.call(*self.BASE, "components", "install", "gdal", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("What the package manager says it would do", out)
        self.assertIn("- apt install: 2 to install, 1 to upgrade, download 1.6 MiB", out)
        self.assertLess(out.index("apt-get install -y gdal-bin"), out.index("What the package manager says"))     # the commands, then what they would do, then the question

    def test_no_simulate_and_json_leave_the_output_as_it_was(self):
        for extra in (["--no-simulate"], ["--json"]):
            with mock.patch.object(qi.simulate, "_run", self.fake()), mock.patch.object(requirements, "is_present", lambda rid, **kw: False):
                rc, out, _ = self.call(*extra, *self.BASE, "components", "install", "gdal", "--dry-run")
            self.assertNotIn("What the package manager says", out)
        doc = json.loads(out)
        self.assertEqual(doc["steps"][0]["sh"].strip().splitlines()[-1], "apt-get install -y gdal-bin")

    def test_update_and_install_plans_show_it_too(self):
        items = [{"kind": "apt", "pkgs": ["qgis"], "v": "3.44", "o": "", "root": True}]
        with mock.patch.object(qi.simulate, "_run", self.fake()), mock.patch.object(uninstall, "find_installs", lambda s: items):
            rc, out, _ = self.call(*self.BASE, "update", "--dry-run")
        self.assertIn("apt install:", out)
        self.assertIn("only-upgrade", out)

    def test_a_package_manager_that_cannot_look_does_not_stop_anything(self):
        with mock.patch.object(requirements, "is_present", lambda rid, **kw: False):
            rc, out, _ = self.call(*self.BASE, "components", "install", "gdal", "--dry-run")      # simulate._run says "cannot tell"
        self.assertEqual(rc, 0)
        self.assertIn("1 command(s) could not be simulated", out)
        self.assertIn("apt-get install -y gdal-bin", out)


# --------------------------------------------------------------------------- versions: choose one, go back, keep it
MADISON = """    qgis | 1:3.44.5+24noble | http://qgis.org/ubuntu-ltr noble/main amd64 Packages
    qgis | 1:3.44.3+24noble | http://qgis.org/ubuntu-ltr noble/main amd64 Packages
    qgis | 1:3.44.3+24noble | http://archive.ubuntu.com/ubuntu noble/universe amd64 Packages
python3-qgis | 1:3.44.5+24noble | http://qgis.org/ubuntu-ltr noble/main amd64 Packages
"""
DNF_LIST5 = """Installed packages
qgis.x86_64 3.44.5-1.fc44 3d628ccc7de241efa0768e20e681b450

Available packages
qgis.x86_64 3.44.1-1.fc44 fedora
qgis.x86_64 3.44.5-1.fc44 updates
qgis.x86_64 3.44.10-1.fc44 updates
"""
ZYP_SEARCH = """Loading repository data...
Reading installed packages...

S  | Name | Type    | Version    | Arch   | Repository
---+------+---------+------------+--------+------------------------
i+ | qgis | package | 3.44.5-9.1 | x86_64 | openSUSE-Tumbleweed-Oss
v  | qgis | package | 3.44.1-1.1 | x86_64 | geo
"""
COMMIT_A, COMMIT_B = "8" * 64, "4" * 64
FLAT_LOG = """        ID: org.qgis.qgis
       Ref: app/org.qgis.qgis/x86_64/stable
  Download: 592.6?MB
 Installed: 1.6?GB

    Commit: {a}
    Parent: {b}
   Subject: patch pdal so it can detect zstd properly (b5b068e1a700)
      Date: 2026-10-13 23:37:12 +0000
   History:

    Commit: {b}
   Subject: Update to SDK 6.11 (1827da20ef01)
      Date: 2026-09-03 19:28:06 +0000
""".format(a=COMMIT_A, b=COMMIT_B)


class VersionsList(unittest.TestCase):
    def test_apt_lists_every_version_once_newest_first_with_where_it_comes_from(self):
        rows = qi.versions.available(dict(APT, v="1:3.44.5+24noble"), run=answers([(["apt-cache", "madison", "qgis"], (0, MADISON))]))["versions"]
        self.assertEqual([r["version"] for r in rows], ["1:3.44.5+24noble", "1:3.44.3+24noble"])
        self.assertEqual([r["installed"] for r in rows], [True, False])
        self.assertIn("qgis.org/ubuntu-ltr", rows[1]["origin"])                                  # the first origin of a duplicated version

    def test_dnf_sorts_by_version_not_as_text_and_marks_the_installed_one(self):
        item = {"kind": "dist", "pm": "dnf", "pkgs": ["qgis"], "v": "3.44.5", "root": True}
        rows = qi.versions.available(item, run=answers([(["dnf", "-q", "list", "--showduplicates", "qgis"], (0, DNF_LIST5))]))["versions"]
        self.assertEqual([r["version"] for r in rows], ["3.44.10-1.fc44", "3.44.5-1.fc44", "3.44.1-1.fc44"])      # 10 > 5 > 1
        self.assertEqual([r["installed"] for r in rows], [False, True, False])
        four = DNF_LIST5.replace("Installed packages", "Installed Packages").replace("Available packages", "Available Packages")
        rows4 = qi.versions.available(item, run=answers([(["dnf"], (0, four))]))["versions"]
        self.assertEqual(len(rows4), 3)

    def test_zypper_reads_the_search_table(self):
        item = {"kind": "dist", "pm": "zypper", "pkgs": ["qgis"], "v": "3.44.5", "root": True}
        rows = qi.versions.available(item, run=answers([(["zypper", "--non-interactive", "search", "-s"], (0, ZYP_SEARCH))]))["versions"]
        self.assertEqual([(r["version"], r["installed"], r["origin"]) for r in rows],
                         [("3.44.5-9.1", True, "openSUSE-Tumbleweed-Oss"), ("3.44.1-1.1", False, "geo")])

    def test_flatpak_lists_builds_not_version_numbers(self):
        rows = qi.versions.available(FP_STABLE, run=answers([(["flatpak", "remote-info", "--log", "--user", "flathub", "org.qgis.qgis//stable"], (0, FLAT_LOG))]))
        self.assertEqual([r["commit"] for r in rows["versions"]], [COMMIT_A, COMMIT_B])
        self.assertTrue(rows["versions"][0]["version"].startswith("2026-10-13"))
        self.assertIn("zstd", rows["versions"][0]["version"])

    def test_flatpak_a_commit_that_the_real_log_repeats_is_listed_once(self):
        twice = FLAT_LOG + "
    Commit: {a}
   Subject: again
      Date: 2026-10-13 23:37:12 +0000
".format(a=COMMIT_A)
        rows = qi.versions.available(FP_STABLE, run=answers([(["flatpak", "remote-info", "--log"], (0, twice))]))
        self.assertEqual([r["commit"] for r in rows["versions"]], [COMMIT_A, COMMIT_B])
        self.assertEqual(rows["note"], "ver_flatpak")

    def test_arch_and_unknown_kinds_say_why_there_is_nothing_to_choose(self):
        self.assertEqual(qi.versions.available(DIST_AUR, run=answers([])), {"versions": [], "note": "ver_arch"})
        self.assertEqual(qi.versions.available(SNAP, run=answers([]))["note"], "ver_unsupported")

    def test_nothing_listed_when_the_tool_failed(self):
        self.assertEqual(qi.versions.available(APT, run=answers([]))["versions"], [])


class VersionsGoTo(unittest.TestCase):
    def test_apt_pins_exactly_the_packages_that_have_that_version_and_allows_the_downgrade(self):
        run = answers([(["apt-cache", "madison", "qgis"], (0, MADISON)), (["apt-cache", "madison", "python3-qgis"], (0, MADISON)),
                       (["apt-cache", "madison", "libqgis3"], (0, ""))])
        item = dict(APT, pkgs=["libqgis3", "python3-qgis", "qgis"])
        r = qi.versions.steps_for(item, {"version": "1:3.44.5+24noble"}, run=run)
        sh = r["steps"][0]["sh"]
        self.assertIn("apt-get install -y --allow-downgrades python3-qgis=1:3.44.5+24noble qgis=1:3.44.5+24noble\n", sh)
        self.assertNotIn("libqgis3", sh)                                        # it has no such version: not forced
        self.assertTrue(r["steps"][0]["root"] and sh_syntax_ok(sh))

    def test_apt_refuses_a_version_the_main_package_does_not_have(self):
        with self.assertRaises(ValueError):
            qi.versions.steps_for(APT, {"version": "9.9"}, run=answers([(["apt-cache", "madison"], (0, MADISON))]))

    def test_dnf_downgrades_when_older_and_installs_when_newer(self):
        item = {"kind": "dist", "pm": "dnf", "pkgs": ["qgis"], "v": "3.44.5-1.fc44", "root": True}
        down = qi.versions.steps_for(item, {"version": "3.44.1-1.fc44", "installed": False})["steps"][0]["sh"]
        up = qi.versions.steps_for(item, {"version": "3.44.10-1.fc44", "installed": False})["steps"][0]["sh"]
        self.assertIn("dnf downgrade -y qgis-3.44.1-1.fc44\n", down)
        self.assertIn("dnf install -y qgis-3.44.10-1.fc44\n", up)

    def test_zypper_allows_the_old_package(self):
        item = {"kind": "dist", "pm": "zypper", "pkgs": ["qgis"], "v": "3.44.5-9.1", "root": True}
        sh = qi.versions.steps_for(item, {"version": "3.44.1-1.1"})["steps"][0]["sh"]
        self.assertIn("zypper --non-interactive install --oldpackage qgis=3.44.1-1.1\n", sh)

    def test_flatpak_goes_to_a_commit_in_the_right_scope_and_refuses_a_made_up_one(self):
        user = qi.versions.steps_for(FP_STABLE, {"version": "x", "commit": COMMIT_B})["steps"][0]
        self.assertEqual((user["root"], "flatpak update --user -y --commit=" + COMMIT_B + " org.qgis.qgis//stable" in user["sh"]), (False, True))
        sysm = qi.versions.steps_for(FP_LTS, {"version": "x", "commit": COMMIT_A})["steps"][0]
        self.assertTrue(sysm["root"] and "--system" in sysm["sh"] and "org.qgis.qgis//lts" in sysm["sh"])
        for bad in ({"version": "x", "commit": "../../etc"}, {"version": "x", "commit": "abc"}, {"version": "x"}):
            with self.assertRaises(ValueError):
                qi.versions.steps_for(FP_STABLE, bad)

    def test_no_way_for_arch_or_snap(self):
        for item in (DIST_AUR, SNAP):
            with self.assertRaises(ValueError):
                qi.versions.steps_for(item, {"version": "1"})

    def test_a_version_string_cannot_inject_a_command(self):
        run = answers([(["apt-cache", "madison"], (0, "qgis | 1; rm -rf ~ | x\n"))])
        r = qi.versions.steps_for(APT, {"version": "1; rm -rf ~"}, run=run)
        self.assertIn("'qgis=1; rm -rf ~'", r["steps"][0]["sh"])                  # one quoted word, not a second command
        self.assertTrue(sh_syntax_ok(r["steps"][0]["sh"]))


class VersionsKeep(unittest.TestCase):
    def test_state_of_every_mechanism(self):
        self.assertIs(qi.versions.lock_state(APT, run=answers([(["apt-mark", "showhold"], (0, "qgis\ntzdata\n"))])), True)
        self.assertIs(qi.versions.lock_state(APT, run=answers([(["apt-mark", "showhold"], (0, "tzdata\n"))])), False)
        self.assertIsNone(qi.versions.lock_state(APT, run=answers([])))                             # could not ask: not "free"
        self.assertIs(qi.versions.lock_state(FP_STABLE, run=answers([(["flatpak", "mask", "--user"], (0, "org.qgis.qgis//stable\n"))])), True)
        self.assertIs(qi.versions.lock_state(FP_STABLE, run=answers([(["flatpak", "mask", "--user"], (0, ""))])), False)
        zy = {"kind": "dist", "pm": "zypper", "pkgs": ["qgis"], "v": "1", "root": True}
        locks = "# | Name | Type    | Repository | Comment\n--+------+---------+------------+--------\n1 | qgis | package | (any)      | \n"
        self.assertIs(qi.versions.lock_state(zy, run=answers([(["zypper", "--non-interactive", "locks"], (0, locks))])), True)
        self.assertIs(qi.versions.lock_state(zy, run=answers([(["zypper", "--non-interactive", "locks"], (0, "No locks defined.\n"))])), False)
        self.assertIsNone(qi.versions.lock_state(DIST_AUR, run=answers([])))
        dnf = {"kind": "dist", "pm": "dnf", "pkgs": ["qgis"], "v": "1", "root": True}
        five = "# Added by 'versionlock add' command on 2026-10-15 12:10:57\nPackage name: qgis\nevr = 3.44.5-1.fc44\n"
        four = "qgis-0:3.44.5-1.fc44.*\nbash-0:5.1.8-6.fc.*\n"
        for out in (five, four):
            self.assertIs(qi.versions.lock_state(dnf, run=answers([(["dnf", "versionlock", "list"], (0, out))])), True, out)
        other = "Package name: qgis-server\nevr = 1\n"
        self.assertIs(qi.versions.lock_state(dnf, run=answers([(["dnf", "versionlock", "list"], (0, other))])), False)
        self.assertIs(qi.versions.lock_state(dnf, run=answers([(["dnf", "versionlock", "list"], (0, ""))])), False)
        self.assertIsNone(qi.versions.lock_state(dnf, run=answers([(["dnf", "versionlock", "list"], (1, "Unknown command"))])))

    def test_hold_and_release_commands(self):
        L = qi.versions.lock_steps
        self.assertIn("apt-mark hold python3-qgis qgis\n", L(APT, True)["steps"][0]["sh"])
        self.assertIn("apt-mark unhold python3-qgis qgis\n", L(APT, False)["steps"][0]["sh"])
        self.assertIn("flatpak mask --user org.qgis.qgis//stable\n", L(FP_STABLE, True)["steps"][0]["sh"])
        self.assertIn("flatpak mask --system --remove org.qgis.qgis//lts\n", L(FP_LTS, False)["steps"][0]["sh"])
        self.assertTrue(L(FP_LTS, True)["steps"][0]["root"] and not L(FP_STABLE, True)["steps"][0]["root"])
        zy = {"kind": "dist", "pm": "zypper", "pkgs": ["qgis"], "v": "1", "root": True}
        self.assertIn("zypper --non-interactive addlock qgis\n", L(zy, True)["steps"][0]["sh"])
        dnf = dict(zy, pm="dnf")
        self.assertIn("dnf versionlock add qgis\n", L(dnf, True)["steps"][0]["sh"])
        self.assertIn("lock_dnf_plugin", L(dnf, True)["notes"])
        arch = L(DIST_AUR, True)
        self.assertEqual(arch["steps"], [])                                      # no command exists: instructions only
        self.assertIn("IgnorePkg = qgis-ltr", arch["manual"][0]["text"])
        for item in (APT, FP_STABLE, zy, dnf):
            for lock in (True, False):
                self.assertTrue(sh_syntax_ok(L(item, lock)["steps"][0]["sh"]))

    def test_every_text_exists_in_both_languages(self):
        for key in ("ver_none", "ver_installed", "ver_unknown_version", "ver_head", "ver_title", "rcw_ver_downgrade", "rcw_ver_flatpak",
                    "rcw_ver_arch", "rcw_ver_unsupported", "rcw_lock_dnf_plugin", "rcw_lock_arch", "rcw_lock_unsupported", "rcm_lock_arch",
                    "lock_kept", "lock_free", "lock_unknown", "lock_title_on", "lock_title_off"):
            for lang in ("en", "ka"):
                self.assertIn(key, i18n.STR[lang])


class VersionsCli(unittest.TestCase):
    call = Cli.call
    BASE = ["--lang", "en", "--os-release", os.path.join(FIX, "ubuntu-noble"), "--pm", "apt-get", "--arch", "amd64", "--tools", ""]

    def run_cmd(self, *argv, items=(APT,), table=()):
        run = answers(list(table) or [(["apt-cache", "madison"], (0, MADISON)), (["apt-mark", "showhold"], (0, "qgis\n"))])
        with mock.patch.object(uninstall, "find_installs", lambda s: list(items)), mock.patch.object(qi.versions, "_run", run), \
                mock.patch.object(qi.instances.shutil, "which", have("qgis", "flatpak")):
            return self.call(*self.BASE, *argv)

    def test_versions_lists_with_the_installed_mark_the_keep_state_and_the_note(self):
        rc, out, _ = self.run_cmd("versions", "apt", items=(dict(APT, v="1:3.44.5+24noble"),))
        self.assertEqual(rc, 0)
        self.assertRegex(out, r"1:3.44.5\+24noble +\(installed\)")
        self.assertIn("1:3.44.3+24noble", out)
        self.assertIn("version kept (not updated)", out)
        self.assertIn("Going back to an older version can fail", out)

    def test_versions_json(self):
        rc, out, _ = self.run_cmd("--json", "versions", "apt")
        doc = json.loads(out)
        self.assertEqual((doc["id"], doc["locked"], [v["version"] for v in doc["versions"]]), ("apt", True, ["1:3.44.5+24noble", "1:3.44.3+24noble"]))

    def test_install_version_shows_commands_and_refuses_a_version_not_in_the_list(self):
        rc, out, _ = self.run_cmd("install-version", "apt", "1:3.44.3+24noble", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("apt-get install -y --allow-downgrades", out)
        self.assertIn("qgis=1:3.44.3+24noble", out)
        rc, _, err = self.run_cmd("install-version", "apt", "9.9", "--dry-run")
        self.assertEqual(rc, 2)
        self.assertIn("Version '9.9' is not in the list. Choose one of: 1:3.44.5+24noble, 1:3.44.3+24noble", err)

    def test_hold_and_unhold_and_unknown_ids(self):
        rc, out, _ = self.run_cmd("hold", "apt", "--dry-run")
        self.assertIn("apt-mark hold python3-qgis qgis", out)
        rc, out, _ = self.run_cmd("unhold", "apt", "--dry-run")
        self.assertIn("apt-mark unhold python3-qgis qgis", out)
        rc, _, err = self.run_cmd("hold", "nope")
        self.assertEqual(rc, 2)
        self.assertIn("Unknown installation 'nope'", err)
        rc, out, _ = self.run_cmd("hold", "dist-pacman-qgis-ltr", items=(DIST_AUR,), table=[(["x"], (0, ""))])
        self.assertEqual(rc, 0)                                                  # instructions only: nothing to run
        self.assertIn("IgnorePkg = qgis-ltr", out)

    def test_instances_shows_whether_a_version_is_kept(self):
        rc, out, _ = self.run_cmd("instances")                                   # the fake apt-mark says qgis is held
        self.assertEqual(rc, 0)
        self.assertIn("[apt] [version kept]", out)
        rc, out, _ = self.run_cmd("instances", table=[(["apt-mark", "showhold"], (0, "tzdata\n"))])
        self.assertNotIn("version kept", out)                                    # free: no marker
        rc, out, _ = self.run_cmd("instances", table=[(["x"], (1, ""))])
        self.assertNotIn("version kept", out)                                    # could not ask: no claim either way
        rc, out, _ = self.run_cmd("--json", "instances")
        self.assertIs(json.loads(out)["instances"][0]["locked"], True)


# --------------------------------------------------------------------------- environment files
REPO_UBUNTU_LTR = {"kind": "repo", "files": ["/etc/apt/sources.list.d/qgis.sources"], "c": " \u2014 ubuntu-ltr", "root": True}


def comp_rows(pm="apt-get", present=()):
    return requirements.components(pm, which=lambda t: "/x/" + t if t in present else None,
                                   find_spec=lambda m: object() if m in present else None)


class EnvExport(unittest.TestCase):
    TODAY = datetime.date(2026, 10, 15)

    def export(self, items, present=("gdalinfo", "ogr2ogr", "numpy"), name=""):
        return qi.envspec.export_spec(items, comp_rows(present=present), name, today=self.TODAY)

    def test_apt_with_the_qgis_repository_and_its_channel(self):
        spec = self.export([dict(APT, v="1:3.44.5+24noble"), REPO_UBUNTU_LTR], name="GIS lab")
        self.assertEqual(spec["qgis"], {"goal": "stable", "recipe": "apt-official", "options": {"channel": "ltr"}, "version": "1:3.44.5+24noble"})
        self.assertEqual((spec["schema"], spec["name"], spec["created"]), (1, "GIS lab", "2026-10-15"))
        self.assertEqual(spec["components"], ["gdal", "numpy"])

    def test_the_channel_is_read_from_the_repository_url_for_every_variant(self):
        for url, channel, goal in (("ubuntu", "latest", "latest"), ("debian-ltr", "ltr", "stable"), ("ubuntugis-ltr", "ltr", "stable"),
                                   ("ubuntu-nightly-ltr", "nightly-ltr", "stable"), ("debian-nightly-release", "nightly-release", "latest"),
                                   ("ubuntu-nightly", "nightly", "latest")):
            spec = self.export([APT, dict(REPO_UBUNTU_LTR, c=" \u2014 " + url)])
            self.assertEqual((spec["qgis"]["options"]["channel"], spec["qgis"]["goal"]), (channel, goal), url)

    def test_apt_without_the_repository_is_the_distribution_package(self):
        self.assertEqual(self.export([APT])["qgis"]["recipe"], "apt-distro")

    def test_the_other_kinds_and_nothing(self):
        self.assertEqual(self.export([FP_LTS])["qgis"], {"goal": "stable", "recipe": "flatpak", "options": {"branch": "lts", "scope": "system"}, "version": "3.44.5"})
        self.assertEqual(self.export([FP_STABLE])["qgis"]["goal"], "latest")
        self.assertEqual(self.export([{"kind": "dist", "pm": "dnf", "pkgs": ["qgis"], "v": "3.44.1", "root": True}])["qgis"]["recipe"], "dnf-fedora")
        self.assertEqual(self.export([BOX])["qgis"], {"goal": "alongside", "recipe": "distrobox", "options": {}})
        self.assertIsNone(self.export([])["qgis"])
        self.assertIsNone(self.export([{"kind": "dist", "pm": "urpmi", "pkgs": ["qgis"], "v": "1", "root": True}])["qgis"])
        self.assertEqual(self.export([], present=())["components"], [])

    def test_the_export_is_a_valid_file_and_survives_a_round_trip(self):
        spec = self.export([dict(APT, v="1:3.44.5+24noble"), REPO_UBUNTU_LTR], name="x")
        again = qi.envspec.validate(json.loads(json.dumps(spec)))
        self.assertEqual(again, spec)
        for items in ([FP_LTS], [BOX], [], [APT]):
            qi.envspec.validate(self.export(items))


class EnvValidate(unittest.TestCase):
    def good(self, **over):
        doc = {"schema": 1, "name": "lab", "created": "2026-10-15", "components": ["gdal"],
               "qgis": {"goal": "stable", "recipe": "apt-official", "options": {"channel": "ltr"}, "version": "3.44.5"}}
        doc.update(over)
        return doc

    def bad(self, doc, needle):
        with self.assertRaises(qi.envspec.SpecError) as cm:
            qi.envspec.validate(doc)
        self.assertIn(needle, str(cm.exception))

    def test_a_good_file_is_accepted_and_duplicates_collapse(self):
        v = qi.envspec.validate(self.good(components=["gdal", "numpy", "gdal"]))
        self.assertEqual(v["components"], ["gdal", "numpy"])
        self.assertEqual(qi.envspec.validate({"schema": 1})["qgis"], None)              # only the schema is required

    def test_the_shape_of_the_file(self):
        self.bad([], "one JSON object")
        self.bad(self.good(schema=2), "schema must be 1")
        self.bad(dict(self.good(), extra=1), "unknown field")
        self.bad(self.good(name="a\nb"), "name")
        self.bad(self.good(name=5), "name")
        self.bad(self.good(created="yesterday"), "created")
        self.bad(self.good(components="gdal"), "list")
        self.bad(self.good(components=[5]), "list")
        self.bad(self.good(components=["gdal", "rm -rf ~"]), "unknown component")
        self.bad(self.good(qgis="apt"), "qgis must be")

    def test_the_qgis_part_only_holds_names_from_closed_lists(self):
        def q(**kw):
            base = {"goal": "stable", "recipe": "apt-official", "options": {}}
            base.update(kw)
            return self.good(qgis=base)
        self.bad(q(extra=1), "unknown field")
        self.bad(q(goal="best"), "goal")
        self.bad(q(recipe="apt-official; rm -rf ~"), "unknown recipe")
        self.bad(q(recipe=["x"]), "unknown recipe")
        self.bad(q(options=[]), "options")
        self.bad(q(options={"branch": "lts"}), "not an option of recipe")                  # a Flatpak option on an apt recipe
        self.bad(q(options={"channel": "../etc"}), "channel")
        self.bad(q(options={"channel": ["ltr"]}), "channel")
        self.bad(q(options={5: 1}), "not an option")
        self.bad(q(goal=["stable"]), "goal")
        self.bad(q(recipe={"a": 1}), "unknown recipe")
        self.bad(q(recipe="flatpak", options={"branch": ["lts"]}), "branch")
        self.bad(q(recipe="flatpak", options={"scope": {"x": 1}}), "scope")
        self.bad(q(recipe="flatpak", options={"branch": "dev"}), "branch")
        self.bad(q(recipe="flatpak", options={"scope": "root"}), "scope")
        self.bad(q(recipe="distrobox", options={"image": "x; rm -rf ~"}), "image")
        self.bad(q(recipe="distrobox", options={"image": "$(id)"}), "image")
        self.bad(q(recipe="zypper-opensuse", options={"geo_repo": "yes"}), "true or false")
        self.bad(q(version="1; rm -rf ~"), "version")
        self.bad(q(version=3), "version")
        ok = qi.envspec.validate(q(recipe="distrobox", options={"image": "registry.opensuse.org/opensuse/toolbox:latest"}))
        self.assertEqual(ok["qgis"]["options"]["image"], "registry.opensuse.org/opensuse/toolbox:latest")

    def test_a_null_recipe_is_allowed_it_means_use_the_goal(self):
        v = qi.envspec.validate(self.good(qgis={"goal": "latest", "recipe": None, "options": {}}))
        self.assertEqual(v["qgis"]["recipe"], None)


# --------------------------------------------------------------------------- the doctor
D = qi.doctor


class DoctorShadowing(unittest.TestCase):
    def test_a_user_copy_that_hides_a_system_copy_is_found(self):
        with tempfile.TemporaryDirectory() as d:
            user, system = os.path.join(d, "user"), os.path.join(d, "system")
            for base, names in ((user, ("numpy", "osgeo", "mylib")), (system, ("numpy", "pandas", "mylib"))):
                for n in names:
                    os.makedirs(os.path.join(base, n))
            found = D.check_shadowing([user], [system])
            self.assertEqual([(lvl, key, p["name"]) for lvl, key, p in found], [("warn", "shadowing", "numpy")])
            self.assertEqual((found[0][2]["user"], found[0][2]["system"]), (os.path.join(user, "numpy"), os.path.join(system, "numpy")))

    def test_no_finding_without_both_copies_or_for_libraries_that_are_not_watched(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "user", "numpy"))
            os.makedirs(os.path.join(d, "system", "mylib"))
            os.makedirs(os.path.join(d, "user", "mylib"))
            self.assertEqual(D.check_shadowing([os.path.join(d, "user")], [os.path.join(d, "system")]), [])     # numpy only in user; mylib not watched
            self.assertEqual(D.check_shadowing([], [os.path.join(d, "system")]), [])

    def test_the_users_folders_are_found_for_every_python_version(self):
        with tempfile.TemporaryDirectory() as d:
            for v in ("python3.11", "python3.13"):
                os.makedirs(os.path.join(d, ".local", "lib", v, "site-packages"))
            os.makedirs(os.path.join(d, ".local", "lib", "python2.7", "site-packages"))
            got = D.user_site_dirs(d)
            self.assertEqual([os.path.basename(os.path.dirname(x)) for x in got], ["python3.11", "python3.13"])


class DoctorChecks(unittest.TestCase):
    def test_gdal_versions_are_compared_by_major_and_minor(self):
        self.assertEqual(D.check_gdal("GDAL 3.10.3, released 2025/04/01", "3.8.4"),
                         [("warn", "gdal_mismatch", {"cli": "3.10", "py": "3.8"})])
        self.assertEqual(D.check_gdal("GDAL 3.8.4, released 2024/02/08", "3.8.1"), [])        # another patch level is fine
        self.assertEqual(D.check_gdal("", "3.8.4"), [])
        self.assertEqual(D.check_gdal("GDAL 3.8.4", None), [])                                  # not known: no claim

    def test_python_gdal_version_asks_the_interpreter(self):
        run = answers([(["python3", "-c"], (0, "3.8.4\n"))])
        self.assertEqual(D.python_gdal_version(run=run), "3.8.4")
        self.assertIsNone(D.python_gdal_version(run=answers([])))

    def test_proj_folder_that_is_missing_or_has_no_database(self):
        with tempfile.TemporaryDirectory() as d:
            good, nodb = os.path.join(d, "good"), os.path.join(d, "nodb")
            os.makedirs(good)
            os.makedirs(nodb)
            open(os.path.join(good, "proj.db"), "wb").close()
            self.assertEqual(D.check_proj({"PROJ_LIB": good}), [])
            self.assertEqual(D.check_proj({}), [])
            self.assertEqual([(l, k) for l, k, _ in D.check_proj({"PROJ_LIB": os.path.join(d, "gone")})], [("problem", "proj_missing")])
            self.assertEqual([(l, k) for l, k, _ in D.check_proj({"PROJ_DATA": nodb})], [("problem", "proj_nodb")])
            both = D.check_proj({"PROJ_DATA": good + os.pathsep + nodb, "PROJ_LIB": os.path.join(d, "gone")})
            self.assertEqual(sorted(k for _l, k, _ in both), ["proj_missing", "proj_nodb"])

    def test_repository_file_of_another_release(self):
        text = "Types: deb\nURIs: https://qgis.org/ubuntu-ltr\nSuites: jammy\nComponents: main\n"
        self.assertEqual(D.check_repo(text, "noble"), [("problem", "repo_old", {"suite": "jammy", "codename": "noble"})])
        self.assertEqual(D.check_repo(text, "jammy"), [])
        self.assertEqual(D.check_repo("Types: deb\n", "noble"), [])                              # no Suites line: no claim
        self.assertEqual(D.check_repo(text, ""), [])

    def test_dpkg_audit(self):
        self.assertEqual(D.check_dpkg(""), [])
        self.assertEqual(D.check_dpkg("\n"), [])
        f = D.check_dpkg("The following packages are only half configured:\n qgis\n")
        self.assertEqual((f[0][0], f[0][1]), ("problem", "dpkg_broken"))
        self.assertIn("half configured", f[0][2]["first"])

    def test_disk_space(self):
        usage = lambda path: type("U", (), {"free": {"/home/u": 200 * 1024 ** 2, "/var": 50 * 1024 ** 3}[path]})()  # noqa: E731
        f = D.check_disk([("profile", "/home/u"), ("packages", "/var")], usage=usage, exists=lambda p: True)
        self.assertEqual([(l, k, p["where"], p["free"]) for l, k, p in f], [("warn", "disk_low", "/home/u", "200 MB")])
        self.assertEqual(D.check_disk([("profile", "/nowhere")], usage=usage, exists=lambda p: False), [])

    def test_installations_that_share_a_profile(self):
        self.assertEqual(D.check_sources([APT, BOX]), [("info", "shared_profile", {"n": 2})])
        self.assertEqual(D.check_sources([APT, FP_STABLE, FP_LTS, SNAP]), [])                   # Flatpak and Snap keep their own
        self.assertEqual(D.check_sources([APT]), [])


class DoctorRun(unittest.TestCase):
    def run_all(self, items=(), sysinfo=None, table=(), python_gdal=None, **kw):
        sysinfo = sysinfo or {"apt": True, "code": "noble"}
        kw.setdefault("home", "/nonexistent-home")
        kw.setdefault("user_dirs", [])
        kw.setdefault("system_dirs", [])
        kw.setdefault("usage", lambda p: type("U", (), {"free": 50 * 1024 ** 3})())
        kw.setdefault("exists", lambda p: True)
        return D.run_all(list(items), sysinfo, env=kw.pop("env", {}), run=answers(list(table)), python_gdal=python_gdal, **kw)

    def test_everything_that_was_looked_at_is_listed_and_a_clean_system_has_no_findings(self):
        res = self.run_all(table=[(["gdalinfo"], (0, "GDAL 3.8.4, released 2024")), (["dpkg", "--audit"], (0, ""))], python_gdal="3.8.4",
                           read=lambda path: "Suites: noble\n")
        self.assertEqual(res["findings"], [])
        self.assertEqual(res["ran"], ["shadowing", "gdal", "proj", "repo", "dpkg", "disk", "sources"])
        self.assertEqual(res["skipped"], [])

    def test_what_could_not_be_looked_at_is_said_not_passed_over(self):
        res = self.run_all(table=[(["dpkg", "--audit"], (1, ""))], python_gdal=None)                     # no gdalinfo, dpkg unusable, no repo file
        self.assertEqual(res["skipped"], ["gdal", "repo", "dpkg"])
        self.assertNotIn("gdal", res["ran"])

    def test_non_apt_systems_skip_the_apt_checks(self):
        res = self.run_all(sysinfo={"apt": False, "code": ""}, python_gdal="3.8.4", table=[(["gdalinfo"], (0, "GDAL 3.8.4"))])
        self.assertEqual(res["ran"], ["shadowing", "gdal", "proj", "disk", "sources"])

    def test_findings_come_worst_first(self):
        with tempfile.TemporaryDirectory() as d:
            for base in ("u", "s"):
                os.makedirs(os.path.join(d, base, "numpy"))
            res = self.run_all(items=[APT, BOX], table=[(["gdalinfo"], (0, "GDAL 3.10.3")), (["dpkg", "--audit"], (0, "half configured\n"))],
                               python_gdal="3.8.4", env={"PROJ_LIB": "/nowhere"}, user_dirs=[os.path.join(d, "u")], system_dirs=[os.path.join(d, "s")],
                               exists=lambda p: p != "/nowhere" and os.path.exists(p) or p == d, read=lambda p: "Suites: jammy\n")
        levels = [lvl for lvl, _k, _p in res["findings"]]
        self.assertEqual(levels, sorted(levels, key=["problem", "warn", "info"].index))
        keys = {k for _l, k, _p in res["findings"]}
        self.assertEqual(keys, {"shadowing", "gdal_mismatch", "proj_missing", "repo_old", "dpkg_broken", "shared_profile"})


class DoctorCli(unittest.TestCase):
    call = Cli.call
    BASE = ["--lang", "en", "--os-release", os.path.join(FIX, "ubuntu-noble"), "--pm", "apt-get", "--arch", "amd64", "--tools", ""]

    def run_doctor(self, findings, ran=("shadowing", "proj"), skipped=(), *argv):
        res = {"findings": findings, "ran": list(ran), "skipped": list(skipped)}
        with mock.patch.object(uninstall, "find_installs", lambda s: []), mock.patch.object(D, "run_all", lambda items, sysinfo, **kw: res):
            return self.call(*self.BASE, *argv, "doctor")

    def test_a_clean_result_exits_0_and_says_what_was_looked_at(self):
        rc, out, _ = self.run_doctor([], skipped=("gdal",))
        self.assertEqual(rc, 0)
        self.assertIn("What the doctor looked at: Python libraries hidden by your own copies, PROJ data folder.", out)
        self.assertIn("No problem found in what was looked at.", out)
        self.assertIn("Not looked at (not available here): GDAL tools against GDAL for Python.", out)

    def test_a_problem_exits_1_a_warning_does_not(self):
        rc, out, _ = self.run_doctor([("problem", "proj_missing", {"var": "PROJ_LIB", "path": "/x"})])
        self.assertEqual(rc, 1)
        self.assertIn("[PROBLEM] PROJ_LIB points to /x, which does not exist", out)
        rc, out, _ = self.run_doctor([("warn", "disk_low", {"where": "/home/u", "free": "200 MB"})])
        self.assertEqual(rc, 0)
        self.assertIn("[warning] Only 200 MB free in /home/u", out)

    def test_json_and_georgian(self):
        rc, out, _ = self.run_doctor([("info", "shared_profile", {"n": 2})], ("sources",), (), "--json")
        doc = json.loads(out)
        self.assertEqual((rc, doc["findings"][0][1], doc["ran"]), (0, "shared_profile", ["sources"]))
        res = {"findings": [("problem", "repo_old", {"suite": "jammy", "codename": "noble"})], "ran": ["repo"], "skipped": []}
        with mock.patch.object(uninstall, "find_installs", lambda s: []), mock.patch.object(D, "run_all", lambda items, sysinfo, **kw: res):
            rc, out, _ = self.call("--lang", "ka", *self.BASE[2:], "doctor")
        self.assertEqual(rc, 1)
        self.assertIn("[პრობლემა]", out)
        self.assertIn("„jammy“-ისთვისაა", out)

    def test_every_finding_and_check_has_a_text_in_both_languages(self):
        keys = ["shadowing", "gdal_mismatch", "proj_missing", "proj_nodb", "repo_old", "dpkg_broken", "disk_low", "shared_profile"]
        for lang in ("en", "ka"):
            for k in keys:
                self.assertIn("doc_" + k, i18n.STR[lang])
            for c in ("shadowing", "gdal", "proj", "repo", "dpkg", "disk", "sources"):
                self.assertIn("doc_chk_" + c, i18n.STR[lang])
            for lvl in ("problem", "warn", "info"):
                self.assertIn("doc_level_" + lvl, i18n.STR[lang])


class Packaging(unittest.TestCase):
    def test_the_version_is_the_same_in_the_package_and_in_pyproject(self):
        try:
            import tomllib
        except ImportError:                                                     # Python before 3.11 has no TOML reader
            self.skipTest("no tomllib")
        with open(os.path.join(ROOT, "qgis-installer", "pyproject.toml"), "rb") as fh:
            meta = tomllib.load(fh)
        self.assertEqual(meta["project"]["version"], qi.__version__)
        self.assertEqual(meta["project"]["scripts"], {"qgis-installer-cli": "qgis_installer.cli:main"})
        self.assertEqual(meta["tool"]["setuptools"]["packages"], ["qgis_installer"])
        self.assertEqual(meta["project"]["dependencies"], [])                    # standard library only

    def test_every_module_of_the_package_is_packaged(self):
        folder = os.path.join(ROOT, "qgis-installer", "qgis_installer")
        self.assertEqual(sorted(f for f in os.listdir(folder) if f.endswith(".py"))[:2], ["__init__.py", "__main__.py"])
        for f in os.listdir(folder):
            self.assertFalse(os.path.isdir(os.path.join(folder, f)) and f != "__pycache__", f)    # a sub-package would need listing in pyproject

    def test_version_flag(self):
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(io.StringIO()) as out:
            qcli.main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(out.getvalue().strip(), "qgis-installer " + qi.__version__)


# --------------------------------------------------------------------------- what the plugins import
PS = qi.pluginscan


def make_plugin(base, name, files, metadata=True):
    root = os.path.join(base, name)
    for rel, text in files.items():
        path = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    if metadata:
        with open(os.path.join(root, "metadata.txt"), "w", encoding="utf-8") as fh:
            fh.write("[general]\nname=" + name + "\n")
    return root


class PluginScan(unittest.TestCase):
    def scan(self, files):
        with tempfile.TemporaryDirectory() as d:
            return PS.scan_plugin(make_plugin(d, "myplug", files))

    def test_required_optional_and_what_is_not_third_party(self):
        sc = self.scan({"__init__.py": "import os, json\nimport numpy as np\nfrom openpyxl.styles import Font\nfrom qgis.core import QgsProject\n"
                                       "from PyQt5.QtCore import Qt\nimport processing\nfrom . import local\n",
                        "local.py": "import requests\n"})
        self.assertEqual((sc["required"], sc["optional"]), ({"numpy", "openpyxl", "requests"}, set()))

    def test_imports_in_functions_and_guarded_by_import_error_are_optional(self):
        sc = self.scan({"a.py": "import numpy\n"
                                "def f():\n    import pandas\n"
                                "class K:\n    import yaml\n"
                                "try:\n    import lxml\nexcept ImportError:\n    lxml = None\n"
                                "try:\n    import PIL\nexcept ModuleNotFoundError:\n    PIL = None\n"
                                "try:\n    import jinja2\nexcept Exception:\n    jinja2 = None\n"
                                "try:\n    import sqlalchemy\nexcept:\n    pass\n"
                                "try:\n    import shapely\nexcept ValueError:\n    pass\n"})
        self.assertEqual(sc["required"], {"numpy", "yaml", "shapely"})              # a class body runs at import; ValueError is no import guard
        self.assertEqual(sc["optional"], {"pandas", "lxml", "PIL", "jinja2", "sqlalchemy"})

    def test_type_checking_imports_never_run(self):
        sc = self.scan({"a.py": "from typing import TYPE_CHECKING\nimport typing\nif TYPE_CHECKING:\n    import numpy\n"
                                "if typing.TYPE_CHECKING:\n    import scipy\nelse:\n    import pandas\n"})
        self.assertEqual((sc["required"], sc["optional"]), ({"pandas"}, set()))

    def test_the_plugins_own_modules_and_packages_are_not_third_party_wherever_they_are(self):
        sc = self.scan({"__init__.py": "import i18n\nimport core.thing\nimport myplug\nimport openpyxl\n", "i18n.py": "import deep_lib\n",
                        "core/__init__.py": "", "core/thing.py": "from tools import helper\n", "gui/tools/helper.py": "import numpy\n"})
        self.assertEqual(sc["required"], {"openpyxl", "deep_lib", "numpy"})          # i18n, core, tools and the plugin's own name are local

    def test_tests_and_docs_and_pycache_are_not_read_and_unreadable_files_are_reported(self):
        sc = self.scan({"a.py": "import numpy\n", "tests/t.py": "import pytest\n", "docs/conf.py": "import sphinx\n", "__pycache__/x.py": "import junk\n",
                        "broken.py": "def (:\n"})
        self.assertEqual((sc["required"], sc["unreadable"]), ({"numpy"}, ["broken.py"]))

    def test_relative_imports_and_star_imports_and_dotted_names(self):
        sc = self.scan({"a.py": "from . import b\nfrom .b import c\nfrom .. import d\nimport scipy.stats.distributions\nfrom shapely.geometry import *\n"})
        self.assertEqual(sc["required"], {"scipy", "shapely"})

    def test_a_place_that_is_not_there_is_an_error_not_nothing(self):
        with self.assertRaises(FileNotFoundError):
            PS.scan_plugin("/nowhere/at/all")

    def test_the_scan_never_runs_the_plugin(self):
        with tempfile.TemporaryDirectory() as d:
            marker = os.path.join(d, "ran")
            root = make_plugin(d, "evil", {"__init__.py": "open(%r, 'w').write('x')\nimport numpy\n" % marker})
            PS.scan_plugin(root)
            PS.report([d], "apt-get", find_spec=lambda m: None)
            self.assertFalse(os.path.exists(marker))


class PluginMissing(unittest.TestCase):
    def test_missing_uses_the_importer_it_is_given(self):
        sc = {"required": {"numpy", "nonsense_mod"}, "optional": {"openpyxl"}}
        res = PS.missing(sc, find_spec=lambda m: object() if m == "numpy" else None)
        self.assertEqual(res, {"required": ["nonsense_mod"], "optional": ["openpyxl"]})
        boom = PS.missing({"required": {"x"}, "optional": set()}, find_spec=lambda m: (_ for _ in ()).throw(ValueError("bad")))
        self.assertEqual(boom["required"], ["x"])                                  # a module that cannot even be looked up counts as missing

    def test_packages_for_what_is_missing_and_what_has_none(self):
        comp, manual = PS.packages(["osgeo", "openpyxl", "yaml", "PIL", "somethingrare"], "apt-get")
        self.assertEqual(comp, {"gdal-python": ["python3-gdal"], "openpyxl": ["python3-openpyxl"], "pyyaml": ["python3-yaml"], "pillow": ["python3-pil"]})
        self.assertEqual(manual, ["somethingrare"])
        comp, manual = PS.packages(["rasterio", "yaml"], "pacman")
        self.assertEqual((comp, manual), ({"pyyaml": ["python-yaml"]}, ["rasterio"]))                  # Arch has no package for rasterio
        self.assertEqual(PS.packages(["yaml"], "zypper", "313")[0], {"pyyaml": ["python313-PyYAML"]})
        self.assertEqual(PS.packages(["yaml"], "")[0], {})

    def test_every_module_in_the_table_is_a_real_component_with_a_matching_module_name(self):
        for module, rid in PS.MODULE_TO_COMPONENT.items():
            self.assertIn(rid, requirements.REQ, module)
            self.assertEqual(requirements.REQ[rid]["module"], module)

    def test_report_lists_only_plugins_that_lack_something(self):
        with tempfile.TemporaryDirectory() as d:
            make_plugin(d, "needs_yaml", {"__init__.py": "import yaml\nimport numpy\n"})
            make_plugin(d, "fine", {"__init__.py": "import numpy\n"})
            make_plugin(d, "optional_only", {"__init__.py": "def f():\n    import openpyxl\n"})
            make_plugin(d, "not_a_plugin", {"x.py": "import yaml\n"}, metadata=False)
            res = PS.report([d], "apt-get", find_spec=lambda m: object() if m == "numpy" else None)
        self.assertEqual(res["checked"], 3)                                         # the folder without metadata.txt is not a plugin
        rows = {r["plugin"]: r for r in res["rows"]}
        self.assertEqual(sorted(rows), ["needs_yaml", "optional_only"])
        self.assertEqual((rows["needs_yaml"]["required_missing"], rows["needs_yaml"]["components"]), (["yaml"], {"pyyaml": ["python3-yaml"]}))
        self.assertEqual((rows["optional_only"]["required_missing"], rows["optional_only"]["optional_missing"]), ([], ["openpyxl"]))


class PluginDepsCli(unittest.TestCase):
    call = Cli.call
    BASE = ["--lang", "en", "--os-release", os.path.join(FIX, "ubuntu-noble"), "--pm", "apt-get", "--arch", "amd64", "--tools", ""]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        make_plugin(self.tmp.name, "needs_yaml", {"__init__.py": "import yaml\n"})
        make_plugin(self.tmp.name, "wants_xlsx", {"__init__.py": "def f():\n    import openpyxl\n    import rare_thing\n"})

    def run_cmd(self, *argv):
        with mock.patch.object(PS.importlib.util, "find_spec", lambda m: None):
            return self.call(*self.BASE, "plugin-deps", "--dir", self.tmp.name, *argv)

    def test_the_report_says_who_needs_what_and_how_to_get_it_and_exits_1_for_a_required_one(self):
        rc, out, _ = self.run_cmd()
        self.assertEqual(rc, 1)
        self.assertIn("Plugins checked: 2.", out)
        self.assertIn("needs_yaml: does not load without yaml", out)
        self.assertIn("-> install with the system: python3-yaml", out)
        self.assertIn("wants_xlsx: works without openpyxl, rare_thing but with less", out)
        self.assertIn("-> no package for this system: rare_thing", out)

    def test_optional_only_exits_0(self):
        with open(os.path.join(self.tmp.name, "needs_yaml", "__init__.py"), "w") as fh:
            fh.write("pass\n")
        rc, out, _ = self.run_cmd()
        self.assertEqual(rc, 0)

    def test_install_shows_the_commands_for_what_has_a_package_and_skips_the_optional_unless_asked(self):
        rc, out, _ = self.run_cmd("--install", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("apt-get install -y python3-yaml", out)
        self.assertNotIn("openpyxl", out.split("These commands will run")[1])
        rc, out, _ = self.run_cmd("--install", "--optional", "--dry-run")
        self.assertIn("apt-get install -y python3-yaml python3-openpyxl", out)
        self.assertNotIn("rare_thing", out.split("These commands will run")[1])           # nothing for it: never guessed

    def test_json_nothing_missing_and_no_folder(self):
        with mock.patch.object(PS.importlib.util, "find_spec", lambda m: None):
            rc, out, _ = self.call("--json", *self.BASE, "plugin-deps", "--dir", self.tmp.name)
        doc = json.loads(out)
        self.assertEqual(doc["checked"], 2)
        self.assertEqual(sorted(r["plugin"] for r in doc["rows"]), ["needs_yaml", "wants_xlsx"])
        self.assertEqual(doc["rows"][0]["components"] or doc["rows"][1]["components"], {"pyyaml": ["python3-yaml"]} if doc["rows"][0]["plugin"] == "needs_yaml" else {"openpyxl": ["python3-openpyxl"]})
        rc, _, err = self.call(*self.BASE, "plugin-deps", "--dir", "/nowhere/plugins")
        self.assertEqual(rc, 2)
        self.assertIn("No QGIS plugin folder was found", err)

    def test_default_folders_cover_the_profiles_of_qgis_3_and_4_and_of_the_flatpak(self):
        with tempfile.TemporaryDirectory() as home:
            for rel in (".local/share/QGIS/QGIS3/profiles/default/python/plugins", ".local/share/QGIS/QGIS4/profiles/work/python/plugins",
                        ".var/app/org.qgis.qgis/data/QGIS/QGIS3/profiles/default/python/plugins"):
                os.makedirs(os.path.join(home, *rel.split("/")))
            got = [os.path.relpath(p, home).replace("\\", "/") for p in qcli.default_plugin_roots(home)]
            self.assertEqual(len(got), 3)
            self.assertTrue(any("QGIS4/profiles/work" in g for g in got) and any(g.startswith(".var/app/org.qgis.qgis") for g in got))

    def test_the_texts_exist_in_both_languages(self):
        for key in ("pd_head", "pd_none", "pd_required", "pd_optional", "pd_install", "pd_manual", "pd_unreadable", "pd_no_plugins", "pd_nothing_to_install"):
            for lang in ("en", "ka"):
                self.assertIn(key, i18n.STR[lang])


class GeorgianStyle(unittest.TestCase):
    def test_no_comma_before_the_word_da_in_any_georgian_text(self):
        """The house rule: no comma before the conjunction "da" ("and"). A word that merely starts with it (da-nart...) is not the conjunction."""
        hits = [k for k, v in i18n.STR["ka"].items() if isinstance(v, str) and re.search("," + " " + "და" + r"(?![ა-ჰ])", v)]
        self.assertEqual(hits, [])


class EnvFuzz(unittest.TestCase):
    """A file passed around between machines: whatever it holds, the answer is a clean SpecError or a valid spec - never a crash."""

    def junk(self, rnd, depth=0):
        pick = rnd.randrange(12 if depth < 3 else 8)
        if pick == 0:
            return None
        if pick == 1:
            return rnd.choice([True, False])
        if pick == 2:
            return rnd.randrange(-5, 10**6)
        if pick == 3:
            return rnd.random() * 1e9
        if pick == 4:
            return rnd.choice(["", "stable", "ltr", "latest", "apt-official", "flatpak", "gdal", "numpy", "user", "system", "../../x", "x; rm -rf ~",
                               "$(id)", "\n", "\x00", "3.44.5", "2026-10-15", "a" * 300, "\u10d0\u10d1"])
        if pick == 5:
            return rnd.choice(list(__import__("qgis_installer").recipes.RECIPES))
        if pick in (6, 7):
            return rnd.choice(["schema", "name", "components", "qgis", "options", "channel", "branch", "scope", "image", "grass", "x"])
        if pick in (8, 9):
            return [self.junk(rnd, depth + 1) for _ in range(rnd.randrange(4))]
        return {rnd.choice(["schema", "name", "created", "components", "qgis", "goal", "recipe", "options", "version", "channel", "branch",
                            "scope", "image", "grass", "python", "server", "geo_repo", "extra"]): self.junk(rnd, depth + 1)
                for _ in range(rnd.randrange(6))}

    def test_ten_thousand_random_files(self):
        import random
        rnd = random.Random(20261015)
        ok = bad = 0
        for _ in range(10000):
            doc = {"schema": 1 if rnd.random() < 0.8 else self.junk(rnd)}
            for key in ("name", "created", "components", "qgis"):
                if rnd.random() < 0.6:
                    doc[key] = self.junk(rnd)
            if rnd.random() < 0.7:
                doc["qgis"] = {"goal": self.junk(rnd) if rnd.random() < 0.3 else "stable", "recipe": self.junk(rnd),
                               "options": {rnd.choice(["channel", "branch", "scope", "image", "grass", "x"]): self.junk(rnd) for _ in range(rnd.randrange(3))},
                               "version": self.junk(rnd)}
            before = json.dumps(doc, default=str, sort_keys=True)
            try:
                out = qi.envspec.validate(doc)
                ok += 1
                json.dumps(out)                                                   # what comes out is plain JSON data again
                self.assertTrue(out["components"] == [c for c in out["components"] if c in qi.envspec.component_ids()])
                if out["qgis"]:
                    self.assertIn(out["qgis"]["goal"], qi.recipes.GOALS)
                    self.assertTrue(out["qgis"]["recipe"] is None or out["qgis"]["recipe"] in qi.recipes.RECIPES)
            except qi.envspec.SpecError:
                bad += 1
            self.assertEqual(json.dumps(doc, default=str, sort_keys=True), before)       # the input is never changed
        self.assertGreater(ok, 20)                                                # the generator does hit valid files...
        self.assertGreater(bad, 5000)                                             # ...and mostly invalid ones


class EnvPlan(unittest.TestCase):
    def spec(self, **kw):
        return qi.envspec.validate(dict({"schema": 1, "components": ["gdal", "numpy"],
                                        "qgis": {"goal": "stable", "recipe": "apt-official", "options": {"channel": "ltr"}, "version": "3.44.5"}}, **kw))

    def test_check_tells_missing_ok_version_and_unavailable(self):
        rows = comp_rows(present=("numpy",))
        st = qi.envspec.check(self.spec(), [], rows)
        self.assertEqual((st["qgis"]["state"], st["components_missing"], st["components_ok"]), ("missing", ["gdal"], ["numpy"]))
        st = qi.envspec.check(self.spec(), [dict(APT, v="1:3.44.5+24noble")], rows)
        self.assertEqual(st["qgis"], {"state": "ok", "installed": "1:3.44.5+24noble"})
        st = qi.envspec.check(self.spec(), [dict(APT, v="1:3.40.1+24noble")], rows)
        self.assertEqual((st["qgis"]["state"], st["qgis"]["wanted"]), ("version", "3.44.5"))
        self.assertEqual(qi.envspec.check(self.spec(qgis=None), [], rows)["qgis"], {"state": "none"})
        un = qi.envspec.check(self.spec(components=["rasterio"]), [], comp_rows("pacman"))                  # Arch has no package for it
        self.assertEqual((un["components_missing"], un["unavailable"]), ([], ["rasterio"]))

    def test_the_plan_installs_qgis_with_the_recipe_and_the_missing_components(self):
        d = fxt("ubuntu-noble", "apt-get")
        res = qi.envspec.plan(self.spec(), [], comp_rows(present=("numpy",)), d)
        self.assertEqual(res["recipe"], "apt-official")
        text = "\n".join(st["sh"] for st in res["steps"])
        self.assertIn("qgis.org", text)                                                    # the official repository is set up
        self.assertIn("apt-get install -y gdal-bin\n", text)                               # only what is missing
        self.assertNotIn("python3-numpy", text.split("qgis.org")[-1].split("gdal-bin")[-1])
        for st in res["steps"]:
            self.assertTrue(sh_syntax_ok(st["sh"]), st["sh"])

    def test_an_ubuntu_file_on_fedora_uses_what_fedora_recommends_for_the_same_goal(self):
        d = fxt("fedora-43", "dnf")
        res = qi.envspec.plan(self.spec(), [], comp_rows("dnf"), d)
        self.assertEqual(res["recipe"], "dnf-fedora")
        self.assertIn("env_recipe_swapped", res["notes"])
        self.assertIn("dnf install -y qgis python3-qgis qgis-grass", "\n".join(st["sh"] for st in res["steps"]))

    def test_a_machine_that_already_matches_gets_no_steps(self):
        d = fxt("ubuntu-noble", "apt-get")
        res = qi.envspec.plan(self.spec(), [dict(APT, v="1:3.44.5+24noble")], comp_rows(present=("gdalinfo", "ogr2ogr", "numpy")), d)
        self.assertEqual((res["steps"], res["manual"], res["notes"]), ([], [], []))

    def test_another_installed_version_is_reported_not_forced(self):
        d = fxt("ubuntu-noble", "apt-get")
        res = qi.envspec.plan(self.spec(components=[]), [dict(APT, v="1:3.40.1+24noble")], comp_rows(), d)
        self.assertEqual((res["steps"], res["notes"]), ([], ["env_version_differs"]))

    def test_instructions_only_recipes_and_no_recipe_at_all(self):
        nix = qi.envspec.validate({"schema": 1, "components": [], "qgis": {"goal": "stable", "recipe": "nix-manual", "options": {}}})
        res = qi.envspec.plan(nix, [], comp_rows(""), fxt("nixos", ""))
        self.assertEqual(res["steps"], [])
        self.assertIn("nix-shell", res["manual"][0]["text"])
        res = qi.envspec.plan(self.spec(), [], comp_rows(""), fxt("slackware", "", tools=()))
        self.assertIn("env_recipe_swapped", res["notes"])
        self.assertIn("env_no_recipe", res["notes"]) if res["recipe"] is None else None

    def test_nothing_from_the_file_but_closed_names_reaches_a_command(self):
        evil = {"schema": 1, "name": "$(touch /tmp/pwned)", "created": "2026-10-15", "components": ["gdal"],
                "qgis": {"goal": "stable", "recipe": "apt-official", "options": {"channel": "ltr"}, "version": "3.44.5"}}
        res = qi.envspec.plan(qi.envspec.validate(evil), [], comp_rows(), fxt("ubuntu-noble", "apt-get"))
        self.assertNotIn("pwned", "\n".join(st["sh"] for st in res["steps"]))             # the free text of the file is never used


class EnvCli(unittest.TestCase):
    call = Cli.call
    BASE = ["--lang", "en", "--os-release", os.path.join(FIX, "ubuntu-noble"), "--pm", "apt-get", "--arch", "amd64", "--tools", ""]

    def write(self, d, doc, name="env.json"):
        path = os.path.join(d, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(doc if isinstance(doc, str) else json.dumps(doc))
        return path

    def run_env(self, *argv, items=(), present=()):
        with mock.patch.object(uninstall, "find_installs", lambda s: list(items)), \
                mock.patch.object(requirements, "is_present", lambda rid, **kw: rid in present):
            return self.call(*self.BASE, *argv)

    DOC = {"schema": 1, "name": "lab", "components": ["gdal", "numpy"],
           "qgis": {"goal": "stable", "recipe": "apt-official", "options": {"channel": "ltr"}, "version": "3.44.5"}}

    def test_export_to_stdout_and_to_a_file(self):
        rc, out, _ = self.run_env("env", "export", "--name", "lab", items=[dict(APT, v="1:3.44.5+24noble"), REPO_UBUNTU_LTR], present=("numpy",))
        doc = json.loads(out)
        self.assertEqual((rc, doc["qgis"]["recipe"], doc["components"], doc["name"]), (0, "apt-official", ["numpy"], "lab"))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.json")
            rc, out, _ = self.run_env("env", "export", "--output", path, items=[APT])
            self.assertIn("Written: " + path, out)
            with open(path, encoding="utf-8") as fh:
                qi.envspec.validate(json.load(fh))

    def test_check_reports_and_the_exit_code_says_whether_something_is_missing(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.write(d, self.DOC)
            rc, out, _ = self.run_env("env", "check", path, present=("numpy",))
            self.assertEqual(rc, 1)
            self.assertIn("QGIS: not installed, the file asks for one", out)
            self.assertIn("Components: 1 of 2 present", out)
            self.assertIn("to install: GDAL command line tools", out)
            rc, out, _ = self.run_env("env", "check", path, items=[dict(APT, v="1:3.44.5+24noble")], present=("gdal", "numpy"))
            self.assertEqual(rc, 0)
            self.assertIn("installed (1:3.44.5+24noble), as the file asks", out)
            rc, out, _ = self.run_env("--json", "env", "check", path, present=("numpy",))
            doc = json.loads(out)
            self.assertEqual((doc["qgis"]["state"], doc["components_missing"]), ("missing", ["gdal"]))

    def test_apply_shows_the_plan_and_runs_nothing_on_a_dry_run(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(runner, "run_steps") as run:
            path = self.write(d, self.DOC)
            rc, out, _ = self.run_env("env", "apply", path, "--dry-run", present=("numpy",))
        self.assertEqual(rc, 0)
        self.assertIn("qgis.org", out)
        self.assertIn("apt-get install -y gdal-bin", out)
        self.assertRegex(out, r"\d+ command\(s\) could not be simulated")    # (the host's package manager is not asked in tests)
        run.assert_not_called()

    def test_apply_on_a_machine_that_matches_says_so(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.write(d, self.DOC)
            rc, out, _ = self.run_env("env", "apply", path, "--yes", items=[dict(APT, v="1:3.44.5+24noble")], present=("gdal", "numpy"))
        self.assertEqual(rc, 0)
        self.assertIn("This machine already matches the file.", out)

    def test_bad_files_are_refused_with_a_reason_and_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            for label, doc, needle in (("json", "{not json", "Not a valid environment file"),
                                       ("recipe", dict(self.DOC, qgis={"goal": "stable", "recipe": "x; rm -rf ~", "options": {}}), "unknown recipe"),
                                       ("component", dict(self.DOC, components=["gdal", "evil"]), "unknown component"),
                                       ("big", " " * (65 * 1024), "larger than 64 KB")):
                path = self.write(d, doc, label + ".json")
                for cmd in ("check", "apply"):
                    rc, out, err = self.run_env("env", cmd, path)
                    self.assertEqual(rc, 2, (label, cmd))
                    self.assertIn(needle, err)
                    self.assertEqual(out, "")                                  # nothing printed, nothing run
            rc, _, err = self.run_env("env", "check", os.path.join(d, "nope.json"))
            self.assertEqual(rc, 2)
            self.assertIn("Cannot read", err)

    def test_georgian(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.write(d, self.DOC)
            with mock.patch.object(uninstall, "find_installs", lambda s: []), mock.patch.object(requirements, "is_present", lambda rid, **kw: False):
                rc, out, _ = self.call("--lang", "ka", *self.BASE[2:], "env", "check", path)
        self.assertIn("დაყენებული არ არის", out)
        self.assertIn("კომპონენტები: 0 / 2 არის", out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
