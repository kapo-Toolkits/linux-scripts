#!/usr/bin/env python3
"""DevOps Toolbox local web app, over real HTTP on a throw-away loopback port, with a fake ufw. Offline, nothing is changed on the
system.   Run: python3 tests/test_devops_web.py"""
import http.client
import json
import os
import re
import socket
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "devops-toolbox"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ.update(XDG_CONFIG_HOME=tempfile.mkdtemp(), XDG_STATE_HOME=tempfile.mkdtemp())

from test_devops_commands import Runner, box  # noqa: E402
from test_devops_ssh import toolbox as ssh_toolbox  # noqa: E402
from test_devops_toolbox import FakeUfw, toolbox  # noqa: E402

from devops_toolbox import i18n, web, webui  # noqa: E402

KEY = "k" * 43


class WebCase(unittest.TestCase):
    def setUp(self):
        self.tb, self.fake = toolbox(FakeUfw(rules=["ufw allow 22/tcp", "ufw allow 19999/tcp comment 'netdata'"]))
        self.app = web.WebApp(port=0, toolbox=self.tb, key=KEY).start()
        self.addCleanup(self.app.stop)
        self.port = self.app.port
        self.origin = f"http://127.0.0.1:{self.port}"

    def request(self, method, path, body=None, headers=None, host=None, raw=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": host if host is not None else f"127.0.0.1:{self.port}"}
        h.update(headers or {})
        data = raw if raw is not None else (json.dumps(body) if body is not None else None)
        payload = data.encode("utf-8") if isinstance(data, str) else data
        c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for k, v in h.items():
            c.putheader(k, v)
        if payload is not None:
            c.putheader("Content-Length", str(len(payload)))
        c.endheaders(payload)
        r = c.getresponse()
        text = r.read().decode("utf-8", "replace")
        c.close()
        return r.status, dict((k.lower(), v) for k, v in r.getheaders()), text

    def post(self, path, body, key=KEY, origin="same", ctype="application/json", **kw):
        h = {"Content-Type": ctype}
        if key is not None:
            h["X-Toolbox-Key"] = key
        if origin == "same":
            h["Origin"] = self.origin
        elif origin:
            h["Origin"] = origin
        return self.request("POST", path, body, h, **kw)

    def api(self, path, body):
        status, _h, text = self.post(path, body)
        self.assertEqual(status, 200, text)
        return json.loads(text)

    def raw_post(self, raw):
        return self.request("POST", "/api/preview", headers={"X-Toolbox-Key": KEY, "Origin": self.origin, "Content-Type": "application/json"},
                            raw=raw)


class Security(WebCase):
    def test_binds_only_to_loopback_and_refuses_anything_else(self):
        self.assertEqual(self.app.server.server_address[0], "127.0.0.1")
        for bad in ("0.0.0.0", "::", "192.168.1.10", "example.com", "", "127.0.0.2", "LOCALHOST ", None):
            with self.assertRaises(web.BadAddress, msg=repr(bad)):
                web.WebApp(host=bad, port=0, toolbox=self.tb)
        self.assertEqual(web.check_host("localhost"), "127.0.0.1")

    def test_the_page_needs_the_key(self):
        self.assertEqual(self.request("GET", "/")[0], 403)
        self.assertEqual(self.request("GET", "/?key=wrong")[0], 403)
        self.assertEqual(self.request("GET", "/?key=")[0], 403)
        self.assertEqual(self.request("GET", "/?key=" + KEY[:-1])[0], 403)
        self.assertEqual(self.request("GET", "/?key=" + KEY)[0], 200)

    def test_the_api_needs_the_key(self):
        self.assertEqual(self.request("GET", "/api/state")[0], 403)
        self.assertEqual(self.request("GET", "/api/state", headers={"X-Toolbox-Key": "x"})[0], 403)
        self.assertEqual(self.request("GET", "/api/state", headers={"X-Toolbox-Key": KEY})[0], 200)
        self.assertEqual(self.post("/api/preview", {"op": "ufw.status"}, key=None)[0], 403)
        self.assertEqual(self.post("/api/preview", {"op": "ufw.status"}, key="nope")[0], 403)
        self.assertEqual(self.post("/api/execute", {"op": "ufw.rule.add"}, key="")[0], 403)
        self.assertEqual(self.fake.calls, [])

    def test_host_header_must_be_this_loopback_address_and_port(self):
        for host in ("evil.example", "evil.example:%d" % self.port, "127.0.0.1", "127.0.0.1:1", "192.168.1.5:%d" % self.port, "",
                     "localhost.evil.com:%d" % self.port):
            self.assertEqual(self.request("GET", "/?key=" + KEY, host=host)[0], 403, host)
            self.assertEqual(self.request("GET", "/api/state", headers={"X-Toolbox-Key": KEY}, host=host)[0], 403, host)
            self.assertEqual(self.post("/api/preview", {"op": "ufw.status"}, host=host)[0], 403, host)
        for host in (f"127.0.0.1:{self.port}", f"localhost:{self.port}", f"[::1]:{self.port}"):
            self.assertEqual(self.request("GET", "/?key=" + KEY, host=host)[0], 200, host)

    def test_csrf_origin_content_type_size_and_json_are_enforced(self):
        good = {"op": "ufw.status"}
        self.assertEqual(self.post("/api/preview", good)[0], 200)
        for origin in (None, "", "null", "http://evil.example", f"http://127.0.0.1:{self.port + 1}", f"https://127.0.0.1:{self.port}",
                       f"http://127.0.0.1:{self.port}.evil.com"):
            self.assertEqual(self.post("/api/preview", good, origin=origin)[0], 403, origin)
        for ctype in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data", ""):
            self.assertEqual(self.post("/api/preview", good, ctype=ctype)[0], 415, ctype)
        self.assertEqual(self.post("/api/preview", {"op": "x" * (web.MAX_BODY + 10)})[0], 413)
        self.assertEqual(self.raw_post("{not json")[0], 400)
        self.assertEqual(self.raw_post("[1, 2]")[0], 400)
        self.assertEqual(self.raw_post("")[0], 400)
        self.assertEqual(self.raw_post(b"\xff\xfe\x00")[0], 400)
        self.assertEqual(self.fake.changes(), [])

    def test_only_the_known_routes_and_methods_exist(self):
        for path in ("/api/shell", "/api/exec", "/static/x", "/../etc/passwd", "/api/state/../x", "/index.html", "//", "/api/"):
            self.assertIn(self.request("GET", path, headers={"X-Toolbox-Key": KEY})[0], (403, 404), path)
            self.assertEqual(self.post(path, {})[0], 404, path)
        for method in ("PUT", "DELETE", "PATCH", "OPTIONS"):
            status, headers, _ = self.request(method, "/api/state", headers={"X-Toolbox-Key": KEY})
            self.assertEqual(status, 405, method)
            self.assertNotIn("access-control-allow-origin", headers)

    def test_response_headers_csp_nonce_and_no_cors(self):
        _s, h1, page1 = self.request("GET", "/?key=" + KEY)
        _s, h2, _page2 = self.request("GET", "/?key=" + KEY)
        n1 = re.search(r"script-src 'nonce-([\w-]+)'", h1["content-security-policy"]).group(1)
        n2 = re.search(r"script-src 'nonce-([\w-]+)'", h2["content-security-policy"]).group(1)
        self.assertNotEqual(n1, n2)                                                   # fresh per response
        self.assertIn('<script nonce="%s">' % n1, page1)
        self.assertIn('<style nonce="%s">' % n1, page1)
        csp = h1["content-security-policy"]
        for part in ("default-src 'none'", "connect-src 'self'", "base-uri 'none'", "form-action 'none'", "frame-ancestors 'none'"):
            self.assertIn(part, csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertNotIn("unsafe-eval", csp)
        self.assertEqual(h1["cache-control"], "no-store")
        self.assertEqual(h1["x-frame-options"], "DENY")
        self.assertEqual(h1["x-content-type-options"], "nosniff")
        self.assertEqual(h1["referrer-policy"], "no-referrer")
        self.assertNotIn("access-control-allow-origin", h1)
        _s, hj, _p = self.post("/api/preview", {"op": "ufw.status"})
        self.assertNotIn("access-control-allow-origin", hj)

    def test_the_page_has_no_external_resources_inline_handlers_or_the_key(self):
        _s, _h, page = self.request("GET", "/?key=" + KEY)
        self.assertNotRegex(page, r"""(src|href)\s*=\s*["']?https?:""")
        self.assertNotRegex(page, r"\son[a-z]+\s*=")                                  # no onclick= and friends
        self.assertNotRegex(page, r"\sstyle\s*=")                                     # no style attributes (CSP)
        self.assertNotIn("innerHTML", page)
        self.assertNotIn("eval(", page)
        self.assertNotIn(KEY, page)                                                   # the secret is never sent back in the page
        evil = webui.render("N", {"en": {"x": "</script><img src=x onerror=alert(1)>"}}, {"light": {"bg": "#fff"}})
        self.assertNotIn("</script><img", evil)                                       # a text can never close the script block

    def test_malicious_parameters_over_http_never_reach_a_command(self):
        for params in ({"port": "19999; reboot", "proto": "tcp", "action": "allow"}, {"port": "80", "proto": "tcp; id", "action": "allow"},
                       {"port": "80", "proto": "tcp", "action": "disable"}, {"port": "80", "proto": "tcp", "action": "allow", "extra": "x"},
                       {"port": ["80"], "proto": "tcp", "action": "allow"}, {"port": {"$": 1}, "proto": "tcp", "action": "allow"}):
            p = self.api("/api/preview", {"op": "ufw.rule.add", "params": params})
            self.assertFalse(p["ok"], params)
            self.assertEqual(p["token"], "")
            r = self.api("/api/execute", {"op": "ufw.rule.add", "params": params, "token": "x", "confirmed": True})
            self.assertFalse(r["result"]["ok"])
        for op in ("ufw.disable", "shell", "../x", "", None, 7, ["ufw.status"], {"a": 1}):
            self.assertFalse(self.api("/api/preview", {"op": op})["ok"], op)
        self.assertEqual(self.fake.changes(), [])


class Functionality(WebCase):
    def test_state_catalog_and_translations(self):
        _s, _h, text = self.request("GET", "/api/state?lang=ka", headers={"X-Toolbox-Key": KEY})
        data = json.loads(text)
        self.assertEqual(data["catalog"]["categories"][0]["name"], i18n.TEXT["ka"]["cat_net"])
        self.assertTrue(data["info"]["ufw"]["installed"])
        self.assertEqual(data["history"], [])
        _s, _h, page = self.request("GET", "/?key=" + KEY)
        self.assertIn("DevOps ხელსაწყოები", page)                                      # the Georgian table is in the page
        self.assertIn("DevOps Toolbox", page)

    def test_status_preview_confirm_execute_history_and_clear(self):
        r = self.api("/api/status", {"lang": "en"})
        self.assertTrue(r["result"]["ok"])
        self.assertEqual([x["spec"] for x in r["info"]["ufw"]["rules"]], ["22/tcp", "19999/tcp"])
        params = {"port": "8080", "proto": "tcp", "action": "allow", "comment": "web"}
        p = self.api("/api/preview", {"op": "ufw.rule.add", "params": params})
        self.assertTrue(p["ok"])
        self.assertEqual(p["commands"][0]["display"], "sudo ufw allow 8080/tcp comment web")
        self.assertEqual(self.fake.changes(), [])
        r = self.api("/api/execute", {"op": "ufw.rule.add", "params": params, "token": p["token"], "confirmed": False})
        self.assertFalse(r["result"]["ok"])                                           # not confirmed
        r = self.api("/api/execute", {"op": "ufw.rule.add", "params": params, "token": p["token"], "confirmed": "true"})
        self.assertFalse(r["result"]["ok"])                                           # a string is not a confirmation
        self.assertEqual(self.fake.changes(), [])
        p = self.api("/api/preview", {"op": "ufw.rule.add", "params": params})
        r = self.api("/api/execute", {"op": "ufw.rule.add", "params": params, "token": p["token"], "confirmed": True})
        self.assertTrue(r["result"]["ok"], r)
        self.assertEqual(self.fake.changes(), [["/usr/sbin/ufw", "allow", "8080/tcp", "comment", "web"]])
        self.assertTrue(any(h["op"] == "ufw.rule.add" for h in r["history"]))
        r = self.api("/api/execute", {"op": "ufw.rule.add", "params": params, "token": p["token"], "confirmed": True})
        self.assertFalse(r["result"]["ok"])                                           # the token was single-use
        self.assertEqual(len(self.fake.changes()), 1)
        self.assertEqual(self.api("/api/history/clear", {})["history"], [])
        self.assertEqual(self.tb.history_entries(), [])

    def test_language_parameter_selects_the_message_language(self):
        bad = {"port": "0", "proto": "tcp", "action": "allow"}
        p = self.api("/api/preview", {"op": "ufw.rule.add", "params": bad, "lang": "ka"})
        self.assertRegex(p["errors"][0]["message"], "[Ⴀ-ჿ]")
        p = self.api("/api/preview", {"op": "ufw.rule.add", "params": bad, "lang": "xx"})
        self.assertIn("between", p["errors"][0]["message"])

    def test_delete_over_http(self):
        self.api("/api/status", {})
        params = {"port": 19999, "proto": "tcp", "action": "allow"}
        p = self.api("/api/preview", {"op": "ufw.rule.delete", "params": params})
        self.assertEqual(p["risk"], "high")
        r = self.api("/api/execute", {"op": "ufw.rule.delete", "params": params, "token": p["token"], "confirmed": True})
        self.assertTrue(r["result"]["ok"])
        self.assertEqual(self.fake.changes(), [["/usr/sbin/ufw", "--force", "delete", "allow", "19999/tcp"]])


class AllCategories(unittest.TestCase):
    """The generic routes: run a reading operation with inputs, ask for the choices of a dynamic parameter."""

    def setUp(self):
        self.runner = Runner({"ping": "PING ok\n"})
        self.app = web.WebApp(port=0, toolbox=box(runner=self.runner), key=KEY).start()
        self.addCleanup(self.app.stop)
        self.web = WebCase("run")
        self.web.port, self.web.origin = self.app.port, "http://127.0.0.1:%d" % self.app.port

    def api(self, path, body):
        status, _h, text = self.web.post(path, body)
        self.assertEqual(status, 200, text)
        return json.loads(text)

    def test_the_catalogue_has_all_the_themes(self):
        _s, _h, text = self.web.request("GET", "/api/state?lang=en", headers={"X-Toolbox-Key": KEY})
        cats = json.loads(text)["catalog"]["categories"]
        self.assertEqual([c["id"] for c in cats], ["net", "firewall", "ssh", "svc", "web", "docker", "git", "users", "pkg", "disk", "mon", "sec", "db", "bk"])
        self.assertGreaterEqual(sum(len(c["operations"]) for c in cats), 140)
        net = next(c for c in cats if c["id"] == "net")
        ping = next(o for o in net["operations"] if o["id"] == "net.ping")
        self.assertEqual([p["name"] for p in ping["params"]], ["host", "count"])
        self.assertEqual(ping["risk"], "info")

    def test_run_executes_a_reading_operation_with_its_inputs(self):
        r = self.api("/api/run", {"op": "net.ping", "params": {"host": "example.com", "count": 2}})
        self.assertTrue(r["result"]["ok"], r)
        self.assertEqual(self.runner.calls[-1][0], ["/usr/bin/ping", "-c", "2", "--", "example.com"])
        self.assertIn("PING ok", r["result"]["output"])
        bad = self.api("/api/run", {"op": "net.ping", "params": {"host": "x; reboot", "count": 2}})
        self.assertFalse(bad["result"]["ok"])
        self.assertEqual(len(self.runner.calls), 1)

    def test_run_refuses_anything_that_changes_the_system(self):
        for op in ("svc.action", "pkg.upgrade", "disk.old.delete", "ufw.rule.add", "usr.add", "pkg.reboot.now", "nope", "", None, 5):
            r = self.api("/api/run", {"op": op, "params": {"service": "nginx", "svc_action": "stop", "days": 30}})
            self.assertFalse(r["result"]["ok"], op)
        self.assertEqual(self.runner.calls, [])

    def test_choices_only_for_dynamic_parameters(self):
        self.assertEqual(self.api("/api/choices", {"op": "web.site.enable", "param": "site"})["choices"], ["default", "mgawm"])
        self.assertEqual(self.api("/api/choices", {"op": "dk.compose.ps", "param": "project"})["choices"], ["docker-app"])
        for body in ({"op": "net.ping", "param": "host"}, {"op": "nope", "param": "x"}, {"op": 1, "param": 2}, {}, {"op": "web.site.enable", "param": "../x"}):
            self.assertEqual(self.api("/api/choices", body)["choices"], [], body)

    def test_a_modifying_operation_still_needs_the_token_over_http(self):
        params = {"service": "nginx", "svc_action": "restart"}
        r = self.api("/api/execute", {"op": "svc.action", "params": params, "token": "x", "confirmed": True})
        self.assertFalse(r["result"]["ok"])
        p = self.api("/api/preview", {"op": "svc.action", "params": params})
        r = self.api("/api/execute", {"op": "svc.action", "params": params, "token": p["token"], "confirmed": True})
        self.assertTrue(r["result"]["ok"], r)
        self.assertEqual(self.runner.calls[-1][0], ["/usr/bin/systemctl", "restart", "nginx"])
        self.assertNotIn("refresh", r["result"])                                 # no firewall password prompt after a service change


class Targets(unittest.TestCase):
    """Running the operations on another computer, over the web page's routes (a fake ssh answers)."""

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.tb, self.fake = ssh_toolbox(home=self.home)
        self.app = web.WebApp(port=0, toolbox=self.tb, key=KEY).start()
        self.addCleanup(self.app.stop)
        self.web = WebCase("run")
        self.web.port, self.web.origin = self.app.port, "http://127.0.0.1:%d" % self.app.port

    def api(self, path, body):
        status, _h, text = self.web.post(path, body)
        self.assertEqual(status, 200, text)
        return json.loads(text)

    def test_state_tells_the_target_and_the_keys_you_can_choose(self):
        _s, _h, text = self.web.request("GET", "/api/state?lang=en", headers={"X-Toolbox-Key": KEY})
        target = json.loads(text)["target"]
        self.assertEqual((target["kind"], target["label"]), ("local", "this computer"))
        self.assertEqual(target["keys"], ["id_ed25519", "work_key"])

    def test_choose_a_computer_then_run_an_operation_there(self):
        r = self.api("/api/target", {"kind": "remote", "host": "10.0.0.5", "port": 22, "user": "alice", "identity": "id_ed25519"})
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["target"]["label"], "alice@10.0.0.5:22")
        res = self.api("/api/run", {"op": "net.addr", "params": {}})["result"]
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["target"], "alice@10.0.0.5:22")
        self.assertEqual(self.fake.remote[-1]["prog"], "/usr/bin/ip")
        p = self.api("/api/preview", {"op": "svc.action", "params": {"service": "nginx", "svc_action": "restart"}})
        self.assertTrue(p["remote"])
        self.assertEqual(p["target"], "alice@10.0.0.5:22")
        r = self.api("/api/execute", {"op": "svc.action", "params": {"service": "nginx", "svc_action": "restart"}, "token": p["token"], "confirmed": True})
        self.assertTrue(r["result"]["ok"], r)
        self.assertTrue(self.fake.remote[-1]["root"])
        self.assertEqual(self.api("/api/target", {"kind": "local"})["target"]["kind"], "local")

    def test_bad_target_values_are_refused_with_a_message_for_each_field(self):
        for body, field in (({"kind": "remote", "host": "-oProxyCommand=id", "port": 22, "user": "alice"}, "host"),
                            ({"kind": "remote", "host": "h.example", "port": 70000, "user": "alice"}, "port"),
                            ({"kind": "remote", "host": "h.example", "port": 22, "user": "a;b"}, "user"),
                            ({"kind": "remote", "host": "h.example", "port": 22, "user": "alice", "identity": "../../etc/passwd"}, "identity")):
            r = self.api("/api/target", body)
            self.assertFalse(r["ok"], body)
            self.assertEqual(r["errors"][0]["param"], field)
        self.assertFalse(self.api("/api/target", {"kind": "sideways"})["ok"])
        self.assertFalse(self.api("/api/target", {})["ok"])
        self.assertEqual(self.api("/api/state", {}) if False else self.tb.target_info()["kind"], "local")
        self.assertEqual(self.fake.remote, [])

    def test_the_host_key_is_shown_first_and_trusted_only_with_the_token_and_a_confirmation(self):
        scan = self.api("/api/target/hostkey", {"host": "10.0.0.5", "port": 22})
        self.assertTrue(scan["ok"], scan)
        self.assertEqual(scan["fingerprints"], ["SHA256:AbCdEf1234567890 (ED25519)"])
        kh = os.path.join(self.home, ".ssh", "known_hosts")
        self.assertFalse(os.path.exists(kh))
        self.assertFalse(self.api("/api/target/trust", {"token": scan["token"], "confirmed": False})["ok"])
        self.assertFalse(self.api("/api/target/trust", {"token": scan["token"], "confirmed": "true"})["ok"])
        self.assertFalse(self.api("/api/target/trust", {"token": "nope", "confirmed": True})["ok"])
        self.assertFalse(os.path.exists(kh))
        self.assertTrue(self.api("/api/target/trust", {"token": scan["token"], "confirmed": True})["ok"])
        self.assertTrue(os.path.exists(kh))
        self.assertFalse(self.api("/api/target/hostkey", {"host": "x; id", "port": 22})["ok"])

    def test_the_connection_test(self):
        self.api("/api/target", {"kind": "remote", "host": "10.0.0.5", "port": 22, "user": "alice"})
        r = self.api("/api/target/test", {})
        self.assertTrue(r["ok"])
        self.assertTrue(r["sudo"])
        self.assertIn("Connected to alice@10.0.0.5:22", r["message"])

    def test_the_new_routes_need_the_key_and_the_origin_like_every_other(self):
        for path in ("/api/target", "/api/target/test", "/api/target/hostkey", "/api/target/trust"):
            self.assertEqual(self.web.post(path, {"kind": "local"}, key=None)[0], 403, path)
            self.assertEqual(self.web.post(path, {"kind": "local"}, key="wrong")[0], 403, path)
            self.assertEqual(self.web.post(path, {"kind": "local"}, origin="http://evil.example")[0], 403, path)
        self.assertEqual(self.fake.remote, [])

    def test_stopping_the_web_app_closes_the_connection(self):
        self.api("/api/target", {"kind": "remote", "host": "10.0.0.5", "port": 22, "user": "alice"})
        self.api("/api/run", {"op": "net.addr", "params": {}})
        folder = self.tb.target.control_dir
        self.assertTrue(os.path.isdir(folder))
        self.app.stop()
        self.assertFalse(os.path.exists(folder))


