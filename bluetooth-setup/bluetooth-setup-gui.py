#!/usr/bin/env python3
"""Bluetooth Setup — English / ქართული.

1. Shows every Bluetooth controller (also several USB dongles at once): version, Classic/BLE/SSP support,
   whether it initialised, and — from the kernel log — why a dongle failed.
2. Scans, pairs (PIN / passkey prompts are handled in the window), trusts, connects, disconnects, forgets.
3. Speakers: "Use as audio output".
Needs only BlueZ (`bluetoothctl`).  Optional: `pactl` (audio output), `pkexec` (software re-plug of a USB dongle).
"""
import os
import re
import subprocess
import sys
import threading

_here = os.path.dirname(os.path.abspath(__file__))
for _p in reversed((os.path.join(_here, "..", "common"), os.path.join(_here, "..", "lib", "linux-scripts"),
                    "/usr/local/lib/linux-scripts", "/usr/lib/linux-scripts")):   # first entry wins
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
from lscommon import ensure_tkinter, load_lang, run, save_lang, warn_missing  # noqa: E402

ensure_tkinter()

import tkinter as tk  # noqa: E402
from tkinter import ttk, messagebox, simpledialog, scrolledtext  # noqa: E402

LANG = load_lang()

LMP = {0: "1.0b", 1: "1.1", 2: "1.2", 3: "2.0 + EDR", 4: "2.1 + EDR", 5: "3.0 + HS", 6: "4.0", 7: "4.1",
       8: "4.2", 9: "5.0", 10: "5.1", 11: "5.2", 12: "5.3", 13: "5.4", 14: "6.0"}

