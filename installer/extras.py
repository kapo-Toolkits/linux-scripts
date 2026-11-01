#!/usr/bin/env python3
"""Other programs the toolkit can install straight from their publishers (not part of install.sh). No UI.

balenaEtcher (https://etcher.balena.io, Apache-2.0): writes an OS image to a USB stick / SD card.  Linux is offered as
the publisher's own .deb and .rpm on GitHub releases.  Nothing is bundled here: the installer looks up the latest release,
downloads the package over HTTPS from github.com/balena-io/etcher, **checks its SHA-256** against the digest GitHub
publishes for that exact asset, and only then installs it with the system package manager (administrator password).
Other systems get the publisher's download page instead of a guess.

    python3 installer/extras.py etcher plan [--json]      # what would run (looks up the release, runs nothing)
    python3 installer/extras.py etcher installed          # the installed version, if any

Brasero, Xfburn and K3b (CD/DVD burners) come from the distribution's own repositories: package_steps("brasero", pm).
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import urllib.request

ETCHER_REPO = "balena-io/etcher"
ETCHER_API = f"https://api.github.com/repos/{ETCHER_REPO}/releases/latest"
ETCHER_PAGE = "https://etcher.balena.io/#download-etcher"
ETCHER_PACKAGE = "balena-etcher"
CACHE = os.path.join("~", ".cache", "linux-scripts", "downloads")
X86 = ("amd64", "x86_64")

# ---- the list of "other programs" lives in programs.json next to this file ----
PROGRAMS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "programs.json")
KINDS = {"claude", "vscode", "virtualbox", "filee", "codex", "flutter", "dart", "discord", "brave", "etcher", "github", "package"}      # the recipe that installs it
NEEDED = {"github": ("display", "repo", "package", "cmd", "asset"), "package": ("display", "cmd")}


def load_programs(path=None):
    """The programs.json entries, checked: a typo there must say what is wrong, not crash later in a dialog."""
    with open(path or PROGRAMS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    seen = set()
    for p in data["programs"]:
        i = p.get("id", "?")
        if i in seen:
            raise ValueError(f"programs.json: {i} appears twice")
        seen.add(i)
        if p.get("kind") not in KINDS:
            raise ValueError(f"programs.json: {i}: kind must be one of {sorted(KINDS)}")
        if p.get("group") not in data["groups"]:
            raise ValueError(f"programs.json: {i}: group must be one of {data['groups']}")
        for lang in ("en", "ka"):
            if not p.get("name", {}).get(lang) or not p.get("info", {}).get(lang):
                raise ValueError(f"programs.json: {i}: name and info need both en and ka")
        for key in NEEDED.get(p["kind"], ()):
            if not p.get(key):
                raise ValueError(f"programs.json: {i}: kind {p['kind']} needs '{key}'")
        if "aur" in p and not re.fullmatch(r"[a-z0-9][a-z0-9@._+-]*", str(p["aur"])):
            raise ValueError(f"programs.json: {i}: 'aur' must be an AUR package name ({p['aur']})")
        for d in p.get("data", []):
            if not d.startswith("~/") or ".." in d:
                raise ValueError(f"programs.json: {i}: data paths must start with ~/ and stay inside it ({d})")
    return data


PROGRAMS = load_programs()["programs"]
GITHUB_APPS = {p["id"]: {"name": p["display"], "repo": p["repo"], "package": p["package"], "cmd": p["cmd"], "asset": p["asset"]}
               for p in PROGRAMS if p["kind"] == "github"}
PACKAGE_APPS = {p["id"]: {"cmd": p["cmd"], "name": p["display"], "fallback": p.get("fallback", {})}
                for p in PROGRAMS if p["kind"] == "package"}
FLATPAK_IDS = {p["id"]: p["flatpak"] for p in PROGRAMS if p.get("flatpak")}
AUR_IDS = {p["id"]: p["aur"] for p in PROGRAMS if p.get("aur")}
DATA_DIRS = {p["id"]: p.get("data", []) for p in PROGRAMS}



def fetch_json(url, timeout=20, opener=urllib.request.urlopen):
    req = urllib.request.Request(url, headers={"User-Agent": "linux-scripts-installer", "Accept": "application/vnd.github+json"})
    with opener(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def etcher_release(fetch=fetch_json):
    """-> {'tag', 'version', 'assets': {name: {'url', 'size', 'sha256'}}} for the latest published release."""
    data = fetch(ETCHER_API)
    assets = {}
    for a in data.get("assets", []):
        digest = a.get("digest") or ""
        assets[a["name"]] = {"url": a["browser_download_url"], "size": int(a.get("size", 0)),
                             "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else ""}
    tag = data["tag_name"]
    return {"tag": tag, "version": tag.lstrip("v"), "assets": assets}


def etcher_asset(release, pm, arch):
    """The publisher's package for this system, or None: .deb for apt, .rpm for dnf / zypper, x86-64 only."""
    if arch not in X86:
        return None
    v = release["version"]
    name = {"apt-get": f"balena-etcher_{v}_amd64.deb", "dnf": f"balena-etcher-{v}-1.x86_64.rpm",
            "zypper": f"balena-etcher-{v}-1.x86_64.rpm"}.get(pm)
    a = release["assets"].get(name) if name else None
    return dict(a, name=name) if a and a["sha256"] else None


def download_script(asset, cache_dir=None, proto="=https"):
    """POSIX sh: download over HTTPS to a private cache folder and refuse to go on unless the SHA-256 matches."""
    d = os.path.expanduser(cache_dir or CACHE)
    q = shlex.quote
    name = asset["name"]
    return f"""set -eu
command -v curl >/dev/null 2>&1 || {{ echo "curl is not installed (Debian/Ubuntu: sudo apt install curl)" >&2; exit 1; }}
command -v sha256sum >/dev/null 2>&1 || {{ echo "sha256sum is not installed (package coreutils)" >&2; exit 1; }}
mkdir -p {q(d)}
cd {q(d)}
trap 'rm -f {q(name)}.part' EXIT
curl -fL --progress-bar --proto '{proto}' --tlsv1.2 -o {q(name)}.part {q(asset['url'])}
echo "{asset['sha256']}  {name}.part" | sha256sum -c - >/dev/null || {{ echo "CHECKSUM MISMATCH - the download is not what the publisher published; nothing was installed" >&2; exit 1; }}
echo "SHA-256 verified: {asset['sha256']}"
mv {q(name)}.part {q(name)}
"""


def etcher_steps(release, pm, arch, cache_dir=None):
    """-> (steps, info). steps = [{'root': bool, 'sh': str}]; info = what the user is asked to agree to.
    steps is [] and info['manual'] holds the publisher's page when this system has no official package."""
    asset = etcher_asset(release, pm, arch)
    if not asset:
        return [], {"manual": ETCHER_PAGE, "version": release["version"]}
    d = os.path.expanduser(cache_dir or CACHE)
    path = os.path.join(d, asset["name"])
    install = {"apt-get": f"apt-get install -y {shlex.quote(path)}", "dnf": f"dnf install -y {shlex.quote(path)}",
               "zypper": f"zypper --non-interactive install --allow-unsigned-rpm {shlex.quote(path)}"}[pm]
    steps = [{"root": False, "sh": download_script(asset, cache_dir)},
             {"root": True, "sh": f"set -eu\n{install}\n"},
             {"root": False, "sh": f"rm -f {shlex.quote(path)}\n"}]
    return steps, {"version": release["version"], "file": asset["name"], "mb": round(asset["size"] / 1048576),
                   "url": asset["url"], "sha256": asset["sha256"], "source": "github.com/" + ETCHER_REPO}


def etcher_remove_steps(pm):
    cmd = {"apt-get": f"apt-get purge -y {ETCHER_PACKAGE}", "dnf": f"dnf remove -y {ETCHER_PACKAGE}",
           "zypper": f"zypper --non-interactive remove {ETCHER_PACKAGE}"}.get(pm)
    return [{"root": True, "sh": f"set -u\n{cmd}\n"}] if cmd else []


def etcher_installed(run=subprocess.run, which=shutil.which):
    """The installed version string, or None."""
    for cmd in (["dpkg-query", "-W", "-f=${Status} ${Version}", ETCHER_PACKAGE],
                ["rpm", "-q", "--qf", "install ok installed %{VERSION}", ETCHER_PACKAGE]):
        if which(cmd[0]):
            try:
                r = run(cmd, capture_output=True, text=True, timeout=20)
            except Exception:  # noqa: BLE001
                continue
            if r.returncode == 0 and r.stdout.startswith("install ok installed"):
                return r.stdout.split()[-1]
    return None


# ---- Brave Browser: the publisher's own install script (BSD-3-Clause, https://github.com/brave/install.sh) ----
# It adds Brave's package repository (signing key + source file, fetched over HTTPS from brave.com) and installs
# brave-browser with the system package manager (apt / dnf / zypper / yum / pacman + AUR helper / rpm-ostree / eopkg).
# It is never piped blindly into a shell: it is downloaded first, its SHA-256 and full text are shown, and it runs as the
# administrator only after the user agrees.
BRAVE_SCRIPT_URL = "https://dl.brave.com/install.sh"
BRAVE_SOURCE = "https://github.com/brave/install.sh"
BRAVE_MAX_BYTES = 200 * 1024


