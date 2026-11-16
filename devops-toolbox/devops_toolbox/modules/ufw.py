"""UFW Firewall Manager: show the rules, open / block a port, delete a rule.

How UFW behaves (checked against ufw 0.36 and the Ubuntu documentation), because the interface says it:
  * `ufw allow 19999/tcp` takes effect IMMEDIATELY while the firewall is active. `ufw reload` is only needed after the files in
    /etc/ufw are edited by hand, so this module never runs it. A rule added while the firewall is inactive is stored and starts
    working when the firewall is enabled.
  * Every ufw command, even `ufw status`, needs root: all of them run through pkexec (runner.run_root).
  * `ufw show added` lists the configured rules also when the firewall is inactive: the rule list and the duplicate check use it.
  * Deleting a rule by its text (`ufw --force delete allow 19999/tcp`) is stable; deleting by number is not (numbers shift).
    ufw answers "Could not delete non-existent rule" with exit status 0, so the output is read, not only the exit code.
  * Turning the firewall on or off is deliberately NOT here: `disable` would drop protection silently and `enable` can lock you
    out of an SSH session unless an SSH rule exists first (MyDevOps Task 7). Do those two in a terminal, on purpose.
"""
import os
import re
import shlex

from .. import registry, validation
from ..registry import Operation, Param, Plan

from . import _dsl

_dsl.category("net", "Network", "ქსელი")
_dsl.category("firewall", "Firewall (UFW)", "Firewall (UFW)")

UFW_PATHS = ("/usr/sbin/ufw", "/sbin/ufw", "/usr/bin/ufw")      # root-owned places only: root runs this program
CONF = "/etc/ufw/ufw.conf"
DEFAULTS = "/etc/default/ufw"
ADD_ACTIONS = ("allow", "deny", "reject")
PROTOCOLS = ("tcp", "udp")
SSH_PORT = 22
_SIMPLE = re.compile(r"^([0-9]{1,5})(?:/(tcp|udp))?$")
_SSH_CONN = re.compile(r"^\S+ [0-9]+ \S+ ([0-9]+)$")


# ---- what is installed / configured (all readable without root) ----
def find_ufw(isfile=os.path.isfile, access=os.access):
    for p in UFW_PATHS:
        if isfile(p) and access(p, os.X_OK):
            return p
    return None


