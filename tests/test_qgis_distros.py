#!/usr/bin/env python3
"""Offline tests of the distribution-specific QGIS paths of the installation guide: Fedora (+ Atomic), openSUSE
(+ immutable), Arch (+ AUR), containers (Distrobox / Toolbx) and Nix - their scripts and their removal.

    python3 tests/test_qgis_distros.py

The recipes themselves (applicability, recommendation, plans) are tested in test_qgis_installer.py; this file checks
what only matters for the immutable / container / AUR flows: every generated script parses, re-running is safe,
and the uninstaller finds and removes exactly what these recipes create. Tools are injected, so nothing depends on the host.
"""
import os
import subprocess
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "qgis-installer"))

from qgis_installer import i18n, recipes, system, uninstall  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "os-release")


def fx(name, pm="", tools=(), immutable=None):
    return system.detect(os.path.join(FIX, name), pm, "amd64", tools={t: True for t in tools}, immutable=immutable or "none")


def sh_ok(script):
    return subprocess.run(["sh", "-n", "-c", script], capture_output=True).returncode == 0


class Scripts(unittest.TestCase):
    def test_fedora_atomic_layers_idempotently_and_says_to_reboot(self):
        d = fx("fedora-silverblue-43", "dnf", tools=("rpm-ostree",), immutable="ostree")
        sh = recipes.make_plan("rpm-ostree-fedora", d)["steps"][0]["sh"]
        self.assertIn("rpm-ostree install --idempotent qgis python3-qgis qgis-grass", sh)
        self.assertIn("Reboot", sh)
        self.assertTrue(sh_ok(sh))

    def test_a_container_is_not_created_twice(self):
        for rid, tool, cmd in (("distrobox", "distrobox", "distrobox list | grep -q qgis-box || distrobox create"),
                               ("toolbx", "toolbox", "toolbox list --containers | grep -q qgis-box || toolbox create")):
            sh = recipes.make_plan(rid, fx("fedora-43", "dnf", tools=(tool,)))["steps"][0]["sh"]
            self.assertIn(cmd, sh)

    def test_toolbx_on_fedora_is_pinned_to_the_hosts_release_elsewhere_it_is_the_guides_image(self):
        sh = recipes.make_plan("toolbx", fx("fedora-silverblue-43", "dnf", tools=("toolbox",), immutable="ostree"))["steps"][0]["sh"]
        self.assertIn("registry.fedoraproject.org/fedora-toolbox:43", sh)
        sh = recipes.make_plan("toolbx", fx("opensuse-microos", "zypper", tools=("toolbox",), immutable="transactional"))["steps"][0]["sh"]
        self.assertIn(recipes.TOOLBX_IMAGE, sh)
        sh = recipes.make_plan("toolbx", fx("fedora-43", "dnf", tools=("toolbox",)), {"image": "example.org/x:1"})["steps"][0]["sh"]
        self.assertIn("example.org/x:1", sh)                                     # an explicit image wins

    def test_every_script_of_every_recipe_parses(self):
        systems = [fx("fedora-43", "dnf", tools=("flatpak", "distrobox", "toolbox", "spack")),
                   fx("fedora-silverblue-43", "dnf", tools=("rpm-ostree", "toolbox"), immutable="ostree"),
                   fx("opensuse-tumbleweed", "zypper", tools=("distrobox",)),
                   fx("opensuse-microos", "zypper", tools=("distrobox",), immutable="transactional"),
                   fx("arch", "pacman", tools=("yay",)), fx("arch", "pacman", tools=("paru",)),
                   fx("mageia-9", "", tools=("urpmi",)), fx("nixos"), fx("slackware"),
                   fx("ubuntu-noble", "apt-get"), fx("debian-trixie", "apt-get")]
        variants = [{}, {"server": True}, {"grass": False, "python": False}, {"channel": "testing"}, {"branch": "lts", "scope": "system"},
                    {"geo_repo": True}]
        seen = 0
        for d in systems:
            for rid, r in recipes.RECIPES.items():
                if not recipes.applicability(rid, d)[0]:
                    continue
                for o in variants:
                    try:
                        plan = recipes.make_plan(rid, d, o)
                    except ValueError:
                        continue                                               # an option this recipe does not have
                    for s in plan["steps"]:
                        seen += 1
                        self.assertTrue(sh_ok(s["sh"]), (rid, d["name"], o, s["sh"]))
        self.assertGreater(seen, 40)                                           # the loop really looked at scripts


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

    def test_the_box_the_recipes_create_is_the_box_the_uninstaller_looks_for(self):
        self.assertEqual(recipes.BOX, system.CONTAINER_BOX)
        for rid in ("distrobox", "toolbx"):
            sh = recipes.make_plan(rid, fx("fedora-43", "dnf", tools=("distrobox", "toolbox")))["steps"][0]["sh"]
            self.assertIn(system.CONTAINER_BOX, sh)

    def test_find_installs_sees_a_container_aur_packages_and_a_layered_package(self):
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

        def rpm_run(cmd):
            return (0, "3.44.1") if cmd[:2] == ["rpm", "-q"] and cmd[-1] == "qgis" else (1, "")
        with mock.patch.object(uninstall, "_run", rpm_run), \
                mock.patch.object(uninstall.shutil, "which", lambda c: "/usr/bin/" + c if c == "rpm" else None), \
                mock.patch.object(uninstall.os.path, "isdir", return_value=False):
            items = uninstall.find_installs(fx("fedora-silverblue-43", "", tools=("rpm-ostree",), immutable="ostree"))
        dist = [i for i in items if i["kind"] == "dist"]
        self.assertEqual([(i["pm"], i["pkgs"]) for i in dist], [("rpm-ostree", ["qgis"])])


class Texts(unittest.TestCase):
    def test_both_languages_have_the_same_keys(self):
        self.assertEqual(set(i18n.STR["en"]), set(i18n.STR["ka"]))

    def test_the_removed_method_texts_are_gone_and_the_guide_describes_the_recipes(self):
        for lang in ("en", "ka"):
            self.assertNotIn("mD", i18n.STR[lang])
            self.assertIn("Distrobox", i18n.STR[lang]["guide"])
            self.assertNotIn("WHAT METHOD E", i18n.STR[lang]["guide"])
            self.assertTrue(i18n.t("k_container", lang, tool="distrobox", name="qgis-box"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
