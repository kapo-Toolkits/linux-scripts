"""The two remembered choices: language (the same file the other linux-scripts tools use, so the language follows you) and theme."""
import os

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "linux-scripts")
THEMES = ("light", "dark")


def _read(name):
    try:
        with open(os.path.join(CONFIG_DIR, name), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _write(name, value):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(os.path.join(CONFIG_DIR, name), "w", encoding="utf-8") as f:
            f.write(value)
    except OSError:
        pass


def load_lang():
    v = _read("lang")
    return v if v in ("en", "ka") else "en"


def save_lang(lang):
    if lang in ("en", "ka"):
        _write("lang", lang)


def load_theme():
    v = _read("devops-toolbox-theme")
    return v if v in THEMES else "light"


def save_theme(theme):
    if theme in THEMES:
        _write("devops-toolbox-theme", theme)
