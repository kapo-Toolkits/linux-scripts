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
incompletely, or the last lines of the error) and keeps the full log in `~/.cache/linux-scripts/start.log`. On the first
run the window installs Python's `tkinter` itself (`python3-tk`) with a graphical password prompt.
If the file manager shows “untrusted launcher”: right-click the icon → *Allow Launching* (or `chmod +x` it), and a copied
icon from another computer points to the OLD path - make a new one with the command above.

## The window

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

| **Brasero**, **Xfburn**, **K3b** — CD/DVD burners (Brasero: GNOME; Xfburn: light, Xfce; K3b: full-featured, KDE — on a non-KDE desktop it brings many KDE libraries, ~55 packages on Mint) | Come from your **distribution's own repositories**: `apt install brasero` (or `xfburn`, `k3b`) / `dnf install …` / `pacman -S …` / `zypper install …` / `apk add …`. The window shows the package and asks; uninstall removes it the same way. The package names are checked against each distribution's repositories by `tests/pkgnames_check.py` (CI). |

Nothing is bundled in this repository. These programs are never ticked by *Select all*. The same logic runs without a window:
`python3 installer/extras.py etcher plan` prints what would run (it looks the release up, downloads nothing).
Writing an image is destructive for the target drive: Etcher asks you to pick it, and `usb-eject` is the tool for removing the stick safely afterwards.

If `pkexec` is missing, the window shows the `sudo …` command to paste into a terminal.
