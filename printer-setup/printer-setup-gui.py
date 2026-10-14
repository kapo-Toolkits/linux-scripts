#!/usr/bin/env python3
"""Printer Setup — find, check, install a driver and add a printer (CUPS). English / ქართული.

Flow:  1 Detect  ->  2 Find driver  ->  3 (if missing) get & check a driver .deb  ->  4 Add printer  ->  5 Test page
It does NOT bundle vendor drivers (licences differ); it finds them, shows what a .deb will do
before installing it, and installs only after you confirm.
Requires: python3-tk, CUPS (lpinfo/lpadmin/lp). apt/dpkg for installing .deb files.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import webbrowser

_here = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_here, "..", "common"), os.path.join(_here, "..", "lib", "linux-scripts"),
           "/usr/local/lib/linux-scripts", "/usr/lib/linux-scripts"):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
from lscommon import ensure_tkinter, load_lang, run, save_lang  # noqa: E402

ensure_tkinter()

import tkinter as tk  # noqa: E402
from tkinter import ttk, messagebox, filedialog, scrolledtext  # noqa: E402

LANG = load_lang()

# vendor (lowercase, first word of the make) -> apt packages worth trying first
APT_HINTS = {
    "epson": ["printer-driver-escpr"],
    "hp": ["hplip"],
    "brother": ["printer-driver-brlaser"],
    "samsung": ["printer-driver-splix"],
    "canon": ["printer-driver-gutenprint"],
}
GENERIC_APT = ["printer-driver-gutenprint"]

STR = {
"en": {
 "title": "Printer Setup", "lang_btn": "ქართული", "tab_setup": "Setup", "tab_guide": "Guide",
 "s1": "1. Detect", "detect": "Detect printers", "none": "No printer found. Plug it in, power it on, press Detect.",
 "s2": "2. Driver", "find": "Find driver", "ppd": "Driver:", "apt": "Try apt drivers",
 "s3": "3. Driver missing?", "web": "Open vendor download page", "deb": "Install downloaded .deb…",
 "s4": "4. Add", "add": "Add printer", "driverless": "Add driverless (network)",
 "s5": "5. Test", "queue": "Queue:", "test": "Print test page", "log": "Log",
 "pick": "Select a printer in the list first.", "err": "Error", "info": "Printer Setup",
 "searching": "Searching installed drivers (can take a few seconds)…",
 "found": "{n} matching driver(s) found.", "notfound": "No installed driver matches “{m}”. Use step 3.",
 "added": "Printer “{q}” added.", "add_fail": "Could not add the printer:\n{e}",
 "no_ppd": "Find a driver first (step 2) or choose one in the list.",
 "not_net": "Driverless needs a network printer (dnssd/ipp).",
 "apt_run": "Installing {p} (administrator password may be requested)…", "apt_ok": "Done. Run Find driver again.",
 "apt_fail": "Install failed:\n{e}",
 "deb_pick": "Choose the downloaded driver (.deb)", "deb_title": "Check before installing",
 "deb_model_ok": "✔ Contains a driver file for “{m}”.", "deb_model_no": "⚠ No file mentioning “{m}” — it may be the wrong package.",
 "install": "Install", "cancel": "Cancel", "deb_installed": "Driver installed. Run Find driver again.",
 "no_queue": "No printer queues yet.", "sent": "Test page sent to “{q}”.", "test_fail": "Could not print:\n{e}",
 "need_model": "Select a detected printer first.",
 "guide": (
  "HOW TO SET UP A PRINTER ON LINUX\n\n"
  "1. Connect the printer (USB, or the same Wi-Fi/LAN), power it on, press Detect printers.\n"
  "2. Select it, press Find driver. If a driver is found, press Add printer.\n"
  "   Network printers often work with no driver: Add driverless.\n"
  "3. If no driver is found:\n"
  "   a) Try apt drivers (vendor packages from your distribution).\n"
  "   b) Otherwise press Open vendor download page, choose your OS (Debian/Ubuntu = DEB, x64),\n"
  "      accept the licence and download the PRINTER DRIVER .deb.\n"
  "      Do NOT take: “Source Code” (.src.rpm), “Utility” (ink levels only), “PC-Fax”, “Manual”.\n"
  "   c) Press Install downloaded .deb… — the app shows its contents and install scripts first.\n"
  "4. Press Find driver again, then Add printer.\n"
  "5. Choose the queue and press Print test page.\n\n"
  "TIPS\n"
  "• Some vendor sites block command-line downloads (HTTP 403) — use your browser.\n"
  "• Use a model-specific name, e.g. “L1250 Series”; a similar model's driver may print wrongly.\n"
  "• Only install drivers from the manufacturer's own site.\n"
  "• Nothing prints? Run in a terminal:  lpstat -t   and   journalctl -u cups -b | tail"),
},
"ka": {
 "title": "პრინტერის დაყენება", "lang_btn": "English", "tab_setup": "დაყენება", "tab_guide": "ინსტრუქცია",
 "s1": "1. აღმოჩენა", "detect": "პრინტერების ძებნა", "none": "პრინტერი ვერ მოიძებნა. შეაერთეთ, ჩართეთ და დააჭირეთ ძებნას.",
 "s2": "2. დრაივერი", "find": "დრაივერის პოვნა", "ppd": "დრაივერი:", "apt": "apt დრაივერები",
 "s3": "3. დრაივერი არ არის?", "web": "მწარმოებლის გვერდის გახსნა", "deb": "ჩამოტვირთული .deb-ის დაყენება…",
 "s4": "4. დამატება", "add": "პრინტერის დამატება", "driverless": "დრაივერის გარეშე (ქსელი)",
 "s5": "5. შემოწმება", "queue": "რიგი:", "test": "სატესტო გვერდი", "log": "ლოგი",
 "pick": "ჯერ სიაში აირჩიეთ პრინტერი.", "err": "შეცდომა", "info": "პრინტერის დაყენება",
 "searching": "ინსტალირებულ დრაივერებში ვეძებ (რამდენიმე წამი)…",
 "found": "ნაპოვნია {n} შესაბამისი დრაივერი.", "notfound": "„{m}“-ისთვის დაყენებული დრაივერი არ არის. გადადით მე-3 ნაბიჯზე.",
 "added": "პრინტერი „{q}“ დაემატა.", "add_fail": "პრინტერი ვერ დაემატა:\n{e}",
 "no_ppd": "ჯერ იპოვეთ დრაივერი (ნაბიჯი 2) ან აირჩიეთ სიიდან.",
 "not_net": "დრაივერის გარეშე მხოლოდ ქსელური პრინტერისთვისაა (dnssd/ipp).",
 "apt_run": "ვაყენებ {p} (შეიძლება ადმინისტრატორის პაროლი მოითხოვოს)…", "apt_ok": "მზადაა. დრაივერის პოვნა თავიდან გაუშვით.",
 "apt_fail": "დაყენება ვერ მოხერხდა:\n{e}",
 "deb_pick": "აირჩიეთ ჩამოტვირთული დრაივერი (.deb)", "deb_title": "შემოწმება დაყენებამდე",
 "deb_model_ok": "✔ შეიცავს დრაივერის ფაილს „{m}“-ისთვის.", "deb_model_no": "⚠ ფაილი, რომელიც „{m}“-ს ახსენებს, არ არის — შეიძლება არასწორი პაკეტია.",
 "install": "დაყენება", "cancel": "გაუქმება", "deb_installed": "დრაივერი დაყენდა. დრაივერის პოვნა თავიდან გაუშვით.",
 "no_queue": "პრინტერის რიგები ჯერ არ არის.", "sent": "სატესტო გვერდი გაიგზავნა „{q}“-ზე.", "test_fail": "ბეჭდვა ვერ მოხერხდა:\n{e}",
 "need_model": "ჯერ აირჩიეთ აღმოჩენილი პრინტერი.",
 "guide": (
  "როგორ დავაყენოთ პრინტერი Linux-ზე\n\n"
  "1. შეაერთეთ პრინტერი (USB ან იმავე Wi-Fi/LAN), ჩართეთ და დააჭირეთ „პრინტერების ძებნა“.\n"
  "2. აირჩიეთ და დააჭირეთ „დრაივერის პოვნა“. თუ ნაპოვნია, დააჭირეთ „პრინტერის დამატება“.\n"
  "   ქსელური პრინტერები ხშირად დრაივერის გარეშე მუშაობს: „დრაივერის გარეშე“.\n"
  "3. თუ დრაივერი ვერ მოიძებნა:\n"
  "   ა) სცადეთ „apt დრაივერები“ (დისტრიბუციის პაკეტები).\n"
  "   ბ) ან დააჭირეთ „მწარმოებლის გვერდის გახსნა“, აირჩიეთ OS (Debian/Ubuntu = DEB, x64),\n"
  "      დაეთანხმეთ ლიცენზიას და ჩამოტვირთეთ ბეჭდვის დრაივერის .deb (Printer Driver).\n"
  "      ნუ აიღებთ: „Source Code“ (.src.rpm), „Utility“ (მხოლოდ მელნის დონე), „PC-Fax“, „Manual“.\n"
  "   გ) დააჭირეთ „ჩამოტვირთული .deb-ის დაყენება…“ — პროგრამა ჯერ შიგთავსს და დაყენების სკრიპტებს გაჩვენებთ.\n"
  "4. კვლავ დააჭირეთ „დრაივერის პოვნა“, შემდეგ „პრინტერის დამატება“.\n"
  "5. აირჩიეთ რიგი და დააჭირეთ „სატესტო გვერდი“.\n\n"
  "რჩევები\n"
  "• ზოგი საიტი ბრძანებით ჩამოტვირთვას ბლოკავს (HTTP 403) — გამოიყენეთ ბრაუზერი.\n"
  "• მოძებნეთ ზუსტი მოდელით, მაგ. „L1250 Series“; მსგავსი მოდელის დრაივერმა შეიძლება არასწორად დაბეჭდოს.\n"
  "• დრაივერი დააყენეთ მხოლოდ მწარმოებლის ოფიციალური საიტიდან.\n"
  "• არ ბეჭდავს? ტერმინალში:  lpstat -t   და   journalctl -u cups -b | tail"),
},
}


def t(k, **kw):
    s = STR[LANG][k]
    return s.format(**kw) if kw else s




def detect_printers():
    """[{uri, make, model, kind}] from `lpinfo -v` (USB direct + network dnssd/ipp)."""
    rc, out = run(["lpinfo", "-v"])
    found, seen = [], set()
    for line in out.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2 or "://" not in parts[1]:
            continue
        kind, uri = parts[0], parts[1].strip()
        u = urllib.parse.urlparse(uri)
        if u.scheme == "usb":
            make, model = urllib.parse.unquote(u.netloc), urllib.parse.unquote(u.path.lstrip("/"))
        elif u.scheme in ("dnssd", "ipp", "ipps"):
            name = urllib.parse.unquote(u.netloc).split("._")[0]
            make, model = (name.split(" ", 1) + [""])[:2] if " " in name else ("", name)
        else:
            continue
        key = (make, model)
        if not model or key in seen:
            continue
        seen.add(key)
        found.append({"uri": uri, "make": make, "model": model,
                      "kind": "usb" if u.scheme == "usb" else "network"})
    return found


def model_token(model):
    m = re.search(r"[A-Za-z]*[- ]?\d{2,}[A-Za-z0-9-]*", model)
    return re.sub(r"[\s-]", "", m.group(0)).lower() if m else re.sub(r"\W", "", model).lower()


def token_regex(tok):
    """'l1250' -> matches l1250 / l-1250 / l_1250, but not hl1250 or l12500."""
    chunks = re.findall(r"[a-z]+|\d+", tok)
    return re.compile(r"(?<![a-z0-9])" + r"[^a-z0-9]?".join(chunks) + r"(?![0-9])")


def search_ppds(make, model):
    """Installed PPDs matching the model (word-bounded, so 'hl1250' != 'l1250')."""
    rc, out = run(["lpinfo", "-m"], timeout=180)
    rx = token_regex(model_token(model))
    vendor = (make.split()[0].lower() if make else "")
    hits = []
    for line in out.splitlines():
        ppd, _, desc = line.partition(" ")
        if rx.search(line.lower()) and (not vendor or vendor in line.lower()):
            hits.append((ppd, desc.strip()))
    return hits


def vendor_url(make, model):
    if make.lower().startswith("epson"):
        q = urllib.parse.quote_plus(model)
        return f"https://download-center.epson.com/download/?device_id={q}&os=DEBX64&region=US&language=en"
    q = urllib.parse.quote_plus(f"{make} {model} linux driver deb")
    return f"https://duckduckgo.com/?q={q}"


def queue_name(model):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", model.strip()).strip("_") or "Printer"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.geometry("720x640")
        self.minsize(640, 560)
        self.printers, self.ppds, self.busy = [], [], False

        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(10, 0))
        self.btn_lang = ttk.Button(top, width=10, command=self.toggle_lang)
        self.btn_lang.pack(side="right")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=12, pady=8)
        self.tab_setup, self.tab_guide = ttk.Frame(self.nb), ttk.Frame(self.nb)
        self.nb.add(self.tab_setup, text="")
        self.nb.add(self.tab_guide, text="")

        s = self.tab_setup
        self.f1 = ttk.LabelFrame(s)
        self.f1.pack(fill="x", padx=8, pady=6)
        self.btn_detect = ttk.Button(self.f1, command=self.on_detect)
        self.btn_detect.pack(anchor="w", padx=8, pady=6)
        self.lst = tk.Listbox(self.f1, height=4, exportselection=False)
        self.lst.pack(fill="x", padx=8, pady=(0, 8))

        self.f2 = ttk.LabelFrame(s)
        self.f2.pack(fill="x", padx=8, pady=6)
        row = ttk.Frame(self.f2)
        row.pack(fill="x", padx=8, pady=6)
        self.btn_find = ttk.Button(row, command=self.on_find)
        self.btn_find.pack(side="left")
        self.btn_apt = ttk.Button(row, command=self.on_apt)
        self.btn_apt.pack(side="left", padx=8)
        row2 = ttk.Frame(self.f2)
        row2.pack(fill="x", padx=8, pady=(0, 8))
        self.lbl_ppd = ttk.Label(row2)
        self.lbl_ppd.pack(side="left")
        self.ppd_var = tk.StringVar()
        self.cmb_ppd = ttk.Combobox(row2, textvariable=self.ppd_var, state="readonly")
        self.cmb_ppd.pack(side="left", fill="x", expand=True, padx=6)

        self.f3 = ttk.LabelFrame(s)
        self.f3.pack(fill="x", padx=8, pady=6)
        row = ttk.Frame(self.f3)
        row.pack(fill="x", padx=8, pady=8)
        self.btn_web = ttk.Button(row, command=self.on_web)
        self.btn_web.pack(side="left")
        self.btn_deb = ttk.Button(row, command=self.on_deb)
        self.btn_deb.pack(side="left", padx=8)

        self.f4 = ttk.LabelFrame(s)
        self.f4.pack(fill="x", padx=8, pady=6)
        row = ttk.Frame(self.f4)
        row.pack(fill="x", padx=8, pady=8)
        self.btn_add = ttk.Button(row, command=self.on_add)
        self.btn_add.pack(side="left")
        self.btn_dl = ttk.Button(row, command=self.on_driverless)
        self.btn_dl.pack(side="left", padx=8)

        self.f5 = ttk.LabelFrame(s)
        self.f5.pack(fill="x", padx=8, pady=6)
        row = ttk.Frame(self.f5)
        row.pack(fill="x", padx=8, pady=8)
        self.lbl_q = ttk.Label(row)
        self.lbl_q.pack(side="left")
        self.q_var = tk.StringVar()
        self.cmb_q = ttk.Combobox(row, textvariable=self.q_var, state="readonly", width=28,
                                  postcommand=self.load_queues)
        self.cmb_q.pack(side="left", padx=6)
        self.btn_test = ttk.Button(row, command=self.on_test)
        self.btn_test.pack(side="left")

        self.lbl_log = ttk.Label(s)
        self.lbl_log.pack(anchor="w", padx=10)
        self.log = scrolledtext.ScrolledText(s, height=6, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.txt_guide = scrolledtext.ScrolledText(self.tab_guide, wrap="word")
        self.txt_guide.pack(fill="both", expand=True, padx=8, pady=8)

        self.buttons = [self.btn_detect, self.btn_find, self.btn_apt, self.btn_web, self.btn_deb,
                        self.btn_add, self.btn_dl, self.btn_test]
        self.apply_lang()
        self.on_detect()

    # ---- i18n
    def apply_lang(self):
        self.title(t("title"))
        self.btn_lang.config(text=t("lang_btn"))
        self.nb.tab(0, text=t("tab_setup"))
        self.nb.tab(1, text=t("tab_guide"))
        for f, k in ((self.f1, "s1"), (self.f2, "s2"), (self.f3, "s3"), (self.f4, "s4"), (self.f5, "s5")):
            f.config(text=t(k))
        self.btn_detect.config(text=t("detect")); self.btn_find.config(text=t("find"))
        self.btn_apt.config(text=t("apt")); self.lbl_ppd.config(text=t("ppd"))
        self.btn_web.config(text=t("web")); self.btn_deb.config(text=t("deb"))
        self.btn_add.config(text=t("add")); self.btn_dl.config(text=t("driverless"))
        self.lbl_q.config(text=t("queue")); self.btn_test.config(text=t("test"))
        self.lbl_log.config(text=t("log"))
        self.txt_guide.config(state="normal")
        self.txt_guide.delete("1.0", "end")
        self.txt_guide.insert("end", t("guide"))
        self.txt_guide.config(state="disabled")
        self.fill_list()

    def toggle_lang(self):
        global LANG
        LANG = "ka" if LANG == "en" else "en"
        save_lang(LANG)
        self.apply_lang()

    # ---- helpers
    def say(self, text):
        self.log.config(state="normal")
        self.log.insert("end", str(text).rstrip() + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def bg(self, work, done=None):
        if self.busy:
            return
        self.busy = True
        for b in self.buttons:
            b.state(["disabled"])

        def thread():
            try:
                res = work()
            except Exception as e:
                res = e
            self.after(0, lambda: self.finish(res, done))
        threading.Thread(target=thread, daemon=True).start()

    def finish(self, res, done):
        self.busy = False
        for b in self.buttons:
            b.state(["!disabled"])
        if isinstance(res, Exception):
            self.say(res)
        elif done:
            done(res)

    def current(self):
        sel = self.lst.curselection()
        if not sel or not self.printers:
            messagebox.showinfo(t("info"), t("pick"))
            return None
        return self.printers[sel[0]]

    def fill_list(self):
        self.lst.delete(0, "end")
        for p in self.printers:
            self.lst.insert("end", f"[{p['kind']}] {p['make']} {p['model']}".strip())
        if not self.printers:
            self.lst.insert("end", t("none"))
        elif not self.lst.curselection():
            self.lst.selection_set(0)

    # ---- step 1
    def on_detect(self):
        self.bg(detect_printers, self.after_detect)

    def after_detect(self, res):
        self.printers = res
        self.fill_list()
        self.say(f"{len(res)} printer(s)" if res else t("none"))

    # ---- step 2
    def on_find(self):
        p = self.current()
        if not p:
            return
        self.say(t("searching"))
        self.bg(lambda: search_ppds(p["make"], p["model"]), lambda hits: self.after_find(p, hits))

    def after_find(self, p, hits):
        self.ppds = hits
        self.cmb_ppd["values"] = [f"{d}  [{n}]" for n, d in hits]
        if hits:
            self.cmb_ppd.current(0)
            self.say(t("found", n=len(hits)))
        else:
            self.ppd_var.set("")
            self.say(t("notfound", m=p["model"]))

    def on_apt(self):
        p = self.current()
        if not p:
            return
        pkgs = APT_HINTS.get(p["make"].split()[0].lower() if p["make"] else "", GENERIC_APT)
        self.say(t("apt_run", p=" ".join(pkgs)))

        def work():
            return run(["pkexec", "apt-get", "install", "-y"] + pkgs, timeout=900)
        self.bg(work, self.after_install)

    def after_install(self, res, ok_key="apt_ok"):
        rc, out = res
        self.say(out[-1500:])
        self.say(t(ok_key) if rc == 0 else t("apt_fail", e=out[-300:]))

    # ---- step 3
    def on_web(self):
        p = self.current()
        if p:
            webbrowser.open(vendor_url(p["make"], p["model"]))

    def on_deb(self):
        p = self.current()
        if not p:
            return
        path = filedialog.askopenfilename(title=t("deb_pick"),
                                          initialdir=os.path.expanduser("~/Downloads"),
                                          filetypes=[("Debian package", "*.deb")])
        if not path:
            return
        self.review_deb(path, p)

    def review_deb(self, path, p):
        tok = model_token(p["model"])
        rc, info = run(["dpkg-deb", "-I", path])
        _, contents = run(["dpkg-deb", "-c", path])
        with open(path, "rb") as f:
            sha = hashlib.sha256(f.read()).hexdigest()
        names = [ln.split()[-1] for ln in contents.splitlines() if ln.split()]
        mentions = [n for n in names if tok in re.sub(r"[\s-]", "", n.lower())]
        ppds = [n for n in names if n.lower().endswith((".ppd", ".ppd.gz"))]
        tmp = tempfile.mkdtemp()
        scripts = ""
        if run(["dpkg-deb", "-e", path, tmp])[0] == 0:
            for s in ("preinst", "postinst", "prerm", "postrm"):
                fp = os.path.join(tmp, s)
                if os.path.isfile(fp):
                    scripts += f"\n===== {s} =====\n" + open(fp, errors="replace").read()
        shutil.rmtree(tmp, ignore_errors=True)

        win = tk.Toplevel(self)
        win.title(t("deb_title"))
        win.geometry("700x560")
        ok = bool(mentions)
        head = (t("deb_model_ok", m=p["model"]) if ok else t("deb_model_no", m=p["model"]))
        ttk.Label(win, text=head, font=("", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 4))
        box = scrolledtext.ScrolledText(win, wrap="none")
        box.pack(fill="both", expand=True, padx=10)
        box.insert("end", f"{os.path.basename(path)}\nsha256: {sha}\n\n{info}\n\n"
                          f"PPD files: {len(ppds)}\n" + "\n".join(mentions[:10]) +
                   f"\n\n--- contents ({len(names)} entries) ---\n{contents}\n\n--- install scripts ---{scripts}")
        box.config(state="disabled")
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=10, pady=10)

        def go():
            win.destroy()
            self.say(t("apt_run", p=os.path.basename(path)))
            self.bg(lambda: run(["pkexec", "apt-get", "install", "-y", os.path.abspath(path)], timeout=900),
                    lambda r: self.after_install(r, "deb_installed"))
        ttk.Button(bar, text=t("install"), command=go).pack(side="right")
        ttk.Button(bar, text=t("cancel"), command=win.destroy).pack(side="right", padx=8)

    # ---- step 4
    def add_queue(self, p, model_arg):
        q = queue_name(p["model"])
        cmd = ["lpadmin", "-p", q, "-E", "-v", p["uri"], "-m", model_arg]
        rc, out = run(cmd)
        if rc != 0:
            rc, out = run(["pkexec"] + cmd)
        return q, rc, out

    def finish_add(self, res):
        q, rc, out = res
        if rc == 0:
            self.say(t("added", q=q))
            self.q_var.set(q)
        else:
            self.say(t("add_fail", e=out))
            messagebox.showerror(t("err"), t("add_fail", e=out))

    def on_add(self):
        p = self.current()
        if not p:
            return
        i = self.cmb_ppd.current()
        if i < 0 or i >= len(self.ppds):
            return messagebox.showinfo(t("info"), t("no_ppd"))
        ppd = self.ppds[i][0]
        self.bg(lambda: self.add_queue(p, ppd), self.finish_add)

    def on_driverless(self):
        p = self.current()
        if not p:
            return
        if p["kind"] != "network":
            return messagebox.showinfo(t("info"), t("not_net"))
        self.bg(lambda: self.add_queue(p, "everywhere"), self.finish_add)

    # ---- step 5
    def load_queues(self):
        rc, out = run(["lpstat", "-e"])
        qs = [x for x in out.splitlines() if x.strip()] if rc == 0 else []
        self.cmb_q["values"] = qs
        if qs and not self.q_var.get():
            self.q_var.set(qs[0])

    def on_test(self):
        self.load_queues()
        q = self.q_var.get()
        if not q:
            return messagebox.showinfo(t("info"), t("no_queue"))
        page = next((f for f in ("/usr/share/cups/data/testprint",
                                 "/usr/share/cups/data/default-testpage.pdf") if os.path.exists(f)), None)
        if not page:
            return messagebox.showerror(t("err"), t("test_fail", e="test page file not found"))

        def work():
            return run(["lp", "-d", q, page])

        def done(r):
            rc, out = r
            self.say(out)
            if rc == 0:
                self.say(t("sent", q=q))
            else:
                messagebox.showerror(t("err"), t("test_fail", e=out))
        self.bg(work, done)


if __name__ == "__main__":
    App().mainloop()
