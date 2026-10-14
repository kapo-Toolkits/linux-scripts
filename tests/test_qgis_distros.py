#!/usr/bin/env python3
"""Offline tests of the distribution-specific QGIS paths from the installation guide: Fedora (+ Atomic),
openSUSE (+ immutable), Arch (+ AUR), containers (Distrobox / Toolbx) and Nix.

    python3 tests/test_qgis_distros.py

Tool presence (distrobox, yay, nix-shell ...) is injected, so the results do not depend on the host.
"""
import contextlib
import io
import os
import subprocess
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "qgis-installer"))

import qgis_installer as qi  # noqa: E402
from qgis_installer import cli as qcli, i18n, system, uninstall  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "os-release")
PK = {"grass": True, "python": True, "server": False}


def fx(name, pm="", tools=(), ostree=False):
    """Detect a fixture system with an injected PATH and /run/ostree-booted."""
    return qi.detect(os.path.join(FIX, name), pm, "amd64",
                     which=lambda c: "/usr/bin/" + c if c in tools else None,
                     exists=lambda p: ostree and p == "/run/ostree-booted")


def sh_ok(script):
    return subprocess.run(["sh", "-n", "-c", script], capture_output=True).returncode == 0


def plan(method, d, channel="latest", **pk):
    return qi.build_install(method, d, channel, dict(PK, **pk))


class Detection(unittest.TestCase):
    def test_fedora_atomic_and_suse_immutable_and_nix(self):
        self.assertTrue(fx("fedora-silverblue-43", "dnf")["atomic"])          # VARIANT_ID=silverblue
        self.assertTrue(fx("fedora-43", "dnf", ostree=True)["atomic"])        # /run/ostree-booted
        self.assertFalse(fx("fedora-43", "dnf")["atomic"])
        self.assertFalse(fx("ubuntu-noble", "apt-get", ostree=True)["atomic"])  # ostree on a non-Fedora base: not rpm-ostree
        self.assertTrue(fx("opensuse-microos", "zypper")["suse_immutable"])
        self.assertFalse(fx("opensuse-tumbleweed", "zypper")["suse_immutable"])
        self.assertTrue(fx("nixos")["nix"])
        self.assertTrue(fx("ubuntu-noble", "apt-get", tools=("nix-shell",))["nix"])
        self.assertFalse(fx("ubuntu-noble", "apt-get")["nix"])

    def test_tools(self):
        self.assertEqual(fx("arch", "pacman", tools=("yay", "paru"))["aur_helper"], "yay")
        self.assertEqual(fx("arch", "pacman", tools=("paru",))["aur_helper"], "paru")
        self.assertEqual(fx("arch", "pacman")["aur_helper"], "")
        self.assertEqual(fx("ubuntu-noble", "apt-get", tools=("yay",))["aur_helper"], "")   # AUR only on pacman
        self.assertEqual(fx("fedora-43", "dnf", tools=("distrobox", "toolbox"))["container_tool"], "distrobox")
        self.assertEqual(fx("fedora-43", "dnf", tools=("toolbox",))["container_tool"], "toolbox")

    def test_method_availability(self):
        d = fx("fedora-43", "dnf", tools=("toolbox", "nix-shell"))
        self.assertEqual([qi.method_available(m, d) for m in qi.METHODS], [False, True, True, True, True])
        d = fx("fedora-43", "dnf")
        self.assertEqual([qi.method_available(m, d) for m in "DE"], [False, False])
        atomic = fx("fedora-silverblue-43", "")                              # no dnf at all, still installable
        self.assertTrue(qi.method_available("C", atomic))

    def test_channels_per_method(self):
        self.assertEqual(qi.channels_for("A", fx("ubuntu-noble", "apt-get")), qi.LTR_ONLY_CHANNELS)
        self.assertEqual(qi.channels_for("B", fx("arch", "pacman")), [])
        self.assertEqual(qi.channels_for("C", fx("fedora-43", "dnf")), [])
        self.assertEqual(qi.channels_for("C", fx("opensuse-tumbleweed", "zypper")), ["latest", "ltr"])
        self.assertEqual(qi.channels_for("C", fx("arch", "pacman")), [])      # no AUR helper -> only the official qgis
        self.assertEqual(qi.channels_for("C", fx("arch", "pacman", tools=("yay",))), ["latest", "ltr", "nightly"])
        self.assertEqual(qi.channels_for("E", fx("nixos")), ["latest", "ltr"])
        self.assertEqual(qi.channels_for("D", fx("opensuse-microos", "zypper", tools=("distrobox",))), ["latest", "ltr"])
        self.assertEqual(qi.channels_for("D", fx("fedora-43", "dnf", tools=("toolbox",))), [])


