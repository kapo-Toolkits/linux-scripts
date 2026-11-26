# Changelog

What changed in this toolkit, newest first. The project has no version numbers: it is used from `main`, and every change arrives as a pull
request (`#n`) that passed CI. Dates are merge dates. · ცვლილებების ისტორია, ახალი ზემოდან.

## Unreleased
- **Added** [`autostart`](autostart/) — *Autostart Manager*: the programs that start at login (yours and the system's), turn them on / off (system entries through your own copy, never edited), add an application or a command, remove / reset, start or stop one now; warns before turning off parts of the desktop; EN/KA; `./install.sh autostart` (also in `all`).
- **Added** DevOps Toolbox can run its operations on **another computer over SSH**: a *Run on* bar (host or IP, port, user, key), keys only, host-key fingerprint shown and confirmed before it is trusted, `sudo -n` for administrator operations, previews bound to the computer, and the plan made against the remote system. Tested against a real sshd in a container.
- **Added** DevOps Toolbox now covers the whole MyDevOps command set: 146 operations in 14 themes (network, firewall, SSH, services, nginx and certificates, Docker and Compose, Git, users, updates, disk and logs, monitoring, security audit, PostgreSQL, backups and cron), a generic operation panel in the window and the web page, your own repositories and Compose projects from a configuration file, and a coverage map that says where every documented command went (or why it stays in the terminal).

## 2026-11-16 — safer updates, installs and CI; DevOps Toolbox
- **Added** [`devops-toolbox`](devops-toolbox/): click-based, allowlisted DevOps operations with a window and a loopback-only web page; first module is the UFW firewall manager (preview → confirm → execute, history, EN/KA, light/dark) (#55).
- **Security** `install.sh` no longer overwrites or removes files that are not its own; records what it installed (path + SHA-256); new `--dry-run` and `--force`; `--prefix` with special characters fixed (#53).
- **Security** The no-git updater and `get.sh` no longer write through symbolic links, stage the update and roll it back on any failure, refuse archives with links or escaping paths and check the snapshot's commit id and size; adopting a plain copy backs up files of yours first (#51).
- **Added** CI: `ruff`, `shellcheck` on every shell script, full `compileall`, Python 3.8–3.13 matrix (#54). **Fixed** plugin scanning on Python 3.8/3.9 reported the standard library as packages to install; a test read the real `/etc/apt` of the machine running it (#54).
- **Changed** `bluetooth-setup` moved to its own repository with its history (#52).

## 2026-11-09 … 11-15 — more programs
- **Added** Ventoy (bootable multi-ISO USB, SHA-256-checked GitHub tarball, no administrator password) (#50); Electerm with `.deb` and `.rpm`, and git / curl / vim / htop / net-tools as command-line programs (#47, #48).
- **Added** a *GIS toolbox* tab in the GIS window — QGIS from the distribution or from Flathub (stable and LTR), SAGA, SpatiaLite — and a search box (#49).
- **Added** PrintHub photo mode: fill / whole / exact print sizes / actual size, margins, repeat on a sheet, one code path for preview and print (#46). Optional Flutter Linux desktop tools per distribution (#45).

## 2026-10-26 … 11-08 — the installer learns about your system
- **Added** the installer says what a system can get and why a program is not offered, and an AUR route for Arch / Manjaro with a full PKGBUILD review before anything is built (#44); Flutter with Dart (#42); Codex CLI (#41); Filee (#40); VirtualBox (#39); unrar (#38).
- **Added** a GIS catalogue (OSGeo and community projects) and an OpenGeos card browser (#34, #35); logs, a program registry (`programs.json`) and bootstrap of missing Python (#33). **Fixed** retry patterns of the network-dependent tests (#43).

## 2026-10-14 … 10-19 — the toolkit takes shape
- **Added** `usb-eject`, `wifi-hotspot` (WPA2 step by step, GUI, QR code, choose devices to share, #36), `printer-setup`.
- **Added** `qgis-installer`: recipes for every way the QGIS guide describes, update, components, instances, safety checks, environment files, doctor, offline copy (#1–#10, #15).
- **Added** PrintHub in the toolkit (#11, #12), desktop shortcuts (#17), the installer window around `install.sh` (#18), balenaEtcher and Brasero (#19, #20), Claude Desktop and update checks (#26), more programs (#27), updating without git (#28), Settings with a GitHub link (#29), Flatpak support and full uninstall (#31, #32).
- **Fixed** launcher behaviour on different desktops and terminals (#21, #22, #23), the file-count check of the portability matrix (#16), CI workflow syntax (#37).
