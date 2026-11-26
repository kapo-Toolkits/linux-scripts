#!/usr/bin/env python3
"""Runs INSIDE a throwaway Ubuntu container (as a normal user's HOME is not needed: everything goes to a temp HOME).
The Android Studio recipe against Google's real servers:
 - developer.android.com/studio is read: one Linux tarball on Google's download host, its version and SHA-256;
 - the download URL answers and its size matches what the page prints;
 - with ASTUDIO_FULL=1 (slow, ~1.6 GB download, ~4 GB disk) the whole install runs for real: free-space check, SHA-256 gate,
   unpack, marker, launcher, menu entry, version detection, then removal. A corrupted checksum must stop before anything is unpacked."""
import os
import subprocess
import sys
import tempfile
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "installer"))
import extras  # noqa: E402

failed = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{str(detail)[:300]}]" if detail and not ok else ""))
    if not ok:
        failed.append(name)


def run_steps(steps, env):
    for st in steps:
        r = subprocess.run(["sh", "-c", st["sh"]], capture_output=True, text=True, env=env)
        if r.returncode:
            return r
    return r


rel = extras.astudio_release()
check("the page gives one Linux tarball with a SHA-256", len(rel["sha256"]) == 64 and rel["name"].endswith("-linux.tar.gz"), rel)
check("the link is on Google's download host", extras.ASTUDIO_LINK_RE.fullmatch(rel["url"]) is not None, rel["url"])
print("   ", rel["title"], rel["version"], rel["url"])
req = urllib.request.Request(rel["url"], method="HEAD", headers={"User-Agent": "linux-scripts-installer"})
with urllib.request.urlopen(req, timeout=30) as r:
    size = int(r.headers.get("Content-Length", 0))
check("the download answers and its size matches the page (within 5 %)", abs(size - rel["size"]) < rel["size"] * 0.05, (size, rel["size"]))

if os.environ.get("ASTUDIO_FULL") == "1":
    home = tempfile.mkdtemp(prefix="as-home-")
    env = dict(os.environ, HOME=home, XDG_DATA_HOME=os.path.join(home, ".local", "share"))
    cache = os.path.join(home, ".cache", "linux-scripts", "downloads")

    bad = dict(rel, sha256="0" * 64)
    steps, _ = extras.astudio_steps(bad, "x86_64", cache_dir=cache)
    r = run_steps(steps, env)
    check("a wrong checksum stops the install", r.returncode != 0 and "CHECKSUM MISMATCH" in r.stderr, r.stderr[-300:])
    check("... and nothing was installed or left behind", not extras.astudio_installed(env["XDG_DATA_HOME"])
          and not any(n.endswith(".tar.gz") for n in os.listdir(cache)))

    steps, info = extras.astudio_steps(rel, "x86_64", cache_dir=cache)
    r = run_steps(steps, env)
    check("the real install runs (space, SHA-256, unpack)", r.returncode == 0, (r.stdout + r.stderr)[-500:])
    data = env["XDG_DATA_HOME"]
    check("marker + version", extras.astudio_version(data) == rel["version"], extras.astudio_version(data))
    app = extras.astudio_dir(data)
    check("Google's launcher is there", os.access(os.path.join(app, "bin", "studio"), os.X_OK)
          or os.access(os.path.join(app, "bin", "studio.sh"), os.X_OK), os.listdir(os.path.join(app, "bin")))
    desk = open(os.path.join(data, "applications", "android-studio.desktop")).read()
    icon = next(x[5:] for x in desk.splitlines() if x.startswith("Icon="))
    check("the menu entry's icon exists", os.path.isfile(icon), icon)
    check("the command exists", os.access(os.path.join(home, ".local", "bin", "android-studio"), os.X_OK))
    check("the download was removed", os.listdir(cache) == [], os.listdir(cache))
    r = subprocess.run(["sh", "-c", extras.astudio_remove_steps()[0]["sh"]], capture_output=True, text=True, env=env)
    check("removal", r.returncode == 0 and not os.path.exists(app)
          and not os.path.exists(os.path.join(home, ".local", "bin", "android-studio")), r.stderr)
else:
    print("(full 1.6 GB install skipped - run with ASTUDIO_FULL=1)")

print("RESULT:", "ALL PASS" if not failed else f"{len(failed)} FAILED: {failed}")
sys.exit(1 if failed else 0)
