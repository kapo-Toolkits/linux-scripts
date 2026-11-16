"""A small, declarative way to define operations, so the whole documented command set stays readable and uniform.

    op("net.ping", "net", ("Ping a host", "Host-ის პინგი"), ("...en...", "...ka..."),
       argv=["@ping", "-c", "{count}", "--", "{host}"], params=[P("host"), P("count", lo=1, hi=10, default=4)])

* `argv` is an argument LIST. '@name' is a program, looked up in fixed root-owned folders (never through PATH, so a planted
  program cannot be chosen); '{param}' is replaced by that parameter AFTER validation, always as one whole argument ('{*ports}'
  as several) - a value can never become a second argument or an option, because validators refuse a leading '-', spaces
  and everything outside the kind's alphabet.
* `build(ctx, p)` returns several argument lists when one list is not enough; `native(ctx, p)` is a built-in check that runs
  inside the tool (no program at all).
* `check(ctx, p)` -> (i18n key, kwargs) to refuse an operation for a reason; `warn(ctx, p)` -> [(key, kwargs)] shown in the preview;
  `risk_for(ctx, p)` raises the risk for a particular input.
Both language texts are required for every operation (i18n.add), so an operation can never exist in one language only."""
from .. import i18n, registry, validation
from ..registry import Operation, Param, Plan

# the words of the parameters, once (both languages)
LABELS = {
    "host": ("Host or address", "Host ან მისამართი"), "ip": ("IP address", "IP მისამართი"),
    "count": ("How many (1-10)", "რამდენჯერ (1-10)"), "ports": ("Ports (e.g. 22,80,443)", "პორტები (მაგ. 22,80,443)"),
    "port": ("Port (1-65535)", "პორტი (1-65535)"), "scheme": ("Protocol", "პროტოკოლი"),
    "insecure": ("Accept a self-signed certificate (local addresses only)", "მივიღო თვითხელმოწერილი სერტიფიკატი (მხოლოდ ლოკალურ მისამართებზე)"),
    "service": ("Service", "სერვისი"), "service_any": ("Service name", "სერვისის სახელი"),
    "svc_action": ("What to do", "რა გავაკეთო"), "lines": ("Lines (10-500)", "ხაზები (10-500)"),
    "container": ("Container name", "კონტეინერის სახელი"), "image": ("Image name", "იმიჯის სახელი"),
    "project": ("Compose project (from your configuration)", "Compose პროექტი (თქვენი კონფიგურაციიდან)"),
    "repo": ("Repository (from your configuration)", "რეპოზიტორია (თქვენი კონფიგურაციიდან)"),
    "key": ("Setting", "პარამეტრი"), "value": ("Value", "მნიშვნელობა"),
    "user": ("User name", "მომხმარებლის სახელი"), "group": ("Group", "ჯგუფი"), "jail": ("Jail", "Jail"),
    "package": ("Package", "პაკეტი"), "dir": ("Folder", "საქაღალდე"), "size": ("Bigger than", "უფრო დიდი ვიდრე"),
    "days": ("Older than (days)", "უფრო ძველი (დღე)"), "vacuum": ("Keep at most", "დარჩეს მაქსიმუმ"),
    "site": ("Site", "საიტი"), "cert": ("Certificate", "სერტიფიკატი"), "db": ("Database", "მონაცემთა ბაზა"),
    "setting": ("Setting", "პარამეტრი"), "zone": ("Time zone (e.g. Asia/Tbilisi)", "დროის სარტყელი (მაგ. Asia/Tbilisi)"),
    "name": ("Name", "სახელი"), "policy": ("Policy", "პოლიტიკა"), "profile": ("Application profile", "აპლიკაციის პროფილი"),
    "file": ("File", "ფაილი"), "swappiness": ("Value (0-100)", "მნიშვნელობა (0-100)"), "limit": ("Show the first", "აჩვენე პირველი"),
    "cn": ("Name for the certificate (host or address)", "სახელი სერტიფიკატისთვის (host ან მისამართი)"),
    "validity": ("Valid for (days)", "მოქმედების ვადა (დღე)"), "config": ("Configuration", "კონფიგურაცია"),
    "unit": ("SSH service", "SSH სერვისი"), "username": ("User name", "მომხმარებლის სახელი"),
    "image_ref": ("Image (e.g. hello-world or nginx:latest)", "იმიჯი (მაგ. hello-world ან nginx:latest)"),
}