STR = {
"en": {
 "title": "Bluetooth Setup", "lang_btn": "ქართული",
 "f_ctl": "Controllers (Bluetooth adapters)", "f_dev": "Devices", "log": "Log",
 "c_name": "Controller", "c_addr": "Address", "c_ver": "Bluetooth", "c_feat": "Features", "c_usb": "USB", "c_state": "State",
 "d_name": "Name", "d_mac": "Address", "d_type": "Type", "d_pair": "Paired", "d_conn": "Connected", "d_sig": "Signal",
 "refresh": "Refresh", "replug": "Software re-plug…", "scan": "Scan 15 s", "pair": "Pair & connect", "connect": "Connect",
 "disconnect": "Disconnect", "forget": "Forget", "audio": "Use as audio output", "use_ctl": "Active controller:",
 "yes": "yes", "no": "no", "up": "working", "down": "NOT initialised", "off": "powered off",
 "ok_classic_le": "Classic + Low Energy: works with speakers, headsets, keyboards, mice.",
 "classic_only": "Classic only (no Low Energy): fine for speakers/headsets; most newer keyboards and mice (BLE) cannot connect to it.",
 "no_ssp": "No Secure Simple Pairing: some modern devices will refuse to pair.",
 "failed": "Did not initialise — kernel reports: {why}. Try a USB port directly on the computer (no hub), then ‘Software re-plug’. If it keeps failing the dongle is probably faulty.",
 "usb_err": "USB errors in the log ({n}×): bad contact, hub or port. Re-seat the dongle firmly in a direct port.",
 "clone": "Unbranded CSR clone detected (works, but limited).",
 "t_audio": "speaker/headset", "t_keyboard": "keyboard", "t_mouse": "mouse", "t_phone": "phone", "t_other": "device",
 "scanning": "Scanning… put the device in pairing mode (blinking light).", "scan_done": "Scan finished.",
 "pick_dev": "Select a device first.", "pick_ctl": "No working controller.",
 "pairing": "Pairing {n}…", "pair_ok": "Paired, trusted and connected: {n}.", "pair_fail": "Pairing failed: {e}",
 "conn_ok": "Connected.", "conn_fail": "Connection failed: {e}",
 "confirm": "Does this code match the one shown on {n}?\n\n{code}", "enter_pin": "Enter the PIN for {n} (try 0000 or 1234):",
 "show_code": "Type this code on {n}, then press Enter:\n\n{code}", "authorize": "Allow {n} to use a service?",
 "forget_q": "Forget {n}? You will have to pair it again.",
 "audio_ok": "Audio output set to {n}.", "audio_none": "No audio output for this device yet — connect it first (speakers only).",
 "replug_q": "Disable and re-enable the USB dongle {u} (like unplugging it)? Administrator password required.",
 "replug_ok": "Re-plug command sent. Press Refresh in a few seconds.", "replug_fail": "Re-plug failed: {e}",
 "no_bt": "No Bluetooth controller found. Plug in a dongle (or enable Bluetooth in firmware).",
 "guide": ("• Put the device in pairing mode first (the light blinks), then press ‘Scan’.\n"
           "• Keyboards may show a code to type on them; speakers just connect.\n"
           "• Older dongles (Bluetooth 2.0) cannot talk to Low-Energy-only devices; use a 4.0+ dongle for those.\n"
           "• Several dongles work at once — choose the active one above."),
},
"ka": {
 "title": "Bluetooth-ის მართვა", "lang_btn": "English",
 "f_ctl": "კონტროლერები (Bluetooth ადაპტერები)", "f_dev": "მოწყობილობები", "log": "ლოგი",
 "c_name": "კონტროლერი", "c_addr": "მისამართი", "c_ver": "Bluetooth", "c_feat": "შესაძლებლობები", "c_usb": "USB", "c_state": "მდგომარეობა",
 "d_name": "სახელი", "d_mac": "მისამართი", "d_type": "ტიპი", "d_pair": "დაწყვილებული", "d_conn": "დაკავშირებული", "d_sig": "სიგნალი",
 "refresh": "განახლება", "replug": "პროგრამული ამოღება/ჩადება…", "scan": "ძებნა 15 წმ", "pair": "დაწყვილება და დაკავშირება", "connect": "დაკავშირება",
 "disconnect": "გათიშვა", "forget": "დავიწყება", "audio": "ხმის გამოსავლად", "use_ctl": "აქტიური კონტროლერი:",
 "yes": "კი", "no": "არა", "up": "მუშაობს", "down": "ვერ ჩაირთო", "off": "გამორთულია",
 "ok_classic_le": "Classic + Low Energy: მუშაობს დინამიკებთან, ყურსასმენებთან, კლავიატურებთან, მაუსებთან.",
 "classic_only": "მხოლოდ Classic (Low Energy-ს გარეშე): დინამიკებისა და ყურსასმენებისთვის კარგია; ახალი კლავიატურები და მაუსები (BLE) ვერ დაუკავშირდება.",
 "no_ssp": "Secure Simple Pairing არ აქვს: ზოგი თანამედროვე მოწყობილობა დაწყვილებაზე უარს იტყვის.",
 "failed": "ვერ ინიციალიზდა — ბირთვი წერს: {why}. სცადეთ USB პორტი უშუალოდ კომპიუტერზე (ჰაბის გარეშე), მერე „პროგრამული ამოღება/ჩადება“. თუ ისევ ვარდება, დონგლი სავარაუდოდ დეფექტურია.",
 "usb_err": "USB შეცდომები ჟურნალში ({n}×): ცუდი კონტაქტი, ჰაბი ან პორტი. ჩასვით დონგლი მაგრად, უშუალო პორტში.",
 "clone": "აღმოჩენილია უბრენდო CSR კლონი (მუშაობს, მაგრამ შეზღუდულია).",
 "t_audio": "დინამიკი/ყურსასმენი", "t_keyboard": "კლავიატურა", "t_mouse": "მაუსი", "t_phone": "ტელეფონი", "t_other": "მოწყობილობა",
 "scanning": "ვეძებ… მოწყობილობა pairing რეჟიმში გადაიყვანეთ (ციმციმი).", "scan_done": "ძებნა დასრულდა.",
 "pick_dev": "ჯერ აირჩიეთ მოწყობილობა.", "pick_ctl": "მუშა კონტროლერი არ არის.",
 "pairing": "ვაწყვილებ {n}…", "pair_ok": "დაწყვილდა, სანდოა და დაკავშირდა: {n}.", "pair_fail": "დაწყვილება ვერ მოხერხდა: {e}",
 "conn_ok": "დაკავშირებულია.", "conn_fail": "დაკავშირება ვერ მოხერხდა: {e}",
 "confirm": "ემთხვევა ეს კოდი {n}-ზე ნაჩვენებს?\n\n{code}", "enter_pin": "შეიყვანეთ {n}-ის PIN (სცადეთ 0000 ან 1234):",
 "show_code": "აკრიფეთ ეს კოდი {n}-ზე და დააჭირეთ Enter-ს:\n\n{code}", "authorize": "ნება დართოთ {n}-ს სერვისის გამოყენებაზე?",
 "forget_q": "დავივიწყო {n}? თავიდან მოგიწევთ დაწყვილება.",
 "audio_ok": "ხმის გამოსავალია {n}.", "audio_none": "ამ მოწყობილობას ხმის გამოსავალი ჯერ არ აქვს — ჯერ დააკავშირეთ (მხოლოდ დინამიკებისთვის).",
 "replug_q": "გამოვრთო და ისევ ჩავრთო USB დონგლი {u} (როგორც ამოღება/ჩადება)? საჭიროა ადმინისტრატორის პაროლი.",
 "replug_ok": "ბრძანება გაიგზავნა. რამდენიმე წამში დააჭირეთ „განახლება“.", "replug_fail": "ვერ მოხერხდა: {e}",
 "no_bt": "Bluetooth კონტროლერი ვერ მოიძებნა. ჩართეთ დონგლი (ან ჩართეთ Bluetooth ფირმვერში).",
 "guide": ("• ჯერ მოწყობილობა pairing რეჟიმში გადაიყვანეთ (ციმციმებს), მერე დააჭირეთ „ძებნას“.\n"
           "• კლავიატურები შეიძლება კოდს გაჩვენებდეს — თვითონ კლავიატურაზე აკრიფეთ; დინამიკი უბრალოდ უკავშირდება.\n"
           "• ძველი დონგლები (Bluetooth 2.0) Low-Energy მოწყობილობებს ვერ ესაუბრება; მათთვის 4.0+ დონგლი გჭირდებათ.\n"
           "• რამდენიმე დონგლი ერთად მუშაობს — ზემოთ აირჩიეთ აქტიური."),
},
}


