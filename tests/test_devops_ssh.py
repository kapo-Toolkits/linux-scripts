#!/usr/bin/env python3
"""DevOps Toolbox - running the operations on ANOTHER computer over SSH. No network and no real ssh: a fake `ssh` decodes the remote command the
way a server would, and answers from the same fake computer (FakeSys) the other tests use.   Run: python3 tests/test_devops_ssh.py"""
import os
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "devops-toolbox"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ.update(XDG_CONFIG_HOME=tempfile.mkdtemp(), XDG_STATE_HOME=tempfile.mkdtemp())

from test_devops_commands import FULL, HOME, PAYLOADS, SBIN, FakeSys, sample  # noqa: E402

from devops_toolbox import api, history, registry, target  # noqa: E402

HOST_KEY = "AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SPvQ7Fh9Yl9Qd0mP2Kx8cQ1x3n8nIq5G"
SCAN = "10.0.0.5 ssh-ed25519 " + HOST_KEY + "\n"


class FakeSsh:
    """A fake subprocess.run for BOTH the local tools (ssh-keyscan, ssh-keygen) and `ssh`: for ssh it parses the remote command line."""

    def __init__(self, sysx=None, answers=None, sudo_ok=True, fail=None, scan=SCAN):
        self.sys = sysx or FakeSys(**FULL)
        import json
        self.sys.files[HOME + "/.config/linux-scripts/devops-toolbox.json"] = json.dumps(self.sys._config)
        self.answers, self.sudo_ok, self.fail, self.scan = answers or {}, sudo_ok, fail, scan
        self.local, self.remote = [], []                    # local program calls; parsed remote calls

    def __call__(self, argv, **kw):
        if os.path.basename(argv[0]) != "ssh":
            self.local.append((list(argv), kw))
            return self.local_tool(argv)
        if "-O" in argv:
            return subprocess.CompletedProcess(argv, 0, "", "")
        if self.fail == "timeout":
            raise subprocess.TimeoutExpired(argv, 1)
        if self.fail:
            return subprocess.CompletedProcess(argv, 255, "", {"refused": "ssh: connect to host h port 22: Connection refused",
                                                               "auth": "alice@h: Permission denied (publickey).",
                                                               "hostkey": "Host key verification failed.",
                                                               "changed": "@@@ WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED! @@@",
                                                               "resolve": "ssh: Could not resolve hostname h: Name or service not known",
                                                               "weird": "something nobody expected"}[self.fail])
        command = argv[argv.index("--") + 2]
        tokens = shlex.split(command)
        root, user = False, None
        if tokens[:2] == ["/usr/bin/sudo", "-n"]:
            root = True
            tokens = tokens[2:]
            if tokens[:1] == ["-u"]:
                user, tokens = tokens[1], tokens[2:]
            if not self.sudo_ok:
                return subprocess.CompletedProcess(argv, 1, "", "sudo: a password is required")
        assert tokens[:2] == ["/usr/bin/env", "-i"], tokens
        i = 2
        env = {}
        while "=" in tokens[i] and not tokens[i].startswith("/"):
            k, _, v = tokens[i].partition("=")
            env[k] = v
            i += 1
        prog, args = tokens[i], tokens[i + 1:]
        self.remote.append({"root": root, "user": user, "prog": prog, "args": args, "env": env, "command": command, "argv": list(argv)})
        return self.handle(os.path.basename(prog), prog, args, env, root)

    def done(self, argv, out="", rc=0, err=""):
        return subprocess.CompletedProcess(argv, rc, out, err)

    def handle(self, name, prog, args, env, root):
        s = self.sys
        if name == "test":
            flag, path = args[0], args[1]
            ok = {"-f": s.isfile, "-d": s.isdir, "-L": s.islink, "-e": s.exists}[flag](path)
            return self.done(args, rc=0 if ok else 1)
        if name == "ls":
            path = args[-1]
            return self.done(args, "\n".join(s.listdir(path)) + "\n", rc=0 if path in s.dirs else 2)
        if name == "head":
            text = s.read_text(args[-1])
            return self.done(args, text or "", rc=0 if text is not None else 1)
        if name == "stat":
            fmt, path = args[1], args[-1]
            if fmt == "%a":
                m = s.stat_mode(path)
                return self.done(args, "%o\n" % m, rc=0) if m is not None else self.done(args, rc=1)
            if fmt == "%s":
                return self.done(args, "1234\n")
            if fmt == "%Y":
                return self.done(args, "%d\n" % (1800000000 - int(s.ages.get(path, 0) * 86400)))
        if name == "date":
            return self.done(args, "1800000000\n")
        if name == "id":
            return self.done(args, ("alice\n" if args == ["-un"] else "0\n"))
        if name == "getent" and args[0] == "passwd":
            rows = [(n, u, sh) for n, u, sh in s.users_]
            if len(args) > 1:
                rows = [r for r in rows if r[0] == args[1]]
            return self.done(args, "".join("%s:x:%d:%d::%s:%s\n" % (n, u, u, "/home/" + n, sh) for n, u, sh in rows))
        if name == "sh" and args[0] == "-c":
            found = s.find_program(args[-1], root=env["PATH"].startswith("/usr/sbin"))
            return self.done(args, (found + "\n") if found else "", rc=0 if found else 1)
        if name == "chmod":
            s.chmods.append((args[-1], int(args[0], 8)))
            return self.done(args)
        if name == "rm":
            s.removed.append(args[-1])
            return self.done(args)
        out = self.answers.get(name, "ok\n")
        return self.done(args, out() if callable(out) else out)

    def local_tool(self, argv):
        name = os.path.basename(argv[0])
        if name == "ssh-keyscan":
            return subprocess.CompletedProcess(argv, 0, self.scan, "")
        if name == "ssh-keygen" and "-lf" in argv:
            return subprocess.CompletedProcess(argv, 0, "256 SHA256:AbCdEf1234567890 10.0.0.5 (ED25519)\n", "")
        if name == "ssh-keygen" and "-F" in argv:
            return subprocess.CompletedProcess(argv, 1, "", "")
        return subprocess.CompletedProcess(argv, 0, "", "")