PROGRAM_HINTS = {     # program -> (Debian/Ubuntu package that provides it)
    "ss": "iproute2", "ip": "iproute2", "ping": "iputils-ping", "nc": "netcat-openbsd", "lsof": "lsof", "netstat": "net-tools",
    "whois": "whois", "resolvectl": "systemd-resolved", "curl": "curl", "netplan": "netplan.io", "docker": "docker.io",
    "git": "git", "fail2ban-client": "fail2ban", "chronyc": "chrony", "tailscale": "tailscale", "psql": "postgresql-client",
    "pg_dump": "postgresql-client", "nginx": "nginx", "openssl": "openssl", "iostat": "sysstat", "crontab": "cron",
    "last": "util-linux", "lastb": "util-linux", "journalctl": "systemd", "systemctl": "systemd", "systemd-analyze": "systemd",
    "apt-get": "apt (Debian/Ubuntu only)", "apt": "apt (Debian/Ubuntu only)", "dpkg": "dpkg (Debian/Ubuntu only)",
    "sshd": "openssh-server", "ssh-keygen": "openssh-client", "timedatectl": "systemd", "logrotate": "logrotate",
    "adduser": "adduser (Debian/Ubuntu only)", "usermod": "passwd", "gpasswd": "passwd", "passwd": "passwd", "tar": "tar",
    "find": "findutils", "du": "coreutils", "df": "coreutils", "free": "procps", "uptime": "procps", "ps": "procps",
    "nproc": "coreutils", "sysctl": "procps", "chown": "coreutils", "chmod": "coreutils", "ln": "coreutils", "rm": "coreutils",
    "grep": "grep", "env": "coreutils", "ufw": "ufw", "cat": "coreutils", "getent": "libc-bin", "id": "coreutils", "groups": "coreutils",
}

i18n.add("blocked_tool_missing", "This needs the program {program} (Debian/Ubuntu package: {package}), which was not found.",
         "ამისთვის საჭიროა პროგრამა {program} (Debian/Ubuntu-ს პაკეტი: {package}), რომელიც ვერ მოიძებნა.")
i18n.add("ok_done", "Done.", "შესრულდა.")
i18n.add("err_command_failed", "The command ended with an error. {detail}", "ბრძანება შეცდომით დასრულდა. {detail}")
i18n.add("err_identifier_invalid", "Use letters, digits and . _ @ - only (at most 64), starting with a letter or digit.",
         "გამოიყენეთ მხოლოდ ასოები, ციფრები და . _ @ - (მაქსიმუმ 64), დაწყებული ასოთი ან ციფრით.")
i18n.add("err_ip_invalid", "That is not a valid IP address.", "ეს არ არის სწორი IP მისამართი.")
i18n.add("err_host_invalid", "Enter a host name (letters, digits, '-', dots) or an IP address.", "შეიყვანეთ host-ის სახელი (ასოები, ციფრები, '-', წერტილები) ან IP მისამართი.")
i18n.add("err_int_invalid", "Enter a whole number from {min} to {max}.", "შეიყვანეთ მთელი რიცხვი {min}-დან {max}-მდე.")
i18n.add("err_ports_invalid", "Enter up to {limit} ports (1-65535) separated by commas.", "შეიყვანეთ მაქსიმუმ {limit} პორტი (1-65535) მძიმეებით გამოყოფილი.")
i18n.add("err_image_invalid", "Enter an image name like hello-world or nginx:latest.", "შეიყვანეთ იმიჯის სახელი, მაგ. hello-world ან nginx:latest.")
i18n.add("err_username_invalid", "A user name uses lower-case letters, digits, '_' and '-' (at most 32) and starts with a letter or '_'.",
         "მომხმარებლის სახელი იყენებს პატარა ასოებს, ციფრებს, '_' და '-' (მაქსიმუმ 32) და იწყება ასოთი ან '_'-ით.")
i18n.add("err_bool_invalid", "Yes or no is expected.", "მოსალოდნელია დიახ ან არა.")
i18n.add("err_text_invalid", "Use plain text of at most {max} characters, not starting with '-'.", "გამოიყენეთ უბრალო ტექსტი მაქსიმუმ {max} სიმბოლო, რომელიც '-'-ით არ იწყება.")
i18n.add("err_choice_dynamic", "That choice is not available on this computer: {allowed}.", "ეს არჩევანი ამ კომპიუტერზე მიუწვდომელია: {allowed}.")
i18n.add("blocked_nothing_configured", "Nothing is configured here yet. Add it to ~/.config/linux-scripts/devops-toolbox.json (see the README).",
         "აქ ჯერ არაფერია გამართული. დაამატეთ ~/.config/linux-scripts/devops-toolbox.json-ში (იხ. README).")
