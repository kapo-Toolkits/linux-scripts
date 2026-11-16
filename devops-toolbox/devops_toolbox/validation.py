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


# ---- more value kinds (used by the generic operations) ----
_IDENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}")                 # a service, container, user, database or jail name
_HOST_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_TEXT_MAX = 100


def identifier(value):
    """A name: letters, digits and _ . @ -, starting with a letter or digit (so it can never look like an option), at most 64."""
    if not isinstance(value, str) or not _IDENT_RE.fullmatch(value):
        raise ValidationError("err_identifier_invalid")
    return value


def ip_address(value):
    """An IPv4 or IPv6 address, normalised."""
    import ipaddress
    if not isinstance(value, str) or len(value) > 45 or not value.strip() == value:
        raise ValidationError("err_ip_invalid")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        raise ValidationError("err_ip_invalid") from None


def host(value):
    """A host name (labels of letters, digits and '-', dots between them) or an IP address; never starts with '-'."""
    if not isinstance(value, str) or not value or len(value) > 253 or value.strip() != value:
        raise ValidationError("err_host_invalid")
    try:
        return ip_address(value)
    except ValidationError:
        pass
    if not all(_HOST_LABEL.fullmatch(label) for label in value.rstrip(".").split(".")):
        raise ValidationError("err_host_invalid")
    return value


def integer(value, lo, hi):
    """A whole number lo..hi given as int or digit string (bool and floats are refused)."""
    if isinstance(value, bool) or isinstance(value, float):
        raise ValidationError("err_int_invalid", min=lo, max=hi)
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,9}", value):
        value = int(value)
    if not isinstance(value, int) or not lo <= value <= hi:
        raise ValidationError("err_int_invalid", min=lo, max=hi)
    return value


def ports(value, limit=10):
    """'22, 80,443' (or a list) -> [22, 80, 443]; each 1-65535, at most `limit`."""
    items = value if isinstance(value, list) else (value.split(",") if isinstance(value, str) else None)
    if not items or len(items) > limit:
        raise ValidationError("err_ports_invalid", limit=limit)
    return [port(str(x).strip()) for x in items]


def boolean(value):
    if not isinstance(value, bool):
        raise ValidationError("err_bool_invalid")
    return value


def text(value, maximum=_TEXT_MAX):
    """Free text for a value such as a git user name: printable, at most `maximum` characters, not starting with '-'."""
    if not isinstance(value, str):
        raise ValidationError("err_text_invalid", max=maximum)
    v = value.strip()
    if not v or len(v) > maximum or _CONTROL_RE.search(v) or v.startswith("-"):
        raise ValidationError("err_text_invalid", max=maximum)
    return v


def is_private_or_loopback(addr):
    """True for localhost, loopback and private-network addresses (where a self-signed certificate may be accepted)."""
    import ipaddress
    if addr in ("localhost",):
        return True
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


_IMAGE_RE = re.compile(r"[a-z0-9][a-z0-9_.-]*(?:[/:][A-Za-z0-9_.-]+){0,4}")
_USER_RE = re.compile(r"[a-z_][a-z0-9_-]{0,31}")


def image_ref(value):
    """A container image name such as hello-world, nginx:latest or ghcr.io/org/app:1.2 (no spaces, never starts with '-', no '..')."""
    if not isinstance(value, str) or not value or len(value) > 200 or ".." in value or not _IMAGE_RE.fullmatch(value):
        raise ValidationError("err_image_invalid")
    return value


def username(value):
    """A Linux user name: lower-case letters, digits, '_' and '-', at most 32, not starting with a digit or '-'."""
    if not isinstance(value, str) or not _USER_RE.fullmatch(value):
        raise ValidationError("err_username_invalid")
    return value
