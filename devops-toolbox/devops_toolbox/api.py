"""The one door to the toolbox. The desktop window and the web app both call ONLY these methods, so validation, confirmation,
privilege handling and history are implemented once.

    tb = Toolbox()
    tb.catalog(lang)                         what can be done (categories, operations, their inputs)
    tb.info(lang)                            UFW installed / active, default policy, whether the rule list is loaded
    tb.run_readonly("ufw.status", lang)      operations that only read (risk 'info'): no confirmation needed
    p = tb.preview(op_id, params, lang)      validates, shows the exact command(s); p["token"] if it may be executed
    tb.execute(op_id, params, p["token"], confirmed=True, lang)   runs it - only with a fresh, unused token AND confirmed=True

Every method returns plain dicts of strings, numbers, lists and booleans (JSON-ready) and never raises for bad input."""
import os
import re
import secrets
import shlex
import subprocess
import time

from . import i18n, registry, runner, validation
from .history import History
from . import sysaccess, target as target_mod
from .modules import ufw as ufw_module
from .modules import _dsl
from .registry import OPERATIONS

TOKEN_TTL = 300                    # seconds a preview stays valid
TOKEN_MAX = 100
OUTPUT_MAX = 4000


class Context:
    """What an operation may look at while planning: UFW's path, the state read without root, and the last loaded rule list."""

    def __init__(self, ufw, active, ssh_port, rules, policy, sysx=None):
        self.ufw, self.active, self.ssh_port, self.rules, self.policy = ufw, active, ssh_port, rules, policy
        self.sysx = sysx or sysaccess.SysAccess()

    def prog(self, name, root=False):
        """Absolute path of a program (fixed folders only), or None."""
        return self.sysx.find_program(name, root)


