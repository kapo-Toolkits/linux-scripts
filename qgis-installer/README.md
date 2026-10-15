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

## Recipes: every way the installation guide describes

The guide ([Linux section](https://qgis.org/resources/installation-guide/#linux)) has more than three ways to get QGIS.
Each is a *recipe* (`qgis-installer-cli recipes`): it knows which systems it fits, what options it has, and either runs
shell steps (shown first, run only after you confirm) or just prints instructions.

| Recipe | Fits | Notes | Checked by |
|---|---|---|---|
| `apt-official` | Debian 12/13/sid, Ubuntu 22.04-26.04, Mint (amd64) | latest / LTR / nightly, key fingerprint verified | real install in a container |
| `apt-distro` | any apt system | older, simplest | apt dry run |
| `flatpak` | everywhere | **branch `stable` (QGIS 4) or `lts` (QGIS 3 LTR)**, user or system | Flathub refs exist |
| `dnf-fedora` / `rpm-ostree-fedora` | Fedora / Fedora Atomic | `qgis python3-qgis qgis-grass`, optional server | dnf dry run / from the guide |
| `zypper-opensuse` | openSUSE | `qgis qgis-plugin-grass`, optional Application:Geo repository | zypper dry run |
| `pacman-arch` / `aur-helper` | Arch and derivatives | official `qgis`; LTR/git from the AUR via `yay`/`paru` (builds from source) | pacman `--print` / from the guide |
| `urpmi-mageia` | Mageia (Mandriva's successor) | `qgis qgis-grass` | package names exist |
| `spack`, `distrobox`, `toolbx` | where the tool is installed | source build / separate container | from the guide |
| `nix-manual`, `slackware-manual` | NixOS, Slackware | instructions only, nothing is changed for you | - |

```bash
qgis-installer-cli recommend --goal stable|latest|alongside     # the best one here, and why
qgis-installer-cli plan --goal alongside                        # try QGIS 4 next to the one you have
qgis-installer-cli plan --recipe flatpak --branch lts
qgis-installer-cli install --recipe zypper-opensuse --geo-repo
```

Where this tool differs from the guide, on purpose (each was checked against the real repositories):
- **Flathub has two branches** - the guide says "stable only". `stable` is built on the KDE 6.11 runtime (QGIS 4), `lts` on an
  end-of-life KDE 5.15 runtime (QGIS 3 LTR). A non-interactive `flatpak install -y flathub org.qgis.qgis` fails with
  "No ref chosen", so the recipe always names the branch.
- openSUSE has **no `qgis-ltr`** and no `python3-qgis` (Python support is part of `qgis`), also not in Application:Geo.
- Mandriva's `qgis-python` does not exist on Mageia; the packages are `qgis` and `qgis-grass`.
- The guide's `yaourt` is dead; the AUR recipe uses `yay` or `paru` when present.
- ubuntugis builds (Ubuntu 22.04/24.04) are not offered; `deb-src` is not added.

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

## Components (the OSGeo4W chooser, in a small Linux form)

OSGeo4W lets you pick QGIS and the programs around it from one list. On Linux the system's package manager is the chooser;
this lists the useful pieces in one place and installs them with it:

```bash
qgis-installer-cli components                          # what is there and what can be added, grouped
qgis-installer-cli components --category python        # cli | engine | python | db
qgis-installer-cli components install gdal numpy --dry-run
```

Groups: command line tools (GDAL, PROJ, ExifTool), GIS engines (GRASS, SAGA, WindNinja), Python libraries (GDAL/OGR, NumPy, pandas,
SciPy, Matplotlib, Shapely, pyproj, rasterio, Fiona, GeoPandas, psycopg2) and database clients (PostgreSQL). Where a distribution has
no package (for example SAGA on Fedora, rasterio on Arch) the program says so instead of guessing. The package names are checked
against the repositories of all seven distributions by `tests/run-distros.sh`, and installing and re-listing runs for real on
Debian, Fedora, openSUSE and Arch (`tests/run-recipes-containers.sh`). Nothing here **removes** packages: a library such as NumPy can
be a dependency of QGIS itself, and removing it would take QGIS along. Python libraries installed this way are visible to a QGIS that
uses the system's Python; a Flatpak or Snap QGIS has its own sandbox.

## Updating what is installed

```bash
qgis-installer-cli update --dry-run     # shows the commands for every QGIS found here, runs nothing
qgis-installer-cli update               # asks first; close QGIS before running it
```

It upgrades the installed packages of each installation found (apt `--only-upgrade`, Flatpak, Snap, dnf, zypper, `rpm-ostree upgrade`)
and keeps the channel: latest to LTR needs *Uninstall* and a new install, because apt will not downgrade. Arch is never updated
package by package (a partial upgrade can break the system): the program prints `sudo pacman -Syu` and the AUR line for you to run.
Containers (`qgis-box`) are updated inside with their own package manager; the program says how. User data is never touched.

Recipes that live apart from the system's QGIS (Flatpak, containers, Spack, Nix) are marked `side_by_side` in `recipes`: they can be
installed while QGIS is running and do not replace the QGIS you have. The other recipes change the system's QGIS in place.

## Ways to install

See **Recipes** above: every way the guide describes is a recipe, `recommend` picks one for your goal and system, and the
window offers the same. The old letters still work on the command line: `--method A` is `apt-official`, `B` is `flatpak`,
`C` is the distribution package of your system (`apt-distro`, `dnf-fedora`, `zypper-opensuse`, `pacman-arch`).

**Not run by the author** (taken from the guide, marked "from the guide" in the program): `rpm-ostree`, Spack, Distrobox,
Toolbx and the AUR. Re-running the container recipes is safe (an existing `qgis-box` is reused); on Fedora hosts Toolbx
uses `fedora-toolbox:<host release>`, elsewhere the guide's image. Fedora Atomic layering is `--idempotent` and tells you to reboot.

`uninstall` also finds AUR packages (`qgis-ltr`, `qgis-git`), `rpm-ostree` layers and the `qgis-box` container
(removing the container deletes the files inside it - the app says so).

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
| Distro package (dnf / zypper / pacman, AUR `qgis-ltr` / `qgis-git`, `rpm-ostree` layers) | native remove |
| Container `qgis-box` (Distrobox / Toolbx) | `distrobox rm` / `toolbox rm` |
| User data: `~/.local/share/QGIS`, `~/.config/QGIS`, `~/.cache/QGIS`, `~/.var/app/org.qgis.qgis` | `rm -rf` on these **exact** paths only — **never ticked by default** (profiles, settings, plugins) |

Everything root-level runs as one step (one password prompt), after a command preview. With *“open the Install tab afterwards”* ticked you can immediately install another channel — needed e.g. for latest → LTR, since apt will not downgrade.

## Differences from the guide's quickstart

- `Types: deb` only (no `deb-src`) — source indexes are not needed to install.
- `software-properties-common` is skipped (not needed for a `.sources` file); `wget`, `gnupg`, `ca-certificates` are installed.
- ubuntugis variants are not offered.
- Only `amd64`, as in the guide.

## Status

⚠️ Written from the guide; the generated shell is syntax-checked (`sh -n`) in the unit tests for every recipe on every distribution fixture, and the GUI starts. Detection was checked against a real apt install (QGIS 3.44 LTR from `qgis.org/ubuntu-ltr`); removal commands were generated and syntax-checked but **not executed**. Snap/dnf/pacman/zypper detection is untested.
