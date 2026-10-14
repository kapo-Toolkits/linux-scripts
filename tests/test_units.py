#!/usr/bin/env python3
"""Fast offline unit tests (no root, no network, no display). Run: python3 tests/test_units.py"""
import importlib.util
import os
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "common"))

for n in ("tkinter", "tkinter.ttk", "tkinter.messagebox", "tkinter.scrolledtext", "tkinter.filedialog"):
    sys.modules[n] = types.ModuleType(n)
tk = sys.modules["tkinter"]
tk.ttk, tk.messagebox = sys.modules["tkinter.ttk"], sys.modules["tkinter.messagebox"]
tk.scrolledtext, tk.filedialog = sys.modules["tkinter.scrolledtext"], sys.modules["tkinter.filedialog"]
tk.Tk = object


def load(rel):
    spec = importlib.util.spec_from_file_location(os.path.basename(rel).replace("-", "_"), os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Common(unittest.TestCase):
    def test_lang_roundtrip(self):
        import lscommon
        with tempfile.TemporaryDirectory() as d:
            lscommon.LANG_FILE = os.path.join(d, "x", "lang")
            self.assertEqual(lscommon.load_lang(), "en")          # default English
            lscommon.save_lang("ka")
            self.assertEqual(lscommon.load_lang(), "ka")
            with open(lscommon.LANG_FILE, "w") as f:
                f.write("garbage")
            self.assertEqual(lscommon.load_lang(), "en")

    def test_run_never_raises(self):
        import lscommon
        rc, out = lscommon.run(["definitely-not-a-command-xyz"])
        self.assertEqual(rc, 1)
        self.assertEqual(lscommon.run(["echo", "hi"]), (0, "hi"))


class Printer(unittest.TestCase):
    m = load("printer-setup/printer-setup-gui.py")

    def test_model_matching_is_word_bounded(self):
        rx = self.m.token_regex(self.m.model_token("L1250 Series"))
        self.assertTrue(rx.search("epson-l1250_series-epson-driver.ppd"))
        self.assertTrue(rx.search("epson l1250 series"))
        self.assertFalse(rx.search("brother hl-1250 foomatic/hl1250"))
        self.assertFalse(rx.search("epson l12500"))

    def test_queue_name(self):
        self.assertEqual(self.m.queue_name("L1250 Series"), "L1250_Series")
        self.assertEqual(self.m.queue_name("///"), "Printer")


class Hotspot(unittest.TestCase):
    m = load("wifi-hotspot/hotspot-gui.py")

    def test_psk_rules(self):
        self.assertTrue(self.m.valid_psk("abcdefgh"))
        self.assertFalse(self.m.valid_psk("short"))
        self.assertFalse(self.m.valid_psk("a" * 64))
        self.assertFalse(self.m.valid_psk("პაროლი12345"))          # Latin only


class Qgis(unittest.TestCase):
    m = load("qgis-installer/qgis-installer-gui.py")
    mint = {"name": "x", "family": "ubuntu", "code": "noble", "pm": "apt-get", "arch": "amd64",
            "supported": True, "ltr_only": True, "apt": True}

    def test_support_table(self):
        s = self.m.SUPPORT
        self.assertTrue(s["ubuntu"]["noble"] and s["ubuntu"]["jammy"] and s["debian"]["bookworm"])   # LTR only
        self.assertFalse(s["debian"]["trixie"] or s["ubuntu"]["resolute"])

    def test_sources_file(self):
        txt = self.m.sources_text(self.mint, "ltr")
        self.assertIn("URIs: https://qgis.org/ubuntu-ltr", txt)
        self.assertIn("Suites: noble", txt)
        d = dict(self.mint, family="debian", code="trixie")
        self.assertIn("URIs: https://qgis.org/debian\n", self.m.sources_text(d, "latest"))

    def test_install_script_has_fingerprint_gate(self):
        sh = self.m.build_install("A", self.mint, "ltr", {"grass": True, "python": True, "server": True})[0]["sh"]
        self.assertIn(self.m.KEY_FPR, sh)
        self.assertIn("exit 1", sh)
        self.assertLess(sh.index("exit 1"), sh.index(self.m.SOURCES + " <<"))   # gate comes before sources are written
        self.assertIn("--no-install-recommends --no-install-suggests qgis-server", sh)

    def test_remove_only_touches_known_user_dirs(self):
        home = os.path.expanduser("~")
        items = [{"kind": "data", "path": home + "/.local/share/QGIS", "sz": "1"},
                 {"kind": "data", "path": home + "/Documents", "sz": "1"},
                 {"kind": "data", "path": "/etc", "sz": "1"}]
        txt = " ".join(s["sh"] for s in self.m.build_remove_steps(items, False, False, self.mint))
        self.assertIn(".local/share/QGIS", txt)
        self.assertNotIn("Documents", txt)
        self.assertNotIn("rm -rf -- /etc", txt)


class Usb(unittest.TestCase):
    m = load("usb-eject/usb-eject-gui.py")

    def test_mountpoints(self):
        self.assertEqual(self.m.mountpoints({"mountpoints": [None, "/mnt/a"]}), ["/mnt/a"])
        self.assertEqual(self.m.mountpoints({"mountpoint": "/x"}), ["/x"])
        self.assertEqual(self.m.mountpoints({}), [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
