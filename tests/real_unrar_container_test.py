#!/usr/bin/env python3
"""Runs INSIDE a throwaway Debian/Ubuntu container as root: the installer's unrar recipe against the real repositories.
Ubuntu (multiverse) gets the real 'unrar'; Debian (no non-free) must fall back to 'unrar-free'; both must provide the
command 'unrar', and removal must take it away again."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "installer"))
import extras  # noqa: E402

failed = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail[:200]}]" if detail and not ok else ""))
    if not ok:
        failed.append(name)


def sh(script):
    return subprocess.run(["sh", "-c", script], capture_output=True, text=True)


osrel = open("/etc/os-release").read()
debian = "ID=debian" in osrel
sh("apt-get update -qq")
steps = extras.package_steps("unrar", "apt-get")
r = sh(steps[0]["sh"])
check("install runs", r.returncode == 0, r.stdout + r.stderr)
check("the command 'unrar' exists afterwards", sh("command -v unrar").returncode == 0)
pkg = "unrar-free" if debian else "unrar"
check(f"the package that came is {pkg}", sh(f"dpkg -s {pkg}").returncode == 0)
r = sh("unrar 2>&1")                                    # no arguments: nonfree prints its banner, unrar-free "Archive not specified"
check("it really is unrar (it names itself)", "unrar" in (r.stdout + r.stderr).lower(), r.stdout + r.stderr)
r = sh(extras.package_steps("unrar", "apt-get", remove=True)[0]["sh"])
check("removal runs", r.returncode == 0, r.stdout + r.stderr)
check("the command is gone afterwards", sh("command -v unrar").returncode != 0)
check("nothing of it is left installed", sh("dpkg -l unrar unrar-free 2>/dev/null | grep -q '^ii'").returncode != 0)
print("RESULT:", "ALL PASSED" if not failed else f"{len(failed)} FAILED: {failed}")
sys.exit(1 if failed else 0)
