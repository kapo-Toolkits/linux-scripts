#!/usr/bin/env python3
"""Runs INSIDE a throwaway Ubuntu container: Filee's recipe against the real GitHub release (about 130 MB): the latest release
is looked up, the package is downloaded, its SHA-256 is checked, the project's own install.sh runs as the user, then an
upgrade over the existing installation, then the project's own uninstall.sh."""
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
app = os.path.join(home, ".local/share/filee/application")
release = extras.filee_release()
steps, info = extras.filee_steps(release, os.uname().machine)
check("a checked package was found in the latest release", bool(steps), str(info))
if steps:
    r = run_steps(steps)
    check("download + SHA-256 + the project's install.sh", r.returncode == 0, r.stdout[-300:] + r.stderr[-300:])
    check("the application is in place", os.access(os.path.join(app, "Filee"), os.X_OK))
    check("the filee command is linked", os.path.islink(os.path.join(home, ".local/bin/filee")))
    check("the launcher exists", os.path.isfile(os.path.join(home, ".local/share/applications/com.filee.app.desktop")))
    check("the installed marker is detected", extras.filee_installed())
    check("the download and the unpacked copy are gone", not [f for f in os.listdir(os.path.expanduser(extras.CACHE))])
    os.makedirs(os.path.join(home, ".config/Filee"), exist_ok=True)
    open(os.path.join(home, ".config/Filee/settings.json"), "w").write("{}")
    r = run_steps(steps)                                          # a second run is an upgrade in place
    check("running it again upgrades in place", r.returncode == 0 and "Upgraded" in r.stdout, r.stdout[-300:] + r.stderr[-300:])
    r = run_steps(extras.filee_remove_steps())
    check("the project's uninstall.sh runs", r.returncode == 0, r.stdout[-300:] + r.stderr[-300:])
    check("the application is gone", not os.path.exists(app))
    check("the command and launcher are gone", not os.path.lexists(os.path.join(home, ".local/bin/filee"))
          and not os.path.exists(os.path.join(home, ".local/share/applications/com.filee.app.desktop")))
    check("the user's settings are kept", os.path.isfile(os.path.join(home, ".config/Filee/settings.json")))
    check("detection says not installed", not extras.filee_installed())
print("RESULT:", "ALL PASSED" if not failed else f"{len(failed)} FAILED: {failed}")
sys.exit(1 if failed else 0)
