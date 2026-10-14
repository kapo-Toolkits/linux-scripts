#!/usr/bin/env python3
"""Wi-Fi Hotspot GUI (WPA2, NetworkManager) — English / ქართული.

Same logic as hotspot.sh: 2.4 GHz, ipv4 shared, psk-flags 0, pmf 1.
Requires: python3-tk, NetworkManager (nmcli), iw.  Run `hotspot.sh check` first on a fresh install.
"""
import os
import subprocess
import sys
import threading

_here = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_here, "..", "common"), os.path.join(_here, "..", "lib", "linux-scripts"),
           "/usr/local/lib/linux-scripts", "/usr/lib/linux-scripts"):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
from lscommon import ensure_tkinter, load_lang, run, save_lang  # noqa: E402
import lsqr  # noqa: E402

ensure_tkinter()

import tkinter as tk  # noqa: E402
from tkinter import ttk, messagebox  # noqa: E402

CON = "Hotspot"
LANG = load_lang()

STR = {
    "en": {
        "title": "Wi-Fi Hotspot", "lang_btn": "ქართული",
        "iface": "Wi-Fi interface", "state": "Status", "on": "ON (AP)", "off": "OFF",
        "no_iface": "not found", "ssid": "Network name (SSID)", "psk": "Password (Latin, 8–63)",
        "show": "Show", "channel": "Channel (2.4 GHz)", "autostart": "Start at boot",
        "save": "Save profile", "start": "▶  Start", "stop": "■  Stop", "log": "Log",
        "err": "Error", "info": "Hotspot",
        "bad_ssid": "Enter a network name.",
        "bad_psk": "Password must be 8–63 Latin/ASCII characters.",
        "bad_ch": "Channel must be 1–11.",
        "no_profile": "Save the profile first.",
        "saved": "Profile saved. Press Start.",
        "saving": "Saving profile…", "starting": "Starting…", "stopping": "Stopping…",
        "fail": "Failed. Run  hotspot.sh logs  for the real reason.",
        "no_wifi": "No Wi-Fi interface found.",
        "clients": "Connected devices", "c_name": "Device", "c_ip": "IP", "c_mac": "MAC", "c_sig": "Signal",
        "c_time": "Connected", "c_data": "↓ / ↑", "c_none": "No devices connected", "c_off": "Start the hotspot to see connected devices",
        "qr": "QR code", "qr_title": "Join the hotspot",
        "qr_hint": "Scan with the phone camera to join “{s}”.\nAnyone who sees this code can join and gets the password.",
        "qr_long": "SSID + password are too long for a QR code.",
    },
    "ka": {
        "title": "Wi-Fi Hotspot", "lang_btn": "English",
        "iface": "Wi-Fi ინტერფეისი", "state": "სტატუსი", "on": "ჩართულია (AP)", "off": "გამორთულია",
        "no_iface": "ვერ მოიძებნა", "ssid": "ქსელის სახელი (SSID)", "psk": "პაროლი (ლათინური, 8–63)",
        "show": "ჩვენება", "channel": "არხი (2.4 GHz)", "autostart": "ჩართვისას ავტომატურად",
        "save": "პროფილის შენახვა", "start": "▶  ჩართვა", "stop": "■  გამორთვა", "log": "ლოგი",
        "err": "შეცდომა", "info": "Hotspot",
        "bad_ssid": "ჩაწერეთ ქსელის სახელი.",
        "bad_psk": "პაროლი უნდა იყოს 8–63 ლათინური/ASCII სიმბოლო.",
        "bad_ch": "არხი უნდა იყოს 1–11.",
        "no_profile": "ჯერ შეინახეთ პროფილი.",
        "saved": "პროფილი შენახულია. დააჭირეთ ჩართვას.",
        "saving": "პროფილი ინახება…", "starting": "ირთვება…", "stopping": "ითიშება…",
        "fail": "ვერ მოხერხდა. რეალური მიზეზისთვის: hotspot.sh logs",
        "no_wifi": "Wi-Fi ინტერფეისი ვერ მოიძებნა.",
        "clients": "დაკავშირებული მოწყობილობები", "c_name": "მოწყობილობა", "c_ip": "IP", "c_mac": "MAC", "c_sig": "სიგნალი",
        "c_time": "დაკავშირებულია", "c_data": "↓ / ↑", "c_none": "მოწყობილობა არ არის დაკავშირებული", "c_off": "Hotspot-ის ჩასართავად დააჭირეთ „ჩართვა“ — მერე მოწყობილობები გამოჩნდება",
        "qr": "QR კოდი", "qr_title": "Hotspot-თან მიერთება",
        "qr_hint": "დაასკანირეთ ტელეფონის კამერით, რომ დაუკავშირდეთ „{s}“-ს.\nვინც ამ კოდს ნახავს, დაუკავშირდება და პაროლსაც მიიღებს.",
        "qr_long": "SSID და პაროლი QR კოდისთვის ზედმეტად გრძელია.",
    },
}