i18n.add("explain_builtin", "This is a built-in check: no program is started.", "ეს ჩაშენებული შემოწმებაა: არცერთი პროგრამა არ ეშვება.")

def configured(ctx, key):
    """[{'name', 'path'}] from the user's own configuration file: a valid name and an absolute path that is a folder."""
    import re
    out = []
    for item in (ctx.sysx.config().get(key) or []):
        if isinstance(item, dict) and isinstance(item.get("name"), str) and isinstance(item.get("path"), str):
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}", item["name"]) and item["path"].startswith("/") \
                    and ".." not in item["path"].split("/") and ctx.sysx.isdir(item["path"]):
                out.append({"name": item["name"], "path": item["path"]})
    return out


DYNAMIC = {}        # name -> function(ctx) -> list of allowed values (a folder listing, a configured list ...)


def dynamic(name):
    def deco(fn):
        DYNAMIC[name] = fn
        return fn
    return deco


def category(cid, en, ka):
    return registry.category(registry.Category(cid, i18n.add("cat_" + cid, en, ka)))


def P(name, kind="", label=None, **kw):
    """A parameter. The kind defaults from the name (host -> host, port -> port ...); the label text comes from LABELS."""
    default_kind = {"host": "host", "ip": "ip", "port": "port", "ports": "ports", "insecure": "bool", "count": "int", "lines": "int",
                    "days": "int", "swappiness": "int", "validity": "int", "comment": "comment", "cn": "host", "value": "text", "image_ref": "image",
                    "username": "username"}
    kind = kind or default_kind.get(name, "choice" if kw.get("choices") or kw.get("dynamic") else "identifier")
    en, ka = LABELS[label or name]
    key = i18n.add("p_" + (label or name), en, ka)
    kw.setdefault("required", kind != "bool")
    return Param(name, kind, key, **kw)


def _clean(ctx, param, value):
    """Validate one value by its kind -> the normalised value (raises ValidationError)."""
    k = param.kind
    if k == "port":
        return validation.port(value)
    if k == "int":
        return validation.integer(value, param.lo, param.hi)
    if k == "choice":
        allowed = list(param.choices)
        if param.dynamic:
            allowed = list(DYNAMIC[param.dynamic](ctx))
            if not isinstance(value, str) or value.startswith("-") or value not in allowed:
                raise validation.ValidationError("err_choice_dynamic", allowed=", ".join(allowed[:20]) or "-")
            return value
        return validation.choice(value, allowed)
    if k == "comment":
        return validation.comment(value)
    if k == "text":
        return validation.text(value)
    if k == "host":
        return validation.host(value)
    if k == "ip":
        return validation.ip_address(value)
    if k == "identifier":
        return validation.identifier(value)
    if k == "ports":
        return validation.ports(value)
    if k == "bool":
        return validation.boolean(value)
    if k == "image":
        return validation.image_ref(value)
    if k == "username":
        return validation.username(value)
    raise ValueError(k)


def clean_params(ctx, params_def, given):
    out = {}
    for p in params_def:
        value = given.get(p.name)
        if value in (None, "") and not p.required:
            if p.kind == "bool":
                out[p.name] = False
            elif p.default not in (None, ""):
                out[p.name] = _clean(ctx, p, p.default)
            elif p.kind in ("comment",):
                out[p.name] = ""
            continue
        if value in (None, ""):
            value = p.default if p.default not in (None, "") else value
        out[p.name] = _clean(ctx, p, value)
    return out


def _expand(item, p):
    """One argv template element -> list of strings."""
    if item.startswith("{*") and item.endswith("}"):
        return [str(x) for x in p[item[2:-1]]]
    if item.startswith("{") and item.endswith("}") and item[1:-1] in p:
        return [str(p[item[1:-1]])]
    return [item]


