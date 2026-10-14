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
from qgis_installer import cli as qcli, i18n, plan, runner, system, uninstall  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "os-release")
HAVE_SH = shutil.which("sh") is not None


def fx(name, pm="apt-get", arch="amd64"):
    return qi.detect(os.path.join(FIX, name), pm, arch)


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
    NOBLE = ["--os-release", os.path.join(FIX, "ubuntu-noble"), "--pm", "apt-get", "--arch", "amd64"]
    FEDORA = ["--os-release", os.path.join(FIX, "fedora-43"), "--pm", "dnf", "--arch", "amd64"]

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
        self.assertEqual(doc["methods"], {"A": True, "B": True, "C": True})
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
        rc, out, _ = self.call("--json", *self.FEDORA, "plan")          # not possible there: Flatpak
        self.assertIn("flatpak", "".join(s["sh"] for s in json.loads(out)["steps"]))

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


if __name__ == "__main__":
    unittest.main(verbosity=1)
