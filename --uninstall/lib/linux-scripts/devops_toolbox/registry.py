"""The allowlist: every operation the toolbox can perform is declared here, in code, as an Operation. There is no way to add one
at run time and no operation that takes a command, path, URL or program name from the user."""
from collections import OrderedDict

RISKS = ("info", "low", "medium", "high")          # info = only reads; high = removes something / may lock you out


KINDS = ("port", "int", "choice", "comment", "text", "host", "ip", "identifier", "ports", "bool", "image", "username")


class Param:
    """One input of an operation. kind: port | int (lo..hi) | choice (fixed list, or a list the system provides: `dynamic`) |
    comment (a rule description) | text | host | ip | identifier | ports ('22,80') | bool. Every kind has its own strict validator
    in validation.py; nothing is passed to a program without passing it."""

    def __init__(self, name, kind, label, choices=(), required=True, default="", dynamic="", lo=0, hi=0):
        assert kind in KINDS
        self.name, self.kind, self.label = name, kind, label           # label: i18n key
        self.choices, self.required, self.default = tuple(choices), required, default
        self.dynamic = dynamic                                          # name of a context lookup that supplies the choices
        self.lo, self.hi = lo, hi

    def as_dict(self):
        return {"name": self.name, "kind": self.kind, "label": self.label, "choices": list(self.choices),
                "required": self.required, "default": self.default, "dynamic": bool(self.dynamic), "lo": self.lo, "hi": self.hi}


class Operation:
    """id: unique ('ufw.rule.add'). category: key of a Category. name / description: i18n keys (Georgian + English live in
    i18n.py). params: [Param]. risk: one of RISKS. needs_root: True when it needs administrator rights.
    plan(ctx, params) -> Plan: validates `params` (raising validation.ValidationError) and builds what would run.
    finish(ctx, plan, results) -> (ok, i18n key, kwargs, summary): turns the programs' output into a result."""

    def __init__(self, id, category, name, description, params, risk, needs_root, plan, finish, timeout=120):
        assert risk in RISKS
        self.id, self.category, self.name, self.description = id, category, name, description
        self.params, self.risk, self.needs_root = list(params), risk, needs_root
        self.plan, self.finish, self.timeout = plan, finish, timeout


class Plan:
    """What an operation would do: `commands` = [argv lists] (run in order, stopping at the first failure), plus what the user
    must read before agreeing. `blocked` is an i18n key when it must not run (duplicate rule, nothing to do ...)."""

    def __init__(self, commands, params, explain=(), warnings=(), blocked="", blocked_args=None, root=True, risk=None,
                 func=None, post=None, as_user=None, env=None):
        self.commands = [list(c) for c in commands]
        self.func = func                              # a built-in check run inside the tool instead of a program: () -> text
        self.post = post                              # text -> text: keep the lines that matter (top 10, a filter ...)
        self.as_user = as_user                        # run as this system user through pkexec --user (e.g. postgres)
        self.env = env
        self.params = dict(params)                    # the validated, normalised parameters (what history and tokens use)
        self.explain = list(explain)                  # [(i18n key, kwargs)]
        self.warnings = list(warnings)                # [(i18n key, kwargs)]
        self.blocked, self.blocked_args = blocked, dict(blocked_args or {})
        self.root = root
        self.risk = risk                              # overrides the operation's risk for this call (e.g. denying port 22)


class Category:
    def __init__(self, id, name, icon=""):
        self.id, self.name, self.icon = id, name, icon                 # name: i18n key


CATEGORIES = OrderedDict()
OPERATIONS = OrderedDict()


def category(cat):
    CATEGORIES.setdefault(cat.id, cat)
    return cat


def register(op):
    if op.id in OPERATIONS:
        raise ValueError("duplicate operation id: " + op.id)
    if op.category not in CATEGORIES:
        raise ValueError("unknown category: " + op.category)
    OPERATIONS[op.id] = op
    return op


def get(op_id):
    """The operation, or None for an id that is not on the allowlist."""
    return OPERATIONS.get(op_id) if isinstance(op_id, str) else None
