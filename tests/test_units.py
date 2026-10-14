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


class HotspotClients(unittest.TestCase):
    m = Hotspot.m
    fx = os.path.join(ROOT, "tests", "fixtures")

    def read(self, name):
        with open(os.path.join(self.fx, name)) as f:
            return f.read()

    def test_parse_station_dump(self):
        st = self.m.parse_station_dump(self.read("iw_station_dump.txt"))
        self.assertEqual([x["mac"] for x in st], ["aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02"])   # MAC lower-cased
        self.assertEqual((st[0]["signal"], st[0]["connected"], st[0]["rx"], st[0]["tx"]), (-45, 3725, 5242880, 1048576))
        self.assertEqual(st[1]["signal"], -71)       # "signal avg" must not override "signal"

    def test_neigh_prefers_ipv4_and_leases_give_names(self):
        self.assertEqual(self.m.parse_neigh(self.read("ip_neigh.txt"))["aa:bb:cc:dd:ee:01"], "10.42.0.35")
        lease = self.m.parse_leases(self.read("dnsmasq.leases"))
        self.assertEqual(lease["aa:bb:cc:dd:ee:01"], ("10.42.0.35", "Giorgis-iPhone"))
        self.assertEqual(lease["aa:bb:cc:dd:ee:02"][1], "")          # "*" = no hostname

    def test_list_clients_merges_sources(self):
        outputs = {"iw": self.read("iw_station_dump.txt"), "ip": self.read("ip_neigh.txt")}
        orig, env = self.m.run, os.environ.get("HOTSPOT_LEASES")
        self.m.run = lambda cmd, timeout=None: (0, outputs[cmd[0]])
        os.environ["HOTSPOT_LEASES"] = os.path.join(self.fx, "dnsmasq.leases")
        try:
            rows = self.m.list_clients("wlp3s0")
        finally:
            self.m.run = orig
            os.environ.pop("HOTSPOT_LEASES", None) if env is None else os.environ.update(HOTSPOT_LEASES=env)
        self.assertEqual([(r["ip"], r["name"]) for r in rows], [("10.42.0.35", "Giorgis-iPhone"), ("10.42.0.77", "")])

    def test_humanizers(self):
        self.assertEqual(self.m.human_secs(42), "42s")
        self.assertEqual(self.m.human_secs(320), "5m 20s")
        self.assertEqual(self.m.human_secs(3725), "1h 2m")
        self.assertEqual(self.m.human_bytes(2048), "2.0 KB")
        self.assertEqual(self.m.human_bytes(512), "512 B")


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


class Qr(unittest.TestCase):
    import lsqr

    def test_payload_escaping(self):
        self.assertEqual(self.lsqr.wifi_payload("My;Net", 'pa:ss"w,\\d'), 'WIFI:T:WPA;S:My\\;Net;P:pa\\:ss\\"w\\,\\\\d;;')
        self.assertEqual(self.lsqr.wifi_payload("Open", ""), "WIFI:T:nopass;S:Open;;")

    def test_structure(self):
        m = self.lsqr.make_qr("WIFI:T:WPA;S:MyHotspot;P:secret123;;")
        n = len(m)
        self.assertEqual(n, 29)                                   # version 3
        for cx, cy in ((0, 0), (n - 7, 0), (0, n - 7)):           # three finder patterns
            self.assertTrue(all(m[cy][cx + i] and m[cy + 6][cx + i] for i in range(7)))
            self.assertFalse(m[cy + 1][cx + 1] or m[cy + 5][cx + 5])
            self.assertTrue(m[cy + 3][cx + 3])
        self.assertTrue(m[n - 8][8])                              # the fixed dark module

    def test_versions_and_limit(self):
        sizes = [len(self.lsqr.make_qr("x" * k)) for k in (1, 14, 15, 213)]
        self.assertEqual(sizes, [21, 21, 25, 57])
        with self.assertRaises(ValueError):
            self.lsqr.make_qr("x" * 214)


class Usb(unittest.TestCase):
    m = load("usb-eject/usb-eject-gui.py")

    def test_mountpoints(self):
        self.assertEqual(self.m.mountpoints({"mountpoints": [None, "/mnt/a"]}), ["/mnt/a"])
        self.assertEqual(self.m.mountpoints({"mountpoint": "/x"}), ["/x"])
        self.assertEqual(self.m.mountpoints({}), [])

    def test_find_blockers_sees_cwd_and_open_file(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "data.txt")
            open(f, "w").close()
            a = subprocess.Popen(["sleep", "30"], cwd=d)                       # holds the folder as cwd
            b = subprocess.Popen(["sh", "-c", f"exec 3<{f}; exec sleep 30"])       # holds a file open
            try:
                import time
                time.sleep(0.5)
                rows = {r[0]: r for r in self.m.find_blockers([d])}
                self.assertEqual(rows[a.pid][3], "cwd")
                self.assertEqual(rows[b.pid][3], "open")
                self.assertTrue(rows[b.pid][4].endswith("data.txt"))
                self.assertIn("PID", self.m.describe_blockers([d]))
            finally:
                a.kill(); b.kill(); a.wait(); b.wait()
            self.assertEqual(self.m.find_blockers([d]), [])                    # nobody left


if __name__ == "__main__":
    unittest.main(verbosity=1)
