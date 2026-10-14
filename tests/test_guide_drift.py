#!/usr/bin/env python3
"""tests/guide_drift.py against a saved excerpt of the real guide and against edited copies of it (offline)."""
import contextlib
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import guide_drift  # noqa: E402

with open(os.path.join(HERE, "fixtures", "guide-excerpt.html"), encoding="utf-8") as _f:
    EXCERPT = _f.read()


def run(html):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "g.html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(html)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = guide_drift.main(["guide_drift.py", p])
    return rc, out.getvalue()


class Drift(unittest.TestCase):
    def test_the_excerpt_is_in_sync(self):
        rc, out = run(EXCERPT)
        self.assertEqual(rc, 0, out)
        self.assertIn("in sync", out)

    def test_parse_reads_the_facts(self):
        g = guide_drift.parse(EXCERPT)
        self.assertEqual((g["latest"], g["ltr"]), ("4.2.x", "3.44.x"))
        self.assertEqual(g["codenames"]["debian"], {"bookworm": True, "trixie": False, "sid": False})
        self.assertEqual(g["codenames"]["ubuntu"]["noble"], True)
        self.assertEqual(g["codenames"]["ubuntu"]["resolute"], False)
        self.assertIn("2D7E3441A707FDB3E7059441D155B8E6A419C5BE", g["fingerprints"])

    def test_a_new_release_is_reported(self):
        rc, out = run(EXCERPT.replace("4.2.3", "4.3.0").replace("3.44.15", "3.44.16"))
        self.assertEqual(rc, 1)
        self.assertIn("latest release: guide 4.3.x", out)
        self.assertNotIn("long-term", out)                    # a point release of the LTR is no drift

    def test_a_new_ltr_is_reported(self):
        rc, out = run(EXCERPT.replace("3.44", "3.46"))
        self.assertEqual(rc, 1)
        self.assertIn("long-term release: guide 3.46.x", out)

    def test_a_new_ubuntu_is_reported_and_a_dropped_one_too(self):
        rc, out = run(EXCERPT.replace("<td>resolute", "<td>zesty").replace("<td>jammy", "<td>kinetic"))
        self.assertEqual(rc, 1)
        self.assertIn("lists 'zesty'", out)
        self.assertIn("system.SUPPORT has 'resolute'", out)
        self.assertIn("lists 'kinetic'", out)
        self.assertIn("system.SUPPORT has 'jammy'", out)

    def test_a_flipped_only_ltr_flag_is_reported(self):
        rc, out = run(EXCERPT.replace("trixie<a href=#id3>[3]</a></td><td></td>", "trixie<a href=#id3>[3]</a></td><td>yes</td>"))
        self.assertEqual(rc, 1)
        self.assertIn("'trixie' only-LTR is True in the guide", out)

    def test_a_rotated_key_is_reported(self):
        rc, out = run(EXCERPT.replace("2D7E3441A707FDB3E7059441D155B8E6A419C5BE", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"))
        self.assertEqual(rc, 1)
        self.assertIn("fingerprint", out)

    def test_a_changed_layout_is_not_mistaken_for_no_change(self):
        for broken in (EXCERPT.replace("Latest Release", "Newest"),
                       EXCERPT.replace("<th>Distribution</th>", "<th>Distro</th>"),
                       "<html>maintenance</html>"):
            rc, out = run(broken)
            self.assertEqual(rc, 2, out)

    def test_unreadable_file_is_exit_2(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(guide_drift.main(["x", os.path.join(HERE, "no-such-file.html")]), 2)


if __name__ == "__main__":
    unittest.main()