def _read_kv(path, opener=open):
    out = {}
    try:
        with opener(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        return None
    return out


def read_active(path=CONF, opener=open):
    """True / False from ENABLED= in /etc/ufw/ufw.conf (world-readable), None when it cannot be read."""
    kv = _read_kv(path, opener)
    if kv is None or "ENABLED" not in kv:
        return None
    return kv["ENABLED"].lower() in ("yes", "true", "1")


def read_default_policy(path=DEFAULTS, opener=open):
    kv = _read_kv(path, opener) or {}
    return {"incoming": kv.get("DEFAULT_INPUT_POLICY", "").lower(), "outgoing": kv.get("DEFAULT_OUTPUT_POLICY", "").lower()}


def ssh_port_of_session(env=None):
    """The port this very session was opened through when it is an SSH session (SSH_CONNECTION), else None."""
    m = _SSH_CONN.match((env if env is not None else os.environ).get("SSH_CONNECTION", ""))
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 65535 else None


# ---- the rule list ----
class Rule:
    """A rule UFW reports and this module can manage: ufw <action> <port>[/<proto>] [comment '...'], proto 'any' = tcp and udp."""

    def __init__(self, action, port, proto, comment=""):
        self.action, self.port, self.proto, self.comment = action, port, proto, comment

    @property
    def spec(self):
        return str(self.port) if self.proto == "any" else f"{self.port}/{self.proto}"

    @property
    def text(self):
        return f"{self.action} {self.spec}"

    def as_dict(self):
        return {"action": self.action, "port": self.port, "proto": self.proto, "comment": self.comment, "spec": self.spec}

    def __eq__(self, other):
        return isinstance(other, Rule) and (self.action, self.port, self.proto) == (other.action, other.port, other.proto)

    def __hash__(self):
        return hash((self.action, self.port, self.proto))


def parse_added(text):
    """`ufw show added` -> ([Rule], [other rule lines]). Rules that are not plain 'action port[/proto]' (a source address, a port
    range, an interface, routing ...) are kept as text in the second list: shown, never edited here."""
    rules, other = [], []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line.startswith("ufw "):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            other.append(line)
            continue
        rule = None
        if len(tokens) >= 3 and tokens[1] in ("allow", "deny", "reject", "limit"):
            m = _SIMPLE.match(tokens[2])
            rest = tokens[3:]
            comment = ""
            if m and (not rest or (len(rest) == 2 and rest[0] == "comment")):
                if rest:
                    comment = rest[1]
                port = int(m.group(1))
                if 1 <= port <= 65535:
                    rule = Rule(tokens[1], port, m.group(2) or "any", comment)
        if rule:
            rules.append(rule)
        else:
            other.append(line[4:])
    return rules, other


def _overlap(a_proto, b_proto):
    return a_proto == b_proto or "any" in (a_proto, b_proto)


# ---- the operations ----
def _ufw(ctx):
    return getattr(ctx, "ufw", None)


def plan_status(ctx, params):
    if not _ufw(ctx):
        return Plan([], {}, blocked="err_ufw_missing", root=False)
    return Plan([[ctx.ufw, "show", "added"]], {}, explain=[("explain_status", {})])


def finish_status(ctx, plan, results):
    res = results[-1]
    if not res.ok:
        return (False,) + _failure(res) + (_summary(res), None)
    rules, other = parse_added(res.stdout)
    data = {"rules": [r.as_dict() for r in rules], "other": other}
    return True, "ok_status", {"n": len(rules) + len(other)}, f"{len(rules) + len(other)} rules", data


def plan_add(ctx, params):
    port = validation.port(params.get("port"))
    proto = validation.choice(params.get("proto"), PROTOCOLS, "err_protocol")
    action = validation.choice(params.get("action"), ADD_ACTIONS, "err_action")
    comment = validation.comment(params.get("comment"))
    clean = {"port": port, "proto": proto, "action": action, "comment": comment}
    if not _ufw(ctx):
        return Plan([], clean, blocked="err_ufw_missing", root=False)
    explain = [("explain_add_now", {}), ("explain_no_reload", {})]
    warnings, risk = [], "medium"
    rules = getattr(ctx, "rules", None)
    if rules is None:
        warnings.append(("warn_rules_unknown", {}))
    else:
        for r in rules:
            if r.port == port and _overlap(r.proto, proto):
                if r.action == action:
                    return Plan([], clean, explain, warnings, blocked="blocked_duplicate", blocked_args={"rule": r.text})
                return Plan([], clean, explain, warnings, blocked="blocked_conflict", blocked_args={"rule": r.text})
    if getattr(ctx, "active", None) is False:
        warnings.append(("warn_inactive", {}))
    elif getattr(ctx, "active", None) is None:
        warnings.append(("warn_state_unknown", {}))
    if action in ("deny", "reject") and proto == "tcp" and port in (SSH_PORT, getattr(ctx, "ssh_port", None)):
        warnings.append(("warn_ssh_lockout", {"port": port}))
        risk = "high"
    argv = [ctx.ufw, action, f"{port}/{proto}"] + (["comment", comment] if comment else [])
    return Plan([argv], clean, explain, warnings, risk=risk)


def plan_delete(ctx, params):
    port = validation.port(params.get("port"))
    proto = validation.choice(params.get("proto"), PROTOCOLS + ("any",), "err_protocol")
    which = validation.choice(params.get("action") or "any", ("any", "allow", "deny", "reject", "limit"), "err_action")
    clean = {"port": port, "proto": proto, "action": which}
    if not _ufw(ctx):
        return Plan([], clean, blocked="err_ufw_missing", root=False)
    rules = getattr(ctx, "rules", None)
    if rules is None:
        return Plan([], clean, blocked="blocked_rules_unknown")
    found = [r for r in rules if r.port == port and r.proto == proto and which in ("any", r.action)]
    if not found:
        return Plan([], clean, blocked="blocked_no_such_rule", blocked_args={"rule": f"{port}/{proto}"})
    warnings = []
    if any(r.action in ("allow", "limit") and r.port in (SSH_PORT, getattr(ctx, "ssh_port", None)) for r in found):
        warnings.append(("warn_ssh_delete", {"port": found[0].port}))
    if len(found) > 1:
        warnings.append(("warn_several_rules", {"n": len(found)}))
    cmds = [[ctx.ufw, "--force", "delete", r.action, r.spec] for r in found]
    return Plan(cmds, clean, [("explain_delete_now", {}), ("explain_no_reload", {})], warnings, risk="high")


_ERRORS = (                                                 # (text in ufw's answer, i18n key), first match wins
    ("you need to be root", "err_not_authorized"),
    ("could not delete non-existent rule", "err_rule_missing"),
    ("bad port", "err_port_invalid"),
    ("problem running iptables", "err_firewall_backend"),
    ("could not fetch rule set", "err_firewall_backend"),
    ("permission denied", "err_not_authorized"),
    ("command not found", "err_ufw_missing"),
)


def _failure(res):
    """-> (i18n key, kwargs) for a program that failed or whose answer says the rule was not changed."""
    if res.error:
        return res.error, {"detail": (res.stderr or "").strip()[:200]}
    text = (res.stdout + "\n" + res.stderr).lower()
    for needle, key in _ERRORS:
        if needle in text:
            return key, {}
    return "err_ufw_failed", {"detail": _first_line(res.stderr or res.stdout)}


def _first_line(text):
    for line in (text or "").splitlines():
        if line.strip() and "initcaps" not in line:
            return line.strip()[:200]
    return ""


def _summary(res):
    return _first_line(res.stderr or res.stdout) or (res.error or "")


def _finish_change(ok_key, ctx, plan, results):
    out = ""
    for res in results:
        if not res.ok:
            return (False,) + _failure(res) + (_summary(res), None)
        out += res.stdout + "\n"
        low = out.lower()
        if "could not delete non-existent rule" in low:          # exit status 0, but nothing was deleted
            return False, "err_rule_missing", {}, "rule not found", None
    if "skipping adding existing rule" in out.lower():
        return True, "ok_rule_exists", {}, "already existed", None
    return True, ok_key, {}, _first_line(out) or "ok", None


def finish_add(ctx, plan, results):
    return _finish_change("ok_rule_added", ctx, plan, results)


def finish_delete(ctx, plan, results):
    return _finish_change("ok_rule_deleted", ctx, plan, results)


registry.register(Operation("ufw.status", "firewall", "op_ufw_status", "op_ufw_status_desc", [], "info", True,
                            plan_status, finish_status, timeout=120))
registry.register(Operation("ufw.rule.add", "firewall", "op_ufw_add", "op_ufw_add_desc", [
    Param("port", "port", "p_port"),
    Param("proto", "choice", "p_proto", PROTOCOLS, default="tcp"),
    Param("action", "choice", "p_action", ADD_ACTIONS, default="allow"),
    Param("comment", "text", "p_comment", required=False)], "medium", True, plan_add, finish_add, timeout=120))
registry.register(Operation("ufw.rule.delete", "firewall", "op_ufw_delete", "op_ufw_delete_desc", [
    Param("port", "port", "p_port"),
    Param("proto", "choice", "p_proto", PROTOCOLS + ("any",), default="tcp"),
    Param("action", "choice", "p_action_filter", ("any", "allow", "deny", "reject", "limit"), required=False, default="any")],
    "high", True, plan_delete, finish_delete, timeout=120))


# ---- more of the firewall tab of the MyDevOps notes (tasks 7, 8, 17): verbose / numbered status, application profiles, default policy ----
from ._dsl import P as _P  # noqa: E402
from ._dsl import op as _op  # noqa: E402
from .. import i18n as _i18n  # noqa: E402

_PROFILES = ("ssh", "http", "https", "OpenSSH", "Nginx HTTP", "Nginx HTTPS", "Nginx Full")
_POLICIES = ("deny incoming", "allow outgoing")
_i18n.add("warn_default_deny_no_ssh", "No rule allows SSH (port 22) yet: once the firewall is active, 'deny incoming' would cut off SSH access.",
          "SSH-ს (პორტი 22) არც ერთი წესი არ უშვებს: როცა firewall ჩაირთვება, 'deny incoming' SSH წვდომას გაწყვეტს.")

_op("ufw.status.verbose", "firewall", ("UFW status (verbose)", "UFW-ის სტატუსი (დეტალურად)"), ("State, default policies and the active rules (ufw status verbose); needs administrator rights.", "მდგომარეობა, ნაგულისხმევი პოლიტიკა და მოქმედი წესები (ufw status verbose); საჭიროა ადმინისტრატორის უფლება."),
    argv=["@ufw", "status", "verbose"], root=True)
_op("ufw.status.numbered", "firewall", ("UFW status (numbered)", "UFW-ის სტატუსი (დანომრილი)"), ("The active rules with their numbers (ufw status numbered). The tool deletes by rule text, never by number.", "მოქმედი წესები ნომრებით (ufw status numbered). ხელსაწყო წესს წაშლის ტექსტით და არა ნომრით."),
    argv=["@ufw", "status", "numbered"], root=True)
_op("ufw.app.allow", "firewall", ("UFW: allow an application profile", "UFW: აპლიკაციის პროფილის დაშვება"), ("Allows a known service by name (ssh, http, https, Nginx ...): ufw allow 'Nginx Full'.", "უშვებს ცნობილ სერვისს სახელით (ssh, http, https, Nginx ...): ufw allow 'Nginx Full'."),
    argv=["@ufw", "allow", "{profile}"], params=[_P("profile", choices=_PROFILES, default="ssh")], root=True, risk="medium",
    explain=[("explain_add_now", {}), ("explain_no_reload", {})])


def _default_check_risk(ctx, p):
    if p["policy"] == "deny incoming" and not any(r.port == SSH_PORT and r.action in ("allow", "limit") for r in (ctx.rules or [])):
        return "high"
    return None


_op("ufw.default", "firewall", ("UFW: default policy", "UFW: ნაგულისხმევი პოლიტიკა"), ("Sets the default for traffic without a rule: deny incoming, allow outgoing (ufw default ...).", "ადგენს ნაგულისხმევს წესის გარეშე ტრაფიკისთვის: შემომავალი აიკრძალოს, გამავალი დაშვდეს (ufw default ...)."),
    build=lambda ctx, p: [["ufw", "default"] + p["policy"].split()], params=[_P("policy", choices=_POLICIES, default="deny incoming")], root=True,
    risk="medium", risk_for=_default_check_risk,
    warn=lambda ctx, p: [("warn_default_deny_no_ssh", {})] if _default_check_risk(ctx, p) == "high" else [],
    explain=[("explain_no_reload", {})])
