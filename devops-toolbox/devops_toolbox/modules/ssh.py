"""SSH (MyDevOps tasks 4 and 23): check the configuration, see the effective settings, inspect and repair the key folder, show a public
key, and read the failed / accepted logins. (Creating a key and ssh-copy-id are left to the terminal on purpose: they ask for a
passphrase or a password, which this tool must never handle.)"""
import os

from . import _dsl
from ._dsl import P, grep, op
from .. import i18n

C = "ssh"
_dsl.category(C, "SSH", "SSH")
KEY_OPTIONS = ("permitrootlogin", "passwordauthentication", "pubkeyauthentication", "x11forwarding", "maxauthtries", "port",
               "permitemptypasswords", "kbdinteractiveauthentication", "allowusers", "allowgroups")

i18n.add("ssh_folder_missing", "There is no ~/.ssh folder.", "~/.ssh საქაღალდე არ არსებობს.")
i18n.add("ssh_ok", "ok", "წესრიგშია")
i18n.add("ssh_fixed", "fixed", "გასწორდა")

op("ssh.test", C, ("Check the SSH configuration", "SSH-ის კონფიგურაციის შემოწმება"), ("Tests the sshd configuration files for mistakes before a restart (sshd -t); silence means OK.", "ამოწმებს sshd-ის კონფიგურაციას შეცდომებზე გადატვირთვამდე (sshd -t); სიჩუმე ნიშნავს რომ წესრიგშია."),
   argv=["@sshd", "-t"], root=True)


def _only_keys(text):
    return "\n".join(ln for ln in text.splitlines() if ln.split(" ", 1)[0].lower() in KEY_OPTIONS)


op("ssh.config", C, ("Effective SSH settings", "SSH-ის მოქმედი პარამეტრები"), ("The security-relevant settings sshd really uses: root login, passwords, keys, port ... (sshd -T, filtered).", "უსაფრთხოებასთან დაკავშირებული პარამეტრები, რომლებსაც sshd რეალურად იყენებს: root-ით შესვლა, პაროლები, გასაღებები, პორტი ... (sshd -T, გაფილტრული)."),
   argv=["@sshd", "-T"], root=True, post=_only_keys)


def _config_file(ctx, p):
    out = []
    files = ["/etc/ssh/sshd_config"] + ["/etc/ssh/sshd_config.d/" + f for f in ctx.sysx.listdir("/etc/ssh/sshd_config.d") if f.endswith(".conf")]
    for path in files:
        text = ctx.sysx.read_text(path)
        if text is None:
            continue
        for ln in text.splitlines():
            first = ln.strip().split(" ", 1)[0].lower()
            if first in KEY_OPTIONS:
                out.append("%s: %s" % (os.path.basename(path), ln.strip()))
    return "\n".join(out) or "-"


op("ssh.config.file", C, ("SSH settings in the files", "SSH-ის პარამეტრები ფაილებში"), ("What /etc/ssh/sshd_config and sshd_config.d/*.conf say about the important options (read-only, no administrator rights).", "რას ამბობს /etc/ssh/sshd_config და sshd_config.d/*.conf მნიშვნელოვან პარამეტრებზე (მხოლოდ კითხვა)."),
   native=_config_file)


def _keys_report(ctx, p):
    ssh = os.path.join(ctx.sysx.home, ".ssh")
    if not ctx.sysx.isdir(ssh):
        return i18n.t("en", "ssh_folder_missing")
    lines = []
    want = {ssh: 0o700}
    for f in ctx.sysx.listdir(ssh):
        path = os.path.join(ssh, f)
        if f.endswith(".pub") or f in ("known_hosts", "config"):
            want[path] = 0o644 if f.endswith(".pub") or f == "known_hosts" else 0o600
        elif f == "authorized_keys" or f.startswith("id_") or ctx.sysx.isfile(path):
            want[path] = 0o600
    for path, expected in sorted(want.items()):
        mode = ctx.sysx.stat_mode(path)
        if mode is None:
            continue
        loose = mode & ~expected & 0o777
        lines.append("%s  %s  %s" % (oct(mode)[2:].rjust(4, "0"), path.replace(ctx.sysx.home, "~"),
                                     "ok" if not loose else "too open (should be %s)" % oct(expected)[2:]))
    return "\n".join(lines) or "-"