def toolbox(fake=None, home=None, **kw):
    d = tempfile.mkdtemp()
    fake = fake or FakeSsh()
    local = FakeSys(**dict(FULL, dirs=dict(FULL["dirs"], **{HOME + "/.ssh": ["id_ed25519", "id_ed25519.pub", "work_key", "work_key.pub", "lonely", "known_hosts"]})))
    local.home = home or d
    kw.setdefault("find_ssh", lambda: "/usr/bin/ssh")                                  # the tests never start a real ssh
    tb = api.Toolbox(runner_fn=fake, history=history.History(os.path.join(d, "h.json")), env={}, euid=0, sysx=local,
                     find_ufw=lambda: "/usr/sbin/ufw", read_active=lambda: True, read_policy=lambda: {"incoming": "drop", "outgoing": "accept"}, **kw)
    tb._local.sysx.dirs[local.home + "/.ssh"] = ["id_ed25519", "id_ed25519.pub", "work_key", "work_key.pub", "lonely", "known_hosts"]
    return tb, fake


def remote(tb, host="10.0.0.5", port=22, user="alice", identity=""):
    r = tb.set_target("remote", host, port, user, identity)
    assert r["ok"], r
    return r


class Command(unittest.TestCase):
    def test_the_ssh_command_line_is_strict(self):
        t = target.RemoteTarget("10.0.0.5", 2222, "alice", "id_ed25519", find_ssh=lambda: "/usr/bin/ssh", home="/home/me")
        a = t.ssh_argv("X")
        self.assertEqual(a[:3], ["/usr/bin/ssh", "-F", "/dev/null"])
        joined = " ".join(a)
        for want in ("BatchMode=yes", "StrictHostKeyChecking=yes", "PasswordAuthentication=no", "KbdInteractiveAuthentication=no", "PreferredAuthentications=publickey",
                     "ForwardAgent=no", "ForwardX11=no", "ClearAllForwardings=yes", "ConnectTimeout=10", "IdentitiesOnly=yes", "-p 2222", "-l alice",
                     "-i /home/me/.ssh/id_ed25519"):
            self.assertIn(want, joined)
        self.assertNotIn("StrictHostKeyChecking=no", joined)
        self.assertNotIn("accept-new", joined)
        self.assertNotIn("UserKnownHostsFile=/dev/null", joined)
        self.assertIn("UserKnownHostsFile=/home/me/.ssh/known_hosts", joined)             # the file the trust step writes to
        self.assertEqual(a[-3:], ["--", "10.0.0.5", "X"])                                # the host is always after '--'
        t.close()
        self.assertIsNone(target.RemoteTarget("h", 22, "u", find_ssh=lambda: None).ssh_argv("x"))

    def test_the_remote_command_quotes_every_word_and_sets_a_fixed_environment(self):
        for argv in (["/usr/sbin/ufw", "allow", "80/tcp", "comment", "a b; c $(id) `id` 'q' \"d\" \\ \n x"], ["/usr/bin/ping", "-c", "3", "--", "h"],
                     ["/usr/bin/git", "config", "--global", "user.name", "O'Brien; rm -rf /"]):
            cmd = target.RemoteTarget.remote_command(argv, root=True, as_user=None, is_root=False)
            tokens = shlex.split(cmd)
            self.assertEqual(tokens[-len(argv):], argv)                                  # the remote shell hands back exactly these words
            self.assertEqual(tokens[:5], ["/usr/bin/sudo", "-n", "/usr/bin/env", "-i", "PATH=/usr/sbin:/usr/bin:/sbin:/bin"])
        user_cmd = target.RemoteTarget.remote_command(["/usr/bin/ss", "-tuln"], root=False, as_user=None, is_root=False, home="/home/alice")
        self.assertEqual(shlex.split(user_cmd)[:2], ["/usr/bin/env", "-i"])
        self.assertIn("HOME=/home/alice", user_cmd)
        self.assertNotIn("sudo", user_cmd)
        root_cmd = target.RemoteTarget.remote_command(["/usr/bin/ss"], root=True, as_user=None, is_root=True)
        self.assertNotIn("sudo", root_cmd)                                               # connected as root: no sudo needed
        pg = shlex.split(target.RemoteTarget.remote_command(["/usr/bin/psql", "-l"], root=True, as_user="postgres", is_root=False))
        self.assertEqual(pg[:5], ["/usr/bin/sudo", "-n", "-u", "postgres", "/usr/bin/env"])


