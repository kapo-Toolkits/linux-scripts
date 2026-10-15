#!/usr/bin/env python3
"""Offline tests of the qgis_installer core package and its command line (no root, no network, no display).

    python3 tests/test_qgis_installer.py

The distribution matrix comes from tests/fixtures/os-release/*; the real apt/qgis.org behaviour is covered by
tests/qgis_container_test.py (run in throw-away containers).
"""
import contextlib
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
