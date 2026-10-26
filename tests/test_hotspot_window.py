#!/usr/bin/env python3
"""The Wi-Fi hotspot window for real (Tk under xvfb / your screen): adapter and network choice. nmcli, iw and pkexec are faked;
nothing on the system is touched. Skipped without tkinter / a display."""
import importlib.util
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "common"))
os.environ.update(XDG_CONFIG_HOME=tempfile.mkdtemp())
try:
    import tkinter as tk
    tk.Tk().destroy()
    SKIP = ""
except Exception as e:  # noqa: BLE001
    SKIP = f"no tkinter / display: {e}"

if not SKIP:
    spec = importlib.util.spec_from_file_location("hotspot_gui", os.path.join(ROOT, "wifi-hotspot", "hotspot-gui.py"))
    gui = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gui)

INTERNAL = {"dev": "wlp3s0", "phy": "phy0", "driver": "iwlwifi", "bus": "pci", "model": "Centrino Advanced-N 6205", "ap": True,
            "state": "connected", "connection": ""}
USB = {"dev": "wlx6070721c3312", "phy": "phy1", "driver": "mt7601u", "bus": "usb", "model": "MT7601U Wireless Adapter", "ap": False,
       "state": "connected", "connection": "Home"}
CABLE = {"dev": "eno1", "type": "ethernet", "connection": "Wired connection 1", "gateway": "192.168.0.1"}
WIFI2 = {"dev": "wlx6070721c3312", "type": "wifi", "connection": "Home", "gateway": "10.9.0.1"}


@unittest.skipIf(SKIP, SKIP)
class HotspotWindow(unittest.TestCase):
    def setUp(self):
        gui.LANG = "en"
        self.calls = []
        self.shown = []

        def fake_run(cmd, timeout=None):
            self.calls.append(cmd)
            return (0, "") if cmd[:3] != ["nmcli", "-t", "-f"] else (0, "")
        self.patches = [
            mock.patch.object(gui, "run", fake_run),
            mock.patch.object(gui, "warn_missing", lambda *a, **k: None),
            mock.patch.object(gui, "profile_exists", lambda: False),
            mock.patch.object(gui, "profile_iface", lambda: ""),
            mock.patch.object(gui, "is_active", lambda: False),
            mock.patch.object(gui.lsnet, "wifi_adapters", lambda *a, **k: [USB, INTERNAL]),        # USB plugged in first
            mock.patch.object(gui.lsnet, "uplink_choices", lambda ap, con="Hotspot", **k: [u for u in (CABLE, WIFI2) if u["dev"] != ap]),
            mock.patch.object(gui.lsnet, "current_uplink", lambda *a, **k: ""),
            mock.patch.object(gui.messagebox, "showerror", lambda *a, **k: self.shown.append(("error", a))),
            mock.patch.object(gui.messagebox, "showinfo", lambda *a, **k: self.shown.append(("info", a))),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def pump(self, app, secs=0.3):
        end = time.time() + secs
        while time.time() < end:
            app.update()
            time.sleep(0.02)

    def make(self):
        app = gui.App()
        app.after = lambda ms, fn=None, *a: None                       # no background polling in the test
        self.pump(app)
        return app

    def test_the_adapter_that_can_host_is_preselected_and_both_lists_are_filled(self):
        app = self.make()
        try:
            self.assertEqual(app.iface, "wlp3s0")                       # not the USB one that was listed first
            self.assertIn("wlp3s0", app.v_adapter.get())
            self.assertIn("can host a hotspot", app.v_adapter.get())
            self.assertEqual(len(app.cmb_adapter.cget("values")), 2)
            ups = list(app.cmb_uplink.cget("values"))
            self.assertEqual(len(ups), 3)                                # automatic + cable + the second Wi-Fi adapter
            self.assertTrue(ups[0].startswith("Automatic"))
            self.assertIn("eno1", ups[1])
            self.assertIn("Home", ups[2])
            self.assertEqual(app.uplink_dev(), "")
        finally:
            app.destroy()

    def test_choosing_the_usb_adapter_is_refused_with_a_reason(self):
        app = self.make()
        try:
            app.cmb_adapter.current(0)
            app.cmb_adapter.event_generate("<<ComboboxSelected>>")
            self.pump(app)
            self.assertEqual(app.iface, "wlx6070721c3312")
            self.assertNotIn("Home", " ".join(app.cmb_uplink.cget("values")))        # it cannot also be the network to share
            self.assertIn("cannot host a hotspot", app.v_adapter.get())
            app.ssid.set("Net")
            app.psk.set("password123")
            app.on_save()
            self.pump(app)
            self.assertEqual(self.shown[-1][0], "error")
            self.assertIn("no AP mode", self.shown[-1][1][1])
            self.assertFalse([c for c in self.calls if c[:3] == ["nmcli", "con", "add"]])        # nothing was created
        finally:
            app.destroy()

    def test_save_creates_the_profile_on_the_chosen_adapter_and_applies_the_network(self):
        app = self.make()
        try:
            app.ssid.set("Net")
            app.psk.set("password123")
            app.cmb_uplink.current(2)                                    # the second Wi-Fi adapter, connected to another network
            app.cmb_uplink.event_generate("<<ComboboxSelected>>")
            self.assertEqual(app.uplink_dev(), "wlx6070721c3312")
            with mock.patch.object(gui.lsnet, "helper_path", lambda here: "/x/hotspot-uplink.sh"):
                app.on_save()
                t0 = time.time()
                while app.busy and time.time() - t0 < 5:
                    self.pump(app, 0.1)
                self.pump(app, 0.2)
            add = next(c for c in self.calls if c[:3] == ["nmcli", "con", "add"])
            self.assertEqual(add[add.index("ifname") + 1], "wlp3s0")
            helper = next(c for c in self.calls if c[:1] == ["pkexec"])
            self.assertEqual(helper, ["pkexec", "sh", "/x/hotspot-uplink.sh", "install", "wlx6070721c3312", "Hotspot"])
        finally:
            app.destroy()

    def test_unchanged_network_choice_asks_for_no_password(self):
        app = self.make()
        try:
            app.ssid.set("Net")
            app.psk.set("password123")
            app.on_save()
            t0 = time.time()
            while app.busy and time.time() - t0 < 5:
                self.pump(app, 0.1)
            self.assertFalse([c for c in self.calls if c[:1] == ["pkexec"]])
        finally:
            app.destroy()

    def test_georgian_labels(self):
        gui.LANG = "ka"
        app = self.make()
        try:
            self.assertEqual(app.lbl_uplink.cget("text"), gui.t("uplink") + ":")
            self.assertIn("ვარგისია Hotspot-ისთვის", app.v_adapter.get())
        finally:
            gui.LANG = "en"
            app.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=1)
