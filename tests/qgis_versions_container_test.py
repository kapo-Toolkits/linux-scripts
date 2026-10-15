#!/usr/bin/env python3
"""Versions for real, in a throw-away container, as root: list, go back to an older one, keep one, release it.

usage: qgis_versions_container_test.py       (run by tests/run-recipes-containers.sh versions IMAGE)

QGIS itself is far too big for this, so the same code runs on a small package that exists on every distribution (the plan builder
only needs "an installed package with several versions"): tzdata on Ubuntu (whose archive keeps the older pockets, so a real
downgrade is possible), bash elsewhere. The Flatpak part (build list of the real org.qgis.qgis, mask / unmask) runs on Debian.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "qgis-installer"))
from qgis_installer import simulate, system, versions  # noqa: E402

fails = []


def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not ok:
        fails.append(name)


def sh(script):
    p = subprocess.run(["sh", "-c", script], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def run_steps(res):
    out = []
    for st in res["steps"]:
        rc, text = sh(st["sh"])
        out.append((rc, text))
    return out


s = system.detect()
pm = s["pm"]
print("system:", s["name"], "| pm:", pm, "| id:", s["id"])

if pm == "apt-get":
    sh("apt-get update -qq")
    rc, out = sh("apt-get install -y -qq tzdata")
    check("tzdata installed for the test", rc == 0, out.strip()[-100:])
    rc, cur = sh("dpkg-query -W -f='${Version}' tzdata")
    item = {"kind": "apt", "pkgs": ["tzdata"], "v": cur.strip(), "root": True}
    av = versions.available(item)
    check("the repositories' versions are listed, the installed one is marked",
          len(av["versions"]) >= 1 and sum(r["installed"] for r in av["versions"]) == 1, av["versions"])
    print("   versions:", [r["version"] for r in av["versions"]])
    held = versions.lock_steps(item, True)
    rc, out = run_steps(held)[0]
    check("hold runs", rc == 0, out.strip()[-80:])
    check("lock_state sees the hold", versions.lock_state(item) is True)
    rc, out = sh("apt-get -s install --only-upgrade tzdata")
    check("a held package is not offered for upgrade by apt", "Inst tzdata" not in out, out.strip()[-120:])
    rc, out = run_steps(versions.lock_steps(item, False))[0]
    check("unhold runs", rc == 0, out.strip()[-80:])
    check("lock_state sees it released", versions.lock_state(item) is False)

    if s["id"] == "ubuntu" and len(av["versions"]) >= 2:
        old = av["versions"][-1]
        res = versions.steps_for(item, old)
        sim = simulate.explain(res["steps"])
        check("the simulation says it is a downgrade of one package", sim["items"] and sim["items"][0]["downgrades"] == 1, sim)
        print(simulate.format_text(sim, "en"))
        rc, out = run_steps(res)[0]
        check("going back to the oldest version runs", rc == 0, out.strip()[-120:])
        rc, now = sh("dpkg-query -W -f='${Version}' tzdata")
        check("the installed version is now exactly that one", now.strip() == old["version"], (now, old["version"]))
        item2 = dict(item, v=now.strip())
        sh("apt-mark hold tzdata")
        rc, out = sh("apt-get install -y --only-upgrade tzdata")
        rc, still = sh("dpkg-query -W -f='${Version}' tzdata")
        check("while kept, an upgrade request leaves the old version alone", still.strip() == old["version"], (still, out.strip()[-100:]))
        sh("apt-mark unhold tzdata")
        rc, out = sh("apt-get install -y --only-upgrade tzdata")
        rc, newest = sh("dpkg-query -W -f='${Version}' tzdata")
        check("released, the same request brings the newest version back", newest.strip() == av["versions"][0]["version"], (newest, av["versions"][0]["version"]))
        del item2
    else:
        print("   (this distribution's archive keeps only the current version: the downgrade itself is exercised on Ubuntu)")

    # Flatpak: the real QGIS build list and the mask, without installing the (large) app
    rc, out = sh("apt-get install -y -qq flatpak")
    rc, out = sh("flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo")
    fp = {"kind": "flatpak", "i": "user", "v": "?", "br": "stable", "root": False}
    av = versions.available(fp)
    check("Flatpak: the real build list of org.qgis.qgis//stable is read", len(av["versions"]) >= 2
          and all(len(r["commit"]) == 64 for r in av["versions"]), av["versions"][:2])
    print("   newest build:", av["versions"][0]["version"] if av["versions"] else None)
    check("Flatpak: a build is described by date and subject", av["versions"] and av["versions"][0]["version"][:4].isdigit(), av["versions"][:1])
    rc, out = run_steps(versions.lock_steps(fp, True))[0]
    check("Flatpak: mask runs", rc == 0, out.strip()[-100:])
    check("Flatpak: lock_state sees the mask", versions.lock_state(fp) is True)
    rc, out = run_steps(versions.lock_steps(fp, False))[0]
    check("Flatpak: unmask runs", rc == 0, out.strip()[-100:])
    check("Flatpak: lock_state sees it released", versions.lock_state(fp) is False)
    res = versions.steps_for(fp, av["versions"][1])
    check("Flatpak: the step to go back names the commit and the branch",
          av["versions"][1]["commit"] in res["steps"][0]["sh"] and "org.qgis.qgis//stable" in res["steps"][0]["sh"], res["steps"][0]["sh"])
    sim = simulate.simulate_line("flatpak install --user -y flathub org.qgis.qgis//stable")
    check("Flatpak: the size of the app is read from the real remote", sim and sim["download"] and sim["disk"], sim)
    print("   flatpak size:", sim and (sim["download"], sim["disk"]))

elif pm == "dnf":
    item = {"kind": "dist", "pm": "dnf", "pkgs": ["bash"], "v": "", "root": True}
    av = versions.available(item)
    check("dnf: versions are listed and one is the installed one", len(av["versions"]) >= 1 and sum(r["installed"] for r in av["versions"]) == 1, av["versions"])
    rc, out = run_steps(versions.lock_steps(item, True))[0]
    check("dnf: versionlock add runs", rc == 0, out.strip()[-120:])
    check("dnf: lock_state sees it", versions.lock_state(item) is True, sh("dnf versionlock list")[1][-200:])
    rc, out = run_steps(versions.lock_steps(item, False))[0]
    check("dnf: versionlock delete runs", rc == 0, out.strip()[-120:])
    check("dnf: lock_state sees it released", versions.lock_state(item) is False)

elif pm == "zypper":
    sh("zypper -q --non-interactive refresh")
    item = {"kind": "dist", "pm": "zypper", "pkgs": ["bash"], "v": "", "root": True}
    av = versions.available(item)
    check("zypper: versions are listed and one is the installed one", len(av["versions"]) >= 1 and sum(r["installed"] for r in av["versions"]) >= 1, av["versions"])
    rc, out = run_steps(versions.lock_steps(item, True))[0]
    check("zypper: addlock runs", rc == 0, out.strip()[-120:])
    check("zypper: lock_state sees it", versions.lock_state(item) is True, sh("zypper locks")[1][-200:])
    rc, out = run_steps(versions.lock_steps(item, False))[0]
    check("zypper: removelock runs", rc == 0, out.strip()[-120:])
    check("zypper: lock_state sees it released", versions.lock_state(item) is False)

elif pm == "pacman":
    item = {"kind": "dist", "pm": "pacman", "pkgs": ["bash"], "v": "", "root": True}
    av = versions.available(item)
    check("pacman: nothing to choose, and it says why", av == {"versions": [], "note": "ver_arch"}, av)
    lock = versions.lock_steps(item, True)
    check("pacman: instructions only (IgnorePkg), nothing is run", lock["steps"] == [] and "IgnorePkg = bash" in lock["manual"][0]["text"], lock)

else:
    raise SystemExit("no versions check for " + str(pm))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
