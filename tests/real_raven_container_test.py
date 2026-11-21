#!/usr/bin/env python3
"""Runs INSIDE a throwaway Ubuntu container (as a normal user): Raven's recipe against the real 'nightly' release (about 40 MB): the release and its
SHA256SUMS are looked up, the archive is downloaded and checked, unpacked safely, the `raven` command works, a Windows console program
(the archive's own hostname.exe) runs, then removal keeps the user's Windows prefixes."""
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
    r = None
    for st in steps:
        r = subprocess.run(["sh", "-c", st["sh"]], capture_output=True, text=True)
        if r.returncode != 0:
            return r
    return r


home = os.path.expanduser("~")
release = extras.raven_release()
check("the nightly release and its SHA256SUMS were read", bool(release["sums"].get(extras.RAVEN_ASSET)) and bool(release["revision"]), str(release.get("name")))
steps, info = extras.raven_steps(release, os.uname().machine)
check("a checked archive was found", bool(steps), str(info))
if steps:
    check("no shared library is missing (the container has them)", info["missing"] == [], str(info["missing"]))
    r = run_steps(steps)
    check("download + SHA-256 + safe unpack + install", r.returncode == 0, r.stdout[-300:] + r.stderr[-300:])
    check("the runtime is in place", os.access(os.path.join(home, ".local/share/raven-runtime/runtime/raven"), os.X_OK))
    check("the detected version is the release's revision", extras.raven_version() == release["revision"][:7], str(extras.raven_version()))
    check("the download and the unpacked copy are gone", not os.listdir(os.path.expanduser(extras.CACHE)))
    raven = os.path.join(home, ".local/bin/raven")
    r = subprocess.run([raven, "--help"], capture_output=True, text=True, timeout=60)
    check("the raven command starts and prints its usage", "--run-process" in (r.stdout + r.stderr), r.stdout[-200:] + r.stderr[-200:])
    prefix = os.path.join(home, ".local/share/raven/test-app")
    os.makedirs(prefix)
    exe = os.path.join(home, ".local/share/raven-runtime/runtime/hostname.exe")
    env = dict(os.environ, RAVEN_PREFIX=prefix)
    r = subprocess.run([raven, "--run-process", "--execution=native", "--timeout-ms=60000", exe], capture_output=True, text=True, timeout=120, env=env)
    check("a Windows program (hostname.exe) runs", r.returncode == 0 and "status 0" in (r.stdout + r.stderr), r.stdout[-200:] + r.stderr[-200:])
    r = run_steps(steps)
    check("running it again upgrades in place", r.returncode == 0, r.stdout[-300:] + r.stderr[-300:])
    check("the prefix survived the upgrade", os.path.isdir(prefix))
    r = run_steps(extras.raven_remove_steps())
    check("removal runs", r.returncode == 0, r.stderr[-300:])
    check("the runtime and the command are gone", not os.path.exists(os.path.join(home, ".local/share/raven-runtime")) and not os.path.lexists(raven))
    check("the user's Windows prefix is kept", os.path.isdir(prefix))
    check("detection says not installed", not extras.raven_installed())
print("RESULT:", "ALL PASSED" if not failed else f"{len(failed)} FAILED: {failed}")
sys.exit(1 if failed else 0)
