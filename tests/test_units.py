#!/usr/bin/env python3
"""Fast offline unit tests (no root, no network, no display). Run: python3 tests/test_units.py"""
import importlib.util
import json
import os
import shutil
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


class TkinterPrompt(unittest.TestCase):
    def test_prompt_is_bilingual_only_where_it_can_be_shown(self):
        import lscommon
        both = lscommon.tk_prompt("python3-tk", True)
        self.assertIn("Install python3-tk now?", both)
        self.assertIn("ვერ მოიძებნა", both)
        plain = lscommon.tk_prompt("python3-tk", False)                  # a terminal without UTF-8 would print ?????
        self.assertIn("Install python3-tk now?", plain)
        self.assertTrue(plain.isascii())

    def test_terminal_fallback_picks_an_installed_terminal_with_its_own_flag(self):
        import lscommon
        have = lambda *names: (lambda c: "/usr/bin/" + c if c in names else None)      # noqa: E731
        cmd = lscommon.terminal_command(["/p/app.py", "--x"], which=have("xfce4-terminal", "xterm"))
        self.assertEqual(cmd[:2], ["xfce4-terminal", "-x"])                            # XFCE first: its flag is -x, not -e
        self.assertEqual(cmd[-2:], ["/p/app.py", "--x"])
        self.assertIn("Press Enter", cmd[4])                                           # the window stays open on failure
        self.assertEqual(lscommon.terminal_command(["a"], which=have("gnome-terminal"))[:2], ["gnome-terminal", "--"])
        self.assertEqual(lscommon.terminal_command(["a"], which=have("konsole"))[:2], ["konsole", "-e"])
        self.assertIsNone(lscommon.terminal_command(["a"], which=have()))

    def test_a_locked_package_manager_is_explained(self):
        import lscommon
        for out in ("E: Could not get lock /var/lib/dpkg/lock-frontend. It is held by process 123 (ubiquity)",
                    "E: Unable to acquire the dpkg frontend lock (/var/lib/dpkg/lock-frontend), is another process using it?"):
            self.assertIn("Wait until it finishes", lscommon.lock_hint(out))
        self.assertEqual(lscommon.lock_hint("E: Unable to locate package nope"), "")
        self.assertEqual(lscommon.lock_hint(None), "")

    def test_zenity_wrapper_reports_no_window_when_it_cannot_run(self):
        import lscommon
        boom = lambda *a, **k: (_ for _ in ()).throw(OSError("no zenity"))   # noqa: E731
        self.assertIsNone(lscommon._zenity("question", "x", run=boom))
        R = lambda rc: types.SimpleNamespace(returncode=rc)                  # noqa: E731
        self.assertTrue(lscommon._zenity("question", "x", run=lambda *a, **k: R(0)))
        self.assertFalse(lscommon._zenity("question", "x", run=lambda *a, **k: R(1)))
        self.assertFalse(lscommon._gui_available(which=lambda c: None, env={"DISPLAY": ":0"}))
        self.assertFalse(lscommon._gui_available(which=lambda c: "/usr/bin/zenity", env={}))
        self.assertTrue(lscommon._gui_available(which=lambda c: "/usr/bin/zenity", env={"WAYLAND_DISPLAY": "w"}))


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

    def test_other_programs_are_grouped_contiguously(self):
        m = Installer.m
        seen = []
        for x in m.EXTRAS:
            self.assertIn(x["group"], m.GROUP_TEXT)
            if not seen or seen[-1] != x["group"]:
                seen.append(x["group"])
        self.assertEqual(len(seen), len(set(seen)), "a group must not be split in two headings")
        for lang in ("en", "ka"):
            for key in m.GROUP_TEXT.values():
                self.assertIn(key, m.STR[lang])

    def test_every_text_key_used_by_the_window_exists_in_both_languages(self):
        import re
        with open(os.path.join(ROOT, "installer", "installer-gui.py")) as f:
            src = f.read()
        used = set(re.findall(r'\bt\("([a-z_0-9]+)"', src))
        self.assertTrue(used)
        for lang in ("en", "ka"):
            self.assertEqual(sorted(used - set(self.m.STR[lang])), [], lang)

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
        self.assertIn('Exec=sh "/r/installer/start.sh"', txt)
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

    def test_start_sh_installs_exactly_the_bootstrap_packages(self):
        import lscommon
        with open(os.path.join(ROOT, "installer", "start.sh")) as f:
            src = f.read()
        for pm, pkgs in lscommon.PYTHON_BOOTSTRAP.items():
            line = next(ln for ln in src.splitlines() if ln.strip().startswith(pm.replace("apt-get", "apt-get") + ")"))
            for pkg in pkgs:
                words = [w.strip('";') for w in line.split("||")[0].split()]
                self.assertIn(pkg, words, (pm, pkg))                              # the table and the shell script agree
        self.assertIn(["apk", "add"], [c for m, c, _ in lscommon.TK_PACKAGES if m == "apk"])
        self.assertEqual([p for m, _, p in lscommon.TK_PACKAGES if m == "apk"], ["python3-tkinter"])   # not the old wrong name

    def test_window_size_fits_small_screens(self):
        f = self.m.fit_geometry
        self.assertEqual(f(1920, 1080), (1040, 600, 760, 470))                   # a big screen gets the wanted size
        self.assertEqual(f(1366, 768), (1040, 600, 760, 470))
        w, h, mw, mh = f(1024, 600)
        self.assertLessEqual(w, 1024 - 30)
        self.assertLessEqual(h, 600 - 80)                                       # room for the panel and the title bar
        self.assertLessEqual(mw, w)
        self.assertLessEqual(mh, h)
        w, h, mw, mh = f(800, 480)                                              # tiny: it still fits, minimums follow
        self.assertTrue(w <= 770 and h <= 400 and mw <= w and mh <= h)

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
                       run_jobs=lambda jobs, on_line, ctl=None: calls.__setitem__("jobs", jobs) or 0,
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
            quiet = types.SimpleNamespace(pack=lambda **k: None, pack_forget=lambda: None, config=lambda **k: None,
                                          start=lambda *a: None, stop=lambda: None, state=lambda *a: None)
            app.runbar, app.prog, app.b_cancel = quiet, quiet, quiet
            app.finish = lambda rc: m.App.finish(app, rc)
            app.start_jobs = lambda *a, **k: m.App.start_jobs(app, *a, **k)
            app.show_progress = lambda pct: None
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

    def test_download_step_says_so_when_curl_is_missing(self):
        asset = {"name": "x.deb", "url": "https://example.invalid/x.deb", "sha256": "0" * 64}
        r = subprocess.run(["/bin/sh", "-c", self.ex.download_script(asset, "/tmp/never-created")], capture_output=True,
                           text=True, env={"PATH": "/nonexistent"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("curl is not installed", r.stderr)

    @unittest.skipUnless(shutil.which("curl") and shutil.which("sha256sum"), "needs curl and sha256sum")
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
        self.assertIn("apt-get purge -y balena-etcher", self.ex.etcher_remove_steps("apt-get")[0]["sh"])
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


@unittest.skipUnless(shutil.which("git"), "needs git")
class Updater(unittest.TestCase):
    up = load("installer/updater.py")

    def git(self, cwd, *a):
        r = subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main"] + list(a),
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def world(self, d):
        """A bare 'GitHub', a clone that is the user's checkout, and a second clone that publishes new work."""
        origin = os.path.join(d, "origin.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], check=True)
        mine, other = os.path.join(d, "mine"), os.path.join(d, "other")
        for path in (mine, other):
            subprocess.run(["git", "clone", "-q", origin, path], check=True, capture_output=True)
        with open(os.path.join(other, "install.sh"), "w") as f:
            f.write("#!/bin/sh\necho v1\n")
        self.git(other, "add", "-A")
        self.git(other, "commit", "-q", "-m", "first")
        self.git(other, "push", "-q", "origin", "main")
        self.git(mine, "pull", "-q", "origin", "main")
        return origin, mine, other

    def publish(self, other, text, title):
        with open(os.path.join(other, "install.sh"), "w") as f:
            f.write(text)
        self.git(other, "commit", "-q", "-am", title)
        self.git(other, "push", "-q", "origin", "main")

    def test_check_sees_new_work_and_update_pulls_it(self):
        with tempfile.TemporaryDirectory() as d:
            origin, mine, other = self.world(d)
            res = self.up.check(mine)
            self.assertEqual((res["mode"], res["behind"]), ("git", 0))
            self.publish(other, "#!/bin/sh\necho v2\n", "Add the new thing")
            self.publish(other, "#!/bin/sh\necho v3\n", "Fix the other thing")
            res = self.up.check(mine)
            self.assertEqual(res["behind"], 2)
            self.assertEqual([t for _, t in res["commits"]], ["Fix the other thing", "Add the new thing"])
            ok, msg = self.up.update(mine)
            self.assertTrue(ok, msg)
            with open(os.path.join(mine, "install.sh")) as f:
                self.assertIn("v3", f.read())
            self.assertEqual(self.up.check(mine)["behind"], 0)

    def test_update_refuses_when_you_changed_a_tracked_file(self):
        with tempfile.TemporaryDirectory() as d:
            origin, mine, other = self.world(d)
            self.publish(other, "#!/bin/sh\necho v2\n", "new")
            with open(os.path.join(mine, "install.sh"), "a") as f:
                f.write("# my own edit\n")
            ok, msg = self.up.update(mine)
            self.assertFalse(ok)
            self.assertIn("install.sh", msg)
            with open(os.path.join(mine, "install.sh")) as f:
                self.assertIn("my own edit", f.read())                              # nothing was overwritten

    def test_update_from_another_branch_switches_to_main_when_clean(self):
        with tempfile.TemporaryDirectory() as d:
            origin, mine, other = self.world(d)
            self.git(mine, "checkout", "-q", "-b", "feature")
            self.publish(other, "#!/bin/sh\necho v2\n", "new on main")
            ok, msg = self.up.update(mine)
            self.assertTrue(ok, msg)
            self.assertEqual(self.up.local_info(mine)["branch"], "main")

    def test_a_plain_copy_is_adopted_and_keeps_untracked_files(self):
        with tempfile.TemporaryDirectory() as d:
            origin, mine, other = self.world(d)
            self.publish(other, "#!/bin/sh\necho v2\n", "new")
            copy = os.path.join(d, "usb copy")                                       # a folder copied without .git, a space in the path
            os.makedirs(copy)
            with open(os.path.join(copy, "install.sh"), "w") as f:
                f.write("#!/bin/sh\necho v1\n")
            with open(os.path.join(copy, "start-installer.desktop"), "w") as f:
                f.write("per machine launcher\n")
            self.assertEqual(self.up.check(copy)["mode"], "adopt")
            ok, msg = self.up.adopt(copy, url=origin)
            self.assertTrue(ok, msg)
            with open(os.path.join(copy, "install.sh")) as f:
                self.assertIn("v2", f.read())                                        # brought to the latest
            self.assertTrue(os.path.exists(os.path.join(copy, "start-installer.desktop")))   # untracked file untouched
            self.assertTrue(self.up.local_info(copy)["git"])                          # from now on a normal checkout
            self.assertEqual(self.up.check(copy)["mode"], "git")
            self.assertFalse(self.up.adopt(copy, url=origin)[0])                      # not twice

    def test_adopt_refuses_the_wrong_folder_and_nested_repositories(self):
        with tempfile.TemporaryDirectory() as d:
            empty = os.path.join(d, "empty")
            os.makedirs(empty)
            ok, msg = self.up.adopt(empty, url="file:///nowhere")
            self.assertFalse(ok)
            self.assertIn("install.sh", msg)
            origin, mine, other = self.world(d)
            inner = os.path.join(mine, "sub")
            os.makedirs(inner)
            open(os.path.join(inner, "install.sh"), "w").close()
            res = self.up.check(inner)
            self.assertEqual(res["mode"], "error")                                   # inside somebody else's repository
            self.assertFalse(self.up.adopt(inner, url=origin)[0])

    def test_offline_is_an_error_not_a_crash(self):
        with tempfile.TemporaryDirectory() as d:
            origin, mine, other = self.world(d)
            self.git(mine, "remote", "set-url", "origin", os.path.join(d, "gone.git"))
            res = self.up.check(mine)
            self.assertEqual(res["mode"], "error")
            self.assertTrue(res["error"])

    def test_settings_roundtrip_and_the_quiet_check_schedule(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x", "settings.json")
            self.assertEqual(self.up.load_settings(path), {})
            self.assertTrue(self.up.save_settings({"auto_update_check": False, "last_update_check": 5}, path))
            self.assertEqual(self.up.load_settings(path)["auto_update_check"], False)
            with open(path, "w") as f:
                f.write("{broken")
            self.assertEqual(self.up.load_settings(path), {})                          # damaged file -> defaults
        self.assertTrue(self.up.should_check({}, now=10 ** 9))                          # on by default (never checked before)
        self.assertFalse(self.up.should_check({"auto_update_check": False}, now=10 ** 9))
        self.assertFalse(self.up.should_check({"last_update_check": 1000}, now=1000 + 60))     # checked a minute ago
        self.assertTrue(self.up.should_check({"last_update_check": 1000}, now=1000 + self.up.CHECK_INTERVAL))


class UpdaterWithoutGit(unittest.TestCase):
    """No git on the computer: GitHub's API + snapshot download, Python only."""
    u = load("installer/updater.py")
    SHA1, SHA2 = "a" * 40, "b" * 40

    def no_git(self, *a, **k):
        raise FileNotFoundError("git")

    def snapshot(self, d, files, extra=None):
        import io
        import tarfile
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for name, data in dict(files, **(extra or {})).items():
                ti = tarfile.TarInfo(name)
                ti.size = len(data)
                ti.mode = 0o755 if name.endswith(".sh") else 0o644
                tar.addfile(ti, io.BytesIO(data))
        return io.BytesIO(buf.getvalue())

    def folder(self, d):
        root = os.path.join(d, "ls")
        os.makedirs(root)
        with open(os.path.join(root, "install.sh"), "w") as f:
            f.write("old\n")
        with open(os.path.join(root, "mine.txt"), "w") as f:
            f.write("keep\n")
        return root

    def test_missing_git_switches_to_archive_mode(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.folder(d)
            calls = []

            def fetch(url):
                calls.append(url)
                return {"sha": self.SHA2}
            res = self.u.check(root, run=self.no_git, fetch=fetch)
            self.assertEqual(res["mode"], "archive")
            self.assertIsNone(res["behind"])                         # commit unknown the first time
            self.assertTrue(res["local"]["git_missing"])
            self.assertEqual(res["latest"], self.SHA2)

    def test_behind_uses_the_compare_api_and_marker(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.folder(d)
            with open(os.path.join(root, ".installed-sha"), "w") as f:
                f.write(self.SHA1 + "\n")

            def fetch(url):
                if url.endswith("/commits/main"):
                    return {"sha": self.SHA2}
                self.assertIn(f"compare/{self.SHA1}...{self.SHA2}", url)
                return {"ahead_by": 2, "commits": [{"sha": "1" * 40, "commit": {"message": "first\n\nbody"}},
                                                    {"sha": "2" * 40, "commit": {"message": "second"}}]}
            res = self.u.check(root, run=self.no_git, fetch=fetch)
            self.assertEqual((res["mode"], res["behind"]), ("archive", 2))
            self.assertEqual(res["commits"][0], ("2222222", "second"))        # newest first
            with open(os.path.join(root, ".installed-sha"), "w") as f:
                f.write(self.SHA2 + "\n")
            self.assertEqual(self.u.check(root, run=self.no_git, fetch=fetch)["behind"], 0)

    def test_offline_is_an_error_not_a_crash(self):
        with tempfile.TemporaryDirectory() as d:
            def boom(url):
                raise OSError("offline")
            res = self.u.check(self.folder(d), run=self.no_git, fetch=boom)
            self.assertEqual(res["mode"], "error")
            self.assertIn("offline", res["error"])

    def test_update_replaces_changed_files_backs_up_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.folder(d)
            snap = self.snapshot(d, {"ls-main/install.sh": b"new\n", "ls-main/installer/new.py": b"x\n", "ls-main/run.sh": b"#!/bin/sh\n"})
            ok, msg = self.u.update_archive(root, self.SHA2, opener=lambda req, timeout=0: snap, backup_dir=os.path.join(d, "bak"))
            self.assertTrue(ok, msg)
            self.assertEqual(open(os.path.join(root, "install.sh")).read(), "new\n")
            self.assertEqual(open(os.path.join(root, "mine.txt")).read(), "keep\n")
            self.assertTrue(os.path.exists(os.path.join(root, "installer", "new.py")))
            self.assertEqual(open(os.path.join(d, "bak", "install.sh")).read(), "old\n")
            self.assertTrue(os.access(os.path.join(root, "run.sh"), os.X_OK))
            self.assertEqual(open(os.path.join(root, ".installed-sha")).read().strip(), self.SHA2)

    def test_hostile_or_wrong_archives_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.folder(d)
            evil = self.snapshot(d, {"x/install.sh": b"n\n"}, {"x/../../escape.txt": b"boom"})
            ok, msg = self.u.update_archive(root, self.SHA2, opener=lambda req, timeout=0: evil, backup_dir=os.path.join(d, "b"))
            self.assertTrue(ok, msg)
            self.assertFalse(os.path.exists(os.path.join(d, "escape.txt")))
            self.assertFalse(os.path.exists(os.path.join(os.path.dirname(root), "escape.txt")))
            wrong = self.snapshot(d, {"x/readme": b"n\n"})
            ok, msg = self.u.update_archive(root, self.SHA2, opener=lambda req, timeout=0: wrong)
            self.assertFalse(ok)
            ok, msg = self.u.update_archive(root, "not-a-sha")
            self.assertFalse(ok)
            ok, msg = self.u.update_archive(d, self.SHA2)                # no install.sh there
            self.assertFalse(ok)

    def test_preview_lists_what_would_change_and_touches_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.folder(d)
            snap = self.snapshot(d, {"ls-main/install.sh": b"new\n", "ls-main/a/b.py": b"x\n", "ls-main/same.txt": b"s\n"})
            with open(os.path.join(root, "same.txt"), "w") as f:
                f.write("s\n")
            ok, files = self.u.preview_archive(root, self.SHA2, opener=lambda req, timeout=0: snap)
            self.assertTrue(ok, files)
            self.assertEqual(files, [("changed", "install.sh"), ("new", "a/b.py")])
            with open(os.path.join(root, "install.sh")) as f:
                self.assertEqual(f.read(), "old\n")
            self.assertFalse(os.path.exists(os.path.join(root, ".installed-sha")))
            ok, msg = self.u.preview_archive(root, "zz")
            self.assertFalse(ok)

    def test_settings_has_a_github_button(self):
        self.assertEqual(self.u.REPO_PAGE, "https://github.com/kapo-Toolkits/linux-scripts")
        self.assertEqual(self.u.REPO_URL, self.u.REPO_PAGE + ".git")
        self.assertTrue(hasattr(Installer.m.App, "open_repo"))
        with mock.patch("webbrowser.open", return_value=True) as wb:
            Installer.m.App.open_repo(object())
        wb.assert_called_once_with(self.u.REPO_PAGE)

    def test_apply_dispatches_and_banner(self):
        with mock.patch.object(self.u, "update_archive", return_value=(True, "ok")) as ua:
            self.assertEqual(self.u.apply("/x", {"mode": "archive", "latest": self.SHA2}), (True, "ok"))
            ua.assert_called_once_with("/x", self.SHA2)
        b = Installer.m.banner_for
        self.assertEqual(b({"mode": "archive", "behind": 3}, {}, 1000), ("behind", 3))
        self.assertIsNone(b({"mode": "archive", "behind": 0}, {}, 1000))
        self.assertEqual(b({"mode": "archive", "behind": None}, {}, 1000), ("plain", None))
        self.assertIsNone(b({"mode": "archive", "behind": None}, {"update_snooze_until": 5000}, 1000))


class VendorPrograms(unittest.TestCase):
    """VS Code, Discord, RustDesk, Tabby, WinBoat, ArtCraft: how they are fetched and verified."""
    ex = Installer.m.extras

    def release(self, app_id, names):
        v = "9.9.9"
        return {"tag": "v" + v, "version": v,
                "assets": {n.format(v=v): {"url": "https://github.com/x/" + n.format(v=v), "size": 5 << 20, "sha256": "ab" * 32}
                           for n in names}}

    def test_github_apps_pick_the_right_deb_and_gate_on_sha256(self):
        for app_id, app in self.ex.GITHUB_APPS.items():
            rel = self.release(app_id, app["asset"].values())
            steps, info = self.ex.github_steps(app_id, rel, "apt-get", "x86_64")
            self.assertEqual([x["root"] for x in steps], [False, True, False], app_id)
            self.assertIn("sha256sum -c", steps[0]["sh"])
            self.assertIn("--proto '=https'", steps[0]["sh"])
            self.assertLess(steps[0]["sh"].index("sha256sum -c"), steps[0]["sh"].index("mv "))
            self.assertIn("apt-get install -y", steps[1]["sh"])
            self.assertEqual(info["sha256"], "ab" * 32)
            for st in steps:
                self.assertEqual(subprocess.run(["sh", "-n", "-c", st["sh"]], capture_output=True).returncode, 0, app_id)
            for pm, arch in (("dnf", "x86_64"), ("apt-get", "i386"), ("pacman", "x86_64")):
                steps, info = self.ex.github_steps(app_id, rel, pm, arch)
                self.assertEqual(steps, [])
                self.assertIn("github.com/" + app["repo"], info["manual"])

    def test_no_digest_means_no_install(self):
        rel = self.release("tabby", self.ex.GITHUB_APPS["tabby"]["asset"].values())
        for a in rel["assets"].values():
            a["sha256"] = ""
        self.assertEqual(self.ex.github_steps("tabby", rel, "apt-get", "amd64")[0], [])

    def test_arm_only_where_the_project_ships_it(self):
        for app_id, ok in (("rustdesk", True), ("tabby", True), ("artcraft", True), ("winboat", False)):
            rel = self.release(app_id, self.ex.GITHUB_APPS[app_id]["asset"].values())
            self.assertEqual(bool(self.ex.github_steps(app_id, rel, "apt-get", "aarch64")[0]), ok, app_id)

    def test_release_lookup_reads_digests(self):
        data = {"tag_name": "v1.2", "assets": [{"name": "a.deb", "browser_download_url": "https://h/a.deb", "size": 3,
                                                  "digest": "sha256:" + "cd" * 32}, {"name": "b", "browser_download_url": "u"}]}
        rel = self.ex.github_release("winboat", fetch=lambda url: data)
        self.assertEqual(rel["version"], "1.2")
        self.assertEqual(rel["assets"]["a.deb"]["sha256"], "cd" * 32)
        self.assertEqual(rel["assets"]["b"]["sha256"], "")

    def test_vscode_recipe(self):
        steps, info = self.ex.vscode_steps("apt-get", "amd64")
        sh = steps[0]["sh"]
        self.assertEqual(subprocess.run(["sh", "-n", "-c", sh], capture_output=True).returncode, 0)
        self.assertIn("BC528686B50D79E339D3721CEB3E94ADBE1229CF", sh)
        self.assertLess(sh.index("KEY FINGERPRINT MISMATCH"), sh.index("install -D -m644"))
        self.assertIn("https://packages.microsoft.com/repos/code", sh)
        self.assertTrue(sh.rstrip().endswith("apt-get install -y code"))
        self.assertEqual(self.ex.vscode_steps("dnf", "x86_64")[0], [])

    def test_discord_recipe(self):
        steps, info = self.ex.discord_steps("apt-get", "x86_64")
        self.assertEqual([x["root"] for x in steps], [False, True, False])
        self.assertIn("--proto '=https'", steps[0]["sh"])
        self.assertIn("--proto-redir '=https'", steps[0]["sh"])
        self.assertIn("grep -qx discord", steps[0]["sh"])             # what arrived must be the discord package
        for st in steps:
            self.assertEqual(subprocess.run(["sh", "-n", "-c", st["sh"]], capture_output=True).returncode, 0)
        self.assertEqual(self.ex.discord_steps("apt-get", "aarch64")[0], [])

    def test_installed_and_remove(self):
        ok = types.SimpleNamespace(returncode=0, stdout="install ok installed")
        gone = types.SimpleNamespace(returncode=1, stdout="")
        self.assertTrue(self.ex.deb_installed("code", run=lambda *a, **k: ok, which=lambda c: "/x"))
        self.assertFalse(self.ex.deb_installed("code", run=lambda *a, **k: gone, which=lambda c: "/x" if c == "dpkg-query" else None))
        self.assertTrue(self.ex.deb_installed("code", "code", run=lambda *a, **k: gone, which=lambda c: "/x"))
        self.assertIn("apt-get purge -y rustdesk", self.ex.apt_remove_steps("rustdesk", "apt-get")[0]["sh"])
        self.assertEqual(self.ex.apt_remove_steps("rustdesk", "dnf"), [])

    def test_every_new_program_is_in_the_window_and_the_shortcuts(self):
        ids = {x["id"] for x in Installer.m.EXTRAS}
        sc = {x["id"] for x in load("shortcuts/shortcuts-gui.py").TOOLS}
        for i in ("vscode", "discord", *self.ex.GITHUB_APPS):
            self.assertIn(i, ids)
            self.assertIn(i, sc)


class ProgramUpdates(unittest.TestCase):
    ex = Installer.m.extras

    def test_version_compare(self):
        k = self.ex.version_key
        self.assertEqual(k("1:2.1.7-3"), (2, 1, 7))
        self.assertEqual(k("v0.4.1"), (0, 4, 1))
        self.assertEqual(k("1.0.161"), (1, 0, 161))
        self.assertGreater(k("1.0.238"), k("1.0.99"))            # numbers, not text
        self.assertGreater(k("0.4.1"), k("0.3.2-1"))
        self.assertEqual(k("1.142.0-1792035033"), (1, 142, 0))

    def test_only_installed_and_older_ones_are_reported(self):
        have = {"rustdesk": "1.4.0", "tabby-terminal": "1.0.238", "balena-etcher": "2.1.7"}
        rel = {"rustdesk": "1.5.0", "tabby": "1.0.238", "winboat": "9.9.9", "artcraft": "9.9.9"}
        found, failed = self.ex.outdated(installed=have.get, github=lambda i: {"version": rel[i]},
                                         etcher=lambda: {"version": "2.1.8"})
        self.assertEqual({x["id"] for x in found}, {"rustdesk", "etcher"})      # winboat/artcraft not installed, tabby current
        self.assertEqual(failed, [])
        r = next(x for x in found if x["id"] == "rustdesk")
        self.assertEqual((r["installed"], r["latest"]), ("1.4.0", "1.5.0"))

    def test_a_failed_lookup_is_named_not_guessed(self):
        def boom(i):
            raise OSError("offline")
        found, failed = self.ex.outdated(installed=lambda p: "1.0" if p == "rustdesk" else None, github=boom)
        self.assertEqual((found, failed), ([], ["rustdesk"]))

    def test_installed_version(self):
        ok = types.SimpleNamespace(returncode=0, stdout="install ok installed 1.5.0")
        self.assertEqual(self.ex.installed_version("x", run=lambda *a, **k: ok, which=lambda c: "/x"), "1.5.0")
        self.assertIsNone(self.ex.installed_version("x", run=lambda *a, **k: ok, which=lambda c: None))


class FullRemoval(unittest.TestCase):
    """Uninstall takes the program AND what the installer added to apt (repository entry, key) off the system."""
    ex = Installer.m.extras

    def fake_bin(self, d, insiders=False):
        b = os.path.join(d, "bin")
        os.makedirs(b)
        log = os.path.join(d, "log")
        with open(os.path.join(b, "apt-get"), "w") as f:
            f.write(f'#!/bin/sh\necho "apt-get $*" >> {log}\n')
        with open(os.path.join(b, "dpkg"), "w") as f:
            f.write(f'#!/bin/sh\nexit {0 if insiders else 1}\n')
        for n in ("apt-get", "dpkg"):
            os.chmod(os.path.join(b, n), 0o755)
        return b, log

    def run_sh(self, sh, bindir):
        return subprocess.run(["sh", "-c", sh], capture_output=True, text=True, env=dict(os.environ, PATH=bindir + ":" + os.environ["PATH"]))

    def test_vscode_repository_and_key_go_with_the_program(self):
        with tempfile.TemporaryDirectory() as d:
            b, log = self.fake_bin(d)
            src = os.path.join(d, "sources.list.d")
            os.makedirs(src)
            key, lst = os.path.join(d, "microsoft.gpg"), os.path.join(src, "vscode.sources")
            for f in (key, lst):
                open(f, "w").close()
            sh = self.ex.vscode_remove_steps("apt-get", sources_dir=src, keyring=key, listfile=lst)[0]["sh"]
            r = self.run_sh(sh, b)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse(os.path.exists(lst))
            self.assertFalse(os.path.exists(key))
            self.assertIn("apt-get purge -y code", open(log).read())

    def test_vscode_key_stays_when_another_source_uses_it(self):
        with tempfile.TemporaryDirectory() as d:
            b, log = self.fake_bin(d)
            src = os.path.join(d, "sources.list.d")
            os.makedirs(src)
            key, lst = os.path.join(d, "microsoft.gpg"), os.path.join(src, "vscode.sources")
            open(key, "w").close()
            open(lst, "w").close()
            with open(os.path.join(src, "edge.sources"), "w") as f:
                f.write("Signed-By: /usr/share/keyrings/microsoft.gpg\n")
            self.run_sh(self.ex.vscode_remove_steps("apt-get", sources_dir=src, keyring=key, listfile=lst)[0]["sh"], b)
            self.assertFalse(os.path.exists(lst))
            self.assertTrue(os.path.exists(key))

    def test_vscode_repository_stays_when_insiders_is_installed(self):
        with tempfile.TemporaryDirectory() as d:
            b, log = self.fake_bin(d, insiders=True)
            src = os.path.join(d, "s")
            os.makedirs(src)
            key, lst = os.path.join(d, "microsoft.gpg"), os.path.join(src, "vscode.sources")
            open(key, "w").close()
            open(lst, "w").close()
            self.run_sh(self.ex.vscode_remove_steps("apt-get", sources_dir=src, keyring=key, listfile=lst)[0]["sh"], b)
            self.assertTrue(os.path.exists(lst) and os.path.exists(key))

    def test_claude_files_are_removed(self):
        with tempfile.TemporaryDirectory() as d:
            b, log = self.fake_bin(d)
            key, lst = os.path.join(d, "k.asc"), os.path.join(d, "c.list")
            open(key, "w").close()
            open(lst, "w").close()
            self.run_sh(self.ex.claude_remove_steps("apt-get", keyring=key, listfile=lst)[0]["sh"], b)
            self.assertFalse(os.path.exists(key) or os.path.exists(lst))
            self.assertIn("apt-get purge -y claude-desktop", open(log).read())

    def test_every_removal_on_apt_is_a_purge_and_others_stay_possible(self):
        for sh in (self.ex.etcher_remove_steps("apt-get")[0]["sh"], self.ex.brave_remove_steps("apt-get")[0]["sh"],
                   self.ex.apt_remove_steps("x", "apt-get")[0]["sh"], self.ex.package_steps("k3b", "apt-get", remove=True)[0]["sh"]):
            self.assertIn("apt-get purge -y", sh)
            self.assertNotIn("apt-get remove", sh)
        self.assertEqual(self.ex.vscode_remove_steps("dnf"), [])
        self.assertIn("dnf remove", self.ex.etcher_remove_steps("dnf")[0]["sh"])


class PersonalData(unittest.TestCase):
    ex = Installer.m.extras

    def home(self, d):
        h = os.path.join(d, "home")
        for p in (".config/Code/User", ".vscode/extensions", ".config/discord", ".config/keepme"):
            os.makedirs(os.path.join(h, p))
        for p in (".config/Code/User/settings.json", ".config/discord/x", ".config/keepme/y"):
            with open(os.path.join(h, p), "w") as f:
                f.write("data")
        return h

    def test_only_existing_data_of_the_selected_programs_is_listed(self):
        with tempfile.TemporaryDirectory() as d:
            h = self.home(d)
            found = self.ex.data_paths(["vscode", "winboat"], home=h)
            names = sorted(os.path.relpath(p, os.path.realpath(h)) for p, _n in found)
            self.assertEqual(names, [".config/Code", ".vscode"])          # discord not selected, winboat has nothing
            self.assertEqual(dict(found)[os.path.join(os.path.realpath(h), ".config/Code")], 4)

    def test_remove_deletes_only_what_it_was_given(self):
        with tempfile.TemporaryDirectory() as d:
            h = self.home(d)
            paths = [p for p, _n in self.ex.data_paths(["vscode", "discord"], home=h)]
            done, failed = self.ex.remove_data(paths, home=h)
            self.assertEqual((len(done), failed), (3, []))
            self.assertFalse(os.path.exists(os.path.join(h, ".config/Code")))
            self.assertFalse(os.path.exists(os.path.join(h, ".config/discord")))
            self.assertTrue(os.path.exists(os.path.join(h, ".config/keepme/y")))

    def test_it_refuses_the_home_folder_and_anything_outside_it(self):
        with tempfile.TemporaryDirectory() as d:
            h = self.home(d)
            outside = os.path.join(d, "outside")
            os.makedirs(outside)
            done, failed = self.ex.remove_data([h, outside, "/etc", os.path.join(h, ".config")], home=h)
            self.assertTrue(os.path.isdir(h) and os.path.isdir(outside) and os.path.isdir("/etc"))
            self.assertEqual(len(failed), 3)                              # home itself, outside, /etc
            self.assertEqual(done, [os.path.join(h, ".config")])        # a real folder inside home is allowed

    def test_a_symlink_is_removed_but_never_followed(self):
        with tempfile.TemporaryDirectory() as d:
            h = self.home(d)
            target = os.path.join(d, "precious")
            os.makedirs(target)
            with open(os.path.join(target, "f"), "w") as f:
                f.write("x")
            link = os.path.join(h, ".config", "discord_link")
            os.symlink(target, link)
            done, failed = self.ex.remove_data([link], home=h)
            self.assertEqual((done, failed), ([link], []))
            self.assertTrue(os.path.exists(os.path.join(target, "f")))

    def test_every_program_with_data_is_known_to_the_window(self):
        ids = {x["id"] for x in Installer.m.EXTRAS}
        self.assertEqual(set(self.ex.DATA_DIRS), ids)
        for paths in self.ex.DATA_DIRS.values():
            for p in paths:
                self.assertTrue(p.startswith("~/") and ".." not in p)


class FlatpakRoute(unittest.TestCase):
    ex = Installer.m.extras
    App = Installer.m.App

    def test_install_steps(self):
        steps, info = self.ex.flatpak_steps("discord", "dnf", False)
        self.assertEqual([x["root"] for x in steps], [True, False])
        self.assertIn("dnf install -y flatpak", steps[0]["sh"])
        self.assertIn("flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo", steps[1]["sh"])
        self.assertIn("flatpak install -y --user flathub com.discordapp.Discord", steps[1]["sh"])
        self.assertTrue(info["needs_flatpak"])
        steps, info = self.ex.flatpak_steps("vscode", "pacman", True)
        self.assertEqual([x["root"] for x in steps], [False])               # no administrator password at all
        for st in steps:
            self.assertEqual(subprocess.run(["sh", "-n", "-c", st["sh"]], capture_output=True).returncode, 0)

    def test_no_flathub_entry_or_no_way_to_get_flatpak_means_the_manual_page(self):
        self.assertEqual(self.ex.flatpak_steps("winboat", "dnf", True)[0], [])
        self.assertEqual(self.ex.flatpak_steps("discord", "unknown-pm", False)[0], [])
        self.assertEqual(self.ex.flatpak_steps("discord", "unknown-pm", False)[1]["manual"], self.ex.FLATPAK_SETUP)

    def test_remove_steps_follow_the_scope(self):
        steps, _ = self.ex.flatpak_steps("rustdesk", "dnf", True, remove_scopes={"user"})
        self.assertEqual([x["root"] for x in steps], [False])
        steps, _ = self.ex.flatpak_steps("rustdesk", "dnf", True, remove_scopes={"user", "system"})
        self.assertEqual([x["root"] for x in steps], [False, True])

    def test_scopes_come_from_flatpak_info(self):
        def run(cmd, **k):
            return types.SimpleNamespace(returncode=0 if "--user" in cmd else 1)
        self.assertEqual(self.ex.flatpak_scopes("discord", run=run, which=lambda c: "/x"), {"user"})
        self.assertEqual(self.ex.flatpak_scopes("discord", run=run, which=lambda c: None), set())
        self.assertEqual(self.ex.flatpak_scopes("winboat", run=run, which=lambda c: "/x"), set())

    def test_every_flatpak_program_is_known_and_has_its_data_folder_listed(self):
        ids = {x["id"] for x in Installer.m.EXTRAS}
        self.assertTrue(set(self.ex.FLATPAK_IDS) <= ids)
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".var/app/com.discordapp.Discord/config"))
            found = [os.path.relpath(p, os.path.realpath(d)) for p, _n in self.ex.data_paths(["discord"], home=d)]
            self.assertEqual(found, [".var/app/com.discordapp.Discord"])

    def fake_app(self, native, scopes, pm, asked=True):
        app = types.SimpleNamespace()
        app.ex_native_state = lambda i: "yes" if native else None
        app.steps_to_jobs = lambda steps: [["job"] for _ in steps]
        m = Installer.m
        return app, mock.patch.multiple(m, detect_pm=lambda: pm, messagebox=mock.Mock(askyesno=lambda *a, **k: asked, showinfo=mock.Mock()),
                                        t=lambda k, **kw: k), mock.patch.object(self.ex, "flatpak_scopes", lambda i: scopes)

    def test_routing(self):
        with mock.patch("platform.machine", return_value="x86_64"):
            app, p1, p2 = self.fake_app(False, set(), "apt-get")
            with p1, p2:
                self.assertEqual(self.App.flatpak_jobs(app, "install", "discord"), (False, []))        # apt: the normal route
            app, p1, p2 = self.fake_app(False, set(), "dnf")
            with p1, p2, mock.patch("shutil.which", return_value="/usr/bin/flatpak"):
                handled, jobs = self.App.flatpak_jobs(app, "install", "discord")
                self.assertTrue(handled)
                self.assertEqual(len(jobs), 1)
            app, p1, p2 = self.fake_app(False, set(), "dnf", asked=False)
            with p1, p2, mock.patch("shutil.which", return_value="/usr/bin/flatpak"):
                self.assertEqual(self.App.flatpak_jobs(app, "install", "discord"), (True, None))       # declined
            app, p1, p2 = self.fake_app(False, {"user"}, "dnf")
            with p1, p2:
                self.assertEqual(self.App.flatpak_jobs(app, "uninstall", "discord")[0], True)           # flatpak only: that is all
            app, p1, p2 = self.fake_app(True, {"user"}, "apt-get")
            with p1, p2:
                handled, jobs = self.App.flatpak_jobs(app, "uninstall", "discord")
                self.assertEqual((handled, len(jobs)), (False, 1))                                      # both: flatpak + the normal route
            app, p1, p2 = self.fake_app(True, set(), "apt-get")
            with p1, p2:
                self.assertEqual(self.App.flatpak_jobs(app, "uninstall", "discord"), (False, []))
            with p1, p2:
                self.assertEqual(self.App.flatpak_jobs(app, "install", "claude"), (False, []))          # no flatpak for it


class RunControl(unittest.TestCase):
    m = Installer.m

    def test_curl_progress_lines_become_percentages(self):
        f = self.m.progress_percent
        self.assertEqual(f("######                                                     10.5%\n"), 10.5)
        self.assertEqual(f("#################################################### 100.0%"), 100.0)
        self.assertIsNone(f("SHA-256 verified: 5ea2"))
        self.assertIsNone(f("Reading package lists... 100%"))            # not curl's bar (no '#')
        self.assertIsNone(f(""))

    def test_cancel_stops_a_user_command_and_the_next_steps(self):
        import threading
        import time as _t
        ctl = {"cancel": False}
        lines = []
        threading.Timer(0.6, lambda: (ctl.update(cancel=True), self.m.stop_process(ctl["proc"]))).start()
        t0 = _t.time()
        rc = self.m.run_jobs([["sh", "-c", "echo start; sleep 30"], ["sh", "-c", "echo SHOULD-NOT-RUN"]], lines.append, ctl)
        self.assertLess(_t.time() - t0, 10)
        self.assertEqual(rc, 130)
        self.assertIn("start\n", lines)
        self.assertNotIn("SHOULD-NOT-RUN\n", lines)

    def test_cancel_between_steps(self):
        ctl = {"cancel": True}
        lines = []
        self.assertEqual(self.m.run_jobs([["sh", "-c", "echo no"]], lines.append, ctl), 130)
        self.assertEqual(lines, [])

    def test_an_elevated_command_is_not_killed(self):
        ctl = {"cancel": True}
        lines = []
        with mock.patch.object(self.m, "ROOT", "/"):
            rc = self.m.run_command(["sh", "-c", "echo done"], lines.append, dict(ctl, elevated=False))
        self.assertEqual(lines, ["done\n"])
        # a command named pkexec / sudo sets ctl["elevated"], so the cancel flag never terminates it
        fake = os.path.join(tempfile.mkdtemp(), "sudo")
        with open(fake, "w") as f:
            f.write("#!/bin/sh\nsleep 1\necho finished\n")
        os.chmod(fake, 0o755)
        ctl2 = {"cancel": True}
        lines2 = []
        rc2 = self.m.run_command([fake], lines2.append, ctl2)
        self.assertEqual((rc2, lines2), (0, ["finished\n"]))


class AutoApply(unittest.TestCase):
    f = staticmethod(Installer.m.should_auto_apply)

    def test_it_is_opt_in_and_only_for_clear_cases(self):
        git = {"mode": "git", "behind": 2, "local": {"dirty": []}}
        self.assertFalse(self.f(git, {}))                                       # off by default
        self.assertTrue(self.f(git, {"auto_apply_update": True}))
        self.assertFalse(self.f(dict(git, local={"dirty": ["install.sh"]}), {"auto_apply_update": True}))   # local changes
        self.assertFalse(self.f(dict(git, ahead=1), {"auto_apply_update": True}))                           # local commits
        self.assertFalse(self.f(dict(git, behind=0), {"auto_apply_update": True}))
        self.assertTrue(self.f({"mode": "archive", "behind": 3, "local": {}}, {"auto_apply_update": True}))
        self.assertFalse(self.f({"mode": "archive", "behind": None, "local": {}}, {"auto_apply_update": True}))  # unknown: show list first
        self.assertFalse(self.f({"mode": "adopt", "behind": None, "local": {}}, {"auto_apply_update": True}))
        self.assertFalse(self.f(None, {"auto_apply_update": True}))


class InstallerLog(unittest.TestCase):
    m = Installer.m

    def test_lines_are_appended_old_files_are_pruned(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(14):
                with open(os.path.join(d, f"installer-202601{i + 10:02d}.log"), "w") as f:
                    f.write("old\n")
            path = os.path.join(d, "installer-20260201.log")
            self.assertTrue(self.m.log_line("first", path))
            self.assertTrue(self.m.log_line("second\n", path))
            text = self.m.read_log(path)
            self.assertIn("first\n", text)
            self.assertTrue(text.splitlines()[1].endswith(" second"))
            self.assertEqual(len([x for x in os.listdir(d) if x.endswith(".log")]), self.m.LOG_KEEP)
            self.assertTrue(os.path.exists(path))                            # the newest survives

    def test_it_never_raises(self):
        self.assertFalse(self.m.log_line("x", "/proc/nope/installer-1.log"))
        self.assertEqual(self.m.read_log("/nonexistent/installer.log"), "")

    def test_read_log_returns_only_the_tail(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "installer-x.log")
            with open(path, "w") as f:
                f.write("".join(f"line{i}\n" for i in range(1000)))
            tail = self.m.read_log(path, max_lines=5)
            self.assertEqual(tail.splitlines(), [f"line{i}" for i in range(995, 1000)])

    def test_log_dir_honours_xdg_cache(self):
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": "/x/cache"}):
            self.assertEqual(self.m.log_dir(), "/x/cache/linux-scripts/logs")


class ProgramsRegistry(unittest.TestCase):
    ex = Installer.m.extras

    def base(self):
        with open(self.ex.PROGRAMS_FILE, encoding="utf-8") as f:
            return json.load(f)

    def load(self, data):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "programs.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            return self.ex.load_programs(path)

    def test_the_shipped_file_is_valid_and_drives_everything(self):
        progs = self.ex.PROGRAMS
        self.assertGreaterEqual(len(progs), 12)
        self.assertEqual([x["id"] for x in Installer.m.EXTRAS], [p["id"] for p in progs])
        self.assertEqual(set(self.ex.GITHUB_APPS), {p["id"] for p in progs if p["kind"] == "github"})
        self.assertEqual(set(Installer.m.GROUP_TEXT), set(self.base()["groups"]))

    def test_every_program_has_a_shortcut_entry_so_the_two_lists_cannot_drift(self):
        sc = {x["id"] for x in load("shortcuts/shortcuts-gui.py").TOOLS}
        for p in self.ex.PROGRAMS:
            sid = p.get("shortcut", p["id"])   # the shortcuts tool names a few programs differently
            self.assertIn(sid, sc, p["id"])

    def test_adding_a_program_is_one_entry(self):
        data = self.base()
        data["programs"].append({"id": "newapp", "group": "more", "kind": "github", "display": "NewApp", "repo": "o/r",
                                 "package": "newapp", "cmd": "newapp", "asset": {"x86": "newapp-{v}.deb"},
                                 "name": {"en": "NewApp", "ka": "NewApp"}, "info": {"en": "x", "ka": "y"}, "data": ["~/.config/newapp"]})
        loaded = self.load(data)
        self.assertEqual(loaded["programs"][-1]["id"], "newapp")

    def test_mistakes_are_named(self):
        for mutate, needle in (
                (lambda d: d["programs"].append(dict(d["programs"][0])), "appears twice"),
                (lambda d: d["programs"][0].update(kind="nonsense"), "kind must be"),
                (lambda d: d["programs"][0].update(group="nope"), "group must be"),
                (lambda d: d["programs"][0]["name"].pop("ka"), "both en and ka"),
                (lambda d: next(p for p in d["programs"] if p["kind"] == "github").pop("repo"), "needs 'repo'"),
                (lambda d: d["programs"][0].update(data=["/etc"]), "data paths"),
                (lambda d: d["programs"][0].update(data=["~/../etc"]), "data paths")):
            data = self.base()
            mutate(data)
            with self.assertRaises(ValueError) as cm:
                self.load(data)
            self.assertIn(needle, str(cm.exception))


class GetScript(unittest.TestCase):
    """get.sh: the one-file bootstrap. GitHub is replaced by a local snapshot (LS_SNAPSHOT), everything else is real."""

    def snapshot(self, d):
        snap = os.path.join(d, "snap.tar.gz")
        top = os.path.join(d, "top")
        os.makedirs(top)
        os.symlink(ROOT, os.path.join(top, "linux-scripts"))
        subprocess.run(["tar", "-czhf", snap, "-C", top, "--exclude=.git", "--exclude=__pycache__", "--exclude=.installed-sha",
                        "--exclude=start-installer.desktop", "linux-scripts"], check=True, capture_output=True)
        return snap

    def run_get(self, d, *args, snap=None):
        env = dict(os.environ, HOME=os.path.join(d, "home"), LS_SNAPSHOT=snap or self.snapshot(d), LS_SHA="a" * 40,
                   XDG_CACHE_HOME=os.path.join(d, "cache"), XDG_DATA_HOME=os.path.join(d, "data"))
        os.makedirs(env["HOME"], exist_ok=True)
        return subprocess.run(["sh", os.path.join(ROOT, "get.sh"), *args], capture_output=True, text=True, env=env, timeout=120)

    def test_syntax(self):
        self.assertEqual(subprocess.run(["sh", "-n", os.path.join(ROOT, "get.sh")], capture_output=True).returncode, 0)

    def test_fresh_install_into_a_folder(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "home", "linux-scripts")
            r = self.run_get(d, "--no-start")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for f in ("install.sh", "installer/start.sh", "installer/installer-gui.py", "installer/programs.json"):
                self.assertTrue(os.path.isfile(os.path.join(dest, f)), f)
            with open(os.path.join(dest, ".installed-sha")) as fh:
                self.assertEqual(fh.read().strip(), "a" * 40)                  # the updater can tell what this copy is
            self.assertTrue(os.path.isfile(os.path.join(dest, "start-installer.desktop")))       # launcher for THIS folder

    def test_an_existing_copy_is_backed_up_and_own_files_stay(self):
        with tempfile.TemporaryDirectory() as d:
            snap = self.snapshot(d)
            self.assertEqual(self.run_get(d, "--no-start", snap=snap).returncode, 0)
            dest = os.path.join(d, "home", "linux-scripts")
            with open(os.path.join(dest, "my-notes.txt"), "w") as f:
                f.write("mine")
            with open(os.path.join(dest, "install.sh"), "w") as f:
                f.write("edited")
            r = self.run_get(d, "--no-start", snap=snap)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            backups = [x for x in os.listdir(os.path.join(d, "home")) if x.startswith("linux-scripts.backup-")]
            self.assertEqual(len(backups), 1)
            with open(os.path.join(d, "home", backups[0], "install.sh")) as f:
                self.assertEqual(f.read(), "edited")
            with open(os.path.join(dest, "install.sh")) as f:
                self.assertNotEqual(f.read(), "edited")                        # replaced by the snapshot's
            self.assertTrue(os.path.exists(os.path.join(dest, "my-notes.txt")))

    def test_an_unrelated_folder_is_never_touched(self):
        with tempfile.TemporaryDirectory() as d:
            other = os.path.join(d, "stuff")
            os.makedirs(other)
            with open(os.path.join(other, "important.txt"), "w") as f:
                f.write("x")
            r = self.run_get(d, other, "--no-start")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("not a toolkit folder", r.stderr)
            self.assertEqual(os.listdir(other), ["important.txt"])

    def test_a_wrong_download_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.tar.gz")
            os.makedirs(os.path.join(d, "t", "x"))
            with open(os.path.join(d, "t", "x", "readme"), "w") as f:
                f.write("not the toolkit")
            subprocess.run(["tar", "-czf", bad, "-C", os.path.join(d, "t"), "x"], check=True)
            r = self.run_get(d, "--no-start", snap=bad)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("does not look like", r.stderr)
            self.assertFalse(os.path.exists(os.path.join(d, "home", "linux-scripts", "install.sh")))


class GisCatalogue(unittest.TestCase):
    ex = Installer.m.extras

    def base(self):
        with open(self.ex.GIS_FILE, encoding="utf-8") as f:
            return json.load(f)

    def load(self, data):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "gis.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            return self.ex.load_gis(path)

    def test_the_two_lists_are_all_there(self):
        data = self.ex.load_gis()
        self.assertEqual([s["id"] for s in data["sections"]], ["osgeo", "community"])
        names = {p["id"]: p["name"] for p in self.ex.gis_programs(data).values()}
        osgeo = {p["name"] for p in data["sections"][0]["programs"]}
        community = {p["name"] for p in data["sections"][1]["programs"]}
        for n in ("GeoNode", "Marble", "gvSIG Desktop", "QGIS Desktop", "TorchGeo", "PROJ", "GDAL/OGR", "GEOS", "GRASS", "GeoNetwork",
                  "pycsw", "OSGeoLive", "PostGIS", "pgRouting", "pygeoapi", "MapServer", "OpenLayers", "PyWPS", "GeoServer"):
            self.assertIn(n, osgeo)
        for n in ("OSGeo4W", "pygeometa", "SFCGAL", "OWSLib", "QField", "EOEPCA+", "MobilityDB", "rasdaman", "GeoGirafe", "istSOS"):
            self.assertIn(n, community)
        self.assertFalse(osgeo & community)
        self.assertEqual(len(names), len(osgeo) + len(community))                    # ids are unique over both lists

    def test_every_entry_has_a_project_page_and_categories_have_georgian_names(self):
        data = self.ex.load_gis()
        for p in self.ex.gis_programs(data).values():
            self.assertTrue(p["url"].startswith("https://www.osgeo.org/projects/"), p["id"])
            self.assertTrue(data["categories"][p["category"]])

    def test_install_and_remove_steps(self):
        g = self.ex.gis_programs()
        self.assertEqual(self.ex.gis_steps(g["mapserver"], "apt-get")[0]["sh"], "set -u\napt-get install -y mapserver-bin cgi-mapserver\n")
        self.assertIn("apt-get purge -y mapserver-bin cgi-mapserver", self.ex.gis_steps(g["mapserver"], "apt-get", remove=True)[0]["sh"])
        self.assertIn("dnf install -y gdal", self.ex.gis_steps(g["gdal"], "dnf")[0]["sh"])
        self.assertEqual(self.ex.gis_steps(g["grass-gis"], "pacman"), [])             # no package there: honest, no guess
        self.assertEqual(self.ex.gis_steps(g["geoserver"], "apt-get"), [])             # link-only
        for pm in ("apt-get", "dnf", "pacman", "zypper"):
            for item in g.values():
                for st in self.ex.gis_steps(item, pm):
                    self.assertTrue(st["root"])
                    self.assertEqual(subprocess.run(["sh", "-n", "-c", st["sh"]], capture_output=True).returncode, 0)

    def test_installed_needs_every_package(self):
        g = self.ex.gis_programs()
        have = {"cgi-mapserver"}

        def run(cmd, **k):
            return types.SimpleNamespace(returncode=0, stdout="install ok installed" if cmd[-1] in have else "")
        which = lambda c: "/x"            # noqa: E731
        self.assertFalse(self.ex.gis_installed(g["mapserver"], "apt-get", run=run, which=which))
        have.add("mapserver-bin")
        self.assertTrue(self.ex.gis_installed(g["mapserver"], "apt-get", run=run, which=which))
        self.assertFalse(self.ex.gis_installed(g["geoserver"], "apt-get", run=run, which=which))

    def test_mistakes_are_named(self):
        for mutate, needle in (
                (lambda d: d["sections"][1]["programs"].append(dict(d["sections"][0]["programs"][0])), "appears twice"),
                (lambda d: d["sections"][0]["programs"][0].update(category="Nope"), "category must be"),
                (lambda d: d["sections"][0]["programs"][0].update(url="http://x"), "https url"),
                (lambda d: d["sections"][0]["programs"][1].update(packages={"apt-get": ["a b"]}), "bad packages"),
                (lambda d: d["sections"][0]["programs"][1].update(packages={"nix": ["a"]}), "bad packages"),
                (lambda d: d["sections"][0]["title"].pop("ka"), "title needs")):
            data = self.base()
            mutate(data)
            with self.assertRaises(ValueError) as cm:
                self.load(data)
            self.assertIn(needle, str(cm.exception))


class OpenGeos(unittest.TestCase):
    ex = Installer.m.extras

    def test_the_catalogue_has_every_group_of_the_organisations_readme(self):
        data = self.ex.load_opengeos()
        titles = [sec["title"]["en"] for sec in data["sections"]]
        self.assertEqual(titles, ["GIS Platforms", "Python Packages", "Data Catalogs", "QGIS Plugins", "MapLibre GL JS Plugins",
                                  "R Packages", "ArcGIS Toolboxes", "Web Apps", "Useful Resources"])
        items = {it["name"] for sec in data["sections"] for it in sec["items"]}
        for n in ("GeoLibre", "leafmap", "segment-geospatial", "whitebox-python", "Basemaps", "maplibre-gl-swipe", "whiteboxR", "streamlit-geospatial"):
            self.assertIn(n, items)
        self.assertTrue(all(it["url"].startswith("https://") for sec in data["sections"] for it in sec["items"]))
        self.assertEqual(data["org"], "https://github.com/opengeos")

    def test_filter_by_text_and_category(self):
        data = self.ex.load_opengeos()
        every = self.ex.opengeos_filter(data)
        self.assertEqual(sum(len(i) for _s, i in every), sum(len(s["items"]) for s in data["sections"]))
        hit = self.ex.opengeos_filter(data, "LEAFMAP")                                 # case-insensitive
        self.assertTrue(any(it["name"] == "leafmap" for _s, items in hit for it in items))
        only = self.ex.opengeos_filter(data, "", "r-packages")
        self.assertEqual([(s["id"], [i["name"] for i in items]) for s, items in only], [("r-packages", ["whiteboxR"])])
        self.assertEqual(self.ex.opengeos_filter(data, "zzzz-nothing-zzzz"), [])

    def test_mistakes_are_named(self):
        with open(self.ex.OPENGEOS_FILE, encoding="utf-8") as f:
            base = json.load(f)
        for mutate, needle in (
                (lambda d: d["sections"].append(dict(d["sections"][0])), "appears twice"),
                (lambda d: d["sections"][0]["title"].pop("ka"), "title needs"),
                (lambda d: d["sections"][0]["items"][0].update(url="http://x"), "https url"),
                (lambda d: d["intro"].pop("en"), "intro needs")):
            data = json.loads(json.dumps(base))
            mutate(data)
            with tempfile.TemporaryDirectory() as d:
                path = os.path.join(d, "o.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                with self.assertRaises(ValueError) as cm:
                    self.ex.load_opengeos(path)
            self.assertIn(needle, str(cm.exception))


class ClaudeDesktop(unittest.TestCase):
    ex = Installer.m.extras

    def test_only_debian_based_x86_64_or_arm64_get_a_plan(self):
        for arch in ("amd64", "arm64", "x86_64", "aarch64"):
            steps, info = self.ex.claude_steps("apt-get", arch)
            self.assertEqual([x["root"] for x in steps], [True], arch)
        for pm, arch in (("dnf", "x86_64"), ("pacman", "x86_64"), ("", "amd64"), ("apt-get", "armv7l"), ("apt-get", "i386")):
            steps, info = self.ex.claude_steps(pm, arch)
            self.assertEqual(steps, [], (pm, arch))
            self.assertEqual(info["manual"], self.ex.CLAUDE_PAGE)

    def test_script_follows_the_vendor_instructions(self):
        steps, info = self.ex.claude_steps("apt-get", "amd64")
        sh = steps[0]["sh"]
        self.assertEqual(subprocess.run(["sh", "-n", "-c", sh], capture_output=True).returncode, 0)
        self.assertIn("https://downloads.claude.ai/claude-desktop/key.asc", sh)
        self.assertIn("31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE", sh)
        self.assertIn("--proto '=https'", sh)
        self.assertLess(sh.index("KEY FINGERPRINT MISMATCH"), sh.index("install -D -m644"))         # gate before anything is written
        self.assertIn("deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/claude-desktop-archive-keyring.asc] "
                      "https://downloads.claude.ai/claude-desktop/apt/stable stable main", sh)
        self.assertIn("/etc/apt/sources.list.d/claude-desktop.list", sh)
        self.assertTrue(sh.rstrip().endswith("apt-get install -y claude-desktop"))
        self.assertIn("apt-get purge -y claude-desktop", self.ex.claude_remove_steps("apt-get")[0]["sh"])
        self.assertEqual(self.ex.claude_remove_steps("dnf"), [])
        self.assertTrue(self.ex.claude_installed(which=lambda c: "/usr/bin/claude-desktop"))
        self.assertFalse(self.ex.claude_installed(which=lambda c: None))

    @unittest.skipUnless(shutil.which("gpg") and shutil.which("curl") and shutil.which("awk"), "needs gpg, curl and awk")
    def test_the_fingerprint_gate_really_works(self):
        with tempfile.TemporaryDirectory() as d:
            home = os.path.join(d, "gh")
            os.makedirs(home, mode=0o700)
            env = dict(os.environ, GNUPGHOME=home)
            subprocess.run(["gpg", "--batch", "--passphrase", "", "--quick-generate-key", "Test <t@t>", "rsa2048", "sign", "never"],
                           env=env, capture_output=True, check=True)
            armored = subprocess.run(["gpg", "--armor", "--export"], env=env, capture_output=True, check=True).stdout
            key = os.path.join(d, "key.asc")
            with open(key, "wb") as f:
                f.write(armored)
            fpr = subprocess.run(["gpg", "--with-colons", "--list-keys"], env=env, capture_output=True, text=True).stdout
            fpr = next(ln.split(":")[9] for ln in fpr.splitlines() if ln.startswith("fpr"))
            keyring, listfile = os.path.join(d, "ring.asc"), os.path.join(d, "x.list")

            def run(expected):
                sh = self.ex.claude_steps("apt-get", "amd64", proto="=file", keyring=keyring, listfile=listfile,
                                          fpr=expected, url="file://" + key)[0][0]["sh"]
                # keep only the key / fingerprint / repository part: there is no apt in a unit test
                head = []
                for ln in sh.splitlines():
                    if ln == "apt-get update":
                        break
                    if not ln.startswith("apt-get install"):
                        head.append(ln)
                head = "\n".join(head)
                return subprocess.run(["sh", "-c", head], capture_output=True, text=True)
            ok = run(fpr)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn("Key fingerprint OK", ok.stdout)
            self.assertTrue(os.path.exists(keyring) and os.path.exists(listfile))
            os.remove(keyring)
            os.remove(listfile)
            bad = run("0" * 40)                                                   # a key that is not the published one
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("KEY FINGERPRINT MISMATCH", bad.stderr)
            self.assertFalse(os.path.exists(keyring) or os.path.exists(listfile))   # nothing written

    def test_window_explains_the_key_check_and_runs_nothing_when_declined(self):
        m = Installer.m
        saved = {k: getattr(m, k) for k in ("detect_pm", "elevate", "LANG")}
        saved_mb = m.messagebox
        asked, infos = [], []
        try:
            m.LANG = "en"
            m.detect_pm = lambda: "apt-get"
            m.elevate = lambda c, **k: ["pkexec"] + list(c)
            answers = [False, True]
            m.messagebox = types.SimpleNamespace(askyesno=lambda t_, msg: asked.append(msg) or answers.pop(0),
                                                 showinfo=lambda *a: infos.append(a[1]), showwarning=lambda *a: None)
            with mock.patch("platform.machine", return_value="x86_64"):
                self.assertIsNone(m.App.claude_jobs(object(), "install"))
                jobs = m.App.claude_jobs(object(), "install")
            self.assertIn("31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE", asked[0])
            self.assertIn("kvm", asked[0])                                         # the Cowork note from the vendor page
            self.assertEqual(jobs[0][:3], ["pkexec", "sh", "-c"])
            m.detect_pm = lambda: "dnf"
            with mock.patch("platform.machine", return_value="x86_64"):
                self.assertIsNone(m.App.claude_jobs(object(), "install"))
            self.assertIn("code.claude.com", infos[-1])                           # other systems: the vendor's page
        finally:
            for k, v in saved.items():
                setattr(m, k, v)
            m.messagebox = saved_mb


class UpdateWindow(unittest.TestCase):
    m = Installer.m

    def test_banner_only_when_there_is_news(self):
        b = self.m.banner_for
        self.assertEqual(b({"mode": "git", "behind": 3}, {}, 100), ("behind", 3))
        self.assertIsNone(b({"mode": "git", "behind": 0}, {}, 100))
        self.assertIsNone(b({"mode": "error", "error": "offline"}, {}, 100))
        self.assertIsNone(b(None, {}, 100))
        self.assertEqual(b({"mode": "adopt"}, {}, 100), ("plain", None))                    # a copied folder is told about it
        self.assertIsNone(b({"mode": "adopt"}, {"update_snooze_until": 500}, 100))          # ... until "Later" runs out
        self.assertEqual(b({"mode": "adopt"}, {"update_snooze_until": 50}, 100), ("plain", None))

    def test_only_programs_installed_for_the_user_are_reinstalled(self):
        tools = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        where = {"a": {"user"}, "b": {"system"}, "c": {"user", "system"}}
        self.assertEqual(self.m.reinstall_ids(tools, lambda x: where[x["id"]]), ["a", "c"])
        self.assertEqual(self.m.reinstall_ids(tools, lambda x: set()), [])

    def test_update_flow_updates_reinstalls_then_restarts(self):
        m = self.m
        calls = {"order": [], "said": []}
        saved = {k: getattr(m, k) for k in ("run_command", "installed_where")}
        saved_up = (m.updater.update, m.updater.adopt)
        try:
            m.updater.update = lambda root, **k: calls["order"].append("update") or (True, "Updating abc..def")
            m.updater.adopt = lambda root, **k: calls["order"].append("adopt") or (True, "connected")
            m.installed_where = lambda tool: {"user"} if tool["id"] in ("usb-eject", "printhub") else set()
            m.run_command = lambda cmd, on_line: calls["order"].append(("reinstall", cmd[-2:])) or 0
            app = types.SimpleNamespace(ui=lambda fn, *a: fn(*a), say=lambda text: calls["said"].append(text),
                                        restart=lambda: calls["order"].append("restart"),
                                        update_failed=lambda msg: calls["order"].append(("failed", msg)))
            m.App.do_update(app, {"mode": "git"}, True)
            self.assertEqual(calls["order"][0], "update")
            self.assertEqual(calls["order"][1], ("reinstall", ["usb-eject", "printhub"]))   # only what was installed
            self.assertEqual(calls["order"][-1], "restart")
            calls["order"].clear()
            m.App.do_update(app, {"mode": "adopt"}, False)                                   # plain copy, no reinstall asked
            self.assertEqual(calls["order"], ["adopt", "restart"])
            calls["order"].clear()
            m.updater.update = lambda root, **k: (False, "files were changed here, update refused: install.sh")
            m.App.do_update(app, {"mode": "git"}, True)
            self.assertEqual(calls["order"], [("failed", "files were changed here, update refused: install.sh")])   # no restart
        finally:
            for k, v in saved.items():
                setattr(m, k, v)
            m.updater.update, m.updater.adopt = saved_up


class Brave(unittest.TestCase):
    ex = Installer.m.extras
    fx = os.path.join(ROOT, "tests", "fixtures", "brave-install.sh")             # the vendor's script, BSD-3-Clause, as served

    def fake_opener(self, body, url="https://dl.brave.com/install.sh"):
        import io
        class R(io.BytesIO):
            def geturl(self_inner):
                return url
            def __enter__(self_inner):
                return self_inner
            def __exit__(self_inner, *a):
                return False
        return lambda req, timeout=None: R(body)

    def test_fetch_accepts_the_real_script_and_reports_its_hash(self):
        import hashlib
        with open(self.fx, "rb") as f:
            raw = f.read()
        info = self.ex.brave_fetch_script(opener=self.fake_opener(raw))
        self.assertEqual(info["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(info["bytes"], len(raw))
        self.assertTrue(info["text"].startswith("#!/bin/sh"))
        self.assertIn("brave-browser", info["text"])

    def test_fetch_refuses_anything_else(self):
        bad = {"an HTML error page": b"<!doctype html><html>404 not found brave</html>",
               "an empty answer": b"",
               "a script that is not Brave's": b"#!/bin/sh\necho hello\n",
               "something huge": b"#!/bin/sh\n# brave\n" + b"x" * (self.ex.BRAVE_MAX_BYTES + 10)}
        for what, body in bad.items():
            with self.assertRaises(ValueError, msg=what):
                self.ex.brave_fetch_script(opener=self.fake_opener(body))
        with self.assertRaises(ValueError):                                        # redirected to plain http
            self.ex.brave_fetch_script(opener=self.fake_opener(b"#!/bin/sh\n# brave\n", url="http://evil.example/x.sh"))

    def test_the_vendor_script_really_parses_and_does_what_we_describe(self):
        self.assertEqual(subprocess.run(["sh", "-n", self.fx], capture_output=True).returncode, 0)
        with open(self.fx) as f:
            text = f.read()
        for needle in ("brave-browser-apt-", "apt-get install -y", "dnf", "zypper", "/usr/share/keyrings/", "/etc/apt/sources.list.d/"):
            self.assertIn(needle, text)                                            # repository + key + package, as the window says
        self.assertNotIn("curl | sh", text.replace(" ", ""))

    def test_steps_run_as_administrator_then_delete_the_script(self):
        steps = self.ex.brave_steps("/home/u/.cache/linux-scripts/downloads/brave install.sh")
        self.assertEqual([x["root"] for x in steps], [True, False])
        self.assertIn("sh '/home/u/.cache/linux-scripts/downloads/brave install.sh'", steps[0]["sh"])      # quoted
        self.assertIn("rm -f", steps[1]["sh"])
        for st in steps:
            self.assertEqual(subprocess.run(["sh", "-n", "-c", st["sh"]], capture_output=True).returncode, 0)

    def test_remove_steps(self):
        apt = self.ex.brave_remove_steps("apt-get")[0]["sh"]
        self.assertIn("apt-get purge -y brave-browser", apt)
        self.assertIn("brave-browser-release.sources", apt)                         # the repository the script added
        self.assertIn("brave-browser-archive-keyring.gpg", apt)
        self.assertIn("dnf remove -y brave-browser", self.ex.brave_remove_steps("dnf")[0]["sh"])
        self.assertEqual(self.ex.brave_remove_steps("unknown"), [])
        self.assertTrue(self.ex.brave_installed(which=lambda c: "/usr/bin/brave-browser" if c == "brave-browser" else None))
        self.assertFalse(self.ex.brave_installed(which=lambda c: None))

    def test_window_shows_the_script_and_runs_nothing_when_declined(self):
        m = Installer.m
        with open(self.fx, "rb") as f:
            raw = f.read()
        info = self.ex.brave_fetch_script(opener=self.fake_opener(raw))
        saved = {k: getattr(m, k) for k in ("detect_pm", "elevate")}
        saved_fetch, saved_mb = m.extras.brave_fetch_script, m.messagebox
        shown = []
        try:
            m.detect_pm = lambda: "apt-get"
            m.elevate = lambda c, **k: ["pkexec"] + list(c)
            m.extras.brave_fetch_script = lambda *a, **k: info
            m.messagebox = types.SimpleNamespace(showinfo=lambda *a: None, showwarning=lambda *a: shown.append(a[1]))
            app = types.SimpleNamespace(lbl_status=types.SimpleNamespace(config=lambda **k: None), update_idletasks=lambda: None,
                                        confirm_script=lambda i: shown.append(i["sha256"]) or False)
            self.assertIsNone(m.App.brave_jobs(app, "install"))                    # shown, declined -> nothing runs
            self.assertEqual(shown, [info["sha256"]])
            app.confirm_script = lambda i: True
            with mock.patch("os.path.expanduser", return_value=tempfile.mkdtemp()):
                jobs = m.App.brave_jobs(app, "install")
            self.assertEqual(jobs[0][:3], ["pkexec", "sh", "-c"])                  # administrator, one password prompt
            written = jobs[0][3].split("sh ", 1)[1].strip().strip("'")
            with open(written) as f:
                self.assertEqual(f.read(), info["text"])                           # exactly the text the user saw
            m.extras.brave_fetch_script = lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))
            self.assertIsNone(m.App.brave_jobs(app, "install"))                    # offline: a message, nothing runs
            self.assertIn("offline", shown[-1])
        finally:
            for k, v in saved.items():
                setattr(m, k, v)
            m.extras.brave_fetch_script, m.messagebox = saved_fetch, saved_mb


class PackagePrograms(unittest.TestCase):
    ex = Installer.m.extras

    def test_steps_per_package_manager_and_names(self):
        want = {"apt-get": "apt-get install -y {}", "dnf": "dnf install -y {}", "pacman": "pacman -S --noconfirm {}",
                "zypper": "zypper --non-interactive install {}", "apk": "apk add {}"}
        for app in ("brasero", "xfburn", "k3b"):
            for pm, cmd in want.items():
                steps = self.ex.package_steps(app, pm)
                self.assertEqual([x["root"] for x in steps], [True], (app, pm))
                self.assertIn(cmd.format(app) + "\n", steps[0]["sh"])
                self.assertEqual(subprocess.run(["sh", "-n", "-c", steps[0]["sh"]], capture_output=True).returncode, 0)
                self.assertEqual(self.ex.package_name(app, pm), app)
        self.assertEqual(set(self.ex.PACKAGE_APPS), {"brasero", "xfburn", "k3b"})
        self.assertEqual({x["id"] for x in Installer.m.EXTRAS}, set(self.ex.PACKAGE_APPS) | {"etcher", "brave", "claude", "vscode", "discord"} | set(self.ex.GITHUB_APPS))   # window and logic agree
        self.assertEqual({x["id"] for x in Shortcuts.m.TOOLS} >= set(self.ex.PACKAGE_APPS), True)       # and shortcuts know them
        self.assertIn("apt-get purge -y brasero", self.ex.package_steps("brasero", "apt-get", remove=True)[0]["sh"])
        self.assertIn("pacman -R --noconfirm brasero", self.ex.package_steps("brasero", "pacman", remove=True)[0]["sh"])
        self.assertEqual(self.ex.package_steps("brasero", "unknown-pm"), [])
        self.assertEqual(self.ex.package_steps("brasero", ""), [])

    def test_installed_means_the_command_is_on_the_path(self):
        self.assertTrue(self.ex.package_installed("brasero", which=lambda c: "/usr/bin/" + c))
        self.assertFalse(self.ex.package_installed("brasero", which=lambda c: None))

    def test_window_asks_then_installs_with_administrator_rights(self):
        m = Installer.m
        asked = []
        saved = {k: getattr(m, k) for k in ("detect_pm", "elevate", "LANG")}
        saved_mb = m.messagebox
        try:
            m.LANG = "en"                          # the user's saved language must not change the assertions
            m.detect_pm = lambda: "apt-get"
            m.elevate = lambda c, **k: ["pkexec"] + list(c)
            answers = [True, False]
            m.messagebox = types.SimpleNamespace(askyesno=lambda t_, msg: asked.append(msg) or answers.pop(0),
                                                 showinfo=lambda *a: asked.append(a[1]), showwarning=lambda *a: None)
            jobs = m.App.package_jobs(object(), "install", "brasero")
            self.assertEqual(jobs[0][:3], ["pkexec", "sh", "-c"])
            self.assertIn("apt-get install -y brasero", jobs[0][3])
            self.assertIn("Package: brasero  (apt-get)", asked[0])
            self.assertIsNone(m.App.package_jobs(object(), "install", "brasero"))          # "no" -> nothing runs
            m.detect_pm = lambda: "unknown-pm"
            self.assertIsNone(m.App.package_jobs(object(), "install", "brasero"))          # unknown manager -> a message
            self.assertIn("No known Brasero package", asked[-1])
            m.detect_pm = lambda: "apt-get"
            removal = m.App.package_jobs(object(), "uninstall", "brasero")                 # removal is confirmed by the window
            self.assertIn("apt-get purge -y brasero", removal[0][3])
        finally:
            for k, v in saved.items():
                setattr(m, k, v)
            m.messagebox = saved_mb


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
