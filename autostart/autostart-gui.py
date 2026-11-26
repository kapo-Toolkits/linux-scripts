#!/usr/bin/env python3
"""Autostart Manager — which programs start when you log in: turn them on / off, add, remove, start or stop now. English / ქართული.

Works with the XDG Autostart standard every desktop follows (Cinnamon, GNOME, KDE, XFCE, MATE, LXQt):
  ~/.config/autostart/*.desktop        your entries (and your changes to the system's ones)
  /etc/xdg/autostart/*.desktop          the system's entries (never written: no administrator password is needed)
Turning a system entry off writes a copy into ~/.config/autostart with Hidden=true and X-GNOME-Autostart-enabled=false (the way the
desktops' own "Startup Applications" do it); turning it back on removes that copy. Nothing runs through a shell.
Requires: python3-tk.
"""
import os
import re
import shlex
import signal
import subprocess
import sys

_here = os.path.dirname(os.path.abspath(__file__))
for _p in reversed((os.path.join(_here, "..", "common"), os.path.join(_here, "..", "lib", "linux-scripts"),
                    "/usr/local/lib/linux-scripts", "/usr/lib/linux-scripts")):   # first entry wins
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
from lscommon import ensure_tkinter, load_lang, save_lang  # noqa: E402

GROUP = "Desktop Entry"
OVERRIDE = "X-Linux-Scripts-Override"      # a copy of a system entry this program wrote to turn it off
ADDED = "X-Linux-Scripts-Added"            # an entry this program added
INTERPRETERS = {"python", "python3", "sh", "bash", "dash", "perl", "node", "ruby", "java", "env"}
# helpers that start something else and exit: a process with this name is never "that program" (Stop now would hit the wrong thing)
NOT_A_PROGRAM = {"systemctl", "dbus-send", "gdbus", "busctl", "gio", "xdg-open", "flatpak", "snap", "true", "false", "sleep", "nohup", "setsid"}
# parts of the desktop itself: turning them off can break sign-in, passwords, sound, power or settings
CRITICAL = ("polkit", "gnome-keyring", "at-spi", "xdg-user-dirs", "user-dirs-update", "xfsettingsd", "xfce4-power-manager",
            "xfce4-notifyd", "im-launch", "xapp-sn-watcher", "org.gnome.settingsdaemon", "gsd-", "csd-", "cinnamon-settings-daemon",
            "pulseaudio", "pipewire", "light-locker", "xscreensaver", "kwalletd", "pam_kwallet", "lxpolkit", "mate-settings-daemon")


# ---------- desktop files ----------
def parse_desktop(text):
    """The [Desktop Entry] group as {key: value} (keys keep their case and locale suffix)."""
    out, inside = {}, False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            inside = s == f"[{GROUP}]"
            continue
        if inside and "=" in s and not s.startswith("#"):
            k, v = s.split("=", 1)
            out.setdefault(k.strip(), v.strip())
    return out


def set_keys(text, values):
    """Set (or with value None: drop) keys in the [Desktop Entry] group; every other line stays as it was."""
    lines, out, inside, done = text.splitlines(), [], False, set()
    start = None
    for line in lines:
        s = line.strip()
        if s.startswith("["):
            if inside:
                out.extend(f"{k}={v}" for k, v in values.items() if k not in done and v is not None)
                done.update(values)
            inside = s == f"[{GROUP}]"
            if inside:
                start = len(out)
            out.append(line)
            continue
        if inside and "=" in s and not s.startswith("#"):
            k = s.split("=", 1)[0].strip()
            if k in values:
                if k not in done and values[k] is not None:
                    out.append(f"{k}={values[k]}")
                done.add(k)
                continue
        out.append(line)
    if start is None:
        out = [f"[{GROUP}]"] + out
        inside = True
    if inside:
        out.extend(f"{k}={v}" for k, v in values.items() if k not in done and v is not None)
    return "\n".join(out) + "\n"


def localized(d, key, lang):
    return d.get(f"{key}[{lang}]") or d.get(key, "")


def is_true(v):
    return str(v).strip().lower() in ("true", "1", "yes")


def strip_field_codes(exec_line):
    return re.sub(r"%%", "%", re.sub(r"(?<!%)%[fFuUdDnNickvm]", "", exec_line)).strip()