class Plans(unittest.TestCase):
    def test_fedora_follows_the_guide(self):
        s = plan("C", fx("fedora-43", "dnf"), server=True)
        self.assertEqual(len(s), 1)
        self.assertTrue(s[0]["root"])
        self.assertIn("dnf install -y qgis python3-qgis qgis-grass qgis-server\n", s[0]["sh"])
        self.assertIn("dnf install -y qgis\n", plan("C", fx("fedora-43", "dnf"), grass=False, python=False)[0]["sh"])

    def test_fedora_atomic_layers_with_rpm_ostree(self):
        s = plan("C", fx("fedora-silverblue-43", "dnf"))
        self.assertIn("rpm-ostree install --idempotent qgis python3-qgis qgis-grass", s[0]["sh"])
        self.assertIn("Reboot", s[0]["sh"])
        self.assertTrue(sh_ok(s[0]["sh"]))

    def test_opensuse_stable_and_ltr(self):
        d = fx("opensuse-tumbleweed", "zypper")
        self.assertIn("zypper --non-interactive install qgis qgis-plugin-grass\n", plan("C", d, "latest")[0]["sh"])
        self.assertIn("zypper --non-interactive install qgis-ltr qgis-plugin-grass\n", plan("C", d, "ltr")[0]["sh"])

    def test_arch_official_and_aur(self):
        plain = fx("arch", "pacman")
        s = plan("C", plain, "latest")
        self.assertTrue(s[0]["root"] and "pacman -S --noconfirm qgis\n" in s[0]["sh"])
        self.assertIn("pacman -S --noconfirm qgis\n", plan("C", plain, "ltr")[0]["sh"])      # no helper: official one
        yay = fx("arch", "pacman", tools=("yay",))
        s = plan("C", yay, "ltr")
        self.assertEqual((s[0]["root"], s[0]["sh"]), (False, "set -eu\nyay -S --needed qgis-ltr\n"))   # AUR: as the user
        self.assertIn("yay -S --needed qgis-git", plan("C", yay, "nightly")[0]["sh"])
        self.assertIn("paru -S --needed qgis-git", plan("C", fx("arch", "pacman", tools=("paru",)), "nightly")[0]["sh"])

    def test_nix_runs_qgis_without_installing(self):
        d = fx("nixos")
        self.assertEqual(plan("E", d, "latest"), [{"root": False, "sh": "set -eu\nnix-shell -p qgis --command qgis\n"}])
        self.assertIn("nix-shell -p qgis-ltr --command qgis", plan("E", d, "ltr")[0]["sh"])

    def test_distrobox_on_opensuse_uses_the_guides_image(self):
        d = fx("opensuse-microos", "zypper", tools=("distrobox",))
        s = plan("D", d, "ltr")
        self.assertEqual([x["root"] for x in s], [False])                      # nothing needs the host's root
        sh = s[0]["sh"]
        self.assertIn("--image registry.opensuse.org/opensuse/toolbox:latest", sh)
        self.assertIn("distrobox enter --name qgis-box -- sudo zypper --non-interactive install qgis-ltr qgis-plugin-grass", sh)
        self.assertIn("distrobox-export --app qgis", sh)
        self.assertIn("grep -q 'qgis-box'", sh)                                # re-running does not fail on an existing box

    def test_toolbox_and_distrobox_on_fedora_use_the_hosts_release(self):
        d = fx("fedora-silverblue-43", "dnf", tools=("toolbox",))
        sh = plan("D", d)[0]["sh"]
        self.assertIn("toolbox create --container qgis-box --image registry.fedoraproject.org/fedora-toolbox:43", sh)
        self.assertIn("toolbox run --container qgis-box sudo dnf install -y qgis python3-qgis qgis-grass", sh)
        d = fx("fedora-silverblue-43", "dnf", tools=("distrobox",))
        sh = plan("D", d)[0]["sh"]
        self.assertIn("fedora-toolbox:43", sh)
        self.assertIn("sudo dnf install -y", sh)

    def test_no_container_tool_no_plan(self):
        self.assertEqual(plan("D", fx("fedora-43", "dnf")), [])

    def test_every_new_script_parses(self):
        cases = [("C", fx("fedora-43", "dnf")), ("C", fx("fedora-silverblue-43", "dnf")),
                 ("C", fx("opensuse-tumbleweed", "zypper")), ("C", fx("arch", "pacman", tools=("yay",))),
                 ("D", fx("opensuse-microos", "zypper", tools=("distrobox",))),
                 ("D", fx("fedora-43", "dnf", tools=("toolbox",))), ("E", fx("nixos"))]
        for method, d in cases:
            for channel in ("latest", "ltr", "nightly"):
                for server in (False, True):
                    for s in plan(method, d, channel, server=server):
                        self.assertTrue(sh_ok(s["sh"]), (method, d["name"], channel, s["sh"]))


