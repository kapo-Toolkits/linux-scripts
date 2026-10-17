#!/usr/bin/env python3
"""Toolkit Installer — a window around ./install.sh: tick programs, choose where, click Install. English / ქართული.

It only builds and runs the same command you could type (`./install.sh --prefix … TOOL…`) and shows it first,
so nothing is hidden.  For yourself (~/.local) no password is needed; for everyone (/usr/local) the window asks for the
administrator password through pkexec.
"""
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

_here = os.path.dirname(os.path.abspath(__file__))
for _p in reversed((os.path.join(_here, "..", "common"), os.path.join(_here, "..", "lib", "linux-scripts"),
                    "/usr/local/lib/linux-scripts", "/usr/lib/linux-scripts")):   # first entry wins
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
from lscommon import detect_pm, ensure_tkinter, load_lang, save_lang  # noqa: E402
if _here not in sys.path:
    sys.path.insert(0, _here)
import extras  # noqa: E402  (programs installed from their publishers, see extras.py)
import updater  # noqa: E402  (updates from GitHub, see updater.py)

ensure_tkinter()

import tkinter as tk  # noqa: E402
from tkinter import ttk, messagebox, scrolledtext  # noqa: E402

LANG = load_lang()
ROOT = os.path.dirname(_here)                         # the linux-scripts checkout this file lives in

# id (as install.sh knows it), the commands it installs (first one decides "installed"), texts, extra weight
TOOLS = [
    {"id": "usb-eject", "cmds": ["usb-eject-gui", "usb-eject"],
     "name": {"en": "USB Safe Eject", "ka": "USB უსაფრთხო გამორთვა"},
     "info": {"en": "unmount and power off USB drives", "ka": "USB დისკის უსაფრთხო გამორთვა"}},
    {"id": "wifi-hotspot", "cmds": ["hotspot-gui", "hotspot"],
     "name": {"en": "Wi-Fi Hotspot", "ka": "Wi-Fi Hotspot"},
     "info": {"en": "hotspot, QR code, connected devices", "ka": "Hotspot, QR კოდი, მოწყობილობების სია"}},
    {"id": "printer-setup", "cmds": ["printer-setup"],
     "name": {"en": "Printer Setup", "ka": "პრინტერის დაყენება"},
     "info": {"en": "find a driver, add a printer", "ka": "დრაივერის პოვნა, პრინტერის დამატება"}},
    {"id": "qgis-installer", "cmds": ["qgis-installer", "qgis-installer-cli"],
     "name": {"en": "QGIS Installer", "ka": "QGIS-ის დაყენება"},
     "info": {"en": "install / update / remove QGIS", "ka": "QGIS-ის დაყენება, განახლება, წაშლა"}},
    {"id": "bluetooth-setup", "cmds": ["bluetooth-setup"],
     "name": {"en": "Bluetooth Setup", "ka": "Bluetooth-ის მართვა"},
     "info": {"en": "adapters, scan, pair", "ka": "ადაპტერები, ძებნა, დაწყვილება"}},
    {"id": "shortcuts", "cmds": ["toolkit-shortcuts"],
     "name": {"en": "Desktop Shortcuts", "ka": "იარლიყები სამუშაო მაგიდაზე"},
     "info": {"en": "put these programs on the Desktop", "ka": "პროგრამების დადება სამუშაო მაგიდაზე"}},
    {"id": "printhub", "cmds": ["printhub"], "heavy": True,
     "name": {"en": "PrintHub", "ka": "PrintHub"},
     "info": {"en": "print PDFs, images, Office files (downloads ~200 MB)", "ka": "PDF, სურათები, Office ფაილები (ჩამოტვირთავს ~200 MB)"}},
]

GROUP_TEXT = {"dev": "g_dev", "net": "g_net", "disk": "g_disk", "more": "g_more"}

# installed from the publisher (not by install.sh): shown in their own block, never ticked by default
EXTRAS = [
    {"id": "claude", "group": "dev",
     "name": {"en": "Claude Desktop (beta)", "ka": "Claude Desktop (ბეტა)"},
     "info": {"en": "the Claude app: Chat, Cowork, Claude Code; Ubuntu / Debian / Mint; from Anthropic's apt repository",
              "ka": "Claude-ის აპლიკაცია: Chat, Cowork, Claude Code; Ubuntu / Debian / Mint; Anthropic-ის apt რეპოზიტორიიდან"}},
    {"id": "vscode", "group": "dev",
     "name": {"en": "Visual Studio Code", "ka": "Visual Studio Code"},
     "info": {"en": "code editor; from Microsoft's apt repository (key fingerprint checked); updates via apt",
              "ka": "კოდის რედაქტორი; Microsoft-ის apt რეპოზიტორიიდან (გასაღების თითის ანაბეჭდი მოწმდება); განახლება apt-ით"}},
    {"id": "tabby", "group": "dev",
     "name": {"en": "Tabby", "ka": "Tabby"},
     "info": {"en": "terminal with SSH / serial; .deb from GitHub, SHA-256 checked (~130 MB)",
              "ka": "ტერმინალი SSH / serial-ით; .deb GitHub-იდან, SHA-256 მოწმდება (~130 MB)"}},
    {"id": "discord", "group": "net",
     "name": {"en": "Discord", "ka": "Discord"},
     "info": {"en": "chat and voice; the publisher's own .deb (no checksum is published, only HTTPS)",
              "ka": "ჩატი და ხმა; გამომცემლის საკუთარი .deb (კონტროლური ჯამი არ ქვეყნდება, მხოლოდ HTTPS)"}},
    {"id": "rustdesk", "group": "net",
     "name": {"en": "RustDesk", "ka": "RustDesk"},
     "info": {"en": "remote desktop; .deb from the project's GitHub release, SHA-256 checked",
              "ka": "დისტანციური სამუშაო მაგიდა; .deb პროექტის GitHub-იდან, SHA-256 მოწმდება"}},
    {"id": "brave", "group": "net",
     "name": {"en": "Brave Browser", "ka": "Brave Browser"},
     "info": {"en": "web browser; runs Brave's own install script (you see it first), adds Brave's repository",
              "ka": "ბრაუზერი; უშვებს Brave-ის საკუთარ ინსტალაციის სკრიპტს (წინასწარ ნახავთ), ამატებს Brave-ის რეპოზიტორიას"}},
    {"id": "etcher", "group": "disk",
     "name": {"en": "balenaEtcher", "ka": "balenaEtcher"},
     "info": {"en": "write an OS image to a USB stick / SD card (downloads ~120 MB from the publisher)",
              "ka": "OS-ის იმიჯის ჩაწერა USB ფლეშკაზე / SD ბარათზე (ჩამოტვირთავს ~120 MB გამომცემლისგან)"}},
    {"id": "brasero", "group": "disk",
     "name": {"en": "Brasero", "ka": "Brasero"},
     "info": {"en": "burn CDs and DVDs (from your distribution's repositories)",
              "ka": "CD და DVD დისკების ჩაწერა (თქვენი დისტრიბუციის რეპოზიტორიიდან)"}},
    {"id": "xfburn", "group": "disk",
     "name": {"en": "Xfburn", "ka": "Xfburn"},
     "info": {"en": "light CD/DVD burner (Xfce); from your distribution's repositories",
              "ka": "მსუბუქი CD/DVD ჩამწერი (Xfce); თქვენი დისტრიბუციის რეპოზიტორიიდან"}},
    {"id": "k3b", "group": "disk",
     "name": {"en": "K3b", "ka": "K3b"},
     "info": {"en": "full CD/DVD/Blu-ray burner (KDE, brings many KDE libraries); from your distribution's repositories",
              "ka": "სრული CD/DVD/Blu-ray ჩამწერი (KDE, ბევრ KDE ბიბლიოთეკას მოიტანს); თქვენი დისტრიბუციის რეპოზიტორიიდან"}},
    {"id": "winboat", "group": "more",
     "name": {"en": "WinBoat", "ka": "WinBoat"},
     "info": {"en": "run Windows apps on Linux (needs Docker + KVM); .deb from GitHub, SHA-256 checked (~120 MB)",
              "ka": "Windows-ის აპების გაშვება Linux-ზე (სჭირდება Docker + KVM); .deb GitHub-იდან, SHA-256 მოწმდება (~120 MB)"}},
    {"id": "artcraft", "group": "more",
     "name": {"en": "ArtCraft Launcher", "ka": "ArtCraft Launcher"},
     "info": {"en": "ArtCraft launcher; .deb from GitHub, SHA-256 checked",
              "ka": "ArtCraft-ის გამშვები; .deb GitHub-იდან, SHA-256 მოწმდება"}},
]

USER_PREFIX = os.path.join(os.path.expanduser("~"), ".local")
SYSTEM_PREFIX = "/usr/local"

