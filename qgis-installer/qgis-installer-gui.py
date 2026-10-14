#!/usr/bin/env python3
"""QGIS Installer — English / ქართული.

Three methods, your choice:
  A  Official QGIS repository (Debian / Ubuntu / Mint…) — latest, LTR or nightly, with the signing key
     verified against the published fingerprint before it is trusted.
  B  Flatpak (Flathub) — any distribution, installed for your user only.
  C  Your distribution's own package (apt / dnf / pacman / zypper) — older, but the simplest.
Every action is shown as a command preview first; nothing runs until you confirm.
Source of method A: https://qgis.org/resources/installation-guide/#debian--ubuntu
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading

# ---------------------------------------------------------------- tkinter bootstrap
TK_PKGS = [("apt-get", ["apt-get", "install", "-y"], "python3-tk"),
           ("dnf", ["dnf", "install", "-y"], "python3-tkinter"),
           ("pacman", ["pacman", "-S", "--noconfirm"], "tk"),
           ("zypper", ["zypper", "--non-interactive", "install"], "python3-tk"),
           ("apk", ["apk", "add"], "py3-tkinter")]


def ensure_tkinter():
    try:
        import tkinter  # noqa: F401
        return
    except ImportError:
        pass
    for mgr, cmd, pkg in TK_PKGS:
        if shutil.which(mgr):
            break
    else:
        sys.exit("tkinter missing — install python3-tk / python3-tkinter / tk")
    if sys.stdin.isatty() and input(f"tkinter is missing. Install {pkg}? [Y/n] ").strip().lower() not in ("", "y", "yes"):
        sys.exit("Cancelled.")
    elevate = ["pkexec"] if shutil.which("pkexec") and os.environ.get("DISPLAY") else ["sudo"]
    if mgr == "apt-get":
        subprocess.run(elevate + ["apt-get", "update"])
    if subprocess.run(elevate + cmd + [pkg]).returncode != 0:
        sys.exit(f"Could not install {pkg}.")
    os.execv(sys.executable, [sys.executable] + sys.argv)


if __name__ == "__main__":
    ensure_tkinter()

import tkinter as tk  # noqa: E402
from tkinter import ttk, messagebox, scrolledtext  # noqa: E402

# ---------------------------------------------------------------- data
LATEST, LTR = "4.2.x", "3.44.x"           # per the QGIS installation guide (2026-10)
KEY_URL = "https://download.qgis.org/downloads/qgis-archive-keyring.gpg"
KEY_FPR = "2D7E3441A707FDB3E7059441D155B8E6A419C5BE"   # expires 2027-08-08
KEYRING = "/etc/apt/keyrings/qgis-archive-keyring.gpg"
SOURCES = "/etc/apt/sources.list.d/qgis.sources"

# supported codenames -> LTR only?
SUPPORT = {
    "debian": {"bookworm": True, "trixie": False, "sid": False},
    "ubuntu": {"resolute": False, "questing": False, "plucky": False, "noble": True, "jammy": True},
}
# channel key -> repository suffix
SUFFIX = {"latest": "", "ltr": "-ltr", "nightly-release": "-nightly-release",
          "nightly-ltr": "-nightly-ltr", "nightly": "-nightly"}
CHANNELS = ["latest", "ltr", "nightly-release", "nightly-ltr", "nightly"]
LTR_ONLY_CHANNELS = ["ltr", "nightly-ltr"]

LANG = "en"
STR = {
"en": {
 "title": "QGIS Installer", "lang_btn": "ქართული", "tab_inst": "Install", "tab_guide": "Guide",
 "f_sys": "Your system", "f_method": "Method", "f_ver": "Version (official repository)",
 "f_pkg": "Packages (official repository)", "log": "Log",
 "mA": "A. Official QGIS repository (Debian/Ubuntu/Mint) — recommended",
 "mB": "B. Flatpak (Flathub) — any distribution, your user only",
 "mC": "C. Distribution package — simplest, usually older",
 "ch_latest": "Latest release {v}", "ch_ltr": "Long-term release (LTR) {v} — most stable",
 "ch_nightly-release": "Nightly of the next point release", "ch_nightly-ltr": "Nightly of the next LTR point release",
 "ch_nightly": "Nightly development (master) — unstable, debug build",
 "p_grass": "GRASS plugin (qgis-plugin-grass)", "p_server": "QGIS Server (qgis-server)",
 "p_python": "Python plugin support (python3-qgis)",
 "preview": "Preview & install…", "remove": "Uninstall…", "copy": "Copy commands",
 "sys_line": "{name} • codename: {code} • arch: {arch} • package manager: {pm}",
 "st_ok": "✔ Official repository supports this system.",
 "st_ltr": "ℹ This release has only the LTR line in the official repository (dependencies are not QGIS 4 ready).",
 "st_unsup": "⚠ This system is not in the official repository list — use Flatpak (B) or the distribution package (C).",
 "st_nodeb": "ℹ Not Debian/Ubuntu-based — the official apt repository does not apply. Use Flatpak (B) or the distribution package (C).",
 "st_arch": "⚠ The official repository is built for amd64 only.",
 "st_inst": "Installed now: {v}", "st_none": "QGIS is not installed (apt).",
 "confirm_title": "Review before running", "will_run": "These commands will run:",
 "root_note": "# runs as administrator (a password prompt appears)", "user_note": "# runs as your user",
 "run": "Run", "cancel": "Cancel", "done_ok": "Finished successfully. Find QGIS in the application menu.",
 "done_fail": "A step failed (exit code {rc}). See the log.",
 "elev_fail": "Could not get administrator rights automatically.\nRun this in a terminal instead:\n\n{cmd}",
 "copied": "Commands copied to the clipboard.", "running": "Running…",
 "no_method": "This method is not available on your system.",
 "rm_title": "Uninstall QGIS", "tab_rm": "Uninstall / switch version",
 "rm_goto": "Uninstall / switch version…", "rm_scan": "Rescan", "rm_sel": "Remove selected…",
 "rm_none": "No QGIS installation found (apt, repository files, Flatpak, Snap, distro package, user data).",
 "rm_found": "Found — tick what to remove:", "rm_opts": "Options",
 "rm_purge": "Also delete system configuration files (apt purge)", "rm_auto": "Remove unused dependencies afterwards (autoremove)",
 "rm_next": "After removal, open the Install tab (to choose another version)",
 "rm_data_warn": "⚠ User data = your QGIS profiles, settings, installed plugins. Deleted permanently, not ticked by default.",
 "rm_nothing": "Nothing selected.",
 "k_apt": "apt packages: {n} (qgis {v}) — source: {o}", "k_repo": "QGIS apt repository files: {f}{c}",
 "k_flatpak": "Flatpak ({i}) org.qgis.qgis {v}", "k_snap": "Snap: qgis {v}", "k_dist": "Distribution package ({pm}): qgis {v}",
 "k_data": "User data: {p} ({sz})", "k_unknown": "unknown",
 "guide": (
  "WHICH METHOD?\n\n"
  "A  Official repository — newest QGIS, updated through apt. Debian 12/13/sid, Ubuntu 22.04–26.04 and derivatives (Linux Mint uses its Ubuntu codename).\n"
  "   Debian 12, Ubuntu 22.04 and 24.04 get only the LTR line (their libraries are too old for QGIS 4).\n"
  "B  Flatpak — works on every distribution, sandboxed, installs for your user. Slightly bigger and files access is sandboxed.\n"
  "C  Distribution package — tiny effort, but often an old QGIS.\n\n"
  "CHANNELS\n\n"
  "• Latest release — newest features (new major version first months can be rough).\n"
  "• LTR (long-term) — fewer changes, best for work and teaching.\n"
  "• Nightly — rebuilt daily, may break. Not for production.\n\n"
  "WHAT METHOD A DOES\n\n"
  "1. installs wget, gnupg, ca-certificates\n"
  "2. downloads the QGIS signing key and CHECKS its fingerprint (" + KEY_FPR + ") — aborts on mismatch\n"
  "3. installs it to " + KEYRING + "\n"
  "4. writes " + SOURCES + " (your codename + chosen channel)\n"
  "5. apt update, then installs the packages you ticked\n\n"
  "TROUBLESHOOTING\n\n"
  "• Remove QGIS from other sources first (distribution packages, other PPAs) to avoid conflicts.\n"
  "• “NO_PUBKEY”/key errors: the signing key expires 2027-08-08 — download a newer key from qgis.org.\n"
  "• Repository 404 after a distro upgrade: use Uninstall…, then install again for the new codename.\n"
  "• Administrator prompt does not appear: the app shows the commands to paste in a terminal.\n\n"
  "SWITCHING VERSION\n\n"
  "Use the Uninstall tab: it finds every QGIS (apt, repository files, Flatpak, Snap, distro package, user data), you tick what to remove, then choose another version in the Install tab. Going from a newer to an older line (e.g. latest → LTR) needs the old one removed first — apt will not downgrade."),
},
"ka": {
 "title": "QGIS-ის დაყენება", "lang_btn": "English", "tab_inst": "დაყენება", "tab_guide": "ინსტრუქცია",
 "f_sys": "თქვენი სისტემა", "f_method": "მეთოდი", "f_ver": "ვერსია (ოფიციალური რეპოზიტორია)",
 "f_pkg": "პაკეტები (ოფიციალური რეპოზიტორია)", "log": "ლოგი",
 "mA": "ა. ოფიციალური QGIS რეპოზიტორია (Debian/Ubuntu/Mint) — რეკომენდებული",
 "mB": "ბ. Flatpak (Flathub) — ნებისმიერ დისტრიბუციაზე, მხოლოდ თქვენთვის",
 "mC": "გ. დისტრიბუციის პაკეტი — უმარტივესი, ხშირად ძველი ვერსია",
 "ch_latest": "უახლესი რელიზი {v}", "ch_ltr": "გრძელვადიანი რელიზი (LTR) {v} — ყველაზე სტაბილური",
 "ch_nightly-release": "შემდეგი point-რელიზის ღამის ბილდი", "ch_nightly-ltr": "შემდეგი LTR point-რელიზის ღამის ბილდი",
 "ch_nightly": "განვითარების ღამის ბილდი (master) — არასტაბილური, debug",
 "p_grass": "GRASS დანამატი (qgis-plugin-grass)", "p_server": "QGIS Server (qgis-server)",
 "p_python": "Python დანამატების მხარდაჭერა (python3-qgis)",
 "preview": "ნახვა და დაყენება…", "remove": "წაშლა…", "copy": "ბრძანებების კოპირება",
 "sys_line": "{name} • კოდური სახელი: {code} • არქიტექტურა: {arch} • პაკეტ-მენეჯერი: {pm}",
 "st_ok": "✔ ოფიციალური რეპოზიტორია ამ სისტემას უჭერს მხარს.",
 "st_ltr": "ℹ ამ სისტემისთვის ოფიციალურ რეპოზიტორიაში მხოლოდ LTR ხაზია (ბიბლიოთეკები QGIS 4-ისთვის მზად არ არის).",
 "st_unsup": "⚠ ეს სისტემა ოფიციალური რეპოზიტორიის სიაში არ არის — გამოიყენეთ Flatpak (ბ) ან დისტრიბუციის პაკეტი (გ).",
 "st_nodeb": "ℹ სისტემა Debian/Ubuntu-ზე დაფუძნებული არ არის — ოფიციალური apt რეპოზიტორია არ გამოდგება. გამოიყენეთ Flatpak (ბ) ან დისტრიბუციის პაკეტი (გ).",
 "st_arch": "⚠ ოფიციალური რეპოზიტორია მხოლოდ amd64-ისთვისაა.",
 "st_inst": "ახლა დაყენებულია: {v}", "st_none": "QGIS დაყენებული არ არის (apt).",
 "confirm_title": "გადახედეთ გაშვებამდე", "will_run": "შესრულდება ეს ბრძანებები:",
 "root_note": "# ადმინისტრატორის უფლებით (გამოჩნდება პაროლის ფანჯარა)", "user_note": "# თქვენი მომხმარებლით",
 "run": "გაშვება", "cancel": "გაუქმება", "done_ok": "წარმატებით დასრულდა. QGIS მოძებნეთ აპლიკაციების მენიუში.",
 "done_fail": "ერთი ნაბიჯი ჩავარდა (კოდი {rc}). იხილეთ ლოგი.",
 "elev_fail": "ადმინისტრატორის უფლება ავტომატურად ვერ მივიღე.\nგაუშვით ტერმინალში:\n\n{cmd}",
 "copied": "ბრძანებები დაკოპირდა.", "running": "სრულდება…",
 "no_method": "ეს მეთოდი თქვენს სისტემაზე ხელმისაწვდომი არ არის.",
 "rm_title": "QGIS-ის წაშლა", "tab_rm": "წაშლა / ვერსიის შეცვლა",
 "rm_goto": "წაშლა / ვერსიის შეცვლა…", "rm_scan": "თავიდან ძებნა", "rm_sel": "მონიშნულის წაშლა…",
 "rm_none": "QGIS-ის არცერთი ინსტალაცია ვერ მოიძებნა (apt, რეპოზიტორიის ფაილები, Flatpak, Snap, დისტრიბუციის პაკეტი, მომხმარებლის მონაცემები).",
 "rm_found": "ნაპოვნია — მონიშნეთ რისი წაშლაც გინდათ:", "rm_opts": "პარამეტრები",
 "rm_purge": "სისტემური კონფიგურაციის ფაილებიც წაიშალოს (apt purge)", "rm_auto": "შემდეგ წაიშალოს გამოუყენებელი დამოკიდებულებები (autoremove)",
 "rm_next": "წაშლის შემდეგ გაიხსნას „დაყენება“ (სხვა ვერსიის ასარჩევად)",
 "rm_data_warn": "⚠ მომხმარებლის მონაცემები = თქვენი QGIS პროფილები, პარამეტრები, დაყენებული დანამატები. იშლება სამუდამოდ, ნაგულისხმევად მონიშნული არ არის.",
 "rm_nothing": "არაფერია მონიშნული.",
 "k_apt": "apt პაკეტები: {n} (qgis {v}) — წყარო: {o}", "k_repo": "QGIS apt რეპოზიტორიის ფაილები: {f}{c}",
 "k_flatpak": "Flatpak ({i}) org.qgis.qgis {v}", "k_snap": "Snap: qgis {v}", "k_dist": "დისტრიბუციის პაკეტი ({pm}): qgis {v}",
 "k_data": "მომხმარებლის მონაცემები: {p} ({sz})", "k_unknown": "უცნობი",
 "guide": (
  "რომელი მეთოდი?\n\n"
  "ა  ოფიციალური რეპოზიტორია — ყველაზე ახალი QGIS, განახლება apt-ით. Debian 12/13/sid, Ubuntu 22.04–26.04 და წარმოებულები (Linux Mint-ი თავის Ubuntu-ს კოდურ სახელს იყენებს).\n"
  "   Debian 12-ს, Ubuntu 22.04-სა და 24.04-ს მხოლოდ LTR ხაზი აქვს (ბიბლიოთეკები QGIS 4-ისთვის ძველია).\n"
  "ბ  Flatpak — ნებისმიერ დისტრიბუციაზე მუშაობს, იზოლირებულია, თქვენი მომხმარებლისთვის ყენდება. ცოტა მძიმეა და ფაილებზე წვდომა შეზღუდულია.\n"
  "გ  დისტრიბუციის პაკეტი — უმარტივესი, მაგრამ ხშირად ძველი QGIS.\n\n"
  "არხები\n\n"
  "• უახლესი რელიზი — ახალი შესაძლებლობები (ახალი მაჟორული ვერსიის პირველ თვეებში შეიძლება უხეში იყოს).\n"
  "• LTR (გრძელვადიანი) — ნაკლები ცვლილება, სამუშაოსა და სწავლებისთვის საუკეთესო.\n"
  "• Nightly — ყოველდღე ახლდება, შეიძლება გაფუჭდეს. სამუშაოსთვის არ ვარგა.\n\n"
  "რას აკეთებს მეთოდი „ა“\n\n"
  "1. აყენებს wget, gnupg, ca-certificates\n"
  "2. ჩამოტვირთავს QGIS-ის ხელმოწერის გასაღებს და ამოწმებს თითის ანაბეჭდს (" + KEY_FPR + ") — შეუსაბამობისას წყდება\n"
  "3. ათავსებს აქ: " + KEYRING + "\n"
  "4. წერს " + SOURCES + " (თქვენი კოდური სახელი + არჩეული არხი)\n"
  "5. apt update, შემდეგ აყენებს მონიშნულ პაკეტებს\n\n"
  "პრობლემები\n\n"
  "• ჯერ წაშალეთ QGIS სხვა წყაროებიდან (დისტრიბუციის პაკეტები, სხვა PPA), კონფლიქტი რომ არ მოხდეს.\n"
  "• „NO_PUBKEY“/გასაღების შეცდომა: გასაღები 2027-08-08-ს იწურება — qgis.org-დან ახალი გადმოწერეთ.\n"
  "• 404 დისტრიბუციის განახლების შემდეგ: „წაშლა…“, მერე ახალი კოდური სახელით თავიდან დააყენეთ.\n"
  "• ადმინისტრატორის ფანჯარა არ ჩანს: აპი აჩვენებს ბრძანებებს ტერმინალში ჩასასმელად.\n\n"
  "ვერსიის შეცვლა\n\n"
  "გამოიყენეთ „წაშლა“ ჩანართი: ის პოულობს ყველა QGIS-ს (apt, რეპოზიტორიის ფაილები, Flatpak, Snap, დისტრიბუციის პაკეტი, მომხმარებლის მონაცემები), მონიშნავთ რისი წაშლაც გინდათ, მერე „დაყენება“ ჩანართში სხვა ვერსიას არჩევთ. ახალი ხაზიდან ძველზე (მაგ. უახლესი → LTR) გადასვლისას ჯერ ძველი უნდა წაიშალოს — apt ვერსიას არ დააქვეითებს."),
},
}


def t(k, **kw):
    s = STR[LANG][k]
    return s.format(**kw) if kw else s


# ---------------------------------------------------------------- system detection
def read_os_release():
    d = {}
    try:
        for line in open("/etc/os-release"):
            if "=" in line:
                k, v = line.rstrip("\n").split("=", 1)
                d[k] = v.strip('"')
    except OSError:
        pass
    return d


def detect():
    o = read_os_release()
    like = (o.get("ID", "") + " " + o.get("ID_LIKE", "")).lower()
    family, code = None, o.get("VERSION_CODENAME", "")
    if o.get("UBUNTU_CODENAME"):
        family, code = "ubuntu", o["UBUNTU_CODENAME"]
    elif o.get("DEBIAN_CODENAME"):
        family, code = "debian", o["DEBIAN_CODENAME"]
    elif "ubuntu" in like:
        family = "ubuntu"
    elif "debian" in like:
        family = "debian"
    pm = next((m for m in ("apt-get", "dnf", "pacman", "zypper") if shutil.which(m)), "")
    arch = ""
    if shutil.which("dpkg"):
        arch = subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True).stdout.strip()
    else:
        arch = os.uname().machine
    supported, ltr_only = False, False
    if family and code in SUPPORT.get(family, {}):
        supported, ltr_only = True, SUPPORT[family][code]
    return {"name": o.get("PRETTY_NAME", "Linux"), "family": family, "code": code, "pm": pm,
            "arch": arch, "supported": supported, "ltr_only": ltr_only,
            "apt": family is not None and pm == "apt-get"}


def installed_qgis():
    if not shutil.which("dpkg-query"):
        return None
    r = subprocess.run(["dpkg-query", "-W", "-f=${Status} ${Version}", "qgis"], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.startswith("install ok installed"):
        return r.stdout.split()[-1]
    return None


# ---------------------------------------------------------------- command builders
def sources_text(sysinfo, channel):
    uri = f"https://qgis.org/{sysinfo['family']}{SUFFIX[channel]}"
    return (f"Types: deb\nURIs: {uri}\nSuites: {sysinfo['code']}\nArchitectures: amd64\n"
            f"Components: main\nSigned-By: {KEYRING}\n")


def build_install(method, sysinfo, channel, pkgs):
    """-> list of steps {root: bool, sh: str}. POSIX sh only."""
    if method == "A":
        names = ["qgis"] + (["qgis-plugin-grass"] if pkgs["grass"] else []) + (["python3-qgis"] if pkgs["python"] else [])
        steps = [
            {"root": True, "sh": f"""set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y wget gnupg ca-certificates
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
wget -qO "$TMP/key.gpg" {KEY_URL}
mkdir -m700 "$TMP/gnupg"
FPR=$(gpg --homedir "$TMP/gnupg" --no-default-keyring --keyring "$TMP/key.gpg" --list-keys --with-colons | awk -F: '$1=="fpr"{{print $10; exit}}')
if [ "$FPR" != "{KEY_FPR}" ]; then echo "KEY FINGERPRINT MISMATCH: $FPR" >&2; exit 1; fi
echo "Key fingerprint OK: $FPR"
install -m755 -d /etc/apt/keyrings
install -m644 "$TMP/key.gpg" {KEYRING}
cat > {SOURCES} <<'EOF'
{sources_text(sysinfo, channel)}EOF
apt-get update
apt-get install -y {' '.join(names)}
"""}]
        if pkgs["server"]:
            steps[0]["sh"] += "apt-get install -y --no-install-recommends --no-install-suggests qgis-server\n"
        return steps
    if method == "B":
        steps = []
        if not shutil.which("flatpak"):
            pm = sysinfo["pm"]
            inst = {"apt-get": "apt-get install -y flatpak", "dnf": "dnf install -y flatpak",
                    "pacman": "pacman -S --noconfirm flatpak", "zypper": "zypper --non-interactive install flatpak"}.get(pm)
            if inst:
                steps.append({"root": True, "sh": "set -eu\n" + inst + "\n"})
        steps.append({"root": False, "sh": """set -eu
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user -y flathub org.qgis.qgis
"""})
        return steps
    pm = sysinfo["pm"]
    cmd = {"apt-get": "apt-get install -y qgis qgis-plugin-grass", "dnf": "dnf install -y qgis",
           "pacman": "pacman -S --noconfirm qgis", "zypper": "zypper --non-interactive install qgis"}.get(pm)
    return [{"root": True, "sh": f"set -eu\n{cmd}\n"}] if cmd else []


def _run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout
    except Exception:
        return 1, ""


def _du(path):
    rc, out = _run(["du", "-sk", path])
    try:
        kb = int(out.split()[0])
    except (IndexError, ValueError):
        return "?"
    return f"{kb / 1024:.0f} MB" if kb >= 1024 else f"{kb} KB"


USER_DATA = ["~/.local/share/QGIS", "~/.config/QGIS", "~/.cache/QGIS", "~/.var/app/org.qgis.qgis"]


def find_installs(sysinfo):
    """Everything QGIS-related on this machine -> list of item dicts."""
    import glob
    items = []
    # apt / dpkg
    if shutil.which("dpkg-query"):
        rc, out = _run(["dpkg-query", "-W", "-f=${db:Status-Abbrev}|${Package}|${Version}\\n",
                        "qgis*", "python3-qgis*", "libqgis*"])
        pk, ver = [], ""
        for line in out.splitlines():
            st, _, rest = line.partition("|")
            if st.strip() == "ii":
                name, _, v = rest.partition("|")
                pk.append(name)
                if name == "qgis":
                    ver = v
        if pk:
            origin = ""
            rc, pol = _run(["apt-cache", "policy", "qgis" if "qgis" in pk else sorted(pk)[0]])
            lines = pol.splitlines()
            for i, ln in enumerate(lines):
                if "***" in ln and i + 1 < len(lines):
                    origin = lines[i + 1].split()[1] if len(lines[i + 1].split()) > 1 else ""
                    break
            items.append({"kind": "apt", "pkgs": sorted(set(pk)), "v": ver or "?", "o": origin, "root": True})
    # repository + key files
    files = []
    for pat in ("/etc/apt/sources.list.d/*qgis*", "/etc/apt/keyrings/*qgis*", "/usr/share/keyrings/*qgis*",
                "/etc/apt/trusted.gpg.d/*qgis*"):
        files += glob.glob(pat)
    if files:
        chan = ""
        for f in files:
            if f.endswith((".sources", ".list")):
                m = re.search(r"qgis\.org/(\S+)", open(f, errors="replace").read())
                if m:
                    chan = f" — {m.group(1)}"
                    break
        items.append({"kind": "repo", "files": sorted(files), "c": chan, "root": True})
    # flatpak
    if shutil.which("flatpak"):
        rc, out = _run(["flatpak", "list", "--app", "--columns=application,version,installation"])
        for line in out.splitlines():
            c = [x.strip() for x in line.split("\t")]
            if c and c[0] == "org.qgis.qgis":
                inst = c[2] if len(c) > 2 else "user"
                items.append({"kind": "flatpak", "i": inst, "v": c[1] if len(c) > 1 else "?",
                              "root": inst == "system"})
    # snap
    if shutil.which("snap"):
        rc, out = _run(["snap", "list", "qgis"])
        for line in out.splitlines()[1:]:
            c = line.split()
            if c and c[0] == "qgis":
                items.append({"kind": "snap", "v": c[1] if len(c) > 1 else "?", "root": True})
    # distro packages other than apt
    pm = sysinfo["pm"]
    if pm == "pacman" and _run(["pacman", "-Q", "qgis"])[0] == 0:
        items.append({"kind": "dist", "pm": pm, "v": _run(["pacman", "-Q", "qgis"])[1].split()[-1], "root": True})
    elif pm in ("dnf", "zypper") and shutil.which("rpm"):
        rc, out = _run(["rpm", "-q", "--qf", "%{VERSION}", "qgis"])
        if rc == 0:
            items.append({"kind": "dist", "pm": pm, "v": out.strip(), "root": True})
    # user data (never ticked by default)
    for d in USER_DATA:
        full = os.path.expanduser(d)
        if os.path.isdir(full):
            items.append({"kind": "data", "path": full, "sz": _du(full), "root": False})
    return items


def label_for(it):
    k = it["kind"]
    if k == "apt":
        return t("k_apt", n=len(it["pkgs"]), v=it["v"], o=it["o"] or t("k_unknown"))
    if k == "repo":
        return t("k_repo", f=", ".join(os.path.basename(f) for f in it["files"]), c=it["c"])
    if k == "flatpak":
        return t("k_flatpak", i=it["i"], v=it["v"])
    if k == "snap":
        return t("k_snap", v=it["v"])
    if k == "dist":
        return t("k_dist", pm=it["pm"], v=it["v"])
    return t("k_data", p=it["path"], sz=it["sz"])


def build_remove_steps(items, purge, autoremove, sysinfo):
    """items = selected item dicts -> steps (one root step so the password is asked once)."""
    import shlex
    root, user = [], []
    home = os.path.expanduser("~")
    for it in items:
        k = it["kind"]
        if k == "apt":
            root.append(f"apt-get {'purge' if purge else 'remove'} -y {' '.join(shlex.quote(p) for p in it['pkgs'])}")
        elif k == "repo":
            root.append("rm -f " + " ".join(shlex.quote(f) for f in it["files"]))
        elif k == "flatpak":
            (root if it["root"] else user).append(f"flatpak uninstall --{it['i']} -y org.qgis.qgis")
        elif k == "snap":
            root.append("snap remove qgis")
        elif k == "dist":
            root.append({"dnf": "dnf remove -y qgis", "zypper": "zypper --non-interactive remove qgis",
                         "pacman": "pacman -R --noconfirm qgis"}[it["pm"]])
        elif k == "data":
            path = it["path"]
            allowed = {os.path.expanduser(d) for d in USER_DATA}
            if path in allowed and path.startswith(home + os.sep):   # exact known folders only
                user.append(f"rm -rf -- {shlex.quote(path)}")
    if any(i["kind"] in ("apt", "repo") for i in items):
        if autoremove and any(i["kind"] == "apt" for i in items):
            root.append("apt-get autoremove -y")
        if any(i["kind"] == "repo" for i in items):
            root.append("apt-get update")
    steps = []
    if root:
        steps.append({"root": True, "sh": "set -u\n" + "\n".join(root) + "\n"})
    if user:
        steps.append({"root": False, "sh": "set -u\n" + "\n".join(user) + "\n"})
    return steps


def steps_text(steps):
    out = []
    for s in steps:
        out.append(t("root_note") if s["root"] else t("user_note"))
        out.append(s["sh"].rstrip())
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- GUI
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.geometry("760x720")
        self.minsize(680, 620)
        self.sys = detect()
        self.busy = False
        self.method = tk.StringVar()
        self.channel_key = "ltr"
        self.v_grass, self.v_server, self.v_python = (tk.BooleanVar(value=True), tk.BooleanVar(value=False),
                                                      tk.BooleanVar(value=True))

        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(10, 0))
        self.btn_lang = ttk.Button(top, width=10, command=self.toggle_lang)
        self.btn_lang.pack(side="right")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=12, pady=8)
        tab, rmtab, guide = ttk.Frame(self.nb), ttk.Frame(self.nb), ttk.Frame(self.nb)
        self.nb.add(tab, text="")
        self.nb.add(rmtab, text="")
        self.nb.add(guide, text="")

        self.f_sys = ttk.LabelFrame(tab)
        self.f_sys.pack(fill="x", padx=8, pady=6)
        self.lbl_sys = ttk.Label(self.f_sys, justify="left", wraplength=690)
        self.lbl_sys.pack(anchor="w", padx=8, pady=6)

        self.f_method = ttk.LabelFrame(tab)
        self.f_method.pack(fill="x", padx=8, pady=6)
        self.rb = {}
        for m in "ABC":
            self.rb[m] = ttk.Radiobutton(self.f_method, variable=self.method, value=m, command=self.sync_state)
            self.rb[m].pack(anchor="w", padx=8, pady=2)

        self.f_ver = ttk.LabelFrame(tab)
        self.f_ver.pack(fill="x", padx=8, pady=6)
        self.cmb = ttk.Combobox(self.f_ver, state="readonly")
        self.cmb.pack(fill="x", padx=8, pady=8)
        self.cmb.bind("<<ComboboxSelected>>", self.on_channel)

        self.f_pkg = ttk.LabelFrame(tab)
        self.f_pkg.pack(fill="x", padx=8, pady=6)
        self.cb_grass = ttk.Checkbutton(self.f_pkg, variable=self.v_grass)
        self.cb_python = ttk.Checkbutton(self.f_pkg, variable=self.v_python)
        self.cb_server = ttk.Checkbutton(self.f_pkg, variable=self.v_server)
        for c in (self.cb_grass, self.cb_python, self.cb_server):
            c.pack(anchor="w", padx=8, pady=1)

        bar = ttk.Frame(tab)
        bar.pack(fill="x", padx=8, pady=8)
        self.btn_inst = ttk.Button(bar, command=self.on_install)
        self.btn_inst.pack(side="left")
        self.btn_rm = ttk.Button(bar, command=lambda: (self.nb.select(1), self.rescan()))
        self.btn_rm.pack(side="left", padx=8)
        self.btn_copy = ttk.Button(bar, command=self.on_copy)
        self.btn_copy.pack(side="left")

        self.lbl_log = ttk.Label(tab)
        self.lbl_log.pack(anchor="w", padx=10)
        self.log = scrolledtext.ScrolledText(tab, height=7, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # ---- uninstall tab
        self.rm_items, self.rm_vars = [], []
        top_rm = ttk.Frame(rmtab)
        top_rm.pack(fill="x", padx=8, pady=8)
        self.btn_scan = ttk.Button(top_rm, command=self.rescan)
        self.btn_scan.pack(side="left")
        self.lbl_found = ttk.Label(rmtab, font=("", 10, "bold"))
        self.lbl_found.pack(anchor="w", padx=10)
        self.rm_box = ttk.Frame(rmtab)
        self.rm_box.pack(fill="x", padx=14, pady=4)
        self.lbl_warn = ttk.Label(rmtab, wraplength=690, foreground="#b42318", justify="left")
        self.lbl_warn.pack(anchor="w", padx=10, pady=(4, 0))
        self.f_opts = ttk.LabelFrame(rmtab)
        self.f_opts.pack(fill="x", padx=8, pady=8)
        self.v_purge, self.v_auto, self.v_next = tk.BooleanVar(value=False), tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        self.cb_purge = ttk.Checkbutton(self.f_opts, variable=self.v_purge)
        self.cb_auto = ttk.Checkbutton(self.f_opts, variable=self.v_auto)
        self.cb_next = ttk.Checkbutton(self.f_opts, variable=self.v_next)
        for c in (self.cb_purge, self.cb_auto, self.cb_next):
            c.pack(anchor="w", padx=8, pady=1)
        self.btn_rm_go = ttk.Button(rmtab, command=self.on_remove_selected)
        self.btn_rm_go.pack(anchor="w", padx=8, pady=6)

        self.txt = scrolledtext.ScrolledText(guide, wrap="word")
        self.txt.pack(fill="both", expand=True, padx=8, pady=8)

        s = self.sys
        self.method.set("A" if self.avail("A") else "B")
        self.apply_lang()
        self.rescan()

    # ---- i18n / state
    def avail(self, m):
        s = self.sys
        if m == "A":
            return s["apt"] and s["supported"] and s["arch"] == "amd64"
        if m == "B":
            return True
        return bool(s["pm"])

    def allowed_channels(self):
        return LTR_ONLY_CHANNELS if self.sys["ltr_only"] else CHANNELS

    def channel_label(self, k):
        return t("ch_" + k, v=LATEST if k == "latest" else LTR)

    def apply_lang(self):
        s = self.sys
        self.title(t("title"))
        self.btn_lang.config(text=t("lang_btn"))
        self.nb.tab(0, text=t("tab_inst"))
        self.nb.tab(1, text=t("tab_rm"))
        self.nb.tab(2, text=t("tab_guide"))
        self.btn_scan.config(text=t("rm_scan")); self.btn_rm_go.config(text=t("rm_sel"))
        self.f_opts.config(text=t("rm_opts")); self.cb_purge.config(text=t("rm_purge"))
        self.cb_auto.config(text=t("rm_auto")); self.cb_next.config(text=t("rm_next"))
        self.lbl_warn.config(text=t("rm_data_warn"))
        self.render_rm()
        for f, k in ((self.f_sys, "f_sys"), (self.f_method, "f_method"), (self.f_ver, "f_ver"), (self.f_pkg, "f_pkg")):
            f.config(text=t(k))
        for m in "ABC":
            self.rb[m].config(text=t("m" + m))
        self.cb_grass.config(text=t("p_grass"))
        self.cb_python.config(text=t("p_python"))
        self.cb_server.config(text=t("p_server"))
        self.btn_inst.config(text=t("preview"))
        self.btn_rm.config(text=t("rm_goto"))
        self.btn_copy.config(text=t("copy"))
        self.lbl_log.config(text=t("log"))

        lines = [t("sys_line", name=s["name"], code=s["code"] or "-", arch=s["arch"], pm=s["pm"] or "-")]
        if not s["family"]:
            lines.append(t("st_nodeb"))
        elif not s["supported"]:
            lines.append(t("st_unsup"))
        else:
            lines.append(t("st_ltr") if s["ltr_only"] else t("st_ok"))
        if s["family"] and s["arch"] != "amd64":
            lines.append(t("st_arch"))
        v = installed_qgis()
        lines.append(t("st_inst", v=v) if v else t("st_none"))
        self.lbl_sys.config(text="\n".join(lines))

        keys = self.allowed_channels()
        if self.channel_key not in keys:
            self.channel_key = "ltr" if s["ltr_only"] else "latest"
        self.cmb["values"] = [self.channel_label(k) for k in keys]
        self.cmb.current(keys.index(self.channel_key))

        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("end", t("guide"))
        self.txt.config(state="disabled")
        self.sync_state()

    def toggle_lang(self):
        global LANG
        LANG = "ka" if LANG == "en" else "en"
        self.apply_lang()

    def on_channel(self, _e=None):
        self.channel_key = self.allowed_channels()[self.cmb.current()]

    def sync_state(self):
        for m in "ABC":
            self.rb[m].state(["!disabled"] if self.avail(m) else ["disabled"])
        if not self.avail(self.method.get()):
            self.method.set("B")
        a = self.method.get() == "A"
        self.cmb.state(["!disabled", "readonly"] if a else ["disabled"])
        for c in (self.cb_grass, self.cb_python, self.cb_server):
            c.state(["!disabled"] if a else ["disabled"])

    # ---- helpers
    def say(self, text):
        self.log.config(state="normal")
        self.log.insert("end", str(text).rstrip("\n") + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def steps(self):
        m = self.method.get()
        pk = {"grass": self.v_grass.get(), "server": self.v_server.get(), "python": self.v_python.get()}
        return build_install(m, self.sys, self.channel_key, pk)

    def on_copy(self):
        txt = steps_text(self.steps())
        self.clipboard_clear()
        self.clipboard_append(txt)
        self.say(t("copied"))

    def on_install(self):
        self.confirm(self.steps(), t("title"))

    def rescan(self):
        self.rm_items = find_installs(self.sys)
        self.rm_vars = [tk.BooleanVar(value=(it["kind"] != "data")) for it in self.rm_items]
        self.render_rm()

    def render_rm(self):
        for w in self.rm_box.winfo_children():
            w.destroy()
        if not self.rm_items:
            self.lbl_found.config(text=t("rm_none"))
            return
        self.lbl_found.config(text=t("rm_found"))
        for it, var in zip(self.rm_items, self.rm_vars):
            ttk.Checkbutton(self.rm_box, text=label_for(it), variable=var).pack(anchor="w", pady=1)

    def on_remove_selected(self):
        chosen = [it for it, v in zip(self.rm_items, self.rm_vars) if v.get()]
        steps = build_remove_steps(chosen, self.v_purge.get(), self.v_auto.get(), self.sys)
        if not steps:
            return messagebox.showinfo(t("rm_title"), t("rm_nothing"))
        self.confirm(steps, t("rm_title"), on_success=self.after_remove)

    def after_remove(self):
        self.rescan()
        self.apply_lang()
        if self.v_next.get():
            self.nb.select(0)

    def confirm(self, steps, title, on_success=None):
        if not steps:
            return messagebox.showinfo(title, t("no_method"))
        win = tk.Toplevel(self)
        win.title(t("confirm_title"))
        win.geometry("720x520")
        ttk.Label(win, text=t("will_run"), font=("", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 4))
        box = scrolledtext.ScrolledText(win, wrap="none")
        box.pack(fill="both", expand=True, padx=10)
        box.insert("end", steps_text(steps))
        box.config(state="disabled")
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=10, pady=10)

        def go():
            win.destroy()
            self.run_steps(steps, on_success)
        ttk.Button(bar, text=t("run"), command=go).pack(side="right")
        ttk.Button(bar, text=t("cancel"), command=win.destroy).pack(side="right", padx=8)

    def run_steps(self, steps, on_success=None):
        if self.busy:
            return
        self.busy = True
        for b in (self.btn_inst, self.btn_rm, self.btn_copy, self.btn_rm_go, self.btn_scan):
            b.state(["disabled"])
        self.say(t("running"))

        def work():
            for s in steps:
                cmd = ["sh", "-c", s["sh"]]
                if s["root"] and os.geteuid() != 0:
                    cmd = ["pkexec"] + cmd
                try:
                    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                except FileNotFoundError:
                    return 127, s
                for line in p.stdout:
                    self.after(0, self.say, line)
                rc = p.wait()
                if rc != 0:
                    return rc, s
            return 0, None

        def done(res):
            rc, s = res
            self.busy = False
            for b in (self.btn_inst, self.btn_rm, self.btn_copy, self.btn_rm_go, self.btn_scan):
                b.state(["!disabled"])
            if rc == 0:
                self.say(t("done_ok"))
                self.apply_lang()
                if on_success:
                    on_success()
            elif rc in (126, 127) and s and s["root"]:
                path = os.path.join(tempfile.gettempdir(), "qgis-installer-root.sh")
                with open(path, "w") as f:
                    f.write("\n".join(x["sh"] for x in steps if x["root"]))
                msg = t("elev_fail", cmd=f"sudo sh {path}")
                self.say(msg)
                messagebox.showwarning(t("title"), msg)
            else:
                self.say(t("done_fail", rc=rc))
        threading.Thread(target=lambda: self.after(0, done, work()), daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
