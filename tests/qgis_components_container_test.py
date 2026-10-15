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
WANT = ["exiftool", "numpy"]                  # small everywhere (PROJ is not: on Fedora it brings 779 MiB of datum grids)
rows = {r["id"]: r for r in requirements.components(pm)}
check("both components have a package for this package manager", all(rows[i]["packages"] for i in WANT),
      {i: rows[i]["packages"] for i in WANT})
check("both are missing before", not any(rows[i]["present"] for i in WANT), [i for i in WANT if rows[i]["present"]])

# before installing: ask the real package manager what it would do (simulation), as the preview does
from qgis_installer import simulate  # noqa: E402
steps, _ = requirements.install_steps(WANT, pm)
sim = simulate.explain(steps)
print(simulate.format_text(sim, "en"))
check("the simulation understood the real package manager's answer", len(sim["items"]) == 1 and sim["unsimulated"] == 0, sim)
if sim["items"]:
    it = sim["items"][0]
    check("it says how many packages would be installed", it["installs"] > 0, it)
    check("it says how much would be downloaded or used (or the tool does not tell)", bool(it.get("download") or it.get("disk")) or pm == "apk", it)
    check("installing two small components removes nothing", sim["warnings"] == [] and it["remove_count"] == 0, sim["warnings"])

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

# a removal that drags dependents along is reported (apt: numpy <- scipy, installed here only for this check)
if pm == "apt-get":
    import subprocess
    subprocess.run(["apt-get", "install", "-y", "-qq", "python3-scipy"], capture_output=True)
    rm = simulate.explain([{"root": True, "sh": "apt-get remove -y python3-numpy\n"}])
    keys = [k for k, _ in rm["warnings"]]
    check("removing numpy is reported to take scipy with it", keys == ["sim_removes_dependents"] and "python3-scipy" in rm["warnings"][0][1]["names"], rm)

# "is a newer build waiting?" asked of the real package manager about what was just installed: it must answer yes or no, not "could not tell"
from qgis_installer import instances  # noqa: E402
pkg = rows[WANT[0]]["packages"][0]
item = ({"kind": "apt", "pkgs": [pkg], "v": "x", "root": True} if pm == "apt-get"
        else {"kind": "dist", "pm": pm, "pkgs": [pkg], "v": "x", "root": True})
res = instances.check_updates([item])[0]
check("the package manager answers whether a newer build is waiting (not 'could not tell')", res["update"] in (True, False), res)
check("a package that was just installed from the current index has no update waiting", res["update"] is False, res)
rows_i = instances.list_instances([item], which=lambda c: None)
check("instances lists it with an id and no start command (it is not QGIS)", len(rows_i) == 1 and rows_i[0]["launch"] is None, rows_i)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