op("ssh.keys", C, ("Check the SSH key folder", "SSH გასაღებების საქაღალდის შემოწმება"), ("Lists ~/.ssh with each file's permissions and says which are too open (private keys 600, folder 700).", "აჩვენებს ~/.ssh-ს ფაილების უფლებებით და ამბობს, რომელია ზედმეტად ღია (პირადი გასაღებები 600, საქაღალდე 700)."),
   native=_keys_report)


def _fix_perms(ctx, p):
    ssh = os.path.join(ctx.sysx.home, ".ssh")
    if not ctx.sysx.isdir(ssh):
        return i18n.t("en", "ssh_folder_missing")
    lines = []
    plan = [(ssh, 0o700)]
    for f in ctx.sysx.listdir(ssh):
        path = os.path.join(ssh, f)
        if ctx.sysx.islink(path) or not ctx.sysx.isfile(path):
            continue                                         # never follow or change a link or a folder inside
        plan.append((path, 0o644 if f.endswith(".pub") or f == "known_hosts" else 0o600))
    for path, mode in plan:
        have = ctx.sysx.stat_mode(path)
        if have is not None and have != mode:
            ctx.sysx.chmod(path, mode)
            lines.append("%s -> %s %s" % (path.replace(ctx.sysx.home, "~"), oct(mode)[2:], i18n.t("en", "ssh_fixed")))
    return "\n".join(lines) or i18n.t("en", "ssh_ok")


op("ssh.perms.fix", C, ("Repair SSH key permissions", "SSH გასაღებების უფლებების გასწორება"), ("Sets ~/.ssh to 700, private keys and authorized_keys to 600, public keys to 644 (chmod). Links are never followed.", "~/.ssh-ს ადგენს 700-ზე, პირად გასაღებებსა და authorized_keys-ს 600-ზე, საჯაროებს 644-ზე (chmod). ბმულებს არ მიჰყვება."),
   native=_fix_perms, risk="medium")


@_dsl.dynamic("ssh_pub_keys")
def _pub_keys(ctx):
    return [f for f in ctx.sysx.listdir(os.path.join(ctx.sysx.home, ".ssh")) if f.endswith(".pub")]


op("ssh.pubkey", C, ("Show a public key", "საჯარო გასაღების ჩვენება"), ("The fingerprint of one of your public keys (ssh-keygen -lf), to compare with what a server or GitHub shows.", "თქვენი საჯარო გასაღების ანაბეჭდი (ssh-keygen -lf) სერვერზე ან GitHub-ზე ნაჩვენებთან შესადარებლად."),
   build=lambda ctx, p: [["ssh-keygen", "-lf", os.path.join(ctx.sysx.home, ".ssh", p["file"])]],
   params=[P("file", choices=(), dynamic="ssh_pub_keys")])
op("ssh.log.failed", C, ("Failed SSH logins", "წარუმატებელი SSH შესვლები"), ("The last 50 failed, invalid or denied login lines of the SSH service (journalctl -u ssh, filtered).", "SSH სერვისის ბოლო 50 წარუმატებელი, არასწორი ან უარყოფილი შესვლის ხაზი (journalctl -u ssh, გაფილტრული)."),
   argv=["@journalctl", "-u", "{unit}", "--no-pager", "-n", "2000"], params=[P("unit", choices=("ssh", "sshd"), default="ssh")], root=True,
   post=grep("fail", "invalid", "denied", last=50))
op("ssh.log.accepted", C, ("Accepted SSH logins", "მიღებული SSH შესვლები"), ("The last 20 successful logins (journalctl -u ssh, filtered).", "ბოლო 20 წარმატებული შესვლა (journalctl -u ssh, გაფილტრული)."),
   argv=["@journalctl", "-u", "{unit}", "--no-pager", "-n", "2000"], params=[P("unit", choices=("ssh", "sshd"), default="ssh")], root=True,
   post=grep("Accepted", last=20))