STR = {
"en": {
 "title": "Toolkit Installer", "lang_btn": "ქართული", "head": "Tick the programs you want, choose where, then click Install",
 "c_name": "Program", "c_what": "What it does", "c_state": "Installed",
 "me": "for me", "all": "for everyone", "both": "both", "none": "—", "yes": "installed",
 "c_tools": "Toolkit programs",
 "f_where": "Where", "w_user": "Only for me (~/.local)", "w_user_note": "no password needed", "w_sys": "For everyone (/usr/local)", "w_sys_note": "asks for the administrator password",
 "f_opts": "Also", "o_desk": "launcher on the Desktop", "o_fold": "launchers in the program folders",
 "o_note_sys": "(only in “Only for me” mode)",
 "install": "Install selected", "uninstall": "Uninstall selected", "sel_all": "Select all", "sel_none": "Select none",
 "cmd": "Command:", "log": "Log", "nothing": "Tick at least one program first.",
 "running": "Working… do not close the window.", "done_ok": "Finished successfully.", "done_fail": "Failed (exit code {rc}). See the log.",
 "confirm_un": "Remove the selected programs ({where})?\n\n{names}", "no_pkexec": "pkexec is not available. Run this in a terminal instead:\n\n{cmd}",
 "venv": "PrintHub needs the Python ‘venv’ package (or pip), and neither is installed.\n\nInstall it first:\n\n  sudo apt install python3-venv\n\nthen click Install again.",
 "heavy": "PrintHub downloads about 200 MB (PySide6). Continue?",
 "c_other": "Other programs (from their publishers)", "looking": "Looking up the latest version…",
 "lookup_fail": "Could not look up the latest version (no internet, or GitHub is unreachable):\n{e}",
 "etcher_ask": "Install balenaEtcher {version}?\n\nDownload: {file} ({mb} MB)\nFrom: {source}\nChecked with SHA-256 before installing:\n{sha}\n\nThen installed with the system package manager (administrator password).",
 "etcher_manual": "balenaEtcher has no official package for this system here.\n\nGet it from the publisher:\n{url}",
 "gh_ask": "Install {name} {version}?\n\nDownload: {file} ({mb} MB)\nFrom: {source}\nChecked with SHA-256 before installing:\n{sha}\n\nThen installed with apt (administrator password).",
 "gh_manual": "{name} has no checked package for this system here.\n\nGet it from the project page:\n{url}",
 "vscode_ask": "Install Visual Studio Code?\n\nAdds Microsoft's apt repository. The signing key is downloaded over HTTPS and its fingerprint must be\n{fpr}\notherwise nothing is installed. Then apt installs 'code' (administrator password).",
 "discord_ask": "Install Discord?\n\nThe publisher's .deb is downloaded from {source} over HTTPS and installed with apt (administrator password).\nDiscord publishes no checksum, so only HTTPS protects this download.",
 "etcher_un": "balenaEtcher",
 "claude_ask": "Install Claude Desktop (beta)?\n\nFrom Anthropic's apt repository:\n{repo}\n\nThe signing key is downloaded and its fingerprint must equal the one Anthropic publishes:\n{fpr}\nIf it does not, nothing is installed.\n\nThen: apt install claude-desktop (administrator password).\n\n{notes}",
 "claude_manual": "Claude Desktop (beta) is published only for Debian-based Linux (Ubuntu 22.04+, Debian 12+, Linux Mint) on x86-64 / arm64.\n\nSee {url}\nOn other systems the vendor points to the Claude Code command line.",
 "settings": "Settings", "set_close": "Close", "upd_head": "Updates from GitHub",
 "upd_current": "This copy: {short} ({branch}, {date})\nFolder: {folder}", "upd_plain": "Version of this copy: not recorded yet (no link to GitHub).",
 "upd_check": "Check for updates", "upd_now": "Update now", "upd_checking": "Looking at GitHub…", "upd_none": "Up to date.",
 "upd_behind": "{n} new change(s) on GitHub:", "upd_ahead": "(this copy also has {a} change(s) that GitHub does not)",
 "upd_error": "Could not check: {e}", "upd_auto": "Check for updates when the installer starts (at most every 6 hours)",
 "upd_reinstall": "After updating, reinstall the programs I have installed (for me)",
 "upd_adopt_ask": "This folder is a plain copy. Connect it to GitHub and bring it to the latest version?\n\nFiles that git tracks here are replaced by the latest ones; other files (like start-installer.desktop) stay.",
 "upd_done": "Updated. The installer restarts now.", "upd_failed": "Not updated:\n{e}",
 "upd_unknown": "This copy's version is not known yet. {n} file(s) differ from GitHub's latest (list below; replaced files are saved first).",
 "upd_unknown_same": "This copy is identical to GitHub's latest version.",
 "upd_archive_ask": "Download the latest version from GitHub and replace the files listed?\n\nThe old copies are saved to ~/.cache/linux-scripts/update-backup/ first. Your other files stay.",
 "prog_check": "Check programs for updates", "prog_checking": "Asking GitHub about your installed programs…",
 "prog_none": "All programs installed from GitHub are up to date.", "prog_found": "{n} program(s) have a newer version:",
 "prog_fail": "Could not look up: {ids}", "prog_tick": "Tick them in the main window",
 "prog_ticked": "Ticked. Press “Install selected” in the main window to update them.",
 "g_dev": "AI and development", "g_net": "Internet and remote", "g_disk": "Disks and burning", "g_more": "More", "search": "Search:", "no_match": "Nothing matches.",
 "dup_hint": "Some programs are installed twice (for you and for everyone). To drop the system copy: tick them, choose “For everyone” and press Uninstall.",
 "data_ask": "Also delete your personal data of the program(s) you are uninstalling?\n\n{list}\n\nThis cannot be undone (settings, logins, history, downloaded data).\nNo = keep them, so a later reinstall finds everything as it was.",
 "data_done": "Personal data removed: {n} item(s).", "data_fail": "Could not remove: {p} ({e})",
 "flatpak_ask": "Install {name} as a Flatpak?\n\nFrom Flathub ({source}), id {fid}. Installed for you only, no administrator password.{extra}",
 "flatpak_need": "\n\nFlatpak itself is not installed yet: it is installed first from your distribution's repositories (administrator password).",
 "cancel": "Cancel", "cancelling": "Cancelling…", "cancelled": "Cancelled. Nothing further was run.", "downloading": "Downloading… {pct}%",
 "upd_apply": "Install updates automatically at start-up (only when nothing was changed here; the window restarts)",
 "repo_url": "Could not open a browser. The project page:\n{url}",
 "upd_nogit": "git is not installed on this computer: updating works without it (Python downloads GitHub's snapshot).",
 "upd_archive": "This copy: GitHub commit {short} (updated without git)\nFolder: {folder}",
 "upd_banner": "{n} new change(s) on GitHub", "upd_banner_plain": "This copy has not been compared with GitHub yet. Open Settings to see what is new.",
 "upd_banner_btn": "Update…", "upd_later": "Later", "upd_working": "Updating…",
 "brave_title": "Brave Browser — review the script before it runs",
 "brave_head": "Brave's official install script ({kb} KB, SHA-256 {sha}) from {url}\nwill run as the ADMINISTRATOR. Source: {src}\nIt adds Brave's package repository (signing key + source file) and installs brave-browser.",
 "brave_install": "Run it (administrator password)", "brave_cancel": "Cancel",
 "brave_fail": "Could not get Brave's install script:\n{e}",
 "pkg_ask": "Install {name} from your distribution's repositories?\n\nPackage: {pkg}  ({pm})\n(administrator password)",
 "pkg_unknown": "No known {name} package for this system's package manager ({pm}).",
 "prereq_ask": "PrintHub needs Python's venv / pip, which this computer does not have yet.\n\nInstall it now, then PrintHub, and start PrintHub?\n(asks for the administrator password; command: {cmd})",
 "prereq_run": "Installing what PrintHub needs…", "launching": "Starting PrintHub…",
 "note": "This window only runs ./install.sh for you — the command is shown above the buttons.",
},
"ka": {
 "title": "ხელსაწყოების დამყენებელი", "lang_btn": "English", "head": "მონიშნეთ პროგრამები, აირჩიეთ სად, და დააჭირეთ „დაყენებას“",
 "c_name": "პროგრამა", "c_what": "რას აკეთებს", "c_state": "დაყენებულია",
 "me": "ჩემთვის", "all": "ყველასთვის", "both": "ორივე", "none": "—", "yes": "დაყენებულია",
 "c_tools": "ხელსაწყოების პროგრამები",
 "f_where": "სად", "w_user": "მხოლოდ ჩემთვის (~/.local)", "w_user_note": "პაროლი არ სჭირდება", "w_sys": "ყველასთვის (/usr/local)", "w_sys_note": "ადმინისტრატორის პაროლს მოითხოვს",
 "f_opts": "ასევე", "o_desk": "იარლიყი სამუშაო მაგიდაზე", "o_fold": "იარლიყები საქაღალდეებში",
 "o_note_sys": "(მხოლოდ „ჩემთვის“ რეჟიმში)",
 "install": "მონიშნულის დაყენება", "uninstall": "მონიშნულის წაშლა", "sel_all": "ყველას მონიშვნა", "sel_none": "მონიშვნის მოხსნა",
 "cmd": "ბრძანება:", "log": "ლოგი", "nothing": "ჯერ მონიშნეთ ერთი პროგრამა მაინც.",
 "running": "მუშაობს… ფანჯარა არ დახუროთ.", "done_ok": "წარმატებით დასრულდა.", "done_fail": "ვერ მოხერხდა (კოდი {rc}). იხილეთ ლოგი.",
 "confirm_un": "წავშალო მონიშნული პროგრამები ({where})?\n\n{names}".replace("\\\n", "\n"),
 "no_pkexec": "pkexec არ არის. გაუშვით ტერმინალში:\n\n{cmd}".replace("\\\n", "\n"),
 "venv": "PrintHub-ს სჭირდება Python-ის ‘venv’ პაკეტი (ან pip), მაგრამ არცერთი არ არის დაყენებული.\n\nჯერ დააყენეთ:\n\n  sudo apt install python3-venv\n\nმერე ისევ დააჭირეთ „დაყენებას“.".replace("\\\n", "\n"),
 "heavy": "PrintHub-ი დაახლოებით 200 MB-ს ჩამოტვირთავს (PySide6). გავაგრძელო?",
 "c_other": "სხვა პროგრამები (გამომცემლისგან)", "looking": "ვეძებ უახლეს ვერსიას…",
 "lookup_fail": "უახლესი ვერსიის მოძებნა ვერ მოხერხდა (ინტერნეტი არ არის ან GitHub მიუწვდომელია):\n{e}",
 "etcher_ask": "დავაყენო balenaEtcher {version}?\n\nჩამოტვირთვა: {file} ({mb} MB)\nსაიდან: {source}\nდაყენებამდე შემოწმდება SHA-256-ით:\n{sha}\n\nმერე დაყენდება სისტემის პაკეტ-მენეჯერით (ადმინისტრატორის პაროლი).",
 "etcher_manual": "balenaEtcher-ს ამ სისტემისთვის ოფიციალური პაკეტი აქ არ აქვს.\n\nაიღეთ გამომცემლის გვერდიდან:\n{url}",
 "gh_ask": "დავაყენო {name} {version}?\n\nჩამოტვირთვა: {file} ({mb} MB)\nსაიდან: {source}\nდაყენებამდე შემოწმდება SHA-256-ით:\n{sha}\n\nმერე დაყენდება apt-ით (ადმინისტრატორის პაროლი).",
 "gh_manual": "{name}-ს ამ სისტემისთვის შემოწმებადი პაკეტი აქ არ აქვს.\n\nაიღეთ პროექტის გვერდიდან:\n{url}",
 "vscode_ask": "დავაყენო Visual Studio Code?\n\nემატება Microsoft-ის apt რეპოზიტორია. ხელმოწერის გასაღები ჩამოიტვირთება HTTPS-ით და მისი თითის ანაბეჭდი უნდა იყოს\n{fpr}\nსაწინააღმდეგო შემთხვევაში არაფერი დაყენდება. მერე apt დააყენებს 'code'-ს (ადმინისტრატორის პაროლი).",
 "discord_ask": "დავაყენო Discord?\n\nგამომცემლის .deb ჩამოიტვირთება {source}-დან HTTPS-ით და დაყენდება apt-ით (ადმინისტრატორის პაროლი).\nDiscord კონტროლურ ჯამს არ აქვეყნებს, ამიტომ ჩამოტვირთვას მხოლოდ HTTPS იცავს.",
 "etcher_un": "balenaEtcher",
 "claude_ask": "დავაყენო Claude Desktop (ბეტა)?\n\nAnthropic-ის apt რეპოზიტორიიდან:\n{repo}\n\nჩამოიტვირთება ხელმოწერის გასაღები და მისი თითის ანაბეჭდი უნდა ემთხვეოდეს იმას, რასაც Anthropic აქვეყნებს:\n{fpr}\nთუ არ ემთხვევა, არაფერი დაყენდება.\n\nშემდეგ: apt install claude-desktop (ადმინისტრატორის პაროლი).\n\n{notes}",
 "claude_manual": "Claude Desktop (ბეტა) ქვეყნდება მხოლოდ Debian-ზე დაფუძნებული Linux-ისთვის (Ubuntu 22.04+, Debian 12+, Linux Mint), x86-64 / arm64.\n\nიხილეთ {url}\nსხვა სისტემებისთვის მწარმოებელი Claude Code-ის ბრძანების ხაზის ვერსიას გვთავაზობს.",
 "settings": "პარამეტრები", "set_close": "დახურვა", "upd_head": "განახლებები GitHub-იდან",
 "upd_current": "ეს ასლი: {short} ({branch}, {date})\nსაქაღალდე: {folder}", "upd_plain": "ამ ასლის ვერსია ჯერ არ არის ჩაწერილი (GitHub-თან კავშირი არ აქვს).",
 "upd_check": "განახლებების შემოწმება", "upd_now": "ახლავე განახლება", "upd_checking": "ვუყურებ GitHub-ს…", "upd_none": "ყველაფერი ახალია.",
 "upd_behind": "GitHub-ზე {n} ახალი ცვლილებაა:", "upd_ahead": "(ამ ასლს {a} ისეთი ცვლილებაც აქვს, რაც GitHub-ზე არ არის)",
 "upd_error": "შემოწმება ვერ მოხერხდა: {e}", "upd_auto": "განახლებების შემოწმება ინსტალერის გახსნისას (არაუმეტეს 6 საათში ერთხელ)",
 "upd_reinstall": "განახლების შემდეგ ხელახლა დავაყენო ჩემთვის დაყენებული პროგრამები",
 "upd_adopt_ask": "ეს საქაღალდე უბრალო ასლია. მივაერთო GitHub-ს და გავაახლო ბოლო ვერსიამდე?\n\nფაილები, რასაც git აკონტროლებს, ჩანაცვლდება უახლესით; სხვა ფაილები (მაგ. start-installer.desktop) დარჩება.",
 "upd_done": "განახლდა. ინსტალერი ახლა თავიდან გაიხსნება.", "upd_failed": "ვერ განახლდა:\n{e}",
 "upd_unknown": "ამ ასლის ვერსია ჯერ უცნობია. GitHub-ის უახლესისგან {n} ფაილით განსხვავდება (სია ქვემოთაა; ჩასანაცვლებელ ფაილებს წინასწარ შევინახავ).",
 "upd_unknown_same": "ეს ასლი GitHub-ის უახლესი ვერსიის იდენტურია.",
 "upd_archive_ask": "ჩამოვტვირთო GitHub-იდან უახლესი ვერსია და ჩავანაცვლო ჩამოთვლილი ფაილები?\n\nძველი ასლები წინასწარ შეინახება ~/.cache/linux-scripts/update-backup/-ში. თქვენი სხვა ფაილები არ შეიცვლება.",
 "prog_check": "პროგრამების განახლების შემოწმება", "prog_checking": "ვეკითხები GitHub-ს თქვენს დაყენებულ პროგრამებზე…",
 "prog_none": "GitHub-იდან დაყენებული ყველა პროგრამა ახალია.", "prog_found": "{n} პროგრამას ახალი ვერსია აქვს:",
 "prog_fail": "ვერ შევამოწმე: {ids}", "prog_tick": "მონიშნეთ მთავარ ფანჯარაში",
 "prog_ticked": "მონიშნულია. განახლებისთვის მთავარ ფანჯარაში დააჭირეთ „მონიშნულის დაყენებას“.",
 "g_dev": "AI და დეველოპმენტი", "g_net": "ინტერნეტი და დისტანციური წვდომა", "g_disk": "დისკები და ჩაწერა", "g_more": "სხვა", "search": "ძებნა:", "no_match": "არაფერი ემთხვევა.",
 "dup_hint": "ზოგი პროგრამა ორჯერ არის დაყენებული (თქვენთვის და ყველასთვის). სისტემური ასლის მოსაცილებლად: მონიშნეთ ისინი, აირჩიეთ „ყველასთვის“ და დააჭირეთ წაშლას.",
 "data_ask": "წავშალო თქვენი პირადი მონაცემებიც იმ პროგრამებისა, რომლებსაც წაშლით?\n\n{list}\n\nეს ვეღარ აღდგება (პარამეტრები, ანგარიშები, ისტორია, ჩამოტვირთული მონაცემები).\nარა = დარჩება, რომ მოგვიანებით ხელახლა დაყენებისას ყველაფერი ისე დახვდეთ.",
 "data_done": "პირადი მონაცემები წაიშალა: {n}.", "data_fail": "ვერ წავშალე: {p} ({e})",
 "flatpak_ask": "დავაყენო {name} Flatpak-ად?\n\nFlathub-იდან ({source}), id {fid}. დაყენდება მხოლოდ თქვენთვის, ადმინისტრატორის პაროლის გარეშე.{extra}",
 "flatpak_need": "\n\nთვითონ Flatpak ჯერ დაყენებული არ არის: ჯერ დაყენდება თქვენი დისტრიბუციის რეპოზიტორიიდან (ადმინისტრატორის პაროლი).",
 "cancel": "გაუქმება", "cancelling": "ვაუქმებ…", "cancelled": "გაუქმდა. მეტი არაფერი გაშვებულა.", "downloading": "მიმდინარეობს ჩამოტვირთვა… {pct}%",
 "upd_apply": "განახლებების ავტომატური დაყენება გახსნისას (მხოლოდ თუ აქ არაფერია შეცვლილი; ფანჯარა თავიდან გაიხსნება)",
 "repo_url": "ბრაუზერის გახსნა ვერ მოხერხდა. პროექტის გვერდი:\n{url}",
 "upd_nogit": "ამ კომპიუტერზე git დაყენებული არ არის: განახლება მის გარეშეც მუშაობს (Python ჩამოტვირთავს GitHub-ის ასლს).",
 "upd_archive": "ეს ასლი: GitHub-ის კომიტი {short} (განახლებულია git-ის გარეშე)\nსაქაღალდე: {folder}",
 "upd_banner": "GitHub-ზე {n} ახალი ცვლილებაა", "upd_banner_plain": "ეს ასლი GitHub-თან ჯერ შედარებული არ არის. გახსენით პარამეტრები და ნახეთ, რა არის ახალი.",
 "upd_banner_btn": "განახლება…", "upd_later": "მოგვიანებით", "upd_working": "ვაახლებ…",
 "brave_title": "Brave Browser — გადახედეთ სკრიპტს გაშვებამდე",
 "brave_head": "Brave-ის ოფიციალური ინსტალაციის სკრიპტი ({kb} KB, SHA-256 {sha}) მისამართიდან {url}\nგაეშვება ადმინისტრატორის უფლებით. წყარო: {src}\nის ამატებს Brave-ის პაკეტების რეპოზიტორიას (ხელმოწერის გასაღები + წყაროს ფაილი) და აყენებს brave-browser-ს.",
 "brave_install": "გაშვება (ადმინისტრატორის პაროლი)", "brave_cancel": "გაუქმება",
 "brave_fail": "Brave-ის სკრიპტის მიღება ვერ მოხერხდა:\n{e}",
 "pkg_ask": "დავაყენო {name} თქვენი დისტრიბუციის რეპოზიტორიიდან?\n\nპაკეტი: {pkg}  ({pm})\n(ადმინისტრატორის პაროლი)",
 "pkg_unknown": "ამ სისტემის პაკეტ-მენეჯერისთვის ({pm}) {name}-ის ცნობილი პაკეტი არ არის.",
 "prereq_ask": "PrintHub-ს სჭირდება Python-ის venv / pip, რაც ამ კომპიუტერზე ჯერ არ არის.\n\nდავაყენო ახლა, მერე PrintHub და გავუშვა PrintHub?\n(ადმინისტრატორის პაროლს მოითხოვს; ბრძანება: {cmd})",
 "prereq_run": "ვაყენებ იმას, რაც PrintHub-ს სჭირდება…", "launching": "ვუშვებ PrintHub-ს…",
 "note": "ეს ფანჯარა მხოლოდ ./install.sh-ს უშვებს თქვენთვის — ბრძანება ღილაკების ზემოთ ჩანს.",
},
}