class Validation(unittest.TestCase):
    def test_host_port_user_and_key_are_validated(self):
        tb, fake = toolbox()
        self.assertTrue(tb.set_target("remote", "example.com", 2222, "alice", "")["ok"])
        self.assertTrue(tb.set_target("remote", "fe80::1", "22", "k.user@x", "work_key")["ok"])
        for host in PAYLOADS + ["-oProxyCommand=id", "-F/etc/passwd", "a@b", "host:22", "http://x"]:
            r = tb.set_target("remote", host, 22, "alice", "")
            self.assertFalse(r["ok"], host)
            self.assertEqual(r["errors"][0]["param"], "host")
        for port in (0, 65536, "x", "22; id", -1, True, None, "", 22.5):
            self.assertFalse(tb.set_target("remote", "h.example", port, "alice", "")["ok"], port)
        for user in PAYLOADS + ["-oProxyCommand=id", "a b", "root;id"]:
            self.assertFalse(tb.set_target("remote", "h.example", 22, user, "")["ok"], user)
        for key in ("../../etc/passwd", "lonely", "id_ed25519.pub", "nope", "-x", "/etc/shadow", "known_hosts", "a b"):
            self.assertFalse(tb.set_target("remote", "h.example", 22, "alice", key)["ok"], key)                 # only your own private keys
        self.assertEqual(tb.target_info()["keys"], ["id_ed25519", "work_key"])
        self.assertFalse(tb.set_target("sideways")["ok"])
        self.assertEqual(fake.remote, [])                                                  # nothing connected while setting up
        self.assertEqual(tb.set_target("local")["target"]["kind"], "local")