def t(k, **kw):
    s = STR[LANG][k]
    return s.format(**kw) if kw else s




def wifi_iface():
    rc, out = run(["nmcli", "-t", "-f", "DEVICE,TYPE", "device"])
    for line in out.splitlines():
        dev, _, typ = line.partition(":")
        if typ == "wifi":
            return dev
    return ""


def profile_exists():
    return CON in run(["nmcli", "-t", "-f", "NAME", "con", "show"])[1].splitlines()


def is_active():
    return CON in run(["nmcli", "-t", "-f", "NAME", "con", "show", "--active"])[1].splitlines()


def get_prop(prop, secrets=False):
    cmd = ["nmcli", "-e", "no"] + (["-s"] if secrets else []) + ["-g", prop, "con", "show", CON]
    rc, out = run(cmd)
    return out if rc == 0 else ""


def valid_psk(s):
    return 8 <= len(s) <= 63 and s.isascii() and s.isprintable()


def parse_station_dump(text):
    """`iw dev X station dump` -> [{mac, signal, connected, rx, tx}] (connected in seconds, rx/tx in bytes)."""
    out, cur = [], None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("Station "):
            cur = {"mac": line.split()[1].lower(), "signal": None, "connected": None, "rx": 0, "tx": 0}
            out.append(cur)
        elif cur is not None and ":" in line:
            k, _, v = line.partition(":")
            v = v.split()
            if not v:
                continue
            if k == "signal" and v[0].lstrip("-").isdigit():
                cur["signal"] = int(v[0])
            elif k == "connected time" and v[0].isdigit():
                cur["connected"] = int(v[0])
            elif k == "rx bytes" and v[0].isdigit():
                cur["rx"] = int(v[0])
            elif k == "tx bytes" and v[0].isdigit():
                cur["tx"] = int(v[0])
    return out


def parse_neigh(text):
    """`ip neigh show dev X` -> {mac: ip} (IPv4 preferred)."""
    res = {}
    for line in text.splitlines():
        f = line.split()
        if "lladdr" in f and len(f) > 2:
            mac, ip = f[f.index("lladdr") + 1].lower(), f[0]
            if mac not in res or ":" in res[mac]:      # keep IPv4 over IPv6
                res[mac] = ip
    return res


def parse_leases(text):
    """dnsmasq lease file lines `expiry mac ip hostname clientid` -> {mac: (ip, hostname)}."""
    res = {}
    for line in text.splitlines():
        f = line.split()
        if len(f) >= 4:
            res[f[1].lower()] = (f[2], "" if f[3] == "*" else f[3])
    return res


def human_bytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def human_secs(s):
    if s is None:
        return "-"
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    return f"{h}h {m}m" if h else (f"{m}m {sec}s" if m else f"{sec}s")


