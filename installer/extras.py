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
curl -fL --proto '{proto}' --tlsv1.2 -o {q(name)}.part {q(asset['url'])}
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
    cmd = {"apt-get": f"apt-get remove -y {ETCHER_PACKAGE}", "dnf": f"dnf remove -y {ETCHER_PACKAGE}",
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


# programs that simply come from the distribution's own repositories (no download, nothing to verify by hand)
PACKAGE_APPS = {"brasero": {"cmd": "brasero", "name": "Brasero"},
                "xfburn": {"cmd": "xfburn", "name": "Xfburn"},
                "k3b": {"cmd": "k3b", "name": "K3b"}}
_INSTALL = {"apt-get": "apt-get install -y {p}", "dnf": "dnf install -y {p}", "yum": "yum install -y {p}",
            "pacman": "pacman -S --noconfirm {p}", "zypper": "zypper --non-interactive install {p}",
            "apk": "apk add {p}", "xbps-install": "xbps-install -y {p}"}
_REMOVE = {"apt-get": "apt-get remove -y {p}", "dnf": "dnf remove -y {p}", "yum": "yum remove -y {p}",
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
