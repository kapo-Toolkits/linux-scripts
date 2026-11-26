"""Where every command of the MyDevOps notes (https://ezdanapak.github.io/MyDevOps/) went: to an operation of this tool, or - with the reason -
left to the terminal on purpose. A test checks that every operation named here exists and that every operation is justified by at least one
documented command (or is listed as an extra), so the claim "the documented commands are covered" can be verified, not just believed."""

# (documented command or group, [operation ids])
COVERED = [
    # network - tasks 2, 3, 22
    ("ip a / ip -br a / ip link / ip route", ["net.addr", "net.addr.full", "net.link", "net.route"]),
    ("ping -c N host", ["net.ping"]), ("resolvectl status", ["net.dns"]), ("getent / name resolution checks", ["net.lookup"]),
    ("ss -tlnp / -tunlp / ss -tlnp 'sport = :PORT' / ss -tlpn", ["net.listen", "net.listen.proc", "net.port.who"]),
    ("ss -tn state established / ss -s / ss -tan", ["net.conns", "net.sockets", "net.sockets.all"]),
    ("lsof -i -P -n / lsof -i :80", ["net.lsof", "net.lsof.port"]), ("netstat -plntu", ["net.netstat"]), ("whois IP", ["net.whois"]),
    ("nc -zv -w 2 host ports", ["net.nc"]), ("curl -I http://host / curl -kI https://localhost/ / curl status checks", ["net.http"]),
    ("sudo chmod 600 /etc/netplan/*.yaml", ["net.netplan.perms"]), ("sudo netplan apply", ["net.netplan.apply"]),
    ("tailscale ip -4 / tailscale status", ["ts.ip", "ts.status"]),
    # firewall - tasks 4, 7, 8, 15, 17, 22, 23
    ("ufw status / status verbose / status numbered", ["ufw.status", "ufw.status.verbose", "ufw.status.numbered"]),
    ("ufw allow 22 / 80 / 443 / 19999/tcp, ufw deny, ufw reject", ["ufw.rule.add"]), ("ufw delete N", ["ufw.rule.delete"]),
    ("ufw allow ssh / 'Nginx HTTP' / 'Nginx Full'", ["ufw.app.allow"]), ("ufw default deny incoming / allow outgoing", ["ufw.default"]),
    # ssh - tasks 4, 23
    ("sudo sshd -t", ["ssh.test"]), ("sudo sshd -T | grep ...", ["ssh.config"]), ("grep PermitRootLogin /etc/ssh/sshd_config", ["ssh.config.file"]),
    ("ls -l ~/.ssh/ / chmod 700 ~/.ssh / chmod 600 authorized_keys", ["ssh.keys", "ssh.perms.fix"]), ("cat ~/.ssh/id_ed25519.pub", ["ssh.pubkey"]),
    ("journalctl -u ssh | grep failed / Accepted", ["ssh.log.failed", "ssh.log.accepted"]),
    # services - tasks 4, 8, 10, 12, 23, 25
    ("systemctl status X", ["svc.status"]), ("systemctl is-active a b c", ["svc.overview"]), ("systemctl is-enabled X", ["svc.enabled"]),
    ("systemctl enable --now / start / stop / restart / reload / disable X", ["svc.action"]), ("journalctl -u X -n N", ["svc.logs"]),
    ("systemd-analyze blame", ["svc.analyze"]), ("systemctl --failed", ["svc.failed"]), ("systemctl list-units --state=running", ["svc.running"]),
    # web server and certificates - tasks 8, 9, 16, 17
    ("sudo nginx -t", ["web.test"]), ("sudo nginx -T | grep server_name", ["web.servername"]), ("ls -l /etc/nginx/sites-enabled/", ["web.sites"]),
    ("ln -s sites-available/X sites-enabled/ ; rm sites-enabled/X", ["web.site.enable", "web.site.disable"]),
    ("openssl x509 -noout -dates -subject", ["ssl.cert.show"]), ("openssl req -x509 -nodes -days 365 -newkey rsa:2048 ...", ["ssl.selfsigned.create"]),
    # docker - tasks 14, 15, 16, 19, 21, 23
    ("docker --version / docker compose version", ["dk.version"]), ("docker ps / docker ps -a", ["dk.ps", "dk.ps.all"]), ("docker images", ["dk.images"]),
    ("docker stats --no-stream", ["dk.stats"]), ("docker system df", ["dk.df"]), ("docker compose logs / docker logs", ["dk.logs", "dk.compose.logs"]),
    ("docker compose restart / docker restart", ["dk.restart", "dk.compose.restart"]), ("docker run --rm hello-world", ["dk.hello"]),
    ("docker rmi hello-world", ["dk.rmi"]), ("docker system prune -a", ["dk.prune"]), ("docker compose ps", ["dk.compose.ps"]),
    ("docker compose up -d", ["dk.compose.up"]), ("docker compose pull", ["dk.compose.pull"]), ("docker compose down", ["dk.compose.down"]),
    ("docker compose down -v", ["dk.compose.down_volumes"]), ("docker compose up -d --build --remove-orphans", ["dk.compose.rebuild"]),
    # git - tasks 9, 18, 19
    ("git config --global user.name / user.email / init.defaultBranch", ["git.config.show", "git.config.set"]), ("git status / git status -sb", ["git.status"]),
    ("git log --oneline", ["git.log"]), ("git branch -vv / git remote", ["git.branch", "git.remote"]), ("git diff", ["git.diff"]),
    ("git rev-parse HEAD", ["git.head"]), ("git ls-files", ["git.files"]), ("git fetch", ["git.fetch"]), ("git pull --ff-only", ["git.pull"]),
    # users - tasks 6, 23
    ("awk ... /etc/passwd (users with a shell)", ["usr.list"]), ("id / whoami / groups", ["usr.me"]), ("getent group sudo", ["usr.sudo"]),
    ("sudo grep -rvE '^\\s*(#|$)' /etc/sudoers /etc/sudoers.d/", ["usr.sudoers"]), ("sudo passwd -S root", ["usr.root"]), ("last -n 10 / last -a", ["usr.last"]),
    ("sudo lastb | head", ["usr.lastb"]), ("sudo adduser NAME", ["usr.add"]), ("sudo usermod -aG sudo|docker NAME", ["usr.group.add"]),
    ("sudo gpasswd -d NAME sudo", ["usr.group.remove"]),
    # updates and packages - tasks 5, 14, 20, 23
    ("sudo apt update", ["pkg.update"]), ("apt list --upgradable", ["pkg.upgradable", "sec.upgradable"]), ("sudo apt upgrade -y", ["pkg.upgrade"]),
    ("sudo apt install -y git curl vim htop net-tools nginx postgresql fail2ban ...", ["pkg.install"]), ("dpkg -l git curl vim htop net-tools | grep ^ii", ["pkg.installed"]),
    ("ls /var/run/reboot-required", ["pkg.reboot.check"]), ("sudo reboot", ["pkg.reboot.now"]), ("sudo apt autoremove --dry-run", ["pkg.autoremove.dry"]),
    ("sudo apt clean / apt-get autoclean / autoremove", ["pkg.clean", "pkg.autoclean", "pkg.autoremove"]),
    # disk and logs - task 21
    ("df -h / df -i /", ["disk.df", "disk.inodes"]), ("sudo du -xh / --max-depth=1 | sort -rh | head", ["disk.du"]),
    ("sudo find / -xdev -type f -size +50M", ["disk.big"]), ("sudo find /var/log -type f -mtime +30 -print", ["disk.old.list"]),
    ("sudo find /var/log -type f -mtime +30 -delete", ["disk.old.delete"]), ("journalctl --disk-usage", ["jr.usage"]),
    ("sudo journalctl --vacuum-time=2d / 30d", ["jr.vacuum.time"]), ("sudo journalctl --vacuum-size=500M", ["jr.vacuum.size"]),
    ("sudo logrotate -d /etc/logrotate.d/X", ["logrotate.debug"]),
    # monitoring and performance - tasks 12, 20, 25
    ("uptime", ["mon.uptime"]), ("free -h", ["mon.mem"]), ("nproc", ["mon.cpus"]), ("ps aux --sort=-%cpu | head / --sort=-%mem | head", ["mon.top.cpu", "mon.top.mem"]),
    ("iostat -x 1 3", ["mon.io"]), ("ulimit -n", ["mon.ulimit"]), ("cat /proc/sys/vm/swappiness", ["mon.swappiness"]), ("sudo sysctl vm.swappiness=10", ["mon.swappiness.set"]),
    ("timedatectl | grep ...", ["mon.timezone"]), ("sudo timedatectl set-timezone Asia/Tbilisi", ["mon.timezone.set"]),
    ("chronyc tracking", ["mon.chrony"]), ("sudo chronyc makestep", ["mon.chrony.step"]),
    # security audit - tasks 13, 23
    ("sudo fail2ban-client status [sshd]", ["sec.f2b", "sec.f2b.jail"]), ("sudo fail2ban-client set sshd unbanip IP", ["sec.f2b.unban"]),
    ("grep 'Failed password' auth.log | awk | sort | uniq -c", ["sec.attackers"]), ("journalctl _COMM=sudo | grep COMMAND", ["sec.sudo.log"]),
    ("systemctl is-enabled unattended-upgrades", ["sec.autoupgrades"]),
    # database - tasks 10, 11, 24, 25
    ("sudo -u postgres psql / psql -l", ["db.list"]), ("psql -c 'SELECT version();'", ["db.version"]), ("sudo -u postgres psql -c 'SHOW shared_buffers;'", ["db.show"]),
    ("psql \\du", ["db.roles"]), ("pg_dump -w -h localhost -U user -d db -f file", ["db.backup"]),
    # backup and cron - tasks 11, 12, 21, 24
    ("crontab -l / crontab -l | cat -n", ["cron.list"]), ("ls -lh ~/backups/", ["bk.list"]), ("tar -tzf latest.tar.gz", ["bk.verify"]),
    ("find ~/backups -name '*.tar.gz' -mtime +30 -print / -delete", ["bk.old.list", "bk.old.delete"]), ("sudo tar -cvzf ~/app_files.tar.gz /var/www/html /etc/nginx", ["bk.web"]),
]