def list_clients(iface):
    """Devices associated to the hotspot, merged with IP (ARP table) and name (dnsmasq leases if readable)."""
    if not iface:
        return []
    rc, dump = run(["iw", "dev", iface, "station", "dump"], timeout=5)
    if rc != 0:
        return []
    neigh = parse_neigh(run(["ip", "neigh", "show", "dev", iface], timeout=5)[1])
    leases = {}
    for path in (os.environ.get("HOTSPOT_LEASES") or f"/var/lib/NetworkManager/dnsmasq-{iface}.leases",
                 "/var/lib/misc/dnsmasq.leases"):
        try:
            with open(path) as f:
                leases.update(parse_leases(f.read()))
        except OSError:
            pass
    res = []
    for st in parse_station_dump(dump):
        ip, host = leases.get(st["mac"], (neigh.get(st["mac"], ""), ""))
        st.update({"ip": ip or neigh.get(st["mac"], ""), "name": host})
        res.append(st)
    return res


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.geometry("560x700")
        self.minsize(520, 620)
        self.iface = wifi_iface()
        self.busy = False

        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(12, 6))
        self.lbl_title = ttk.Label(top, font=("", 14, "bold"))
        self.lbl_title.pack(side="left")
        self.btn_lang = ttk.Button(top, width=10, command=self.toggle_lang)
        self.btn_lang.pack(side="right")

        info = ttk.Frame(self)
        info.pack(fill="x", padx=12)
        self.lbl_iface = ttk.Label(info)
        self.lbl_iface.grid(row=0, column=0, sticky="w")
        self.val_iface = ttk.Label(info)
        self.val_iface.grid(row=0, column=1, sticky="w", padx=8)
        self.lbl_state = ttk.Label(info)
        self.lbl_state.grid(row=1, column=0, sticky="w")
        self.val_state = ttk.Label(info, font=("", 10, "bold"))
        self.val_state.grid(row=1, column=1, sticky="w", padx=8)

        form = ttk.Frame(self)
        form.pack(fill="x", padx=12, pady=10)
        form.columnconfigure(1, weight=1)
        self.lbl_ssid = ttk.Label(form)
        self.lbl_ssid.grid(row=0, column=0, sticky="w", pady=3)
        self.ssid = tk.StringVar(value="MyHotspot")
        ttk.Entry(form, textvariable=self.ssid).grid(row=0, column=1, sticky="ew", padx=8)

        self.lbl_psk = ttk.Label(form)
        self.lbl_psk.grid(row=1, column=0, sticky="w", pady=3)
        self.psk = tk.StringVar()
        self.ent_psk = ttk.Entry(form, textvariable=self.psk, show="•")
        self.ent_psk.grid(row=1, column=1, sticky="ew", padx=8)
        self.showpw = tk.BooleanVar(value=False)
        self.chk_show = ttk.Checkbutton(form, variable=self.showpw, command=self.toggle_pw)
        self.chk_show.grid(row=1, column=2)

        self.lbl_ch = ttk.Label(form)
        self.lbl_ch.grid(row=2, column=0, sticky="w", pady=3)
        self.channel = tk.StringVar(value="1")
        ttk.Spinbox(form, from_=1, to=11, width=5, textvariable=self.channel).grid(row=2, column=1, sticky="w", padx=8)

        self.autostart = tk.BooleanVar(value=False)
        self.chk_auto = ttk.Checkbutton(form, variable=self.autostart, command=self.on_autostart)
        self.chk_auto.grid(row=3, column=0, columnspan=2, sticky="w", pady=3)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=12)
        self.btn_save = ttk.Button(bar, command=self.on_save)
        self.btn_save.pack(side="left")
        self.btn_start = ttk.Button(bar, command=self.on_start)
        self.btn_start.pack(side="left", padx=8)
        self.btn_stop = ttk.Button(bar, command=self.on_stop)
        self.btn_stop.pack(side="left")
        self.btn_qr = ttk.Button(bar, command=self.on_qr)
        self.btn_qr.pack(side="left", padx=8)

        self.f_cl = ttk.LabelFrame(self)
        self.f_cl.pack(fill="x", padx=12, pady=(10, 0))
        self.tree = ttk.Treeview(self.f_cl, columns=("ip", "mac", "sig", "time", "data"), height=4, selectmode="none")
        for col, w in (("#0", 120), ("ip", 95), ("mac", 130), ("sig", 70), ("time", 85), ("data", 105)):
            self.tree.column(col, width=w, anchor="w")
        self.tree.pack(fill="x", padx=6, pady=(6, 2))
        self.lbl_cl = ttk.Label(self.f_cl, foreground="#888888")
        self.lbl_cl.pack(anchor="w", padx=8, pady=(0, 6))

        self.lbl_log = ttk.Label(self)
        self.lbl_log.pack(anchor="w", padx=12, pady=(12, 2))
        self.log = tk.Text(self, height=8, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.apply_lang()
        self.load_profile()
        self.update_status()

    # --- i18n / UI helpers
    def apply_lang(self):
        self.title(t("title"))
        self.lbl_title.config(text=t("title"))
        self.btn_lang.config(text=t("lang_btn"))
        self.tree.heading("#0", text=t("c_name"))
        for col, key in (("ip", "c_ip"), ("mac", "c_mac"), ("sig", "c_sig"), ("time", "c_time"), ("data", "c_data")):
            self.tree.heading(col, text=t(key))
        self.refresh_clients()
        self.lbl_iface.config(text=t("iface") + ":")
        self.lbl_state.config(text=t("state") + ":")
        self.lbl_ssid.config(text=t("ssid"))
        self.lbl_psk.config(text=t("psk"))
        self.chk_show.config(text=t("show"))
        self.lbl_ch.config(text=t("channel"))
        self.chk_auto.config(text=t("autostart"))
        self.btn_save.config(text=t("save"))
        self.btn_start.config(text=t("start"))
        self.btn_stop.config(text=t("stop"))
        self.btn_qr.config(text=t("qr"))
        self.lbl_log.config(text=t("log"))
        self.val_iface.config(text=self.iface or t("no_iface"))
        self.refresh_state_label()

    def toggle_lang(self):
        global LANG
        LANG = "ka" if LANG == "en" else "en"
        save_lang(LANG)
        self.apply_lang()

    def toggle_pw(self):
        self.ent_psk.config(show="" if self.showpw.get() else "•")

    def write_log(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def refresh_state_label(self):
        on = getattr(self, "active", False)
        self.val_state.config(text=t("on") if on else t("off"),
                              foreground="#1a7f37" if on else "#888888")

    def refresh_clients(self):
        self.tree.delete(*self.tree.get_children())
        rows = list_clients(self.iface) if getattr(self, "active", False) else []
        for c in rows:
            sig = f"{c['signal']} dBm" if c["signal"] is not None else "-"
            self.tree.insert("", "end", text=c["name"] or "—",
                             values=(c["ip"] or "-", c["mac"], sig, human_secs(c["connected"]),
                                     f"{human_bytes(c['rx'])} / {human_bytes(c['tx'])}"))
        self.f_cl.config(text=f"{t('clients')} ({len(rows)})")
        if not getattr(self, "active", False):
            self.lbl_cl.config(text=t("c_off"))
        else:
            self.lbl_cl.config(text="" if rows else t("c_none"))

    def update_status(self):
        if not self.busy:
            self.active = is_active()
            self.refresh_state_label()
            self.refresh_clients()
        self.after(3000, self.update_status)

    def load_profile(self):
        if not profile_exists():
            return
        self.ssid.set(get_prop("802-11-wireless.ssid") or self.ssid.get())
        ch = get_prop("802-11-wireless.channel")
        if ch.isdigit() and ch != "0":
            self.channel.set(ch)
        self.psk.set(get_prop("802-11-wireless-security.psk", secrets=True))
        self.autostart.set(get_prop("connection.autoconnect") == "yes")

    # --- actions (run in a thread, never block the UI)
    def bg(self, label_key, fn):
        if self.busy:
            return
        self.busy = True
        for b in (self.btn_save, self.btn_start, self.btn_stop):
            b.state(["disabled"])
        self.write_log("→ " + t(label_key))

        def work():
            try:
                ok, msg = fn()
            except Exception as e:  # keep the UI alive
                ok, msg = False, str(e)
            self.after(0, lambda: self.finish(ok, msg))
        threading.Thread(target=work, daemon=True).start()

    def finish(self, ok, msg):
        self.busy = False
        for b in (self.btn_save, self.btn_start, self.btn_stop):
            b.state(["!disabled"])
        if msg:
            self.write_log(msg)
        if not ok:
            messagebox.showerror(t("err"), msg or t("fail"))
        self.active = is_active()
        self.refresh_state_label()

    def on_save(self):
        ssid, psk = self.ssid.get().strip(), self.psk.get()
        ch = self.channel.get().strip()
        if not self.iface:
            return messagebox.showerror(t("err"), t("no_wifi"))
        if not ssid:
            return messagebox.showerror(t("err"), t("bad_ssid"))
        if not valid_psk(psk):
            return messagebox.showerror(t("err"), t("bad_psk"))
        if not (ch.isdigit() and 1 <= int(ch) <= 11):
            return messagebox.showerror(t("err"), t("bad_ch"))
        auto = "yes" if self.autostart.get() else "no"

        def work():
            run(["nmcli", "con", "down", CON])
            run(["nmcli", "con", "delete", CON])
            steps = [
                ["nmcli", "con", "add", "type", "wifi", "ifname", self.iface, "con-name", CON,
                 "autoconnect", auto, "ssid", ssid],
                ["nmcli", "con", "modify", CON, "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg",
                 "802-11-wireless.channel", ch, "802-11-wireless.powersave", "2", "ipv4.method", "shared"],
                ["nmcli", "con", "modify", CON, "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.proto", "rsn",
                 "wifi-sec.pairwise", "ccmp", "wifi-sec.group", "ccmp", "wifi-sec.psk", psk],
                ["nmcli", "con", "modify", CON, "802-11-wireless-security.psk-flags", "0"],
                ["nmcli", "con", "modify", CON, "802-11-wireless-security.pmf", "1"],
            ]
            for s in steps:
                rc, out = run(s)
                if rc != 0:
                    return False, out
            return True, t("saved")
        self.bg("saving", work)

    def on_start(self):
        if not profile_exists():
            return messagebox.showerror(t("err"), t("no_profile"))

        def work():
            rc, out = run(["nmcli", "con", "up", CON])
            return rc == 0, (out if rc == 0 else out + "\n" + t("fail"))
        self.bg("starting", work)

    def on_stop(self):
        def work():
            rc, out = run(["nmcli", "con", "down", CON])
            return rc == 0, out
        self.bg("stopping", work)

    def on_qr(self):
        ssid, psk = self.ssid.get().strip(), self.psk.get()
        if not ssid:
            return messagebox.showerror(t("err"), t("bad_ssid"))
        if not valid_psk(psk):
            return messagebox.showerror(t("err"), t("bad_psk"))
        try:
            matrix = lsqr.make_qr(lsqr.wifi_payload(ssid, psk))
        except ValueError:
            return messagebox.showerror(t("err"), t("qr_long"))
        self.show_qr(matrix, ssid)

    def show_qr(self, matrix, ssid):
        win = tk.Toplevel(self)
        win.title(t("qr_title"))
        win.resizable(False, False)
        n, cell, quiet = len(matrix), 8, 4
        side = (n + 2 * quiet) * cell
        cv = tk.Canvas(win, width=side, height=side, bg="white", highlightthickness=0)
        cv.pack(padx=16, pady=(16, 8))
        for y, row in enumerate(matrix):
            for x, dark in enumerate(row):
                if dark:
                    x0, y0 = (x + quiet) * cell, (y + quiet) * cell
                    cv.create_rectangle(x0, y0, x0 + cell, y0 + cell, fill="black", width=0)
        ttk.Label(win, text=t("qr_hint", s=ssid), justify="center").pack(padx=16, pady=(0, 16))

    def on_autostart(self):
        if profile_exists():
            val = "yes" if self.autostart.get() else "no"
            rc, out = run(["nmcli", "con", "modify", CON, "connection.autoconnect", val])
            self.write_log(f"autoconnect = {val}" if rc == 0 else out)


if __name__ == "__main__":
    App().mainloop()
