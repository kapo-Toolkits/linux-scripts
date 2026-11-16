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

## What it can do now: 146 operations in 14 themes

Everything below comes from the commands in the MyDevOps notes (<https://ezdanapak.github.io/MyDevOps/>), sorted by theme. The sidebar lists the
themes; each shows its operations, builds a form from the chosen operation's inputs, and works the same way: **Preview** shows the exact command and
the risk, a reading operation has a **Run** button, a changing one needs the preview and then a confirmation (a stronger one for *high* risk).
102 operations only read, 8 are low, 26 medium and 10 high risk; 58 need administrator rights (through `pkexec`, only for that command).

| Theme | Operations (examples from the notes) |
|---|---|
| **Network** (23) | addresses, links, routes, DNS, ping, listening ports (with and without programs), connections, socket summary, *who uses port N*, port reachability (`nc`), HTTP check (`curl -I`), `lsof`, `netstat`, `whois`, secure and apply netplan, Tailscale status / address |
| **Firewall (UFW)** (7) | the **UFW manager** (rules table, open / block / delete a port) plus status verbose / numbered, application profiles (`allow 'Nginx Full'`), default policy |
| **SSH** (8) | test the configuration (`sshd -t`), effective settings, settings in the files, check and repair `~/.ssh` permissions, public key fingerprint, failed and accepted logins |
| **Services** (8) | status, enabled?, logs, running / failed units, key services overview, boot time (`systemd-analyze blame`), start / stop / restart / reload / enable / disable for the listed services |
| **Web server and certificates** (7) | `nginx -t`, `server_name` lines, enabled sites, enable / disable a site, show a certificate, create a self-signed one |
| **Docker** (19) | versions, containers, images, stats, disk use, logs, restart, test run, remove an image, prune; **Compose** for your own projects: status, logs, start, pull, restart, stop, rebuild, stop and delete volumes |
| **Git** (11) | identity, and for your configured repositories: status, log, branches, remotes, diff summary, head, files, fetch, `pull --ff-only` |
| **Users and permissions** (10) | who can log in, who has sudo, sudoers rules, root account state, recent / failed logins, create a user, add or remove a user in the `sudo` / `docker` group |
| **Updates and packages** (11) | refresh, what can be upgraded, upgrade, install one of the listed packages, installed?, reboot needed?, autoremove (dry run first), clean, reboot |
| **Disk and logs** (10) | free space and inodes, biggest folders and files, old logs (list first, then delete), journal size and vacuum, logrotate dry run |
| **Monitoring and performance** (14) | uptime, memory, CPUs, busiest processes, disk I/O, limits, swappiness (read / set), time zone (show / set), time synchronisation, system information |
| **Security audit** (7) | Fail2Ban status / jail / unban, who failed to log in (counted), recent sudo commands, updates waiting, automatic updates |
| **Database** (5) | databases, version, a few settings, roles (as the `postgres` account), backup with `pg_dump` |
| **Backup and cron** (6) | your crontab, back up the web files, list backups, check the newest, delete old backups (list first) |

**Where every documented command went** is written down in `devops_toolbox/coverage.py`, and a test checks it: each command of the notes maps to real
operations, each operation is justified by a documented command (or declared as an extra), and the commands that were **left to the terminal on purpose**
are listed with the reason — editing config files with `nano`, creating SSH keys and `ssh-copy-id` (passphrases and passwords), `scp`, interactive tools (`htop`,
`glances`), `git commit` / `push` / `reset --hard`, `curl | sh` installers, restoring databases from arbitrary files, passwords of any kind.

### Your own repositories and Compose projects

The folder of a repository or Compose project is never typed into the tool: you list it once in `~/.config/linux-scripts/devops-toolbox.json`, and the
operations offer those names:

```json
{"repos":    [{"name": "mgawm",      "path": "/var/www/mgawm"}],
 "projects": [{"name": "docker-app", "path": "/home/k/docker-app"}]}
```

A name is letters, digits and `._@-`; a path must be absolute, without `..`, and an existing folder; anything else in the file is ignored.

### UFW Firewall Manager

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
  purpose (allow SSH first, otherwise you can lock yourself out of an SSH session). Blocking port 22 — or the port of your current SSH session —,
  deleting an SSH allow rule and `default deny incoming` without an SSH rule are marked *high risk* with a warning.
* **Everything ufw does needs root, even listing** (`ufw status` refuses a normal user). So each operation runs
  `pkexec /usr/sbin/ufw …` — a system password dialog; the window itself never runs as root, there is no root-owned helper of ours.
  The rules are read when you open the firewall tab, not at start-up. Without `pkexec` (package *polkit*) the tool says so and runs nothing.

## Security design

* **Allowlist only**: operations are declared in `registry.py`/`modules/`; a request can only name one of them. Unknown operations, unknown or
  missing parameters, a wrong type, and anything outside the allowed values are refused **in the backend**, whatever the interface checked. Every
  value has a strict kind (port, number in a range, host, IP, identifier, user name, image name, fixed list, a list the computer offers ...); none
  accepts a leading `-`, a space or a shell character except plain text fields, which still become **one** argument.
* **Programs from fixed folders**: `ss`, `systemctl`, `docker` ... are looked up in `/usr/bin`, `/bin` (and `/usr/sbin`, `/sbin`); a program run as root only from the
  root-owned ones — never through `PATH`, so a planted program cannot be chosen. A missing program is reported with the package that provides it.
* **No paths, URLs or program names from a request**: folders and files come from fixed lists or from what the computer lists itself (nginx sites, certificates,
  logrotate files), repositories and Compose projects from your configuration file. Tests feed 24 hostile values into **every parameter of every operation**
  (1,500+ combinations) and require that each is refused or stays one inert argument.
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
tools), `pkexec` (package *polkit*) for administrator operations, and the programs each operation uses (`ufw`, `ss`, `docker`, `git`, `nginx`, `fail2ban-client`, `psql` ...): an
operation whose program is missing says so and names the Debian/Ubuntu package. The update and package operations are for **Debian / Ubuntu** (apt); the others use
standard Linux tools. Nothing else, no services, no background processes: the web app runs only while you keep it open.