def t(k, **kw):
    s = STR[LANG][k]
    return s.format(**kw) if kw else s


# ---------------------------------------------------------------- logic (no UI, unit-tested)
def installed_where(tool, home=None, exists=os.path.exists, system_prefix=SYSTEM_PREFIX):
    """-> set of {'user', 'system'} where the tool's first command is installed."""
    home = home or os.path.expanduser("~")
    cmd = tool["cmds"][0]
    res = set()
    if exists(os.path.join(home, ".local", "bin", cmd)):
        res.add("user")
    if exists(os.path.join(system_prefix, "bin", cmd)):
        res.add("system")
    return res


def build_command(root, tool_ids, action, where, desktop=False, folders=False, home=None):
    """The exact command: ['bash', '<root>/install.sh', '--prefix', P, ('--uninstall'), ('--desktop'), ('--folders'), TOOL…].
    Desktop / folder launchers only for the user prefix (as root they would land in root's home)."""
    prefix = SYSTEM_PREFIX if where == "system" else os.path.join(home or os.path.expanduser("~"), ".local")
    cmd = ["bash", os.path.join(root, "install.sh"), "--prefix", prefix]
    if action == "uninstall":
        cmd.append("--uninstall")
    if where != "system":
        if desktop:
            cmd.append("--desktop")
        if folders:
            cmd.append("--folders")
    return cmd + list(tool_ids)