class Lifecycle(unittest.TestCase):
    def test_starts_and_stops_cleanly_and_frees_the_port(self):
        tb, _ = toolbox()
        app = web.WebApp(port=0, toolbox=tb, key=KEY).start()
        port = app.port
        self.assertTrue(app.url.startswith(f"http://127.0.0.1:{port}/?key="))
        self.assertTrue(app.thread.is_alive())
        app.stop()
        self.assertFalse(app.thread.is_alive())
        with socket.socket() as s:
            s.settimeout(1)
            self.assertNotEqual(s.connect_ex(("127.0.0.1", port)), 0)                 # nothing listens any more
        again = web.WebApp(port=port, toolbox=tb, key=KEY).start()                   # and the port can be used again at once
        again.stop()

    def test_random_keys_differ_and_are_long(self):
        tb, _ = toolbox()
        a, b = web.WebApp(port=0, toolbox=tb), web.WebApp(port=0, toolbox=tb)
        try:
            self.assertNotEqual(a.key, b.key)
            self.assertGreaterEqual(len(a.key), 32)
        finally:
            a.server.server_close()
            b.server.server_close()

    def test_command_line_refuses_other_addresses(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("dtw", os.path.join(ROOT, "devops-toolbox", "devops-toolbox-web.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.main(["--host", "0.0.0.0", "--no-browser"]), 2)
        self.assertEqual(mod.main(["--host", "192.168.0.5", "--port", "0"]), 2)


if __name__ == "__main__":
    unittest.main()
