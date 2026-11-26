"""Services (MyDevOps tasks 4, 8, 10, 12, 23 and 25): status, enabled, logs, start / stop / restart / reload / enable / disable for the
services the notes use, systemd-analyze, and the failed units. Changing a service is limited to a fixed list: a typed name can
be READ about, but only the listed services can be stopped or restarted."""
from . import _dsl
from ._dsl import P, head, op
from .. import i18n

C = "svc"
_dsl.category(C, "Services (systemd)", "სერვისები (systemd)")
MANAGED = ("ssh", "sshd", "nginx", "postgresql", "cron", "docker", "fail2ban", "chrony", "tailscaled", "bluetooth", "snapd", "netdata",
           "unattended-upgrades")
OVERVIEW = ("ssh", "nginx", "postgresql", "docker", "fail2ban", "chrony", "tailscaled", "cron", "ufw")
ACTIONS = ("start", "stop", "restart", "reload", "enable", "disable", "enable-now")

i18n.add("warn_service_ssh", "Stopping or disabling the SSH service can lock you out of a remote computer.",
         "SSH სერვისის გაჩერებამ ან გამორთვამ შეიძლება დაშორებულ კომპიუტერზე წვდომა დაგაკარგვინოთ.")
i18n.add("warn_service_docker", "Stopping Docker stops every container that depends on it.", "Docker-ის გაჩერება აჩერებს ყველა კონტეინერს, რომელიც მასზეა დამოკიდებული.")

op("svc.status", C, ("Service status", "სერვისის სტატუსი"), ("State and the latest log lines of one service (systemctl status).", "ერთი სერვისის მდგომარეობა და ბოლო ჟურნალის ხაზები (systemctl status)."),
   argv=["@systemctl", "status", "--no-pager", "--lines", "15", "{service_any}"], params=[P("service_any", "identifier", default="nginx")], ok_codes=(0, 3))
op("svc.overview", C, ("Key services: active?", "მთავარი სერვისები: აქტიურია?"), ("Whether the services used in the notes are running (systemctl is-active ...).", "მუშაობს თუ არა ჩანაწერებში გამოყენებული სერვისები (systemctl is-active ...)."),
   argv=["@systemctl", "is-active"] + list(OVERVIEW), ok_codes=(0, 3))
op("svc.enabled", C, ("Starts at boot?", "ჩაირთვება ჩატვირთვისას?"), ("Whether a service is enabled to start at boot (systemctl is-enabled).", "ჩართულია თუ არა სერვისი ჩატვირთვისას გასაშვებად (systemctl is-enabled)."),
   argv=["@systemctl", "is-enabled", "{service_any}"], params=[P("service_any", "identifier", default="nginx")], ok_codes=(0, 1, 3))
op("svc.running", C, ("Running services", "გაშვებული სერვისები"), ("Every service that is running now (systemctl list-units).", "ყველა სერვისი, რომელიც ახლა მუშაობს (systemctl list-units)."),
   argv=["@systemctl", "list-units", "--type=service", "--state=running", "--no-pager"])
op("svc.failed", C, ("Failed services", "ჩავარდნილი სერვისები"), ("Units that failed to start (systemctl --failed).", "ერთეულები, რომლებიც ვერ გაეშვა (systemctl --failed)."),
   argv=["@systemctl", "--failed", "--no-pager"])
op("svc.logs", C, ("Service log", "სერვისის ჟურნალი"), ("The latest log lines of one service (journalctl -u NAME -n N); needs administrator rights to see everything.", "ერთი სერვისის ბოლო ჟურნალის ხაზები (journalctl -u NAME -n N); ყველაფრის სანახავად საჭიროა ადმინისტრატორის უფლება."),
   argv=["@journalctl", "-u", "{service_any}", "-n", "{lines}", "--no-pager"],
   params=[P("service_any", "identifier", default="nginx"), P("lines", lo=10, hi=500, default=50)], root=True)
op("svc.analyze", C, ("Slowest services at boot", "ჩატვირთვისას ყველაზე ნელი სერვისები"), ("Which units took longest to start (systemd-analyze blame, first 20).", "რომელმა ერთეულებმა მოანდომა ყველაზე მეტი დრო (systemd-analyze blame, პირველი 20)."),
   argv=["@systemd-analyze", "blame"], post=head(20))


def _action_build(ctx, p):
    a = p["svc_action"]
    return [["systemctl", "enable", "--now", p["service"]]] if a == "enable-now" else [["systemctl", a, p["service"]]]


def _action_risk(ctx, p):
    return "high" if p["svc_action"] in ("stop", "disable") and p["service"] in ("ssh", "sshd", "docker") else None


def _action_warn(ctx, p):
    out = []
    if p["svc_action"] in ("stop", "disable") and p["service"] in ("ssh", "sshd"):
        out.append(("warn_service_ssh", {}))
    if p["svc_action"] in ("stop", "disable") and p["service"] == "docker":
        out.append(("warn_service_docker", {}))
    return out


op("svc.action", C, ("Start, stop or restart a service", "სერვისის გაშვება, გაჩერება ან გადატვირთვა"), ("start / stop / restart / reload / enable / disable (and enable --now) for the services of the notes (systemctl).", "start / stop / restart / reload / enable / disable (და enable --now) ჩანაწერების სერვისებისთვის (systemctl)."),
   build=_action_build, params=[P("service", "choice", choices=MANAGED, default="nginx"), P("svc_action", "choice", choices=ACTIONS, default="restart")],
   root=True, risk="medium", risk_for=_action_risk, warn=_action_warn)
