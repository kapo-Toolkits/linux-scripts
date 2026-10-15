#!/usr/bin/env python3
"""plugin-deps for real, in a throw-away container, as root: a plugin that needs a library the system lacks -> found -> installed -> clean.

usage: qgis_plugindeps_container_test.py       (run by tests/run-recipes-containers.sh plugindeps IMAGE)
"""
import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "qgis-installer"))
from qgis_installer import cli, pluginscan, requirements, system  # noqa: E402

fails = []


def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{str(extra)[:220]}]" if extra else ""))
    if not ok:
        fails.append(name)


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main(["--lang", "en", *argv])
    return rc, out.getvalue(), err.getvalue()


s = system.detect()
print("system:", s["name"], "| pm:", s["pm"])
root = tempfile.mkdtemp()
plug = os.path.join(root, "lab_report")
os.makedirs(plug)
with open(os.path.join(plug, "metadata.txt"), "w") as fh:
    fh.write("[general]\nname=Lab report\n")
with open(os.path.join(plug, "__init__.py"), "w") as fh:
    fh.write("import os\nimport helper\nfrom qgis.core import QgsProject\nimport openpyxl\n\ndef later():\n    import yaml\n")
with open(os.path.join(plug, "helper.py"), "w") as fh:
    fh.write("import json\n")

check("the library really is missing before (so the test means something)", not pluginscan.can_import("openpyxl"))
rc, out, err = run("plugin-deps", "--dir", root)
check("the plugin that needs openpyxl is found, exit 1 (it does not load without it)", rc == 1 and "lab_report: does not load without openpyxl" in out, (rc, out))
check("its own helper module and qgis are not reported", "helper" not in out and "qgis" not in out.replace("QGIS", ""), out)
check("the package for this system is named", "install with the system:" in out and "openpyxl" in out, out)
check("yaml, used only inside a function, is reported as optional", "works without yaml" in out, out)

rc, out, err = run("plugin-deps", "--dir", root, "--install", "--yes")
check("--install installs what is required and has a package", rc == 0 and "Finished successfully" in out, (rc, err.strip()[-200:]))
check("the library is importable now", pluginscan.can_import("openpyxl"))
rc, out, err = run("plugin-deps", "--dir", root)
check("the same plugin no longer needs anything required (exit 0); the optional one is still said", rc == 0 and "does not load without" not in out and "works without yaml" in out, (rc, out))
rc, out, err = run("plugin-deps", "--dir", root, "--install", "--optional", "--yes")
check("with --optional the rest is installed too", rc == 0 and pluginscan.can_import("yaml"), (rc, out[-200:]))
rc, out, err = run("plugin-deps", "--dir", root)
check("nothing is missing now", rc == 0 and "Nothing is missing" in out, out)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
