#!/usr/bin/env python3
"""Fast offline unit tests (no root, no network, no display). Run: python3 tests/test_units.py"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "common"))

for n in ("tkinter", "tkinter.ttk", "tkinter.messagebox", "tkinter.scrolledtext", "tkinter.filedialog", "tkinter.simpledialog"):
    sys.modules[n] = types.ModuleType(n)
tk = sys.modules["tkinter"]
tk.ttk, tk.messagebox = sys.modules["tkinter.ttk"], sys.modules["tkinter.messagebox"]
tk.scrolledtext, tk.filedialog = sys.modules["tkinter.scrolledtext"], sys.modules["tkinter.filedialog"]
tk.simpledialog = sys.modules["tkinter.simpledialog"]
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


class MissingTools(unittest.TestCase):
    def test_hints_per_package_manager(self):
        import lscommon
        miss = [("nmcli", lscommon.PKG_FOR["nmcli"]["dnf"]), ("iw", "iw")]
        self.assertEqual(lscommon.install_command(miss, "dnf"), "sudo dnf install NetworkManager iw")
        self.assertEqual(lscommon.install_command([("nmcli", lscommon.PKG_FOR["nmcli"]["pacman"])], "pacman"),
                         "sudo pacman -S networkmanager")
        self.assertEqual(lscommon.install_command([("x", None)], "apt-get"), "")

    def test_missing_tools_uses_path(self):
        import lscommon
        self.assertEqual(lscommon.missing_tools(["sh"], "apt-get"), [])
        self.assertEqual(lscommon.missing_tools(["no-such-tool-xyz"], "apt-get"), [("no-such-tool-xyz", None)])
        from unittest import mock
        with mock.patch("shutil.which", return_value=None):          # pretend nothing is installed
            self.assertEqual(lscommon.missing_tools(["lsblk", "nmcli"], "apt-get"),
                             [("lsblk", "util-linux"), ("nmcli", "network-manager")])
            self.assertEqual(lscommon.missing_tools(["nmcli"], "dnf"), [("nmcli", "NetworkManager")])


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


class Bluetooth(unittest.TestCase):
    m = load("bluetooth-setup/bluetooth-setup-gui.py")
    fx = os.path.join(ROOT, "tests", "fixtures")

    def read(self, n):
        with open(os.path.join(self.fx, n)) as f:
            return f.read()

    def test_mgmt_info_two_dongles(self):
        c = {x["index"]: x for x in self.m.parse_mgmt_info(self.read("mgmt_info_dongles.txt"))}
        self.assertEqual(self.m.LMP[c["hci0"]["version"]], "2.0 + EDR")
        self.assertEqual(self.m.features_of(c["hci0"]), ["BR/EDR"])                 # classic only
        self.assertEqual(self.m.LMP[c["hci1"]["version"]], "4.0")
        self.assertEqual(self.m.features_of(c["hci1"]), ["BR/EDR", "LE", "SSP"])
        self.assertEqual(c["hci0"]["addr"], "00:15:83:0C:BF:EB")
        self.assertIn("powered", c["hci0"]["current"])

    def test_kernel_hints(self):
        h = self.m.kernel_hints(self.read("dmesg_bluetooth.txt"))
        self.assertIn("tx timeout", h["hci1"]["failed"])
        self.assertTrue(h["hci0"]["clone"])
        self.assertEqual(h["hci0"]["failed"], "")
        self.assertEqual(h["_usb_errors"], 3)

    def test_device_info_and_kind(self):
        info = self.m.parse_info(self.read("btctl_info_speaker.txt"))
        self.assertEqual((info["Paired"], info["Connected"]), ("yes", "yes"))
        self.assertEqual(self.m.device_kind(info), "audio")
        self.assertEqual(self.m.device_kind({"Icon": "input-keyboard", "uuids": []}), "keyboard")
        self.assertEqual(self.m.device_kind({"Icon": "input-mouse", "uuids": []}), "mouse")
        self.assertEqual(self.m.device_kind({"uuids": ["Human Interface Device (00001124-...)"]}), "keyboard")

    def test_parse_devices(self):
        d = self.m.parse_devices("Device 5C:FB:7C:12:34:56 JBL Flip 5\nDevice aa:bb:cc:00:11:22 K-Snake Keyboard\n")
        self.assertEqual(d, {"5C:FB:7C:12:34:56": "JBL Flip 5", "AA:BB:CC:00:11:22": "K-Snake Keyboard"})

    def test_event_parser_on_a_pairing_transcript(self):
        events = [e for e in map(self.m.parse_bt_line, self.read("btctl_pairing_session.txt").splitlines()) if e]
        self.assertEqual(events[0], ("new", "5C:FB:7C:12:34:56", "JBL Flip 5"))
        self.assertIn(("chg", "5C:FB:7C:12:34:56", "RSSI", "-60"), events)
        self.assertIn(("chg", "AA:BB:CC:00:11:22", "RSSI", "-71"), events)
        self.assertIn(("del", "11:22:33:44:55:66"), events)
        self.assertIn(("show_code", "482913"), events)
        self.assertIn(("show_code", "123456"), events)
        self.assertIn(("confirm", "654321"), events)
        self.assertIn(("enter_pin",), events)
        self.assertIn(("authorize",), events)
        self.assertIn(("chg", "AA:BB:CC:00:11:22", "Paired", "yes"), events)
        self.assertIn(("result", "pair", True, ""), events)
        self.assertIn(("result", "pair", False, "org.bluez.Error.AuthenticationFailed"), events)
        self.assertIn(("result", "connect", True, ""), events)
        self.assertEqual([e for e in events if e[0] == "result" and e[1] == "connect" and not e[2]][0][3].split()[0],
                         "org.bluez.Error.Failed")
        self.assertIsNone(self.m.parse_bt_line("\x1b[0;94m[bluetooth]\x1b[0m# \x01\x02"))   # prompt noise

    def test_ansi_and_prompt_are_stripped(self):
        self.assertEqual(self.m.parse_bt_line("\x1b[0;92m[NEW]\x1b[0m Device AA:BB:CC:00:11:22 Mouse"),
                         ("new", "AA:BB:CC:00:11:22", "Mouse"))

    def test_session_roundtrip_with_fake_bluetoothctl(self):
        import stat, subprocess, tempfile, time
        with tempfile.TemporaryDirectory() as d:
            fake = os.path.join(d, "bluetoothctl")
            with open(fake, "w") as f:
                f.write("#!/bin/sh\necho '[NEW] Device 5C:FB:7C:12:34:56 JBL Flip 5'\necho '[agent] Confirm passkey 111222 (yes/no): '\n"
                        "while read l; do echo \"GOT:$l\"; [ \"$l\" = quit ] && exit 0; done\n")
            os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
            seen, old = [], os.environ["PATH"]
            os.environ["PATH"] = d + os.pathsep + old
            try:
                s = self.m.BtSession(seen.append)
                time.sleep(0.5)
                s.send("yes")
                time.sleep(0.5)
                s.close()
            finally:
                os.environ["PATH"] = old
            txt = "".join(seen)
            self.assertIn("JBL Flip 5", txt)
            self.assertIn("GOT:yes", txt)
            self.assertIn(("confirm", "111222"), [self.m.parse_bt_line(x) for x in seen])


class Shortcuts(unittest.TestCase):
    m = load("shortcuts/shortcuts-gui.py")

    def tool(self, i):
        return next(x for x in self.m.TOOLS if x["id"] == i)

    def make_root(self, d):
        root = os.path.join(d, "checkout")
        for x in self.m.TOOLS:
            if not x["script"]:                                  # installed by a package, nothing in the checkout
                continue
            os.makedirs(os.path.dirname(os.path.join(root, x["script"])), exist_ok=True)
            open(os.path.join(root, x["script"]), "w").close()
        open(os.path.join(root, "install.sh"), "w").close()
        return root

    def test_every_tool_has_the_fields_a_launcher_needs(self):
        ids = [x["id"] for x in self.m.TOOLS]
        self.assertEqual(len(ids), len(set(ids)))
        for x in self.m.TOOLS:
            for k in ("cmd", "file", "icon", "cats"):
                self.assertTrue(x[k], (x["id"], k))
            self.assertIn("script", x)                                    # may be "" for programs installed by a package
            self.assertTrue(x["file"].endswith(".desktop"))
            self.assertEqual(set(x["name"]), {"en", "ka"})
            self.assertEqual(set(x["comment"]), {"en", "ka"})

    def test_resolve_prefers_the_installed_command_then_the_folder(self):
        with tempfile.TemporaryDirectory() as d:
            root, home = self.make_root(d), os.path.join(d, "home")
            tool = self.tool("usb-eject")
            nobin = {"bin_dirs": [os.path.join(d, "no-such-bin")]}          # independent of what the host has installed
            kind, ex = self.m.resolve_exec(tool, root, which=lambda c: "/usr/bin/" + c, home=home, **nobin)
            self.assertEqual((kind, ex), ("installed", "/usr/bin/usb-eject-gui"))
            os.makedirs(os.path.join(home, ".local", "bin"))
            exe = os.path.join(home, ".local", "bin", tool["cmd"])
            open(exe, "w").close()
            os.chmod(exe, 0o755)
            self.assertEqual(self.m.resolve_exec(tool, root, which=lambda c: "/usr/bin/" + c, home=home), ("installed", exe))
            os.remove(exe)
            kind, ex = self.m.resolve_exec(tool, root, which=lambda c: None, home=home, **nobin)
            self.assertEqual(kind, "folder")
            self.assertTrue(ex.startswith("python3 ") and ex.endswith("usb-eject/usb-eject-gui.py"))
            self.assertTrue(self.m.resolve_exec(self.tool("printhub"), root, which=lambda c: None, home=home, **nobin)[1].startswith("sh "))
            self.assertEqual(self.m.resolve_exec(tool, None, which=lambda c: None, home=home, **nobin), (None, None))

    def test_add_replace_foreign_and_remove(self):
        with tempfile.TemporaryDirectory() as d:
            root, desk = self.make_root(d), os.path.join(d, "Desktop")
            kw = {"which": lambda c: None, "home": os.path.join(d, "h"), "bin_dirs": [os.path.join(d, "nobin")]}
            tool = self.tool("wifi-hotspot")
            res, path = self.m.add_shortcut(tool, root, desk, **kw)
            self.assertEqual(res, "added")
            with open(path) as fh:
                text = fh.read()
            self.assertIn("Exec=python3 " + os.path.join(root, "wifi-hotspot/hotspot-gui.py"), text)
            self.assertIn("Name[ka]=Wi-Fi Hotspot", text)
            self.assertIn("X-Toolkit-Id=wifi-hotspot", text)
            self.assertIn("Path=" + os.path.join(root, "wifi-hotspot"), text)
            self.assertTrue(os.access(path, os.X_OK))
            self.assertEqual(self.m.add_shortcut(tool, root, desk, **kw)[0], "added")      # ours: replaced, no error
            self.assertEqual(self.m.remove_shortcut(tool, desk), "removed")
            self.assertEqual(self.m.remove_shortcut(tool, desk), "absent")
            # somebody else's file with the same name is never touched
            with open(os.path.join(desk, tool["file"]), "w") as f:
                f.write("[Desktop Entry]\nName=Mine\nExec=/opt/other/thing\n")
            self.assertEqual(self.m.add_shortcut(tool, root, desk, **kw)[0], "foreign")
            self.assertEqual(self.m.remove_shortcut(tool, desk), "foreign")
            with open(os.path.join(desk, tool["file"])) as fh:
                self.assertIn("Name=Mine", fh.read())
            # not available anywhere -> nothing is written
            self.assertEqual(self.m.add_shortcut(self.tool("printhub"), None, desk, **kw), ("missing", None))

    def test_launchers_made_by_install_sh_are_recognised(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "hotspot-gui.desktop")
            with open(p, "w") as f:
                f.write("[Desktop Entry]\nName=Wi-Fi Hotspot\nExec=/home/k/.local/bin/hotspot-gui\n")
            self.assertTrue(self.m.is_ours(p, self.tool("wifi-hotspot")))
            self.assertFalse(self.m.is_ours(p, self.tool("usb-eject")))
            self.assertFalse(self.m.is_ours(os.path.join(d, "nothing.desktop"), self.tool("usb-eject")))

    def test_find_root(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.make_root(d)
            self.assertEqual(self.m.find_root({"TOOLKIT_ROOT": root}, here="/nowhere/x", home=d), root)
            self.assertEqual(self.m.find_root({}, here=os.path.join(root, "shortcuts"), home=d), root)
            cfg = os.path.join(d, ".config", "linux-scripts")
            os.makedirs(cfg)
            with open(os.path.join(cfg, "root"), "w") as f:
                f.write(root + "\n")
            self.assertEqual(self.m.find_root({}, here="/nowhere/x", home=d), root)       # what install.sh remembered
            self.assertIsNone(self.m.find_root({}, here="/nowhere/x", home=os.path.join(d, "empty")))


class Installer(unittest.TestCase):
    m = load("installer/installer-gui.py")

    def test_every_tool_is_one_install_sh_knows(self):
        with open(os.path.join(ROOT, "install.sh")) as f:
            src = f.read()
        for x in self.m.TOOLS:
            self.assertIn(f"[{x['id']}]=", src, x["id"])           # present in install.sh's tables
            self.assertEqual(set(x["name"]), {"en", "ka"})
            self.assertEqual(set(x["info"]), {"en", "ka"})
        self.assertEqual(set(self.m.STR["en"]), set(self.m.STR["ka"]))

    def test_build_command_matches_install_sh_options(self):
        b = self.m.build_command
        self.assertEqual(b("/r", ["usb-eject"], "install", "user", home="/h"),
                         ["bash", "/r/install.sh", "--prefix", "/h/.local", "usb-eject"])
        self.assertEqual(b("/r", ["a", "b"], "uninstall", "user", desktop=True, folders=True, home="/h"),
                         ["bash", "/r/install.sh", "--prefix", "/h/.local", "--uninstall", "--desktop", "--folders", "a", "b"])
        sysc = b("/r", ["usb-eject"], "install", "system", desktop=True, folders=True, home="/h")
        self.assertEqual(sysc, ["bash", "/r/install.sh", "--prefix", "/usr/local", "usb-eject"])   # no launchers as root

    def test_elevation(self):
        self.assertEqual(self.m.elevate(["x"], which=lambda c: "/usr/bin/pkexec", euid=1000), ["pkexec", "x"])
        self.assertIsNone(self.m.elevate(["x"], which=lambda c: None, euid=1000))
        self.assertEqual(self.m.elevate(["x"], which=lambda c: None, euid=0), ["x"])

    def test_installed_state(self):
        tool = {"cmds": ["foo"]}
        ex = lambda p: p in ("/h/.local/bin/foo",)               # noqa: E731
        self.assertEqual(self.m.installed_where(tool, "/h", ex), {"user"})
        ex = lambda p: p in ("/h/.local/bin/foo", "/usr/local/bin/foo")   # noqa: E731
        self.assertEqual(self.m.installed_where(tool, "/h", ex), {"user", "system"})
        self.assertEqual(self.m.installed_where(tool, "/h", lambda p: False), set())

    def test_launcher_text(self):
        txt = self.m.launcher_text("/r")
        self.assertIn("Exec=python3 /r/installer/installer-gui.py", txt)
        self.assertIn("Path=/r", txt)
        self.assertIn("Name[ka]=", txt)

    def test_a_real_install_and_uninstall_through_the_same_code_path(self):
        with tempfile.TemporaryDirectory() as d:
            lines = []
            cmd = ["bash", os.path.join(ROOT, "install.sh"), "--prefix", d, "usb-eject"]
            self.assertEqual(self.m.run_command(cmd, lines.append), 0)
            self.assertTrue(os.path.exists(os.path.join(d, "bin", "usb-eject-gui")))
            self.assertIn("usb-eject", "".join(lines))
            self.assertEqual(self.m.run_command(cmd[:4] + ["--uninstall"] + cmd[4:], lines.append), 0)
            self.assertFalse(os.path.exists(os.path.join(d, "bin", "usb-eject-gui")))
            self.assertEqual(self.m.run_command(["definitely-not-a-command-xyz", "x"], lines.append), 127)

    def test_prerequisite_commands_per_package_manager(self):
        self.assertEqual(self.m.prereq_command("apt-get")[:2], ["sh", "-c"])
        self.assertIn("python3-venv", self.m.prereq_command("apt-get")[2])
        self.assertIn("python3-pip", self.m.prereq_command("dnf")[2])
        self.assertIn("python-pip", self.m.prereq_command("pacman")[2])
        self.assertIsNone(self.m.prereq_command("unknown-pm"))
        self.assertIsNone(self.m.prereq_command(""))

    def test_jobs_stop_at_the_first_failure(self):
        seen = []
        ok, bad, never = ["sh", "-c", "echo one"], ["sh", "-c", "echo two; exit 3"], ["sh", "-c", "echo three"]
        self.assertEqual(self.m.run_jobs([ok, bad, never], seen.append), 3)
        self.assertEqual("".join(seen).split(), ["one", "two"])          # the third never ran
        self.assertEqual(self.m.run_jobs([ok, ok], lambda l: None), 0)
        self.assertEqual(self.m.run_jobs([], lambda l: None), 0)

    def test_tool_path_follows_the_location(self):
        ex = lambda p: p in ("/h/.local/bin/printhub",)            # noqa: E731
        self.assertEqual(self.m.tool_path("printhub", "user", "/h", ex), "/h/.local/bin/printhub")
        self.assertIsNone(self.m.tool_path("printhub", "system", "/h", ex))
        self.assertIsNone(self.m.tool_path("printhub", "user", "/h", lambda p: False))

    def test_window_offers_prerequisite_then_installs_then_starts_printhub(self):
        m = self.m
        calls = {"jobs": None, "asked": [], "popen": []}
        patches = dict(venv_ready=lambda *a, **k: False, detect_pm=lambda: "apt-get",
                       elevate=lambda c, **k: ["pkexec"] + list(c),
                       run_jobs=lambda jobs, on_line: calls.__setitem__("jobs", jobs) or 0,
                       tool_path=lambda *a, **k: "/h/.local/bin/printhub")
        class FakeApp:                                     # only what go() touches, no display needed
            pass
        saved = {k: getattr(m, k) for k in patches}
        saved_mb, saved_popen = (m.messagebox, m.subprocess.Popen)
        try:
            for k, v in patches.items():
                setattr(m, k, v)
            m.messagebox = types.SimpleNamespace(
                askyesno=lambda title, msg: calls["asked"].append(msg) or True,
                showinfo=lambda *a: None, showwarning=lambda *a: None)
            m.subprocess.Popen = lambda cmd, **k: calls["popen"].append(cmd)
            app = FakeApp()
            app.busy, app.where = False, types.SimpleNamespace(get=lambda: "user")
            app.v_desk = app.v_fold = types.SimpleNamespace(get=lambda: False)
            app.selected_ids = lambda: ["printhub"]
            app.selected_extras = lambda: []
            app.b_inst = app.b_un = types.SimpleNamespace(state=lambda *a: None)
            app.lbl_status = types.SimpleNamespace(config=lambda **k: None)
            app.say = lambda *a: None
            app.render = lambda: None
            app.finish = lambda rc: m.App.finish(app, rc)
            app.after = lambda ms, fn, *a: fn(*a)           # run the "UI" hand-off inline
            m.threading = types.SimpleNamespace(Thread=lambda target, daemon: types.SimpleNamespace(start=target))
            m.App.go(app, "install")
            self.assertEqual(len(calls["asked"]), 1)
            self.assertIn("python3-venv", calls["asked"][0])
            jobs = calls["jobs"]
            self.assertEqual(jobs[0][:3], ["pkexec", "sh", "-c"])                 # 1. the prerequisite, as administrator
            self.assertIn("install.sh", jobs[1][1])                                # 2. the install itself, as the user
            self.assertIn("printhub", jobs[1])
            self.assertEqual(calls["popen"], [["/h/.local/bin/printhub"]])         # 3. and PrintHub starts
        finally:
            for k, v in saved.items():
                setattr(m, k, v)
            m.messagebox, m.subprocess.Popen = saved_mb, saved_popen
            import threading
            m.threading = threading

    def test_venv_check_is_false_when_nothing_works(self):
        class R:
            returncode = 1
        self.assertFalse(self.m.venv_ready(run=lambda *a, **k: R()))
        R.returncode = 0
        self.assertTrue(self.m.venv_ready(run=lambda *a, **k: R()))


class Extras(unittest.TestCase):
    ex = Installer.m.extras
    fx = os.path.join(ROOT, "tests", "fixtures", "etcher_release.json")

    def release(self):
        with open(self.fx) as f:
            data = json.load(f)
        return self.ex.etcher_release(fetch=lambda url: data)

    def test_release_parsing_uses_githubs_per_asset_digest(self):
        r = self.release()
        self.assertEqual((r["tag"], r["version"]), ("v2.1.7", "2.1.7"))
        deb = r["assets"]["balena-etcher_2.1.7_amd64.deb"]
        self.assertEqual(deb["sha256"], "9dbea6165ddee1ec1f1b7a38fe92f0d2c54c6217710438a7af6752c267d19395")
        self.assertEqual(r["assets"]["npm-sbom.json"]["sha256"], "")          # no digest -> never offered as a package

    def test_package_choice_per_system(self):
        r = self.release()
        pick = lambda pm, arch="amd64": (self.ex.etcher_asset(r, pm, arch) or {}).get("name")   # noqa: E731
        self.assertEqual(pick("apt-get"), "balena-etcher_2.1.7_amd64.deb")
        self.assertEqual(pick("dnf", "x86_64"), "balena-etcher-2.1.7-1.x86_64.rpm")
        self.assertEqual(pick("zypper", "x86_64"), "balena-etcher-2.1.7-1.x86_64.rpm")
        self.assertIsNone(pick("pacman"))                      # no official package: the page is offered, not a guess
        self.assertIsNone(pick("apt-get", "arm64"))            # the publisher ships x86-64 Linux packages only
        self.assertIsNone(pick(""))

    def test_steps_apt_and_rpm_parse_and_install_what_was_verified(self):
        r = self.release()
        for pm, arch, installer in (("apt-get", "amd64", "apt-get install -y"), ("dnf", "x86_64", "dnf install -y"),
                                    ("zypper", "x86_64", "--allow-unsigned-rpm")):
            steps, info = self.ex.etcher_steps(r, pm, arch, cache_dir="/tmp/cache with space")
            self.assertEqual([x["root"] for x in steps], [False, True, False])
            self.assertIn(installer, steps[1]["sh"])
            self.assertIn(info["sha256"], steps[0]["sh"])
            self.assertIn("--proto '=https'", steps[0]["sh"])
            self.assertIn("'/tmp/cache with space/", steps[1]["sh"])               # quoted: spaces survive
            self.assertEqual(info["source"], "github.com/balena-io/etcher")
            for st in steps:
                self.assertEqual(subprocess.run(["sh", "-n", "-c", st["sh"]], capture_output=True).returncode, 0)
        steps, info = self.ex.etcher_steps(r, "pacman", "x86_64")
        self.assertEqual(steps, [])
        self.assertEqual(info["manual"], self.ex.ETCHER_PAGE)

    def test_download_step_verifies_the_checksum_for_real(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "pkg.deb")
            with open(src, "wb") as f:
                f.write(b"the package bytes")
            good = hashlib.sha256(b"the package bytes").hexdigest()
            cache = os.path.join(d, "cache")
            run = lambda sha: subprocess.run(["sh", "-c", self.ex.download_script(       # noqa: E731
                {"name": "pkg.deb", "url": "file://" + src, "sha256": sha}, cache, proto="=file")], capture_output=True, text=True)
            ok = run(good)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertTrue(os.path.exists(os.path.join(cache, "pkg.deb")))
            os.remove(os.path.join(cache, "pkg.deb"))
            bad = run("0" * 64)                                                           # tampered / wrong -> refuse
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("CHECKSUM MISMATCH", bad.stderr)
            self.assertEqual(os.listdir(cache), [])                                        # nothing left behind, not even .part

    def test_installed_and_remove(self):
        R = lambda out, rc=0: types.SimpleNamespace(returncode=rc, stdout=out)             # noqa: E731
        self.assertEqual(self.ex.etcher_installed(run=lambda *a, **k: R("install ok installed 2.1.7"), which=lambda c: "/x"), "2.1.7")
        self.assertIsNone(self.ex.etcher_installed(run=lambda *a, **k: R("", 1), which=lambda c: "/x"))
        self.assertIsNone(self.ex.etcher_installed(run=lambda *a, **k: R("install ok installed 1"), which=lambda c: None))
        self.assertIn("apt-get remove -y balena-etcher", self.ex.etcher_remove_steps("apt-get")[0]["sh"])
        self.assertEqual(self.ex.etcher_remove_steps("pacman"), [])

    def test_window_asks_before_downloading_then_runs_download_install_cleanup(self):
        m = Installer.m
        calls = {"asked": []}
        saved = {k: getattr(m, k) for k in ("detect_pm", "elevate")}
        saved_rel, saved_mb = m.extras.etcher_release, m.messagebox
        release = self.release()                       # built before the lookup is replaced below
        try:
            m.detect_pm = lambda: "apt-get"
            m.elevate = lambda c, **k: ["pkexec"] + list(c)
            m.extras.etcher_release = lambda *a, **k: release
            answers = [True]
            m.messagebox = types.SimpleNamespace(askyesno=lambda t_, msg: calls["asked"].append(msg) or answers.pop(0),
                                                 showinfo=lambda *a: None, showwarning=lambda *a: None)
            app = types.SimpleNamespace(lbl_status=types.SimpleNamespace(config=lambda **k: None), update_idletasks=lambda: None)
            with mock.patch("platform.machine", return_value="x86_64"):
                jobs = m.App.etcher_jobs(app, "install")
            self.assertEqual(len(calls["asked"]), 1)
            self.assertIn("9dbea6165ddee1ec1f1b7a38fe92f0d2c54c6217710438a7af6752c267d19395", calls["asked"][0])
            self.assertIn("balena-etcher_2.1.7_amd64.deb (118 MB)", calls["asked"][0])
            self.assertEqual([j[0] for j in jobs], ["sh", "pkexec", "sh"])             # user, administrator, user
            answers.append(False)                                                      # the user says no -> nothing runs
            with mock.patch("platform.machine", return_value="x86_64"):
                self.assertIsNone(m.App.etcher_jobs(app, "install"))
            m.extras.etcher_release = lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))
            answers.append(True)                                                       # offline -> a message, no crash
            self.assertIsNone(m.App.etcher_jobs(app, "install"))
        finally:
            for k, v in saved.items():
                setattr(m, k, v)
            m.extras.etcher_release, m.messagebox = saved_rel, saved_mb


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
