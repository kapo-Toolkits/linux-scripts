#!/usr/bin/env python3
"""An environment file for real, in a throw-away container, as root: check -> apply -> check -> export.

usage: qgis_envfile_container_test.py       (run by tests/run-recipes-containers.sh envfile IMAGE)

QGIS itself is far too big for this; the QGIS part of a plan is checked as a plan (built and shell-parsed for this distribution), the
components are installed for real: exiftool and numpy (small everywhere).
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "qgis-installer"))
from qgis_installer import cli, envspec, recipes, requirements, system  # noqa: E402

fails = []


def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{str(extra)[:200]}]" if extra else ""))
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
WANT = ["exiftool", "numpy"]
tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "lab.json")
with open(path, "w", encoding="utf-8") as fh:
    json.dump({"schema": 1, "name": "test lab", "created": "2026-10-15", "components": WANT, "qgis": None}, fh)

rc, out, err = run("env", "check", path)
check("check: both are missing, exit code 1 says so", rc == 1 and "Components: 0 of 2 present" in out and "to install:" in out, (rc, out))
rc, out, err = run("env", "apply", path, "--dry-run")
check("apply --dry-run shows the commands and the simulation, installs nothing",
      rc == 0 and "What the package manager says it would do" in out and not any(requirements.is_present(c) for c in WANT), out[-300:])

rc, out, err = run("env", "apply", path, "--yes")
check("apply --yes installs for real", rc == 0 and "Finished successfully" in out, (rc, err.strip()[-200:]))
rows = {r["id"]: r for r in requirements.components(pm)}
check("the system sees both afterwards", all(rows[c]["present"] for c in WANT), [c for c in WANT if not rows[c]["present"]])
rc, out, err = run("env", "check", path)
check("check: it matches now (exit 0)", rc == 0 and "Components: 2 of 2 present" in out, (rc, out))
rc, out, err = run("env", "apply", path, "--yes")
check("apply again: nothing to do", rc == 0 and "already matches" in out, out)

rc, out, err = run("env", "export", "--name", "after")
doc = json.loads(out)
check("export lists both components", rc == 0 and all(c in doc["components"] for c in WANT) and doc["name"] == "after", doc)
envspec.validate(doc)
exported = os.path.join(tmp, "exported.json")
rc, out, err = run("env", "export", "--output", exported)
rc, out, err = run("env", "check", exported)
check("a file exported here checks clean here", rc == 0, out)

# the QGIS part of a file written for another system: the plan for THIS one is built, not run
spec = envspec.validate({"schema": 1, "components": [], "qgis": {"goal": "stable", "recipe": "apt-official", "options": {"channel": "ltr"}}})
plan = envspec.plan(spec, [], requirements.components(pm), s)
if plan["steps"] or plan["manual"]:
    bad = [st["sh"] for st in plan["steps"] if subprocess.run(["sh", "-n", "-c", st["sh"]], capture_output=True).returncode != 0]
    check("the QGIS part for this system is a plan that parses (recipe: {})".format(plan["recipe"]), bad == [], bad)
    check("an Ubuntu recipe on another system is swapped for the recommendation of its goal",
          plan["recipe"] == "apt-official" or "env_recipe_swapped" in plan["notes"], (plan["recipe"], plan["notes"]))
    check("what it chose is a real recipe", plan["recipe"] in recipes.RECIPES, plan["recipe"])

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
