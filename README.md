# linux-scripts

Practical Linux utilities that solve specific problems — each in its own folder with its own README, each usable on its own.
Most have a small window (English / ქართული) **and** a command line.

პრაქტიკული Linux ხელსაწყოები კონკრეტული ამოცანებისთვის: თითო საქაღალდე, თითო README, თითოეული დამოუკიდებლად მუშაობს.
უმეტესს აქვს პატარა ფანჯარა (EN/ქართული) და ბრძანების ხაზიც.

## The tools · ხელსაწყოები

| Tool | What it does | რას აკეთებს | Commands | Needs |
|---|---|---|---|---|
| [usb-eject](usb-eject/) | Safely unmount and power off USB drives | USB დისკის უსაფრთხო გამორთვა | `usb-eject`, `usb-eject-gui` | `udisks2`, `lsblk` |
| [wifi-hotspot](wifi-hotspot/) | WPA2 Wi-Fi hotspot step by step, QR code, connected devices, choose which network to share | WPA2 Wi-Fi hotspot ნაბიჯ-ნაბიჯ, QR კოდი, მოწყობილობების სია | `hotspot`, `hotspot-gui` | NetworkManager (`nmcli`), `iw` |
| [printer-setup](printer-setup/) | From "plugged in a printer" to "test page printed": find and install the driver, add the printer | პრინტერის შეერთებიდან სატესტო გვერდამდე: დრაივერის პოვნა და დაყენება | `printer-setup` | CUPS |
| [autostart](autostart/) | Programs that start when you log in: turn on / off, add, remove, start or stop now | პროგრამების ავტოგაშვება: ჩართვა / გამორთვა, დამატება, წაშლა, ახლავე გაშვება ან გათიშვა | `autostart-manager` | — |
| [printhub](printhub/) | Print front-end (Qt): PDF, images, Office files; preview, full print settings, photo mode. *Not in `all`* (Qt download) | ბეჭდვის ფანჯარა: PDF, სურათები, Office; წინასწარი ნახვა, ფოტო-რეჟიმი | `printhub` | PySide6 (system or private venv ~200 MB), CUPS |
| [qgis-installer](qgis-installer/) | Install QGIS the way you choose (official repo latest/LTR/nightly, Flatpak, distro package, AUR…), plus doctor, plugin dependencies, offline copy, full removal | QGIS-ის დაყენება თქვენი არჩევანით, დიაგნოსტიკა, პლაგინების დამოკიდებულებები, სრული წაშლა | `qgis-installer`, `qgis-installer-cli` | python3 |
| [installer](installer/) | One window to install many programs and update the toolkit itself (picks the right way for your distribution and says why a program is not offered) | ერთი ფანჯარა მრავალი პროგრამის დასაყენებლად და ხელსაწყოების განახლებისთვის | `sh installer/start.sh` | `sh`; Python is offered if missing |
| [shortcuts](shortcuts/) | Put the toolkit's launchers on the Desktop (or take them off) | ხელსაწყოების იარლიყები სამუშაო მაგიდაზე | `toolkit-shortcuts` | tkinter |
| [devops-toolbox](devops-toolbox/) | The commands of the MyDevOps notes as click-based, allowlisted operations (146 in 14 themes: network, firewall/UFW, SSH, services, nginx, Docker, Git, users, updates, disk, monitoring, security, database, backups). Preview → confirm → execute; window **and** loopback-only web page; light/dark | MyDevOps-ის ბრძანებები ერთი დაჭერით (146 ოპერაცია 14 თემაში); ფანჯარა და ლოკალური ვებ გვერდი | `devops-toolbox`, `devops-toolbox-web` | `pkexec` (polkit) + the programs an operation uses |

