"""Parameter validation. Runs in the backend for every request, whatever the user interface already checked.

Each validator returns the normalised value or raises ValidationError(key, **details): `key` is an i18n message key, so the
error reads the same (and is translated) in the window and in the web app."""
import re

PORT_MIN, PORT_MAX = 1, 65535
COMMENT_MAX = 80
_PORT_RE = re.compile(r"[0-9]{1,5}")                     # ASCII digits only (no '+', no spaces, no other scripts' digits)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f  ]")


class ValidationError(ValueError):
    def __init__(self, key, **details):
        super().__init__(key)
        self.key = key
        self.details = details


def port(value):
    """1-65535 as an int. Accepts an int or a string of digits; refuses bool, floats, signs, spaces, ranges, names."""
    if isinstance(value, bool) or isinstance(value, float):
        raise ValidationError("err_port_invalid", min=PORT_MIN, max=PORT_MAX)
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, str):
        text = value
    else:
        raise ValidationError("err_port_invalid", min=PORT_MIN, max=PORT_MAX)
    if not _PORT_RE.fullmatch(text):
        raise ValidationError("err_port_invalid", min=PORT_MIN, max=PORT_MAX)
    number = int(text)
    if not PORT_MIN <= number <= PORT_MAX:
        raise ValidationError("err_port_range", min=PORT_MIN, max=PORT_MAX)
    return number


def choice(value, allowed, key="err_choice"):
    """One of `allowed` (compared exactly, case-sensitive: the lists are lower-case words)."""
    if not isinstance(value, str) or value not in allowed:
        raise ValidationError(key, allowed=", ".join(allowed))
    return value


def comment(value):
    """Optional free text for a rule: '' when empty. At most 80 printable characters, no quotes, no backslash, no control
    characters, not starting with '-'. (It is passed as ONE argument to ufw, never through a shell; the limits keep the stored
    rule file and the rule list readable.)"""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValidationError("err_comment_invalid", max=COMMENT_MAX)
    text = value.strip()
    if not text:
        return ""
    if len(text) > COMMENT_MAX or _CONTROL_RE.search(text) or any(c in text for c in "'\"`\\") or text.startswith("-"):
        raise ValidationError("err_comment_invalid", max=COMMENT_MAX)
    return text