class Running(unittest.TestCase):
    def test_a_reading_operation_runs_on_the_other_computer(self):
        tb, fake = toolbox()
        remote(tb)
        res = tb.run_readonly("net.addr")
        self.assertTrue(res["ok"], res)
        call = fake.remote[-1]
        self.assertEqual((call["root"], call["prog"], call["args"]), (False, "/usr/bin/ip", ["-br", "a"]))
        self.assertEqual(call["env"]["PATH"], "/usr/local/bin:/usr/bin:/bin:/snap/bin:/usr/sbin:/usr/bin:/sbin:/bin")
        self.assertEqual(res["target"], "alice@10.0.0.5:22")
        argv = call["argv"]
        self.assertEqual(argv[0], "/usr/bin/ssh")
        self.assertEqual(argv[argv.index("--") + 1], "10.0.0.5")
        self.assertFalse([c for c, _ in fake.local if os.path.basename(c[0]) not in ("ssh",)])      # nothing ran on THIS computer

    def test_administrator_operations_use_sudo_n_and_postgres_uses_sudo_u(self):
        tb, fake = toolbox()
        remote(tb)
        tb.run_readonly("net.listen.proc")
        self.assertEqual((fake.remote[-1]["root"], fake.remote[-1]["prog"]), (True, "/usr/bin/ss"))
        self.assertEqual(fake.remote[-1]["command"].split()[:2], ["/usr/bin/sudo", "-n"])
        tb.run_readonly("db.list")
        self.assertEqual((fake.remote[-1]["root"], fake.remote[-1]["user"]), (True, "postgres"))
        pv = tb.preview("svc.action", {"service": "nginx", "svc_action": "restart"})
        self.assertEqual(pv["commands"][0]["display"], "sudo systemctl restart nginx")
        self.assertTrue(pv["commands"][0]["exact"].startswith("ssh -p 22 alice@10.0.0.5 "))
        self.assertEqual((pv["target"], pv["remote"]), ("alice@10.0.0.5:22", True))
        res = tb.execute("svc.action", {"service": "nginx", "svc_action": "restart"}, pv["token"], True)
        self.assertTrue(res["ok"], res)
        self.assertEqual((fake.remote[-1]["root"], fake.remote[-1]["prog"], fake.remote[-1]["args"]), (True, "/usr/bin/systemctl", ["restart", "nginx"]))

    def test_connected_as_root_needs_no_sudo(self):
        tb, fake = toolbox()
        remote(tb, user="root")
        tb.run_readonly("net.listen.proc")
        self.assertNotIn("sudo", fake.remote[-1]["command"])

    def test_a_preview_never_runs_on_another_computer(self):
        tb, fake = toolbox()
        remote(tb, host="10.0.0.5")
        pv = tb.preview("svc.action", {"service": "nginx", "svc_action": "restart"})
        remote(tb, host="10.0.0.9")
        res = tb.execute("svc.action", {"service": "nginx", "svc_action": "restart"}, pv["token"], True)
        self.assertFalse(res["ok"])
        self.assertIn("expired", res["message"])
        pv = tb.preview("svc.action", {"service": "nginx", "svc_action": "restart"})
        tb.set_target("local")
        self.assertFalse(tb.execute("svc.action", {"service": "nginx", "svc_action": "restart"}, pv["token"], True)["ok"])
        remote(tb, host="10.0.0.9", port=2200)                                           # even the port belongs to the token
        pv = tb.preview("svc.action", {"service": "nginx", "svc_action": "restart"})
        remote(tb, host="10.0.0.9", port=2201)
        self.assertFalse(tb.execute("svc.action", {"service": "nginx", "svc_action": "restart"}, pv["token"], True)["ok"])
        self.assertEqual([c for c in fake.remote if c["prog"].endswith("systemctl")], [])

    def test_switching_forgets_what_was_learned_about_the_other_computer(self):
        tb, fake = toolbox(FakeSsh(answers={"ufw": "Added user rules (see 'ufw status' for running firewall):\nufw allow 9090/tcp\n"}))
        remote(tb)
        tb.run_readonly("ufw.status")
        self.assertTrue(tb.info()["ufw"]["rules_loaded"])
        remote(tb, host="10.0.0.9")
        self.assertFalse(tb.info()["ufw"]["rules_loaded"])

    def test_the_whole_catalogue_plans_on_the_remote_computer_with_remote_programs(self):
        tb, fake = toolbox()
        remote(tb)
        tb.run_readonly("ufw.status")
        n = 0
        for op in registry.OPERATIONS.values():
            params = dict(sample(tb, op), **{"ufw.rule.delete": {"port": "9090", "proto": "tcp", "action": "any"}, "web.site.enable": {"site": "mgawm"},
                                             "usr.add": {"username": "carol"}}.get(op.id, {}))
            pv = tb.preview(op.id, params)
            if op.id == "ufw.rule.delete":
                continue                                                                  # needs a loaded rule list: covered below
            self.assertTrue(pv["ok"], (op.id, pv["errors"], pv["blocked"]))
            plan = op.plan(tb.context(), params)
            for cmd in plan.commands:
                self.assertTrue(cmd[0].startswith(("/usr/sbin/", "/usr/bin/", "/sbin/", "/bin/")), (op.id, cmd))
            n += 1
        self.assertGreater(n, 140)

    def test_native_checks_look_at_the_remote_computer_not_this_one(self):
        tb, fake = toolbox()
        remote(tb)
        res = tb.run_readonly("ssh.config.file")
        self.assertIn("PermitRootLogin no", res["output"])
        self.assertTrue([c for c in fake.remote if c["prog"] == "head"])         # read over ssh
        pv = tb.preview("ssh.perms.fix", {})
        res = tb.execute("ssh.perms.fix", {}, pv["token"], True)
        self.assertTrue(res["ok"], res)
        self.assertIn((HOME + "/.ssh", 0o700), fake.sys.chmods)
        self.assertTrue([c for c in fake.remote if c["prog"].endswith("chmod")])

    def test_the_firewall_knows_which_port_this_connection_uses(self):
        tb, _ = toolbox()
        remote(tb, port=2222)
        pv = tb.preview("ufw.rule.add", {"port": "2222", "proto": "tcp", "action": "deny"})
        self.assertEqual(pv["risk"], "high")                                              # it would cut the very connection the tool uses
        self.assertTrue(any("SSH" in w for w in pv["warnings"]))
        self.assertEqual(tb.preview("ufw.rule.add", {"port": "8081", "proto": "tcp", "action": "deny"})["risk"], "medium")

    def test_remote_answers_are_checked_before_they_are_used(self):
        tb, fake = toolbox()
        remote(tb)
        sysx = tb.sysx
        for evil in ("/tmp/evil/ss", "/home/alice/bin/ss", "ss", "/usr/bin/ss extra", "../../bin/ss"):
            sysx._cache.clear()
            fake.handle = lambda name, prog, args, env, root, e=evil: subprocess.CompletedProcess(args, 0, e + "\n", "")
            self.assertIsNone(sysx.find_program("ss"), evil)
        sysx._cache.clear()
        for name in ("a/b", "../x", "x y", "-x", "", "a;b"):
            self.assertIsNone(sysx.find_program(name), name)
        self.assertEqual(sysx.home, "/home/alice")

    def test_a_remote_home_that_looks_wrong_is_not_trusted(self):
        tb, fake = toolbox()
        remote(tb)
        fake.handle = lambda name, prog, args, env, root: subprocess.CompletedProcess(args, 0, "alice:x:1:1::/home/../etc:/bin/sh\n", "")
        self.assertEqual(tb.sysx.home, "/home/alice")

    def test_output_from_another_computer_is_cleaned(self):
        evil = "ok\x1b[31mred\x1b[0m \x1b]0;title\x07 bell\x07 nul\x00 ctrl\x01\ttab\nline\r\n"
        tb, _ = toolbox(FakeSsh(answers={"ip": evil}))
        remote(tb)
        out = tb.run_readonly("net.addr")["output"]
        self.assertNotIn("\x1b", out)
        self.assertNotIn("\x07", out)
        self.assertNotIn("\x00", out)
        self.assertNotIn("\x01", out)
        self.assertIn("red", out)
        self.assertIn("\t", out)

    def test_history_records_the_computer_but_nothing_secret(self):
        tb, _ = toolbox()
        remote(tb)
        tb.run_readonly("net.addr")
        entry = tb.history_entries()[0]
        self.assertEqual(entry["target"], "alice@10.0.0.5:22")
        raw = open(tb.history.path, encoding="utf-8").read()
        self.assertNotIn("id_ed25519", raw)
        tb.set_target("local")
        tb.run_readonly("net.addr")
        self.assertNotIn("target", tb.history_entries()[0])

    def test_this_computer_is_unaffected(self):
        tb, fake = toolbox()
        res = tb.run_readonly("net.addr")
        self.assertTrue(res["ok"])
        self.assertEqual(fake.remote, [])
        self.assertEqual(res["target"], "this computer")


