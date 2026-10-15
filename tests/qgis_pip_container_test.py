#!/usr/bin/env python3
"""pip install of the package into a clean virtual environment, then run it from there (not from the source folder).

usage: qgis_pip_container_test.py       (run by tests/run-recipes-containers.sh pip IMAGE)

Catches what only a real install shows: a module that is not in the package, a command that is not on the path, a dependency that is not
declared (the package must need nothing but the standard library), a Python older than the claimed minimum.
"""
import os
import shutil
import subprocess
import sys
import tempfile

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "qgis-installer")
fails = []


def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{str(extra)[:200]}]" if extra else ""))
    if not ok:
        fails.append(name)


def sh(*cmd, **kw):
    p = subprocess.run(list(cmd), capture_output=True, text=True, **kw)
    return p.returncode, p.stdout + p.stderr


print("python:", sys.version.split()[0])
work = tempfile.mkdtemp()
src = os.path.join(work, "src")
shutil.copytree(SRC, src, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
venv = os.path.join(work, "venv")
rc, out = sh(sys.executable, "-m", "venv", venv)
if rc != 0:                                    # Debian/Ubuntu ship venv separately
    for cmd in (["apt-get", "install", "-y", "-qq", "python3-venv", "python3-pip"], ["dnf", "install", "-y", "-q", "python3-pip"],
                ["zypper", "-q", "--non-interactive", "install", "python3-pip"], ["pacman", "-S", "--noconfirm", "python-pip"]):
        if shutil.which(cmd[0]):
            sh(*cmd)
    rc, out = sh(sys.executable, "-m", "venv", venv)
check("a virtual environment can be made", rc == 0, out.strip()[-150:])
py, pip = os.path.join(venv, "bin", "python"), os.path.join(venv, "bin", "pip")

rc, out = sh(pip, "install", "-q", "--no-input", src)
check("pip install works with nothing else installed", rc == 0, out.strip()[-300:])
rc, out = sh(pip, "show", "-f", "qgis-installer")
installed = {ln.strip().split("/")[-1] for ln in out.splitlines() if ln.strip().startswith("qgis_installer/") and ln.strip().endswith(".py")}
source = {f for f in os.listdir(os.path.join(SRC, "qgis_installer")) if f.endswith(".py")}
check("every module of the source is in the installed package", installed == source, (sorted(source - installed), sorted(installed - source)))
rc, out = sh(pip, "show", "qgis-installer")
check("the package declares no dependencies", any(ln.strip() == "Requires:" for ln in out.splitlines()), out)

os.chdir("/")
exe = os.path.join(venv, "bin", "qgis-installer-cli")
check("the command is on the environment's path", os.path.exists(exe), exe)
rc, out = sh(exe, "--version")
check("--version names the package version", rc == 0 and out.startswith("qgis-installer "), out)
for argv, needle in ((["--lang", "en", "recipes"], "Official QGIS repository"), (["--lang", "ka", "components", "--category", "db"], "მონაცემთა ბაზის კლიენტები"),
                     (["--lang", "en", "doctor"], "What the doctor looked at"), (["--lang", "en", "--json", "info"], '"schema"'),
                     (["--lang", "en", "env", "export"], '"components"'), (["--lang", "en", "instances"], "")):
    rc, out = sh(exe, *argv)
    check("installed command works: " + " ".join(argv), rc in (0, 1) and needle in out and "Traceback" not in out, out.strip()[-160:])
rc, out = sh(py, "-c", "import qgis_installer as q; print(q.__version__, all(hasattr(q, m) for m in "
                       "('doctor','envspec','instances','recipes','requirements','simulate','update','versions')))")
check("every module imports from the installed package", rc == 0 and out.strip().endswith("True"), out)
rc, out = sh(py, "-m", "qgis_installer", "--version")
check("python -m qgis_installer works too", rc == 0 and out.startswith("qgis-installer "), out)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
