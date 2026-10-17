# linux-scripts

Small, self-contained Linux utilities. Each tool lives in its own folder with its own README.

პატარა, დამოუკიდებელი Linux სკრიპტები — თითოეული თავის საქაღალდეში, თავისი README-თი.

| Tool | Description |
|---|---|
| [usb-eject](usb-eject/) | Safely unmount and power off USB drives (CLI + GUI, EN/KA) |
| [wifi-hotspot](wifi-hotspot/) | WPA2 Wi-Fi Hotspot via NetworkManager, step by step (CLI steps + EN/KA GUI, tested on Linux Mint) |
| [printer-setup](printer-setup/) | GUI (EN/KA): detect a printer, find/inspect/install its driver, add it, print a test page |
| [qgis-installer](qgis-installer/) | GUI + command line (EN/KA): install QGIS via the official repo (latest/LTR/nightly), Flatpak, or the distro package; find and remove every QGIS |

## Works on

Any Linux with Python 3.8+ and `bash`. The portability matrix (`tests/run-distros.sh`, also in CI) runs the unit tests and
`install.sh` round-trip on **Debian 12, Ubuntu 22.04/24.04, Fedora, Arch, openSUSE Tumbleweed and Alpine**, and checks that
the package names the GUIs suggest for missing tools exist in each distribution.
When a tool is missing (`nmcli`, `udisksctl`, CUPS…) the GUI says so in a dialog (EN/KA) with the exact install command
for your package manager. `tkinter` is installed automatically on first run. The QGIS installer offers the official apt
repository only on Debian/Ubuntu-based systems and Flatpak or the distribution package everywhere else.
Still Linux-specific by nature: Hotspot needs NetworkManager + `iw`, USB eject needs `udisks2`, printer setup needs CUPS.

## New computer

```bash
git clone https://github.com/kapo-Toolkits/linux-scripts.git && cd linux-scripts
sh installer/start.sh      # the installer window: tick programs, click Install
```

## Install / uninstall

```bash
./install.sh all                 # or: usb-eject wifi-hotspot printer-setup qgis-installer bluetooth-setup shortcuts
./install.sh --uninstall all
./install.sh --prefix ~/.local all   # no sudo; menu entries land in ~/.local/share/applications
```

The GUIs share `common/lscommon.py` (tkinter auto-install, runner, remembered language in
`~/.config/linux-scripts/lang`); `install.sh` puts it in `PREFIX/lib/linux-scripts`.

## Tests

```bash
python3 tests/test_units.py            # offline, seconds
tests/run-qgis-containers.sh           # needs docker; real apt + qgis.org in throwaway containers
```

CI (GitHub Actions) runs both on every push and weekly.
| [bluetooth-setup](bluetooth-setup/) | GUI (EN/KA): which Bluetooth dongle works and what it supports (Classic/LE/SSP), scan, pair, connect, audio output |
| [printhub](printhub/) | Print front-end (Qt): PDF, images and Office files with preview and full print settings; EN/KA; `./install.sh printhub` |
| [shortcuts](shortcuts/) | Simple GUI (EN/KA): tick toolkit programs and put their launchers on the Desktop (or remove them) |
| [installer](installer/) | Window around `install.sh` (EN/KA): tick programs, choose “for me / for everyone”, click Install; `--make-launcher` makes a double-click icon in this folder |

