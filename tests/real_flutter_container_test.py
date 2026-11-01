#!/usr/bin/env python3
"""Runs INSIDE a throwaway Ubuntu container as root. The Flutter / Dart recipes against Google's real servers:
 - the release manifest is read, the stable release found, the archive URL answers (size from the server) and its SHA-256 is known;
 - the prerequisites from the Flutter docs are installed by the recipe's own administrator step;
 - the standalone Dart SDK: Google's apt repository, the ONE trusted key, `apt-get install dart`, `dart --version`, removal;
 - with FLUTTER_FULL=1 (slow, ~1.6 GB download, ~4 GB disk) the whole Flutter install runs for real: hash check, unpack, links,
   `flutter --version`, `dart --version` through the link, removal.
(In a container there is no VS Code, so the editor-extension step is skipped by the recipe itself.)"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "installer"))
import extras  # noqa: E402

failed = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail[:300]}]" if detail and not ok else ""))
    if not ok:
        failed.append(name)


def sh(script, **kw):
    return subprocess.run(["sh", "-c", script], capture_output=True, text=True, **kw)


def run_steps(steps):
    r = None
    for st in steps:
        r = sh(st["sh"])
        if r.returncode != 0:
            return r
    return r


sh("apt-get update -qq && apt-get install -y -qq curl ca-certificates gnupg python3")
rel = extras.flutter_release()
check("the stable release is found in Google's manifest", bool(rel["version"]) and len(rel["sha256"]) == 64, str(rel))
check("the archive answers and has a size (GB)", rel["size"] > 500 << 20, str(rel["size"]))
check("the archive URL is Google's", rel["url"].startswith("https://storage.googleapis.com/flutter_infra_release/"))

missing = extras.flutter_missing(glu=False)
check("on a bare system the docs' prerequisites are reported missing", "GLU" in missing and len(missing) >= 2, str(missing))
steps, info = extras.flutter_steps(rel, os.uname().machine, "apt-get", missing)
check("the plan starts with ONE administrator step for the prerequisites", steps and steps[0]["root"] and not any(s["root"] for s in steps[1:]))
r = sh(steps[0]["sh"])
check("the prerequisites install", r.returncode == 0, r.stdout[-200:] + r.stderr[-300:])
check("curl git unzip xz zip are there afterwards", all(sh(f"command -v {c}").returncode == 0 for c in ("curl", "git", "unzip", "xz", "zip")))
check("libGLU is known to the linker", sh("ldconfig -p | grep -q libGLU.so.1").returncode == 0)
check("nothing is reported missing now", extras.flutter_missing() == [], str(extras.flutter_missing()))

d_steps, d_info = extras.dart_steps("apt-get", os.uname().machine)
r = sh(d_steps[0]["sh"])
check("Dart: repository + the one trusted key + apt install dart", r.returncode == 0, r.stdout[-200:] + r.stderr[-300:])
v = sh("dart --version 2>&1")
check("Dart: dart --version answers", v.returncode == 0 and "Dart SDK" in v.stdout, v.stdout)
ring = sh(f"gpg --show-keys --with-colons {extras.DART_KEYRING} | grep -c '^pub'").stdout.strip()
check("Dart: exactly one key in the apt keyring", ring == "1", ring)
r = sh(extras.dart_remove_steps("apt-get")[0]["sh"])
check("Dart: removal runs", r.returncode == 0, r.stdout[-200:] + r.stderr[-200:])
check("Dart: command, repository entry and key are gone", sh("command -v dart").returncode != 0 and not os.path.exists(extras.DART_LIST) and not os.path.exists(extras.DART_KEYRING))

# the optional Linux desktop toolchain: installs only what is missing (git is already here and must stay), `flutter doctor`'s own
# test for it (pkg-config finds GTK 3), and removal takes back only what the recipe added
check("Linux tools: not ready on a bare system", not extras.flutter_linux_ready())
lin_steps, lin_info = extras.flutter_linux_steps("apt-get")
r = run_steps(lin_steps)
check("Linux tools: the missing packages install", r.returncode == 0, r.stdout[-200:] + r.stderr[-300:])
check("Linux tools: clang cmake ninja pkg-config are there", all(sh(f"command -v {c}").returncode == 0 for c in ("clang", "cmake", "ninja", "pkg-config")))
check("Linux tools: GTK 3 headers are found by pkg-config", sh("pkg-config --exists gtk+-3.0 liblzma").returncode == 0)
check("Linux tools: the recipe reports it ready", extras.flutter_linux_ready())
marker = open(extras.flutter_linux_marker()).read().split()
check("Linux tools: the record names what was added", "clang" in marker and "libgtk-3-dev" in marker, str(marker))
r = run_steps(extras.flutter_linux_remove_steps("apt-get"))
check("Linux tools: removal runs", r.returncode == 0, r.stdout[-200:] + r.stderr[-300:])
check("Linux tools: clang and the GTK headers are gone, the record too",
      sh("command -v clang").returncode != 0 and sh("dpkg -s libgtk-3-dev >/dev/null 2>&1").returncode != 0
      and not os.path.exists(extras.flutter_linux_marker()))
check("Linux tools: unrelated packages (git, curl) stay", sh("command -v git && command -v curl").returncode == 0)

if os.environ.get("FLUTTER_FULL") == "1":
    r = run_steps(steps[1:])
    check("Flutter: space check + download + SHA-256 + unpack + links + first start", r.returncode == 0, r.stdout[-300:] + r.stderr[-500:])
    home = os.path.expanduser("~")
    v = sh(f"{home}/.local/bin/flutter --version 2>&1")
    check("Flutter: flutter --version answers through the link", v.returncode == 0 and rel["version"] in v.stdout, v.stdout[-300:])
    v = sh(f"{home}/.local/bin/dart --version 2>&1")
    check("Flutter: the bundled Dart answers through its link", v.returncode == 0 and "Dart SDK" in v.stdout, v.stdout[-300:])
    check("Flutter: the download was removed", not [f for f in os.listdir(os.path.expanduser(extras.CACHE)) if f.endswith(".tar.xz")])
    r = sh(extras.flutter_remove_steps()[0]["sh"])
    check("Flutter: removal", r.returncode == 0 and not os.path.exists(f"{home}/development/flutter") and not os.path.lexists(f"{home}/.local/bin/flutter"), r.stdout + r.stderr)
print("RESULT:", "ALL PASSED" if not failed else f"{len(failed)} FAILED: {failed}")
sys.exit(1 if failed else 0)
