# qgis-installer

Bilingual (English / ქართული) GUI that installs **QGIS** the way *you* choose. English by default.
ორენოვანი GUI QGIS-ის დასაყენებლად — მეთოდს თქვენ ირჩევთ.

```bash
python3 qgis-installer-gui.py
```

```bash
# from the repository root
./install.sh qgis-installer
```

If `tkinter` is missing the script offers to install it itself (apt/dnf/pacman/zypper/apk).

## Command line

The same logic without a window - for scripts, SSH sessions and tests:

```bash
qgis-installer-cli info                                  # what this system is, what can be done (--json)
qgis-installer-cli plan --method A --channel ltr         # the commands, nothing runs (--script, --json)
qgis-installer-cli install --method A --channel ltr      # shows the commands, asks, then runs (--yes, --dry-run)
qgis-installer-cli list                                  # every QGIS installation found (--json)
qgis-installer-cli uninstall [--kinds apt,repo,data] [--purge] [--dry-run]
```

```bash
qgis-installer-cli requirements check [--plugin postgis_manager]     # what the GIS GEORGIA QGIS plugins need
qgis-installer-cli requirements install --plugin postgis_manager     # install what is missing (--optional, --dry-run)
```

`requirements` knows the system packages behind psycopg2, the PostgreSQL client tools, ExifTool, GeoPandas, SAGA and
GRASS for apt / dnf / pacman / zypper / apk (names checked against each distribution's repositories by
`tests/pkgnames_check.py`; where a distribution has no package - SAGA on Fedora/Arch/openSUSE, GRASS on Arch, WindNinja
everywhere - it says so instead of guessing). It looks at *this* system's Python and PATH.

Exit codes: `0` ok, `1`/the failing step's code, `2` not possible here or bad arguments, `3` not confirmed.
User data is never removed unless `--kinds` names `data`. `--lang en|ka` selects the language (default: the one the
GUI remembers). To preview another system: `--os-release tests/fixtures/os-release/debian-trixie --pm apt-get --arch amd64`.

## Layout

| Part | What |
|---|---|
| `qgis_installer/` | the logic, no UI toolkit: `system` (detection, channels), `plan` (install steps), `uninstall` (finding and removing), `requirements` (what the GIS GEORGIA plugins need), `i18n` (EN/KA), `runner` (running steps, elevation), `cli` |
| `qgis-installer-gui.py` | the Tk window - a thin layer over the package |
| `qgis-installer-cli.py` | the command line (`python3 -m qgis_installer` from this folder does the same) |

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

⚠️ Written from the guide; the generated shell is syntax-checked (`sh -n`) in the unit tests for every distribution fixture, method and channel, and the GUI starts. Detection was checked against a real apt install (QGIS 3.44 LTR from `qgis.org/ubuntu-ltr`); removal commands were generated and syntax-checked but **not executed**. Snap/dnf/pacman/zypper detection is untested.