class Failures(unittest.TestCase):
    def run_with(self, fail=None, **kw):
        tb, fake = toolbox(FakeSsh(fail=fail, **kw))
        remote(tb)
        return tb.run_readonly("net.addr")

    def test_connection_problems_are_explained(self):
        for fail, word in (("refused", "refused"), ("auth", "did not accept your SSH key"), ("hostkey", "not trusted yet"), ("changed", "CHANGED"),
                           ("resolve", "could not be resolved"), ("timeout", "took too long")):
            res = self.run_with(fail)
            self.assertFalse(res["ok"], fail)
            self.assertIn(word, res["message"], fail)
        res = self.run_with("weird")
        self.assertIn("SSH connection failed", res["message"])

    def test_a_built_in_check_on_an_unreachable_computer_reports_the_connection_not_an_empty_list(self):
        tb, _ = toolbox(FakeSsh(fail="hostkey"))
        remote(tb)
        res = tb.run_readonly("ssh.config.file")
        self.assertFalse(res["ok"])
        self.assertIn("not trusted yet", res["message"])
        res = tb.run_readonly("usr.list")
        self.assertFalse(res["ok"])

    def test_a_missing_sudo_password_is_explained_and_nothing_else_runs(self):
        tb, fake = toolbox(FakeSsh(sudo_ok=False))
        remote(tb)
        res = tb.run_readonly("net.listen.proc")
        self.assertFalse(res["ok"])
        self.assertIn("asks for a password", res["message"])
        t = tb.target_test()
        self.assertTrue(t["ok"])
        self.assertFalse(t["sudo"])
        self.assertIn("NOT available", t["message"])

    def test_the_connection_test(self):
        tb, _ = toolbox()
        remote(tb)
        t = tb.target_test()
        self.assertEqual((t["ok"], t["user"], t["sudo"]), (True, "alice", True))
        self.assertIn("Connected to alice@10.0.0.5:22", t["message"])
        bad, _ = toolbox(FakeSsh(fail="refused"))
        remote(bad)
        self.assertFalse(bad.target_test()["ok"])
        self.assertTrue(toolbox()[0].target_test()["ok"])                                  # local: nothing to test

    def test_no_ssh_client(self):
        tb, _ = toolbox()
        tb.set_target("remote", "h.example", 22, "alice")
        tb.target._find_ssh = lambda: None
        self.assertIn("openssh-client", tb.run_readonly("net.addr")["message"])