def resolve(ctx, argv_lists, root):
    """Replace each list's program NAME by its absolute path. -> (lists, None) or (None, name of the program that is missing)."""
    out = []
    for argv in argv_lists:
        prog = argv[0][1:] if argv[0].startswith("@") else argv[0]
        path = ctx.prog(prog, root)
        if not path:
            return None, prog
        out.append([path] + list(argv[1:]))
    return out, None


def op(oid, cat, name, desc, argv=None, build=None, native=None, params=(), root=False, risk="info", post=None, timeout=60,
       as_user=None, check=None, warn=None, risk_for=None, explain=(), ok_codes=(0,), env_vars=()):
    """Declare and register one operation (see the module docstring)."""
    nkey = i18n.add(oid + ".name", name[0], name[1])
    dkey = i18n.add(oid + ".desc", desc[0], desc[1])
    params = list(params)

    def plan(ctx, given):
        p = clean_params(ctx, params, given)
        if check:
            bad = check(ctx, p)
            if bad:
                return Plan([], p, blocked=bad[0], blocked_args=bad[1] if len(bad) > 1 else {}, root=False)
        warnings = list(warn(ctx, p)) if warn else []
        r = risk_for(ctx, p) if risk_for else None
        if native:
            return Plan([], p, explain=[("explain_builtin", {})] + list(explain), warnings=warnings, root=False, risk=r,
                        func=lambda: native(ctx, p), post=post)
        lists = build(ctx, p) if build else [[x for item in argv for x in _expand(item, p)]]
        if not lists:
            return Plan([], p, blocked="blocked_nothing_configured", root=False)
        cmds, missing = resolve(ctx, lists, root)
        if missing:
            return Plan([], p, blocked="blocked_tool_missing",
                        blocked_args={"program": missing, "package": PROGRAM_HINTS.get(missing, missing)}, root=False)
        if env_vars:                                       # VAR=value assignments through env: still no shell
            env = ctx.prog("env", root)
            if not env:
                return Plan([], p, blocked="blocked_tool_missing", blocked_args={"program": "env", "package": "coreutils"}, root=False)
            cmds = [[env] + list(env_vars) + c for c in cmds]
        return Plan(cmds, p, explain=list(explain), warnings=warnings, root=root, risk=r, post=post, as_user=as_user)

    def finish(ctx, plan_, results):
        for res in results:
            if res.returncode in ok_codes and not res.error and not res.timed_out:
                continue                                  # e.g. `systemctl is-active` answers 3 for 'inactive': information, not failure
            if not res.ok:
                return (False,) + _fail(res) + (_summary(res), {"output": _output(plan_, results)})
        text = _output(plan_, results)
        return True, "ok_done", {}, _first_line(text) or "ok", {"output": text}

    return registry.register(Operation(oid, cat, nkey, dkey, params, risk, root, plan, finish, timeout=timeout))


def _output(plan_, results):
    text = "\n".join(x for r in results for x in ((r.stdout or "").rstrip(), (r.stderr or "").rstrip()) if x)
    if plan_.post:
        try:
            text = plan_.post(text)
        except Exception as e:  # noqa: BLE001 - a filter must never turn a successful command into a crash
            text = text + "\n[" + str(e) + "]"
    return text


def _first_line(text):
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:200]
    return ""


def _summary(res):
    return _first_line(res.stderr or res.stdout) or res.error or ""


def _fail(res):
    if res.error:
        return res.error, {"detail": (res.stderr or "").strip()[:200]}
    low = ((res.stdout or "") + "\n" + (res.stderr or "")).lower()
    if "permission denied" in low or "you need to be root" in low or "must be root" in low or "not permitted" in low:
        return "err_not_authorized_cmd", {"detail": _first_line(res.stderr or res.stdout)}
    return "err_command_failed", {"detail": _first_line(res.stderr or res.stdout)}


i18n.add("err_not_authorized_cmd", "Permission was refused by the system. {detail}", "სისტემამ ნებართვა უარყო. {detail}")


# ---- output filters (the Python equivalents of `| head`, `| sort`, `| grep`) ----
def head(n):
    return lambda text: "\n".join(text.splitlines()[:n])


def tail(n):
    return lambda text: "\n".join(text.splitlines()[-n:])


def grep(*needles, ignore_case=True, last=None):
    def f(text):
        lines = [ln for ln in text.splitlines() if any((n.lower() in ln.lower()) if ignore_case else (n in ln) for n in needles)]
        return "\n".join(lines[-last:] if last else lines)
    return f