def t(k, **kw):
    s = STR[LANG][k]
    return s.format(**kw) if kw else s


# ---------------------------------------------------------------- pure parsing (unit-tested)
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|[\x01\x02\r]")
PROMPT = re.compile(r"^\[[^\]]*\]#\s*")


def clean(line):
    return PROMPT.sub("", ANSI.sub("", line)).rstrip()


def parse_mgmt_info(text):
    """`bluetoothctl mgmt.info` -> [{index, addr, version, manufacturer, supported:set, current:set}]"""
    res, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^(hci\d+):", line.strip())
        if m:
            cur = {"index": m.group(1), "addr": "", "version": None, "manufacturer": None,
                   "supported": set(), "current": set()}
            res.append(cur)
            continue
        if cur is None:
            continue
        line = line.strip()
        m = re.match(r"addr (\S+) version (\d+) manufacturer (\d+)", line)
        if m:
            cur["addr"], cur["version"], cur["manufacturer"] = m.group(1).upper(), int(m.group(2)), int(m.group(3))
        elif line.startswith("supported settings:"):
            cur["supported"] = set(line.split(":", 1)[1].split())
        elif line.startswith("current settings:"):
            cur["current"] = set(line.split(":", 1)[1].split())
    return res


def parse_devices(text):
    """`bluetoothctl devices` -> {mac: name}"""
    res = {}
    for line in text.splitlines():
        m = re.match(r"^\s*Device\s+([0-9A-Fa-f:]{17})\s*(.*)$", clean(line))
        if m:
            res[m.group(1).upper()] = m.group(2) or m.group(1)
    return res


