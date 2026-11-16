"""Where an operation runs: on this computer, or on another one over SSH.

A Target gives an operation everything it needs about "the computer it acts on": the system it may look at (`sysx`: programs, folders, small
files) and a way to run an argument list. Operations never know which one they got, so the same 146 allowlisted operations work on both -
there is still no way to type a command.

SSH rules (it is a remote administrative channel, so it is strict):
  * keys only: BatchMode, passwords and keyboard prompts are switched off; this tool never handles a password;
  * StrictHostKeyChecking=yes always: an unknown host is refused until you have SEEN its fingerprint and confirmed it (hostkey_* in api.py);
    a changed key is refused, never replaced;
  * the host, port, user and key are validated; the key can only be one of your own ~/.ssh private keys;
  * nothing is forwarded (no agent, X11 or ports), the configuration file is not read (-F /dev/null), the connection has timeouts;
  * the remote command is `env -i PATH=<fixed folders> program args...` with every word quoted, and root operations use `sudo -n`
    (no password prompt: a user without passwordless sudo gets a clear message) - or you connect as root."""
import os
import re
import shlex
import shutil
import subprocess
import tempfile

from . import runner
from .sysaccess import ROOT_DIRS, USER_DIRS, SysAccess

SSH_DIRS = ("/usr/bin", "/bin", "/usr/local/bin")
ROOT_PATH = ":".join(ROOT_DIRS)
USER_PATH = ":".join(USER_DIRS + ROOT_DIRS)
KEY_TYPES = ("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521", "sk-ssh-ed25519@openssh.com",
             "sk-ecdsa-sha2-nistp256@openssh.com")
_B64 = re.compile(r"[A-Za-z0-9+/]+={0,3}")

# ssh / sudo messages -> i18n keys (first match wins)
SSH_ERRORS = (
    ("remote host identification has changed", "err_ssh_hostkey_changed"),
    ("host key verification failed", "err_ssh_hostkey_unknown"),
    ("permission denied (publickey", "err_ssh_auth"),
    ("permission denied, please try again", "err_ssh_auth"),
    ("no more authentication methods", "err_ssh_auth"),
    ("connection refused", "err_ssh_refused"),
    ("connection timed out", "err_ssh_unreachable"),
    ("no route to host", "err_ssh_unreachable"),
    ("network is unreachable", "err_ssh_unreachable"),
    ("could not resolve hostname", "err_ssh_resolve"),
    ("name or service not known", "err_ssh_resolve"),
    ("connection closed", "err_ssh_closed"),
    ("connection reset", "err_ssh_closed"),
)


class LocalTarget:
    """This computer: programs run directly (administrator rights through pkexec), the system is read directly."""
    kind = "local"
    host = port = user = identity = None
    label = "this computer"
    key = ("local",)

    def __init__(self, sysx=None):
        self.sysx = sysx or SysAccess()

    def close(self):
        pass


