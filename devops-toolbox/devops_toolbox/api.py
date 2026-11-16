"""The one door to the toolbox. The desktop window and the web app both call ONLY these methods, so validation, confirmation,
privilege handling and history are implemented once.

    tb = Toolbox()
    tb.catalog(lang)                         what can be done (categories, operations, their inputs)
    tb.info(lang)                            UFW installed / active, default policy, whether the rule list is loaded
    tb.run_readonly("ufw.status", lang)      operations that only read (risk 'info'): no confirmation needed
    p = tb.preview(op_id, params, lang)      validates, shows the exact command(s); p["token"] if it may be executed
    tb.execute(op_id, params, p["token"], confirmed=True, lang)   runs it - only with a fresh, unused token AND confirmed=True

Every method returns plain dicts of strings, numbers, lists and booleans (JSON-ready) and never raises for bad input."""
import secrets
import shlex
import subprocess
import time

from . import i18n, registry, runner, validation
from .history import History
from .modules import ufw as ufw_module
from .registry import OPERATIONS

TOKEN_TTL = 300                    # seconds a preview stays valid
TOKEN_MAX = 100
OUTPUT_MAX = 4000


class Context:
    """What an operation may look at while planning: UFW's path, the state read without root, and the last loaded rule list."""

    def __init__(self, ufw, active, ssh_port, rules, policy):
        self.ufw, self.active, self.ssh_port, self.rules, self.policy = ufw, active, ssh_port, rules, policy


def _display(argv, ufw_path):
    """The command as a person would type it: `sudo ufw allow 19999/tcp`."""
    shown = ["ufw" if a == ufw_path else a for a in argv]
    return "sudo " + shlex.join(shown)


class Toolbox:
    def __init__(self, runner_fn=subprocess.run, history=None, env=None, euid=None, which=None, clock=time.time,
                 find_ufw=ufw_module.find_ufw, read_active=ufw_module.read_active, read_policy=ufw_module.read_default_policy):
        self._run, self.history = runner_fn, history or History()
        self._env, self._euid, self._which, self._clock = env, euid, which, clock
        self._find_ufw, self._read_active, self._read_policy = find_ufw, read_active, read_policy
        self._tokens = {}
        self._rules = None                      # [Rule] after the last successful load, else None
        self._other = []

    # ---- reading state ----
    def context(self):
        return Context(self._find_ufw(), self._read_active(), ufw_module.ssh_port_of_session(self._env), self._rules, self._read_policy())

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
        for p in op.params:
            if p.required and (params.get(p.name) in (None, "")):
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
               "commands": [self._command_dict(plan, c) for c in plan.commands], "blocked": "", "needs_confirmation": risk != "info"}
        if plan.blocked:
            out["ok"], out["blocked"] = False, i18n.t(lang, plan.blocked, **plan.blocked_args)
            return out
        if risk != "info":
            out["token"] = self._issue(op.id, plan.params)
        return out

    @staticmethod
    def _command_dict(plan, argv):
        ufw_path = argv[0]
        return {"display": _display(argv, ufw_path), "exact": ("pkexec " if plan.root else "") + shlex.join(argv)}

    @staticmethod
    def _error(lang, err):
        return {"param": err.get("param") or "", "message": i18n.t(lang, err["key"], **err.get("args", {}))}

    # ---- tokens: a modifying operation can only run after a preview, once ----
    def _issue(self, op_id, params):
        now = self._clock()
        self._tokens = {k: v for k, v in self._tokens.items() if v[2] > now}
        while len(self._tokens) >= TOKEN_MAX:
            self._tokens.pop(next(iter(self._tokens)))
        token = secrets.token_urlsafe(24)
        self._tokens[token] = (op_id, dict(params), now + TOKEN_TTL)
        return token

    def _take(self, token, op_id, plan_params):
        entry = self._tokens.pop(token, None) if isinstance(token, str) else None
        return bool(entry) and entry[0] == op_id and entry[1] == plan_params and entry[2] > self._clock()

    # ---- running ----
    def run_readonly(self, op_id, lang="en", record=True):
        op = registry.get(op_id)
        if op is None or op.risk != "info":
            return self._result(lang, False, "err_unknown_operation", {}, None, [], "", status="refused", op_id=str(op_id)[:40])
        return self._run_plan(op, {}, lang, record=record)

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
        for argv in plan.commands:
            res = (runner.run_root(argv, timeout=op.timeout, runner=self._run, euid=self._euid, which=self._which) if plan.root
                   else runner.run(argv, timeout=op.timeout, runner=self._run))
            results.append(res)
            if not res.ok or _says_failed(res):
                break
        ctx = self.context()
        ok, key, kw, summary, data = op.finish(ctx, plan, results)
        if ok and op.id == "ufw.status" and data is not None:
            self._rules = [ufw_module.Rule(r["action"], r["port"], r["proto"], r["comment"]) for r in data["rules"]]
            self._other = list(data["other"])
        output = "\n".join(x for r in results for x in ((r.stdout or "").strip(), (r.stderr or "").strip()) if x and "initcaps" not in x)
        out = self._result(lang, ok, key, kw, results[-1].returncode if results else None,
                           [self._command_dict(plan, a)["display"] for a in plan.commands], output, status="ok" if ok else "failed",
                           op_id=op.id, params=plan.params, summary=summary, record=record)
        if ok and op.risk != "info":
            out["refresh"] = self._refresh(lang)                       # the displayed state follows the real one
        if data is not None:
            out["data"] = data
        return out

    def _refresh(self, lang):
        self._rules = None
        res = self.run_readonly("ufw.status", lang, record=False)        # not an action of the user: not in the history
        return {"ok": res["ok"], "rules": res.get("data", {}).get("rules", []), "other": res.get("data", {}).get("other", [])}

    def _result(self, lang, ok, key, kw, exit_code, commands, output, status, op_id, params=None, summary="", record=True):
        message = i18n.t(lang, key, **kw)
        if record:
            self.history.add(op_id, status, exit_code, summary or message, params)
        return {"ok": ok, "status": status, "key": key, "message": message, "exit_code": exit_code, "commands": commands,
                "output": output[:OUTPUT_MAX]}

    # ---- history ----
    def history_entries(self):
        return self.history.entries()

    def clear_history(self):
        self.history.clear()
        return {"ok": True}


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
