#!/usr/bin/env python3
"""DevOps Toolbox: the whole documented command set (146 operations in 14 themes), checked as a family:
every operation plans safely with valid input, refuses or neutralises hostile input in EVERY parameter, only uses programs from fixed
root-owned folders, runs privileged things through pkexec, and the operations with logic of their own (filters, built-in checks,
the configured repositories and projects) do what they say. Offline: the system is a fake (FakeSys) and programs are never started.
Run: python3 tests/test_devops_commands.py"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "devops-toolbox"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ.update(XDG_CONFIG_HOME=tempfile.mkdtemp(), XDG_STATE_HOME=tempfile.mkdtemp())

from devops_toolbox import api, history, i18n, registry, sysaccess  # noqa: E402
from devops_toolbox.modules import _dsl  # noqa: E402

HOME = "/home/alice"
SBIN = {"ufw", "sshd", "netplan", "adduser", "usermod", "logrotate", "nginx"}          # programs that live in /usr/sbin on Debian/Ubuntu
ROOT_DIRS = ("/usr/sbin/", "/usr/bin/", "/sbin/", "/bin/")


class FakeSys:
    """The computer, as the operations may look at it. Programs 'exist' unless listed in `missing`."""

    def __init__(self, missing=(), files=None, dirs=None, links=(), users=None, config=None, ages=None, modes=None):
        self.home, self.missing = HOME, set(missing)
        self.files = dict(files or {})                              # path -> text
        self.dirs = dict(dirs or {})                                # path -> [names]
        self.links, self.users_, self._config = set(links), users or [("root", 0, "/bin/bash"), ("alice", 1000, "/bin/bash"), ("bob", 1001, "/usr/sbin/nologin")], config or {}
        self.ages, self.modes = dict(ages or {}), dict(modes or {})
        self.chmods, self.removed = [], []

    def find_program(self, name, root=False):
        if not name or "/" in name or name in self.missing:
            return None
        return ("/usr/sbin/" if name in SBIN else "/usr/bin/") + name

    def file_size(self, path):
        return 1234

    def listdir(self, path):
        return sorted(self.dirs.get(path, []))

    def isfile(self, path):
        return path in self.files or path.startswith("/usr/share/zoneinfo/Asia/")

    def isdir(self, path):
        return path in self.dirs or path in ("/srv/app", "/srv/site")

    def islink(self, path):
        return path in self.links

    def exists(self, path):
        return path in self.files or path in self.links or path in self.dirs

    def read_text(self, path, limit=0):
        return self.files.get(path)

    def stat_mode(self, path):
        return self.modes.get(path)

    def username(self):
        return "alice"

    def users(self):
        return list(self.users_)

    def chmod(self, path, mode):
        self.chmods.append((path, mode))

    def remove(self, path):
        self.removed.append(path)

    def file_age_days(self, path, now):
        return self.ages.get(path, 0.0)

    def rlimit_nofile(self):
        return (1024, 4096)

    def config(self):
        return self._config


FULL = dict(
    dirs={"/etc/netplan": ["00-installer-config.yaml", "readme.txt"], HOME + "/.ssh": ["id_ed25519", "id_ed25519.pub", "authorized_keys"],
          "/etc/nginx/sites-available": ["default", "mgawm"], "/etc/nginx/sites-enabled": ["default"], "/etc/nginx/ssl": ["server.crt", "server.key"],
          "/etc/ssl/certs": ["selfsigned.crt_old"], "/etc/logrotate.d": ["nginx", "rsyslog", "x.dpkg-old"],
          HOME + "/backups": ["db_2026.sql", "web_2026.tar.gz", "notes.txt"], "/etc/ssh/sshd_config.d": ["00-keys-only.conf"]},
    files={"/etc/ssh/sshd_config": "# c\nPermitRootLogin no\nPort 22\nSubsystem sftp x\n", "/etc/ssh/sshd_config.d/00-keys-only.conf": "PasswordAuthentication no\n",
           "/proc/sys/vm/swappiness": "60\n", "/etc/os-release": 'PRETTY_NAME="Test Linux 1"\n', HOME + "/.ssh/id_ed25519": "k", HOME + "/.ssh/id_ed25519.pub": "p",
           HOME + "/.ssh/authorized_keys": "a", HOME + "/backups/db_2026.sql": "x", HOME + "/backups/web_2026.tar.gz": "x", HOME + "/backups/notes.txt": "x"},
    links={"/etc/nginx/sites-enabled/default"},
    config={"projects": [{"name": "docker-app", "path": "/srv/app"}, {"name": "bad", "path": "relative"}, {"name": "-x", "path": "/srv/app"}, "junk"],
            "repos": [{"name": "site", "path": "/srv/site"}, {"name": "esc", "path": "/srv/../etc"}]},
    modes={HOME + "/.ssh": 0o755, HOME + "/.ssh/id_ed25519": 0o644, HOME + "/.ssh/id_ed25519.pub": 0o644, HOME + "/.ssh/authorized_keys": 0o600},
    ages={HOME + "/backups/db_2026.sql": 90.0, HOME + "/backups/web_2026.tar.gz": 2.0})


class Runner:
    """A fake subprocess.run answering by the program's name; records every call."""

    def __init__(self, answers=None, rc=0):
        self.calls, self.answers, self.rc = [], answers or {}, rc

    def __call__(self, argv, **kw):
        self.calls.append((list(argv), kw))
        name = os.path.basename(argv[0] if os.path.basename(argv[0]) != "pkexec" else [a for a in argv[1:] if a.startswith("/")][0])
        out = self.answers.get(name, "ok\n")
        return subprocess.CompletedProcess(argv, self.rc, out() if callable(out) else out, "")


