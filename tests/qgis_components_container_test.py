#!/usr/bin/env python3
"""Components for real: install two small ones with the command line, in a throw-away container, as root.

usage: qgis_components_container_test.py      (run by tests/run-recipes-containers.sh)

The list must show them missing, `components install --yes` must really install them with the container's package manager,
the list must then show them present, and installing again must say they are already there. Nothing touches the host.
"""
import contextlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "qgis-installer"))
from qgis_installer import cli, requirements, system  # noqa: E402

fails = []


def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not ok:
        fails.append(name)


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main(["--lang", "en", *argv])
    return rc, out.getvalue(), err.getvalue()


s = system.detect()
pm = s["pm"]
print("system:", s["name"], "| pm:", pm)
WANT = ["proj", "numpy"]                      # small, and present in every distribution we support
rows = {r["id"]: r for r in requirements.components(pm)}
check("both components have a package for this package manager", all(rows[i]["packages"] for i in WANT),
      {i: rows[i]["packages"] for i in WANT})
check("both are missing before", not any(rows[i]["present"] for i in WANT), [i for i in WANT if rows[i]["present"]])

rc, out, err = run("components", "install", *WANT, "--yes")
print(out[-600:])
check("components install --yes succeeds", rc == 0, (rc, err.strip()[-200:]))

rows = {r["id"]: r for r in requirements.components(pm)}
check("both are present afterwards (the system sees them)", all(rows[i]["present"] for i in WANT), [i for i in WANT if not rows[i]["present"]])
rc, out, _ = run("--json", "components")
doc = {r["id"]: r for r in json.loads(out)["components"]}
check("the JSON list agrees", rc == 0 and all(doc[i]["present"] for i in WANT))
rc, out, _ = run("components", "install", *WANT, "--yes")
check("installing again installs nothing and says so", rc == 0 and out.count("already installed") == 2, out)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