class Toolbox:
    def __init__(self, runner_fn=subprocess.run, history=None, env=None, euid=None, which=None, clock=time.time,
                 find_ufw=ufw_module.find_ufw, read_active=ufw_module.read_active, read_policy=ufw_module.read_default_policy,
                 sysx=None, find_ssh=None):
        self._run, self.history = runner_fn, history or History()
        self._find_ssh = find_ssh
        self._local = target_mod.LocalTarget(sysx or sysaccess.SysAccess())
        self.target = self._local
        self._env, self._euid, self._which, self._clock = env, euid, which, clock
        self._find_ufw, self._read_active, self._read_policy = find_ufw, read_active, read_policy
        self._tokens = {}
        self._rules = None                      # [Rule] after the last successful load, else None
        self._other = []

    @property
    def sysx(self):
        """The computer operations look at: this one, or the remote one."""
        return self.target.sysx

    # ---- reading state ----
    def context(self):
        if self.target.kind == "local":
            return Context(self._find_ufw(), self._read_active(), ufw_module.ssh_port_of_session(self._env), self._rules, self._read_policy(),
                           self.sysx)
        sysx = self.sysx                                              # a remote computer: everything is read there, over SSH
        now = self._clock()
        cached = getattr(self, "_remote_ctx", None)
        if cached and cached[0] == self.target.key and now - cached[1] < 5:       # a few seconds: one preview asks several times
            ufw_path, active, policy = cached[2]
        else:
            ufw_path = sysx.find_program("ufw", True)
            active = ufw_module.active_from_text(sysx.read_text(ufw_module.CONF))
            policy = ufw_module.policy_from_text(sysx.read_text(ufw_module.DEFAULTS))
            self._remote_ctx = (self.target.key, now, (ufw_path, active, policy))
        return Context(ufw_path, active, self.target.port, self._rules, policy, sysx)

    def choices(self, op_id, name):
        """The values a dynamic choice may take on this computer (a folder listing, your configured projects ...): [] if none."""
        op = registry.get(op_id)
        p = next((x for x in op.params if x.name == name), None) if op else None
        if p is None or not p.dynamic:
            return []
        return list(_dsl.DYNAMIC[p.dynamic](self.context()))

    def info(self, lang="en"):
        ctx = self.context()
        return {"ufw": {"installed": bool(ctx.ufw), "active": ctx.active, "policy": ctx.policy, "rules_loaded": ctx.rules is not None,
                        "rules": [r.as_dict() for r in (ctx.rules or [])], "other": list(self._other)},
                "language": i18n.norm_lang(lang)}

    def catalog(self, lang="en"):
        lang = i18n.norm_lang(lang)
        cats = []
        for cid, cat in registry.CATEGORIES.items():
            ops = [{"id": o.id, "name": i18n.t(lang, o.name), "description": i18n.t(lang, o.description), "risk": o.risk,
                    "needs_root": o.needs_root, "params": [p.as_dict() for p in o.params]}
                   for o in OPERATIONS.values() if o.category == cid]
            cats.append({"id": cid, "name": i18n.t(lang, cat.name), "operations": ops})
        return {"categories": cats}

    # ---- plan / preview ----
    def _plan(self, op_id, params):
        """-> (op, plan, error dict | None)"""
        op = registry.get(op_id)
        if op is None:
            return None, None, {"key": "err_unknown_operation", "args": {}}
        if not isinstance(params, dict):
            params = {}
        known = {p.name for p in op.params}
        for name in params:
            if name not in known:
                return op, None, {"key": "err_unknown_param", "args": {"name": str(name)[:40]}}
        params = dict(params)
        for p in op.params:
            if p.required and params.get(p.name) in (None, ""):
                if p.default not in (None, ""):
                    params[p.name] = p.default                      # a documented default
                else:
                    return op, None, {"key": "err_missing_param", "args": {"name": p.name}, "param": p.name}
        try:
            return op, op.plan(self.context(), params), None
        except validation.ValidationError as e:
            bad = next((p.name for p in op.params if p.name in params and _fails(op, p.name, params)), None)
            return op, None, {"key": e.key, "args": e.details, "param": bad}

    def preview(self, op_id, params, lang="en"):
        lang = i18n.norm_lang(lang)
        op, plan, err = self._plan(op_id, params)
        if err:
            return {"ok": False, "errors": [self._error(lang, err)], "warnings": [], "commands": [], "token": ""}
        risk = plan.risk or op.risk
        out = {"ok": True, "operation": op.id, "name": i18n.t(lang, op.name), "risk": risk, "level_text": i18n.t(lang, "risk_" + risk),
               "needs_root": bool(plan.commands) and plan.root, "params": dict(plan.params), "errors": [], "token": "",
               "explain": [i18n.t(lang, k, **kw) for k, kw in plan.explain], "warnings": [i18n.t(lang, k, **kw) for k, kw in plan.warnings],
               "commands": [self._command_dict(plan, c) for c in plan.commands], "blocked": "", "needs_confirmation": risk != "info",
               "target": self.target.label, "remote": self.target.kind == "remote"}
        if plan.blocked:
            out["ok"], out["blocked"] = False, i18n.t(lang, plan.blocked, **plan.blocked_args)
            return out
        if risk != "info":
            out["token"] = self._issue(op.id, plan.params)
        return out

    def _command_dict(self, plan, argv):
        """display: the command as a person would type it (`sudo ufw allow 19999/tcp`); exact: what really runs."""
        shown = [os.path.basename(argv[0])] + list(argv[1:])
        if shown[0] == "env":                                          # env VAR=x program ...: show the program by its name too
            i = 1
            while i < len(shown) and "=" in shown[i] and not shown[i].startswith("/"):
                i += 1
            if i < len(shown):
                shown[i] = os.path.basename(shown[i])
        if plan.root:
            who = f"-u {plan.as_user} " if plan.as_user else ""
            display = f"sudo {who}" + shlex.join(shown)
            exact = "pkexec " + (f"--user {plan.as_user} " if plan.as_user else "") + shlex.join(argv)
        else:
            display, exact = shlex.join(shown), shlex.join(argv)
        if self.target.kind == "remote":
            t = self.target
            exact = "ssh -p %d %s@%s %s" % (t.port, t.user, t.host, shlex.quote(t.remote_command(argv, plan.root, plan.as_user, t.is_root, None)))
        return {"display": display, "exact": exact}

    @staticmethod
    def _error(lang, err):
        return {"param": err.get("param") or "", "message": i18n.t(lang, err["key"], **err.get("args", {}))}

    # ---- tokens: a modifying operation can only run after a preview, once ----
    def _issue(self, op_id, params):
        now = self._clock()
        self._tokens = {k: v for k, v in self._tokens.items() if v[2] > now and v[3] == self.target.key}
        while len(self._tokens) >= TOKEN_MAX:
            self._tokens.pop(next(iter(self._tokens)))
        token = secrets.token_urlsafe(24)
        self._tokens[token] = (op_id, dict(params), now + TOKEN_TTL, self.target.key)
        return token

    def _take(self, token, op_id, plan_params):
        entry = self._tokens.pop(token, None) if isinstance(token, str) else None
        return (bool(entry) and entry[0] == op_id and entry[1] == plan_params and entry[2] > self._clock()
                and entry[3] == self.target.key)                      # a preview made for one computer never runs on another

    # ---- running ----
    def run_readonly(self, op_id, lang="en", record=True, params=None):
        """Run an operation that only reads (risk 'info'), with its parameters if it has any. No confirmation is needed for these."""
        op = registry.get(op_id)
        if op is None or op.risk != "info":
            return self._result(lang, False, "err_unknown_operation", {}, None, [], "", status="refused", op_id=str(op_id)[:40])
        return self._run_plan(op, params or {}, lang, record=record)

    def execute(self, op_id, params, token, confirmed, lang="en"):
        lang = i18n.norm_lang(lang)
        op, plan, err = self._plan(op_id, params)
        if err:
            return self._result(lang, False, err["key"], err.get("args", {}), None, [], "", status="refused", op_id=str(op_id)[:40])
        if plan.blocked:
            return self._result(lang, False, plan.blocked, plan.blocked_args, None, [], "", status="refused", op_id=op.id)
        if (plan.risk or op.risk) == "info":
            return self._run_plan(op, params, lang, plan)
        if confirmed is not True:
            return self._result(lang, False, "err_not_confirmed", {}, None, [], "", status="refused", op_id=op.id, params=plan.params)
        if not self._take(token, op.id, plan.params):
            return self._result(lang, False, "err_bad_token", {}, None, [], "", status="refused", op_id=op.id, params=plan.params)
        return self._run_plan(op, params, lang, plan)

    def _run_plan(self, op, params, lang, plan=None, record=True):
        lang = i18n.norm_lang(lang)
        if plan is None:
            op, plan, err = self._plan(op.id, params)
            if err:
                return self._result(lang, False, err["key"], err.get("args", {}), None, [], "", status="refused", op_id=op.id)
            if plan.blocked:
                return self._result(lang, False, plan.blocked, plan.blocked_args, None, [], "", status="refused", op_id=op.id)
        results = []
        if plan.func is not None:                                      # a built-in check: runs here, no program
            if hasattr(self.sysx, "last_error"):
                self.sysx.last_error = ""
            try:
                text = plan.func()
                results.append(runner.RunResult(["(built-in)"], 0, text if isinstance(text, str) else str(text)))
            except Exception as e:  # noqa: BLE001 - reported as a failed check, never a crash
                results.append(runner.RunResult(["(built-in)"], 1, "", str(e)[:300]))
            if getattr(self.sysx, "last_error", ""):                   # the other computer could not be reached: that is the answer, not an empty list
                results = [runner.RunResult(["(built-in)"], None, "", "", error=self.sysx.last_error)]
        for argv in plan.commands:
            if self.target.kind == "remote":
                _ = self.sysx.home                                    # known before a command that may need $HOME (git config --global)
                res = self.target.run(argv, root=plan.root, as_user=plan.as_user, timeout=op.timeout)
            else:
                res = (runner.run_root(argv, timeout=op.timeout, runner=self._run, euid=self._euid, which=self._which, user=plan.as_user)
                       if plan.root else runner.run(argv, timeout=op.timeout, runner=self._run))
            results.append(res)
            if not res.ok or _says_failed(res):
                break
        ctx = self.context()
        ok, key, kw, summary, data = op.finish(ctx, plan, results)
        if ok and op.id == "ufw.status" and data is not None:
            self._rules = [ufw_module.Rule(r["action"], r["port"], r["proto"], r["comment"]) for r in data["rules"]]
            self._other = list(data["other"])
        output = "\n".join(x for r in results for x in ((r.stdout or "").strip(), (r.stderr or "").strip()) if x and "initcaps" not in x)
        if isinstance(data, dict) and "output" in data:                # the operation chose what to show (a filtered list ...)
            output = data["output"]
            data = None if set(data) == {"output"} else {k: v for k, v in data.items() if k != "output"}
        out = self._result(lang, ok, key, kw, results[-1].returncode if results else None,
                           [self._command_dict(plan, a)["display"] for a in plan.commands] if plan.commands else ["(built-in)"],
                           output, status="ok" if ok else "failed",
                           op_id=op.id, params=self._loggable(op, plan.params), summary=summary, record=record)
        if ok and op.risk != "info" and op.id.startswith("ufw."):
            out["refresh"] = self._refresh(lang)                       # the firewall list follows the real state (only for firewall changes)
        if data is not None:
            out["data"] = data
        return out

    @staticmethod
    def _loggable(op, params):
        """Only the values that are safe to keep in the history: names, numbers, choices - not free text."""
        keep = {p.name for p in op.params if p.kind in ("port", "int", "choice", "identifier", "host", "ip", "bool")}
        return {k: v for k, v in params.items() if k in keep}

    def _refresh(self, lang):
        self._rules = None
        res = self.run_readonly("ufw.status", lang, record=False)        # not an action of the user: not in the history
        return {"ok": res["ok"], "rules": res.get("data", {}).get("rules", []), "other": res.get("data", {}).get("other", [])}

    def _result(self, lang, ok, key, kw, exit_code, commands, output, status, op_id, params=None, summary="", record=True):
        message = i18n.t(lang, key, **kw)
        if record:
            self.history.add(op_id, status, exit_code, summary or message, params, target=self.target.label if self.target.kind == "remote" else "")
        return {"ok": ok, "status": status, "key": key, "message": message, "exit_code": exit_code, "commands": commands,
                "output": clean_output(output)[:OUTPUT_MAX], "target": self.target.label}

    # ---- where operations run: this computer, or another one over SSH ----
    def local_keys(self):
        """Your own SSH private keys (a file in ~/.ssh with a matching .pub): the only keys that can be chosen."""
        ssh = os.path.join(self._local.sysx.home, ".ssh")
        names = self._local.sysx.listdir(ssh)
        return [n for n in names if not n.endswith(".pub") and n + ".pub" in names and not n.startswith("-")]

    def target_info(self):
        t = self.target
        return {"kind": t.kind, "label": t.label, "host": t.host or "", "port": t.port or 22, "user": t.user or "", "identity": t.identity or "",
                "keys": self.local_keys()}

    def set_target(self, kind, host="", port=22, user="", identity="", lang="en"):
        """Switch to this computer ('local') or to another one ('remote' + host, port, user, optional key). Validated; nothing connects yet."""
        lang = i18n.norm_lang(lang)
        if kind == "local":
            return self._switch(self._local, lang)
        if kind != "remote":
            return {"ok": False, "errors": [{"param": "kind", "message": i18n.t(lang, "err_unknown_param", name="kind")}], "target": self.target_info()}
        errors = []
        clean = {}
        for name, fn, value in (("host", validation.host, host), ("port", validation.port, port), ("user", validation.identifier, user)):
            try:
                clean[name] = fn(value)
            except validation.ValidationError as e:
                errors.append({"param": name, "message": i18n.t(lang, e.key, **e.details)})
        ident = ""
        if identity not in (None, ""):
            if identity in self.local_keys():
                ident = identity
            else:
                errors.append({"param": "identity", "message": i18n.t(lang, "err_choice_dynamic", allowed=", ".join(self.local_keys()) or "-")})
        if errors:
            return {"ok": False, "errors": errors, "target": self.target_info()}
        return self._switch(target_mod.RemoteTarget(clean["host"], clean["port"], clean["user"], ident, runner_fn=self._run,
                                                    find_ssh=self._find_ssh, home=self._local.sysx.home), lang)

    def _switch(self, new, lang):
        if self.target is not new and self.target is not self._local:
            self.target.close()
        self.target = new
        self._rules, self._other = None, []                        # what was learned about the other computer does not apply here
        self._tokens = {}                                          # and no preview made there can run here
        return {"ok": True, "errors": [], "target": self.target_info()}

    def target_test(self, lang="en"):
        """Try the connection: who am I there, and may I use administrator operations (sudo without a password)?"""
        lang = i18n.norm_lang(lang)
        t = self.target
        if t.kind != "remote":
            return {"ok": True, "message": i18n.t(lang, "tg_local_ok"), "sudo": None, "user": ""}
        who = t.exec(["id", "-un"])
        if not who.ok:
            key = who.error or "err_ssh_failed"
            return {"ok": False, "key": key, "message": i18n.t(lang, key, detail=(who.stderr or "").strip()[:200]), "sudo": None, "user": ""}
        sudo = True if t.is_root else t.run(["/usr/bin/id", "-u"], root=True).ok
        return {"ok": True, "key": "tg_connected", "user": (who.stdout or "").strip(), "sudo": sudo,
                "message": i18n.t(lang, "tg_connected", label=t.label) + " " + i18n.t(lang, "tg_sudo_yes" if sudo else "tg_sudo_no")}

    def hostkey_scan(self, host, port=22, lang="en"):
        """Fetch a computer's host keys and show their fingerprints so YOU can compare them with the real ones. Nothing is trusted yet."""
        lang = i18n.norm_lang(lang)
        try:
            host, port = validation.host(host), validation.port(port)
        except validation.ValidationError as e:
            return {"ok": False, "message": i18n.t(lang, e.key, **e.details), "fingerprints": [], "token": ""}
        scan, keygen = self._local.sysx.find_program("ssh-keyscan"), self._local.sysx.find_program("ssh-keygen")
        if not scan or not keygen:
            return {"ok": False, "message": i18n.t(lang, "err_no_ssh"), "fingerprints": [], "token": ""}
        r = runner.run([scan, "-T", "5", "-p", str(port), host], timeout=30, runner=self._run)
        lines = target_mod.parse_scan(r.stdout)
        if not lines:
            return {"ok": False, "message": i18n.t(lang, "err_hostkey_scan"), "fingerprints": [], "token": ""}
        text = "".join(" ".join(x) + "\n" for x in lines)
        import tempfile
        with tempfile.NamedTemporaryFile("w", prefix="dtb-hk-", delete=False) as f:
            f.write(text)
            tmp = f.name
        try:
            fp = runner.run([keygen, "-lf", tmp], timeout=10, runner=self._run)
        finally:
            os.remove(tmp)
        prints = [ln.split(" ", 1)[1].split(" ")[0] + " " + (ln.rsplit(" ", 1)[-1] if ln.endswith(")") else "")
                  for ln in (fp.stdout or "").splitlines() if ln.strip()]
        token = secrets.token_urlsafe(18)
        self._hostkeys = {k: v for k, v in getattr(self, "_hostkeys", {}).items() if v[3] > self._clock()}
        self._hostkeys[token] = (host, port, text, self._clock() + TOKEN_TTL)
        known = runner.run([keygen, "-F", host if port == 22 else "[%s]:%d" % (host, port)], timeout=10, runner=self._run)
        return {"ok": True, "message": i18n.t(lang, "hk_compare"), "fingerprints": prints, "trusted": known.returncode == 0 and bool((known.stdout or "").strip()),
                "token": token, "host": host, "port": port}

    def hostkey_trust(self, token, confirmed, lang="en"):
        """Add the host keys you were shown to ~/.ssh/known_hosts - only with the token of that very scan and an explicit confirmation."""
        lang = i18n.norm_lang(lang)
        if confirmed is not True:                                   # asking without confirming neither trusts nor uses up the scan
            return {"ok": False, "message": i18n.t(lang, "err_not_confirmed")}
        entry = getattr(self, "_hostkeys", {}).pop(token, None) if isinstance(token, str) else None
        if not entry or entry[3] <= self._clock():
            return {"ok": False, "message": i18n.t(lang, "err_bad_token")}
        ssh = os.path.join(self._local.sysx.home, ".ssh")
        try:
            os.makedirs(ssh, mode=0o700, exist_ok=True)
            path = os.path.join(ssh, "known_hosts")
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(entry[2])
        except OSError as e:
            return {"ok": False, "message": str(e)[:200]}
        self.history.add("target.hostkey.trust", "ok", None, "%s:%d" % (entry[0], entry[1]), {"host": entry[0], "port": entry[1]})
        return {"ok": True, "message": i18n.t(lang, "hk_trusted", host=entry[0])}

    def close(self):
        """Close the connection to a remote computer (the window and the web app call this when they end)."""
        if self.target is not self._local:
            self.target.close()

    # ---- history ----
    def history_entries(self):
        return self.history.entries()

    def clear_history(self):
        self.history.clear()
        return {"ok": True}


_CONTROL = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-Z\\-_]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_output(text):
    """Program output is untrusted text (above all from another computer): terminal escape sequences and control characters are removed."""
    return _CONTROL.sub("", text or "")


def _says_failed(res):
    """ufw reports 'Could not delete non-existent rule' with exit status 0: stop the chain on the words too."""
    return "could not delete non-existent rule" in (res.stdout or "").lower()


def _fails(op, name, params):
    """Which parameter a ValidationError belongs to: the first one whose own validation fails alone."""
    p = next(x for x in op.params if x.name == name)
    try:
        if p.kind == "port":
            validation.port(params.get(name))
        elif p.kind == "choice":
            validation.choice(params.get(name) or p.default, p.choices)
        elif p.kind == "text":
            validation.comment(params.get(name))
    except validation.ValidationError:
        return True
    return False
