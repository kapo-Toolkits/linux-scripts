#!/usr/bin/env python3
"""The doctor against a real system, in a throw-away container, as root.

usage: qgis_doctor_container_test.py       (run by tests/run-recipes-containers.sh doctor IMAGE)

A clean system must give no findings (no false alarms); then each problem the doctor knows is made for real and must be found:
a user copy of numpy hiding the system's, PROJ_LIB pointing nowhere, an old QGIS repository file, and (Debian/Ubuntu, where GDAL is
cheap) the real GDAL tools and GDAL for Python being compared.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import sysconfig

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "qgis-installer"))
from qgis_installer import cli, doctor, requirements, system  # noqa: E402

fails = []


def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{str(extra)[:220]}]" if extra else ""))
    if not ok:
        fails.append(name)


def sh(script):
    p = subprocess.run(["sh", "-c", script], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main(["--lang", "en", *argv])
    return rc, out.getvalue(), err.getvalue()


s = system.detect()
pm = s["pm"]
print("system:", s["name"], "| pm:", pm)

# numpy for the system (everywhere) and, on Debian/Ubuntu, the real GDAL tools and bindings
pk = requirements.packages_for(["numpy"], pm)[0]
if pm == "apt-get":
    sh("apt-get update -qq")
    pk += requirements.packages_for(["gdal", "gdal-python"], pm)[0]
install = requirements.install_steps(["numpy"] + (["gdal", "gdal-python"] if pm == "apt-get" else []), pm)[0]
rc, out = sh(install[0]["sh"])
check("the system's libraries are installed for the test", rc == 0, out.strip()[-120:])

rc, out, err = run("doctor")
print(out)
check("a clean system gives no finding (no false alarm) and exit 0", rc == 0 and "No problem found" in out, out)
res = doctor.run_all([], s)
check("the checks that can be made here were made", {"shadowing", "proj", "disk", "sources"} <= set(res["ran"]), res["ran"])
if pm == "apt-get":
    check("Debian/Ubuntu: GDAL tools and GDAL for Python were compared and agree", "gdal" in res["ran"] and not [f for f in res["findings"] if f[1] == "gdal_mismatch"],
          (res["ran"], res["skipped"]))
    check("Debian/Ubuntu: the package database was audited and is clean", "dpkg" in res["ran"] and not [f for f in res["findings"] if f[1] == "dpkg_broken"], res["ran"])

# a user copy of numpy next to the system's: found
purelib = sysconfig.get_paths()["purelib"]
plat = sysconfig.get_paths()["platlib"]
home = os.path.expanduser("~")
user_dir = os.path.join(home, ".local", "lib", "python{}.{}".format(*sys.version_info[:2]), "site-packages")
os.makedirs(os.path.join(user_dir, "numpy"), exist_ok=True)
with open(os.path.join(user_dir, "numpy", "__init__.py"), "w") as fh:
    fh.write("# a pip install --user copy\n")
system_has = any(os.path.isdir(os.path.join(d, "numpy")) for d in doctor.system_site_dirs())
check("(the system really has numpy in a site folder the doctor knows)", system_has, doctor.system_site_dirs())
rc, out, err = run("doctor")
check("the user copy hiding the system's numpy is found, as a warning (exit still 0)", rc == 0 and "[warning] numpy: your own copy" in out, out)
res = doctor.run_all([], s)
f = [x for x in res["findings"] if x[1] == "shadowing"]
check("the finding names both places", f and f[0][2]["name"] == "numpy" and user_dir in f[0][2]["user"], f)
check("and python really does import the user copy first (so the warning is true)",
      "a pip install --user copy" in sh("python3 -c 'import numpy;print(open(numpy.__file__).read())' 2>&1")[1]
      or sh("python3 -c 'import numpy;print(numpy.__file__)'")[1].startswith(user_dir), sh("python3 -c 'import numpy;print(numpy.__file__)' 2>&1")[1])
sh("rm -rf '{}'".format(os.path.join(user_dir, "numpy")))
check("removed again: no finding", not [x for x in doctor.run_all([], s)["findings"] if x[1] == "shadowing"])

# PROJ_LIB pointing nowhere: a problem, exit 1
os.environ["PROJ_LIB"] = "/nowhere/proj"
rc, out, err = run("doctor")
check("PROJ_LIB pointing nowhere is a problem and the exit code says so", rc == 1 and "[PROBLEM] PROJ_LIB points to /nowhere/proj" in out, (rc, out))
del os.environ["PROJ_LIB"]

# an old QGIS repository file (apt systems)
if pm == "apt-get":
    path = "/etc/apt/sources.list.d/qgis.sources"
    with open(path, "w") as fh:
        fh.write("Types: deb\nURIs: https://qgis.org/{}-ltr\nSuites: {}\nComponents: main\n".format(s["family"], "jammy" if s["code"] != "jammy" else "noble"))
    rc, out, err = run("doctor")
    check("a repository file of another release is a problem (left behind by an upgrade)", rc == 1 and "[PROBLEM] The QGIS repository file is for" in out, (rc, out))
    with open(path, "w") as fh:
        fh.write("Types: deb\nURIs: https://qgis.org/{}-ltr\nSuites: {}\nComponents: main\n".format(s["family"], s["code"]))
    rc, out, err = run("doctor")
    check("the file of this release is fine", rc == 0 and "repo" in doctor.run_all([], s)["ran"], out)
    os.remove(path)
    # a real half-configured package: make dpkg unhappy and let the audit speak
    sh("apt-get install -y -qq tzdata >/dev/null 2>&1")
    rc, out = sh("dpkg --audit")
    check("dpkg --audit is empty on a healthy system (the doctor relies on it)", rc == 0 and not out.strip(), out)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