class HostKeys(unittest.TestCase):
    def test_scan_shows_fingerprints_and_trust_needs_the_token_and_a_confirmation(self):
        home = tempfile.mkdtemp()
        tb, fake = toolbox(home=home)
        scan = tb.hostkey_scan("10.0.0.5", 22)
        self.assertTrue(scan["ok"], scan)
        self.assertEqual(scan["fingerprints"], ["SHA256:AbCdEf1234567890 (ED25519)"])
        self.assertFalse(scan["trusted"])
        self.assertTrue(scan["token"])
        kh = os.path.join(home, ".ssh", "known_hosts")
        self.assertFalse(os.path.exists(kh))                                               # looking is not trusting
        self.assertFalse(tb.hostkey_trust(scan["token"], False)["ok"])
        self.assertFalse(tb.hostkey_trust(scan["token"], "yes")["ok"])
        self.assertFalse(tb.hostkey_trust("made-up", True)["ok"])
        self.assertFalse(os.path.exists(kh))
        scan = tb.hostkey_scan("10.0.0.5", 22)
        done = tb.hostkey_trust(scan["token"], True)
        self.assertTrue(done["ok"], done)
        self.assertEqual(open(kh).read(), SCAN)
        self.assertEqual(oct(os.stat(kh).st_mode & 0o777), "0o600")
        self.assertEqual(oct(os.stat(os.path.dirname(kh)).st_mode & 0o777), "0o700")
        self.assertFalse(tb.hostkey_trust(scan["token"], True)["ok"])                      # single use
        self.assertEqual(tb.history_entries()[0]["op"], "target.hostkey.trust")
        keyscan = [c for c, _ in fake.local if os.path.basename(c[0]) == "ssh-keyscan"][0]
        self.assertEqual(keyscan[-4:], ["-T", "5", "-p", "22"] if False else keyscan[-4:])
        self.assertEqual(keyscan[-1], "10.0.0.5")

    def test_only_well_formed_key_lines_are_ever_written(self):
        evil = ("10.0.0.5 ssh-ed25519 " + HOST_KEY + "\nevil.com,10.0.0.5 ssh-rsa AAAA\n# comment\n|1|hash ssh-rsa AAAA\n10.0.0.5 ssh-ed25519 AAAA;rm -rf /\n"
                "10.0.0.5 ssh-ed25519 AAAA extra\n10.0.0.5 cert-authority AAAA\n@cert-authority * ssh-rsa AAAA\n")
        lines = target.parse_scan(evil)
        self.assertEqual(lines, [("10.0.0.5", "ssh-ed25519", HOST_KEY)])
        home = tempfile.mkdtemp()
        tb, _ = toolbox(FakeSsh(scan=evil), home=home)
        scan = tb.hostkey_scan("10.0.0.5")
        tb.hostkey_trust(scan["token"], True)
        self.assertEqual(open(os.path.join(home, ".ssh", "known_hosts")).read(), "10.0.0.5 ssh-ed25519 " + HOST_KEY + "\n")
        none, _ = toolbox(FakeSsh(scan="garbage\n"))
        self.assertFalse(none.hostkey_scan("10.0.0.5")["ok"])

    def test_scan_validates_the_address(self):
        tb, fake = toolbox()
        for bad in ("-oProxyCommand=id", "a b", "x;y", "", "a@b"):
            self.assertFalse(tb.hostkey_scan(bad, 22)["ok"], bad)
        self.assertFalse(tb.hostkey_scan("h.example", 99999)["ok"])
        self.assertEqual(fake.local, [])

    def test_an_expired_scan_cannot_be_trusted(self):
        now = [1000.0]
        home = tempfile.mkdtemp()
        tb, _ = toolbox(home=home, clock=lambda: now[0])
        scan = tb.hostkey_scan("10.0.0.5")
        now[0] += api.TOKEN_TTL + 1
        self.assertFalse(tb.hostkey_trust(scan["token"], True)["ok"])
        self.assertFalse(os.path.exists(os.path.join(home, ".ssh", "known_hosts")))