class RemoteTarget:
    """Another computer, reached with the system's ssh client."""
    kind = "remote"

    def __init__(self, host, port, user, identity=None, runner_fn=subprocess.run, find_ssh=None, home=None, environ=None):
        self.host, self.port, self.user, self.identity = host, int(port), user, identity
        self._run, self.environ = runner_fn, environ if environ is not None else os.environ
        self.local_home = home or os.path.expanduser("~")
        self._find_ssh = find_ssh or (lambda: next((os.path.join(d, "ssh") for d in SSH_DIRS if os.access(os.path.join(d, "ssh"), os.X_OK)), None))
        self.control_dir = None
        self.sysx = RemoteSys(self)

    @property
    def label(self):
        return "%s@%s:%d" % (self.user, self.host, self.port)

    @property
    def key(self):
        return ("remote", self.host, self.port, self.user, self.identity or "")

    @property
    def is_root(self):
        return self.user == "root"

    # ---- the ssh command line
    def ssh_argv(self, remote_command):
        ssh = self._find_ssh()
        if not ssh:
            return None
        argv = [ssh, "-F", "/dev/null", "-p", str(self.port), "-l", self.user,
                "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + os.path.join(self.local_home, ".ssh", "known_hosts"),
                "-o", "PasswordAuthentication=no",
                "-o", "KbdInteractiveAuthentication=no", "-o", "PreferredAuthentications=publickey",
                "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
                "-o", "ForwardAgent=no", "-o", "ForwardX11=no", "-o", "ClearAllForwardings=yes",
                "-o", "ControlMaster=auto", "-o", "ControlPersist=60", "-o", "ControlPath=" + self._control_path()]
        if self.identity:
            argv += ["-i", os.path.join(self.local_home, ".ssh", self.identity), "-o", "IdentitiesOnly=yes"]
        return argv + ["--", self.host, remote_command]

    def _control_path(self):
        if self.control_dir is None:
            self.control_dir = tempfile.mkdtemp(prefix="dtb-")             # 0700, short path: a unix socket path is limited in length
        return os.path.join(self.control_dir, "%C")

    @staticmethod
    def remote_command(argv, root=False, as_user=None, is_root=False, home=None):
        """The one string sent to the remote shell: every word quoted, a fixed environment, `sudo -n` for administrator operations."""
        words = []
        if as_user or (root and not is_root):
            words += ["/usr/bin/sudo", "-n"] + (["-u", as_user] if as_user else [])
        env = ["PATH=" + (ROOT_PATH if root or as_user else USER_PATH), "LC_ALL=C"]
        if not root and not as_user and home:
            env.append("HOME=" + home)
        words += ["/usr/bin/env", "-i"] + env + list(argv)
        return shlex.join(words)

    def run(self, argv, root=False, as_user=None, timeout=60):
        """Run `argv` on the remote computer -> RunResult (ssh and sudo problems become i18n error keys)."""
        full = self.ssh_argv(self.remote_command(argv, root, as_user, self.is_root, self.sysx.known_home if not root else None))
        if full is None:
            return runner.RunResult(argv, error="err_no_ssh")
        env = {k: self.environ[k] for k in ("SSH_AUTH_SOCK", "HOME") if k in self.environ}
        res = runner.run(full, timeout=timeout, runner=self._run, extra_env=env)
        return self._map_errors(res, argv)

    def lookup(self, argv, root):
        """Like run(), but with the PATH of the root-owned folders (or the user's) and no sudo: used to find where a program is."""
        cmd = self.remote_command(argv, root=False, as_user=None, is_root=self.is_root, home=None)
        if root:
            cmd = cmd.replace("PATH=" + USER_PATH, "PATH=" + ROOT_PATH, 1)
        full = self.ssh_argv(cmd)
        if full is None:
            return runner.RunResult(argv, error="err_no_ssh")
        env = {k: self.environ[k] for k in ("SSH_AUTH_SOCK", "HOME") if k in self.environ}
        return self._map_errors(runner.run(full, timeout=20, runner=self._run, extra_env=env), argv)

    def exec(self, argv, timeout=20):
        """A harmless look-around command for the system object (test, ls, stat, cat ...), as the remote user."""
        return self.run(argv, root=False, timeout=timeout)

    def _map_errors(self, res, argv):
        res.argv = list(argv)
        if res.error or res.timed_out:
            return res
        low = (res.stderr or "").lower()
        if res.returncode == 255:
            for needle, key in SSH_ERRORS:
                if needle in low:
                    res.error = "err_ssh_hostkey_changed" if key == "err_ssh_hostkey_unknown" and self._has_known_entry() else key
                    return res
            res.error = "err_ssh_failed"
        elif "a password is required" in low or "no tty present" in low or "sudo: a terminal is required" in low:
            res.error = "err_sudo_password"
        return res

    def _has_known_entry(self):
        """True when ~/.ssh/known_hosts already has a key for this host: then a failed verification means the key CHANGED (not 'unknown').
        Some ssh versions print only 'Host key verification failed.' in both cases, so the file is asked directly."""
        keygen = next((os.path.join(d, "ssh-keygen") for d in SSH_DIRS if os.access(os.path.join(d, "ssh-keygen"), os.X_OK)), None)
        if not keygen:
            return False
        name = self.host if self.port == 22 else "[%s]:%d" % (self.host, self.port)
        try:
            r = self._run([keygen, "-F", name, "-f", os.path.join(self.local_home, ".ssh", "known_hosts")], capture_output=True, text=True, timeout=10,
                          shell=False, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            return False
        return r.returncode == 0 and bool((r.stdout or "").strip())

    def close(self):
        """End the shared connection and remove its socket folder."""
        ssh = self._find_ssh()
        if ssh and self.control_dir:
            try:
                self._run([ssh, "-F", "/dev/null", "-o", "ControlPath=" + os.path.join(self.control_dir, "%C"), "-O", "exit", "--", self.host],
                          capture_output=True, timeout=5, shell=False, stdin=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError):
                pass
        if self.control_dir:
            shutil.rmtree(self.control_dir, ignore_errors=True)
            self.control_dir = None


CONNECTION_ERRORS = ("err_ssh_hostkey_changed", "err_ssh_hostkey_unknown", "err_ssh_auth", "err_ssh_refused", "err_ssh_unreachable", "err_ssh_resolve",
                     "err_ssh_closed", "err_ssh_failed", "err_no_ssh", "err_timeout")


class RemoteSys:
    """The remote computer as the operations may look at it: the same questions as sysaccess.SysAccess, answered with small remote commands.
    Whatever the remote side answers is checked here (an absolute path in a fixed folder, a number ...) before it is used."""

    def __init__(self, target):
        self.t = target
        self.last_error = ""                                  # the i18n key of the latest connection problem ('' when the last call connected)
        self._home = None
        self._cache = {}
        self.environ = {}

    # -- plumbing
    def _note(self, res):
        self.last_error = res.error if res.error in CONNECTION_ERRORS else ""
        return res

    def _ok(self, *argv):
        return self._note(self.t.exec(list(argv))).returncode == 0

    def _out(self, *argv):
        r = self._note(self.t.exec(list(argv)))
        return (r.stdout or "") if r.ok else None

    @property
    def known_home(self):
        """The home folder if it is already known (never asks: used while building a command, so it cannot recurse)."""
        return self._home

    @property
    def home(self):
        if self._home is None:
            out = self._out("getent", "passwd", self.t.user) or ""
            fields = out.strip().split(":")
            home = fields[5] if len(fields) >= 6 else ""
            self._home = home if home.startswith("/") and "\n" not in home and ".." not in home.split("/") else "/home/" + self.t.user
        return self._home

    # -- the SysAccess interface
    def find_program(self, name, root=False):
        if not name or "/" in name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", name):
            return None
        key = ("prog", name, root)
        if key not in self._cache:
            r = self._note(self.t.lookup(["/bin/sh", "-c", 'command -v -- "$1"', "sh", name], root))
            path = (r.stdout or "").strip().splitlines()[0] if r.ok and (r.stdout or "").strip() else None
            allowed = ROOT_DIRS if root else USER_DIRS + ROOT_DIRS
            found = path if path and path.startswith(tuple(d + "/" for d in allowed)) and " " not in path else None
            if r.error:                                       # a connection problem is not "program not found": do not remember it
                return None
            self._cache[key] = found
        return self._cache[key]

    def listdir(self, path):
        out = self._out("ls", "-1", "-A", "--", path)
        return sorted(x for x in (out or "").splitlines() if x and "\x00" not in x)

    def isfile(self, path):
        return self._ok("test", "-f", path)

    def isdir(self, path):
        return self._ok("test", "-d", path)

    def islink(self, path):
        return self._ok("test", "-L", path)

    def exists(self, path):
        return self._ok("test", "-e", path) or self._ok("test", "-L", path)

    def read_text(self, path, limit=1024 * 1024):
        r = self._note(self.t.exec(["head", "-c", str(int(limit)), "--", path]))
        return r.stdout if r.ok else None

    def stat_mode(self, path):
        out = self._out("stat", "-c", "%a", "--", path)
        try:
            return int((out or "").strip(), 8)
        except ValueError:
            return None

    def file_size(self, path):
        try:
            return int((self._out("stat", "-c", "%s", "--", path) or "0").strip())
        except ValueError:
            return 0

    def username(self):
        return self.t.user

    def users(self):
        rows = []
        for line in (self._out("getent", "passwd") or "").splitlines():
            f = line.split(":")
            if len(f) >= 7 and f[2].isdigit():
                rows.append((f[0], int(f[2]), f[6]))
        return rows

    def chmod(self, path, mode):
        r = self.t.exec(["chmod", "%o" % mode, "--", path])
        if not r.ok:
            raise OSError((r.stderr or "chmod failed").strip()[:200])

    def remove(self, path):
        r = self.t.exec(["rm", "--", path])
        if not r.ok:
            raise OSError((r.stderr or "rm failed").strip()[:200])

    def file_age_days(self, path, now):
        mtime, remote_now = self._out("stat", "-c", "%Y", "--", path), self._out("date", "+%s")
        try:
            return (int(remote_now.strip()) - int(mtime.strip())) / 86400.0      # the remote clock against the remote file
        except (ValueError, AttributeError):
            return 0.0

    def rlimit_nofile(self):
        return None

    def config(self):
        import json
        text = self.read_text(self.home + "/.config/linux-scripts/devops-toolbox.json")
        try:
            data = json.loads(text) if text else {}
        except ValueError:
            data = {}
        return data if isinstance(data, dict) else {}


# ---- known_hosts: show a host's fingerprints, and trust them only after you confirmed them ----
def parse_scan(text):
    """ssh-keyscan output -> [(host field, key type, base64 key)] for well-formed lines only."""
    out = []
    for line in (text or "").splitlines():
        parts = line.strip().split(" ")
        if len(parts) == 3 and parts[1] in KEY_TYPES and _B64.fullmatch(parts[2]) and "," not in parts[0] and not parts[0].startswith(("#", "|")):
            out.append(tuple(parts))
    return out
