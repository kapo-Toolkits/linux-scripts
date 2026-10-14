#!/usr/bin/env python3
"""End-to-end test of qgis-installer's method A + uninstall, meant to run as root INSIDE a throwaway
Debian/Ubuntu container (see tests/run-qgis-containers.sh). Nothing touches the host.

usage: qgis_container_test.py <channel>      e.g. latest | ltr
The big `apt-get install -y qgis ...` is only simulated (-s); a small package (qgis-common) is installed
for real so the uninstall path has something to remove.
"""
import importlib.util
import os
import subprocess
import sys
import types

for n in ("tkinter", "tkinter.ttk", "tkinter.messagebox", "tkinter.scrolledtext", "tkinter.filedialog"):
    sys.modules[n] = types.ModuleType(n)
tk = sys.modules["tkinter"]
tk.ttk, tk.messagebox = sys.modules["tkinter.ttk"], sys.modules["tkinter.messagebox"]
tk.scrolledtext, tk.filedialog = sys.modules["tkinter.scrolledtext"], sys.modules["tkinter.filedialog"]
tk.Tk = object

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("q", os.path.join(here, "..", "qgis-installer", "qgis-installer-gui.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

channel = sys.argv[1] if len(sys.argv) > 1 else "ltr"
fails = []


def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not ok:
        fails.append(name)


def sh(script):
    p = subprocess.run(["sh", "-c", script], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def simulate(script):
    # keep everything real except the big install
    return script.replace("apt-get install -y qgis", "apt-get install -s qgis")


s = m.detect()
print("system:", s)
check("detect: Debian/Ubuntu family, apt, amd64", bool(s["family"]) and s["apt"] and s["arch"] == "amd64")
check("detect: codename supported", s["supported"], f"{s['family']}/{s['code']} ltr_only={s['ltr_only']}")
if s["ltr_only"]:
    check("channel allowed for this codename", channel in m.LTR_ONLY_CHANNELS, channel)

pk = {"grass": True, "python": True, "server": False}

# 1. real install steps (simulated big install)
step = m.build_install("A", s, channel, pk)[0]
rc, out = sh(simulate(step["sh"]))
check("method A script runs", rc == 0, out.strip().splitlines()[-1][:120] if out.strip() else "")
check("key fingerprint verified", "Key fingerprint OK" in out)
src = open(m.SOURCES).read() if os.path.exists(m.SOURCES) else ""
check("sources file written", f"Suites: {s['code']}" in src and f"qgis.org/{s['family']}{m.SUFFIX[channel]}" in src)
check("keyring installed", os.path.exists(m.KEYRING))
rc, pol = sh("apt-cache policy qgis")
cand = [l for l in pol.splitlines() if "Candidate" in l]
check("qgis candidate comes from qgis.org", "qgis.org" in pol and cand, cand[0].strip() if cand else pol[:200])
rc, sim = sh("apt-get install -s qgis qgis-plugin-grass python3-qgis | tail -3")
check("qgis + grass + python resolvable", rc == 0 and "unmet" not in sim.lower(), sim.strip().splitlines()[-1] if sim.strip() else "")

# 2. tampered fingerprint must abort and leave nothing behind
sh(f"rm -f {m.SOURCES} {m.KEYRING}")
good = m.KEY_FPR
m.KEY_FPR = "0" * 40
bad = m.build_install("A", s, channel, pk)[0]
m.KEY_FPR = good
rc, out = sh(simulate(bad["sh"]))
check("wrong fingerprint aborts", rc != 0 and "MISMATCH" in out)
check("nothing written after abort", not os.path.exists(m.SOURCES) and not os.path.exists(m.KEYRING))

# 3. install a small real package, then uninstall through the app's own detection + builder
sh(simulate(step["sh"]))
rc, out = sh("apt-get install -y qgis-common")
check("small real package installs (qgis-common)", rc == 0, out.strip().splitlines()[-1][:100])
items = m.find_installs(s)
kinds = sorted(i["kind"] for i in items)
check("find_installs sees apt + repo", kinds == ["apt", "repo"], str(kinds))
apt = next((i for i in items if i["kind"] == "apt"), {})
check("apt item lists qgis-common and its origin", "qgis-common" in apt.get("pkgs", []) and "qgis.org" in apt.get("o", ""),
      apt.get("o", ""))
steps = m.build_remove_steps(items, True, True, s)
print(m.steps_text(steps))
for st in steps:
    rc, out = sh(st["sh"])
    check("remove step runs", rc == 0, out.strip().splitlines()[-1][:100] if out.strip() else "")
rc, out = sh("dpkg -s qgis-common 2>&1")
check("package gone", rc != 0 or "Status: install ok installed" not in out, out.strip().splitlines()[0][:80])
check("repo + key files gone", not os.path.exists(m.SOURCES) and not os.path.exists(m.KEYRING))
check("find_installs clean afterwards", m.find_installs(s) == [], str(m.find_installs(s)))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