class Removal(unittest.TestCase):
    def test_remove_steps_for_the_new_kinds(self):
        d = fx("arch", "pacman")
        steps = uninstall.build_remove_steps(
            [{"kind": "dist", "pm": "pacman", "pkgs": ["qgis", "qgis-ltr"], "v": "1", "root": True},
             {"kind": "container", "tool": "distrobox", "name": "qgis-box", "root": False}], False, False, d)
        root = [s for s in steps if s["root"]][0]["sh"]
        user = [s for s in steps if not s["root"]][0]["sh"]
        self.assertIn("pacman -R --noconfirm qgis qgis-ltr", root)
        self.assertIn("distrobox rm --force qgis-box", user)
        steps = uninstall.build_remove_steps([{"kind": "dist", "pm": "rpm-ostree", "pkgs": ["qgis"], "v": "1", "root": True}],
                                             False, False, d)
        self.assertIn("rpm-ostree uninstall qgis", steps[0]["sh"])
        for s in steps:
            self.assertTrue(sh_ok(s["sh"]))

    def test_legacy_dist_items_still_work(self):                                  # items without "pkgs"
        steps = uninstall.build_remove_steps([{"kind": "dist", "pm": "dnf", "v": "1", "root": True}], False, False,
                                             fx("fedora-43", "dnf"))
        self.assertIn("dnf remove -y qgis", steps[0]["sh"])

    def test_container_names_are_validated(self):
        steps = uninstall.build_remove_steps([{"kind": "container", "tool": "distrobox", "name": "x; rm -rf ~", "root": False},
                                              {"kind": "container", "tool": "rm", "name": "qgis-box", "root": False}],
                                             False, False, fx("fedora-43", "dnf"))
        self.assertEqual(steps, [])                                                # injection / unknown tool: nothing runs

    def test_find_installs_sees_a_container_and_aur_packages(self):
        def fake_run(cmd):
            if cmd[:2] == ["distrobox", "list"]:
                return 0, "ID | NAME | STATUS\n1 | qgis-box | Up\n"
            if cmd[:2] == ["pacman", "-Q"]:
                return (0, f"{cmd[2]} 3.44.1-1") if cmd[2] in ("qgis", "qgis-ltr") else (1, "")
            return 1, ""
        with mock.patch.object(uninstall, "_run", fake_run), \
                mock.patch.object(uninstall.shutil, "which", lambda c: "/usr/bin/" + c if c in ("distrobox",) else None), \
                mock.patch.object(uninstall.os.path, "isdir", return_value=False):
            items = uninstall.find_installs(fx("arch", "pacman"))
        kinds = {i["kind"]: i for i in items}
        self.assertEqual(kinds["dist"]["pkgs"], ["qgis", "qgis-ltr"])
        self.assertEqual((kinds["container"]["tool"], kinds["container"]["name"]), ("distrobox", "qgis-box"))
        for it in items:
            self.assertTrue(i18n.label_for(it, "en") and i18n.label_for(it, "ka"))


class Texts(unittest.TestCase):
    def test_both_languages_have_the_same_keys(self):
        self.assertEqual(set(i18n.STR["en"]), set(i18n.STR["ka"]))

    def test_new_keys_format(self):
        for lang in ("en", "ka"):
            for k in ("mD", "mE", "ch_latest_dist", "ch_ltr_dist", "ch_nightly_dist", "st_atomic", "st_suse_imm", "st_nix"):
                self.assertTrue(i18n.t(k, lang))
            self.assertIn("yay", i18n.t("st_aur", lang, h="yay"))
            self.assertIn("qgis-box", i18n.t("k_container", lang, tool="distrobox", name="qgis-box"))


class Cli(unittest.TestCase):
    def call(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = qcli.main(list(argv))
            except SystemExit as e:
                rc = e.code
        return rc, out.getvalue(), err.getvalue()

    SUSE = ["--os-release", os.path.join(FIX, "opensuse-tumbleweed"), "--pm", "zypper", "--arch", "amd64"]

    def test_channel_validation_per_method(self):
        rc, out, _ = self.call("--lang", "en", *self.SUSE, "plan", "--method", "C", "--channel", "ltr", "--script")
        self.assertEqual(rc, 0)
        self.assertIn("qgis-ltr", out)
        rc, _, err = self.call("--lang", "en", *self.SUSE, "plan", "--method", "C", "--channel", "nightly")
        self.assertEqual(rc, 2)
        self.assertIn("not offered", err)

    def test_info_lists_all_methods(self):
        import json
        rc, out, _ = self.call("--json", *self.SUSE, "info")
        doc = json.loads(out)
        self.assertEqual(sorted(doc["methods"]), list(qi.METHODS))
        self.assertEqual(doc["method_channels"]["C"], ["latest", "ltr"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