def exec_argv(exec_line):
    try:
        return shlex.split(strip_field_codes(exec_line))
    except ValueError:
        return []


def _is_interpreter(name):
    return os.path.basename(name).rstrip("0123456789.") in INTERPRETERS


def _program_of(argv, depth=0):
    while argv and (os.path.basename(argv[0]) == "env" or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", argv[0])):
        argv = argv[1:]
    if not argv:
        return None
    if not _is_interpreter(argv[0]):
        return argv[0]
    if len(argv) > 2 and argv[1] == "-c" and depth < 2:            # sh -c 'program args'  -> program
        try:
            return _program_of(shlex.split(argv[2]), depth + 1)
        except ValueError:
            return None
    rest = [a for a in argv[1:] if not a.startswith("-")]
    return rest[0] if rest else None                                # python3 /path/x.py -> /path/x.py (never "python3" itself)


def program_names(exec_line):
    """What a running copy of this program looks like: an absolute path (matched exactly) or a command name (matched by name).
    An interpreter (sh, python3 ...) is never a target by itself: for `python3 x.py` it is the script, for `sh -c 'x'` it is x."""
    prog = _program_of(exec_argv(exec_line))
    return [prog] if prog and not _is_interpreter(prog) and os.path.basename(prog) not in NOT_A_PROGRAM else []


def current_desktops(env=None):
    env = os.environ if env is None else env
    return [x.strip().lower() for x in env.get("XDG_CURRENT_DESKTOP", "").split(":") if x.strip()]


def for_this_desktop(d, desktops):
    only = [x.lower() for x in d.get("OnlyShowIn", "").split(";") if x]
    never = [x.lower() for x in d.get("NotShowIn", "").split(";") if x]
    if only and not any(x in only for x in desktops):
        return False
    return not any(x in never for x in desktops)


def dirs(env=None):
    """(your autostart folder, [system autostart folders, most important first])"""
    env = os.environ if env is None else env
    home = env.get("HOME") or os.path.expanduser("~")
    user = os.path.join(env.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"), "autostart")
    system = [os.path.join(p, "autostart") for p in (env.get("XDG_CONFIG_DIRS") or "/etc/xdg").split(":") if p]
    return user, system


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _desktop_files(folder):
    try:
        return sorted(n for n in os.listdir(folder) if n.endswith(".desktop") and os.path.isfile(os.path.join(folder, n)))
    except OSError:
        return []


def scan(env=None, which=None, lang="en"):
    """Every autostart entry as a dict: id, name, comment, exec, scope ('user' = yours only, 'system', 'changed' = a system entry
    with your copy), path (the file that counts), system_path, enabled, why (when off: 'off', 'desktop', 'missing'), critical."""
    env = os.environ if env is None else env
    user, system = dirs(env)
    which = which or (lambda c: _which(c, env))
    desktops = current_desktops(env)
    sys_files = {}
    for folder in system:
        for n in _desktop_files(folder):
            sys_files.setdefault(n, os.path.join(folder, n))
    user_files = {n: os.path.join(user, n) for n in _desktop_files(user)}
    out = []
    for n in sorted(set(sys_files) | set(user_files)):
        path = user_files.get(n) or sys_files[n]
        text = _read(path)
        if text is None:
            continue
        d = parse_desktop(text)
        scope = "changed" if n in user_files and n in sys_files else ("user" if n in user_files else "system")
        if scope == "changed" and is_true(d.get("Hidden")) and not d.get("Exec"):
            d = dict(parse_desktop(_read(sys_files[n]) or ""), Hidden="true")       # a bare "Hidden=true" stub
        why = ""
        if is_true(d.get("Hidden")) or d.get("X-GNOME-Autostart-enabled", "true").lower() == "false":
            why = "off"
        elif not for_this_desktop(d, desktops):
            why = "desktop"
        elif d.get("TryExec") and not which(d["TryExec"]):
            why = "missing"
        low = n.lower()
        out.append({"id": n, "name": localized(d, "Name", lang) or n[:-8], "comment": localized(d, "Comment", lang),
                    "exec": d.get("Exec", ""), "scope": scope, "path": path, "system_path": sys_files.get(n),
                    "enabled": not why, "why": why, "critical": scope != "user" and any(c in low for c in CRITICAL),
                    "ours": is_true(d.get(OVERRIDE)) or is_true(d.get(ADDED))})
    return out


def _which(cmd, env):
    if "/" in cmd:
        return os.access(cmd, os.X_OK)
    import shutil
    return shutil.which(cmd, path=env.get("PATH")) is not None


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def set_enabled(entry, on, env=None):
    """Turn an entry on or off for you. System files are never written: a copy in your autostart folder does it."""
    user, _ = dirs(env)
    mine = os.path.join(user, entry["id"])
    sys_path = entry.get("system_path")
    if on and entry["scope"] == "changed" and sys_path:
        cur = parse_desktop(_read(mine) or "")
        base = parse_desktop(_read(sys_path) or "")
        base_on = not is_true(base.get("Hidden")) and base.get("X-GNOME-Autostart-enabled", "true").lower() != "false"
        if is_true(cur.get(OVERRIDE)) and base_on:
            os.remove(mine)                                    # back to the system's own entry
            return
    if os.path.exists(mine):
        text = _read(mine)
    elif sys_path:
        text = set_keys(_read(sys_path), {OVERRIDE: "true"})
    else:
        raise FileNotFoundError(entry["id"])
    _write(mine, set_keys(text, {"Hidden": "false" if on else "true", "X-GNOME-Autostart-enabled": "true" if on else "false"}))


def remove(entry, env=None):
    """Delete YOUR file of this entry: an entry you added goes away, a changed system entry goes back to the system's setting.
    A system entry without your copy cannot be removed (turn it off instead)."""
    if entry["scope"] == "system":
        raise PermissionError(entry["id"])
    user, _ = dirs(env)
    path = os.path.join(user, entry["id"])
    if os.path.dirname(os.path.realpath(path)) != os.path.realpath(user):
        raise PermissionError(path)
    os.remove(path)


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "program"


def free_name(user, base):
    n, i = f"{base}.desktop", 2
    while os.path.exists(os.path.join(user, n)):
        n, i = f"{base}-{i}.desktop", i + 1
    return n


def add_app(desktop_path, env=None):
    """Copy an installed application's launcher into your autostart folder (turned on). -> the file name."""
    user, _ = dirs(env)
    text = _read(desktop_path)
    if text is None or "Exec" not in parse_desktop(text):
        raise ValueError(desktop_path)
    base = os.path.basename(desktop_path)
    name = base if not os.path.exists(os.path.join(user, base)) else free_name(user, base[:-8])
    _write(os.path.join(user, name), set_keys(text, {"Hidden": None, "NoDisplay": None, "X-GNOME-Autostart-enabled": "true", ADDED: "true"}))
    return name


def add_command(name, command, env=None, delay=0):
    """A new entry for a command you type (run without a shell, like every launcher). -> the file name."""
    name, command = name.strip(), command.strip()
    if not name or not command or any(c in name + command for c in "\r\n\0"):
        raise ValueError("name and command, one line each")
    if not exec_argv(command):
        raise ValueError(command)
    user, _ = dirs(env)
    fname = free_name(user, slug(name))
    keys = {"Type": "Application", "Name": name, "Exec": command, "Terminal": "false", "X-GNOME-Autostart-enabled": "true", ADDED: "true"}
    if delay:
        keys["X-GNOME-Autostart-Delay"] = str(int(delay))
    _write(os.path.join(user, fname), set_keys(f"[{GROUP}]\n", keys))
    return fname


def installed_apps(env=None, lang="en"):
    """[(name, path)] of the applications in the menu (what you can add)."""
    env = os.environ if env is None else env
    home = env.get("HOME") or os.path.expanduser("~")
    roots = [env.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")] + \
        (env.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") + [os.path.join(home, ".local/share/flatpak/exports/share"),
                                                                                  "/var/lib/flatpak/exports/share"]
    seen, out = set(), []
    for r in roots:
        folder = os.path.join(r, "applications")
        for n in _desktop_files(folder):
            if n in seen:
                continue
            seen.add(n)
            d = parse_desktop(_read(os.path.join(folder, n)) or "")
            if d.get("Type", "Application") != "Application" or is_true(d.get("NoDisplay")) or is_true(d.get("Hidden")) or not d.get("Exec"):
                continue
            out.append((localized(d, "Name", lang) or n[:-8], os.path.join(folder, n)))
    return sorted(out, key=lambda x: x[0].lower())


# ---------- running now ----------
def running_pids(names, proc="/proc", uid=None):
    """Your own processes whose program (or script, for python3 x.py) is one of names."""
    uid = os.getuid() if uid is None else uid
    names = {n for n in names if n}
    if not names:
        return []
    out = []
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        return []
    for pid in pids:
        base = os.path.join(proc, pid)
        try:
            if os.stat(base).st_uid != uid or int(pid) == os.getpid():
                continue
            with open(os.path.join(base, "cmdline"), "rb") as f:
                argv = [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
        except (OSError, ValueError):
            continue
        if not argv:
            continue
        prog = argv[0] if not _is_interpreter(argv[0]) else next((a for a in argv[1:3] if not a.startswith("-")), "")
        if not prog:
            continue
        if any(prog == n if n.startswith("/") else os.path.basename(prog) == n for n in names):
            out.append(int(pid))
    return sorted(out)


def stop(pids, uid=None, kill=os.kill, proc="/proc"):
    """SIGTERM to these processes - only those that are still yours. -> how many were signalled."""
    uid = os.getuid() if uid is None else uid
    n = 0
    for pid in pids:
        try:
            if os.stat(os.path.join(proc, str(pid))).st_uid != uid:
                continue
            kill(pid, signal.SIGTERM)
            n += 1
        except OSError:
            pass
    return n


def start(entry, popen=subprocess.Popen):
    argv = exec_argv(entry["exec"])
    if not argv:
        raise ValueError(entry["exec"])
    return popen(argv, start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------- window ----------
STR = {
"en": {
 "title": "Autostart Manager", "lang_btn": "ქართული",
 "head": "Programs that start when you log in",
 "c_on": "Starts", "c_name": "Program", "c_where": "Where", "c_run": "Running now", "c_cmd": "Command",
 "yes": "yes", "no": "no", "w_user": "yours", "w_system": "system", "w_changed": "system (changed by you)",
 "off": "off", "desktop": "not for this desktop", "missing": "program not installed",
 "on_btn": "Turn on", "off_btn": "Turn off", "add_app": "Add program…", "add_cmd": "Add command…", "remove": "Remove",
 "reset": "Reset to system", "start": "Start now", "stop": "Stop now", "refresh": "Refresh",
 "show_all": "Show entries of other desktops",
 "pick": "Select a line first.",
 "critical": "“{name}” is part of the desktop itself (passwords, sign-in, sound, power or settings).\n\nTurning it off can break things after your next login. Turn it off anyway?",
 "remove_ask": "Remove “{name}” from autostart?\n\nThe program itself stays installed.",
 "reset_ask": "Undo your change to “{name}”? It goes back to the system's setting.",
 "sys_remove": "“{name}” is a system entry: it cannot be removed without the administrator, but you can turn it off.",
 "stop_ask": "Stop {n} running process(es) of “{name}” now? Unsaved work in it is lost.",
 "not_running": "“{name}” is not running.", "stopped": "Sent “stop” to {n} process(es) of “{name}”.",
 "started": "“{name}” started.", "start_fail": "Could not start “{name}”:\n{e}",
 "apps_title": "Add a program to autostart", "apps_filter": "Search:", "add": "Add", "cancel": "Cancel",
 "cmd_title": "Add a command to autostart", "cmd_name": "Name:", "cmd_cmd": "Command:", "cmd_delay": "Delay (seconds):",
 "cmd_hint": "Runs without a shell (no pipes or ; ). For those write: sh -c '…'",
 "bad_cmd": "Write a name and a command (one line each).",
 "added": "“{name}” will start at your next login.",
 "note": "Changes apply from your next login. System entries are never edited: your own copy in ~/.config/autostart turns them on or off.",
 "err": "Error",
},
"ka": {
 "title": "ავტოგაშვების მართვა", "lang_btn": "English",
 "head": "პროგრამები, რომლებიც სისტემაში შესვლისას ეშვება",
 "c_on": "ეშვება", "c_name": "პროგრამა", "c_where": "სად", "c_run": "ახლა მუშაობს", "c_cmd": "ბრძანება",
 "yes": "კი", "no": "არა", "w_user": "თქვენი", "w_system": "სისტემის", "w_changed": "სისტემის (თქვენ შეცვალეთ)",
 "off": "გამორთულია", "desktop": "ამ დესკტოპისთვის არ არის", "missing": "პროგრამა არ არის დაყენებული",
 "on_btn": "ჩართვა", "off_btn": "გამორთვა", "add_app": "პროგრამის დამატება…", "add_cmd": "ბრძანების დამატება…", "remove": "წაშლა",
 "reset": "სისტემისაზე დაბრუნება", "start": "ახლავე გაშვება", "stop": "ახლავე გათიშვა", "refresh": "განახლება",
 "show_all": "სხვა დესკტოპების ჩანაწერების ჩვენება",
 "pick": "ჯერ აირჩიეთ ხაზი.",
 "critical": "„{name}“ თავად დესკტოპის ნაწილია (პაროლები, შესვლა, ხმა, კვება ან პარამეტრები).\n\nმისმა გამორთვამ შემდეგი შესვლის შემდეგ შეიძლება რაღაც გააფუჭოს. მაინც გამოვრთო?",
 "remove_ask": "წავშალო „{name}“ ავტოგაშვებიდან?\n\nთავად პროგრამა დაყენებული რჩება.",
 "reset_ask": "გავაუქმო თქვენი ცვლილება „{name}“-ზე? დაუბრუნდება სისტემის პარამეტრს.",
 "sys_remove": "„{name}“ სისტემის ჩანაწერია: ადმინისტრატორის გარეშე ვერ წაიშლება, მაგრამ შეგიძლიათ გამორთოთ.",
 "stop_ask": "გავთიშო „{name}“-ის {n} გაშვებული პროცესი ახლავე? შეუნახავი სამუშაო დაიკარგება.",
 "not_running": "„{name}“ არ მუშაობს.", "stopped": "„{name}“-ის {n} პროცესს გაეგზავნა გათიშვის სიგნალი.",
 "started": "„{name}“ გაეშვა.", "start_fail": "„{name}“ ვერ გაეშვა:\n{e}",
 "apps_title": "პროგრამის დამატება ავტოგაშვებაში", "apps_filter": "ძებნა:", "add": "დამატება", "cancel": "გაუქმება",
 "cmd_title": "ბრძანების დამატება ავტოგაშვებაში", "cmd_name": "სახელი:", "cmd_cmd": "ბრძანება:", "cmd_delay": "დაყოვნება (წამი):",
 "cmd_hint": "ეშვება shell-ის გარეშე (| ან ; არ მუშაობს). ასეთისთვის დაწერეთ: sh -c '…'",
 "bad_cmd": "დაწერეთ სახელი და ბრძანება (თითო ხაზზე).",
 "added": "„{name}“ შემდეგ შესვლაზე გაეშვება.",
 "note": "ცვლილებები მოქმედებს შემდეგი შესვლიდან. სისტემის ჩანაწერები არასოდეს იცვლება: მათ ჩართავს ან გამორთავს თქვენი ასლი ~/.config/autostart-ში.",
 "err": "შეცდომა",
},
}
LANG = "en"


def t(k, **kw):
    s = STR[LANG][k]
    return s.format(**kw) if kw else s


def main():
    global LANG
    ensure_tkinter()
    import tkinter as tk
    from tkinter import ttk, messagebox
    LANG = load_lang()

    class App(tk.Tk):
        def __init__(self):
            super().__init__()
            self.geometry("1060x580")
            self.minsize(760, 420)
            self.entries = []
            top = ttk.Frame(self)
            top.pack(fill="x", padx=12, pady=(10, 4))
            self.lbl_head = ttk.Label(top, font=("", 11, "bold"))
            self.lbl_head.pack(side="left")
            self.btn_lang = ttk.Button(top, width=10, command=self.toggle_lang)
            self.btn_lang.pack(side="right")
            self.show_all = tk.BooleanVar(value=False)
            self.chk_all = ttk.Checkbutton(top, variable=self.show_all, command=self.refresh)
            self.chk_all.pack(side="right", padx=10)

            mid = ttk.Frame(self)
            mid.pack(fill="both", expand=True, padx=12)
            cols = ("on", "name", "where", "run", "cmd")
            self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="browse")
            for c, w in zip(cols, (170, 240, 190, 120, 300)):
                self.tree.column(c, width=w, anchor="w", stretch=c in ("name", "cmd"))
            sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
            self.tree.configure(yscrollcommand=sb.set)
            self.tree.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            self.tree.bind("<Double-1>", lambda e: self.toggle_selected())
            self.tree.tag_configure("off", foreground="gray50")

            bar = ttk.Frame(self)
            bar.pack(fill="x", padx=12, pady=8)
            self.b = {}
            for key, cmd in (("on_btn", lambda: self.switch(True)), ("off_btn", lambda: self.switch(False)), ("start", self.on_start),
                             ("stop", self.on_stop), ("add_app", self.on_add_app), ("add_cmd", self.on_add_cmd),
                             ("remove", self.on_remove), ("refresh", self.refresh)):
                self.b[key] = ttk.Button(bar, command=cmd)
                self.b[key].pack(side="left", padx=(0, 6))
            self.lbl_note = ttk.Label(self, wraplength=1020, foreground="gray40", justify="left")
            self.lbl_note.pack(fill="x", padx=12, pady=(0, 10))
            self.tree.bind("<<TreeviewSelect>>", lambda e: self.update_buttons())
            self.apply_lang()

        def apply_lang(self):
            self.title(t("title"))
            self.lbl_head.config(text=t("head"))
            self.btn_lang.config(text=t("lang_btn"))
            self.chk_all.config(text=t("show_all"))
            for c, k in (("on", "c_on"), ("name", "c_name"), ("where", "c_where"), ("run", "c_run"), ("cmd", "c_cmd")):
                self.tree.heading(c, text=t(k))
            for k, w in self.b.items():
                w.config(text=t(k))
            self.lbl_note.config(text=t("note"))
            self.refresh()

        def toggle_lang(self):
            global LANG
            LANG = "ka" if LANG == "en" else "en"
            save_lang(LANG)
            self.apply_lang()

        def refresh(self):
            sel = self.selected()
            keep = sel["id"] if sel else None
            self.entries = [e for e in scan(lang=LANG) if self.show_all.get() or e["why"] != "desktop"]
            self.tree.delete(*self.tree.get_children())
            for i, e in enumerate(self.entries):
                state = "✔ " + t("yes") if e["enabled"] else "✘ " + t(e["why"])
                running = t("yes") if running_pids(program_names(e["exec"])) else ""
                self.tree.insert("", "end", iid=str(i), tags=() if e["enabled"] else ("off",),
                                 values=(state, e["name"] + (" ⚠" if e["critical"] else ""), t("w_" + e["scope"]), running, e["exec"]))
                if e["id"] == keep:
                    self.tree.selection_set(str(i))
            self.update_buttons()

        def selected(self):
            s = self.tree.selection() if hasattr(self, "tree") else ()
            return self.entries[int(s[0])] if s and int(s[0]) < len(self.entries) else None

        def need(self):
            e = self.selected()
            if not e:
                messagebox.showinfo(t("title"), t("pick"))
            return e

        def update_buttons(self):
            e = self.selected()
            self.b["remove"].config(text=t("reset") if e and e["scope"] == "changed" else t("remove"))

        def toggle_selected(self):
            e = self.selected()
            if e:
                self.switch(not e["enabled"])

        def switch(self, on):
            e = self.need()
            if not e:
                return
            if not on and e["critical"] and not messagebox.askyesno(t("title"), t("critical", name=e["name"]), icon="warning"):
                return
            try:
                set_enabled(e, on)
            except OSError as ex:
                messagebox.showerror(t("err"), str(ex))
            self.refresh()

        def on_remove(self):
            e = self.need()
            if not e:
                return
            if e["scope"] == "system":
                return messagebox.showinfo(t("title"), t("sys_remove", name=e["name"]))
            if not messagebox.askyesno(t("title"), t("reset_ask" if e["scope"] == "changed" else "remove_ask", name=e["name"])):
                return
            try:
                remove(e)
            except OSError as ex:
                messagebox.showerror(t("err"), str(ex))
            self.refresh()

        def on_start(self):
            e = self.need()
            if not e:
                return
            try:
                start(e)
                messagebox.showinfo(t("title"), t("started", name=e["name"]))
            except (OSError, ValueError) as ex:
                messagebox.showerror(t("err"), t("start_fail", name=e["name"], e=ex))
            self.after(1500, self.refresh)

        def on_stop(self):
            e = self.need()
            if not e:
                return
            pids = running_pids(program_names(e["exec"]))
            if not pids:
                return messagebox.showinfo(t("title"), t("not_running", name=e["name"]))
            if messagebox.askyesno(t("title"), t("stop_ask", n=len(pids), name=e["name"])):
                n = stop(pids)
                messagebox.showinfo(t("title"), t("stopped", n=n, name=e["name"]))
                self.after(1000, self.refresh)

        def on_add_app(self):
            apps = installed_apps(lang=LANG)
            win = tk.Toplevel(self)
            win.title(t("apps_title"))
            win.geometry("460x480")
            win.transient(self)
            row = ttk.Frame(win)
            row.pack(fill="x", padx=10, pady=8)
            ttk.Label(row, text=t("apps_filter")).pack(side="left")
            q = tk.StringVar()
            ent = ttk.Entry(row, textvariable=q)
            ent.pack(side="left", fill="x", expand=True, padx=6)
            lst = tk.Listbox(win, exportselection=False)
            lst.pack(fill="both", expand=True, padx=10)
            shown = []

            def fill(*_):
                shown[:] = [a for a in apps if q.get().lower() in a[0].lower()]
                lst.delete(0, "end")
                for name, _p in shown:
                    lst.insert("end", name)
            q.trace_add("write", fill)
            fill()

            def ok():
                s = lst.curselection()
                if not s:
                    return
                name, path = shown[s[0]]
                try:
                    add_app(path)
                except (OSError, ValueError) as ex:
                    return messagebox.showerror(t("err"), str(ex), parent=win)
                win.destroy()
                messagebox.showinfo(t("title"), t("added", name=name))
                self.refresh()
            lst.bind("<Double-1>", lambda e: ok())
            bar = ttk.Frame(win)
            bar.pack(fill="x", padx=10, pady=8)
            ttk.Button(bar, text=t("add"), command=ok).pack(side="right")
            ttk.Button(bar, text=t("cancel"), command=win.destroy).pack(side="right", padx=6)
            ent.focus_set()

        def on_add_cmd(self):
            win = tk.Toplevel(self)
            win.title(t("cmd_title"))
            win.transient(self)
            v_name, v_cmd, v_delay = tk.StringVar(), tk.StringVar(), tk.StringVar(value="0")
            f = ttk.Frame(win)
            f.pack(fill="both", expand=True, padx=12, pady=10)
            for r, (k, v, w) in enumerate((("cmd_name", v_name, 40), ("cmd_cmd", v_cmd, 50), ("cmd_delay", v_delay, 6))):
                ttk.Label(f, text=t(k)).grid(row=r, column=0, sticky="w", pady=3)
                ttk.Entry(f, textvariable=v, width=w).grid(row=r, column=1, sticky="w", pady=3)
            ttk.Label(f, text=t("cmd_hint"), foreground="gray40").grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

            def ok():
                try:
                    delay = int(v_delay.get() or 0)
                    add_command(v_name.get(), v_cmd.get(), delay=max(0, min(delay, 600)))
                except ValueError:
                    return messagebox.showerror(t("err"), t("bad_cmd"), parent=win)
                except OSError as ex:
                    return messagebox.showerror(t("err"), str(ex), parent=win)
                win.destroy()
                messagebox.showinfo(t("title"), t("added", name=v_name.get().strip()))
                self.refresh()
            bar = ttk.Frame(win)
            bar.pack(fill="x", padx=12, pady=(0, 10))
            ttk.Button(bar, text=t("add"), command=ok).pack(side="right")
            ttk.Button(bar, text=t("cancel"), command=win.destroy).pack(side="right", padx=6)

    App().mainloop()


if __name__ == "__main__":
    main()
