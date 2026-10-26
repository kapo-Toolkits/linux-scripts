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
KINDS = {"claude", "vscode", "discord", "brave", "etcher", "github", "package"}      # the recipe that installs it
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
        for d in p.get("data", []):
            if not d.startswith("~/") or ".." in d:
                raise ValueError(f"programs.json: {i}: data paths must start with ~/ and stay inside it ({d})")
    return data


PROGRAMS = load_programs()["programs"]
GITHUB_APPS = {p["id"]: {"name": p["display"], "repo": p["repo"], "package": p["package"], "cmd": p["cmd"], "asset": p["asset"]}
               for p in PROGRAMS if p["kind"] == "github"}
PACKAGE_APPS = {p["id"]: {"cmd": p["cmd"], "name": p["display"]} for p in PROGRAMS if p["kind"] == "package"}
FLATPAK_IDS = {p["id"]: p["flatpak"] for p in PROGRAMS if p.get("flatpak")}
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


def outdated(installed=installed_version, github=None, etcher=None):
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
    """[{'root': True, 'sh': ...}] installing (or removing) the distribution's package, [] when unknown here."""
    pkg = package_name(app, pm)
    fmt = (_REMOVE if remove else _INSTALL).get(pm)
    if not pkg or not fmt:
        return []
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