def parse_info(text):
    """`bluetoothctl info MAC` -> dict of fields (+ 'uuids' list)"""
    d = {"uuids": []}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("UUID:"):
            d["uuids"].append(line.split(":", 1)[1].strip())
        elif ":" in line and not line.startswith("Device "):
            k, _, v = line.partition(":")
            d[k.strip()] = v.strip()
    return d


def device_kind(info):
    icon = info.get("Icon", "")
    uu = " ".join(info.get("uuids", []))
    if "keyboard" in icon:
        return "keyboard"
    if "mouse" in icon or "pointing" in icon:
        return "mouse"
    if "audio" in icon or "Audio Sink" in uu or "Headset" in uu or "Handsfree" in uu:
        return "audio"
    if "phone" in icon:
        return "phone"
    if "Human Interface" in uu:
        return "keyboard"
    return "other"


def parse_bt_line(line):
    """One line of `bluetoothctl` output -> event tuple or None (agent prompts, discoveries, results)."""
    s = clean(line)
    m = re.match(r"^\[NEW\] Device ([0-9A-F:]{17}) ?(.*)$", s, re.I)
    if m:
        return ("new", m.group(1).upper(), m.group(2))
    m = re.match(r"^\[CHG\] Device ([0-9A-F:]{17}) ([A-Za-z ]+): ?(.*)$", s, re.I)
    if m:
        key, val = m.group(2), m.group(3)
        if key == "RSSI":
            mm = re.search(r"\((-?\d+)\)", val) or re.match(r"^(-?\d+)$", val)
            return ("chg", m.group(1).upper(), "RSSI", mm.group(1) if mm else val)
        return ("chg", m.group(1).upper(), key, val)
    m = re.match(r"^\[DEL\] Device ([0-9A-F:]{17})", s, re.I)
    if m:
        return ("del", m.group(1).upper())
    m = re.search(r"Confirm passkey (\d+)", s)
    if m:
        return ("confirm", m.group(1))
    m = re.search(r"\[agent\] Passkey: (\d+)", s)
    if m:
        return ("show_code", m.group(1))
    m = re.search(r"\[agent\] PIN code: (\S+)", s)
    if m:
        return ("show_code", m.group(1))
    if re.search(r"Enter PIN code|Enter passkey", s):
        return ("enter_pin",)
    if re.search(r"Authorize service|Request authorization", s):
        return ("authorize",)
    if s.startswith("Pairing successful"):
        return ("result", "pair", True, "")
    m = re.match(r"^Failed to pair: ?(.*)$", s)
    if m:
        return ("result", "pair", False, m.group(1))
    if s.startswith("Connection successful"):
        return ("result", "connect", True, "")
    m = re.match(r"^Failed to connect: ?(.*)$", s)
    if m:
        return ("result", "connect", False, m.group(1))
    return None


def kernel_hints(text):
    """dmesg/journal text -> {'hci1': {'failed': 'command 0x1004 tx timeout', 'clone': bool}, '_usb_errors': n}"""
    res = {"_usb_errors": 0}
    for line in text.splitlines():
        m = re.search(r"Bluetooth: (hci\d+): (.*)$", line)
        if m:
            h = res.setdefault(m.group(1), {"failed": "", "clone": False})
            msg = m.group(2)
            if "tx timeout" in msg or re.search(r"Opcode 0x[0-9a-f]+ failed: -\d+", msg):
                h["failed"] = msg
            if "Unbranded CSR clone" in msg:
                h["clone"] = True
        elif re.search(r"usb \S+: (device not accepting address|Device not responding to setup address|"
                       r"device descriptor read/\w+, error -\d+)", line):
            res["_usb_errors"] += 1
    return res


def features_of(c):
    sup = c["supported"]
    return ["BR/EDR"] * ("br/edr" in sup) + ["LE"] * ("le" in sup) + ["SSP"] * ("ssp" in sup)