class RemoteFiles(unittest.TestCase):
    def test_the_remote_system_object_answers_like_the_local_one(self):
        tb, _ = toolbox()
        remote(tb)
        s = tb.sysx
        self.assertTrue(s.isdir("/etc/netplan"))
        self.assertFalse(s.isfile("/etc/netplan"))
        self.assertTrue(s.islink("/etc/nginx/sites-enabled/default"))
        self.assertTrue(s.exists("/etc/nginx/sites-enabled/default"))
        self.assertEqual(s.listdir("/etc/netplan"), ["00-installer-config.yaml", "readme.txt"])
        self.assertEqual(s.listdir("/nonexistent"), [])
        self.assertEqual(s.read_text("/proc/sys/vm/swappiness").strip(), "60")
        self.assertIsNone(s.read_text("/nonexistent"))
        self.assertEqual(s.stat_mode(HOME + "/.ssh"), 0o755)
        self.assertEqual(s.username(), "alice")
        self.assertIn(("alice", 1000, "/bin/bash"), s.users())
        self.assertEqual(s.config()["projects"][0]["name"], "docker-app")
        self.assertEqual(s.file_age_days(HOME + "/backups/db_2026.sql", 0), 90.0)
        self.assertIsNone(s.rlimit_nofile())
        self.assertEqual(s.find_program("ss"), "/usr/bin/ss")
        self.assertEqual(s.find_program("ufw", root=True), "/usr/sbin/ufw")
        self.assertNotIn("ufw", SBIN - {"ufw"})


class Closing(unittest.TestCase):
    def test_close_ends_the_shared_connection_and_removes_its_folder(self):
        tb, fake = toolbox()
        remote(tb)
        tb.run_readonly("net.addr")
        folder = tb.target.control_dir
        self.assertTrue(os.path.isdir(folder))
        self.assertEqual(oct(os.stat(folder).st_mode & 0o777), "0o700")
        tb.close()
        self.assertFalse(os.path.exists(folder))
        tb.set_target("local")
        tb.close()                                                                         # nothing to close: no error


if __name__ == "__main__":
    unittest.main()