def brave_fetch_script(opener=urllib.request.urlopen, timeout=20):
    """-> {'text', 'sha256', 'bytes'}; refuses anything that is not a small shell script served over HTTPS."""
    import hashlib
    req = urllib.request.Request(BRAVE_SCRIPT_URL, headers={"User-Agent": "linux-scripts-installer"})
    with opener(req, timeout=timeout) as r:
        if not r.geturl().startswith("https://"):
            raise ValueError("the download was redirected away from HTTPS")
        raw = r.read(BRAVE_MAX_BYTES + 1)
    if len(raw) > BRAVE_MAX_BYTES:
        raise ValueError("the script is much larger than expected")
    text = raw.decode("utf-8")
    if not text.startswith("#!/bin/sh") or "<html" in text[:2000].lower() or "brave" not in text.lower():
        raise ValueError("this does not look like Brave's install script (a web page or an error was received)")
    return {"text": text, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def brave_steps(script_path):
    """The script runs as the administrator (so it needs no sudo of its own and asks for the password once), then is deleted."""
    q = shlex.quote(script_path)
    return [{"root": True, "sh": f"set -eu\nsh {q}\n"}, {"root": False, "sh": f"rm -f {q}\n"}]


def brave_remove_steps(pm):
    """Package plus the repository files the script added (apt); rpm distributions keep their repo file."""
    cmds = {"apt-get": "apt-get purge -y brave-browser\nrm -f /etc/apt/sources.list.d/brave-browser-release.sources "
                       "/usr/share/keyrings/brave-browser-archive-keyring.gpg\napt-get update || true",
            "dnf": "dnf remove -y brave-browser", "yum": "yum remove -y brave-browser",
            "zypper": "zypper --non-interactive remove brave-browser",
            "pacman": "pacman -R --noconfirm brave-browser || pacman -R --noconfirm brave-bin"}
    cmd = cmds.get(pm)
    return [{"root": True, "sh": f"set -u\n{cmd}\n"}] if cmd else []


def brave_installed(which=shutil.which):
    return bool(which("brave-browser") or which("brave"))


# ---- Claude Desktop (beta) for Debian-based Linux: Anthropic's own apt repository ----
# https://code.claude.com/docs/en/desktop-linux  (Ubuntu 22.04+ / Debian 12+, x86_64 or arm64)
CLAUDE_PAGE = "https://code.claude.com/docs/en/desktop-linux"
CLAUDE_KEY_URL = "https://downloads.claude.ai/claude-desktop/key.asc"
CLAUDE_FPR = "31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE"          # printed by `gpg --show-keys` in the vendor's instructions
CLAUDE_KEYRING = "/usr/share/keyrings/claude-desktop-archive-keyring.asc"
CLAUDE_LIST = "/etc/apt/sources.list.d/claude-desktop.list"
CLAUDE_REPO = "https://downloads.claude.ai/claude-desktop/apt/stable stable main"
CLAUDE_NOTES = ("Sign in with your claude.ai account (not an API key). For Cowork: turn on hardware virtualization in the "
                "firmware, then add your user to the kvm group:  sudo usermod -aG kvm $USER  and log out and in.")


def claude_steps(pm, arch, proto="=https", keyring=None, listfile=None, fpr=None, url=None):
    """One administrator step: the key is downloaded, its fingerprint is compared with the one Anthropic publishes (abort on
    a mismatch, nothing is written), the repository is registered, then apt installs claude-desktop.
    -> (steps, info); steps is [] with info['manual'] when this system is not Debian-based x86_64 / arm64."""
    if pm != "apt-get" or arch not in ("amd64", "arm64", "x86_64", "aarch64"):
        return [], {"manual": CLAUDE_PAGE}
    q = shlex.quote
    keyring, listfile, fpr, url = keyring or CLAUDE_KEYRING, listfile or CLAUDE_LIST, fpr or CLAUDE_FPR, url or CLAUDE_KEY_URL
    line = f"deb [arch=amd64,arm64 signed-by={keyring}] {CLAUDE_REPO}"
    sh = f"""set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get install -y curl gnupg ca-certificates || (apt-get update && apt-get install -y curl gnupg ca-certificates)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
curl -fsSL --proto '{proto}' --tlsv1.2 -o "$TMP/key.asc" {q(url)}
mkdir -m700 "$TMP/gnupg"
FPR=$(gpg --homedir "$TMP/gnupg" --show-keys --with-colons "$TMP/key.asc" | awk -F: '$1=="fpr"{{print $10; exit}}')
if [ "$FPR" != "{fpr}" ]; then echo "KEY FINGERPRINT MISMATCH: $FPR - nothing was installed" >&2; exit 1; fi
echo "Key fingerprint OK: $FPR"
install -D -m644 "$TMP/key.asc" {q(keyring)}
printf '%s\\n' {q(line)} > {q(listfile)}
apt-get update
apt-get install -y claude-desktop
"""
    return [{"root": True, "sh": sh}], {"fingerprint": fpr, "url": url, "repo": line, "key": keyring}


def claude_remove_steps(pm, keyring=None, listfile=None):
    """Purge the package, then drop the repository entry and key this installer registered (the package's own removal does
    the same per the vendor docs; removing the files again is harmless)."""
    if pm != "apt-get":
        return []
    q = shlex.quote
    return [{"root": True, "sh": f"set -u\napt-get purge -y claude-desktop\nrm -f {q(listfile or CLAUDE_LIST)} {q(keyring or CLAUDE_KEYRING)}\n"
                                 "apt-get update || true\n"}]


def claude_installed(which=shutil.which):
    return bool(which("claude-desktop"))


# ---- programs published as a .deb on GitHub releases: RustDesk, Tabby, WinBoat, ArtCraft Launcher ----
# Same safety as balenaEtcher: HTTPS download from the project's own GitHub release, SHA-256 checked against the digest
# GitHub publishes for that exact asset, then apt installs it.  Debian-based systems only; elsewhere the project page is shown.


def github_release(app_id, fetch=fetch_json):
    """-> {'tag', 'version', 'assets'} like etcher_release, for the project behind app_id."""
    data = fetch(f"https://api.github.com/repos/{GITHUB_APPS[app_id]['repo']}/releases/latest")
    assets = {}
    for a in data.get("assets", []):
        digest = a.get("digest") or ""
        assets[a["name"]] = {"url": a["browser_download_url"], "size": int(a.get("size", 0)),
                             "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else ""}
    tag = data["tag_name"]
    return {"tag": tag, "version": tag.lstrip("v"), "assets": assets}


def github_steps(app_id, release, pm, arch, cache_dir=None):
    """-> (steps, info) as etcher_steps; steps is [] with info['manual'] when there is no checked .deb for this system."""
    app = GITHUB_APPS[app_id]
    page = "https://github.com/" + app["repo"] + "/releases/latest"
    kind = "x86" if arch in X86 else "arm" if arch in ("arm64", "aarch64") else None
    pattern = app["asset"].get(kind) if kind else None
    a = release["assets"].get(pattern.format(v=release["version"])) if pattern and pm == "apt-get" else None
    if not a or not a["sha256"]:
        return [], {"manual": page, "version": release["version"]}
    asset = dict(a, name=pattern.format(v=release["version"]))
    path = os.path.join(os.path.expanduser(cache_dir or CACHE), asset["name"])
    steps = [{"root": False, "sh": download_script(asset, cache_dir)},
             {"root": True, "sh": f"set -eu\nexport DEBIAN_FRONTEND=noninteractive\napt-get install -y {shlex.quote(path)}\n"},
             {"root": False, "sh": f"rm -f {shlex.quote(path)}\n"}]
    return steps, {"version": release["version"], "file": asset["name"], "mb": round(asset["size"] / 1048576),
                   "url": asset["url"], "sha256": asset["sha256"], "source": "github.com/" + app["repo"]}


def deb_installed(package, cmd=None, run=subprocess.run, which=shutil.which):
    """True when the dpkg package is installed (or, for other systems, its command is on PATH)."""
    if which("dpkg-query"):
        try:
            r = run(["dpkg-query", "-W", "-f=${Status}", package], capture_output=True, text=True, timeout=20)
            if r.returncode == 0 and r.stdout.startswith("install ok installed"):
                return True
        except Exception:  # noqa: BLE001
            pass
    return bool(cmd and which(cmd))


def installed_version(package, run=subprocess.run, which=shutil.which):
    """The dpkg version string of an installed package, or None."""
    if not which("dpkg-query"):
        return None
    try:
        r = run(["dpkg-query", "-W", "-f=${Status} ${Version}", package], capture_output=True, text=True, timeout=20)
    except Exception:  # noqa: BLE001
        return None
    return r.stdout.split()[-1] if r.returncode == 0 and r.stdout.startswith("install ok installed") else None


def version_key(v):
    """'1:2.1.7-3' / 'v0.4.1' -> (2, 1, 7): the upstream numbers only, for comparing a dpkg version with a release tag."""
    v = str(v).strip().lstrip("v")
    if ":" in v.split(".")[0]:
        v = v.split(":", 1)[1]
    v = v.split("-", 1)[0].split("+", 1)[0].split("~", 1)[0]
    return tuple(int(x) for x in v.split(".") if x.isdigit())


def outdated(installed=installed_version, github=None, etcher=None, codex=None, codex_have=None):
    """Programs installed from a publisher's GitHub release whose newest release is newer than what is installed.
    -> ([{'id', 'name', 'installed', 'latest'}], [ids that could not be looked up]).  Nothing is downloaded or installed."""
    github = github or github_release
    etcher = etcher or etcher_release
    found, failed = [], []
    checks = [("etcher", "balenaEtcher", ETCHER_PACKAGE, etcher)] + [
        (i, a["name"], a["package"], (lambda i=i: github(i))) for i, a in GITHUB_APPS.items()]
    for app_id, name, package, get in checks:
        have = installed(package)
        if not have:
            continue
        try:
            latest = get()["version"]
        except Exception:  # noqa: BLE001 - offline, rate limit: say so, do not guess
            failed.append(app_id)
            continue
        if version_key(latest) > version_key(have):
            found.append({"id": app_id, "name": name, "installed": have, "latest": latest})
    have = (codex_have or codex_version)()                         # Codex is a plain binary: ask it for its version
    if have:
        try:
            latest = (codex or codex_release)()["version"]
            if version_key(latest) > version_key(have):
                found.append({"id": "codex", "name": "Codex", "installed": have, "latest": latest})
        except Exception:  # noqa: BLE001
            failed.append("codex")
    return found, failed


def apt_remove_steps(package, pm):
    return [{"root": True, "sh": f"set -u\napt-get purge -y {package}\n"}] if pm == "apt-get" else []


# ---- Visual Studio Code: Microsoft's apt repository, key fingerprint checked ----
VSCODE_PAGE = "https://code.visualstudio.com/docs/setup/linux"
VSCODE_KEY_URL = "https://packages.microsoft.com/keys/microsoft.asc"
VSCODE_FPR = "BC528686B50D79E339D3721CEB3E94ADBE1229CF"          # Microsoft (Release signing); also in the system's microsoft.gpg
VSCODE_KEYRING = "/usr/share/keyrings/microsoft.gpg"
VSCODE_LIST = "/etc/apt/sources.list.d/vscode.sources"


def vscode_steps(pm, arch, proto="=https", keyring=None, listfile=None, fpr=None, url=None):
    if pm != "apt-get" or arch not in ("amd64", "arm64", "x86_64", "aarch64"):
        return [], {"manual": VSCODE_PAGE}
    q = shlex.quote
    keyring, listfile, fpr, url = keyring or VSCODE_KEYRING, listfile or VSCODE_LIST, fpr or VSCODE_FPR, url or VSCODE_KEY_URL
    sh = f"""set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get install -y curl gnupg ca-certificates || (apt-get update && apt-get install -y curl gnupg ca-certificates)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
curl -fsSL --proto '{proto}' --tlsv1.2 -o "$TMP/key.asc" {q(url)}
mkdir -m700 "$TMP/gnupg"
FPR=$(gpg --homedir "$TMP/gnupg" --show-keys --with-colons "$TMP/key.asc" | awk -F: '$1=="fpr"{{print $10; exit}}')
if [ "$FPR" != "{fpr}" ]; then echo "KEY FINGERPRINT MISMATCH: $FPR - nothing was installed" >&2; exit 1; fi
echo "Key fingerprint OK: $FPR"
gpg --homedir "$TMP/gnupg" --dearmor < "$TMP/key.asc" > "$TMP/key.gpg"
install -D -m644 "$TMP/key.gpg" {q(keyring)}
cat > {q(listfile)} <<'EOF'
Types: deb
URIs: https://packages.microsoft.com/repos/code
Suites: stable
Components: main
Architectures: amd64,arm64,armhf
Signed-By: {keyring}
EOF
apt-get update
apt-get install -y code
"""
    return [{"root": True, "sh": sh}], {"fingerprint": fpr, "url": url, "key": keyring}

def vscode_remove_steps(pm, sources_dir="/etc/apt/sources.list.d", keyring=None, listfile=None):
    """Purge `code`, then remove Microsoft's source file for it (and the key when nothing else in apt's sources uses it):
    a system without VS Code should not keep checking Microsoft's repository."""
    if pm != "apt-get":
        return []
    q = shlex.quote
    keyring, listfile = keyring or VSCODE_KEYRING, listfile or VSCODE_LIST
    sh = f"""set -u
apt-get purge -y code
if ! dpkg -s code-insiders >/dev/null 2>&1; then
  rm -f {q(listfile)} {q(sources_dir)}/vscode.list
  if ! grep -rqs {q(os.path.basename(keyring))} {q(sources_dir)} /etc/apt/sources.list 2>/dev/null; then rm -f {q(keyring)}; fi
fi
apt-get update || true
"""
    return [{"root": True, "sh": sh}]

# ---- the user's own data of these programs: only ever offered, never removed silently ----


def _size(path):
    total = 0
    for dirpath, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(dirpath, f)).st_size
            except OSError:
                pass
    return total


def data_paths(app_ids, home=None):
    """-> [(path, bytes)]: the folders / files of these programs that really exist in the home folder (nothing is touched)."""
    home = os.path.realpath(home or os.path.expanduser("~"))
    out, seen = [], set()
    for app_id in app_ids:
        flatpak_data = [f"~/.var/app/{FLATPAK_IDS[app_id]}"] if app_id in FLATPAK_IDS else []
        for p in DATA_DIRS.get(app_id, []) + flatpak_data:
            path = os.path.join(home, p[2:])
            if path in seen or not os.path.lexists(path):
                continue
            seen.add(path)
            out.append((path, os.lstat(path).st_size if os.path.isfile(path) or os.path.islink(path) else _size(path)))
    return out


def remove_data(paths, home=None):
    """Delete the given paths, but only those that lie inside the home folder (a symlink is removed itself, never followed).
    -> (removed, [(path, error)])"""
    home = os.path.realpath(home or os.path.expanduser("~"))
    done, failed = [], []
    for path in paths:
        parent = os.path.realpath(os.path.dirname(path))
        if not (parent == home or parent.startswith(home + os.sep)):      # inside the home folder only (so never the folder itself)
            failed.append((path, "outside the home folder - not touched"))
            continue
        try:
            if os.path.islink(path) or os.path.isfile(path):
                os.unlink(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
            else:
                continue
            done.append(path)
        except OSError as e:
            failed.append((path, str(e)))
    return done, failed


# ---- VirtualBox: Oracle's own apt repository (https://www.virtualbox.org/wiki/Linux_Downloads), key fingerprint checked ----
VBOX_PAGE = "https://www.virtualbox.org/wiki/Linux_Downloads"
VBOX_KEY_URL = "https://www.virtualbox.org/download/oracle_vbox_2016.asc"
VBOX_FPR = "B9F8D658297AF3EFC18D5CDFA2F683C52980AECF"            # "Oracle Corporation (VirtualBox archive signing key)"
VBOX_KEYRING = "/usr/share/keyrings/oracle-virtualbox-2016.gpg"
VBOX_LIST = "/etc/apt/sources.list.d/virtualbox.list"
VBOX_PACKAGE = "virtualbox-7.2"
VBOX_CODENAMES = ("resolute", "questing", "plucky", "noble", "jammy", "trixie", "bookworm", "bullseye")   # what Oracle publishes
VBOX_NOTES = ("Log out and in once: your user was added to the vboxusers group (needed for USB). With Secure Boot on, the "
              "kernel modules must be signed: the installer of the dkms package offers to enrol a key on the next reboot.")


def virtualbox_steps(pm, arch, proto="=https", keyring=None, listfile=None, fpr=None, url=None, codenames=None, osrelease="/etc/os-release"):
    """One administrator step: Oracle's key is downloaded, its fingerprint compared (abort on a mismatch, nothing written), the
    repository for THIS release (Linux Mint counts as its Ubuntu base) registered, then apt installs virtualbox-7.2 with dkms and
    kernel headers, and the user who asked is added to vboxusers. x86-64 Debian / Ubuntu / Mint only; elsewhere the page."""
    if pm != "apt-get" or arch not in X86:
        return [], {"manual": VBOX_PAGE}
    q = shlex.quote
    keyring, listfile, fpr, url = keyring or VBOX_KEYRING, listfile or VBOX_LIST, fpr or VBOX_FPR, url or VBOX_KEY_URL
    names = " ".join(codenames or VBOX_CODENAMES)
    sh = f"""set -eu
export DEBIAN_FRONTEND=noninteractive
. {q(osrelease)}
CN="${{UBUNTU_CODENAME:-${{VERSION_CODENAME:-}}}}"
case " {names} " in *" $CN "*) ;; *) echo "VirtualBox is not published for '$CN' ({names}) - see {VBOX_PAGE}" >&2; exit 1;; esac
apt-get install -y curl gnupg ca-certificates || (apt-get update && apt-get install -y curl gnupg ca-certificates)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
curl -fsSL --proto '{proto}' --tlsv1.2 -o "$TMP/key.asc" {q(url)}
mkdir -m700 "$TMP/gnupg"
FPR=$(gpg --homedir "$TMP/gnupg" --show-keys --with-colons "$TMP/key.asc" | awk -F: '$1=="fpr"{{print $10; exit}}')
if [ "$FPR" != "{fpr}" ]; then echo "KEY FINGERPRINT MISMATCH: $FPR - nothing was installed" >&2; exit 1; fi
echo "Key fingerprint OK: $FPR"
gpg --homedir "$TMP/gnupg" --dearmor < "$TMP/key.asc" > "$TMP/key.gpg"
install -D -m644 "$TMP/key.gpg" {q(keyring)}
printf 'deb [arch=amd64 signed-by=%s] https://download.virtualbox.org/virtualbox/debian %s contrib\n' {q(keyring)} "$CN" > {q(listfile)}
apt-get update
apt-get install -y dkms "linux-headers-$(uname -r)" || echo "(kernel headers for $(uname -r) not installed: install them, then run: sudo dpkg-reconfigure {VBOX_PACKAGE})"
apt-get install -y {VBOX_PACKAGE}
if [ -n "${{PKEXEC_UID:-}}" ]; then
  U=$(getent passwd "$PKEXEC_UID" | cut -d: -f1)
  [ -n "$U" ] && usermod -aG vboxusers "$U" && echo "Added $U to the vboxusers group (log out and in once)."
fi
"""
    return [{"root": True, "sh": sh}], {"fingerprint": fpr, "url": url, "key": keyring, "package": VBOX_PACKAGE, "notes": VBOX_NOTES}


def virtualbox_remove_steps(pm, keyring=None, listfile=None):
    """Purge the package (it also stops running VMs' services), then drop the repository entry and key this installer added.
    Virtual machines and settings in your home folder are never touched here (the window asks about them separately)."""
    if pm != "apt-get":
        return []
    q = shlex.quote
    return [{"root": True, "sh": f"set -u\napt-get purge -y {VBOX_PACKAGE}\nrm -f {q(listfile or VBOX_LIST)} {q(keyring or VBOX_KEYRING)}\n"
                                 "apt-get update || true\n"}]


# ---- Filee (https://github.com/KnifeLemon/Filee, MIT): file converter, installed for the user by the project's own install.sh ----
# The release package (Linux x64 / ARM64 .tar.gz) is downloaded from GitHub, its SHA-256 is checked against the digest GitHub
# publishes for that exact file, and the package's own install.sh runs as the USER (no administrator password at all):
# files go to ~/.local/share/filee/application, the `filee` command to ~/.local/bin, a launcher to ~/.local/share/applications,
# and on GNOME a Shell extension (the "donut at the cursor" on Wayland). Filee updates itself afterwards.
FILEE_REPO = "KnifeLemon/Filee"
FILEE_API = f"https://api.github.com/repos/{FILEE_REPO}/releases/latest"
FILEE_PAGE = f"https://github.com/{FILEE_REPO}/releases/latest"
FILEE_NOTES = ("Hold Ctrl and drag files to open the donut of formats at the cursor (needs X11; on Wayland use the drop zone or the "
               "file manager's right-click menu). Command line: filee convert photo.heic --to jpg. Filee updates itself.")


def filee_release(fetch=fetch_json):
    """-> {'tag', 'version', 'assets': {name: {'url', 'size', 'sha256'}}} for Filee's latest GitHub release."""
    data = fetch(FILEE_API)
    assets = {}
    for a in data.get("assets", []):
        digest = a.get("digest") or ""
        assets[a["name"]] = {"url": a["browser_download_url"], "size": int(a.get("size", 0)),
                             "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else ""}
    tag = data["tag_name"]
    return {"tag": tag, "version": tag.lstrip("v"), "assets": assets}


def filee_asset(release, arch):
    """The Linux package for this CPU (x64 / arm64) with a published SHA-256, or None."""
    kind = "x64" if arch in X86 else "arm64" if arch in ("arm64", "aarch64") else None
    if not kind:
        return None
    name = f"Filee-{release['version']}-linux-{kind}.tar.gz"
    a = release["assets"].get(name)
    return dict(a, name=name) if a and a["sha256"] else None


def filee_steps(release, arch, cache_dir=None):
    """-> (steps, info). Both steps run as the user. 1: download + SHA-256 gate. 2: unpack, check it is Filee, run its install.sh
    (--upgrade when an installation is already there), always remove the download and the unpacked copy afterwards."""
    asset = filee_asset(release, arch)
    if not asset:
        return [], {"manual": FILEE_PAGE, "version": release["version"]}
    d = os.path.expanduser(cache_dir or CACHE)
    q = shlex.quote
    tar, work = os.path.join(d, asset["name"]), os.path.join(d, "filee-unpacked")
    install = f"""set -eu
trap 'rm -rf {q(work)} {q(tar)}' EXIT
rm -rf {q(work)}
mkdir -p {q(work)}
tar -xzf {q(tar)} -C {q(work)}
PKG=$(ls -d {q(work)}/*/ | head -n 1)
[ -f "${{PKG}}install.sh" ] && [ -f "${{PKG}}Filee" ] && [ -f "${{PKG}}filee-cli" ] || {{ echo "the download does not look like Filee - nothing was installed" >&2; exit 1; }}
DATA="${{XDG_DATA_HOME:-$HOME/.local/share}}"
# the upgrade asks the running copy to quit (a .NET program): the invariant-culture switch keeps that working where ICU is missing
if [ -f "$DATA/filee/application/.filee-package" ]; then DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 sh "${{PKG}}install.sh" --upgrade; else sh "${{PKG}}install.sh"; fi
"""
    steps = [{"root": False, "sh": download_script(asset, cache_dir)}, {"root": False, "sh": install}]
    return steps, {"version": release["version"], "file": asset["name"], "mb": round(asset["size"] / 1048576), "url": asset["url"],
                   "sha256": asset["sha256"], "source": "github.com/" + FILEE_REPO, "notes": FILEE_NOTES}


def filee_remove_steps():
    """The package's own uninstall.sh (as the user): removes the application, the `filee` link, the launcher and the GNOME extension;
    settings and results are kept (the window asks about personal data separately). If that script fails (its cleanup stops on
    a missing Thunar 'send to' folder), the same four things are removed here, each only when it carries Filee's own marker."""
    sh = """set -u
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP="$DATA/filee/application"
if [ ! -x "$APP/uninstall.sh" ]; then echo "Filee is not installed."; exit 0; fi
if DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 sh "$APP/uninstall.sh"; then exit 0; fi
echo "Filee's own uninstaller stopped; removing what it installed (only items carrying Filee's marker)." >&2
[ -f "$APP/.filee-package" ] && [ "$(tr -d '\r\n' < "$APP/.filee-package")" = "com.filee.app" ] || { echo "not a Filee installation - left alone" >&2; exit 1; }
EXT="$DATA/gnome-shell/extensions/filee-donut@filee.sh"
if [ -f "$EXT/.filee-package" ] && [ "$(tr -d '\r\n' < "$EXT/.filee-package")" = "com.filee.app" ]; then
  command -v gnome-extensions >/dev/null 2>&1 && gnome-extensions disable filee-donut@filee.sh >/dev/null 2>&1
  rm -rf -- "$EXT"
fi
[ -L "$HOME/.local/bin/filee" ] && [ "$(readlink "$HOME/.local/bin/filee")" = "$APP/filee-cli" ] && rm -- "$HOME/.local/bin/filee"
DESK="$DATA/applications/com.filee.app.desktop"
[ -f "$DESK" ] && grep -q '^X-Filee-Managed=true$' "$DESK" && rm -- "$DESK"
rm -rf -- "$APP"
echo "Filee was removed. Your settings and conversion results were kept."
"""
    return [{"root": False, "sh": sh}]


def filee_installed(data_home=None):
    """True when Filee's own install marker is in place."""
    data = data_home or os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.isfile(os.path.join(data, "filee", "application", ".filee-package"))


# ---- Codex CLI (https://github.com/openai/codex, Apache-2.0): OpenAI's coding agent for the terminal ----
# One static Linux binary from the project's GitHub release. Installed for the user (no administrator password) as
# ~/.local/bin/codex after the SHA-256 of the download matches GitHub's digest for that exact file. A small marker file
# records that THIS installer put it there, so removal and upgrade never touch a codex that came from npm / brew / a package.
CODEX_REPO = "openai/codex"
CODEX_API = f"https://api.github.com/repos/{CODEX_REPO}/releases/latest"
CODEX_PAGE = "https://github.com/openai/codex#installing-and-running-codex-cli"
CODEX_MARKER = os.path.join("~", ".local", "share", "linux-scripts", "codex.installed")
CODEX_NOTES = ("Start it in a terminal (the \"Codex\" shortcut, or the command: codex). First start: sign in with your ChatGPT account "
               "or an API key - you type that into Codex itself, this installer never sees it. Codex works in the folder you start it in.")


def codex_release(fetch=fetch_json):
    """-> {'tag', 'version', 'assets'}; the tag is 'rust-v0.166.0', the version '0.166.0'."""
    data = fetch(CODEX_API)
    assets = {}
    for a in data.get("assets", []):
        digest = a.get("digest") or ""
        assets[a["name"]] = {"url": a["browser_download_url"], "size": int(a.get("size", 0)),
                             "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else ""}
    tag = data["tag_name"]
    return {"tag": tag, "version": re.sub(r"^(rust-)?v", "", tag), "assets": assets}


def codex_asset(release, arch):
    """codex-<cpu>-unknown-linux-musl.tar.gz (a static binary, any distribution) with a published SHA-256, or None."""
    cpu = "x86_64" if arch in X86 else "aarch64" if arch in ("arm64", "aarch64") else None
    if not cpu:
        return None
    name = f"codex-{cpu}-unknown-linux-musl.tar.gz"
    a = release["assets"].get(name)
    return dict(a, name=name, cpu=cpu) if a and a["sha256"] else None


def codex_steps(release, arch, cache_dir=None, bin_dir=None, marker=None):
    """-> (steps, info); both steps run as the user. 1: download + SHA-256 gate. 2: unpack, expect exactly the one binary, check
    it answers --version, install it as ~/.local/bin/codex and write the marker. Refuses to replace a codex this installer
    did not install (no marker) - remove or rename that one first."""
    asset = codex_asset(release, arch)
    if not asset:
        return [], {"manual": CODEX_PAGE, "version": release["version"]}
    d = os.path.expanduser(cache_dir or CACHE)
    q = shlex.quote
    tar, work = os.path.join(d, asset["name"]), os.path.join(d, "codex-unpacked")
    target = os.path.join(os.path.expanduser(bin_dir or os.path.join("~", ".local", "bin")), "codex")
    mark = os.path.expanduser(marker or CODEX_MARKER)
    inner = f"codex-{asset['cpu']}-unknown-linux-musl"
    install = f"""set -eu
trap 'rm -rf {q(work)} {q(tar)}' EXIT
if [ -e {q(target)} ] || [ -L {q(target)} ]; then
  [ -f {q(mark)} ] || {{ echo "{target} already exists and was not installed by this installer - remove or rename it first" >&2; exit 1; }}
fi
rm -rf {q(work)}; mkdir -p {q(work)}
tar -xzf {q(tar)} -C {q(work)}
[ "$(ls -A {q(work)} | wc -l)" = 1 ] && [ -f {q(work)}/{inner} ] || {{ echo "the download does not look like Codex - nothing was installed" >&2; exit 1; }}
chmod 755 {q(work)}/{inner}
{q(work)}/{inner} --version | grep -q codex || {{ echo "the downloaded program does not answer like Codex - nothing was installed" >&2; exit 1; }}
mkdir -p {q(os.path.dirname(target))} {q(os.path.dirname(mark))}
cp {q(work)}/{inner} {q(target)}.new && mv -f {q(target)}.new {q(target)}
printf '%s\\n' {q(release['version'])} > {q(mark)}
echo "Installed $({q(target)} --version) at {target}"
"""
    steps = [{"root": False, "sh": download_script(asset, cache_dir)}, {"root": False, "sh": install}]
    return steps, {"version": release["version"], "file": asset["name"], "mb": round(asset["size"] / 1048576), "url": asset["url"],
                   "sha256": asset["sha256"], "source": "github.com/" + CODEX_REPO, "notes": CODEX_NOTES, "target": target}


def codex_remove_steps(bin_dir=None, marker=None):
    """Remove ~/.local/bin/codex and the marker - only when the marker says this installer installed it."""
    target = os.path.join(os.path.expanduser(bin_dir or os.path.join("~", ".local", "bin")), "codex")
    mark = os.path.expanduser(marker or CODEX_MARKER)
    q = shlex.quote
    sh = f"""set -u
if [ -f {q(mark)} ]; then rm -f {q(target)} {q(mark)}; echo "Codex was removed. Your Codex settings, sign-in and history (~/.codex) were kept."
elif [ -e {q(target)} ] || command -v codex >/dev/null 2>&1; then echo "Codex is installed another way (npm, brew, a package) - remove it the same way; nothing was changed here."
else echo "Codex is not installed."; fi
"""
    return [{"root": False, "sh": sh}]


def codex_version(run=subprocess.run, which=shutil.which, path=None):
    """'0.166.0' from `codex --version` ('codex-cli 0.166.0'), or None when codex is not installed / does not answer."""
    exe = path or which("codex") or os.path.expanduser("~/.local/bin/codex")
    if not os.path.isfile(exe):
        return None
    try:
        r = run([exe, "--version"], capture_output=True, text=True, timeout=20)
    except Exception:  # noqa: BLE001
        return None
    m = re.search(r"(\d+(?:\.\d+)+)", r.stdout) if r.returncode == 0 else None
    return m.group(1) if m else None


def codex_installed(which=shutil.which):
    return bool(which("codex") or os.path.isfile(os.path.expanduser("~/.local/bin/codex")))


# ---- Flutter SDK (includes Dart) and a standalone Dart SDK ----
# Flutter: Google's own release archive (flutter_linux_<version>-stable.tar.xz, ~1.6 GB, with its prebuilt Dart SDK and engine
# artifacts). Its SHA-256 comes from Google's release manifest (releases_linux.json) and is checked before anything is unpacked.
# Prerequisites from https://docs.flutter.dev (curl git unzip xz zip + GLU) are installed from the distribution's repositories,
# in ONE administrator step, only when something is missing. The SDK itself goes into ~/development/flutter (the docs' place; the
# SDK must be writable by you: it updates itself with `flutter upgrade`) and `flutter` / `dart` are linked into ~/.local/bin, so no
# shell startup file is edited. The Dart that ships inside Flutter is the full Dart SDK, so that is the "Dart" most people want.
FLUTTER_MANIFEST = "https://storage.googleapis.com/flutter_infra_release/releases/releases_linux.json"
FLUTTER_PAGE = "https://docs.flutter.dev/install/manual"
FLUTTER_TOOLS = ("curl", "git", "unzip", "xz", "zip")                           # commands the docs list (xz-utils provides xz)
FLUTTER_PREREQ = {                                                              # package names checked in real distributions
    "apt-get": ["curl", "git", "unzip", "xz-utils", "zip", "libglu1-mesa"],
    "dnf": ["curl", "git", "unzip", "xz", "zip", "mesa-libGLU"],
    "pacman": ["curl", "git", "unzip", "xz", "zip", "glu"],
    "zypper": ["curl", "git", "unzip", "xz", "zip", "libGLU1"]}
FLUTTER_MIN_FREE_GB = 6
FLUTTER_NOTES = ("Open a NEW terminal, then run: flutter doctor. Checkmarks are needed only for the platforms you target (Chrome = web, "
                 "Linux desktop); ignore warnings about Android Studio / Xcode until you need them. The Dart commands (dart, dart pub) "
                 "are included. Update later with: flutter upgrade. If VS Code is installed, the Flutter extension (it brings the Dart "
                 "extension) is added too.")


def flutter_release(fetch=fetch_json, size=None):
    """-> {'version', 'dart', 'name', 'url', 'sha256', 'size'} for the current STABLE Linux release in Google's manifest."""
    data = fetch(FLUTTER_MANIFEST)
    cur = data["current_release"]["stable"]
    r = next(x for x in data["releases"] if x["hash"] == cur and x["channel"] == "stable")
    url = data["base_url"].rstrip("/") + "/" + r["archive"]
    n = 0
    try:
        n = int((size or _head_size)(url))
    except Exception:  # noqa: BLE001 - the size is only for the dialog
        pass
    return {"version": r["version"], "dart": r.get("dart_sdk_version", ""), "name": os.path.basename(r["archive"]), "url": url,
            "sha256": r["sha256"], "size": n, "arch": r.get("dart_sdk_arch", "x64")}


def _head_size(url, timeout=20):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "linux-scripts-installer"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.headers.get("Content-Length", 0)


def flutter_missing(which=shutil.which, glu=None):
    """The prerequisites that are not there: command names, plus 'GLU' when libGLU is not known to the linker."""
    out = [c for c in FLUTTER_TOOLS if not which(c)]
    if glu is None:
        try:
            glu = "libGLU.so.1" in subprocess.run(["ldconfig", "-p"], capture_output=True, text=True, timeout=20).stdout
        except Exception:  # noqa: BLE001
            glu = False
    if not glu:
        out.append("GLU")
    return out


def flutter_steps(release, arch, pm, missing, cache_dir=None, dev_dir=None, bin_dir=None):
    """-> (steps, info). [root: prerequisites, only when 'missing' is not empty and this package manager is known] +
    [user: disk-space check] + [user: download + SHA-256 gate] + [user: unpack to ~/development/flutter, link flutter and dart into
    ~/.local/bin, first start (it fetches nothing more: the archive carries its Dart SDK), VS Code extension when VS Code is there]."""
    if arch not in X86 or release.get("arch", "x64") != "x64":
        return [], {"manual": FLUTTER_PAGE, "version": release["version"]}
    q = shlex.quote
    d = os.path.expanduser(cache_dir or CACHE)
    dev = os.path.expanduser(dev_dir or os.path.join("~", "development"))
    binp = os.path.expanduser(bin_dir or os.path.join("~", ".local", "bin"))
    sdk, tar = os.path.join(dev, "flutter"), os.path.join(d, release["name"])
    mark = os.path.join(sdk, ".linux-scripts-flutter")
    steps, prereq = [], None
    names = FLUTTER_PREREQ.get(pm)
    if missing and names:
        fmt = _INSTALL[pm]
        prereq = " ".join(names)
        steps.append({"root": True, "sh": "set -eu\nexport DEBIAN_FRONTEND=noninteractive\n" + fmt.format(p=prereq) + "\n"})
    steps.append({"root": False, "sh": f"""set -eu
mkdir -p {q(d)} {q(dev)}
need={FLUTTER_MIN_FREE_GB}
for dir in {q(d)} {q(dev)}; do
  set -- $(df -Pk "$dir" | tail -n 1)
  free=$(( $4 / 1048576 ))
  [ "$free" -ge "$need" ] || {{ echo "only ${{free}} GB free where $dir is - Flutter needs about $need GB (download + unpacked SDK). Free some space and try again." >&2; exit 1; }}
done
echo "free space OK"
"""})
    steps.append({"root": False, "sh": download_script({"name": release["name"], "url": release["url"], "sha256": release["sha256"]}, cache_dir)})
    install = f"""set -eu
trap 'rm -f {q(tar)}' EXIT
SDK={q(sdk)}
MARK={q(mark)}
if [ -e "$SDK" ] || [ -L "$SDK" ]; then
  [ -f "$MARK" ] || {{ echo "$SDK already exists and was not installed by this installer - rename it first (or use that one)" >&2; exit 1; }}
  echo "Flutter is already installed here ($(cat "$MARK")): keeping it - update it with: flutter upgrade"
else
  mkdir -p {q(dev)}
  tar -xJf {q(tar)} --no-same-owner -C {q(dev)}
  [ -x "$SDK/bin/flutter" ] || {{ echo "the archive did not contain flutter/bin/flutter - nothing was installed" >&2; rm -rf "$SDK"; exit 1; }}
  printf '%s\n' {q(release['version'])} > "$MARK"
fi
mkdir -p {q(binp)}
for c in flutter dart; do
  L={q(binp)}/$c
  if [ -L "$L" ] && [ "$(readlink "$L")" = "$SDK/bin/$c" ]; then continue; fi
  if [ -e "$L" ] || [ -L "$L" ]; then echo "$L exists and is something else - left alone (use $SDK/bin/$c)" >&2; continue; fi
  ln -s "$SDK/bin/$c" "$L"
done
"$SDK/bin/flutter" --version || echo "(flutter --version did not finish - run: flutter doctor)"
if command -v code >/dev/null 2>&1; then code --install-extension Dart-Code.flutter || echo "(the VS Code extension could not be added now - add 'Flutter' in VS Code's Extensions view)"; fi
echo "Flutter is ready in $SDK"
"""
    steps.append({"root": False, "sh": install})
    return steps, {"version": release["version"], "dart": release["dart"], "file": release["name"], "mb": round(release["size"] / 1048576),
                   "sha256": release["sha256"], "source": "storage.googleapis.com/flutter_infra_release", "sdk": sdk,
                   "prereq": prereq, "missing": missing, "min_gb": FLUTTER_MIN_FREE_GB, "notes": FLUTTER_NOTES}


def flutter_remove_steps(dev_dir=None, bin_dir=None):
    """Remove ~/development/flutter and the two links - only when the SDK carries this installer's marker. The prerequisites
    (curl, git, ...) stay: other programs use them. ~/.pub-cache and ~/.config/flutter are personal data (asked separately)."""
    q = shlex.quote
    sdk = os.path.join(os.path.expanduser(dev_dir or os.path.join("~", "development")), "flutter")
    binp = os.path.expanduser(bin_dir or os.path.join("~", ".local", "bin"))
    sh = f"""set -u
SDK={q(sdk)}
if [ ! -f "$SDK/.linux-scripts-flutter" ]; then
  if [ -e "$SDK" ] || command -v flutter >/dev/null 2>&1; then echo "Flutter is installed another way - remove it the same way; nothing was changed here."; else echo "Flutter is not installed."; fi
  exit 0
fi
for c in flutter dart; do
  L={q(binp)}/$c
  [ -L "$L" ] && [ "$(readlink "$L")" = "$SDK/bin/$c" ] && rm -f "$L"
done
rm -rf -- "$SDK"
rmdir {q(os.path.dirname(sdk))} 2>/dev/null || true
echo "Flutter was removed. The prerequisites (curl, git, ...), ~/.pub-cache and your projects were kept."
"""
    return [{"root": False, "sh": sh}]


def flutter_installed(dev_dir=None):
    return os.path.isfile(os.path.join(os.path.expanduser(dev_dir or os.path.join("~", "development")), "flutter", ".linux-scripts-flutter"))


def flutter_version(dev_dir=None):
    try:
        with open(os.path.join(os.path.expanduser(dev_dir or os.path.join("~", "development")), "flutter", ".linux-scripts-flutter")) as f:
            return f.read().strip() or None
    except OSError:
        return None


# standalone Dart SDK (for Dart without Flutter): Google's apt repository; ONLY the one signing key that is checked is put in the keyring
DART_KEY_URL = "https://dl-ssl.google.com/linux/linux_signing_key.pub"
DART_FPR = "EB4C1BFD4F042F6DDDCCEC917721F63BD38B4796"                 # "Google Inc. (Linux Packages Signing Authority)"
DART_KEYRING = "/usr/share/keyrings/dart-archive-keyring.gpg"
DART_LIST = "/etc/apt/sources.list.d/dart_stable.list"
DART_PAGE = "https://dart.dev/get-dart"


def dart_steps(pm, arch, proto="=https", keyring=None, listfile=None, fpr=None, url=None):
    """One administrator step: Google's key file is downloaded, imported into a temporary keyring, the fingerprint of the key
    we trust is compared (abort on mismatch), and only THAT key is exported into the apt keyring (the file carries several).
    Then the repository is registered and apt installs `dart`. Debian / Ubuntu / Mint on x86-64 or ARM64."""
    if pm != "apt-get" or arch not in (*X86, "arm64", "aarch64"):
        return [], {"manual": DART_PAGE}
    q = shlex.quote
    keyring, listfile, fpr, url = keyring or DART_KEYRING, listfile or DART_LIST, fpr or DART_FPR, url or DART_KEY_URL
    sh = f"""set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get install -y curl gnupg ca-certificates || (apt-get update && apt-get install -y curl gnupg ca-certificates)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
curl -fsSL --proto '{proto}' --tlsv1.2 -o "$TMP/key.pub" {q(url)}
mkdir -m700 "$TMP/gnupg"
gpg --homedir "$TMP/gnupg" --batch --import "$TMP/key.pub" 2>/dev/null || true
if ! gpg --homedir "$TMP/gnupg" --with-colons --list-keys {fpr} 2>/dev/null | grep -q "^fpr:::::::::{fpr}:"; then
  echo "KEY FINGERPRINT MISMATCH: {fpr} is not in the downloaded file - nothing was installed" >&2; exit 1
fi
echo "Key fingerprint OK: {fpr}"
gpg --homedir "$TMP/gnupg" --export {fpr} > "$TMP/dart.gpg"
install -D -m644 "$TMP/dart.gpg" {q(keyring)}
printf 'deb [signed-by=%s arch=%s] https://storage.googleapis.com/download.dartlang.org/linux/debian stable main\\n' {q(keyring)} "$(dpkg --print-architecture)" > {q(listfile)}
apt-get update
apt-get install -y dart
"""
    return [{"root": True, "sh": sh}], {"fingerprint": fpr, "url": url, "key": keyring}


def dart_remove_steps(pm, keyring=None, listfile=None):
    if pm != "apt-get":
        return []
    q = shlex.quote
    return [{"root": True, "sh": f"set -u\napt-get purge -y dart\nrm -f {q(listfile or DART_LIST)} {q(keyring or DART_KEYRING)}\napt-get update || true\n"}]


# ---- Discord: the publisher's own .deb (https://discord.com/download).  Discord publishes no checksum, so only HTTPS protects it ----
DISCORD_URL = "https://discord.com/api/download?platform=linux&format=deb"
DISCORD_PAGE = "https://discord.com/download"


def discord_steps(pm, arch, cache_dir=None, proto="=https", url=None):
    if pm != "apt-get" or arch not in X86:
        return [], {"manual": DISCORD_PAGE}
    d = os.path.expanduser(cache_dir or CACHE)
    path = os.path.join(d, "discord.deb")
    q = shlex.quote
    dl = f"""set -eu
command -v curl >/dev/null 2>&1 || {{ echo "curl is not installed (Debian/Ubuntu: sudo apt install curl)" >&2; exit 1; }}
mkdir -p {q(d)}
trap 'rm -f {q(path)}.part' EXIT
curl -fL --progress-bar --proto '{proto}' --proto-redir '{proto}' --tlsv1.2 -o {q(path)}.part {q(url or DISCORD_URL)}
dpkg-deb -f {q(path)}.part Package | grep -qx discord || {{ echo "the download is not the Discord package - nothing was installed" >&2; exit 1; }}
mv {q(path)}.part {q(path)}
"""
    return [{"root": False, "sh": dl},
            {"root": True, "sh": f"set -eu\nexport DEBIAN_FRONTEND=noninteractive\napt-get install -y {q(path)}\n"},
            {"root": False, "sh": f"rm -f {q(path)}\n"}], {"url": DISCORD_URL, "source": "discord.com"}


# programs that simply come from the distribution's own repositories (no download, nothing to verify by hand)
_INSTALL = {"apt-get": "apt-get install -y {p}", "dnf": "dnf install -y {p}", "yum": "yum install -y {p}",
            "pacman": "pacman -S --noconfirm {p}", "zypper": "zypper --non-interactive install {p}",
            "apk": "apk add {p}", "xbps-install": "xbps-install -y {p}"}
_REMOVE = {"apt-get": "apt-get purge -y {p}", "dnf": "dnf remove -y {p}", "yum": "yum remove -y {p}",
           "pacman": "pacman -R --noconfirm {p}", "zypper": "zypper --non-interactive remove {p}",
           "apk": "apk del {p}", "xbps-install": "xbps-remove -y {p}"}


def package_name(app, pm):
    """The distribution's package for this program under this package manager (lscommon.PKG_FOR), or None."""
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (os.path.join(here, "..", "common"), os.path.join(here, "..", "lib", "linux-scripts"),
              "/usr/local/lib/linux-scripts", "/usr/lib/linux-scripts"):
        if os.path.isfile(os.path.join(d, "lscommon.py")) and d not in sys.path:
            sys.path.append(d)
    from lscommon import PKG_FOR
    return PKG_FOR.get(PACKAGE_APPS[app]["cmd"], {}).get(pm)


def package_steps(app, pm, remove=False):
    """[{'root': True, 'sh': ...}] installing (or removing) the distribution's package, [] when unknown here.
    A program can name a fallback package for a package manager (programs.json 'fallback'): tried when the first is not in
    this distribution's repositories (Debian has unrar only in non-free: unrar-free instead); removal takes whichever is installed."""
    pkg = package_name(app, pm)
    fmt = (_REMOVE if remove else _INSTALL).get(pm)
    if not pkg or not fmt:
        return []
    other = PACKAGE_APPS[app].get("fallback", {}).get(pm)
    if other and pm == "apt-get":
        names = f"{shlex.quote(pkg)} {shlex.quote(other)}"
        if remove:
            sh = (f"set -u\npk=\"\"\nfor p in {names}; do dpkg -s \"$p\" >/dev/null 2>&1 && pk=\"$pk $p\"; done\n"
                  f"[ -n \"$pk\" ] && {fmt.format(p='$pk')} || true\n")
        else:
            sh = f"set -u\n{fmt.format(p=shlex.quote(pkg))} || {fmt.format(p=shlex.quote(other))}\n"
        return [{"root": True, "sh": sh}]
    return [{"root": True, "sh": "set -eu\n" + fmt.format(p=shlex.quote(pkg)) + "\n"}]


def package_installed(app, which=shutil.which):
    return bool(which(PACKAGE_APPS[app]["cmd"]))


# ---- GIS catalogue (installer/gis.json): OSGeo projects and community projects ----
GIS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gis.json")
GIS_PMS = {"apt-get", "dnf", "pacman", "zypper"}                       # the package managers the names were checked for


def load_gis(path=None):
    """gis.json, checked: every entry needs id, category (known), name and url; packages only for known package managers."""
    with open(path or GIS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    seen = set()
    for sec in data["sections"]:
        if not all(sec.get("title", {}).get(lang) for lang in ("en", "ka")):
            raise ValueError(f"gis.json: section {sec.get('id')}: title needs en and ka")
        for p in sec["programs"]:
            i = p.get("id", "?")
            if i in seen:
                raise ValueError(f"gis.json: {i} appears twice")
            seen.add(i)
            if p.get("category") not in data["categories"]:
                raise ValueError(f"gis.json: {i}: category must be one of {sorted(data['categories'])}")
            if not p.get("name") or not str(p.get("url", "")).startswith("https://"):
                raise ValueError(f"gis.json: {i}: needs a name and an https url")
            for pm, names in p.get("packages", {}).items():
                if pm not in GIS_PMS or not names or not all(isinstance(n, str) and n and " " not in n for n in names):
                    raise ValueError(f"gis.json: {i}: bad packages for '{pm}'")
    return data


def gis_programs(data=None):
    """Flat {id: entry} over both sections."""
    data = data or load_gis()
    return {p["id"]: p for sec in data["sections"] for p in sec["programs"]}


def gis_packages(item, pm):
    """The distribution packages for this system, or None (link-only entry, or no package under this package manager)."""
    return item.get("packages", {}).get(pm) or None


def gis_steps(item, pm, remove=False):
    """[{'root': True, 'sh': ...}] installing / removing the packages, [] when there is nothing to install here."""
    names = gis_packages(item, pm)
    fmt = (_REMOVE if remove else _INSTALL).get(pm)
    if not names or not fmt:
        return []
    return [{"root": True, "sh": "set -u\n" + fmt.format(p=" ".join(names)) + "\n"}]


def gis_installed(item, pm, run=subprocess.run, which=shutil.which):
    """True when every package of this entry is installed (dpkg / rpm / pacman), False otherwise or when unknown."""
    names = gis_packages(item, pm)
    if not names:
        return False
    for n in names:
        if pm == "apt-get" and which("dpkg-query"):
            cmd, ok = ["dpkg-query", "-W", "-f=${Status}", n], lambda r: r.stdout.startswith("install ok installed")
        elif pm in ("dnf", "zypper") and which("rpm"):
            cmd, ok = ["rpm", "-q", n], lambda r: True
        elif pm == "pacman" and which("pacman"):
            cmd, ok = ["pacman", "-Q", n], lambda r: True
        else:
            return False
        try:
            r = run(cmd, capture_output=True, text=True, timeout=30)
        except Exception:  # noqa: BLE001
            return False
        if r.returncode != 0 or not ok(r):
            return False
    return True



# ---- OpenGeos (https://github.com/opengeos): a catalogue shown as cards, links only ----
OPENGEOS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "opengeos.json")


def load_opengeos(path=None):
    """opengeos.json, checked: every section has en/ka titles and items with a name and an https url."""
    with open(path or OPENGEOS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    seen = set()
    for sec in data["sections"]:
        if sec["id"] in seen:
            raise ValueError(f"opengeos.json: section {sec['id']} appears twice")
        seen.add(sec["id"])
        if not all(sec.get("title", {}).get(lang) for lang in ("en", "ka")):
            raise ValueError(f"opengeos.json: section {sec['id']}: title needs en and ka")
        for it in sec["items"]:
            if not it.get("name") or not str(it.get("url", "")).startswith("https://"):
                raise ValueError(f"opengeos.json: {sec['id']}: every item needs a name and an https url")
    if not all(data.get("intro", {}).get(lang) for lang in ("en", "ka")):
        raise ValueError("opengeos.json: intro needs en and ka")
    return data


def opengeos_filter(data, needle="", section=None):
    """[(section, [items])] whose name / description / section title contains the text, optionally only one section id."""
    needle = needle.strip().lower()
    out = []
    for sec in data["sections"]:
        if section and sec["id"] != section:
            continue
        items = [it for it in sec["items"] if not needle or needle in (it["name"] + " " + it.get("description", "") + " " +
                                                                        sec["title"]["en"] + " " + sec["title"]["ka"]).lower()]
        if items:
            out.append((sec, items))
    return out



# ---- Flatpak (Flathub) for systems where the publisher's .deb / apt repository does not apply (Fedora, openSUSE, Arch ...) ----
# Flathub's own signed remote; installed for the user (no administrator password) once flatpak itself is there.
FLATHUB_REPO = "https://dl.flathub.org/repo/flathub.flatpakrepo"
FLATPAK_SETUP = "https://flatpak.org/setup/"


def flatpak_scopes(app_id, run=subprocess.run, which=shutil.which):
    """{'user', 'system'}: where this program is installed as a flatpak (empty when not, or when flatpak is missing)."""
    fid = FLATPAK_IDS.get(app_id)
    if not fid or not which("flatpak"):
        return set()
    out = set()
    for scope in ("user", "system"):
        try:
            if run(["flatpak", "info", f"--{scope}", fid], capture_output=True, text=True, timeout=30).returncode == 0:
                out.add(scope)
        except Exception:  # noqa: BLE001
            pass
    return out


def flatpak_steps(app_id, pm, have_flatpak, remove_scopes=None):
    """-> (steps, info). Install: [flatpak from the system's own repositories if missing (administrator)] + add Flathub for
    the user + install for the user.  Remove (remove_scopes given): uninstall in each scope it is installed in.
    steps is [] with info['manual'] when this program has no Flathub entry or flatpak cannot be installed here."""
    fid = FLATPAK_IDS.get(app_id)
    if not fid:
        return [], {"manual": FLATPAK_SETUP}
    q = shlex.quote
    if remove_scopes is not None:
        steps = []
        if "user" in remove_scopes:
            steps.append({"root": False, "sh": f"set -u\nflatpak uninstall -y --user {q(fid)}\n"})
        if "system" in remove_scopes:
            steps.append({"root": True, "sh": f"set -u\nflatpak uninstall -y --system {q(fid)}\n"})
        return steps, {"id": fid}
    steps = []
    if not have_flatpak:
        cmd = _INSTALL.get(pm)
        if not cmd:
            return [], {"manual": FLATPAK_SETUP}
        steps.append({"root": True, "sh": "set -eu\n" + cmd.format(p="flatpak") + "\n"})
    steps.append({"root": False, "sh": f"set -eu\nflatpak remote-add --user --if-not-exists flathub {q(FLATHUB_REPO)}\n"
                                       f"flatpak install -y --user flathub {q(fid)}\n"})
    return steps, {"id": fid, "needs_flatpak": not have_flatpak, "source": "flathub.org"}


# ---- what can be installed on THIS system, and how ----
ARM = ("arm64", "aarch64")
# the recipe of each kind: (package managers it works with, None = any; CPUs it works on, None = any) - tests/test_units.py
# checks this table against the recipes themselves
NATIVE = {
    "claude": ({"apt-get"}, (*X86, *ARM)), "vscode": ({"apt-get"}, (*X86, *ARM)), "virtualbox": ({"apt-get"}, X86),
    "dart": ({"apt-get"}, (*X86, *ARM)), "discord": ({"apt-get"}, X86), "etcher": ({"apt-get", "dnf", "zypper"}, X86),
    "brave": ({"apt-get", "dnf", "yum", "zypper", "pacman"}, None), "filee": (None, (*X86, *ARM)),
    "codex": (None, (*X86, *ARM)), "flutter": (None, X86), "github": ({"apt-get"}, None), "package": (None, None)}


def os_release(path="/etc/os-release"):
    """/etc/os-release as a dict ({} when unreadable)."""
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                k, sep, v = line.strip().partition("=")
                if sep:
                    out[k] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def system_summary(pm, arch, osr=None):
    """'Manjaro Linux - pacman, x86_64' for the window."""
    osr = os_release() if osr is None else osr
    return f"{osr.get('PRETTY_NAME') or osr.get('NAME') or 'Linux'} - {pm.replace('-get', '') or '?'}, {arch}"


def is_arch_family(osr=None):
    osr = os_release() if osr is None else osr
    return "arch" in (osr.get("ID", "") + " " + osr.get("ID_LIKE", "")).split()


def native_route(program, pm, arch):
    """True when the program's own recipe can install it with this package manager on this CPU."""
    kind = program["kind"]
    pms, cpus = NATIVE[kind]
    if kind == "package":
        return bool(package_name(program["id"], pm))
    if kind == "github":
        cpus = tuple(c for k, group in (("x86", X86), ("arm", ARM)) if k in program["asset"] for c in group)
    return (pms is None or pm in pms) and (cpus is None or arch in cpus)


def route(program, pm, arch):
    """-> (how, why).  how: 'native' (the program's own recipe), 'flatpak' (Flathub, for you only), 'aur' (Arch User Repository,
    built here) or 'none'; why (only for 'none'): 'cpu' = not offered for this processor, 'pm' = the publisher serves other
    distributions only."""
    if native_route(program, pm, arch):
        return "native", ""
    if program.get("flatpak") and arch in (*X86, *ARM) and (shutil.which("flatpak") or pm in _INSTALL):
        return "flatpak", ""
    if program.get("aur") and pm == "pacman" and arch in X86:
        return "aur", ""
    pms, cpus = NATIVE[program["kind"]]
    return "none", "cpu" if program["kind"] != "package" and (pms is None or pm in pms) else "pm"


# ---- the Arch User Repository (Arch, Manjaro, EndeavourOS ...): packages written by users, built on this computer ----
AUR_HOST = "https://aur.archlinux.org"
AUR_INFO = AUR_HOST + "/rpc/v5/info?arg[]={p}"
AUR_SNAPSHOT = AUR_HOST + "/cgit/aur.git/snapshot/{p}.tar.gz"
AUR_MAX_BYTES = 8 * 1024 * 1024


def aur_workdir(cache_dir=None):
    return os.path.join(os.path.expanduser(cache_dir or CACHE), "aur")


def aur_extract(data, dest, pkg):
    """Unpack an AUR snapshot (.tar.gz bytes) into dest/<pkg>: plain files and folders only, nothing outside the folder."""
    import io
    import tarfile
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    root = os.path.realpath(dest)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = tar.getmembers()
        for m in members:
            target = os.path.realpath(os.path.join(dest, m.name))
            if not (m.isfile() or m.isdir()) or not (target == root or target.startswith(root + os.sep)):
                raise ValueError(f"unsafe entry in the AUR archive: {m.name}")
            if not (m.name == pkg or m.name.startswith(pkg + "/")):
                raise ValueError(f"unexpected entry in the AUR archive: {m.name}")
            m.mode = 0o755 if m.isdir() else 0o644
        try:
            tar.extractall(dest, members=members, filter="data")      # every member was checked above; this is the second belt
        except TypeError:                                              # Python without extraction filters
            tar.extractall(dest, members=members)  # noqa: S202
    return os.path.join(dest, pkg)


def aur_fetch(pkg, cache_dir=None, opener=urllib.request.urlopen):
    """Download the AUR snapshot of a package and read what the user must see before anything is built.
    -> {'dir', 'meta', 'files': {'PKGBUILD': text, 'x.install': text}, 'sha256'}.  Raises on anything unexpected."""
    import hashlib

    def get(url, limit):
        with opener(urllib.request.Request(url, headers={"User-Agent": "linux-scripts"}), timeout=30) as r:
            data = r.read(limit + 1)
        if len(data) > limit:
            raise ValueError("the AUR answer is larger than expected")
        return data
    if not re.fullmatch(r"[a-z0-9][a-z0-9@._+-]*", pkg):
        raise ValueError(f"not an AUR package name: {pkg}")
    info = json.loads(get(AUR_INFO.format(p=pkg), 1 << 20).decode())
    found = [r for r in info.get("results", []) if r.get("Name") == pkg]
    if not found:
        raise ValueError(f"{pkg} is not in the AUR (any more)")
    folder = aur_extract(get(AUR_SNAPSHOT.format(p=pkg), AUR_MAX_BYTES), aur_workdir(cache_dir), pkg)
    files = {}
    for name in sorted(os.listdir(folder)):
        if name == "PKGBUILD" or name.endswith(".install"):
            with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as f:
                files[name] = f.read()
    if "PKGBUILD" not in files:
        raise ValueError("the AUR package has no PKGBUILD")
    digest = hashlib.sha256("".join(files[n] for n in sorted(files)).encode()).hexdigest()
    return {"dir": folder, "meta": found[0], "files": files, "sha256": digest}


def aur_steps(pkg, folder):
    """Build the package as the user (makepkg refuses root) and install it: dependencies come through pacman with the password
    asked by pkexec (PACMAN_AUTH in a private copy of makepkg.conf), then the built file is installed as administrator."""
    q = shlex.quote
    work = os.path.dirname(folder)
    conf = os.path.join(work, "makepkg-aur.conf")
    build = f"""set -eu
cd {q(folder)}
{{ cat /etc/makepkg.conf; echo 'PACMAN_AUTH=(pkexec)'; }} > {q(conf)}
makepkg --config {q(conf)} --syncdeps --rmdeps --noconfirm
"""
    install = f"""set -eu
cd {q(folder)}
files=""
for f in *.pkg.tar.*; do
  case "$f" in *.sig|*-debug-*) ;; *) files="$files $f" ;; esac
done
[ -n "$files" ] || {{ echo "no package was built" >&2; exit 1; }}
pacman -U --noconfirm $files
"""
    return [{"root": True, "sh": "set -eu\npacman -S --needed --noconfirm base-devel\n"},
            {"root": False, "sh": build}, {"root": True, "sh": install},
            {"root": False, "sh": f"rm -rf {q(work)}\n"}]


def aur_remove_steps(pkg):
    return [{"root": True, "sh": f"set -u\npacman -R --noconfirm {shlex.quote(pkg)}\n"}]


def aur_installed(pkg, run=subprocess.run, which=shutil.which):
    """The installed version of an AUR (or any pacman) package, None when not installed."""
    if not which("pacman"):
        return None
    try:
        r = run(["pacman", "-Q", pkg], capture_output=True, text=True, timeout=30)
    except Exception:  # noqa: BLE001
        return None
    return (r.stdout.split() + [""])[1] if r.returncode == 0 else None


def main(argv):
    if len(argv) < 2 or argv[0] != "etcher":
        print(__doc__)
        return 2
    if argv[1] == "installed":
        v = etcher_installed()
        print(v or "not installed")
        return 0 if v else 1
    if argv[1] == "plan":
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
        from lscommon import detect_pm
        arch = subprocess.run(["uname", "-m"], capture_output=True, text=True).stdout.strip()
        steps, info = etcher_steps(etcher_release(), detect_pm(), arch)
        if "--json" in argv:
            print(json.dumps({"info": info, "steps": steps}, indent=2))
        else:
            print(f"balenaEtcher {info.get('version')}: " + (info.get("manual") and f"no official package for this system - {info['manual']}"
                  or f"{info['file']} ({info['mb']} MB) from {info['source']}, SHA-256 {info['sha256']}"))
            for s in steps:
                print("# " + ("as administrator" if s["root"] else "as you"))
                print(s["sh"])
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
