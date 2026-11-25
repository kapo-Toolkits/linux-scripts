#!/usr/bin/env python3
"""printer-setup "Phones" tab against a REAL cupsd (a throw-away Ubuntu container): runs the exact sharing script the window runs
through pkexec, then asks the printer for its attributes over IPP from outside the container, the way a phone does.
Needs docker. Run: python3 tests/real_printer_share_test.py   (nothing on this computer is changed)"""
import importlib.util
import os
import shutil
import struct
import subprocess
import sys
import time
import types
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "common"))
for n in ("tkinter", "tkinter.ttk", "tkinter.messagebox", "tkinter.scrolledtext", "tkinter.filedialog"):
    sys.modules[n] = types.ModuleType(n)
sys.modules["tkinter"].Tk = object
spec = importlib.util.spec_from_file_location("printer_setup_gui", os.path.join(ROOT, "printer-setup", "printer-setup-gui.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

fails = []
Q = "Test_Printer"


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok else "   " + str(detail)[:400]))
    if not ok:
        fails.append(label)


def sh(*cmd, **kw):
    return subprocess.run(list(cmd), capture_output=True, text=True, **kw)


def ipp_request(ip, queue, op):
    """An IPP request as a phone sends it (0x000B Get-Printer-Attributes, 0x0005 Create-Job, which goes through CUPS' sharing check) -> IPP status code,
    or None when the connection is refused."""
    uri = f"ipp://{ip}:631/printers/{queue}".encode()

    def attr(tag, name, value):
        return bytes([tag]) + struct.pack(">H", len(name)) + name + struct.pack(">H", len(value)) + value
    body = (b"\x02\x00" + struct.pack(">HI", op, 1) + b"\x01" + attr(0x47, b"attributes-charset", b"utf-8")
            + attr(0x48, b"attributes-natural-language", b"en") + attr(0x45, b"printer-uri", uri)
            + attr(0x42, b"requesting-user-name", b"phone") + b"\x03")
    req = urllib.request.Request(f"http://{ip}:631/printers/{queue}", data=body, headers={"Content-Type": "application/ipp"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return struct.unpack(">H", r.read()[2:4])[0]
    except (urllib.error.URLError, OSError):
        return None


if not shutil.which("docker"):
    print("SKIP: docker is not installed")
    sys.exit(0)

name = "ls-cups-%d" % os.getpid()
setup = f"""set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq --no-install-recommends cups cups-client cups-bsd >/dev/null
cupsd
for i in $(seq 50); do lpstat -r >/dev/null 2>&1 && break; sleep 0.2; done
lpadmin -p {Q} -E -v socket://127.0.0.1:9100 -m drv:///sample.drv/generic.ppd
lpadmin -p {Q} -o printer-is-shared=false
cupsctl --no-share-printers
"""
r = sh("docker", "run", "-d", "--rm", "--name", name, "ubuntu:24.04", "sleep", "900")
if r.returncode:
    print("FAIL could not start the container", r.stderr)
    sys.exit(1)
try:
    r = sh("docker", "exec", name, "sh", "-c", setup, timeout=600)
    check("cupsd with one queue in the container", r.returncode == 0, r.stdout + r.stderr)
    ip = sh("docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", name).stdout.strip()

    def run_in(cmd, timeout=None):
        p = sh("docker", "exec", name, *cmd, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()

    st = m.share_status(Q, run=run_in)
    check("before: status says not shared", st["queue"] is False and st["server"] is False, st)
    check("before: a phone on the network cannot reach the printer", ipp_request(ip, Q, 0x000B) is None)

    # the window runs ["pkexec", "sh", "-c", SHARE_SH, "sh", queue, "on"]; in the container we already are root
    cmd = m.share_command(Q, True)
    check("the command is pkexec + the fixed script", cmd[0] == "pkexec" and cmd[3] == m.SHARE_SH)
    rc, out = run_in(cmd[1:], timeout=120)
    check("share script (on) succeeds", rc == 0, out)
    st = m.share_status(Q, run=run_in)
    check("after on: queue and CUPS sharing are on", st["queue"] and st["server"], st)
    time.sleep(1)
    code = None
    for _ in range(20):                       # cupsd restarts after cupsctl; give it a moment
        code = ipp_request(ip, Q, 0x000B)
        if code is not None:
            break
        time.sleep(0.5)
    check("after on: Get-Printer-Attributes from outside answers successful-ok", code == 0, code)
    code = ipp_request(ip, Q, 0x0005)
    check("after on: Create-Job from outside is accepted", code == 0, code)

    rc, out = run_in(m.share_command(Q, False)[1:], timeout=60)
    check("share script (off) succeeds", rc == 0, out)
    st = m.share_status(Q, run=run_in)
    check("after off: the queue is not shared", st["queue"] is False, st)
    code = ipp_request(ip, Q, 0x0005)
    check("after off: a job from outside is refused", code is None or code >= 0x0400, code)

    rc, out = run_in(["sh", "-c", m.SHARE_SH, "sh", "No_Such_Queue", "on"], timeout=60)
    check("an unknown queue fails (no silent success)", rc != 0, out)
    rc, out = run_in(["lpstat", "-p", "No_Such_Queue"])
    check("... and is not created", rc != 0, out)
finally:
    sh("docker", "rm", "-f", name)

print("\n%d failure(s)" % len(fails) if fails else "\nall passed")
sys.exit(1 if fails else 0)
