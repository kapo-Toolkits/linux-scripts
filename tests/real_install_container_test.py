#!/usr/bin/env python3
"""Runs INSIDE a throwaway Debian/Ubuntu container as root: the installer's recipes against the real publishers.
 - Claude Desktop and VS Code: key + fingerprint gate + repository entry for real, apt must offer the package from the
   publisher's repository; then the removal steps must take the repository entry (and key) away again.
 - ArtCraft Launcher: the real GitHub release is downloaded, SHA-256 checked and installed with apt, then purged.
(The last 'apt-get install' of the two big apps is cut off: it would only download hundreds of MB.)"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "installer"))
import extras  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail[:200]}]" if detail and not ok else ""))
    if not ok:
        FAILED.append(name)


def sh(script, **kw):
    return subprocess.run(["sh", "-c", script], capture_output=True, text=True, **kw)


def without_final_install(script, package):
    return "\n".join(ln for ln in script.splitlines() if ln.strip() != f"apt-get install -y {package}") + "\n"


def run_steps(steps):
    for st in steps:
        r = sh(st["sh"])
        if r.returncode != 0:
            return r
    return r


def candidate(package):
    out = sh(f"apt-cache policy {package}").stdout
    line = next((ln for ln in out.splitlines() if "Candidate:" in ln), "")
    return line.split(":", 1)[1].strip() if line else "(none)"


def repo_app(name, steps, package, host, remove_steps, files):
    script = without_final_install(steps[0]["sh"], package)
    r = sh(script)
    check(f"{name}: recipe runs (key fingerprint checked, repository added)", r.returncode == 0, r.stdout + r.stderr)
    check(f"{name}: repository entry and key are on disk", all(os.path.exists(f) for f in files), str(files))
    pol = sh(f"apt-cache policy {package}").stdout
    check(f"{name}: apt offers {package} from {host}", candidate(package) not in ("(none)", "") and host in pol, pol)
    r = run_steps(remove_steps)
    check(f"{name}: removal steps run", r.returncode == 0, r.stdout + r.stderr)
    gone = [f for f in files if os.path.exists(f)]
    check(f"{name}: repository entry and key are gone afterwards", not gone, str(gone))
    check(f"{name}: apt no longer offers it", candidate(package) in ("(none)", ""), sh(f"apt-cache policy {package}").stdout)


def main():
    sh("apt-get update -qq && apt-get install -y -qq curl gnupg ca-certificates")
    arch = "x86_64"

    steps, _ = extras.claude_steps("apt-get", arch)
    repo_app("claude", steps, "claude-desktop", "downloads.claude.ai", extras.claude_remove_steps("apt-get"),
             [extras.CLAUDE_KEYRING, extras.CLAUDE_LIST])

    steps, _ = extras.vscode_steps("apt-get", arch)
    repo_app("vscode", steps, "code", "packages.microsoft.com", extras.vscode_remove_steps("apt-get"),
             [extras.VSCODE_KEYRING, extras.VSCODE_LIST])

    rel = extras.github_release("artcraft")
    steps, info = extras.github_steps("artcraft", rel, "apt-get", arch)
    check("artcraft: a checked package was found in the latest release", bool(steps), str(info))
    if steps:
        r = run_steps(steps)
        check("artcraft: download + SHA-256 + apt install", r.returncode == 0, r.stdout + r.stderr)
        check("artcraft: dpkg says installed", sh("dpkg -s artcraft-launcher").returncode == 0)
        r = run_steps(extras.apt_remove_steps("artcraft-launcher", "apt-get"))
        check("artcraft: purge", r.returncode == 0, r.stdout + r.stderr)
        check("artcraft: gone", sh("dpkg -s artcraft-launcher").returncode != 0)
        check("artcraft: downloaded file cleaned up", not [f for f in os.listdir(os.path.expanduser(extras.CACHE)) if f.endswith(".deb")])
    print("RESULT:", "ALL PASSED" if not FAILED else f"{len(FAILED)} FAILED: {FAILED}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
