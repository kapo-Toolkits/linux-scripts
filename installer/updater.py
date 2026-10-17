#!/usr/bin/env python3
"""Keeping a copy of the toolkit up to date from GitHub (no UI). Used by the installer window's Settings.

A computer that got the folder by copying (USB stick, zip) has no link to GitHub; one that was cloned has. Both are handled:
  - a git checkout:  `git fetch` + compare, then `git pull --ff-only` (refuses when tracked files were changed here);
  - a plain copy:    "adopt" it - `git init`, add the GitHub remote, fetch, check out main over the tracked files
                     (files git does not track, like start-installer.desktop, are left alone), after which it is a checkout.

    python3 installer/updater.py check [DIR]      # what is new on GitHub
    python3 installer/updater.py update [DIR]     # fetch + pull (or adopt a plain copy)
"""
import json
import os
import subprocess
import sys
import time

REPO_URL = "https://github.com/kapo-Toolkits/linux-scripts.git"
BRANCH = "main"
CHECK_INTERVAL = 6 * 3600          # the quiet check at start-up runs at most this often


def settings_path():
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "linux-scripts", "settings.json")


def load_settings(path=None):
    try:
        with open(path or settings_path()) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data, path=None):
    path = path or settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=1)
        return True
    except OSError:
        return False


def should_check(settings, now=None):
    """True when the quiet start-up check is switched on (default: on) and was not done in the last few hours."""
    if not settings.get("auto_update_check", True):
        return False
    return (now if now is not None else time.time()) - float(settings.get("last_update_check", 0) or 0) >= CHECK_INTERVAL


def _git(root, *args, run=subprocess.run, timeout=90, raw=False):
    try:
        p = run(["git", "-C", root] + list(args), capture_output=True, text=True, timeout=timeout)
        out = p.stdout + p.stderr
        return p.returncode, (out if raw else out.strip())
    except FileNotFoundError:
        return 127, "git is not installed"
    except Exception as e:  # noqa: BLE001
        return 1, str(e)


def local_info(root, run=subprocess.run):
    """{'git': False} for a plain copy (or a folder nested in somebody else's repository), else sha / branch / date / dirty."""
    rc, top = _git(root, "rev-parse", "--show-toplevel", run=run)
    if rc != 0:
        return {"git": False, "error": top if rc == 127 else ""}
    if os.path.realpath(top) != os.path.realpath(root):
        return {"git": False, "nested_in": top}
    sha = _git(root, "rev-parse", "HEAD", run=run)[1]
    return {"git": True, "sha": sha, "short": sha[:7],
            "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD", run=run)[1],
            "date": _git(root, "log", "-1", "--format=%cs", run=run)[1],
            "dirty": [ln[3:] for ln in _git(root, "status", "--porcelain", "--untracked-files=no", run=run, raw=True)[1].splitlines()]}


def check(root, remote="origin", branch=BRANCH, run=subprocess.run):
    """-> {'mode': 'git'|'adopt'|'error', 'behind': n, 'commits': [(sha, title)], 'local': info, 'error': str}"""
    info = local_info(root, run)
    if not info["git"]:
        if info.get("nested_in"):
            return {"mode": "error", "local": info, "error": f"this folder lies inside another git repository ({info['nested_in']})"}
        if info.get("error"):
            return {"mode": "error", "local": info, "error": info["error"]}
        return {"mode": "adopt", "local": info, "behind": None, "commits": []}
    rc, out = _git(root, "fetch", "--quiet", remote, branch, run=run, timeout=120)
    if rc != 0:
        return {"mode": "error", "local": info, "error": out}
    target = f"{remote}/{branch}"
    behind = int(_git(root, "rev-list", "--count", f"HEAD..{target}", run=run)[1] or 0)
    ahead = int(_git(root, "rev-list", "--count", f"{target}..HEAD", run=run)[1] or 0)
    log = _git(root, "log", "--format=%h\\t%s", "-n", "30", f"HEAD..{target}", run=run)[1]
    commits = [tuple(ln.split("\\t", 1)) for ln in log.splitlines() if "\\t" in ln]
    return {"mode": "git", "local": info, "behind": behind, "ahead": ahead, "commits": commits}


def update(root, remote="origin", branch=BRANCH, run=subprocess.run):
    """Bring the checkout to the latest `branch`. -> (ok, message). Never touches files you changed: it refuses instead."""
    info = local_info(root, run)
    if not info["git"]:
        return False, "not a git checkout - adopt it first"
    if info["dirty"]:
        return False, "files were changed here, update refused: " + ", ".join(info["dirty"][:8])
    if info["branch"] != branch:
        rc, out = _git(root, "checkout", branch, run=run)
        if rc != 0:
            rc, out = _git(root, "checkout", "-B", branch, f"{remote}/{branch}", run=run)
        if rc != 0:
            return False, out
    rc, out = _git(root, "pull", "--ff-only", remote, branch, run=run, timeout=180)
    return rc == 0, out


def adopt(root, url=REPO_URL, branch=BRANCH, run=subprocess.run):
    """Turn a plain copy into a checkout of GitHub's `branch`; tracked files are replaced, untracked ones stay. -> (ok, message)"""
    if not os.path.isfile(os.path.join(root, "install.sh")):
        return False, "this does not look like the linux-scripts folder (no install.sh)"
    info = local_info(root, run)
    if info["git"]:
        return False, "already a git checkout"
    if info.get("nested_in"):
        return False, f"this folder lies inside another git repository ({info['nested_in']})"
    for args in (("init", "-q"), ("remote", "add", "origin", url), ("fetch", "--quiet", "origin", branch),
                 ("checkout", "-q", "-f", "-B", branch, f"origin/{branch}")):
        rc, out = _git(root, *args, run=run, timeout=180)
        if rc != 0:
            return False, f"git {args[0]} failed: {out}"
    return True, "connected to GitHub"


def main(argv):
    if not argv or argv[0] not in ("check", "update"):
        print(__doc__)
        return 2
    root = os.path.abspath(argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    res = check(root)
    if argv[0] == "check":
        if res["mode"] == "error":
            print("error:", res["error"])
            return 1
        if res["mode"] == "adopt":
            print("plain copy (no link to GitHub): run `update` to connect it and get the latest")
            return 0
        print(f"{res['local']['short']} ({res['local']['branch']}, {res['local']['date']}): {res['behind']} new on GitHub")
        for sha, title in res["commits"]:
            print(f"  {sha}  {title}")
        return 0
    if res["mode"] == "error":
        print("error:", res["error"])
        return 1
    ok, msg = adopt(root) if res["mode"] == "adopt" else update(root)
    print(("updated: " if ok else "not updated: ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
