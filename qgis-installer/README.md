# qgis-installer

Bilingual (English / ქართული) GUI that installs **QGIS** the way *you* choose. English by default.
ორენოვანი GUI QGIS-ის დასაყენებლად — მეთოდს თქვენ ირჩევთ.

```bash
python3 qgis-installer-gui.py
```

```bash
sudo install -m 755 qgis-installer-gui.py /usr/local/bin/qgis-installer
sudo install -m 644 qgis-installer.desktop /usr/share/applications/
```

If `tkinter` is missing the script offers to install it itself (apt/dnf/pacman/zypper/apk).

## Methods

| | Method | Works on | Notes |
|---|---|---|---|
| A | **Official QGIS repository** | Debian / Ubuntu / Mint & derivatives, amd64 | latest (4.2.x), LTR (3.44.x) or nightly; packages `qgis`, `qgis-plugin-grass`, `python3-qgis`, optional `qgis-server` |
| B | **Flatpak** (`org.qgis.qgis`, Flathub) | any distribution | installed `--user`, no root for QGIS itself |
| C | **Distribution package** | apt / dnf / pacman / zypper | simplest, usually older ⚠️ dnf/pacman/zypper paths untested |

Supported codenames for A (from the [official guide](https://qgis.org/resources/installation-guide/#debian--ubuntu)):
Debian bookworm\*, trixie, sid · Ubuntu resolute, questing, plucky, noble\*, jammy\* — **\*LTR line only** (their libraries are not QGIS 4 ready).
Linux Mint is mapped through `UBUNTU_CODENAME` (Mint 22.x → noble).

## Safety

- Every action is shown as a **command preview**; nothing runs until you press *Run*.
- Method A downloads the QGIS signing key and **aborts unless its fingerprint equals** `2D7E3441A707FDB3E7059441D155B8E6A419C5BE` (published in the guide; the key expires **2027-08-08**).
- Administrator steps run through `pkexec`; if that is unavailable the app writes the script and tells you the `sudo sh …` command instead.

## Uninstall / switch version

The **Uninstall** tab scans for *every* QGIS on the machine and lets you tick what to remove:

| Found | Removed with |
|---|---|
| apt packages (`qgis*`, `python3-qgis*`, `libqgis*`) + where they came from | `apt-get remove` (or `purge`), optional `autoremove` |
| QGIS repository / key files (`/etc/apt/sources.list.d/*qgis*`, keyrings) | `rm -f` + `apt-get update` |
| Flatpak `org.qgis.qgis` (user and system) | `flatpak uninstall` |
| Snap `qgis` | `snap remove` |
| Distro package (dnf / zypper / pacman) | native remove |
| User data: `~/.local/share/QGIS`, `~/.config/QGIS`, `~/.cache/QGIS`, `~/.var/app/org.qgis.qgis` | `rm -rf` on these **exact** paths only — **never ticked by default** (profiles, settings, plugins) |

Everything root-level runs as one step (one password prompt), after a command preview. With *“open the Install tab afterwards”* ticked you can immediately install another channel — needed e.g. for latest → LTR, since apt will not downgrade.

## Differences from the guide's quickstart

- `Types: deb` only (no `deb-src`) — source indexes are not needed to install.
- `software-properties-common` is skipped (not needed for a `.sources` file); `wget`, `gnupg`, `ca-certificates` are installed.
- ubuntugis variants are not offered.
- Only `amd64`, as in the guide.

## Status

⚠️ Written from the guide; the generated shell was syntax-checked (`sh -n`) for all channels and the GUI starts. Detection was checked against a real apt install (QGIS 3.44 LTR from `qgis.org/ubuntu-ltr`); removal commands were generated and syntax-checked but **not executed**. Snap/dnf/pacman/zypper detection is untested.
