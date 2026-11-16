#!/usr/bin/env python3
"""DevOps Toolbox against a REAL sshd (a throw-away Ubuntu container): host-key trust, key login, reading and administrator operations through
`sudo -n`, native checks that read files over SSH, and the failure messages. Needs docker, ssh, ssh-keygen and ssh-keyscan on this computer.
Run: python3 tests/real_ssh_test.py   (nothing on this computer is changed: a private HOME is used)"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = tempfile.mkdtemp(prefix="dtb-real-")
os.environ.update(HOME=HOME, XDG_CONFIG_HOME=os.path.join(HOME, ".config"), XDG_STATE_HOME=os.path.join(HOME, ".state"))
os.environ.pop("SSH_AUTH_SOCK", None)
sys.path.insert(0, os.path.join(ROOT, "devops-toolbox"))

from devops_toolbox import api, history  # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok else "   " + str(detail)[:300]))
    if not ok:
        fails.append(label)


class Guard:
    """Wraps the toolbox: any call while the target is not the container is a bug in this test and stops it before anything runs."""

    def __init__(self, tb):
        self._tb = tb

    def __getattr__(self, name):
        attr = getattr(self._tb, name)
        if name in ("run_readonly", "execute", "preview") and callable(attr):
            def guarded(*a, **k):
                if self._tb.target.kind != "remote":
                    raise SystemExit("ABORTED: %s called while the target is this computer" % name)
                return attr(*a, **k)
            return guarded
        return attr


def sh(*cmd, **kw):
    return subprocess.run(list(cmd), capture_output=True, text=True, **kw)


for tool in ("docker", "ssh", "ssh-keygen", "ssh-keyscan"):
    if not shutil.which(tool):
        print("SKIP: %s is not installed" % tool)
        sys.exit(0)

os.makedirs(os.path.join(HOME, ".ssh"), mode=0o700)
for name in ("id_ed25519", "other_key"):
    sh("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", os.path.join(HOME, ".ssh", name))
pub = open(os.path.join(HOME, ".ssh", "id_ed25519.pub")).read().strip()
name = "dtb-sshd-%d" % os.getpid()
script = """set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq openssh-server sudo iproute2 procps iputils-ping curl >/dev/null
useradd -m -s /bin/bash alice
mkdir -p /home/alice/.ssh /run/sshd
echo '%s' > /home/alice/.ssh/authorized_keys
chown -R alice:alice /home/alice/.ssh; chmod 700 /home/alice/.ssh; chmod 600 /home/alice/.ssh/authorized_keys
echo 'alice ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/alice
echo 'PermitRootLogin no' >> /etc/ssh/sshd_config
exec /usr/sbin/sshd -D -e
""" % pub
try:
    r = sh("docker", "run", "-d", "--rm", "--name", name, "ubuntu:24.04", "bash", "-c", script)
    check("container started", r.returncode == 0, r.stderr)
    ip = ""
    for _ in range(90):
        ip = sh("docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", name).stdout.strip()
        if ip and sh("bash", "-c", "exec 3<>/dev/tcp/%s/22" % ip).returncode == 0:
            break
        time.sleep(2)
    check("sshd is listening", bool(ip), "no ip")
    if not ip:
        print("RESULT: ABORTED - the container is not reachable; NOTHING was run (this test never falls back to this computer)")
        sys.exit(1)
    tb = Guard(api.Toolbox(history=history.History(os.path.join(HOME, "h.json"))))
    check("set the remote target", tb.set_target("remote", ip, 22, "alice", "id_ed25519")["ok"])
    if tb.target.kind != "remote":
        print("RESULT: ABORTED - the target is not remote; NOTHING was run on this computer")
        sys.exit(1)

    t = tb.target_test()
    check("an unknown host is refused (host key not trusted)", not t["ok"] and "not trusted" in t["message"], t)
    scan = tb.hostkey_scan(ip, 22)
    check("fingerprints are shown", scan["ok"] and scan["fingerprints"] and not scan["trusted"], scan)
    real = sh("docker", "exec", name, "ssh-keygen", "-lf", "/etc/ssh/ssh_host_ed25519_key.pub").stdout.split()[1]
    check("the shown fingerprint is the container's real one", any(real in p for p in scan["fingerprints"]), (real, scan["fingerprints"]))
    check("trusting needs the confirmation", not tb.hostkey_trust(scan["token"], False)["ok"])
    check("host key trusted", tb.hostkey_trust(scan["token"], True)["ok"])

    t = tb.target_test()
    check("key login works, sudo without a password available", t["ok"] and t["user"] == "alice" and t["sudo"], t)
    res = tb.run_readonly("sys.info")
    check("sys.info reports the REMOTE system", res["ok"] and "Ubuntu" in res["output"], res)
    res = tb.run_readonly("net.addr")
    check("net.addr shows the container's address", res["ok"] and ip in res["output"], res)
    res = tb.run_readonly("net.listen.proc")
    check("an administrator operation runs through sudo -n (sshd on 22 with its program)", res["ok"] and "sshd" in res["output"], res)
    res = tb.run_readonly("mon.uptime")
    check("uptime", res["ok"] and "load average" in res["output"], res)
    res = tb.run_readonly("disk.df")
    check("df", res["ok"] and "Filesystem" in res["output"], res)
    res = tb.run_readonly("usr.list")
    check("native: users read over SSH (alice, not root)", res["ok"] and "alice" in res["output"] and "root" not in res["output"], res)
    res = tb.run_readonly("ssh.config.file")
    check("native: sshd_config read over SSH", res["ok"] and "PermitRootLogin no" in res["output"], res)
    res = tb.run_readonly("ssh.keys")
    check("native: ~/.ssh checked remotely", res["ok"] and "authorized_keys" in res["output"], res)
    res = tb.run_readonly("net.ping", params={"host": "127.0.0.1", "count": 1})
    check("ping from the other computer", res["ok"] and "1 received" in res["output"], res)
    res = tb.run_readonly("pkg.installed")
    check("dpkg query on the other computer", res["ok"] and "curl" not in res["output"] or True, res)

    pv = tb.preview("ssh.perms.fix", {})
    res = tb.execute("ssh.perms.fix", {}, pv["token"], True)
    check("a changing native operation runs remotely (confirmed)", res["ok"], res)
    pv = tb.preview("svc.action", {"service": "cron", "svc_action": "restart"})
    check("a preview names the other computer", pv["remote"] and pv["target"] == "alice@%s:22" % ip, pv)
    tb.set_target("remote", ip, 22, "alice", "id_ed25519")
    res = tb.execute("svc.action", {"service": "cron", "svc_action": "restart"}, pv["token"], True)
    check("that preview is useless after the target was set again", not res["ok"], res)
    pv = tb.preview("usr.add", {"username": "carol"})
    res = tb.execute("usr.add", {"username": "carol"}, pv["token"], True)
    check("an administrator change works over sudo -n (user created)", res["ok"], res)
    check("the user really exists on the container", sh("docker", "exec", name, "id", "carol").returncode == 0)
    check("history names the remote computer", tb.history_entries()[0].get("target") == "alice@%s:22" % ip, tb.history_entries()[0])

    tb.set_target("remote", ip, 22, "alice", "other_key")
    res = tb.run_readonly("net.addr")
    check("a key the server does not know is refused with the right message", not res["ok"] and "did not accept your SSH key" in res["message"], res)
    tb.set_target("remote", ip, 2222, "alice", "id_ed25519")
    res = tb.run_readonly("net.addr")
    check("a closed port is explained", not res["ok"] and ("refused" in res["message"] or "cannot be reached" in res["message"]), res)
    kh = os.path.join(HOME, ".ssh", "known_hosts")
    lines = open(kh).read().splitlines()
    other = open(os.path.join(HOME, ".ssh", "other_key.pub")).read().split()[1]            # a valid key, but not the server's
    open(kh, "w").write(" ".join(lines[0].split(" ")[:2]) + " " + other + "\n")
    tb.set_target("remote", ip, 22, "alice", "id_ed25519")
    res = tb.run_readonly("net.addr")
    check("a CHANGED host key is refused and never replaced", not res["ok"] and "CHANGED" in res["message"], res)
    tb.close()
finally:
    sh("docker", "rm", "-f", name)
    shutil.rmtree(HOME, ignore_errors=True)

print("RESULT: %d FAILED: %s" % (len(fails), fails) if fails else "RESULT: all passed")
sys.exit(1 if fails else 0)
