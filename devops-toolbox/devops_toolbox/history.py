"""Execution history: what was done, when, with which result. Small and private (mode 0600) - and it never keeps command output,
passwords, tokens or the free-text rule descriptions: only the operation, the validated parameters that are not free text, the
exit code and a one-line summary chosen by the operation."""
import json
import os
import tempfile
import time

MAX_ENTRIES = 200
SUMMARY_MAX = 120


def default_path():
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "linux-scripts", "devops-toolbox", "history.json")


class History:
    def __init__(self, path=None, now=time.time):
        self.path = path or default_path()
        self.now = now

    def entries(self):
        """Newest first. A missing or damaged file is an empty history, never an error."""
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        items = data if isinstance(data, list) else []
        return [e for e in reversed(items) if isinstance(e, dict)]

    def add(self, op_id, status, exit_code, summary, params=None, target=""):
        """status: 'ok' | 'failed' | 'refused'. params: only values that are safe to keep (ports, protocols, actions)."""
        entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.now())), "op": op_id, "status": status,
                 "exit_code": exit_code, "summary": " ".join(str(summary or "").split())[:SUMMARY_MAX],
                 "params": {k: v for k, v in (params or {}).items() if isinstance(v, (int, str)) and k != "comment"}}
        if target:
            entry["target"] = str(target)[:120]                      # user@host:port of a remote computer (not a secret)
        items = list(reversed(self.entries()))
        items.append(entry)
        self._write(items[-MAX_ENTRIES:])
        return entry

    def clear(self):
        self._write([])

    def _write(self, items):
        folder = os.path.dirname(self.path)
        try:
            os.makedirs(folder, mode=0o700, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=folder, prefix=".history-")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=1)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except OSError:
            pass                                     # a history that cannot be written must not break the operation itself