[bluetooth-setup](https://github.com/kapo-Toolkits/bluetooth-setup) moved to its own repository (history kept).

## Supported systems · რაზე მუშაობს

* **Python 3.8 or newer** (CI runs the offline suites on 3.8, 3.9, 3.10, 3.11, 3.12 and 3.13) and `bash` for `install.sh`.
* **Distributions:** CI runs the unit tests, the `install.sh` install/uninstall round trip and a check of every package name the tools suggest on
  **Debian 12, Ubuntu 22.04 and 24.04, Fedora, Arch, openSUSE Tumbleweed and Alpine** (`tests/run-distros.sh`). Package-specific recipes cover apt, dnf,
  zypper, pacman (+ AUR), apk and Flatpak where a tool installs software; the installer window greys out what a system cannot get and says why.
* **Hardware-specific tools** are only as verified as their README says: the hotspot was tried on one Linux Mint machine, printing and
  Bluetooth depend on your devices. The automated tests use fakes and never need real hardware.
* A missing helper (`nmcli`, `udisksctl`, CUPS, `ufw`…) is reported in the tool's own window (EN/KA) with the install command for your package manager.
  `tkinter` is offered automatically on first run.

## Install · დაყენება

**New computer, one file** (no git, no manual unpacking):

```bash
curl -fsSLO https://raw.githubusercontent.com/kapo-Toolkits/linux-scripts/main/get.sh
sh get.sh                  # read it first: it is short
```

`get.sh` asks GitHub for the newest commit of `main`, downloads exactly that snapshot over HTTPS, refuses archives with links or paths that leave the
folder, and copies it file by file into `~/linux-scripts` (an existing copy is backed up first; your own files stay; a symbolic link of yours is never
written through). It never uses root and opens the installer window.

**From a clone:**

```bash
git clone https://github.com/kapo-Toolkits/linux-scripts.git && cd linux-scripts
sh installer/start.sh                    # the installer window: tick programs, click Install
./install.sh all                         # or pick: usb-eject wifi-hotspot printer-setup qgis-installer shortcuts devops-toolbox autostart printhub
./install.sh --prefix ~/.local all       # no sudo; menu entries land in ~/.local/share/applications
./install.sh --dry-run all               # only print what would be done
```

`install.sh` puts commands in `PREFIX/bin`, menu entries in `PREFIX/share/applications` and shared code in `PREFIX/lib/linux-scripts`. It records
what it installed (path and SHA-256) in `PREFIX/share/linux-scripts/install-manifest` and **never overwrites or removes a file it did not put there**:
a command with the same name from another program stops the install *before* anything is written (`--force` overrides, `--prefix` installs elsewhere).

## Update · განახლება

From the installer window: **⚙ Settings → check for updates** (also a quiet check at start-up, switchable). Three situations are handled:

| Your copy is | What happens |
|---|---|
| a git clone | `git fetch`, then `git pull --ff-only` — refused if you changed tracked files |
| a copy without git | the snapshot of the newest commit is downloaded over HTTPS, checked, unpacked in a scratch folder, then applied file by file (atomic renames, old versions backed up to `~/.cache/linux-scripts/update-backup`); **any failure puts everything back**; symbolic links of yours are left as they are |
| a plain copy (USB stick, zip) | "adopted": connected to GitHub with `git`; files of yours that differ are saved to the backup folder first |

Or run `sh get.sh` again.

## Uninstall · წაშლა

```bash
./install.sh --uninstall all             # add --prefix, --desktop, --folders as used when installing
```

Only what the manifest lists (and still looks like the toolkit's own) is removed; foreign files are kept and reported. The installer window can
also remove the programs it installed.

## Tests and CI

```bash
python3 tests/test_units.py                      # offline, seconds: installer, hotspot, usb-eject, updater, install.sh safety …
python3 tests/test_qgis_installer.py             # qgis-installer core and CLI
python3 tests/test_devops_toolbox.py             # DevOps Toolbox backend (fake ufw: no real firewall is ever touched)
python3 tests/test_devops_web.py                 # its local web app over real HTTP on a loopback port
xvfb-run -a python3 tests/test_installer_window.py   # the Tk windows under a virtual display (also test_hotspot_window, test_devops_window)
tests/run-distros.sh                             # needs docker: unit tests + install round trip + package names on six distributions
tests/run-qgis-containers.sh                     # needs docker: real apt + qgis.org in throwaway containers
```

GitHub Actions runs all of it on every pull request and weekly, plus `ruff`, `shellcheck` on every shell script and a Python 3.8–3.13 matrix.
How to run one piece and what a change needs: [CONTRIBUTING.md](CONTRIBUTING.md).

## More · დამატებით

* [CHANGELOG.md](CHANGELOG.md) — what changed and when · [CONTRIBUTING.md](CONTRIBUTING.md) — how to change something · [SECURITY.md](SECURITY.md) — how to report a problem and what the tools protect against.
* The GUIs share `common/lscommon.py` (tkinter bootstrap, command runner, remembered language in `~/.config/linux-scripts/lang`).
* License: MIT ([LICENSE](LICENSE)).
