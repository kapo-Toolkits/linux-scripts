#!/usr/bin/env python3
"""Runs INSIDE a throwaway Arch Linux container: the installer's AUR route against the real AUR.
As root it prepares a normal user (makepkg refuses root) with a stand-in for pkexec, then runs itself as that user:
fetch the snapshot, build with makepkg (dependencies through PACMAN_AUTH), install with pacman -U, check, remove.
Also: every AUR name in programs.json exists and has a PKGBUILD."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "installer"))
failed = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail[-300:]}]" if detail and not ok else ""))
    if not ok:
        failed.append(name)


def sh(script, root=False):
    return subprocess.run((["sudo"] if root else []) + ["sh", "-c", script], capture_output=True, text=True)


if "--as-user" not in sys.argv:
    def run(cmd):
        r = subprocess.run(["sh", "-c", cmd])
        if r.returncode:
            sys.exit(f"setup failed: {cmd}")
    run("pacman -Syu --noconfirm --quiet python sudo ca-certificates >/dev/null")
    run("useradd -m builder && echo 'builder ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/builder")
    run("printf '#!/bin/sh\\nexec sudo \"$@\"\\n' > /usr/local/bin/pkexec && chmod +x /usr/local/bin/pkexec")
    sys.exit(subprocess.run(["runuser", "-u", "builder", "--", "env", "HOME=/home/builder", "python3", "-I", __file__, "--as-user"]).returncode)

import extras  # noqa: E402

# 1. every AUR name we ship exists in the real AUR, with a PKGBUILD that names itself
for app, pkg in sorted(extras.AUR_IDS.items()):
    try:
        info = extras.aur_fetch(pkg)
        ok = "pkgname" in info["files"].get("PKGBUILD", "") and info["meta"]["Name"] == pkg
        check(f"{app}: AUR package {pkg} exists and has a PKGBUILD", ok, str(info["files"].keys()))
    except Exception as e:  # noqa: BLE001
        check(f"{app}: AUR package {pkg} exists", False, str(e))

# 2. the whole route with a small real package
PKG = "yay-bin"
check("not installed before", extras.aur_installed(PKG) is None)
info = extras.aur_fetch(PKG)
check("fetch gives the PKGBUILD and its checksum", "PKGBUILD" in info["files"] and len(info["sha256"]) == 64)
steps = extras.aur_steps(PKG, info["dir"])
for i, st in enumerate(steps, 1):
    r = sh(st["sh"], root=st["root"])
    check(f"step {i} ({'administrator' if st['root'] else 'user'}) runs", r.returncode == 0, r.stdout + r.stderr)
    if r.returncode:
        break
ver = extras.aur_installed(PKG)
check("pacman knows the package afterwards", bool(ver), str(ver))
check("the program runs", sh("yay --version").returncode == 0)
check("the work folder is cleaned up", not os.path.exists(extras.aur_workdir()))
check("build dependencies were not left behind", sh("pacman -Q go 2>/dev/null").returncode != 0)
r = sh(extras.aur_remove_steps(PKG)[0]["sh"], root=True)
check("removal runs", r.returncode == 0, r.stdout + r.stderr)
check("not installed afterwards", extras.aur_installed(PKG) is None)
print("RESULT:", "ALL PASSED" if not failed else f"{len(failed)} FAILED: {failed}")
sys.exit(1 if failed else 0)