def usb_info(hci):
    """-> (usb 'vid:pid product', sysfs usb device dir) of /sys/class/bluetooth/<hci>"""
    try:
        dev = os.path.realpath(f"/sys/class/bluetooth/{hci}/device")
        usb = os.path.dirname(dev)
        rd = lambda n: open(os.path.join(usb, n)).read().strip()   # noqa: E731
        try:
            prod = rd("product")
        except OSError:
            prod = ""
        return f"{rd('idVendor')}:{rd('idProduct')} {prod}".strip(), usb
    except OSError:
        return "", ""


# ---------------------------------------------------------------- interactive bluetoothctl with agent
class BtSession:
    """`bluetoothctl --agent KeyboardDisplay` as a child process: send() commands, lines arrive via callback."""

    def __init__(self, on_line):
        self.p = subprocess.Popen(["bluetoothctl", "--agent", "KeyboardDisplay"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.on_line = on_line
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            self.on_line(line)

    def send(self, cmd):
        try:
            self.p.stdin.write(cmd + "\n")
            self.p.stdin.flush()
        except (OSError, ValueError):
            pass

    def close(self):
        self.send("quit")
        try:
            self.p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.p.kill()
        for pipe in (self.p.stdin, self.p.stdout):      # no file handles left behind
            try:
                pipe.close()
            except (OSError, ValueError):
                pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.geometry("860x720")
        self.minsize(760, 620)
        self.ctls, self.devs, self.cur_mac, self.pending = [], {}, "", None
        self.session = None

        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(10, 4))
        self.lbl_title = ttk.Label(top, font=("", 14, "bold"))
        self.lbl_title.pack(side="left")
        self.btn_lang = ttk.Button(top, width=10, command=self.toggle_lang)
        self.btn_lang.pack(side="right")

        self.f_ctl = ttk.LabelFrame(self)
        self.f_ctl.pack(fill="x", padx=12, pady=6)
        self.tc = ttk.Treeview(self.f_ctl, columns=("addr", "ver", "feat", "usb", "state"), height=3, selectmode="browse")
        for col, w in (("#0", 80), ("addr", 135), ("ver", 90), ("feat", 120), ("usb", 230), ("state", 120)):
            self.tc.column(col, width=w, anchor="w")
        self.tc.pack(fill="x", padx=8, pady=(8, 2))
        self.tc.bind("<<TreeviewSelect>>", lambda e: self.show_advice())
        self.lbl_adv = ttk.Label(self.f_ctl, wraplength=800, justify="left")
        self.lbl_adv.pack(anchor="w", padx=8, pady=2)
        bar = ttk.Frame(self.f_ctl)
        bar.pack(fill="x", padx=8, pady=(2, 8))
        self.btn_ref = ttk.Button(bar, command=self.refresh_all)
        self.btn_ref.pack(side="left")
        self.btn_replug = ttk.Button(bar, command=self.on_replug)
        self.btn_replug.pack(side="left", padx=8)
        self.lbl_use = ttk.Label(bar)
        self.lbl_use.pack(side="left", padx=(16, 4))
        self.cmb = ttk.Combobox(bar, state="readonly", width=30)
        self.cmb.pack(side="left")
        self.cmb.bind("<<ComboboxSelected>>", self.on_pick_ctl)

        self.f_dev = ttk.LabelFrame(self)
        self.f_dev.pack(fill="both", expand=True, padx=12, pady=6)
        self.td = ttk.Treeview(self.f_dev, columns=("mac", "type", "pair", "conn", "sig"), height=7, selectmode="browse")
        for col, w in (("#0", 200), ("mac", 140), ("type", 130), ("pair", 100), ("conn", 110), ("sig", 80)):
            self.td.column(col, width=w, anchor="w")
        self.td.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        bar = ttk.Frame(self.f_dev)
        bar.pack(fill="x", padx=8, pady=(0, 8))
        self.btns = {}
        for key, cmd in (("scan", self.on_scan), ("pair", self.on_pair), ("connect", self.on_connect),
                         ("disconnect", self.on_disconnect), ("forget", self.on_forget), ("audio", self.on_audio)):
            self.btns[key] = ttk.Button(bar, command=cmd)
            self.btns[key].pack(side="left", padx=(0, 6))

        self.lbl_guide = ttk.Label(self, wraplength=820, justify="left", foreground="#555555")
        self.lbl_guide.pack(anchor="w", padx=14)
        self.lbl_log = ttk.Label(self)
        self.lbl_log.pack(anchor="w", padx=14, pady=(6, 0))
        self.log = scrolledtext.ScrolledText(self, height=6, state="disabled", wrap="word")
        self.log.pack(fill="both", padx=12, pady=(0, 10))

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.apply_lang()
        self.refresh_all()
        self.after(300, lambda: warn_missing(["bluetoothctl"], LANG, t("title")))

    # ---- i18n
    def apply_lang(self):
        self.title(t("title"))
        self.lbl_title.config(text=t("title"))
        self.btn_lang.config(text=t("lang_btn"))
        self.f_ctl.config(text=t("f_ctl"))
        self.f_dev.config(text=t("f_dev"))
        self.lbl_log.config(text=t("log"))
        self.lbl_guide.config(text=t("guide"))
        self.tc.heading("#0", text=t("c_name"))
        for col, k in (("addr", "c_addr"), ("ver", "c_ver"), ("feat", "c_feat"), ("usb", "c_usb"), ("state", "c_state")):
            self.tc.heading(col, text=t(k))
        self.td.heading("#0", text=t("d_name"))
        for col, k in (("mac", "d_mac"), ("type", "d_type"), ("pair", "d_pair"), ("conn", "d_conn"), ("sig", "d_sig")):
            self.td.heading(col, text=t(k))
        self.btn_ref.config(text=t("refresh"))
        self.btn_replug.config(text=t("replug"))
        self.lbl_use.config(text=t("use_ctl"))
        for k, b in self.btns.items():
            b.config(text=t(k))
        self.render_ctls()
        self.render_devs()

    def toggle_lang(self):
        global LANG
        LANG = "ka" if LANG == "en" else "en"
        save_lang(LANG)
        self.apply_lang()

    def say(self, text):
        self.log.config(state="normal")
        self.log.insert("end", str(text).rstrip() + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # ---- controllers
    def read_controllers(self):
        rc, out = run(["bluetoothctl", "mgmt.info"], timeout=8)
        ok = {c["index"]: c for c in parse_mgmt_info(out)} if rc == 0 else {}
        rc, kt = run(["dmesg"], timeout=8)
        if rc != 0:
            rc, kt = run(["journalctl", "-k", "-b", "--no-pager", "-n", "400"], timeout=8)
        hints = kernel_hints(kt if rc == 0 else "")
        ctls = []
        try:
            names = sorted(os.listdir("/sys/class/bluetooth"))
        except OSError:
            names = []
        for h in [n for n in names if re.match(r"hci\d+$", n)]:
            c = dict(ok.get(h) or {"index": h, "addr": "", "version": None, "supported": set(), "current": set()})
            c["usb"], c["usbdir"] = usb_info(h)
            c["working"] = h in ok
            c["powered"] = "powered" in c["current"]
            c["hint"] = hints.get(h, {"failed": "", "clone": False})
            c["usb_errors"] = hints["_usb_errors"]
            ctls.append(c)
        return ctls

    def refresh_all(self):
        self.ctls = self.read_controllers()
        self.render_ctls()
        work = [c for c in self.ctls if c["working"]]
        self.cmb["values"] = [f"{c['index']}  {c['addr']}" for c in work]
        if work:
            idx = next((i for i, c in enumerate(work) if c["addr"] == self.cur_mac), 0)
            self.cmb.current(idx)
            self.cur_mac = work[idx]["addr"]
        else:
            self.cur_mac = ""
            self.cmb.set("")
        self.load_devices()

    def render_ctls(self):
        self.tc.delete(*self.tc.get_children())
        for c in self.ctls:
            ver = f"{LMP.get(c['version'], '?')}" if c["version"] is not None else "?"
            if not c["working"]:
                state = t("down")
            else:
                state = t("up") if c["powered"] else t("off")
            self.tc.insert("", "end", iid=c["index"], text=c["index"],
                           values=(c["addr"] or "-", ver, " ".join(features_of(c)) or "-", c["usb"] or "-", state))
        if self.ctls:
            self.tc.selection_set(self.ctls[0]["index"])
        self.show_advice()
        if not self.ctls:
            self.lbl_adv.config(text=t("no_bt"))

    def show_advice(self):
        sel = self.tc.selection()
        c = next((x for x in self.ctls if sel and x["index"] == sel[0]), None)
        if not c:
            return
        lines = []
        if not c["working"]:
            lines.append(t("failed", why=c["hint"]["failed"] or "?"))
            if c["usb_errors"]:
                lines.append(t("usb_err", n=c["usb_errors"]))
        else:
            sup = c["supported"]
            lines.append(t("ok_classic_le") if "le" in sup else t("classic_only"))
            if "ssp" not in sup:
                lines.append(t("no_ssp"))
        if c["hint"]["clone"]:
            lines.append(t("clone"))
        self.lbl_adv.config(text="\n".join(lines))

    def on_pick_ctl(self, _e=None):
        work = [c for c in self.ctls if c["working"]]
        i = self.cmb.current()
        if 0 <= i < len(work):
            self.cur_mac = work[i]["addr"]
            self.load_devices()

    def on_replug(self):
        sel = self.tc.selection()
        c = next((x for x in self.ctls if sel and x["index"] == sel[0]), None)
        if not c or not c["usbdir"]:
            return
        if not messagebox.askyesno(t("title"), t("replug_q", u=c["usb"])):
            return
        auth = os.path.join(c["usbdir"], "authorized")
        rc, out = run(["pkexec", "sh", "-c", f"echo 0 > '{auth}' && sleep 1 && echo 1 > '{auth}'"], timeout=60)
        self.say(t("replug_ok") if rc == 0 else t("replug_fail", e=out))
        if rc == 0:
            self.after(4000, self.refresh_all)

    # ---- devices
    def ensure_session(self):
        if not self.session:
            self.session = BtSession(lambda ln: self.after(0, self.on_line, ln))
        if self.cur_mac:
            self.session.send(f"select {self.cur_mac}")
        return self.session

    def load_devices(self):
        self.devs = {}
        if self.cur_mac:
            rc, out = run(["bluetoothctl", "devices"], timeout=8)
            for mac, name in parse_devices(out).items():
                info = parse_info(run(["bluetoothctl", "info", mac], timeout=8)[1])
                self.devs[mac] = {"name": info.get("Alias") or name, "kind": device_kind(info),
                                  "paired": info.get("Paired") == "yes", "connected": info.get("Connected") == "yes",
                                  "rssi": ""}
        self.render_devs()

    def render_devs(self):
        sel = self.td.selection()
        self.td.delete(*self.td.get_children())
        for mac, d in sorted(self.devs.items(), key=lambda kv: kv[1]["name"].lower()):
            self.td.insert("", "end", iid=mac, text=d["name"],
                           values=(mac, t("t_" + d["kind"]) if d["kind"] != "audio" else t("t_audio"),
                                   t("yes") if d["paired"] else t("no"), t("yes") if d["connected"] else t("no"),
                                   f"{d['rssi']} dBm" if d["rssi"] else "-"))
        if sel and self.td.exists(sel[0]):
            self.td.selection_set(sel[0])

    def chosen(self):
        sel = self.td.selection()
        if not sel:
            messagebox.showinfo(t("title"), t("pick_dev"))
            return None
        return sel[0]

    def need_ctl(self):
        if not self.cur_mac:
            messagebox.showinfo(t("title"), t("pick_ctl"))
            return False
        return True

    def on_scan(self):
        if not self.need_ctl():
            return
        s = self.ensure_session()
        self.say(t("scanning"))
        s.send("scan on")
        self.after(15000, self.stop_scan)

    def stop_scan(self):
        if self.session:
            self.session.send("scan off")
        self.say(t("scan_done"))

    def on_pair(self):
        mac = self.chosen()
        if not mac or not self.need_ctl():
            return
        self.pending = mac
        self.say(t("pairing", n=self.devs[mac]["name"]))
        s = self.ensure_session()
        s.send("scan off")
        for cmd in ("pair", "trust", "connect"):
            s.send(f"{cmd} {mac}")

    def on_connect(self):
        mac = self.chosen()
        if mac and self.need_ctl():
            self.pending = mac
            self.ensure_session().send(f"connect {mac}")

    def on_disconnect(self):
        mac = self.chosen()
        if mac and self.need_ctl():
            self.ensure_session().send(f"disconnect {mac}")
            self.after(1500, self.load_devices)

    def on_forget(self):
        mac = self.chosen()
        if mac and self.need_ctl() and messagebox.askyesno(t("title"), t("forget_q", n=self.devs[mac]["name"])):
            self.ensure_session().send(f"remove {mac}")
            self.devs.pop(mac, None)
            self.render_devs()

    def on_audio(self):
        mac = self.chosen()
        if not mac:
            return
        key = mac.replace(":", "_").lower()
        rc, out = run(["pactl", "list", "short", "sinks"], timeout=8)
        sink = next((ln.split()[1] for ln in out.splitlines() if len(ln.split()) > 1 and key in ln.lower()), "")
        if rc != 0 or not sink:
            return messagebox.showinfo(t("title"), t("audio_none"))
        run(["pactl", "set-default-sink", sink])
        self.say(t("audio_ok", n=self.devs[mac]["name"]))

    # ---- events from bluetoothctl
    def name_of(self, mac):
        return self.devs.get(mac, {}).get("name") or mac or "?"

    def on_line(self, line):
        ev = parse_bt_line(line)
        if not ev:
            return
        kind = ev[0]
        if kind == "new":
            self.devs.setdefault(ev[1], {"name": ev[2] or ev[1], "kind": "other", "paired": False,
                                         "connected": False, "rssi": ""})
            self.devs[ev[1]]["name"] = ev[2] or self.devs[ev[1]]["name"]
            self.render_devs()
        elif kind == "chg" and ev[1] in self.devs:
            d, key, val = self.devs[ev[1]], ev[2], ev[3]
            if key == "RSSI":
                d["rssi"] = val
            elif key in ("Name", "Alias"):
                d["name"] = val
            elif key == "Paired":
                d["paired"] = val == "yes"
            elif key == "Connected":
                d["connected"] = val == "yes"
            self.render_devs()
        elif kind == "del":
            self.devs.pop(ev[1], None)
            self.render_devs()
        elif kind == "confirm":
            n = self.name_of(self.pending)
            self.session.send("yes" if messagebox.askyesno(t("title"), t("confirm", n=n, code=ev[1])) else "no")
        elif kind == "show_code":
            messagebox.showinfo(t("title"), t("show_code", n=self.name_of(self.pending), code=ev[1]))
        elif kind == "enter_pin":
            pin = simpledialog.askstring(t("title"), t("enter_pin", n=self.name_of(self.pending)), initialvalue="0000", parent=self)
            self.session.send(pin or "")
        elif kind == "authorize":
            self.session.send("yes" if messagebox.askyesno(t("title"), t("authorize", n=self.name_of(self.pending))) else "no")
        elif kind == "result":
            _, what, ok, err = ev
            n = self.name_of(self.pending)
            if what == "pair":
                self.say(t("pair_ok", n=n) if ok else t("pair_fail", e=err))
            else:
                self.say(t("conn_ok") if ok else t("conn_fail", e=err))
            if not ok:
                messagebox.showerror(t("title"), t("pair_fail", e=err) if what == "pair" else t("conn_fail", e=err))
            self.after(1200, self.load_devices)

    def on_close(self):
        if self.session:
            self.session.send("scan off")
            self.session.close()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
