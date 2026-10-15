#!/usr/bin/env python3
"""The Tk window of the QGIS installer, driven without a human: goal -> recommendation -> options -> plan.

Needs tkinter and a display (Windows, macOS, or Linux under xvfb); skipped otherwise. The system is a fixture,
nothing is detected or installed, and no dialog is shown.
"""
import importlib.util
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "qgis-installer"))
sys.path.insert(0, os.path.join(ROOT, "common"))
from qgis_installer import system  # noqa: E402

try:
    import tkinter
    tkinter.Tk().destroy()
    HAVE_TK = True
except Exception:  # no tkinter or no display
    HAVE_TK = False


def load_gui():
    spec = importlib.util.spec_from_file_location("qgis_installer_gui", os.path.join(ROOT, "qgis-installer", "qgis-installer-gui.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fixture(name, pm, tools=(), immutable=None, arch="amd64"):
    return system.detect(os.path.join(HERE, "fixtures", "os-release", name), pm, arch,
                         tools={t: True for t in tools}, immutable=immutable or "none")


@unittest.skipUnless(HAVE_TK, "needs tkinter and a display")
class Window(unittest.TestCase):
    def open(self, sysinfo, lang="en"):
        gui = load_gui()
        gui.LANG = lang
        patches = [mock.patch.object(gui, "detect", lambda: sysinfo), mock.patch.object(gui, "installed_qgis", lambda: None),
                   mock.patch.object(gui, "find_installs", lambda s: [])]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        app = gui.App()
        self.addCleanup(app.destroy)
        app.update()
        return gui, app

    def test_ubuntu_recommends_the_official_repository_and_names_the_ltr(self):
        gui, app = self.open(fixture("ubuntu-noble", "apt-get"))
        self.assertEqual(app.recipe_id, "apt-official")
        self.assertIn("official repository", app.lbl_rec.cget("text"))
        self.assertEqual(app.options()["channel"], "ltr")
        self.assertIn("qgis.org", app.plan_text(app.plan()))

    def test_fedora_stable_is_the_distribution_package_without_options_of_other_recipes(self):
        gui, app = self.open(fixture("fedora-43", "dnf"))
        self.assertEqual(app.recipe_id, "dnf-fedora")
        self.assertIn("dnf install -y qgis python3-qgis qgis-grass", app.plan_text(app.plan()))
        self.assertFalse(app.cmb["branch"].winfo_ismapped())

    def test_alongside_picks_flatpak_stable_and_a_manual_branch_change_is_used(self):
        gui, app = self.open(fixture("fedora-43", "dnf"))
        app.goal.set("alongside")
        app.on_goal()
        app.update()
        self.assertEqual(app.recipe_id, "flatpak")
        self.assertIn("org.qgis.qgis//stable", app.plan_text(app.plan()))
        app.cmb["branch"].current(1)                         # lts
        text = app.plan_text(app.plan())
        self.assertIn("org.qgis.qgis//lts", text)
        self.assertIn("runtime", text.lower())               # the end-of-life warning is part of what the user reads
        app.cmb["scope"].current(1)                          # system
        self.assertIn("--system", app.plan_text(app.plan()))

    def test_picking_another_recipe_by_hand_shows_its_own_options(self):
        gui, app = self.open(fixture("opensuse-tumbleweed", "zypper"))
        i = app.recipe_ids.index("zypper-opensuse")
        app.cmb_recipe.current(i)
        app.on_recipe()
        app.update()
        app.v_geo.set(True)
        self.assertIn("addrepo", app.plan_text(app.plan()))
        self.assertTrue(app.cb_geo.winfo_ismapped())

    def test_manual_recipes_have_nothing_to_run(self):
        gui, app = self.open(fixture("nixos", "nix"))
        self.assertEqual(app.recipe_id, "nix-manual")
        result = app.plan()
        self.assertEqual(result["steps"], [])
        self.assertIn("nix-shell", app.plan_text(result))

    def test_georgian_labels(self):
        gui, app = self.open(fixture("fedora-43", "dnf"), "ka")
        self.assertIn("რეკომენდებულია", app.lbl_rec.cget("text"))
        self.assertEqual(app.f_goal.cget("text"), "რა გსურთ?")


if __name__ == "__main__":
    unittest.main()
