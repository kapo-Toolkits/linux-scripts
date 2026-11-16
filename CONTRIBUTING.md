# Contributing

Thank you for helping. This is a small toolkit with strong habits; this page is what you need to match them. · როგორ შევცვალოთ რამე.

## What belongs here

Utilities that solve a **specific problem**, automate something repetitive, or reach what the desktop's own settings do not — standalone and light
(no background services, no big dependencies). It is **not** meant to collect generic GUIs that duplicate the desktop (disk analysers, system monitors,
file managers, general settings panels). When in doubt, open an issue first and describe the problem you have, not the tool you imagine.

## Layout

```
<tool>/            one folder per tool: its script(s), .desktop file and README (English first, Georgian lines next to it)
common/            code several tools share (lscommon.py: tkinter bootstrap, runner, language; lsnet.py, lsqr.py)
installer/         the installer window, programs.json (the catalogue), extras.py (how each program is installed), updater.py
install.sh         installs / uninstalls the tools (commands, menu entries, shared code) — keep its options working
tests/             offline unit tests, window tests (Xvfb), container tests (docker)
```

Tools that are more than one file are a package next to a thin launcher (`qgis-installer/qgis_installer/`, `devops-toolbox/devops_toolbox/`); `install.sh`
copies the package to `PREFIX/lib/linux-scripts`. Compatibility: **Python 3.8+**, no third-party packages for the tools themselves (PrintHub is the one
Qt application and has its own requirements).

## Rules that every change follows

1. **English by default, Georgian next to it.** Every user-visible text exists in both languages (the tests fail when a key is missing in one). Keep both READMEs lines in step.
2. **Never build a shell string from input.** Use argument lists with `subprocess`, no `shell=True`; validate input where it enters the backend, not only in the window.
3. **Administrator rights only for the one command that needs them** (`pkexec <program> …`); show the user what will run first and confirm anything destructive.
4. **Downloads are verified** (HTTPS + a published SHA-256 before anything is unpacked or run); never run downloaded content unchecked.
5. **Files you did not create are not yours to overwrite or remove.** Updates and installs stage, keep backups and never follow a user's symbolic links.
6. **Handle the missing command / failed step** with a message that says what to do; do not swallow errors silently.
7. **Tests do not need hardware, root or the network.** Fake the program (see `FakeUfw` in `tests/test_devops_toolbox.py`, the fake `nmcli` in the hotspot tests). Container tests are for what only a real distribution can prove.
8. Do not weaken a check to make a test pass.

## Running things

```bash
python3 tests/test_units.py && python3 tests/test_qgis_installer.py     # the offline core, seconds
python3 tests/test_devops_toolbox.py && python3 tests/test_devops_web.py
xvfb-run -a python3 tests/test_installer_window.py                       # Tk windows need Xvfb (apt install xvfb python3-tk)
pip install ruff==0.14.0 && ruff check .                                 # the same as CI
shellcheck -S warning $(git ls-files '*.sh')
tests/run-distros.sh                                                     # docker: six distributions; slow, runs in CI anyway
```

## How to add …

* **A program to the installer window:** an entry in `installer/programs.json` (the kind says how it is installed: `package`, `github` with `.deb`/`.rpm`
  asset patterns, or a recipe in `installer/extras.py`), a matching entry in `shortcuts/shortcuts-gui.py`, and a line in `installer/README.md`. The tests cross-check
  the registry, the shortcuts list and the per-distribution routes; package names are checked against real repositories in CI.
* **A DevOps Toolbox operation:** a module in `devops-toolbox/devops_toolbox/modules/` — see [its README](devops-toolbox/README.md#adding-a-module-later). It needs a `plan` that validates, texts in `i18n.py` for both languages, and tests with the fake runner, including malicious input.
* **A tool:** a folder with script + `.desktop` + README, entries in the tables of `install.sh`, a row in the main README, an entry in the installer and shortcuts lists, tests.

## Pull requests

* One topic per branch (`feat/…`, `fix/…`, `docs/…`), a pull request into `main`, **CI green** before merging. The pull request template lists what to state.
* Say what you ran and what you did **not** run. "Not verified on real hardware" is a useful sentence.
* Update the README of the tool and the [CHANGELOG](CHANGELOG.md) when behaviour changes. Security-relevant changes: say which protection they add or change.
* Security problems: do not open a public issue with details — see [SECURITY.md](SECURITY.md).
