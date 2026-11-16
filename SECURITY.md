# Security policy

## Reporting a problem · როგორ შეგვატყობინოთ

Please **do not post exploit details in a public issue.** Use GitHub's private reporting on this repository (*Security* tab → *Report a vulnerability*) when it is
offered. If it is not, open an issue that says only *that* you found a security problem and in which tool, and ask for a private way to send the details.
Include: the tool and how it was installed (`get.sh`, clone, `install.sh`), your distribution, and the smallest steps that show the problem.

Only the latest `main` is supported; there are no release branches.

## What the tools are built to protect against

This toolkit runs commands on your computer, sometimes as administrator, and updates itself from GitHub, so these are deliberate design rules (each is covered by tests):

| Area | Protection |
|---|---|
| **Updating the toolkit** (`installer/updater.py`, `get.sh`) | HTTPS only; the snapshot's commit id and size are checked; archives with links, absolute paths or `..` are refused; unpacked in a scratch folder, applied file by file with atomic renames, any failure restores the previous files; a user's symbolic link is never written through; replaced files are backed up |
| **Installing** (`install.sh`) | records what it installed (path + SHA-256), never overwrites or removes a file that is not its own, `--dry-run` previews, uses `sudo` only when the destination needs it |
| **Downloads of programs** (installer) | HTTPS, SHA-256 compared with the digest GitHub publishes for that exact file *before* unpacking or running; no digest → no install; vendor install scripts are shown in full and run only after you agree |
| **AUR packages** (Arch) | the PKGBUILD and install scripts are shown with their SHA-256, maintainer and votes before anything is built; `makepkg` runs as you, only the install step is administrator |
| **Privileges** | the windows never run as root; the one command that needs it goes through `pkexec`, after showing what will run |
| **No shell from input** | argument lists for every subprocess, no `shell=True`; values from users or the network are validated before use (ports, names, paths) |
| **DevOps Toolbox** | allowlisted operations only (no command field), backend validation, single-use preview token + explicit confirmation, no `ufw disable`; the web page listens on loopback only, needs a per-run key, checks Host/Origin, has a strict CSP |
| **DevOps Toolbox on another computer (SSH)** | keys only (never a password), `StrictHostKeyChecking=yes` with the fingerprint shown and confirmed by you before it is trusted, a changed key refused, `-F /dev/null`, nothing forwarded, every remote word quoted, `sudo -n` only (no password prompt), previews bound to the computer, remote output cleaned of escape sequences; tested against a real sshd |

## What they do **not** protect against (so you can judge)

* The toolkit itself is trusted through GitHub over HTTPS and the commit id; commits and downloads are **not signed** by the maintainer.
* A program's SHA-256 comes from GitHub's release page: if the publisher's release is malicious, the check passes. Review what you install.
* Anything you start as root yourself (`sudo ./install.sh …`) has root's power, as always. Read a script before running it.
* The real `pkexec` password dialog and live firewall changes are exercised by hand, not by the automated tests (which use fakes). Hardware-dependent tools are verified only on the hardware their README names.
* Running operations on another computer is as trustworthy as the account you connect with: a user with passwordless `sudo` (or `root`) can do everything on that computer, and the fingerprint comparison is only as good as the channel you got the real fingerprint from.
