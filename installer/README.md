# installer

A small bilingual (English / ქართული) window around `./install.sh`: **tick programs, choose where, click Install** (or Uninstall).
პატარა ორენოვანი ფანჯარა `./install.sh`-ის გარშემო: მონიშნეთ პროგრამები, აირჩიეთ სად, დააჭირეთ „დაყენებას“.

```bash
python3 installer/installer-gui.py
```

**One click from the file manager:** double-click `start-installer.desktop` in the top folder of this checkout. It is made for
the place the folder lives in (absolute paths, so it is **not** in git and does **not** survive copying the folder to another
computer or path). Make it once on every computer — this needs nothing but `sh`, no Python, no executable bit:

```bash
sh installer/start.sh --make-launcher              # icon in this folder
sh installer/start.sh --make-launcher --desktop    # ... and a copy on the Desktop
```

### On a new computer (fresh Linux Mint XFCE, …)

```bash
sudo apt install git python3             # python3 is usually there already
git clone https://github.com/kapo-Toolkits/linux-scripts.git
cd linux-scripts
sh installer/start.sh                    # opens the window; run it in a terminal the first time, so you see any message
sh installer/start.sh --make-launcher --desktop
```

If the window does not open, `installer/start.sh` **says why in a message window** (python3 missing, the folder was copied
incompletely, or the last lines of the error) and keeps the full log in `~/.cache/linux-scripts/start.log`.

**No Python on the computer at all?** `start.sh` notices, **asks**, and installs it for you (`python3` + `tkinter`: `apt`
`python3 python3-tk`, `dnf` `python3 python3-tkinter`, `pacman` `python tk`, `zypper` `python3 python3-tk`, `apk` `python3
python3-tkinter`), with a graphical password prompt (or `sudo` in a terminal), then goes on and opens the window. The package
names are checked against each distribution's repositories in CI (`tests/pkgnames_check.py`).
If the file manager shows “untrusted launcher”: right-click the icon → *Allow Launching* (or `chmod +x` it), and a copied
icon from another computer points to the OLD path - make a new one with the command above.

## The window (three columns, fits a small screen)

The window is laid out **side by side**: *Toolkit programs* | *Other programs (from their publishers)* | *Where / Also / buttons*. Each program is two lines (name and state, then a short grey description), the size is shrunk to the screen (a 1024×600 laptop still shows everything; the log gives way first), and the status line is never cut off. Georgian and English were checked at 1024×600 and 1366×768.

| | |
|---|---|
| **Program list** | USB Safe Eject, Wi-Fi Hotspot, Printer Setup, QGIS Installer, Bluetooth Setup, Desktop Shortcuts, PrintHub (not ticked: it downloads ~200 MB). The last column says where each is already installed: *for me* (`~/.local`), *for everyone* (`/usr/local`) or *—*. |
| **Where** | *Only for me* (`~/.local`, no password) or *For everyone* (`/usr/local`, asks for the administrator password through `pkexec`). |
| **Also** | a launcher on the Desktop (`--desktop`) and a double-click launcher inside each program's folder (`--folders`); only for “Only for me” (as root they would land in root's home). |
| **Command** | the exact `bash install.sh --prefix … TOOL…` that **Install selected** will run, shown above the buttons. Nothing is hidden. |

The log shows `install.sh`'s output live. **Uninstall selected** asks first; it removes only what `install.sh` installed
(plus the Desktop / folder launchers if those boxes are ticked).

**PrintHub in one click.** PrintHub needs PySide6, or Python's `venv`, or `pip`. If the computer has none of them the window
offers to install what is missing (`python3-venv` on Debian/Ubuntu/Mint, `python3-pip` on Fedora/openSUSE, `python-pip` on Arch,
`py3-pip` on Alpine — one administrator-password prompt), then installs PrintHub and **starts it**. The same offer appears
from Printer Setup: its *Open PrintHub* button opens this window with PrintHub pre-ticked
(`python3 installer/installer-gui.py --select printhub`) when PrintHub is not installed yet.

## Other programs (from their publishers)

Below the toolkit's own programs the window has a block for programs that are **not** part of `install.sh`:

