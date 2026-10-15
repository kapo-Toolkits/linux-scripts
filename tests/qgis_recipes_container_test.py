#!/usr/bin/env python3
"""Does a recipe's plan really resolve on the distribution it is meant for?  Runs as root INSIDE a throw-away container
(see tests/run-recipes-containers.sh); nothing touches the host.

usage: qgis_recipes_container_test.py <recipe-id> [--opt key=value ...]

The plan is built by qgis_installer.recipes for the REAL system of the container, then the big install is turned into a
dry run (the package manager resolves everything and downloads nothing): dnf --assumeno, zypper --dry-run,
pacman --print, apt-get -s, urpmq; Flatpak: the Flathub ref of the chosen branch must exist. Repository steps
(zypper addrepo, flatpak remote-add, installing flatpak itself) run for real because they are cheap and the
dry run needs them.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "qgis-installer"))
from qgis_installer import recipes, system  # noqa: E402

rid = sys.argv[1]
opts = {}
args = sys.argv[2:]
while args:
    if args[0] == "--opt":
        k, _, v = args[1].partition("=")
        opts[k] = {"true": True, "false": False}.get(v, v)
        args = args[2:]
    else:
        raise SystemExit("bad argument: " + args[0])

fails = []


def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not ok:
        fails.append(name)


def sh(script):
    p = subprocess.run(["sh", "-c", script], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


s = system.detect()
print("system:", s["name"], "| distro:", s["distro"], "| pm:", s["pm"], "| tools:", [t for t, v in s["tools"].items() if v])
ok, reason = recipes.applicability(rid, s)
check(f"recipe {rid} applies to this system", ok, reason)
if not ok:
    sys.exit(1)

result = recipes.make_plan(rid, s, opts)
steps = result["steps"]
check("the plan has steps", bool(steps))

if rid == "dnf-fedora":
    rc, out = sh(steps[0]["sh"].replace("dnf install -y", "dnf install --assumeno"))
    check("dnf resolves qgis + python3-qgis + qgis-grass (dry run)", "Transaction Summary" in out and "No match" not in out and "Error" not in out,
          out.strip().splitlines()[-1][:100] if out.strip() else "")
    check("qgis-server too when asked", "qgis-server" in recipes.make_plan(rid, s, {"server": True})["steps"][0]["sh"])
elif rid == "zypper-opensuse":
    script = steps[0]["sh"].replace("install qgis", "install --dry-run qgis")
    rc, out = sh(script)
    check("zypper resolves qgis + qgis-plugin-grass (dry run)", rc == 0 and "qgis" in out, out.strip().splitlines()[-1][:100] if out.strip() else "")
    check("python3-qgis is not requested (it does not exist on openSUSE)", "python3-qgis" not in steps[0]["sh"])
    rc, out = sh("zypper --non-interactive info qgis-ltr")
    check("qgis-ltr really does not exist (so we must not offer it)", rc != 0 or "not found" in out.lower(), out.strip().splitlines()[-1][:80] if out.strip() else "")
elif rid == "pacman-arch":
    rc, out = sh("pacman -Sy --noconfirm >/dev/null 2>&1; pacman -S --print qgis")
    check("pacman resolves qgis (--print)", rc == 0 and "qgis" in out, out.strip().splitlines()[-1][:100] if out.strip() else "")
elif rid == "apt-distro":
    sh("apt-get update -qq")
    script = steps[0]["sh"].replace("apt-get install -y", "apt-get install -s")
    rc, out = sh(script)
    check("apt resolves the distribution's qgis packages (-s)", rc == 0 and "Inst qgis" in out, out.strip().splitlines()[-1][:100] if out.strip() else "")
elif rid == "flatpak":
    for st in steps[:-1]:                              # installing flatpak itself: for real
        rc, out = sh(st["sh"])
        check("flatpak installed for the test", rc == 0, out.strip().splitlines()[-1][:80] if out.strip() else "")
    last = steps[-1]["sh"]
    remote = [ln for ln in last.splitlines() if ln.startswith("flatpak remote-add")][0]
    rc, out = sh(remote)
    check("the Flathub remote can be added", rc == 0, out.strip()[-80:])
    branch = opts.get("branch", "stable")
    rc, out = sh(f"flatpak remote-info flathub org.qgis.qgis//{branch}")
    check(f"org.qgis.qgis//{branch} exists on Flathub", rc == 0 and re.search(r"Ref:\s+app/org\.qgis\.qgis/\S+/" + branch, out) is not None,
          out.strip()[:80])
    rc, out = sh("flatpak remote-info flathub org.qgis.qgis 2>&1 | head -3")
    check("without a branch it is ambiguous (the reason the branch is always named)", "Multiple branches" in out or "stable" in out and "lts" in out, out.strip()[:100])
    check("the install line names the branch", f"org.qgis.qgis//{branch}" in last)
    runtime = re.search(r"Runtime: (\S+)", sh(f"flatpak remote-info flathub org.qgis.qgis//{branch}")[1])
    print("   runtime of this branch:", runtime.group(1) if runtime else "?")
elif rid == "urpmi-mageia":
    sh("urpmi.update -a")
    names = re.search(r"urpmi --auto (.*)", steps[0]["sh"]).group(1).split()
    for name in names:
        rc, out = sh(f"urpmq {name}")
        check(f"urpmq knows {name}", rc == 0 and name in out, out.strip()[:80])
    rc, out = sh("urpmq -f qgis-python")
    check("qgis-python (the guide's old Mandriva name) does not exist", not re.search(r"^qgis-python-\d", out, re.M), out.strip()[:80])
else:
    raise SystemExit("no container check for recipe " + rid)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
