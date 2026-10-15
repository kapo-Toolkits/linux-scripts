#!/bin/sh
# PrintHub launcher.
#   installed:  <prefix>/bin/printhub  ->  <prefix>/lib/printhub/{printhub/, venv/ (PySide6, if the system has none)}
#   from a checkout of linux-scripts:  printhub/printhub-launcher.sh  runs the package next to it
here="$(dirname "$(readlink -f "$0")")"
if [ -d "$here/../lib/printhub/printhub" ]; then app="$here/../lib/printhub"; else app="$here"; fi
py=python3
[ -x "$app/venv/bin/python" ] && py="$app/venv/bin/python"
if ! "$py" -c 'import PySide6' 2>/dev/null; then
  echo "PrintHub needs PySide6.  Install it with:  ./install.sh printhub   (or: pip install PySide6)" >&2
  exit 1
fi
PYTHONPATH="$app${PYTHONPATH:+:$PYTHONPATH}" exec "$py" -m printhub "$@"
