#!/usr/bin/env python3
"""Convenience launcher: works from any directory.

    python run.py [file]

Equivalent to `python -m printhub`, but doesn't require the current
directory to be the project root.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from printhub.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
