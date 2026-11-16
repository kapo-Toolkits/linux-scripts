"""Network (MyDevOps tasks 2, 3 and 22): addresses, routes, DNS, ping, listening ports and connections, port reachability, an HTTP check,
who uses a port, and applying a netplan configuration."""
from . import _dsl
from ._dsl import P, grep, op
from .. import i18n, validation

C = "net"          # the category is created in ufw.py (it is registered first so the sidebar order is Network, Firewall, ...)

i18n.add("blocked_insecure_remote", "A self-signed certificate is only accepted for this computer and private networks, not for {host}.",
         "თვითხელმოწერილი სერტიფიკატი მიიღება მხოლოდ ამ კომპიუტერზე და კერძო ქსელებში და არა {host}-ზე.")
i18n.add("blocked_nothing_found", "Nothing found to act on.", "მოქმედებისთვის არაფერი მოიძებნა.")
i18n.add("warn_network_may_drop", "Applying a network configuration can cut this computer off the network (and an SSH session with it) if the file is wrong.",
         "ქსელის კონფიგურაციის გამოყენებამ, თუ ფაილი არასწორია, შეიძლება კომპიუტერი ქსელს მოსწყვიტოს (და SSH სესიაც).")

op("net.addr", C, ("Network addresses (brief)", "ქსელის მისამართები (მოკლედ)"), ("Shows every interface with its state and addresses (ip -br a).", "აჩვენებს ყველა ინტერფეისს, მდგომარეობას და მისამართებს (ip -br a)."),
   argv=["@ip", "-br", "a"])
op("net.addr.full", C, ("Network addresses (full)", "ქსელის მისამართები (სრულად)"), ("Full details of every interface (ip a).", "ყველა ინტერფეისის სრული ინფორმაცია (ip a)."),
   argv=["@ip", "a"])
op("net.link", C, ("Network interfaces", "ქსელის ინტერფეისები"), ("Link state and MAC addresses (ip link).", "კავშირის მდგომარეობა და MAC მისამართები (ip link)."),
   argv=["@ip", "link"])
op("net.route", C, ("Routing table", "მარშრუტიზაციის ცხრილი"), ("Where traffic goes, and the default gateway (ip route).", "სად მიდის ტრაფიკი და ნაგულისხმევი gateway (ip route)."),
   argv=["@ip", "route"])
op("net.ping", C, ("Ping a host", "Host-ის პინგი"), ("Checks that a host answers (ping -c N).", "ამოწმებს, პასუხობს თუ არა host (ping -c N)."),
   argv=["@ping", "-c", "{count}", "--", "{host}"], params=[P("host"), P("count", lo=1, hi=10, default=4)], timeout=40)
op("net.lookup", C, ("Resolve a name", "სახელის გარჩევა"), ("Asks the system resolver for the addresses of a name (getent hosts).", "სისტემის resolver-ს სთხოვს სახელის მისამართებს (getent hosts)."),
   argv=["@getent", "ahosts", "{host}"], params=[P("host")])
op("net.dns", C, ("DNS status", "DNS-ის მდგომარეობა"), ("Which DNS servers each interface uses (resolvectl status).", "რომელ DNS სერვერებს იყენებს თითოეული ინტერფეისი (resolvectl status)."),
   argv=["@resolvectl", "status"])
op("net.listen", C, ("Listening ports", "მოსმენადი პორტები"), ("TCP and UDP ports this computer listens on (ss -tuln).", "TCP და UDP პორტები, რომლებსაც კომპიუტერი უსმენს (ss -tuln)."),
   argv=["@ss", "-tuln"])
op("net.listen.proc", C, ("Listening ports with programs", "მოსმენადი პორტები პროგრამებით"),
   ("The same, with the program behind each port; needs administrator rights (ss -tunlp).", "იგივე, თითო პორტის უკან მდგომი პროგრამით; საჭიროა ადმინისტრატორის უფლება (ss -tunlp)."),
   argv=["@ss", "-tunlp"], root=True)
op("net.conns", C, ("Established connections", "დამყარებული კავშირები"), ("Open TCP connections right now (ss -tn state established).", "ახლა გახსნილი TCP კავშირები (ss -tn state established)."),
   argv=["@ss", "-tn", "state", "established"])
op("net.sockets", C, ("Socket summary", "სოკეტების შეჯამება"), ("Counts of sockets by state (ss -s).", "სოკეტების რაოდენობა მდგომარეობის მიხედვით (ss -s)."), argv=["@ss", "-s"])
op("net.sockets.all", C, ("All TCP sockets", "ყველა TCP სოკეტი"), ("Every TCP socket in any state (ss -tan).", "ყველა TCP სოკეტი ნებისმიერ მდგომარეობაში (ss -tan)."), argv=["@ss", "-tan"])
op("net.port.who", C, ("Who uses a port?", "ვინ იყენებს პორტს?"), ("The program listening on one port; needs administrator rights (ss -tlnp 'sport = :PORT').", "პროგრამა, რომელიც ერთ პორტს უსმენს; საჭიროა ადმინისტრატორის უფლება (ss -tlnp 'sport = :PORT')."),
   build=lambda ctx, p: [["ss", "-tlnp", "sport = :%d" % p["port"]]], params=[P("port")], root=True)
