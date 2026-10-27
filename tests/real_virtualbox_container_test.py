#!/usr/bin/env python3
"""Runs INSIDE a throwaway Debian/Ubuntu container as root: the VirtualBox recipe against Oracle's real server. The key is
downloaded and its fingerprint checked, the repository for this release is registered and apt must offer virtualbox-7.2 from
download.virtualbox.org; then the removal steps must take the entry away again. (The big 'apt-get install' lines are cut off:
they would only download hundreds of MB and need kernel headers.)"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "installer"))
import extras  # noqa: E402

failed = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail[:240]}]" if detail and not ok else ""))
    if not ok:
        failed.append(name)


def sh(script):
    return subprocess.run(["sh", "-c", script], capture_output=True, text=True)


sh("apt-get update -qq && apt-get install -y -qq curl gnupg ca-certificates")
script = extras.virtualbox_steps("apt-get", "x86_64")[0][0]["sh"]
cut = "\n".join(ln for ln in script.splitlines() if not ln.startswith(("apt-get install -y dkms", "apt-get install -y virtualbox"))) + "\n"
r = sh(cut)
check("recipe runs (release recognised, key fingerprint checked, repository added)", r.returncode == 0, r.stdout + r.stderr)
check("repository entry and key are on disk", os.path.exists(extras.VBOX_LIST) and os.path.exists(extras.VBOX_KEYRING))
line = open(extras.VBOX_LIST).read() if os.path.exists(extras.VBOX_LIST) else ""
cn = sh(". /etc/os-release; echo ${UBUNTU_CODENAME:-$VERSION_CODENAME}").stdout.strip()
check(f"the entry is for this release ({cn})", f" {cn} contrib" in line, line)
pol = sh("apt-cache policy virtualbox-7.2").stdout
check("apt offers virtualbox-7.2 from download.virtualbox.org", "Candidate: 7.2" in pol and "download.virtualbox.org" in pol, pol)
r = sh(extras.virtualbox_remove_steps("apt-get")[0]["sh"])
check("removal steps run", r.returncode == 0, r.stdout + r.stderr)
check("entry and key are gone", not os.path.exists(extras.VBOX_LIST) and not os.path.exists(extras.VBOX_KEYRING))
check("apt no longer offers it", "Candidate: 7.2" not in sh("apt-cache policy virtualbox-7.2").stdout)

bad = sh(cut.replace(extras.VBOX_FPR, "0" * 40))
check("a wrong fingerprint aborts", bad.returncode != 0 and "KEY FINGERPRINT MISMATCH" in bad.stderr, bad.stderr)
check("nothing is written after the abort", not os.path.exists(extras.VBOX_LIST) and not os.path.exists(extras.VBOX_KEYRING))
print("RESULT:", "ALL PASSED" if not failed else f"{len(failed)} FAILED: {failed}")
sys.exit(1 if failed else 0)
