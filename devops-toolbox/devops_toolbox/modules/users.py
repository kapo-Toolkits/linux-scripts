"""Users and permissions (MyDevOps tasks 6 and 23): who can log in, who has sudo, the sudoers rules, the root account state, logins, creating a
user (without a password: set it in a terminal) and adding / removing a user in the sudo or docker group."""
from . import _dsl
from ._dsl import P, op
from .. import i18n

C = "users"
_dsl.category(C, "Users and permissions", "მომხმარებლები და უფლებები")
i18n.add("blocked_user_exists", "A user with this name already exists.", "ამ სახელის მომხმარებელი უკვე არსებობს.")
i18n.add("blocked_user_unknown", "No such regular user on this computer.", "ასეთი ჩვეულებრივი მომხმარებელი ამ კომპიუტერზე არ არის.")
i18n.add("warn_group_sudo", "Members of 'sudo' can do anything on this computer.", "'sudo'-ს წევრებს ამ კომპიუტერზე ყველაფრის გაკეთება შეუძლიათ.")
i18n.add("warn_group_docker", "Members of 'docker' are effectively administrators: they can start containers that read or change any file.",
         "'docker'-ის წევრები ფაქტობრივად ადმინისტრატორები არიან: მათ შეუძლიათ კონტეინერის გაშვება, რომელიც ნებისმიერ ფაილს კითხულობს ან ცვლის.")
i18n.add("explain_set_password", "No password is set: do it yourself in a terminal (sudo passwd NAME) - this tool never handles passwords.",
         "პაროლი არ დაყენდება: თავად დააყენეთ ტერმინალიდან (sudo passwd NAME) - ეს ხელსაწყო პაროლებს არასოდეს ეხება.")


def _regular(ctx):
    return [(n, uid, sh) for n, uid, sh in ctx.sysx.users() if 1000 <= uid < 65534]


def _list(ctx, p):
    rows = ["%-20s uid=%-6d %s" % (n, uid, sh) for n, uid, sh in _regular(ctx) if not sh.endswith(("nologin", "false"))]
    return "\n".join(rows) or "-"


op("usr.list", C, ("Users who can log in", "მომხმარებლები, რომლებსაც შესვლა შეუძლიათ"), ("Regular accounts (UID 1000 and up) that have a login shell.", "ჩვეულებრივი ანგარიშები (UID 1000-დან), რომლებსაც აქვთ login shell."), native=_list)
op("usr.me", C, ("Who am I?", "ვინ ვარ მე?"), ("Your user, id and groups (id).", "თქვენი მომხმარებელი, id და ჯგუფები (id)."), argv=["@id"])
op("usr.sudo", C, ("Members of the sudo group", "sudo ჯგუფის წევრები"), ("Who may use sudo (getent group sudo).", "ვის შეუძლია sudo-ს გამოყენება (getent group sudo)."), argv=["@getent", "group", "sudo"], ok_codes=(0, 2))
op("usr.sudoers", C, ("The sudoers rules", "sudoers-ის წესები"), ("The active lines of /etc/sudoers and /etc/sudoers.d (comments removed); needs administrator rights.", "/etc/sudoers-ისა და /etc/sudoers.d-ს აქტიური ხაზები (კომენტარების გარეშე); საჭიროა ადმინისტრატორის უფლება."),
   argv=["@grep", "-rvE", r"^\s*(#|$)", "/etc/sudoers", "/etc/sudoers.d/"], root=True)
op("usr.root", C, ("Root account state", "root ანგარიშის მდგომარეობა"), ("Whether root has a usable password: L = locked (good), P = has one (passwd -S root).", "აქვს თუ არა root-ს გამოსადეგი პაროლი: L = დაბლოკილია (კარგია), P = აქვს (passwd -S root)."),
   argv=["@passwd", "-S", "root"], root=True)
op("usr.last", C, ("Recent logins", "ბოლო შესვლები"), ("The last logins (last -n N).", "ბოლო შესვლები (last -n N)."), argv=["@last", "-n", "{lines}"], params=[P("lines", lo=5, hi=100, default=10)])
op("usr.lastb", C, ("Failed login attempts", "წარუმატებელი შესვლის მცდელობები"), ("The last failed logins (lastb -n N); needs administrator rights.", "ბოლო წარუმატებელი შესვლები (lastb -n N); საჭიროა ადმინისტრატორის უფლება."),
   argv=["@lastb", "-n", "{lines}"], params=[P("lines", lo=5, hi=100, default=20)], root=True)


def _exists(ctx, name):
    return any(n == name for n, _u, _s in ctx.sysx.users())


op("usr.add", C, ("Create a user", "მომხმარებლის შექმნა"), ("Creates an account without a password (adduser --disabled-password).", "ქმნის ანგარიშს პაროლის გარეშე (adduser --disabled-password)."),
   build=lambda ctx, p: [["adduser", "--disabled-password", "--gecos", "", p["username"]]], params=[P("username", "username")], root=True, risk="medium",
   check=lambda ctx, p: ("blocked_user_exists", {}) if _exists(ctx, p["username"]) else None, explain=[("explain_set_password", {})])


def _member_check(ctx, p):
    return None if any(n == p["username"] for n, _u, _s in _regular(ctx)) else ("blocked_user_unknown", {})


def _group_warn(ctx, p):
    return [({"sudo": "warn_group_sudo", "docker": "warn_group_docker"}[p["group"]], {})]


op("usr.group.add", C, ("Add a user to a group", "მომხმარებლის ჯგუფში დამატება"), ("Gives a user the rights of the sudo or docker group (usermod -aG).", "მომხმარებელს sudo-ს ან docker-ის ჯგუფის უფლებებს აძლევს (usermod -aG)."),
   build=lambda ctx, p: [["usermod", "-aG", p["group"], p["username"]]], params=[P("username", "username"), P("group", "choice", choices=("sudo", "docker"), default="docker")],
   root=True, risk="high", check=_member_check, warn=_group_warn)
op("usr.group.remove", C, ("Remove a user from a group", "მომხმარებლის ჯგუფიდან ამოღება"), ("Takes the sudo or docker group's rights away from a user (gpasswd -d).", "მომხმარებელს sudo-ს ან docker-ის ჯგუფის უფლებებს ართმევს (gpasswd -d)."),
   build=lambda ctx, p: [["gpasswd", "-d", p["username"], p["group"]]], params=[P("username", "username"), P("group", "choice", choices=("sudo", "docker"), default="docker")],
   root=True, risk="high", check=_member_check)