## Install / uninstall

```bash
./install.sh devops-toolbox              # commands devops-toolbox and devops-toolbox-web + menu entry (add --prefix ~/.local for no sudo)
./install.sh --uninstall devops-toolbox
```

## Adding a module later

A module is one file in `devops_toolbox/modules/` (import it in `modules/__init__.py`). With the helper in `modules/_dsl.py` an operation is one declaration:

```python
op("net.ping", "net", ("Ping a host", "Host-ის პინგი"), ("Checks that a host answers.", "ამოწმებს, პასუხობს თუ არა host."),
   argv=["@ping", "-c", "{count}", "--", "{host}"], params=[P("host"), P("count", lo=1, hi=10, default=4)])
```

`@name` is a program from the fixed folders, `{param}` a validated value that stays one argument; `root=True` runs it through `pkexec`, `risk=` decides
the confirmation, `native=` is a built-in check without a program, `build=` returns several commands, `post=` filters the output, `check=` / `warn=` refuse or
warn for a particular input. Both languages are required by the function signature. The window and the web page get the operation through `Toolbox.catalog()`
with no UI work, and `coverage.py` plus its test make you say which documented command it belongs to.

## Tests

```bash
python3 tests/test_devops_toolbox.py      # backend: validation, argument lists, injection attempts, duplicates, permission errors, timeouts, tokens, history, translations
python3 tests/test_devops_commands.py     # all 146 operations as a family: safe plans, hostile input, fixed program folders, pkexec, filters, built-in checks, coverage of the notes
python3 tests/test_devops_web.py          # the web app over real HTTP on a loopback port: key, Host/Origin/CSRF, CSP, routes, full cycle, start/stop
xvfb-run -a python3 tests/test_devops_window.py   # the Tk window under a virtual display
```

No test touches a real firewall: every program call goes through a fake runner that answers like ufw 0.36 (outputs copied from a real run).
**Not verified here:** the real `pkexec` password dialog and a real `ufw` on a live system (a rule opened and closed on the actual machine) — the first
real use should be a harmless test port such as `ufw allow 19999/tcp` followed by *Delete selected rule…*.
