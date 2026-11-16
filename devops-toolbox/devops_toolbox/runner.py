"""Running a program: argument lists only, a timeout, captured output, and privilege through pkexec for the one program that needs it.

The window / web app is never started as root. A root operation is `pkexec /absolute/path/to/program arg ...` - polkit shows its
own password dialog and runs just that program; this code has no root-owned helper of its own."""
import os
import subprocess
import time

MAX_OUTPUT = 20000
SAFE_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C"}
PKEXEC_REFUSED = (126, 127)          # pkexec: not authorised / the password dialog was dismissed


class RunResult:
    """What happened. `error` is an i18n key ('' when the program ran): the caller never sees a Python exception."""

    def __init__(self, argv, returncode=None, stdout="", stderr="", error="", timed_out=False, duration=0.0):
        self.argv = list(argv)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.error = error
        self.timed_out = timed_out
        self.duration = duration

    @property
    def ok(self):
        return self.returncode == 0 and not self.error and not self.timed_out


def _clip(text):
    text = text or ""
    return text if len(text) <= MAX_OUTPUT else text[:MAX_OUTPUT] + "\n[...]"


def run(argv, timeout=30, runner=subprocess.run, now=time.monotonic):
    """Run `argv` (a list of strings, never a shell string). Never raises."""
    if not isinstance(argv, (list, tuple)) or not argv or not all(isinstance(a, str) and "\x00" not in a for a in argv):
        raise TypeError("argv must be a non-empty list of strings")             # a bug in the caller, not a user error
    start = now()
    try:
        p = runner(list(argv), capture_output=True, text=True, timeout=timeout, shell=False, stdin=subprocess.DEVNULL,
                   env=dict(SAFE_ENV), errors="replace")
    except subprocess.TimeoutExpired as e:
        return RunResult(argv, stdout=_clip(_text(e.stdout)), stderr=_clip(_text(e.stderr)), error="err_timeout", timed_out=True,
                         duration=now() - start)
    except FileNotFoundError:
        return RunResult(argv, error="err_not_found", duration=now() - start)
    except PermissionError:
        return RunResult(argv, error="err_permission", duration=now() - start)
    except OSError as e:
        return RunResult(argv, error="err_os", stderr=str(e), duration=now() - start)
    return RunResult(argv, p.returncode, _clip(p.stdout), _clip(p.stderr), duration=now() - start)


def _text(x):
    if x is None:
        return ""
    return x.decode("utf-8", "replace") if isinstance(x, bytes) else x


def elevate(argv, euid=None, which=None, user=None):
    """-> (argv to run, '') or (None, i18n key): `pkexec` + argv, or argv itself when already root. With `user`, pkexec runs the
    program as that account (pkexec --user postgres ...), which never needs more than administrator permission."""
    if which is None:
        from shutil import which as _which
        which = _which
    euid = os.geteuid() if euid is None and hasattr(os, "geteuid") else (1 if euid is None else euid)
    if euid == 0 and not user:
        return list(argv), ""
    exe = which("pkexec")
    if not exe:
        return None, "err_no_pkexec"
    return [exe] + (["--user", user] if user else []) + list(argv), ""


def run_root(argv, timeout=120, runner=subprocess.run, euid=None, which=None, now=time.monotonic, user=None):
    """Run `argv` with administrator rights. A generous timeout: it includes the time the user needs for the password dialog."""
    full, err = elevate(argv, euid=euid, which=which, user=user)
    if full is None:
        return RunResult(argv, error=err)
    res = run(full, timeout=timeout, runner=runner, now=now)
    if res.returncode in PKEXEC_REFUSED and not res.error and euid != 0:
        res.error = "err_not_authorized"
    return res
