# DevOps Toolbox

Click-based, **allowlisted** DevOps operations — a desktop window and a local web page on the same backend. English / ქართული, light / dark.
ორენოვანი (EN / ქართული) ხელსაწყო: DevOps ოპერაციები ერთი დაჭერით, ბრძანების ხელით აკრეფის გარეშე.

```bash
devops-toolbox            # the window (after ./install.sh devops-toolbox, or: python3 devops-toolbox/devops-toolbox-gui.py)
devops-toolbox-web        # the local web page: prints an address with this run's access key, opens your browser; Ctrl+C stops it
```

It is **not** a terminal and has no command field: every operation is implemented in code (`devops_toolbox/modules/`), validates its
own inputs and builds an argument list for `subprocess` — never a shell string. You pick an operation, fill in the inputs, press
**Preview** (the exact command is shown), confirm, and only then does it run, with the real output and exit code shown afterwards.

## What it can do now: UFW Firewall Manager

| | |
|---|---|
| **UFW rules** | state (active / inactive), default policy, every configured rule (simple rules are listed; rules with source addresses, ranges or interfaces are shown but managed in a terminal) |
| **Open / block a port** | port (1–65535), TCP or UDP, Allow / Deny / Reject, optional description → `sudo ufw allow 19999/tcp` |
| **Delete a rule** | the form's *Delete rule*, or select a row → *Delete selected rule…* (its own confirmation) |

How UFW really behaves, and what the tool does about it:

* **`ufw reload` is not run.** `ufw allow 19999/tcp` takes effect immediately while the firewall is active; `reload` is only for hand edits of
  `/etc/ufw` files. A rule added while the firewall is inactive is stored and starts working when you enable it (the preview says so).
* **Duplicates and conflicts are caught** from the loaded rule list: the same rule (also when `53` already covers `53/udp`) is "nothing to do";
  a different action on the same port (allow vs deny) is refused until the old rule is deleted.
* **Deleting uses the rule's text** (`ufw --force delete allow 19999/tcp`), not a number: numbers shift after every deletion. UFW answers
  "Could not delete non-existent rule" with exit status 0, so the output is read as well, and a missing rule is reported as such.
* **The firewall is never switched off — or on — by this tool.** `ufw disable` does not exist in the code; `ufw enable` is left to you on
  purpose (allow SSH first, otherwise you can lock yourself out of an SSH session). Blocking port 22 — or the port of your current SSH session — and
  deleting an SSH allow rule are marked *high risk* with a warning.
* **Everything ufw does needs root, even listing** (`ufw status` refuses a normal user). So each operation runs
  `pkexec /usr/sbin/ufw …` — a system password dialog; the window itself never runs as root, there is no root-owned helper of ours, and
  the path of `ufw` is fixed to root-owned locations (not looked up in `PATH`). Depending on polkit settings you may be asked once per operation
  (a change plus the refresh that follows it). Without `pkexec` (package *polkit*) the tool says so and runs nothing.

## Security design

* **Allowlist only**: operations are declared in `registry.py`/`modules/`; a request can only name one of them. Unknown operations, unknown or
  missing parameters, a wrong type, and anything outside the allowed values are refused **in the backend**, whatever the interface checked.
* **No shell, ever**: argument lists, a timeout on every call (120 s for root operations: it includes the time you need for the password), a fixed
  minimal environment, stdin closed, output size limited. A test scans the package for `shell=True`, `os.system`, `eval`, `exec`.
* **Preview → confirm → execute**: a changing operation can only run with a single-use token that a preview issued for exactly those parameters
  (valid 5 minutes) *and* an explicit confirmation. Both the window and the web page go through the same `Toolbox.execute`.
* **Local web app** (`devops_toolbox/web.py`): listens on the loopback address only — there is no option to expose it to the network; a random
  per-run key (in the printed address, compared in constant time) is needed for the page and every API call; the `Host` header must be this
  loopback address and port (DNS-rebinding); POSTs also need an `Origin` of the page itself, `Content-Type: application/json` and a small body
  (CSRF); no CORS headers; a nonce-based Content-Security-Policy without `unsafe-inline`; no framing, no referrer, nothing cached; the page
  builds its DOM with `textContent` only. It still needs the pkexec dialog on your desktop for every privileged operation.
* **History** (`~/.local/state/linux-scripts/devops-toolbox/history.json`, mode 0600, newest 200): time, operation, status, exit code and a one-line
  summary. Never the command output, never the free-text description, never secrets. *Clear history* empties it.

## Dependencies

Python 3.8+ (standard library only for the backend and the web app), `tkinter` for the window (offered automatically on first run, like the other
tools), `ufw` (Debian/Ubuntu: `sudo apt install ufw`), `pkexec` (package *polkit*). Nothing else, no services, no background processes: the web
app runs only while you keep it open.

## Install / uninstall

```bash
./install.sh devops-toolbox              # commands devops-toolbox and devops-toolbox-web + menu entry (add --prefix ~/.local for no sudo)
./install.sh --uninstall devops-toolbox
```

## Adding a module later

A module is one file in `devops_toolbox/modules/`: it registers a `Category` and `Operation`s (id, Georgian/English names and descriptions as
`i18n.py` keys, parameters, risk level, whether it needs root, a `plan` function that validates and returns the argument lists, a `finish`
function that turns the program's output into a result). The window and the web page get the new operation through `Toolbox.catalog()`;
a category panel for it is the only UI work. Ideas that fit: services, network diagnostics, Docker listing, Git status, SSH inspection.

## Tests

```bash
python3 tests/test_devops_toolbox.py      # backend: validation, argument lists, injection attempts, duplicates, permission errors, timeouts, tokens, history, translations
python3 tests/test_devops_web.py          # the web app over real HTTP on a loopback port: key, Host/Origin/CSRF, CSP, routes, full cycle, start/stop
xvfb-run -a python3 tests/test_devops_window.py   # the Tk window under a virtual display
```

No test touches a real firewall: every program call goes through a fake runner that answers like ufw 0.36 (outputs copied from a real run).
**Not verified here:** the real `pkexec` password dialog and a real `ufw` on a live system (a rule opened and closed on the actual machine) — the first
real use should be a harmless test port such as `ufw allow 19999/tcp` followed by *Delete selected rule…*.