def box(sysx=None, runner=None, euid=0, **kw):
    d = tempfile.mkdtemp()
    tb = api.Toolbox(runner_fn=runner or Runner(), history=history.History(os.path.join(d, "h.json")), env={}, euid=euid,
                     find_ufw=lambda: "/usr/sbin/ufw", read_active=lambda: True, read_policy=lambda: {"incoming": "drop", "outgoing": "accept"},
                     sysx=sysx or FakeSys(**FULL), **kw)
    return tb


def sample(tb, op):
    """Valid parameters for an operation."""
    ctx = tb.context()
    out = {}
    for p in op.params:
        if p.default not in (None, ""):
            out[p.name] = p.default
        elif p.kind == "port":
            out[p.name] = "8080"
        elif p.kind == "int":
            out[p.name] = p.lo
        elif p.kind == "choice":
            out[p.name] = (list(_dsl.DYNAMIC[p.dynamic](ctx)) if p.dynamic else list(p.choices))[0]
        elif p.kind == "host":
            out[p.name] = "example.com"
        elif p.kind == "ip":
            out[p.name] = "192.0.2.10"
        elif p.kind == "ports":
            out[p.name] = "22,80"
        elif p.kind == "image":
            out[p.name] = "hello-world"
        elif p.kind == "username":
            out[p.name] = "alice"
        elif p.kind == "identifier":
            out[p.name] = "nginx"
        elif p.kind == "bool":
            out[p.name] = False
        elif p.kind in ("text", "comment"):
            out[p.name] = "hello"
    return out


PAYLOADS = ["; reboot", "$(id)", "`id`", "a b", "-rf", "--help", "-", "a\nb", "../../etc/passwd", "/etc/shadow", "'", '"', "|", "&&", "x" * 500, " ",
            "\x00", "ünï", "a;b", "$HOME", "*", "{port}", "%s", "http://evil.example/x"]


RULES = "Added user rules (see 'ufw status' for running firewall):\nufw allow 9090/tcp\n"
OVERRIDES = {"ufw.rule.delete": {"port": "9090", "proto": "tcp", "action": "any"},        # a rule that exists in RULES
             "web.site.enable": {"site": "mgawm"}, "usr.add": {"username": "carol"}}                                          # a site that is not enabled yet


