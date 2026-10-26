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

**A double-click never has to be debugged in a terminal.** When something it needs is missing, the launcher shows a window with
the question — *“tkinter (the window toolkit for Python) is missing. Install it now?”* (English + Georgian) — you click
**Yes**, a graphical password prompt and a pulsing “Installing…” window follow, and the installer window opens when it is done.
If the installation cannot run it says why in a window; the usual case on a computer that is still being set up is
*“Another installer or update is running right now (for example the Linux Mint installer or Update Manager) — wait until it
finishes”* (the package manager is locked). The same question appears when any other toolkit program is started from its icon
without `tkinter`, and in a terminal it is a plain `[Y/n]` (English only when the terminal has no UTF-8, so no `????`).

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
| **Visual Studio Code** ([docs](https://code.visualstudio.com/docs/setup/linux)) | Microsoft's apt repository (Debian-based). The signing key is downloaded over HTTPS and its fingerprint (`BC52 8686 B50D 79E3 39D3 721C EB3E 94AD BE12 29CF`) must match, otherwise nothing is written; then `apt install code`. Updates through `apt upgrade`. |
| **Discord** ([discord.com/download](https://discord.com/download)) | The publisher's own `.deb` over HTTPS (redirects must stay on HTTPS; the file must really be the `discord` package), installed with apt. Discord publishes **no checksum**, so only HTTPS protects this one: the consent dialog says so. |
| **RustDesk**, **Tabby**, **WinBoat**, **ArtCraft Launcher** | The `.deb` from the project's own GitHub release (`rustdesk/rustdesk`, `Eugeny/tabby`, `TibixDev/winboat`, `storytold/craft-launcher`), like balenaEtcher: downloaded over HTTPS, **SHA-256 checked** against the digest GitHub publishes for that exact file, then `apt install`. No digest or no package for the system (non-Debian, ARM where not shipped) → the project page is shown instead. WinBoat additionally needs Docker and KVM. |
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

**More in Settings.** If git is missing and this copy has never been updated, the window first downloads GitHub's latest snapshot into a temporary folder and lists the files that would be replaced (`~` changed, `+` new) before you agree; nothing is touched until you press *Update now*. **Check programs for updates** compares the programs you installed from GitHub releases (balenaEtcher, RustDesk, Tabby, WinBoat, ArtCraft) with their newest release and can tick them in the main window, so one click on *Install selected* updates them; apt-based ones (VS Code, Claude Desktop, Brave) update through `apt upgrade`. In the main window the other programs are grouped, have a search box, and a hint appears when a program is installed twice (for you and for everyone).

**Uninstalling the other programs** removes them from the system completely: on Debian-based systems with `apt-get purge` (the package and its system-wide configuration), plus whatever the installer added to apt — the Claude Desktop and Brave repository entry and key, and the VS Code source file (the Microsoft key only when no other apt source uses it, and nothing at all when `code-insiders` is installed). Your own data in the home folder (for example `~/.config/Code`, `~/.config/discord`) is **never deleted silently**: after you confirm the uninstall, a second question lists exactly the folders that exist (with sizes), defaults to *No*, and only a *Yes* removes them — after the program itself was removed successfully. Only paths inside your home folder are ever touched; a symbolic link is removed, never followed. Other package managers use their normal remove command.

**Downloads and Cancel.** While something runs, a progress bar shows (a percentage for downloads) with a **Cancel** button. Cancel stops a running download at once and skips the remaining steps; an administrator step that has already started is never killed half-way. **Settings** also has an opt-in *install updates automatically at start-up* (only when nothing was changed in this copy; never for an unknown version).

**Fedora, openSUSE, Arch and other non-Debian systems.** Where the publisher's `.deb` / apt repository does not apply, Discord, RustDesk, VS Code and Brave are installed as **Flatpaks from Flathub** — for you only, without an administrator password (Flatpak itself is installed first from the distribution's repositories when it is missing). Uninstalling removes the Flatpak too, and the optional personal-data question also lists `~/.var/app/<id>`.

**Tests against the real publishers.** CI (`tests/run-real-install.sh`) adds the Claude Desktop and VS Code repositories in a throwaway Ubuntu container (key fingerprint, apt must offer the package) and checks that removal takes the entry away again; it also downloads, SHA-256-checks, installs and purges ArtCraft Launcher for real.

**Adding a program.** The *other programs* list is `installer/programs.json`: one entry per program (id, group, kind, names and descriptions in both languages, and for `github` / `package` kinds the repository or command, optional Flatpak id and personal-data folders). The file is checked when it is loaded — a typo names the entry and the problem — and tests make sure every entry also has a shortcut in the shortcuts tool.

**Log.** Everything the window prints is also written to `~/.cache/linux-scripts/logs/installer-YYYYMMDD.log` (the last 10 days are kept). **Settings → Copy log** puts the newest lines on the clipboard for a bug report; **Open log folder** opens the folder.

**Window tests.** `tests/test_installer_window.py` opens the real window (under `xvfb` in CI) and clicks through language switch, search, groups, Settings, progress and Cancel and the small-screen sizes; nothing is installed or downloaded.

## GIS programs (the **GIS** button)

A window of its own with the two lists of [osgeo.org/projects](https://www.osgeo.org/projects/): **OSGeo Projects** and **Community projects**, one tab each, grouped by the same categories (Desktop Applications, Geospatial Libraries, Spatial Databases, Web Mapping, ...). An entry with a package for your system (Marble, PROJ, GDAL/OGR, GEOS, GRASS, PostGIS, pgRouting, MapServer, PyWPS, OWSLib, SFCGAL) has a checkbox and is installed from your distribution's own repositories (one administrator-password prompt, `apt` / `dnf` / `pacman` / `zypper`); **QGIS** opens this toolkit's QGIS installer; every other project (GeoServer, GeoNode, gvSIG, QField, ...) is a **↗** link to its page — those are web servers, Java applications, Python libraries installed per project, or mobile apps, where one distribution package would be a guess. An entry whose package exists only on other distributions says so. The list is `installer/gis.json`; CI checks every package name against the real repositories of Ubuntu, Debian, Fedora, Arch and openSUSE (`tests/run-gis-names.sh`).

## OpenGeos (the **OpenGeos** button, also reachable from the GIS window)

A window of its own for [github.com/opengeos](https://github.com/opengeos) (Open Geospatial Solutions, MIT-licensed geospatial software): every group of the organisation's profile README — GIS platforms, Python packages, data catalogs, QGIS plugins, MapLibre GL JS plugins, R packages, ArcGIS toolboxes, web apps, useful resources — as **cards** (name, GitHub's own description, address) with a search box and a category filter; a click on a card opens the project on GitHub. It is a catalogue (82 projects): nothing is installed from there, because these are per-project Python / JavaScript / QGIS-plugin installs that the project pages describe best. The list is a snapshot, `installer/opengeos.json`, of the README with each repository's description; **README ↗** opens the live page.

**unrar** (group *Command-line tools*): extract `.rar` archives with `unrar x file.rar`. Installed from the distribution's repositories — `unrar` on Ubuntu / Linux Mint (multiverse), Fedora, Arch and openSUSE; **Debian** ships the real unrar only in *non-free*, so there the free `unrar-free` is installed instead (it also provides the `unrar` command). Alpine has no package, so the window says so. Uninstalling purges whichever of the two is installed. CI installs and removes it for real on Ubuntu and Debian (`tests/run-real-install.sh`).
