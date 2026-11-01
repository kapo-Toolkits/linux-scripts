#!/usr/bin/env python3
"""Runs INSIDE a throwaway Ubuntu container: the Codex recipe against the real GitHub release (about 120 MB): the latest release
is looked up, the static binary is downloaded, its SHA-256 is checked against GitHub's digest, it is installed as ~/.local/bin/codex
and must answer --version; a second run upgrades, a foreign codex is never replaced, removal keeps ~/.codex."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "installer"))
import extras  # noqa: E402

failed = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail[:300]}]" if detail and not ok else ""))
    if not ok:
        failed.append(name)


def run_steps(steps):
    for st in steps:
        r = subprocess.run(["sh", "-c", st["sh"]], capture_output=True, text=True)
        if r.returncode != 0:
            return r
    return r


home = os.path.expanduser("~")
target = os.path.join(home, ".local/bin/codex")
release = extras.codex_release()
steps, info = extras.codex_steps(release, os.uname().machine)
check("a checked package was found in the latest release", bool(steps), str(info))
if steps:
    r = run_steps(steps)
    check("download + SHA-256 + install", r.returncode == 0, r.stdout[-300:] + r.stderr[-300:])
    check("the program is in place and executable", os.access(target, os.X_OK))
    v = subprocess.run([target, "--version"], capture_output=True, text=True)
    check("it answers --version with the released version", v.returncode == 0 and release["version"] in v.stdout, v.stdout + v.stderr)
    check("the version helper agrees", extras.codex_version(path=target) == release["version"])
    check("the marker is written", os.path.isfile(os.path.expanduser(extras.CODEX_MARKER)))
    check("the download and the unpacked copy are gone", not os.listdir(os.path.expanduser(extras.CACHE)))
    check("an up-to-date install is not reported as outdated", extras.outdated(installed=lambda p: None)[0] == [])
    r = run_steps(steps)
    check("running it again upgrades in place", r.returncode == 0, r.stdout[-200:] + r.stderr[-200:])
    os.makedirs(os.path.join(home, ".codex"), exist_ok=True)
    open(os.path.join(home, ".codex/auth.json"), "w").write("{}")
    r = run_steps(extras.codex_remove_steps())
    check("removal runs", r.returncode == 0 and "removed" in r.stdout, r.stdout + r.stderr)
    check("the program and the marker are gone", not os.path.exists(target) and not os.path.exists(os.path.expanduser(extras.CODEX_MARKER)))
    check("sign-in and history (~/.codex) are kept", os.path.isfile(os.path.join(home, ".codex/auth.json")))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    open(target, "w").write("#!/bin/sh\necho from-npm\n")
    os.chmod(target, 0o755)
    r = run_steps(steps)
    check("a codex from elsewhere is not replaced", r.returncode != 0 and open(target).read().endswith("from-npm\n"), r.stderr[-200:])
print("RESULT:", "ALL PASSED" if not failed else f"{len(failed)} FAILED: {failed}")
sys.exit(1 if failed else 0)
