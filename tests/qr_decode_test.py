#!/usr/bin/env python3
"""Decode-check for common/lsqr.py with a real QR reader (zbarimg -Sbinary: raw bytes, because without an ECI
mark zbar guesses Shift-JIS for UTF-8 text, which phones do not). Run inside a container that has
zbar-tools (see tests/run-qr-decode.sh).  Every version boundary 1..10, special characters, Georgian text."""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
import lsqr  # noqa: E402

cases = [lsqr.wifi_payload("MyHotspot", "secret123"),
         lsqr.wifi_payload('We;ird:"na,me\\', 'p;a:s"s,\\word99'),
         lsqr.wifi_payload("ჰოტსპოტი-კაპო", "parolilatinuri"),
         lsqr.wifi_payload("Open", ""),
         lsqr.wifi_payload("Hidden", "abcdefgh", hidden=True),
         "x", "https://qgis.org"]
# every byte-capacity boundary of versions 1..10 (level M): 14 26 42 62 84 106 122 152 180 213
for cap in (14, 26, 42, 62, 84, 106, 122, 152, 180, 213):
    for n in (cap - 1, cap):
        cases.append("".join(chr(65 + (i * 7) % 26) for i in range(n)))
cases.append("ა" * 70)       # 210 bytes of UTF-8

fails = 0
with tempfile.TemporaryDirectory() as d:
    for i, text in enumerate(cases):
        path = os.path.join(d, f"{i}.pbm")
        open(path, "wb").write(lsqr.to_pbm(lsqr.make_qr(text), scale=6))
        out = subprocess.run(["zbarimg", "-q", "--raw", "--oneshot", "-Sbinary", path], capture_output=True)
        got = out.stdout.decode("utf-8", "replace").rstrip("\n")
        ok = got == text
        fails += not ok
        print(("PASS" if ok else "FAIL"), f"#{i:02d} len={len(text.encode())}B version={(len(lsqr.make_qr(text)) - 17) // 4}",
              "" if ok else f"\n   want {text!r}\n   got  {got!r} rc={out.returncode} {out.stderr.decode()[:100]}")
print("RESULT:", "ALL PASS" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