def elevate(cmd, which=shutil.which, euid=None):
    """Wrap for the administrator password: pkexec (graphical). Returns None when it is impossible."""
    euid = os.geteuid() if euid is None and hasattr(os, "geteuid") else (euid if euid is not None else 1)
    if euid == 0:
        return list(cmd)
    return ["pkexec"] + list(cmd) if which("pkexec") else None


def shell_line(cmd):
    import shlex
    return " ".join(shlex.quote(c) for c in cmd)


def shlex_quote(text):
    import shlex
    return shlex.quote(text)


def venv_ready(which=shutil.which, run=subprocess.run):
    """PrintHub's installer needs PySide6 on the system, or `python3 -m venv` (with ensurepip), or pip."""
    def ok(args):
        try:
            return run(args, capture_output=True, timeout=20).returncode == 0
        except Exception:  # noqa: BLE001
            return False
    return ok(["python3", "-c", "import PySide6"]) or ok(["python3", "-c", "import ensurepip, venv"]) \
        or ok(["python3", "-m", "pip", "--version"])


# what PrintHub needs to create its private Python environment, per package manager (all run as administrator)
PREREQ = {
    "apt-get": "apt-get install -y python3-venv || (apt-get update && apt-get install -y python3-venv)",
    "dnf": "dnf install -y python3-pip",
    "pacman": "pacman -S --noconfirm python-pip",
    "zypper": "zypper --non-interactive install python3-pip",
    "apk": "apk add py3-pip",
}


def prereq_command(pm):
    """['sh', '-c', '…'] installing venv/pip for this package manager, or None when we do not know how."""
    sh = PREREQ.get(pm)
    return ["sh", "-c", sh] if sh else None


def run_jobs(jobs, on_line, ctl=None):
    """Run commands one after another; stop at the first failure or when the user cancelled (ctl["cancel"]).
    -> exit code of the last one run (130 = cancelled)."""
    rc = 0
    for job in jobs:
        if ctl and ctl.get("cancel"):
            return 130
        rc = run_command(job, on_line, ctl)
        if rc != 0:
            return rc
    return rc


def progress_percent(line):
    """curl's --progress-bar line ('######## 45.3%') -> 45.3, anything else -> None."""
    m = re.search(r"#.*?(\d{1,3}(?:\.\d)?)%\s*$", line)
    return min(100.0, float(m.group(1))) if m else None


def tool_path(tool_id, where, home=None, exists=os.path.exists):
    """The installed launcher command of a tool for this location, or None."""
    tool = next(x for x in TOOLS if x["id"] == tool_id)
    base = os.path.join(home or os.path.expanduser("~"), ".local") if where != "system" else SYSTEM_PREFIX
    path = os.path.join(base, "bin", tool["cmds"][0])
    return path if exists(path) else None


def stop_process(p):
    """End a command and everything it started (a download is a child of the shell that runs it)."""
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        try:
            p.terminate()
        except OSError:
            pass


def run_command(cmd, on_line, ctl=None):
    """Run and stream every output line; returns the exit code (127 when it could not start, 130 when cancelled).
    ctl is the window's control dict: ctl["cancel"] stops a command that runs as the user (never one that runs through
    pkexec / sudo: killing only the wrapper would leave the administrator's command running half-way)."""
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=ROOT, start_new_session=True)
    except OSError:
        return 127
    if ctl is not None:
        ctl["proc"], ctl["elevated"] = p, os.path.basename(cmd[0]) in ("pkexec", "sudo")
    cancelled = False
    with p:
        for line in p.stdout:
            on_line(line)
            if ctl and ctl.get("cancel") and not ctl.get("elevated") and not cancelled:
                cancelled = True
                stop_process(p)
    rc = p.wait()
    if ctl is not None:
        ctl["proc"] = None
    return 130 if (cancelled or (ctl and ctl.get("cancel") and not ctl.get("elevated") and rc != 0)) else rc


def banner_for(res, settings, now):
    """What the quiet start-up check shows on top of the window: ('behind', n) when GitHub has newer work, ('plain', None) for a
    copied folder that is not linked to GitHub (unless snoozed with "Later"), else None."""
    if not res or res.get("mode") == "error":
        return None
    if res["mode"] in ("git", "archive"):
        if res["mode"] == "archive" and res.get("behind") is None:      # commit unknown (first time without git)
            return ("plain", None) if float(settings.get("update_snooze_until", 0) or 0) <= now else None
        return ("behind", res["behind"]) if res.get("behind") else None
    if res["mode"] == "adopt" and float(settings.get("update_snooze_until", 0) or 0) <= now:
        return ("plain", None)
    return None


def should_auto_apply(res, settings):
    """Automatic updating is opt-in and only for the clear cases: a git checkout with nothing changed locally, or a copy whose
    GitHub commit is known (archive mode). Never for an unknown version (the user must see the file list first)."""
    if not settings.get("auto_apply_update", False) or not res or not res.get("behind"):
        return False
    if res["mode"] == "git":
        return not res["local"].get("dirty") and not res.get("ahead")
    return res["mode"] == "archive"


def reinstall_ids(tools, installed_fn):
    """The programs the user has installed for themselves (~/.local): after an update these get the new version."""
    return [x["id"] for x in tools if "user" in installed_fn(x)]


def fit_geometry(screen_w, screen_h, want_w=1040, want_h=600):
    """-> (width, height, min_width, min_height): the wanted size, shrunk to leave room on a small screen
    (panel, window frame), never below a size where the three columns still read."""
    w, h = min(want_w, screen_w - 30), min(want_h, screen_h - 80)
    return w, h, min(760, w), min(470, h)


def launcher_text(root):
    """A double-click launcher for this window, placed in the checkout's top folder (absolute paths: %k does not work).
    It goes through installer/start.sh, which shows a message window when the installer cannot start; `sh` means no
    executable bit is needed, so it also works from a copied or unzipped folder."""
    return "\n".join([
        "[Desktop Entry]", "Type=Application",
        "Name=Install apps (Toolkit Installer)", "Name[ka]=პროგრამების დაყენება (ხელსაწყოების დამყენებელი)",
        "Comment=Tick programs and install them with one click · მონიშნეთ პროგრამები და დააყენეთ",
        f'Exec=sh "{os.path.join(root, "installer", "start.sh")}"', f"Path={root}",
        "Icon=system-software-install", "Terminal=false", "Categories=System;Utility;", ""])


def make_launcher(root=ROOT):
    """Write <checkout>/start-installer.desktop (executable, trusted) and return its path."""
    path = os.path.join(root, "start-installer.desktop")
    with open(path, "w") as f:
        f.write(launcher_text(root))
    os.chmod(path, 0o755)
    if shutil.which("gio"):
        subprocess.run(["gio", "set", path, "metadata::trusted", "true"], capture_output=True)
    return path


