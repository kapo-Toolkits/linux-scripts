"""The local web app: a small standard-library HTTP server in front of the same `Toolbox` API the desktop window uses.

Security model (it is an administrative interface, so it is strict by default):
  * it listens on the loopback interface only - any other address is refused, there is no 'listen on the network' switch;
  * every request must carry the per-run secret (printed in the start-up URL, sent as the X-Toolbox-Key header by the page), so
    other users or programs on the same computer cannot use it; the secret is random and compared in constant time;
  * the Host header must be the loopback address and port the server is on (stops DNS-rebinding pages);
  * a POST must also carry an Origin of this very server, be application/json and be small (CSRF);
  * no CORS headers at all, a nonce-based Content-Security-Policy, no framing, no referrer, nothing cached;
  * only the routes below exist; a request can only name an allowlisted operation - never a command, path or URL.
Administrator rights are still asked by pkexec on the desktop (a system dialog the browser cannot answer)."""
import hmac
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import i18n, themes, webui
from .api import Toolbox

LOOPBACK = {"127.0.0.1": "127.0.0.1", "localhost": "127.0.0.1", "::1": "::1"}
MAX_BODY = 16 * 1024
DEFAULT_PORT = 8765


class BadAddress(ValueError):
    pass


def check_host(host):
    """The loopback address to bind. Anything else is an error: this interface is never offered to the network."""
    if host not in LOOPBACK:
        raise BadAddress(host)
    return LOOPBACK[host]


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, handler, toolbox, key, ipv6=False):
        import socket
        self.address_family = socket.AF_INET6 if ipv6 else socket.AF_INET
        super().__init__(addr, handler)
        self.toolbox, self.key, self.lock = toolbox, key, threading.Lock()

    @property
    def netloc_names(self):
        port = self.server_address[1]
        return {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}