# Operations that do not come from a documented command (listed so the test knows they are deliberate)
EXTRAS = {"sys.info": "system information (a category named in the project's plan)", "net.lookup": "the name check behind 'ping ubuntu.com'"}

# Documented commands that are NOT operations, and why. They stay in the terminal on purpose.
TERMINAL = [
    ("nano / vim edits of config files, crontab -e", "editing arbitrary files is exactly what a free-text interface must not do"),
    ("sudo reboot while a window is open is covered; shutdown / poweroff", "not in the notes"),
    ("ssh-keygen -t ed25519 ..., ssh-copy-id, ssh user@host, scp", "ask for a passphrase or password, or reach arbitrary hosts and paths: this tool must never handle them"),
    ("su - user, sudo -u user shell, newgrp", "interactive sessions"),
    ("htop, glances", "interactive full-screen programs (use a terminal)"),
    ("git add / commit / push / reset --hard / init / clone", "they decide what your project contains and where it goes; clone/push take arbitrary URLs"),
    ("curl | sh installers (Tailscale, Netdata), wget kickstart scripts", "never run downloaded scripts unchecked"),
    ("mkdir / chmod / chown / rm / ln on arbitrary paths, touch, cat, tail -f", "arbitrary paths from a request are not allowed; the useful fixed-path cases are operations above"),
    ("psql restore (< file), mysqldump / mysql, pg_dumpall to arbitrary files", "arbitrary file paths and passwords"),
    ("docker compose exec / docker run with arbitrary images, docker volume rm", "arbitrary programs and images"),
    ("sudo tailscale up", "interactive login"),
    ("sudo systemctl daemon-reload, myapp.service (your own units)", "covered for the listed services only; other units can be read (status, logs) but not changed"),
    ("passwd NAME, usermod passwords, CREATE ROLE ... PASSWORD", "passwords are never typed into this tool"),
]