# ---------------------------------------------------------------- GUI
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        w, h, mw, mh = fit_geometry(self.winfo_screenwidth(), self.winfo_screenheight())
        self.geometry(f"{w}x{h}")
        self.minsize(mw, mh)
        self.wrap = max(150, (w - 40) // 3 - 80)          # width of the grey description lines
        self.busy = False
        self.vars = {x["id"]: tk.BooleanVar(value=not x.get("heavy")) for x in TOOLS}
        self.extra_vars = {x["id"]: tk.BooleanVar(value=False) for x in EXTRAS}
        self.where = tk.StringVar(value="user")
        self.v_desk, self.v_fold = tk.BooleanVar(value=True), tk.BooleanVar(value=False)

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=(8, 2))
        self.lbl_head = ttk.Label(top, font=("", 11, "bold"), wraplength=max(300, w - 160), justify="left")
        self.lbl_head.pack(side="left")
        self.btn_lang = ttk.Button(top, width=9, command=self.toggle_lang)
        self.btn_lang.pack(side="right")
        self.btn_set = ttk.Button(top, width=3, text="⚙", command=self.open_settings)
        self.btn_set.pack(side="right", padx=(0, 6))
        self.top = top
        self.banner = ttk.Frame(self)                           # shown only when GitHub has something new (see start_quiet_check)
        self.lbl_banner = ttk.Label(self.banner, foreground="#1a5fb4", font=("", 9, "bold"))
        self.lbl_banner.pack(side="left", padx=(12, 8))
        self.btn_banner = ttk.Button(self.banner, command=self.open_settings)
        self.btn_banner.pack(side="left")
        self.btn_later = ttk.Button(self.banner, command=self.snooze_banner)
        self.btn_later.pack(side="left", padx=6)

        # three columns side by side: toolkit programs | other programs | where, options, buttons
        main = ttk.Frame(self)
        main.pack(fill="x", padx=8)
        main.columnconfigure(0, weight=5, uniform="col")
        main.columnconfigure(1, weight=5, uniform="col")
        main.columnconfigure(2, weight=5, uniform="col")
        self.f_tools = ttk.LabelFrame(main)
        self.f_tools.grid(row=0, column=0, sticky="nsew", padx=3, pady=3)
        self.f_extra_box = ttk.LabelFrame(main)                 # the publisher's programs: a scrolling list, so a long one
        self.f_extra_box.grid(row=0, column=1, sticky="nsew", padx=3, pady=3)   # never makes the window taller than the screen
        self.v_search = tk.StringVar()
        row_s = ttk.Frame(self.f_extra_box)
        row_s.pack(side="top", fill="x", padx=4, pady=(2, 0))
        self.lbl_search = ttk.Label(row_s, font=("", 8))
        self.lbl_search.pack(side="left")
        ttk.Entry(row_s, textvariable=self.v_search).pack(side="left", fill="x", expand=True, padx=4)
        self.v_search.trace_add("write", lambda *_: self.render())
        self.cv_extra = tk.Canvas(self.f_extra_box, highlightthickness=0, width=200, height=300)
        sb = ttk.Scrollbar(self.f_extra_box, orient="vertical", command=self.cv_extra.yview)
        self.cv_extra.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.cv_extra.pack(side="left", fill="both", expand=True)
        self.f_extra = ttk.Frame(self.cv_extra)
        win_id = self.cv_extra.create_window((0, 0), window=self.f_extra, anchor="nw")
        self.f_extra.bind("<Configure>", lambda e: self.cv_extra.configure(scrollregion=self.cv_extra.bbox("all")))
        self.cv_extra.bind("<Configure>", lambda e: self.cv_extra.itemconfigure(win_id, width=e.width))
        for seq, d in (("<Button-4>", -1), ("<Button-5>", 1), ("<MouseWheel>", None)):
            self.cv_extra.bind_all(seq, lambda e, d=d: self.wheel_extra(e, d), add="+")
        side = ttk.Frame(main)
        side.grid(row=0, column=2, sticky="nsew", padx=3, pady=3)
        self.box = self.f_tools                                 # kept for older callers

        self.f_where = ttk.LabelFrame(side)
        self.f_where.pack(fill="x")
        self.rb_user = ttk.Radiobutton(self.f_where, variable=self.where, value="user", command=self.sync)
        self.rb_sys = ttk.Radiobutton(self.f_where, variable=self.where, value="system", command=self.sync)
        self.note_user = ttk.Label(self.f_where, foreground="#777777", font=("", 8), wraplength=250, justify="left")
        self.note_sys = ttk.Label(self.f_where, foreground="#777777", font=("", 8), wraplength=250, justify="left")
        self.rb_user.pack(anchor="w", padx=6, pady=(2, 0))
        self.note_user.pack(anchor="w", padx=26)
        self.rb_sys.pack(anchor="w", padx=6, pady=(4, 0))
        self.note_sys.pack(anchor="w", padx=26, pady=(0, 2))

        self.f_opts = ttk.LabelFrame(side)
        self.f_opts.pack(fill="x", pady=(4, 0))
        self.cb_desk = ttk.Checkbutton(self.f_opts, variable=self.v_desk, command=self.sync)
        self.cb_fold = ttk.Checkbutton(self.f_opts, variable=self.v_fold, command=self.sync)
        self.cb_desk.pack(anchor="w", padx=6, pady=0)
        self.cb_fold.pack(anchor="w", padx=6, pady=0)
        self.lbl_optnote = ttk.Label(self.f_opts, foreground="#777777", wraplength=200, justify="left")
        self.lbl_optnote.pack(anchor="w", padx=6)

        self.b_inst = ttk.Button(side, command=lambda: self.go("install"))
        self.b_un = ttk.Button(side, command=lambda: self.go("uninstall"))
        self.b_all = ttk.Button(side, command=lambda: self.pick(True))
        self.b_none = ttk.Button(side, command=lambda: self.pick(False))
        self.b_inst.pack(fill="x", pady=(6, 1))
        self.b_un.pack(fill="x", pady=1)
        self.b_all.pack(fill="x", pady=1)
        self.b_none.pack(fill="x", pady=1)

        self.lbl_cmd = ttk.Label(self, wraplength=w - 30, justify="left", foreground="#555555", font=("TkFixedFont", 8))
        self.lbl_cmd.pack(anchor="w", padx=12, pady=(2, 0))
        self.lbl_dup = ttk.Label(self, foreground="#a15c00", font=("", 8), wraplength=w - 30, justify="left")
        self.lbl_dup.pack(anchor="w", padx=12)
        self.lbl_log = ttk.Label(self)                           # (heading kept for older callers; the log has no caption)
        # the status line is packed first, from the bottom, so a small window shortens the log and never cuts the status
        self.lbl_status = ttk.Label(self, foreground="#555555", wraplength=w - 30)
        self.lbl_status.pack(side="bottom", anchor="w", padx=12, pady=(0, 6))
        self.runbar = ttk.Frame(self)                            # shown only while something runs: progress + cancel
        self.prog = ttk.Progressbar(self.runbar, mode="indeterminate")
        self.prog.pack(side="left", fill="x", expand=True)
        self.b_cancel = ttk.Button(self.runbar, command=self.cancel_run)
        self.b_cancel.pack(side="left", padx=(8, 0))
        self.run_ctl = {}
        self.log = scrolledtext.ScrolledText(self, height=2, state="disabled", wrap="word", font=("TkFixedFont", 9))
        self.log.pack(fill="both", expand=True, padx=10, pady=(2, 2))
        self.apply_lang()
        self.after(1500, self.start_quiet_check)

    # ---- UI helpers
    def apply_lang(self):
        self.title(t("title"))
        self.lbl_head.config(text=t("head"))
        self.btn_lang.config(text=t("lang_btn"))
        self.btn_banner.config(text=t("upd_banner_btn"))
        self.btn_later.config(text=t("upd_later"))
        self.f_tools.config(text=t("c_tools"))
        self.f_extra_box.config(text=t("c_other"))
        self.lbl_search.config(text=t("search"))
        self.b_cancel.config(text=t("cancel"))
        self.f_where.config(text=t("f_where"))
        self.rb_user.config(text=t("w_user"))
        self.rb_sys.config(text=t("w_sys"))
        self.note_user.config(text=t("w_user_note"))
        self.note_sys.config(text=t("w_sys_note"))
        self.f_opts.config(text=t("f_opts"))
        self.cb_desk.config(text=t("o_desk"))
        self.cb_fold.config(text=t("o_fold"))
        self.b_inst.config(text=t("install"))
        self.b_un.config(text=t("uninstall"))
        self.b_all.config(text=t("sel_all"))
        self.b_none.config(text=t("sel_none"))
        self.lbl_status.config(text=t("note"))
        self.render()
        self.sync()

    def wheel_extra(self, e, d):
        """Mouse wheel scrolls the list of other programs while the pointer is over it."""
        w = self.winfo_containing(e.x_root, e.y_root)
        while w is not None and w is not self.cv_extra:
            w = w.master
        if w is self.cv_extra:
            self.cv_extra.yview_scroll(d if d is not None else (-1 if e.delta > 0 else 1), "units")

    def fit_extra(self):
        """The list is as tall as the toolkit column next to it (it scrolls when it has more)."""
        self.update_idletasks()
        self.cv_extra.configure(height=max(200, self.f_tools.winfo_reqheight() - 24))

    def item_row(self, parent, base, var, title, info, state, good):
        """Two lines per program: [checkbox] name ... state / grey description. Narrow enough for three columns."""
        parent.columnconfigure(0, weight=1)
        ttk.Checkbutton(parent, text=title, variable=var, command=self.sync).grid(row=base, column=0, sticky="w", padx=(4, 0))
        ttk.Label(parent, text=state, foreground="#1a7f37" if good else "#888888", font=("", 8)).grid(
            row=base, column=1, sticky="e", padx=(4, 6))
        ttk.Label(parent, text=info, foreground="#666666", font=("", 8), wraplength=self.wrap, justify="left").grid(
            row=base + 1, column=0, columnspan=2, sticky="w", padx=(24, 4), pady=(0, 2))

    def ex_native_state(self, ex_id):
        """Installed through the system (apt / dnf ...): the version or 'yes', else None."""
        if ex_id == "etcher":
            return extras.etcher_installed()
        if ex_id == "brave":
            return t("yes") if extras.brave_installed() else None
        if ex_id == "claude":
            return t("yes") if extras.claude_installed() else None
        if ex_id == "vscode":
            return t("yes") if extras.deb_installed("code", "code") else None
        if ex_id == "discord":
            return t("yes") if extras.deb_installed("discord", "discord") else None
        if ex_id in extras.GITHUB_APPS:
            g = extras.GITHUB_APPS[ex_id]
            return t("yes") if extras.deb_installed(g["package"], g["cmd"]) else None
        return t("yes") if extras.package_installed(ex_id) else None

    def ex_state(self, ex_id):
        """What the list shows: installed natively, or as a Flatpak."""
        return self.ex_native_state(ex_id) or (t("yes") if extras.flatpak_scopes(ex_id) else None)

    def flatpak_jobs(self, action, ex_id):
        """Flatpak route for programs whose .deb / apt repository does not apply here, and removal of a flatpak install.
        -> (handled, jobs): handled False means 'use the normal route'; jobs None means cancelled / impossible."""
        import platform
        if ex_id not in extras.FLATPAK_IDS:
            return False, []
        name = next(x["name"][LANG] for x in EXTRAS if x["id"] == ex_id)
        pm = detect_pm()
        if action == "uninstall":
            scopes = extras.flatpak_scopes(ex_id)
            if not scopes:
                return False, []
            steps, _info = extras.flatpak_steps(ex_id, pm, True, remove_scopes=scopes)
            jobs = self.steps_to_jobs(steps)
            if jobs is None:
                return True, None
            if self.ex_native_state(ex_id):                           # installed both ways: take both away
                return False, jobs
            return True, jobs
        if pm == "apt-get" and platform.machine() in ("amd64", "x86_64", "arm64", "aarch64"):
            return False, []
        steps, info = extras.flatpak_steps(ex_id, pm, bool(shutil.which("flatpak")))
        if not steps:
            messagebox.showinfo(t("title"), t("gh_manual", name=name, url=info["manual"]))
            return True, None
        if not messagebox.askyesno(t("title"), t("flatpak_ask", name=name, fid=info["id"], source=info["source"],
                                                  extra=t("flatpak_need") if info["needs_flatpak"] else "")):
            return True, None
        return True, self.steps_to_jobs(steps)

    def render(self):
        for frame in (self.f_tools, self.f_extra):
            for w in frame.winfo_children():
                w.destroy()
        for r, tool in enumerate(TOOLS):
            where = installed_where(tool)
            state = t("both") if where == {"user", "system"} else t("me") if where == {"user"} else t("all") if where else t("none")
            self.item_row(self.f_tools, 2 * r, self.vars[tool["id"]], tool["name"][LANG], tool["info"][LANG], state, bool(where))
        needle = self.v_search.get().strip().lower()
        row, shown_group, hits = 0, None, 0
        for ex in EXTRAS:
            if needle and needle not in (ex["name"][LANG] + " " + ex["info"][LANG] + " " + ex["id"]).lower():
                continue
            if ex["group"] != shown_group:                                  # a heading whenever the group changes
                shown_group = ex["group"]
                ttk.Label(self.f_extra, text=t(GROUP_TEXT[shown_group]), font=("", 9, "bold"), foreground="#444444").grid(
                    row=row, column=0, columnspan=2, sticky="w", padx=4, pady=(6, 0))
                row += 1
            ver = self.ex_state(ex["id"])
            self.item_row(self.f_extra, row, self.extra_vars[ex["id"]], ex["name"][LANG], ex["info"][LANG], ver or t("none"), bool(ver))
            row += 2
            hits += 1
        if not hits:
            ttk.Label(self.f_extra, text=t("no_match"), foreground="#888888").grid(row=0, column=0, padx=8, pady=8)
        both = [x for x in TOOLS if installed_where(x) == {"user", "system"}]
        self.lbl_dup.config(text=t("dup_hint") if both else "")
        self.fit_extra()

    def sync(self):
        system = self.where.get() == "system"
        for cb in (self.cb_desk, self.cb_fold):
            cb.state(["disabled"] if system else ["!disabled"])
        self.lbl_optnote.config(text=t("o_note_sys") if system else "")
        ids = self.selected_ids()
        shown = shell_line(build_command(ROOT, ids or ["…"], "install", self.where.get(),
                                         self.v_desk.get(), self.v_fold.get())) if ids or not self.selected_extras() else ""
        for ex_id in self.selected_extras():
            note = ("balenaEtcher: curl (HTTPS) → sha256sum -c → apt/dnf install (shown in full before it runs)" if ex_id == "etcher"
                    else "Brave: download Brave's install script (HTTPS), show it, run it as administrator after you agree" if ex_id == "brave"
                    else "Claude Desktop: Anthropic's apt repository, key fingerprint checked, apt install claude-desktop" if ex_id == "claude"
                    else "Visual Studio Code: Microsoft's apt repository, key fingerprint checked, apt install code" if ex_id == "vscode"
                    else "Discord: the publisher's .deb over HTTPS (no checksum published), apt install" if ex_id == "discord"
                    else f"{ex_id}: GitHub release .deb over HTTPS → sha256sum -c → apt install" if ex_id in extras.GITHUB_APPS
                    else f"{ex_id}: the distribution's package manager (install {extras.package_name(ex_id, detect_pm()) or ex_id})")
            shown = (shown + "\n" if shown else "") + note
        self.lbl_cmd.config(text=shown)

    def toggle_lang(self):
        global LANG
        LANG = "ka" if LANG == "en" else "en"
        save_lang(LANG)
        self.apply_lang()

    def pick(self, value):
        for v in self.vars.values():
            v.set(value)
        for v in self.extra_vars.values():
            v.set(False)                          # the publisher's programs are never ticked by "select all"
        self.sync()

    def selected_ids(self):
        return [x["id"] for x in TOOLS if self.vars[x["id"]].get()]

    def selected_extras(self):
        return [x["id"] for x in EXTRAS if self.extra_vars[x["id"]].get()]

    def say(self, text):
        self.log.config(state="normal")
        self.log.insert("end", str(text).rstrip("\n") + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # ---- run
    def go(self, action):
        if self.busy:
            return
        ids = self.selected_ids()
        extra_ids = self.selected_extras()
        if not ids and not extra_ids:
            return messagebox.showinfo(t("title"), t("nothing"))
        system = self.where.get() == "system"
        names = "\n".join("• " + x["name"][LANG] for x in TOOLS if x["id"] in ids)
        for ex in EXTRAS:
            if ex["id"] in extra_ids:
                names += ("\n" if names else "") + "• " + ex["name"][LANG]
        if action == "uninstall" and not messagebox.askyesno(
                t("title"), t("confirm_un", where=t("w_sys" if system else "w_user").split("\n")[0], names=names)):
            return
        prereq = None
        if action == "install" and "printhub" in ids:
            if not venv_ready():
                pc = prereq_command(detect_pm())
                if pc is None:
                    return messagebox.showwarning(t("title"), t("venv"))
                if not messagebox.askyesno(t("title"), t("prereq_ask", cmd=pc[-1])):
                    return
                prereq = elevate(pc)
                if prereq is None:
                    return messagebox.showwarning(t("title"), t("no_pkexec", cmd="sudo " + shell_line(pc)))
            elif not messagebox.askyesno(t("title"), t("heavy")):
                return
        extra_jobs = []
        for ex_id in extra_ids:
            handled, fp_jobs = self.flatpak_jobs(action, ex_id)
            if fp_jobs is None:
                return
            if handled:
                extra_jobs += fp_jobs
                continue
            jobs_for = (self.etcher_jobs(action) if ex_id == "etcher" else
                        self.brave_jobs(action) if ex_id == "brave" else
                        self.claude_jobs(action) if ex_id == "claude" else
                        self.vscode_jobs(action) if ex_id == "vscode" else
                        self.discord_jobs(action) if ex_id == "discord" else
                        self.github_jobs(action, ex_id) if ex_id in extras.GITHUB_APPS else self.package_jobs(action, ex_id))
            if jobs_for is None:
                return
            extra_jobs += fp_jobs + jobs_for
        self.pending_data = None
        if action == "uninstall" and extra_ids:                       # asked on its own, default "no": this cannot be undone
            found = extras.data_paths(extra_ids)
            if found:
                listing = "\n".join(f"• {p}  ({max(1, round(n / 1048576))} MB)" for p, n in found[:12]) + (
                    f"\n… (+{len(found) - 12})" if len(found) > 12 else "")
                if messagebox.askyesno(t("title"), t("data_ask", list=listing), default="no"):
                    self.pending_data = [p for p, _n in found]
        cmd, shown = None, ""
        if ids:
            cmd = build_command(ROOT, ids, action, self.where.get(), self.v_desk.get(), self.v_fold.get())
            shown = shell_line(cmd)
            if system:
                cmd = elevate(cmd)
                if cmd is None:
                    return messagebox.showwarning(t("title"), t("no_pkexec", cmd="sudo " + shown))
        jobs = ([prereq] if prereq else []) + ([cmd] if cmd else []) + extra_jobs
        self.start_printhub = action == "install" and "printhub" in ids
        self.busy = True
        for b in (self.b_inst, self.b_un):
            b.state(["disabled"])
        self.lbl_status.config(text=t("running"))
        if prereq:
            self.say("$ " + shell_line(prereq))
            self.say(t("prereq_run"))
        if shown:
            self.say("$ " + shown)

        def to_ui(fn, *a):
            try:
                self.after(0, fn, *a)
            except (RuntimeError, tk.TclError):       # the window was closed while the install was still running
                pass

        self.run_ctl = {"cancel": False}
        self.runbar.pack(side="bottom", fill="x", padx=10, pady=(0, 2), before=self.lbl_status)
        self.prog.config(mode="indeterminate")
        self.prog.start(12)

        def on_line(ln):
            pct = progress_percent(ln)
            if pct is None:
                to_ui(self.say, ln)
            else:
                to_ui(self.show_progress, pct)

        def work():
            rc = run_jobs(jobs, on_line, self.run_ctl)
            to_ui(self.finish, rc)
        threading.Thread(target=work, daemon=True).start()

    def show_progress(self, pct):
        """A download is running: the bar becomes a percentage."""
        self.prog.stop()
        self.prog.config(mode="determinate", value=pct)
        self.lbl_status.config(text=t("downloading", pct=round(pct)))

    def cancel_run(self):
        """Stop at once what runs as the user (a download), and before the next step; an administrator step in progress
        is allowed to finish (it is never killed half-way)."""
        self.run_ctl["cancel"] = True
        self.b_cancel.state(["disabled"])
        self.lbl_status.config(text=t("cancelling"))
        proc = self.run_ctl.get("proc")
        if proc and not self.run_ctl.get("elevated"):
            stop_process(proc)

    def confirm_script(self, info):
        """Show the downloaded script in full and ask. True = run it. (A window of its own: nothing runs unseen.)"""
        win = tk.Toplevel(self)
        win.title(t("brave_title"))
        win.geometry("760x560")
        win.transient(self)
        ttk.Label(win, wraplength=720, justify="left", font=("", 9, "bold"),
                  text=t("brave_head", kb=max(1, round(info["bytes"] / 1024)), sha=info["sha256"],
                         url=extras.BRAVE_SCRIPT_URL, src=extras.BRAVE_SOURCE)).pack(anchor="w", padx=10, pady=(10, 4))
        box = scrolledtext.ScrolledText(win, wrap="none", font=("TkFixedFont", 9))
        box.pack(fill="both", expand=True, padx=10)
        box.insert("end", info["text"])
        box.config(state="disabled")
        answer = {"ok": False}
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=10, pady=10)

        def go():
            answer["ok"] = True
            win.destroy()
        ttk.Button(bar, text=t("brave_install"), command=go).pack(side="right")
        ttk.Button(bar, text=t("brave_cancel"), command=win.destroy).pack(side="right", padx=8)
        win.grab_set()
        self.wait_window(win)
        return answer["ok"]

    def brave_jobs(self, action):
        """Brave: remove through the package manager, or download the vendor's script, show it, run it as administrator."""
        pm = detect_pm()
        if action == "uninstall":
            steps = extras.brave_remove_steps(pm)
            if not steps:
                messagebox.showinfo(t("title"), t("pkg_unknown", name="Brave", pm=pm or "?"))
                return None
        else:
            self.lbl_status.config(text=t("looking"))
            self.update_idletasks()
            try:
                info = extras.brave_fetch_script()
            except Exception as e:  # noqa: BLE001 - offline, changed URL, an error page: say it, do not run anything
                self.lbl_status.config(text=t("note"))
                messagebox.showwarning(t("title"), t("brave_fail", e=e))
                return None
            self.lbl_status.config(text=t("note"))
            if not self.confirm_script(info):
                return None
            import tempfile
            d = os.path.join(os.path.expanduser("~"), ".cache", "linux-scripts", "downloads")
            os.makedirs(d, exist_ok=True)
            fd, path = tempfile.mkstemp(prefix="brave-install-", suffix=".sh", dir=d)
            with os.fdopen(fd, "w") as f:
                f.write(info["text"])                  # exactly the text that was shown
            os.chmod(path, 0o644)
            steps = extras.brave_steps(path)
        jobs = []
        for st in steps:
            job = ["sh", "-c", st["sh"]]
            if st["root"]:
                job = elevate(job)
                if job is None:
                    messagebox.showwarning(t("title"), t("no_pkexec", cmd="sudo sh -c " + shlex_quote(st["sh"])))
                    return None
            jobs.append(job)
        return jobs

    def claude_jobs(self, action):
        """Claude Desktop: Anthropic's apt repository (Debian-based only), the key fingerprint is checked inside the script."""
        import platform
        pm = detect_pm()
        if action == "uninstall":
            steps = extras.claude_remove_steps(pm)
            if not steps:
                messagebox.showinfo(t("title"), t("claude_manual", url=extras.CLAUDE_PAGE))
                return None
        else:
            steps, info = extras.claude_steps(pm, platform.machine())
            if not steps:
                messagebox.showinfo(t("title"), t("claude_manual", url=info["manual"]))
                return None
            if not messagebox.askyesno(t("title"), t("claude_ask", repo=info["repo"], fpr=info["fingerprint"],
                                                      notes=extras.CLAUDE_NOTES)):
                return None
        jobs = []
        for st in steps:
            job = elevate(["sh", "-c", st["sh"]])
            if job is None:
                messagebox.showwarning(t("title"), t("no_pkexec", cmd="sudo sh -c " + shlex_quote(st["sh"])))
                return None
            jobs.append(job)
        return jobs

    # ---- updates from GitHub (Settings; a quiet check at start)
    def ui(self, fn, *a):
        try:
            self.after(0, fn, *a)
        except (RuntimeError, tk.TclError):          # the window was closed meanwhile
            pass

    def start_quiet_check(self):
        """Once the window is up: look at GitHub in the background (at most every few hours) and show a banner if there is news."""
        if not os.path.isfile(os.path.join(ROOT, "install.sh")):
            return
        settings = updater.load_settings()
        if not updater.should_check(settings):
            return

        def work():
            res = updater.check(ROOT)
            st = updater.load_settings()
            st["last_update_check"] = time.time()
            updater.save_settings(st)
            found = banner_for(res, st, time.time())
            if found and found[0] == "behind" and should_auto_apply(res, st):
                self.ui(self.auto_apply, res, st.get("reinstall_after_update", True))
            elif found:
                self.ui(self.show_banner, found)
        threading.Thread(target=work, daemon=True).start()

    def auto_apply(self, res, reinstall):
        """The user switched on 'install updates automatically': bring the toolkit up to date now (the window restarts)."""
        if self.busy:
            return self.show_banner(("behind", res["behind"]))
        self.busy = True
        self.lbl_status.config(text=t("upd_working"))
        threading.Thread(target=self.do_update, args=(res, reinstall), daemon=True).start()

    def show_banner(self, found):
        kind, n = found
        self.lbl_banner.config(text=t("upd_banner", n=n) if kind == "behind" else t("upd_banner_plain"))
        self.banner.pack(fill="x", after=self.top, pady=(0, 2))

    def snooze_banner(self):
        st = updater.load_settings()
        st["update_snooze_until"] = time.time() + 7 * 86400
        updater.save_settings(st)
        self.banner.pack_forget()

    def open_settings(self):
        win = tk.Toplevel(self)
        win.title(t("settings"))
        win.geometry("580x600")
        win.transient(self)
        ttk.Label(win, text=t("upd_head"), font=("", 11, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        lbl_cur = ttk.Label(win, justify="left", wraplength=520)
        lbl_cur.pack(anchor="w", padx=12)
        lbl_res = ttk.Label(win, justify="left", wraplength=520, foreground="#1a5fb4")
        lbl_res.pack(anchor="w", padx=12, pady=(6, 2))
        box = scrolledtext.ScrolledText(win, height=9, wrap="word", state="disabled", font=("TkFixedFont", 9))
        box.pack(fill="both", expand=True, padx=12, pady=4)
        settings = updater.load_settings()
        v_auto = tk.BooleanVar(value=settings.get("auto_update_check", True))
        v_re = tk.BooleanVar(value=settings.get("reinstall_after_update", True))
        v_apply = tk.BooleanVar(value=settings.get("auto_apply_update", False))

        def persist():
            st = updater.load_settings()
            st["auto_update_check"], st["reinstall_after_update"] = v_auto.get(), v_re.get()
            st["auto_apply_update"] = v_apply.get()
            updater.save_settings(st)
        ttk.Checkbutton(win, text=t("upd_auto"), variable=v_auto, command=persist).pack(anchor="w", padx=12)
        ttk.Checkbutton(win, text=t("upd_reinstall"), variable=v_re, command=persist).pack(anchor="w", padx=12)
        ttk.Checkbutton(win, text=t("upd_apply"), variable=v_apply, command=persist).pack(anchor="w", padx=12)
        ttk.Button(win, text="GitHub ↗  " + updater.REPO_PAGE.split("://", 1)[1], command=self.open_repo).pack(anchor="w", padx=12, pady=(6, 0))
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=12, pady=(10, 4))
        b_check = ttk.Button(bar, text=t("upd_check"))
        b_now = ttk.Button(bar, text=t("upd_now"), state="disabled")
        b_check.pack(side="left")
        b_now.pack(side="left", padx=8)
        bar2 = ttk.Frame(win)
        bar2.pack(fill="x", padx=12)
        b_prog = ttk.Button(bar2, text=t("prog_check"))
        b_tick = ttk.Button(bar2, text=t("prog_tick"), state="disabled")
        b_prog.pack(side="left")
        b_tick.pack(side="left", padx=8)
        ttk.Button(bar, text=t("set_close"), command=win.destroy).pack(side="right")
        state = {"res": None}

        def show(res):
            state["res"] = res
            info = res.get("local", {})
            lbl_cur.config(text=t("upd_current", short=info.get("short", "?"), branch=info.get("branch", "?"),
                                  date=info.get("date", "?"), folder=ROOT) if info.get("git") else
                           (t("upd_nogit") + "\n" if info.get("git_missing") else "") +
                           (t("upd_archive", short=info["short"], folder=ROOT) if info.get("short") else t("upd_plain") + "\n" + ROOT))
            lines, can = [], False
            if res["mode"] == "error":
                lbl_res.config(text=t("upd_error", e=res["error"]))
            elif res["mode"] == "archive" and res["behind"] is None and res.get("files") is not None:
                lines = [("~ " if k == "changed" else "+ ") + path for k, path in res["files"]]
                lbl_res.config(text=t("upd_unknown", n=len(lines)) if lines else t("upd_unknown_same"))
                can = True
            elif res["mode"] == "adopt" or (res["mode"] == "archive" and res["behind"] is None):
                lbl_res.config(text=t("upd_banner_plain"))
                can = True
            elif res["behind"]:
                lbl_res.config(text=t("upd_behind", n=res["behind"]) + (" " + t("upd_ahead", a=res["ahead"]) if res.get("ahead") else ""))
                lines = [f"{sha}  {title}" for sha, title in res["commits"]]
                can = True
            else:
                lbl_res.config(text=t("upd_none"))
            box.config(state="normal")
            box.delete("1.0", "end")
            box.insert("end", "\n".join(lines))
            box.config(state="disabled")
            b_now.config(state="normal" if can else "disabled")
            b_check.config(state="normal")

        def do_check():
            lbl_res.config(text=t("upd_checking"))
            b_check.config(state="disabled")
            b_now.config(state="disabled")

            def work():
                res = updater.check(ROOT)
                if res["mode"] == "archive" and res["behind"] is None:      # commit unknown: show what would change first
                    ok, files = updater.preview_archive(ROOT, res.get("latest"))
                    res["files"] = files if ok else None
                st = updater.load_settings()
                st["last_update_check"] = time.time()
                updater.save_settings(st)
                self.ui(show, res)
            threading.Thread(target=work, daemon=True).start()

        found = {"ids": []}

        def show_programs(items, failed):
            found["ids"] = [x["id"] for x in items]
            lines = [f"{x['name']}: {x['installed']} → {x['latest']}" for x in items]
            msg = t("prog_found", n=len(items)) if items else t("prog_none")
            if failed:
                msg += "\n" + t("prog_fail", ids=", ".join(failed))
            lbl_res.config(text=msg)
            box.config(state="normal")
            box.delete("1.0", "end")
            box.insert("end", "\n".join(lines))
            box.config(state="disabled")
            b_prog.config(state="normal")
            b_tick.config(state="normal" if items else "disabled")

        def do_programs():
            lbl_res.config(text=t("prog_checking"))
            b_prog.config(state="disabled")
            b_tick.config(state="disabled")
            threading.Thread(target=lambda: self.ui(show_programs, *extras.outdated()), daemon=True).start()

        def do_tick():
            for i in found["ids"]:
                if i in self.extra_vars:
                    self.extra_vars[i].set(True)
            self.sync()
            win.destroy()
            self.lbl_status.config(text=t("prog_ticked"))
            messagebox.showinfo(t("title"), t("prog_ticked"))
        b_prog.config(command=do_programs)
        b_tick.config(command=do_tick)

        def do_now():
            res = state["res"]
            if not res or (res["mode"] in ("adopt", "archive") and res.get("behind") is None and not messagebox.askyesno(
                    t("settings"), t("upd_archive_ask" if res["mode"] == "archive" else "upd_adopt_ask"), parent=win)):
                return
            lbl_res.config(text=t("upd_working"))
            b_now.config(state="disabled")
            b_check.config(state="disabled")
            win.destroy()
            self.busy = True
            self.lbl_status.config(text=t("upd_working"))
            threading.Thread(target=self.do_update, args=(res, v_re.get()), daemon=True).start()
        b_check.config(command=do_check)
        b_now.config(command=do_now)
        do_check()

    def open_repo(self):
        """Open the project's GitHub page in the default browser; when that is not possible, show the address."""
        import webbrowser
        try:
            opened = webbrowser.open(updater.REPO_PAGE)
        except Exception:  # noqa: BLE001
            opened = False
        if not opened:
            messagebox.showinfo(t("settings"), t("repo_url", url=updater.REPO_PAGE))

    def do_update(self, res, reinstall):
        """Worker thread: update (or adopt), reinstall the installed programs, then restart. Every UI touch goes through ui()."""
        ok, msg = updater.apply(ROOT, res)
        say = lambda text: self.ui(self.say, text)    # noqa: E731
        if not ok:
            self.ui(self.update_failed, msg)
            return
        say(msg)
        if reinstall:
            ids = reinstall_ids(TOOLS, installed_where)
            if ids:
                cmd = build_command(ROOT, ids, "install", "user")
                say("$ " + shell_line(cmd))
                run_command(cmd, say)
        self.ui(self.restart)

    def update_failed(self, msg):
        self.busy = False
        self.lbl_status.config(text=t("note"))
        self.say(t("upd_failed", e=msg))
        messagebox.showerror(t("settings"), t("upd_failed", e=msg))

    def restart(self):
        messagebox.showinfo(t("settings"), t("upd_done"))
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def package_jobs(self, action, app_id):
        """Commands for a program that comes from the distribution's repositories, or None (cancelled / impossible)."""
        pm = detect_pm()
        name = next(x["name"][LANG] for x in EXTRAS if x["id"] == app_id)
        steps = extras.package_steps(app_id, pm, remove=(action == "uninstall"))
        if not steps:
            messagebox.showinfo(t("title"), t("pkg_unknown", name=name, pm=pm or "?"))
            return None
        if action == "install" and not messagebox.askyesno(
                t("title"), t("pkg_ask", name=name, pkg=extras.package_name(app_id, pm), pm=pm)):
            return None
        jobs = []
        for st in steps:
            job = elevate(["sh", "-c", st["sh"]])
            if job is None:
                messagebox.showwarning(t("title"), t("no_pkexec", cmd="sudo sh -c " + shlex_quote(st["sh"])))
                return None
            jobs.append(job)
        return jobs

    def steps_to_jobs(self, steps):
        """[{'root', 'sh'}] -> commands (root steps through pkexec), or None when there is no way to ask for the password."""
        jobs = []
        for st in steps:
            job = ["sh", "-c", st["sh"]]
            if st["root"]:
                job = elevate(job)
                if job is None:
                    messagebox.showwarning(t("title"), t("no_pkexec", cmd="sudo sh -c " + shlex_quote(st["sh"])))
                    return None
            jobs.append(job)
        return jobs

    def github_jobs(self, action, app_id):
        """A .deb from a project's GitHub release (SHA-256 checked), or its removal; None when cancelled / impossible."""
        import platform
        pm, app = detect_pm(), extras.GITHUB_APPS[app_id]
        if action == "uninstall":
            steps = extras.apt_remove_steps(app["package"], pm)
            if not steps:
                messagebox.showinfo(t("title"), t("gh_manual", name=app["name"], url="https://github.com/" + app["repo"]))
                return None
            return self.steps_to_jobs(steps)
        self.lbl_status.config(text=t("looking"))
        self.update_idletasks()
        try:
            release = extras.github_release(app_id)
        except Exception as e:  # noqa: BLE001
            self.lbl_status.config(text=t("note"))
            messagebox.showwarning(t("title"), t("lookup_fail", e=e))
            return None
        self.lbl_status.config(text=t("note"))
        steps, info = extras.github_steps(app_id, release, pm, platform.machine())
        if not steps:
            messagebox.showinfo(t("title"), t("gh_manual", name=app["name"], url=info["manual"]))
            return None
        if not messagebox.askyesno(t("title"), t("gh_ask", name=app["name"], version=info["version"], file=info["file"],
                                                  mb=info["mb"], source=info["source"], sha=info["sha256"])):
            return None
        return self.steps_to_jobs(steps)

    def vscode_jobs(self, action):
        import platform
        pm = detect_pm()
        if action == "uninstall":
            steps = extras.vscode_remove_steps(pm)
        else:
            steps, info = extras.vscode_steps(pm, platform.machine())
            if steps and not messagebox.askyesno(t("title"), t("vscode_ask", fpr=info["fingerprint"])):
                return None
        if not steps:
            messagebox.showinfo(t("title"), t("gh_manual", name="Visual Studio Code", url=extras.VSCODE_PAGE))
            return None
        return self.steps_to_jobs(steps)

    def discord_jobs(self, action):
        import platform
        pm = detect_pm()
        if action == "uninstall":
            steps = extras.apt_remove_steps("discord", pm)
        else:
            steps, info = extras.discord_steps(pm, platform.machine())
            if steps and not messagebox.askyesno(t("title"), t("discord_ask", source=info["source"])):
                return None
        if not steps:
            messagebox.showinfo(t("title"), t("gh_manual", name="Discord", url=extras.DISCORD_PAGE))
            return None
        return self.steps_to_jobs(steps)

    def etcher_jobs(self, action):
        """Commands for balenaEtcher, or None when the user cancelled / it cannot be done (a message was shown)."""
        import platform
        pm = detect_pm()
        if action == "uninstall":
            steps = extras.etcher_remove_steps(pm)
            if not steps:
                messagebox.showinfo(t("title"), t("etcher_manual", url=extras.ETCHER_PAGE))
                return None
        else:
            self.lbl_status.config(text=t("looking"))
            self.update_idletasks()
            try:
                release = extras.etcher_release()
            except Exception as e:  # noqa: BLE001 - offline, rate limit, changed API: say it, do not crash
                self.lbl_status.config(text=t("note"))
                messagebox.showwarning(t("title"), t("lookup_fail", e=e))
                return None
            self.lbl_status.config(text=t("note"))
            steps, info = extras.etcher_steps(release, pm, platform.machine())
            if not steps:
                messagebox.showinfo(t("title"), t("etcher_manual", url=info["manual"]))
                return None
            if not messagebox.askyesno(t("title"), t("etcher_ask", version=info["version"], file=info["file"], mb=info["mb"],
                                                      source=info["source"], sha=info["sha256"])):
                return None
        jobs = []
        for st in steps:
            job = ["sh", "-c", st["sh"]]
            if st["root"]:
                job = elevate(job)
                if job is None:
                    messagebox.showwarning(t("title"), t("no_pkexec", cmd="sudo sh -c " + shlex_quote(st["sh"])))
                    return None
            jobs.append(job)
        return jobs

    def finish(self, rc):
        self.busy = False
        for b in (self.b_inst, self.b_un):
            b.state(["!disabled"])
        self.prog.stop()
        self.runbar.pack_forget()
        self.b_cancel.state(["!disabled"])
        done = t("done_ok") if rc == 0 else t("cancelled") if rc == 130 else t("done_fail", rc=rc)
        self.say(done)
        self.lbl_status.config(text=done)
        if rc == 0 and getattr(self, "pending_data", None):           # only after the programs themselves went away
            done, failed = extras.remove_data(self.pending_data)
            if done:
                self.say(t("data_done", n=len(done)))
            for path, err in failed:
                self.say(t("data_fail", p=path, e=err))
        self.pending_data = None
        self.render()
        if rc == 0 and getattr(self, "start_printhub", False):       # "install it and it runs"
            path = tool_path("printhub", self.where.get())
            if path:
                self.say(t("launching"))
                subprocess.Popen([path], start_new_session=True)
        self.start_printhub = False


def main(argv):
    if "--make-launcher" in argv:
        print(make_launcher())
        return
    app = App()
    if "--select" in argv:                       # e.g. --select printhub: open with only these programs ticked
        ids = argv[argv.index("--select") + 1:]
        app.pick(False)
        for i in ids:
            if i in app.vars:
                app.vars[i].set(True)
        app.sync()
    app.mainloop()


if __name__ == "__main__":
    main(sys.argv[1:])