| Program | How it is installed |
|---|---|
| **balenaEtcher** ([etcher.balena.io](https://etcher.balena.io), Apache-2.0) — writes an OS image to a USB stick / SD card | The window looks up the **latest release** on `github.com/balena-io/etcher`, shows the file, size, source and its **SHA-256**, and asks. Then (as you) it downloads the publisher's `.deb` / `.rpm` over HTTPS, **refuses to go on unless the SHA-256 matches the digest GitHub publishes for that exact file**, and installs it with `apt` / `dnf` / `zypper` (administrator password); the cached download is deleted afterwards. Other systems (Arch, Alpine, ARM…) get the publisher's download page instead of a guess. |

| **Claude Desktop** ([docs](https://code.claude.com/docs/en/desktop-linux)) | Anthropic's apt repository (Ubuntu / Debian / Mint, amd64 + arm64). After a consent dialog the window downloads the signing key over HTTPS, **checks its fingerprint against the one published in the docs** (aborts without writing anything on mismatch), adds the source file and installs `claude-desktop`; later updates come through normal `apt upgrade`. Other systems: the window points to the official page. Sign in with a claude.ai account; Cowork needs virtualization and membership in the `kvm` group. |
| **Brave Browser** ([brave.com](https://brave.com)) | Brave's own install script, `curl -fsS https://dl.brave.com/install.sh | sh` — **but not blindly piped**: the window downloads it over HTTPS (refusing anything that is not a small shell script), shows it **in full with its SHA-256** in a window of its own, and runs it **only after you click Run**, as the administrator (one password prompt; the script needs no `sudo` of its own then). It adds Brave's package repository (signing key + source file from brave.com) and installs `brave-browser` with apt / dnf / zypper / yum / pacman (+ AUR helper) / rpm-ostree. The file that runs is byte-for-byte the text you saw, and it is deleted afterwards. Uninstall removes the package and (apt) the repository files the script added. You still trust Brave's server and TLS: that is the nature of vendor install scripts; source: [github.com/brave/install.sh](https://github.com/brave/install.sh) (BSD-3-Clause). |
| **Brasero**, **Xfburn**, **K3b** — CD/DVD burners (Brasero: GNOME; Xfburn: light, Xfce; K3b: full-featured, KDE — on a non-KDE desktop it brings many KDE libraries, ~55 packages on Mint) | Come from your **distribution's own repositories**: `apt install brasero` (or `xfburn`, `k3b`) / `dnf install …` / `pacman -S …` / `zypper install …` / `apk add …`. The window shows the package and asks; uninstall removes it the same way. The package names are checked against each distribution's repositories by `tests/pkgnames_check.py` (CI). |

Nothing is bundled in this repository. These programs are never ticked by *Select all*. The same logic runs without a window:
`python3 installer/extras.py etcher plan` prints what would run (it looks the release up, downloads nothing).
Writing an image is destructive for the target drive: Etcher asks you to pick it, and `usb-eject` is the tool for removing the stick safely afterwards.

If `pkexec` is missing, the window shows the `sudo …` command to paste into a terminal.

## Updates (⚙ Settings)

The ⚙ button opens **Settings**. It asks GitHub (read-only) whether `main` of this repository has new commits and lists them. **Update now** pulls them (a git checkout is fast-forwarded; refused if you changed tracked files) and, if enabled, reinstalls the tools you installed for yourself, then restarts the window. A toolkit that was just **copied** to another computer (no `.git`) is *adopted*: the window attaches it to the repository and fetches the current version, so no manual copying is needed. Optionally the installer checks quietly at start-up (at most every 6 hours) and shows a banner with **Later** to snooze. Settings are stored in `~/.config/linux-scripts/settings.json`. Command line: `python3 installer/updater.py check|update [DIR]`.

**No git on the computer?** Nothing to install: when `git` is missing, the window (and `updater.py`) switches to a Python-only update. It asks GitHub's API for the newest commit of `main`, downloads exactly that snapshot over HTTPS, and copies its files over the folder; every file it replaces is first saved to `~/.cache/linux-scripts/update-backup/<time>/`, files that are not in the snapshot (your own launcher, notes) are left alone, and the commit id is remembered in `.installed-sha` so the next check can list what is new. Archive members that are links or try to leave the folder are ignored. If git is installed later, a normal checkout can be set up the usual way.

Settings also has a **GitHub ↗** button that opens the project page (`github.com/kapo-Toolkits/linux-scripts`) in your browser, or shows the address when no browser can be started.
