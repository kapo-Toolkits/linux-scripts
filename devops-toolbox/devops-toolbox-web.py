#!/usr/bin/env python3
"""DevOps Toolbox - local web app. Same operations as the desktop window, in your browser.

    devops-toolbox-web                 start on 127.0.0.1:8765 and open the browser
    devops-toolbox-web --port 0        pick a free port
    devops-toolbox-web --no-browser    only print the address (it contains this run's access key)

It listens on the loopback address only (there is no option to expose it to the network). Stop it with Ctrl+C."""
import argparse
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
for _p in reversed((_here, os.path.join(_here, "..", "common"), os.path.join(_here, "..", "lib", "linux-scripts"),
                    "/usr/local/lib/linux-scripts", "/usr/lib/linux-scripts")):      # first entry wins
    if os.path.isdir(_p):
        sys.path.insert(0, _p)

from devops_toolbox import i18n, settings, web  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="DevOps Toolbox local web app (loopback only).")
    ap.add_argument("--host", default="127.0.0.1", help="127.0.0.1 (default), localhost or ::1 - nothing else is accepted")
    ap.add_argument("--port", type=int, default=web.DEFAULT_PORT, help="port (default %(default)s; 0 = any free port)")
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser, only print the address")
    args = ap.parse_args(argv)
    lang = settings.load_lang()
    try:
        app = web.WebApp(args.host, args.port)
    except web.BadAddress:
        print("error: this interface is never offered to the network; use 127.0.0.1, localhost or ::1", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"error: cannot listen on {args.host}:{args.port}: {e}", file=sys.stderr)
        return 1
    app.start()
    print(i18n.t(lang, "web_started", url=app.url), flush=True)
    if not args.no_browser:
        import webbrowser
        try:
            webbrowser.open(app.url)
        except Exception:  # noqa: BLE001 - no browser: the address is printed above
            pass
    try:
        app.thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
