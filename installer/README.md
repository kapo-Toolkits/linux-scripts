# installer

A small bilingual (English / ქართული) window around `./install.sh`: **tick programs, choose where, click Install** (or Uninstall).
პატარა ორენოვანი ფანჯარა `./install.sh`-ის გარშემო: მონიშნეთ პროგრამები, აირჩიეთ სად, დააჭირეთ „დაყენებას“.

```bash
python3 installer/installer-gui.py
```

**One click from the file manager:** double-click `start-installer.desktop` in the top folder of this checkout. It is made for
your machine (absolute paths, so it is not in git); create it once with

```bash
python3 installer/installer-gui.py --make-launcher
```

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

If `pkexec` is missing, the window shows the `sudo …` command to paste into a terminal.
