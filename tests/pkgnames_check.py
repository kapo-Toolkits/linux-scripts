#!/usr/bin/env python3
"""Inside a distro container: does every package name in lscommon.PKG_FOR exist in THIS distro's repositories?
(run via tests/run-distros.sh; the container must have refreshed its package index first)"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
import lscommon  # noqa: E402

pm = lscommon.detect_pm()
CHECK = {
    "apt-get": lambda p: ["sh", "-c", f"apt-cache policy {p} | grep -q 'Candidate: [^(]'"],
    "dnf": lambda p: ["dnf", "-q", "info", p],
    "yum": lambda p: ["yum", "-q", "info", p],
    "pacman": lambda p: ["pacman", "-Si", p],
    # a dry-run install also resolves capabilities (openSUSE has python313 and only *provides* python3 / python3-tk)
    "zypper": lambda p: ["zypper", "--non-interactive", "install", "--dry-run", p],
    "apk": lambda p: ["sh", "-c", f"apk search -e {p} | grep -q ."],
}
print(f"package manager: {pm}")
# a program may name a fallback package for a package manager (programs.json "fallback", e.g. Debian: unrar-free)
import json  # noqa: E402
FALLBACK = {p["cmd"]: p.get("fallback", {}) for p in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "installer", "programs.json")))["programs"]
            if p.get("cmd") and p.get("fallback")}
bad = 0
for cmd, per_pm in sorted(lscommon.PKG_FOR.items()):
    pkg = per_pm.get(pm)
    if not pkg:
        print(f"SKIP {cmd}: no mapping for {pm}")
        continue
    ok = subprocess.run(CHECK[pm](pkg), capture_output=True).returncode == 0
    note = ""
    other = FALLBACK.get(cmd, {}).get(pm)
    if not ok and other:                                   # not in this distribution (Debian non-free): the fallback must exist
        ok = subprocess.run(CHECK[pm](other), capture_output=True).returncode == 0
        note = f"   (not here; fallback {other})"
    bad += not ok
    print(("PASS" if ok else "FAIL"), f"{cmd:10s} -> {pkg}{note}")
# the requirements of the GIS GEORGIA QGIS plugins (qgis_installer.requirements)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "qgis-installer"))
from qgis_installer import requirements  # noqa: E402

for rid, spec in sorted(requirements.REQ.items()):
    names = requirements.packages_for([rid], pm)[0]
    if not names:
        print(f"MANUAL {rid}: no package for {pm}")
        continue
    for pkg in names:
        ok = subprocess.run(CHECK[pm](pkg), capture_output=True).returncode == 0
        bad += not ok
        print(("PASS" if ok else "FAIL"), f"req:{rid:10s} -> {pkg}")
# the packages that tkinter auto-install and installer/start.sh rely on (a wrong name only shows on that distribution)
extra = {pkg for mgr, _cmd, pkg in lscommon.TK_PACKAGES if mgr == pm} | set(lscommon.PYTHON_BOOTSTRAP.get(pm, []))
for pkg in sorted(extra):
    if pm not in CHECK:
        break
    ok = subprocess.run(CHECK[pm](pkg), capture_output=True).returncode == 0
    bad += not ok
    print(("PASS" if ok else "FAIL"), f"bootstrap  -> {pkg}")
print("install hint:", lscommon.install_command([(c, v.get(pm)) for c, v in lscommon.PKG_FOR.items()], pm))
sys.exit(1 if bad else 0)
