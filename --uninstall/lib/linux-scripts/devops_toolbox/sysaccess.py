"""Everything an operation needs to LOOK at on this computer, behind one small object, so tests can replace it and no operation
reaches into the system on its own: which programs exist and where, folder listings, small text files, the user's home."""
import os
import pwd

USER_DIRS = ("/usr/local/bin", "/usr/bin", "/bin", "/snap/bin")
ROOT_DIRS = ("/usr/sbin", "/usr/bin", "/sbin", "/bin")        # a program run as root is only taken from root-owned places
MAX_READ = 1024 * 1024


class SysAccess:
    def __init__(self, home=None, environ=None):
        self.home = home or os.path.expanduser("~")
        self.environ = environ if environ is not None else os.environ

    def find_program(self, name, root=False):
        """Absolute path of `name` in the fixed program folders (never looked up through PATH), or None."""
        if not name or "/" in name:
            return None
        for d in (ROOT_DIRS if root else USER_DIRS + ROOT_DIRS):
            p = os.path.join(d, name)
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
        return None

    def listdir(self, path):
        try:
            return sorted(os.listdir(path))
        except OSError:
            return []

    def isfile(self, path):
        return os.path.isfile(path)

    def isdir(self, path):
        return os.path.isdir(path)

    def islink(self, path):
        return os.path.islink(path)

    def exists(self, path):
        return os.path.lexists(path)

    def read_text(self, path, limit=MAX_READ):
        """The text of a (small) file, or None when it cannot be read."""
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read(limit)
        except OSError:
            return None

    def file_size(self, path):
        try:
            return os.lstat(path).st_size
        except OSError:
            return 0

    def stat_mode(self, path):
        try:
            return os.stat(path, follow_symlinks=False).st_mode & 0o7777
        except OSError:
            return None

    def username(self):
        try:
            return pwd.getpwuid(os.getuid()).pw_name
        except KeyError:
            return ""

    def users(self):
        """[(name, uid, shell)] from the password database."""
        return [(p.pw_name, p.pw_uid, p.pw_shell) for p in pwd.getpwall()]

    def chmod(self, path, mode):
        os.chmod(path, mode, follow_symlinks=False) if os.chmod in os.supports_follow_symlinks else os.chmod(path, mode)

    def remove(self, path):
        os.remove(path)

    def mkdir_private(self, path):
        os.makedirs(path, mode=0o700, exist_ok=True)

    def file_age_days(self, path, now):
        try:
            return (now - os.lstat(path).st_mtime) / 86400.0
        except OSError:
            return 0.0

    def rlimit_nofile(self):
        try:
            import resource
            return resource.getrlimit(resource.RLIMIT_NOFILE)
        except (ImportError, OSError, ValueError):
            return None

    def config(self):
        """The user's own list of repositories and compose projects (a file they edit); {} when absent or damaged."""
        import json
        base = self.environ.get("XDG_CONFIG_HOME") or os.path.join(self.home, ".config")
        text = self.read_text(os.path.join(base, "linux-scripts", "devops-toolbox.json"))
        try:
            data = json.loads(text) if text else {}
        except ValueError:
            data = {}
        return data if isinstance(data, dict) else {}