op("net.nc", C, ("Is a port reachable?", "პორტი ხელმისაწვდომია?"), ("Tests TCP connections to one or more ports of a host (nc -zv -w 2).", "ამოწმებს TCP კავშირს host-ის ერთ ან რამდენიმე პორტთან (nc -zv -w 2)."),
   argv=["@nc", "-zv", "-w", "2", "{host}", "{*ports}"], params=[P("host"), P("ports")], timeout=60)


def _http_url(p):
    h = p["host"]
    h = "[%s]" % h if ":" in h else h
    return "%s://%s%s/" % (p["scheme"], h, (":%d" % p["port"]) if p.get("port") else "")


def _http_check(ctx, p):
    if p["insecure"] and not validation.is_private_or_loopback(p["host"]):
        return ("blocked_insecure_remote", {"host": p["host"]})
    return None


op("net.http", C, ("HTTP check", "HTTP შემოწმება"), ("The status line and headers a web server answers with (curl -I). Host and port only: no free-form address.", "პასუხი, რომელსაც ვებ სერვერი აბრუნებს (curl -I). მხოლოდ host და პორტი."),
   build=lambda ctx, p: [["curl", "-sS", "-I", "--max-time", "8", "--proto", "=http,https"] + (["-k"] if p["insecure"] else []) + [_http_url(p)]],
   params=[P("scheme", choices=("http", "https"), default="http"), P("host", default="localhost"), P("port", required=False), P("insecure")],
   check=_http_check, timeout=30)
op("net.lsof", C, ("Open network files", "გახსნილი ქსელური ფაილები"), ("Every network socket and the process that owns it (lsof -i -P -n); needs administrator rights.", "ყველა ქსელური სოკეტი და მისი პროცესი (lsof -i -P -n); საჭიროა ადმინისტრატორის უფლება."),
   argv=["@lsof", "-i", "-P", "-n"], root=True)
op("net.lsof.port", C, ("Open files on a port", "პორტზე გახსნილი ფაილები"), ("What uses one port (lsof -i :PORT); needs administrator rights.", "რა იყენებს ერთ პორტს (lsof -i :PORT); საჭიროა ადმინისტრატორის უფლება."),
   build=lambda ctx, p: [["lsof", "-i", ":%d" % p["port"], "-P", "-n"]], params=[P("port")], root=True)
op("net.netstat", C, ("Classic netstat", "კლასიკური netstat"), ("Listening sockets with programs (netstat -plntu); needs net-tools and administrator rights.", "მოსმენადი სოკეტები პროგრამებით (netstat -plntu); საჭიროა net-tools და ადმინისტრატორის უფლება."),
   argv=["@netstat", "-plntu"], root=True)
op("net.whois", C, ("Whois an address", "მისამართის whois"), ("Who owns an IP address (whois), e.g. to identify a remote client.", "ვის ეკუთვნის IP მისამართი (whois), მაგ. დაშორებული კლიენტის დასადგენად."),
   argv=["@whois", "{ip}"], params=[P("ip")], timeout=40)


@_dsl.dynamic("netplan_files")
def _netplan_files(ctx):
    return [f for f in ctx.sysx.listdir("/etc/netplan") if f.endswith(".yaml")]


def _netplan_perms(ctx, p):
    files = _netplan_files(ctx)
    return [["chmod", "600"] + ["/etc/netplan/" + f for f in files]] if files else []


op("net.netplan.perms", C, ("Secure netplan files", "netplan-ის ფაილების დაცვა"), ("Sets mode 600 on the files in /etc/netplan so only root can read them (chmod 600).", "/etc/netplan-ის ფაილებზე აყენებს 600-ს, რომ მხოლოდ root-ს შეეძლოს მათი წაკითხვა (chmod 600)."),
   build=_netplan_perms, root=True, risk="medium")
op("net.netplan.apply", C, ("Apply netplan configuration", "netplan-ის კონფიგურაციის გამოყენება"), ("Applies the files in /etc/netplan to the running network (netplan apply).", "/etc/netplan-ის ფაილებს ამოქმედებს მოქმედ ქსელზე (netplan apply)."),
   argv=["@netplan", "apply"], root=True, risk="high", warn=lambda ctx, p: [("warn_network_may_drop", {})], timeout=90)

op("ts.status", C, ("Tailscale status", "Tailscale-ის სტატუსი"), ("Whether Tailscale is connected and which devices it sees (tailscale status).", "დაკავშირებულია თუ არა Tailscale და რომელ მოწყობილობებს ხედავს (tailscale status)."),
   argv=["@tailscale", "status"], ok_codes=(0, 1))
op("ts.ip", C, ("Tailscale address", "Tailscale-ის მისამართი"), ("This computer's Tailscale IPv4 address (tailscale ip -4).", "ამ კომპიუტერის Tailscale IPv4 მისამართი (tailscale ip -4)."),
   argv=["@tailscale", "ip", "-4"])
