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
    "zypper": lambda p: ["sh", "-c", f"zypper -q --non-interactive info {p} | grep -q '^Name'"],
    "apk": lambda p: ["sh", "-c", f"apk search -e {p} | grep -q ."],
}
print(f"package manager: {pm}")
bad = 0
for cmd, per_pm in sorted(lscommon.PKG_FOR.items()):
    pkg = per_pm.get(pm)
    if not pkg:
        print(f"SKIP {cmd}: no mapping for {pm}")
        continue
    ok = subprocess.run(CHECK[pm](pkg), capture_output=True).returncode == 0
    bad += not ok
    print(("PASS" if ok else "FAIL"), f"{cmd:10s} -> {pkg}")
print("install hint:", lscommon.install_command([(c, v.get(pm)) for c, v in lscommon.PKG_FOR.items()], pm))
sys.exit(1 if bad else 0)