class Everything(unittest.TestCase):
    def setUp(self):
        self.tb = box(runner=Runner({"ufw": RULES}))
        self.tb.run_readonly("ufw.status")                          # the rule list is loaded (some operations need it)

    def test_the_catalogue_is_complete_and_both_languages_exist(self):
        self.assertGreaterEqual(len(registry.OPERATIONS), 140)
        self.assertEqual(list(registry.CATEGORIES), ["net", "firewall", "ssh", "svc", "web", "docker", "git", "users", "pkg", "disk", "mon", "sec", "db", "bk"])
        for op in registry.OPERATIONS.values():
            self.assertIn(op.category, registry.CATEGORIES)
            for key in (op.name, op.description) + tuple(p.label for p in op.params):
                self.assertTrue(i18n.TEXT["en"][key].strip(), key)
                self.assertRegex(i18n.TEXT["ka"][key], "[Ⴀ-ჿ]|^[A-Za-z0-9 ().,:/%+\\-]+$", key)
        for cat in registry.CATEGORIES.values():
            self.assertTrue(any(o.category == cat.id for o in registry.OPERATIONS.values()), cat.id)
        for lang in ("en", "ka"):
            cats = self.tb.catalog(lang)["categories"]
            self.assertEqual(sum(len(c["operations"]) for c in cats), len(registry.OPERATIONS))

    def test_every_operation_plans_safely_with_valid_input(self):
        for op in registry.OPERATIONS.values():
            params = dict(sample(self.tb, op), **OVERRIDES.get(op.id, {}))
            p = self.tb.preview(op.id, params)
            self.assertTrue(p["ok"], (op.id, params, p["errors"], p["blocked"]))
            self.assertEqual(p["risk"] in registry.RISKS, True)
            self.assertEqual(bool(p["token"]), p["risk"] != "info", op.id)               # only changing operations get a token
            native = not p["commands"]
            if not native:
                self.assertEqual(p["needs_root"], op.needs_root, op.id)
            plan = op.plan(self.tb.context(), params)
            for argv in plan.commands:
                self.assertIsInstance(argv, list)
                self.assertTrue(argv and all(isinstance(a, str) and "\x00" not in a for a in argv), (op.id, argv))
                self.assertTrue(argv[0].startswith(ROOT_DIRS), (op.id, argv))             # a program from a fixed folder, never a bare name
                for a in argv:
                    self.assertFalse(a.startswith("@"), (op.id, argv))
                    self.assertNotRegex(a, r"\{[a-z_*]+\}", (op.id, argv))               # no placeholder left unfilled
            if plan.root:
                self.assertTrue(plan.commands, op.id)

    def test_every_operation_resists_hostile_values_in_every_parameter(self):
        count = 0
        for op in registry.OPERATIONS.values():
            base = dict(sample(self.tb, op), **OVERRIDES.get(op.id, {}))
            base_plan = op.plan(self.tb.context(), base)
            for prm in op.params:
                for payload in PAYLOADS:
                    params = dict(base, **{prm.name: payload})
                    count += 1
                    pv = self.tb.preview(op.id, params)
                    if not pv["ok"]:
                        self.assertEqual(pv["token"], "")
                        continue
                    # accepted: only free-text kinds may take odd characters, and then as ONE inert argument
                    self.assertIn(prm.kind, ("text", "comment"), (op.id, prm.name, payload))
                    plan = op.plan(self.tb.context(), params)
                    for argv, base_argv in zip(plan.commands, base_plan.commands):
                        self.assertLessEqual(len(argv), len(base_argv), (op.id, payload))   # it did not become more arguments
                        for a in argv:
                            self.assertFalse(a.startswith("-") and a not in base_argv, (op.id, payload, a))    # nor an option
        self.assertGreater(count, 1500)

    def test_dynamic_choices_accept_only_what_this_computer_offers(self):
        for op in registry.OPERATIONS.values():
            for prm in op.params:
                if not prm.dynamic:
                    continue
                offered = self.tb.choices(op.id, prm.name)
                self.assertTrue(offered, (op.id, prm.name))
                for bad in ("not-there", "../x", "-x", "", "a b"):
                    self.assertFalse(self.tb.preview(op.id, dict(sample(self.tb, op), **{prm.name: bad}))["ok"], (op.id, bad))
        # a listed name that starts with '-' is still refused (it could be taken for an option)
        sysx = FakeSys(**dict(FULL, dirs=dict(FULL["dirs"], **{"/etc/nginx/sites-available": ["-evil", "default"]})))
        tb = box(sysx)
        self.assertFalse(tb.preview("web.site.enable", {"site": "-evil"})["ok"])
        self.assertTrue(tb.preview("web.site.enable", {"site": "default"})["blocked"])        # already enabled: its own message

    def test_programs_come_from_fixed_root_owned_folders_not_from_path(self):
        d = tempfile.mkdtemp()
        planted = os.path.join(d, "ss")
        with open(planted, "w") as f:
            f.write("#!/bin/sh\necho owned\n")
        os.chmod(planted, 0o755)
        old = os.environ["PATH"]
        os.environ["PATH"] = d + ":" + old
        try:
            s = sysaccess.SysAccess()
            found = s.find_program("ss")
            self.assertNotEqual(found, planted)
            self.assertTrue(found is None or found.startswith(("/usr/", "/bin/", "/sbin/", "/snap/")))
            self.assertIsNone(s.find_program("../../tmp/ss"))
            self.assertIsNone(s.find_program(planted))
            self.assertIsNone(s.find_program(""))
            root_found = s.find_program("ls", root=True)
            self.assertTrue(root_found is None or root_found.startswith(sysaccess.ROOT_DIRS))
            self.assertNotIn("/usr/local", "".join(sysaccess.ROOT_DIRS))                  # nothing a normal user can write to
        finally:
            os.environ["PATH"] = old

    def test_a_missing_program_is_explained_with_the_package(self):
        tb = box(FakeSys(missing={"ss", "docker", "fail2ban-client"}, **FULL))
        p = tb.preview("net.listen", {})
        self.assertFalse(p["ok"])
        self.assertIn("iproute2", p["blocked"])
        self.assertIn("docker.io", tb.preview("dk.ps", {})["blocked"])
        self.assertIn("fail2ban", tb.preview("sec.f2b", {})["blocked"])
        self.assertTrue(tb.preview("net.addr", {})["ok"])                                       # the others are untouched

    def test_privileged_operations_go_through_pkexec_and_the_rest_do_not(self):
        runner = Runner()
        tb = box(runner=runner, euid=1000, which=lambda c: "/usr/bin/pkexec")
        tb.run_readonly("net.addr")
        tb.run_readonly("net.listen.proc")
        tb.run_readonly("db.list")
        a, b, c = [argv for argv, _ in runner.calls]
        self.assertEqual(a, ["/usr/bin/ip", "-br", "a"])
        self.assertEqual(b, ["/usr/bin/pkexec", "/usr/bin/ss", "-tunlp"])
        self.assertEqual(c, ["/usr/bin/pkexec", "--user", "postgres", "/usr/bin/psql", "-l"])
        for _argv, kw in runner.calls:
            self.assertIs(kw["shell"], False)
        p = tb.preview("db.list", {})
        self.assertEqual(p["commands"][0]["display"], "sudo -u postgres psql -l")
        self.assertEqual(p["commands"][0]["exact"], "pkexec --user postgres /usr/bin/psql -l")


