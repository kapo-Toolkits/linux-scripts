#!/usr/bin/env python3
"""QGIS Installer, command line. See `qgis-installer-cli --help`."""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
for _p in reversed((_here, os.path.join(_here, "..", "common"), os.path.join(_here, "..", "lib", "linux-scripts"),
                    "/usr/local/lib/linux-scripts", "/usr/lib/linux-scripts")):   # first entry wins
    if os.path.isdir(_p):
        sys.path.insert(0, _p)

from qgis_installer.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
