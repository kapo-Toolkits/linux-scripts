"""Security audit (MyDevOps tasks 13 and 23): Fail2Ban state and unban, who tried to log in and from where, sudo history, upgrades pending, automatic
upgrades. (Users, SSH settings and the firewall have their own tabs.)"""
import re
from collections import Counter

from . import _dsl
from ._dsl import P, grep, op
from .. import i18n

C = "sec"
_dsl.category(C, "Security audit", "უსაფრთხოების აუდიტი")
i18n.add("warn_unban", "The address can try to log in again.", "მისამართს შეუძლია ისევ სცადოს შესვლა.")


def _attackers(text):
    ips = Counter(m.group(1) for ln in text.splitlines() if "failed password" in ln.lower()
                  for m in [re.search(r"from (\S+) port", ln)] if m)
    return "\n".join("%6d  %s" % (n, ip) for ip, n in ips.most_common(10)) or "-"


def _count_upgradable(text):
    n = sum(1 for ln in text.splitlines() if ln and not ln.startswith(("WARNING", "Listing")))
    return "%d package(s) can be upgraded" % n


op("sec.f2b", C, ("Fail2Ban status", "Fail2Ban-ის სტატუსი"), ("The jails Fail2Ban watches (fail2ban-client status); needs administrator rights.", "jail-ები, რომლებსაც Fail2Ban აკვირდება (fail2ban-client status); საჭიროა ადმინისტრატორის უფლება."),
   argv=["@fail2ban-client", "status"], root=True)
op("sec.f2b.jail", C, ("Fail2Ban jail", "Fail2Ban-ის jail"), ("Banned addresses and counters of one jail, e.g. sshd (fail2ban-client status JAIL).", "ერთი jail-ის დაბლოკილი მისამართები და მრიცხველები, მაგ. sshd (fail2ban-client status JAIL)."),
   argv=["@fail2ban-client", "status", "{jail}"], params=[P("jail", "identifier", default="sshd")], root=True)
op("sec.f2b.unban", C, ("Unban an address", "მისამართის განბლოკვა"), ("Removes an address from a jail's ban list (fail2ban-client set JAIL unbanip IP).", "მისამართს შლის jail-ის დაბლოკილთა სიიდან (fail2ban-client set JAIL unbanip IP)."),
   argv=["@fail2ban-client", "set", "{jail}", "unbanip", "{ip}"], params=[P("jail", "identifier", default="sshd"), P("ip")], root=True, risk="medium",
   warn=lambda ctx, p: [("warn_unban", {})])
op("sec.attackers", C, ("Who failed to log in", "ვინ ვერ შემოვიდა"), ("The 10 addresses with most failed SSH password attempts (journalctl -u ssh, counted).", "10 მისამართი ყველაზე მეტი წარუმატებელი SSH პაროლის მცდელობით (journalctl -u ssh, დათვლილი)."),
   argv=["@journalctl", "-u", "{unit}", "--no-pager", "-n", "5000"], params=[P("unit", "choice", choices=("ssh", "sshd"), default="ssh")], root=True, post=_attackers)
op("sec.sudo.log", C, ("Recent sudo commands", "ბოლო sudo ბრძანებები"), ("The last 20 commands run with sudo (journalctl _COMM=sudo, filtered for COMMAND).", "ბოლო 20 ბრძანება, რომელიც sudo-თი გაეშვა (journalctl _COMM=sudo, გაფილტრული COMMAND-ზე)."),
   argv=["@journalctl", "_COMM=sudo", "--no-pager", "-n", "3000"], root=True, post=grep("COMMAND", ignore_case=False, last=20))
op("sec.upgradable", C, ("Updates waiting", "მოლოდინში მყოფი განახლებები"), ("How many packages have updates (apt list --upgradable, counted).", "რამდენ პაკეტს აქვს განახლება (apt list --upgradable, დათვლილი)."),
   argv=["@apt", "list", "--upgradable"], post=_count_upgradable)
op("sec.autoupgrades", C, ("Automatic security updates", "ავტომატური უსაფრთხოების განახლებები"), ("Whether unattended-upgrades is enabled (systemctl is-enabled unattended-upgrades).", "ჩართულია თუ არა unattended-upgrades (systemctl is-enabled unattended-upgrades)."),
   argv=["@systemctl", "is-enabled", "unattended-upgrades"], ok_codes=(0, 1, 4))