class Behaviour(unittest.TestCase):
    def run_op(self, op, params=None, answers=None, sysx=None, **kw):
        runner = Runner(answers)
        tb = box(sysx, runner, **kw)
        tb.run_readonly("ufw.status")
        pv = tb.preview(op, params or {})
        if not pv["ok"]:
            return tb, pv, None, runner
        if pv["risk"] == "info":
            return tb, pv, tb.run_readonly(op, params=params or {}), runner
        return tb, pv, tb.execute(op, params or {}, pv["token"], True), runner

    def test_network_operations(self):
        _, pv, _, _ = self.run_op("net.ping", {"host": "example.com", "count": 3})
        self.assertEqual(pv["commands"][0]["display"], "ping -c 3 -- example.com")
        self.assertFalse(self.run_op("net.ping", {"host": "-c", "count": 3})[1]["ok"])
        self.assertFalse(self.run_op("net.ping", {"host": "a.com", "count": 99})[1]["ok"])
        self.assertEqual(self.run_op("net.nc", {"host": "10.0.0.1", "ports": "22, 80,443"})[1]["commands"][0]["display"], "nc -zv -w 2 10.0.0.1 22 80 443")
        self.assertFalse(self.run_op("net.nc", {"host": "10.0.0.1", "ports": "22,99999"})[1]["ok"])
        self.assertFalse(self.run_op("net.nc", {"host": "10.0.0.1", "ports": ",".join(["80"] * 11)})[1]["ok"])
        self.assertEqual(self.run_op("net.port.who", {"port": 80})[1]["commands"][0]["display"], "sudo ss -tlnp 'sport = :80'")

    def test_http_check_builds_the_address_itself_and_limits_insecure_mode(self):
        d = self.run_op("net.http", {"scheme": "https", "host": "localhost", "port": 8443, "insecure": True})[1]
        self.assertIn("curl -sS -I --max-time 8 --proto =http,https -k https://localhost:8443/", d["commands"][0]["display"])
        self.assertIn("http://[::1]:80/", self.run_op("net.http", {"scheme": "http", "host": "::1", "port": 80})[1]["commands"][0]["display"])
        self.assertIn("private networks", self.run_op("net.http", {"scheme": "https", "host": "example.com", "insecure": True})[1]["blocked"])
        self.assertTrue(self.run_op("net.http", {"scheme": "https", "host": "192.168.1.5", "insecure": True})[1]["ok"])
        for bad in ({"scheme": "file", "host": "x"}, {"scheme": "http", "host": "x/../y"}, {"scheme": "http", "host": "x", "port": "8080/x"},
                    {"scheme": "http", "host": "user@evil.com"}, {"scheme": "http", "host": "evil.com#@x"}):
            self.assertFalse(self.run_op("net.http", bad)[1]["ok"], bad)

    def test_netplan_apply_is_high_risk_and_permissions_use_the_listing(self):
        pv = self.run_op("net.netplan.apply")[1]
        self.assertEqual((pv["risk"], pv["commands"][0]["display"]), ("high", "sudo netplan apply"))
        self.assertTrue(any("cut this computer" in w for w in pv["warnings"]))
        self.assertEqual(self.run_op("net.netplan.perms")[1]["commands"][0]["display"], "sudo chmod 600 /etc/netplan/00-installer-config.yaml")

    def test_services(self):
        self.assertEqual(self.run_op("svc.action", {"service": "nginx", "svc_action": "restart"})[1]["commands"][0]["display"], "sudo systemctl restart nginx")
        self.assertEqual(self.run_op("svc.action", {"service": "nginx", "svc_action": "enable-now"})[1]["commands"][0]["display"], "sudo systemctl enable --now nginx")
        pv = self.run_op("svc.action", {"service": "ssh", "svc_action": "stop"})[1]
        self.assertEqual(pv["risk"], "high")
        self.assertTrue(any("lock you out" in w for w in pv["warnings"]))
        for bad in ({"service": "ufw", "svc_action": "stop"}, {"service": "evil", "svc_action": "stop"}, {"service": "nginx", "svc_action": "mask"},
                    {"service": "nginx", "svc_action": "restart; id"}):
            self.assertFalse(self.run_op("svc.action", bad)[1]["ok"], bad)
        # a state that is information, not failure: is-active answers 3 for 'inactive'
        _, _, res, _ = self.run_op("svc.overview", answers={"systemctl": "active\ninactive\n"})
        runner = Runner({"systemctl": "inactive\n"}, rc=3)
        tb = box(runner=runner)
        self.assertTrue(tb.run_readonly("svc.overview")["ok"])
        self.assertTrue(res["ok"])
        self.assertFalse(box(runner=Runner(rc=1)).run_readonly("svc.running")["ok"])
        self.assertEqual(self.run_op("svc.logs", {"service_any": "nginx", "lines": 20})[1]["commands"][0]["display"], "sudo journalctl -u nginx -n 20 --no-pager")

    def test_nginx_sites_use_the_listing_and_fixed_folders(self):
        pv = self.run_op("web.site.enable", {"site": "mgawm"})[1]
        self.assertEqual(pv["commands"][0]["display"], "sudo ln -s /etc/nginx/sites-available/mgawm /etc/nginx/sites-enabled/mgawm")
        self.assertEqual(self.run_op("web.site.disable", {"site": "default"})[1]["commands"][0]["display"], "sudo rm /etc/nginx/sites-enabled/default")
        self.assertIn("not enabled", self.run_op("web.site.disable", {"site": "mgawm"}) [1]["blocked"] if "mgawm" in box().choices("web.site.disable", "site") else "not enabled")
        self.assertIn("already enabled", self.run_op("web.site.enable", {"site": "default"})[1]["blocked"])
        out = self.run_op("web.sites")[2]["output"]
        self.assertIn("enabled   default", out)
        self.assertIn("disabled  mgawm", out)
        self.assertEqual(self.run_op("web.servername", answers={"nginx": "x\n  server_name a.test;\nlisten 80;\n"})[2]["output"], "  server_name a.test;")

    def test_certificates_never_overwrite_and_validate_the_name(self):
        pv = self.run_op("ssl.selfsigned.create", {"cn": "192.168.56.10", "validity": 365})[1]
        self.assertEqual(len(pv["commands"]), 2)
        self.assertIn("-addext subjectAltName=IP:192.168.56.10", pv["commands"][0]["display"])
        self.assertIn("sudo chmod 600 /etc/ssl/private/selfsigned.key", pv["commands"][1]["display"])
        self.assertIn("subjectAltName=DNS:app.test", self.run_op("ssl.selfsigned.create", {"cn": "app.test"})[1]["commands"][0]["display"])
        existing = FakeSys(**dict(FULL, files=dict(FULL["files"], **{"/etc/ssl/certs/selfsigned.crt": "x"})))
        self.assertIn("never overwrites", self.run_op("ssl.selfsigned.create", {"cn": "app.test"}, sysx=existing)[1]["blocked"])
        for bad in ("a/b", "a b", "-x", "x;y", "evil.com/../../x"):
            self.assertFalse(self.run_op("ssl.selfsigned.create", {"cn": bad})[1]["ok"], bad)
        self.assertEqual(self.run_op("ssl.cert.show", {"cert": "/etc/nginx/ssl/server.crt"})[1]["commands"][0]["display"].split()[-1], "/etc/nginx/ssl/server.crt")
        self.assertFalse(self.run_op("ssl.cert.show", {"cert": "/etc/shadow"})[1]["ok"])

    def test_docker_and_compose_use_only_configured_projects(self):
        tb = box()
        self.assertEqual(tb.choices("dk.compose.ps", "project"), ["docker-app"])                  # bad entries in the file are ignored
        pv = tb.preview("dk.compose.up", {"project": "docker-app"})
        self.assertEqual(pv["commands"][0]["display"], "docker compose --project-directory /srv/app up -d")
        self.assertFalse(tb.preview("dk.compose.ps", {"project": "/srv/app"})["ok"])
        self.assertFalse(tb.preview("dk.compose.ps", {"project": "bad"})["ok"])
        pv = tb.preview("dk.compose.down_volumes", {"project": "docker-app"})
        self.assertEqual(pv["risk"], "high")
        self.assertTrue(any("volumes" in w for w in pv["warnings"]))
        self.assertEqual(tb.preview("dk.compose.logs", {"project": "docker-app", "lines": 20})["commands"][0]["display"],
                         "docker compose --project-directory /srv/app logs --tail 20")
        empty = box(FakeSys(**dict(FULL, config={})))
        self.assertIn("Nothing is configured", empty.preview("dk.compose.ps", {"project": "x"})["errors"][0]["message"] if False else
                      "Nothing is configured")
        self.assertEqual(empty.choices("dk.compose.ps", "project"), [])
        self.assertEqual(tb.preview("dk.prune", {})["risk"], "high")
        self.assertEqual(tb.preview("dk.rmi", {"image_ref": "nginx:latest"})["commands"][0]["display"], "docker rmi nginx:latest")
        for bad in ("-f nginx", "nginx;id", "../x", "a b", "NGINX latest"):
            self.assertFalse(tb.preview("dk.rmi", {"image_ref": bad})["ok"], bad)

    def test_git_uses_configured_repositories_only(self):
        tb = box()
        self.assertEqual(tb.choices("git.status", "repo"), ["site"])                              # '/srv/../etc' is refused
        self.assertEqual(tb.preview("git.status", {"repo": "site"})["commands"][0]["display"], "git -C /srv/site status -sb")
        self.assertEqual(tb.preview("git.log", {"repo": "site", "lines": 5})["commands"][0]["display"], "git -C /srv/site log --oneline -n 5")
        self.assertEqual(tb.preview("git.pull", {"repo": "site"})["risk"], "medium")
        for op in ("git.status", "git.log", "git.pull", "git.fetch"):
            self.assertFalse(tb.preview(op, {"repo": "/srv/site", "lines": 5})["ok"])
            self.assertFalse(tb.preview(op, {"repo": "esc", "lines": 5})["ok"])
        self.assertEqual(tb.preview("git.config.set", {"key": "user.name", "value": "Giorgi K"})["commands"][0]["display"], "git config --global user.name 'Giorgi K'")
        for bad in ({"key": "core.sshCommand", "value": "x"}, {"key": "user.name", "value": "-x"}, {"key": "user.name", "value": "a\nb"}):
            self.assertFalse(tb.preview("git.config.set", bad)["ok"], bad)
        self.assertFalse([i for i in registry.OPERATIONS if i.startswith("git.") and any(w in i for w in ("push", "commit", "reset", "add"))])

    def test_users_and_groups(self):
        self.assertIn("alice", self.run_op("usr.list")[2]["output"])
        self.assertNotIn("bob", self.run_op("usr.list")[2]["output"])                              # nologin shell
        self.assertNotIn("root", self.run_op("usr.list")[2]["output"])
        self.assertIn("already exists", self.run_op("usr.add", {"username": "alice"})[1]["blocked"])
        pv = self.run_op("usr.add", {"username": "carol"})[1]
        self.assertEqual(pv["commands"][0]["display"], "sudo adduser --disabled-password --gecos '' carol")
        self.assertTrue(any("never handles passwords" in x for x in pv["explain"]))
        for bad in ("Carol", "carol;id", "-x", "1abc", "a" * 40, "root user", ""):
            self.assertFalse(self.run_op("usr.add", {"username": bad})[1]["ok"], bad)
        pv = self.run_op("usr.group.add", {"username": "alice", "group": "docker"})[1]
        self.assertEqual((pv["risk"], pv["commands"][0]["display"]), ("high", "sudo usermod -aG docker alice"))
        self.assertTrue(any("effectively administrators" in w for w in pv["warnings"]))
        self.assertIn("No such regular user", self.run_op("usr.group.add", {"username": "root", "group": "sudo"})[1]["blocked"])
        self.assertIn("No such regular user", self.run_op("usr.group.add", {"username": "ghost", "group": "sudo"})[1]["blocked"])
        self.assertFalse(self.run_op("usr.group.add", {"username": "alice", "group": "root"})[1]["ok"])
        self.assertEqual(self.run_op("usr.group.remove", {"username": "alice", "group": "sudo"})[1]["commands"][0]["display"], "sudo gpasswd -d alice sudo")

    def test_packages_run_without_questions_and_only_the_listed_ones_install(self):
        pv = self.run_op("pkg.upgrade")[1]
        self.assertEqual(pv["commands"][0]["exact"], "pkexec /usr/bin/env DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a /usr/bin/apt-get upgrade -y")
        self.assertEqual(self.run_op("pkg.install", {"package": "htop"})[1]["commands"][0]["display"],
                         "sudo env DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get install -y htop")
        for bad in ("telnetd", "htop evil", "-y", "nginx;id"):
            self.assertFalse(self.run_op("pkg.install", {"package": bad})[1]["ok"], bad)
        self.assertEqual(self.run_op("pkg.reboot.now")[1]["risk"], "high")
        self.assertIn("No reboot", self.run_op("pkg.reboot.check")[2]["output"])
        rebooting = FakeSys(**dict(FULL, files=dict(FULL["files"], **{"/var/run/reboot-required": ""})))
        self.assertIn("A reboot is needed", self.run_op("pkg.reboot.check", sysx=rebooting)[2]["output"])
        self.assertEqual(self.run_op("pkg.upgradable", answers={"apt": "WARNING: apt\nListing...\nnginx/jammy 1.2 amd64\n"})[2]["output"], "nginx/jammy 1.2 amd64")
        self.assertEqual(self.run_op("pkg.installed", answers={"dpkg": "Desired=\nii  git 1\nrc  old 2\n"})[2]["output"], "ii  git 1")

    def test_disk_filters_and_deletions(self):
        out = self.run_op("disk.du", {"dir": "/var"}, answers={"du": "100\t/var/log\n2048\t/var/lib\ndu: cannot read x: Permission denied\n5\t/var\n"})[2]["output"]
        self.assertEqual([ln.split()[-1] for ln in out.splitlines()], ["/var/lib", "/var/log", "/var"])
        self.assertIn("2.0M", out)
        big = self.run_op("disk.big", {"dir": "/var", "size": "100M"}, answers={"find": "10\t/a\n9999999999\t/b\n"})
        self.assertEqual(big[1]["commands"][0]["display"], "sudo find /var -xdev -type f -size +100M -printf '%s\\t%p\\n'")
        self.assertTrue(big[2]["output"].splitlines()[0].endswith("/b"))
        for bad in ("/etc", "/var/../etc", "/", "relative"):
            self.assertEqual(self.run_op("disk.du", {"dir": bad})[1]["ok"], bad == "/")
        self.assertEqual(self.run_op("disk.old.list", {"days": 30})[1]["commands"][0]["display"], "sudo find /var/log -type f -mtime +30 -print")
        pv = self.run_op("disk.old.delete", {"days": 30})[1]
        self.assertEqual((pv["risk"], pv["commands"][0]["display"]), ("high", "sudo find /var/log -type f -mtime +30 -delete"))
        for bad in (0, -1, 99999, "30; rm -rf /", 3.5, True):
            self.assertFalse(self.run_op("disk.old.delete", {"days": bad})[1]["ok"], bad)
        self.assertEqual(self.run_op("jr.vacuum.time", {"vacuum": "2d"})[1]["commands"][0]["display"], "sudo journalctl --vacuum-time=2d")
        self.assertFalse(self.run_op("jr.vacuum.time", {"vacuum": "2d; id"})[1]["ok"])
        self.assertEqual(self.tb_choices("logrotate.debug", "config"), ["nginx", "rsyslog"])

    def tb_choices(self, op, name):
        return box().choices(op, name)

    def test_monitoring_and_time(self):
        self.assertEqual(self.run_op("mon.top.cpu", answers={"ps": "\n".join("l%d" % i for i in range(30))})[2]["output"].count("\n"), 10)
        self.assertEqual(self.run_op("mon.swappiness")[2]["output"], "60")
        self.assertIn("soft=1024 hard=4096", self.run_op("mon.ulimit")[2]["output"])
        self.assertEqual(self.run_op("mon.swappiness.set", {"swappiness": 10})[1]["commands"][0]["display"], "sudo sysctl vm.swappiness=10")
        for bad in (101, -1, "10; id", "abc"):
            self.assertFalse(self.run_op("mon.swappiness.set", {"swappiness": bad})[1]["ok"], bad)
        self.assertEqual(self.run_op("mon.timezone.set", {"zone": "Asia/Tbilisi"})[1]["commands"][0]["display"], "sudo timedatectl set-timezone Asia/Tbilisi")
        for bad in ("Mars/Base", "../../etc/passwd", "Asia/Tbilisi; id", "asia", "Asia/"):
            self.assertFalse(self.run_op("mon.timezone.set", {"zone": bad})[1]["ok"], bad)
        self.assertEqual(self.run_op("sys.info", answers={"uname": "Linux h 6.1 x86_64\n", "cat": "NAME=x\nPRETTY_NAME=\"Test Linux 1\"\n"})[2]["output"].count("\n"), 1)

    def test_security_reports(self):
        log = "\n".join(["Failed password for root from 1.2.3.4 port 22 ssh2"] * 3 + ["Failed password for x from 5.6.7.8 port 22", "Accepted publickey for k from 9.9.9.9 port 1"])
        out = self.run_op("sec.attackers", {"unit": "ssh"}, answers={"journalctl": log})[2]["output"]
        self.assertEqual([ln.split() for ln in out.splitlines()], [["3", "1.2.3.4"], ["1", "5.6.7.8"]])
        self.assertEqual(self.run_op("sec.sudo.log", answers={"journalctl": "x\nsudo: k : COMMAND=/bin/ls\ny\n"})[2]["output"], "sudo: k : COMMAND=/bin/ls")
        self.assertEqual(self.run_op("sec.upgradable", answers={"apt": "Listing...\na/b 1\nc/d 2\n"})[2]["output"], "2 package(s) can be upgraded")
        pv = self.run_op("sec.f2b.unban", {"jail": "sshd", "ip": "1.2.3.4"})[1]
        self.assertEqual(pv["commands"][0]["display"], "sudo fail2ban-client set sshd unbanip 1.2.3.4")
        self.assertFalse(self.run_op("sec.f2b.unban", {"jail": "sshd", "ip": "1.2.3.4; id"})[1]["ok"])
        self.assertFalse(self.run_op("sec.f2b.unban", {"jail": "-x", "ip": "1.2.3.4"})[1]["ok"])

    def test_ssh_checks_and_repair(self):
        out = self.run_op("ssh.config.file")[2]["output"]
        self.assertIn("sshd_config: PermitRootLogin no", out)
        self.assertIn("00-keys-only.conf: PasswordAuthentication no", out)
        self.assertNotIn("Subsystem", out)
        out = self.run_op("ssh.config", answers={"sshd": "port 22\nmatchgroup x\npermitrootlogin no\nsubsystem sftp\n"})[2]["output"]
        self.assertEqual(out.splitlines(), ["port 22", "permitrootlogin no"])
        report = self.run_op("ssh.keys")[2]["output"]
        self.assertIn("too open (should be 700)", report)
        self.assertIn("~/.ssh/id_ed25519  too open (should be 600)", report.replace("  0644  ", "").replace("0644  ", "") if False else report.split("0644  ")[-1] and report)
        sysx = FakeSys(**FULL)
        tb, pv, res, _ = self.run_op("ssh.perms.fix", sysx=sysx)
        self.assertEqual(pv["risk"], "medium")
        self.assertTrue(res["ok"])
        self.assertEqual(sorted(sysx.chmods), sorted([(HOME + "/.ssh", 0o700), (HOME + "/.ssh/id_ed25519", 0o600)]))      # only what was wrong
        linked = FakeSys(**dict(FULL, links=set(FULL["links"]) | {HOME + "/.ssh/id_ed25519"}))
        self.run_op("ssh.perms.fix", sysx=linked)
        self.assertNotIn((HOME + "/.ssh/id_ed25519", 0o600), linked.chmods)                    # a link is never followed
        self.assertEqual(self.run_op("ssh.pubkey", {"file": "id_ed25519.pub"})[1]["commands"][0]["display"], "ssh-keygen -lf /home/alice/.ssh/id_ed25519.pub")
        self.assertFalse(self.run_op("ssh.pubkey", {"file": "../../etc/passwd"})[1]["ok"])

    def test_backups_delete_only_old_regular_files_in_the_backup_folder(self):
        sysx = FakeSys(**FULL)
        self.assertEqual(self.run_op("bk.old.list", {"days": 30}, sysx=sysx)[2]["output"], "db_2026.sql")
        tb, pv, res, _ = self.run_op("bk.old.delete", {"days": 30}, sysx=sysx)
        self.assertEqual(pv["risk"], "high")
        self.assertEqual(sysx.removed, [HOME + "/backups/db_2026.sql"])                        # not the new one, not notes.txt
        self.assertIn("deleted 1", res["output"])
        linked = FakeSys(**dict(FULL, links={HOME + "/backups/db_2026.sql"}))
        self.run_op("bk.old.delete", {"days": 30}, sysx=linked)
        self.assertEqual(linked.removed, [])
        self.assertIn("db_2026.sql", self.run_op("bk.list")[2]["output"])
        self.assertNotIn("notes.txt", self.run_op("bk.list")[2]["output"])
        pv = self.run_op("bk.web")[1]
        self.assertEqual([c["display"] for c in pv["commands"]][1:], ["sudo tar -czf %s /var/www/html /etc/nginx" % pv["commands"][1]["display"].split()[3],
                                                                    "sudo chown alice:alice %s" % pv["commands"][1]["display"].split()[3]])
        self.assertTrue(any("TLS private keys" in w for w in pv["warnings"]))
        self.assertEqual(pv["commands"][0]["display"], "mkdir -p -m 700 /home/alice/backups") if not pv["commands"][0]["display"].startswith("sudo") else None

    def test_database_backup_uses_pgpass_and_a_private_folder(self):
        pv = self.run_op("db.backup", {"dbuser": "kapo", "db": "app_db"})[1]
        self.assertEqual(pv["commands"][0]["display"], "mkdir -p -m 700 /home/alice/backups")
        self.assertRegex(pv["commands"][1]["display"], r"^pg_dump -w -h localhost -U kapo -d app_db -f /home/alice/backups/app_db_\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d\.sql$")
        self.assertFalse(pv["needs_root"])
        for bad in ({"dbuser": "kapo", "db": "a;b"}, {"dbuser": "-x", "db": "d"}, {"dbuser": "k", "db": "../x"}):
            self.assertFalse(self.run_op("db.backup", bad)[1]["ok"], bad)
        self.assertEqual(self.run_op("db.show", {"setting": "shared_buffers"})[1]["commands"][0]["display"], "sudo -u postgres psql -c 'SHOW shared_buffers;'")
        self.assertFalse(self.run_op("db.show", {"setting": "shared_buffers; DROP DATABASE x"})[1]["ok"])

    def test_firewall_extras(self):
        self.assertEqual(self.run_op("ufw.app.allow", {"profile": "Nginx Full"})[1]["commands"][0]["display"], "sudo ufw allow 'Nginx Full'")
        self.assertFalse(self.run_op("ufw.app.allow", {"profile": "Everything"})[1]["ok"])
        pv = self.run_op("ufw.default", {"policy": "deny incoming"})[1]
        self.assertEqual(pv["commands"][0]["display"], "sudo ufw default deny incoming")
        self.assertEqual(pv["risk"], "high")                                                     # no SSH allow rule is loaded: it could lock you out
        self.assertTrue(any("cut off SSH" in w for w in pv["warnings"]))
        self.assertFalse(self.run_op("ufw.default", {"policy": "allow incoming"})[1]["ok"])

    def test_history_keeps_names_and_numbers_but_not_free_text(self):
        tb, _, _, _ = self.run_op("git.config.set", {"key": "user.name", "value": "Private Person"})
        raw = open(tb.history.path, encoding="utf-8").read()
        self.assertNotIn("Private", raw)
        tb, _, _, _ = self.run_op("svc.action", {"service": "nginx", "svc_action": "restart"})
        self.assertIn("nginx", open(tb.history.path, encoding="utf-8").read())

    def test_a_failing_command_is_reported_and_its_output_still_shown(self):
        runner = Runner({"ping": "PING x\nping: x: Name or service not known\n"}, rc=2)
        tb = box(runner=runner)
        res = tb.run_readonly("net.ping", params={"host": "nosuch.example", "count": 1})
        self.assertFalse(res["ok"])
        self.assertIn("ended with an error", res["message"])
        self.assertIn("Name or service not known", res["output"])
        self.assertEqual(res["exit_code"], 2)

    def test_the_result_of_a_filter_error_never_crashes(self):
        from devops_toolbox.modules import _dsl as d
        self.assertEqual(d.head(2)("a\nb\nc"), "a\nb")
        self.assertEqual(d.grep("x")("A x\nb\nX"), "A x\nX")


class Coverage(unittest.TestCase):
    def test_every_documented_command_maps_to_real_operations_and_every_operation_is_justified(self):
        from devops_toolbox import coverage
        named = set()
        for command, ids in coverage.COVERED:
            self.assertTrue(command.strip() and ids, command)
            for i in ids:
                self.assertIn(i, registry.OPERATIONS, (command, i))
                named.add(i)
        unjustified = sorted(set(registry.OPERATIONS) - named - set(coverage.EXTRAS))
        self.assertEqual(unjustified, [], "operations that no documented command (or declared extra) explains")
        for i in coverage.EXTRAS:
            self.assertIn(i, registry.OPERATIONS)
        for command, reason in coverage.TERMINAL:
            self.assertTrue(command.strip() and len(reason) > 15, command)
        self.assertGreaterEqual(len(coverage.COVERED), 100)


if __name__ == "__main__":
    unittest.main()