class Handler(BaseHTTPRequestHandler):
    server_version = "DevOpsToolbox"
    sys_version = ""
    protocol_version = "HTTP/1.0"

    # ---- plumbing
    def log_message(self, fmt, *args):                  # method, path and status only: never headers, bodies or the key
        pass

    def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False))

    def _error(self, status, key):
        self._json(status, {"ok": False, "key": key, "message": i18n.t("en", key)})

    def _host_ok(self):
        return (self.headers.get("Host") or "") in self.server.netloc_names

    def _key_ok(self, given):
        return isinstance(given, str) and hmac.compare_digest(given.encode("utf-8"), self.server.key.encode("utf-8"))

    # ---- routes
    def do_GET(self):
        if not self._host_ok():
            return self._send(403, "forbidden", "text/plain; charset=utf-8")
        url = urlsplit(self.path)
        if url.path == "/":
            if not self._key_ok((parse_qs(url.query).get("key") or [""])[0]):
                return self._send(403, "Open the address printed by devops-toolbox-web (it contains the access key).", "text/plain; charset=utf-8")
            nonce = secrets.token_urlsafe(16)
            page = webui.render(nonce, i18n.TEXT, themes.PALETTES)
            csp = ("default-src 'none'; script-src 'nonce-%s'; style-src 'nonce-%s'; connect-src 'self'; base-uri 'none'; "
                   "form-action 'none'; frame-ancestors 'none'" % (nonce, nonce))
            return self._send(200, page, "text/html; charset=utf-8", {"Content-Security-Policy": csp})
        if url.path == "/api/state":
            if not self._key_ok(self.headers.get("X-Toolbox-Key", "")):
                return self._error(403, "err_bad_token")
            lang = (parse_qs(url.query).get("lang") or ["en"])[0]
            with self.server.lock:
                tb = self.server.toolbox
                return self._json(200, {"catalog": tb.catalog(lang), "info": tb.info(lang), "history": tb.history_entries(), "target": tb.target_info()})
        self._error(404, "err_unknown_operation")

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, "forbidden", "text/plain; charset=utf-8")
        if not self._key_ok(self.headers.get("X-Toolbox-Key", "")):
            return self._error(403, "err_bad_token")
        origin = self.headers.get("Origin") or ""
        if origin not in {"http://" + n for n in self.server.netloc_names}:                # CSRF: only this very server's page
            return self._error(403, "err_bad_token")
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            return self._error(415, "err_unknown_operation")
        try:
            length = int(self.headers.get("Content-Length") or "")
        except ValueError:
            return self._error(411, "err_unknown_operation")
        if not 0 <= length <= MAX_BODY:
            return self._error(413, "err_unknown_operation")
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self._error(400, "err_unknown_operation")
        if not isinstance(body, dict):
            return self._error(400, "err_unknown_operation")
        lang = body.get("lang") if body.get("lang") in i18n.LANGS else "en"
        path = urlsplit(self.path).path
        with self.server.lock:                                   # one operation at a time; the Toolbox keeps session state
            tb = self.server.toolbox
            if path == "/api/status":
                res = tb.run_readonly("ufw.status", lang)
                return self._json(200, {"result": res, "info": tb.info(lang), "history": tb.history_entries()})
            if path == "/api/target":                            # run on this computer, or on another one over SSH (keys only)
                res = tb.set_target(body.get("kind"), body.get("host", ""), body.get("port", 22), body.get("user", ""), body.get("identity", ""), lang)
                return self._json(200, dict(res, info=tb.info(lang), history=tb.history_entries()))
            if path == "/api/target/test":
                return self._json(200, tb.target_test(lang))
            if path == "/api/target/hostkey":                   # show the fingerprints; nothing is trusted by this call
                return self._json(200, tb.hostkey_scan(body.get("host", ""), body.get("port", 22), lang))
            if path == "/api/target/trust":                     # needs that scan's token AND confirmed: true
                return self._json(200, tb.hostkey_trust(body.get("token"), body.get("confirmed"), lang))
            if path == "/api/run":                               # an operation that only reads, with its inputs (no confirmation needed for these)
                params = body.get("params") if isinstance(body.get("params"), dict) else {}
                res = tb.run_readonly(body.get("op") if isinstance(body.get("op"), str) else "", lang, params=params)
                return self._json(200, {"result": res, "info": tb.info(lang), "history": tb.history_entries()})
            if path == "/api/choices":                           # the values a dynamic choice may take on this computer
                op, name = body.get("op"), body.get("param")
                return self._json(200, {"choices": tb.choices(op, name) if isinstance(op, str) and isinstance(name, str) else []})
            if path == "/api/preview":
                params = body.get("params") if isinstance(body.get("params"), dict) else {}
                return self._json(200, tb.preview(body.get("op"), params, lang))
            if path == "/api/execute":
                params = body.get("params") if isinstance(body.get("params"), dict) else {}
                res = tb.execute(body.get("op"), params, body.get("token"), body.get("confirmed"), lang)
                return self._json(200, {"result": res, "info": tb.info(lang), "history": tb.history_entries()})
            if path == "/api/history/clear":
                tb.clear_history()
                return self._json(200, {"ok": True, "history": []})
        self._error(404, "err_unknown_operation")

    def do_PUT(self):
        self._error(405, "err_unknown_operation")

    do_DELETE = do_PATCH = do_PUT

    def do_OPTIONS(self):                                        # no CORS: a preflight gets nothing
        self._error(405, "err_unknown_operation")


class WebApp:
    """start() / stop() around the server, usable from the command line and from tests."""

    def __init__(self, host="127.0.0.1", port=DEFAULT_PORT, toolbox=None, key=None):
        self.host = check_host(host)
        self.key = key or secrets.token_urlsafe(32)
        self.server = _Server((self.host, port), Handler, toolbox or Toolbox(), self.key, ipv6=self.host == "::1")
        self.thread = None

    @property
    def port(self):
        return self.server.server_address[1]

    @property
    def url(self):
        host = "[::1]" if self.host == "::1" else self.host
        return f"http://{host}:{self.port}/?key={self.key}"

    def start(self):
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
        self.thread.start()
        return self

    def stop(self):
        try:
            self.server.toolbox.close()                          # ends the shared SSH connection, if one is open
        except Exception:  # noqa: BLE001 - stopping must always work
            pass
        self.server.shutdown()
        self.server.server_close()
        if self.thread:
            self.thread.join(timeout=5)
