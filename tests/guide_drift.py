#!/usr/bin/env python3
"""Has the QGIS installation guide moved on from what qgis_installer knows?

usage: guide_drift.py [FILE.html]      (no argument: fetch the live guide)

Compares four facts of https://qgis.org/resources/installation-guide/ with qgis_installer.system:
  latest release series (4.2.x)  |  long-term release series (3.44.x)  |  Debian/Ubuntu codenames and which are "only LTR"
  |  the fingerprint of the repository signing key.
Exit 0: nothing changed.  Exit 1: the guide differs (what to update is printed).  Exit 2: the page could not be read as expected
(the guide's layout changed - the parser here needs a look, which is also a finding).
Only facts that are VERIFIED by the tables of the guide are compared; recipes are not (see recipes.py "verified").
"""
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "qgis-installer"))
from qgis_installer import system  # noqa: E402

URL = "https://qgis.org/resources/installation-guide/"


class Unreadable(Exception):
    pass


def fetch(url=URL):
    req = urllib.request.Request(url, headers={"User-Agent": "linux-scripts-guide-drift"})
    with urllib.request.urlopen(req, timeout=60) as r:       # nosec - fixed https URL of the QGIS project
        return r.read().decode("utf-8", "replace")


def _text(cell):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip()


def parse(html):
    """-> {'latest': '4.2.x', 'ltr': '3.44.x', 'codenames': {'debian': {...: only_ltr}, 'ubuntu': {...}}, 'fingerprints': [...]}"""
    out = {}
    m = re.search(r"Latest Release</[^>]+>.{0,400}?(\d+)\.(\d+)\.\d+", html, re.S)
    if not m:
        raise Unreadable("latest release version not found")
    out["latest"] = "{}.{}.x".format(m.group(1), m.group(2))
    m = re.search(r"(\d+)\.(\d+)\.(?:\d+|x)\s+[A-Z][\wÀ-ɏ]+\s+LTR", _text(html))
    if not m:
        raise Unreadable("long-term release version not found")
    out["ltr"] = "{}.{}.x".format(m.group(1), m.group(2))

    table = re.search(r"<table>\s*<thead>\s*<tr>\s*<th>Distribution</th>.*?</table>", html, re.S)
    if not table:
        raise Unreadable("supported-versions table not found")
    names, current = {"debian": {}, "ubuntu": {}}, None
    for row in re.findall(r"<tr>(.*?)</tr>", table.group(0), re.S):
        cells = [_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 4:
            continue
        if cells[0].lower() in names:
            current = cells[0].lower()
        if current is None:
            raise Unreadable("a table row before any distribution name")
        code = re.sub(r"\[\d+\]", "", cells[2]).strip()
        if not re.fullmatch(r"[a-z]+", code):
            raise Unreadable("unexpected codename cell: {!r}".format(cells[2]))
        names[current][code] = cells[3].lower() == "yes"
    if not names["debian"] or not names["ubuntu"]:
        raise Unreadable("no Debian or no Ubuntu rows")
    out["codenames"] = names
    out["fingerprints"] = sorted(set(re.findall(r"\b[0-9A-F]{40}\b", html)))
    return out


def compare(guide, known=None):
    """-> list of human-readable differences (empty: in sync)."""
    known = known or {"latest": system.LATEST, "ltr": system.LTR, "codenames": system.SUPPORT, "fingerprint": system.KEY_FPR}
    diffs = []
    if guide["latest"] != known["latest"]:
        diffs.append("latest release: guide {} / system.LATEST {}".format(guide["latest"], known["latest"]))
    if guide["ltr"] != known["ltr"]:
        diffs.append("long-term release: guide {} / system.LTR {}".format(guide["ltr"], known["ltr"]))
    for fam in ("debian", "ubuntu"):
        g, k = guide["codenames"][fam], known["codenames"][fam]
        for code in sorted(set(g) - set(k)):
            diffs.append("{}: the guide lists '{}' ({}), system.SUPPORT does not".format(
                fam, code, "only LTR" if g[code] else "latest and LTR"))
        for code in sorted(set(k) - set(g)):
            diffs.append("{}: system.SUPPORT has '{}', the guide no longer lists it".format(fam, code))
        for code in sorted(set(g) & set(k)):
            if g[code] != k[code]:
                diffs.append("{}: '{}' only-LTR is {} in the guide, {} in system.SUPPORT".format(fam, code, g[code], k[code]))
    if known["fingerprint"] not in guide["fingerprints"]:
        diffs.append("signing key fingerprint {} is not in the guide any more (guide shows: {})".format(
            known["fingerprint"], ", ".join(guide["fingerprints"]) or "none"))
    return diffs


def main(argv):
    try:
        if len(argv) > 1:
            with open(argv[1], encoding="utf-8", errors="replace") as f:
                html = f.read()
        else:
            html = fetch()
    except OSError as exc:
        print("cannot read the guide: {}".format(exc))
        return 2
    try:
        guide = parse(html)
    except Unreadable as exc:
        print("the guide's layout is not what this check expects: {}".format(exc))
        return 2
    diffs = compare(guide)
    if not diffs:
        print("in sync with the guide: latest {}, LTR {}, {} Debian + {} Ubuntu codenames, key {}".format(
            guide["latest"], guide["ltr"], len(guide["codenames"]["debian"]), len(guide["codenames"]["ubuntu"]),
            system.KEY_FPR[-8:]))
        return 0
    print("The installation guide differs from qgis_installer.system:")
    for d in diffs:
        print(" - " + d)
    print("Update qgis_installer/system.py (and the codename fixtures/tests), then re-run tests/run-qgis-containers.sh.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
