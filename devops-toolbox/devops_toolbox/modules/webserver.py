"""Web server and certificates (MyDevOps tasks 8, 9, 16 and 17): nginx configuration test, the sites that are enabled, enabling and
disabling a site, the server_name lines, and TLS certificates (show a certificate, create a self-signed one)."""
import os

from . import _dsl
from ._dsl import P, grep, op
from .. import i18n

C = "web"
_dsl.category(C, "Web server and certificates", "ვებ სერვერი და სერტიფიკატები")
AVAIL, ENABLED = "/etc/nginx/sites-available", "/etc/nginx/sites-enabled"
CERT_KEY, CERT_CRT = "/etc/ssl/private/selfsigned.key", "/etc/ssl/certs/selfsigned.crt"

i18n.add("blocked_already_enabled", "This site is already enabled.", "ეს საიტი უკვე ჩართულია.")
i18n.add("blocked_not_enabled", "This site is not enabled (or is not a link).", "ეს საიტი ჩართული არ არის (ან ბმული არ არის).")
i18n.add("blocked_cert_exists", "A certificate with this name already exists ({file}); this tool never overwrites key material.",
         "ამ სახელის სერტიფიკატი უკვე არსებობს ({file}); ხელსაწყო გასაღებებს არასოდეს გადააწერს.")
i18n.add("explain_nginx_then_reload", "Afterwards run 'Test the nginx configuration' and reload nginx (Services).", "მერე გაუშვით „nginx-ის კონფიგურაციის შემოწმება“ და გადატვირთეთ nginx (სერვისები).")

op("web.test", C, ("Test the nginx configuration", "nginx-ის კონფიგურაციის შემოწმება"), ("Checks the nginx files for mistakes before a reload (nginx -t).", "ამოწმებს nginx-ის ფაილებს შეცდომებზე გადატვირთვამდე (nginx -t)."),
   argv=["@nginx", "-t"], root=True)
op("web.servername", C, ("nginx server_name lines", "nginx-ის server_name ხაზები"), ("The server_name of every site in the loaded configuration (nginx -T, filtered).", "ჩატვირთულ კონფიგურაციაში ყველა საიტის server_name (nginx -T, გაფილტრული)."),
   argv=["@nginx", "-T"], root=True, post=grep("server_name"))


@_dsl.dynamic("nginx_available")
def _available(ctx):
    return [f for f in ctx.sysx.listdir(AVAIL) if not f.startswith(".")]


@_dsl.dynamic("nginx_enabled")
def _enabled(ctx):
    return [f for f in ctx.sysx.listdir(ENABLED) if not f.startswith(".")]


def _sites(ctx, p):
    on = set(_enabled(ctx))
    lines = ["%s  %s" % ("enabled " if f in on else "disabled", f) for f in _available(ctx)]
    lines += ["%s  %s (not in sites-available)" % ("enabled ", f) for f in sorted(on - set(_available(ctx)))]
    return "\n".join(lines) or "-"


op("web.sites", C, ("nginx sites", "nginx-ის საიტები"), ("Which sites exist and which are enabled (sites-available / sites-enabled).", "რომელი საიტები არსებობს და რომელია ჩართული (sites-available / sites-enabled)."), native=_sites)
op("web.site.enable", C, ("Enable an nginx site", "nginx-ის საიტის ჩართვა"), ("Links the site into sites-enabled (ln -s).", "საიტს აბამს sites-enabled-ში (ln -s)."),
   build=lambda ctx, p: [["ln", "-s", AVAIL + "/" + p["site"], ENABLED + "/" + p["site"]]],
   params=[P("site", choices=(), dynamic="nginx_available")], root=True, risk="medium",
   check=lambda ctx, p: ("blocked_already_enabled", {}) if ctx.sysx.exists(ENABLED + "/" + p["site"]) else None,
   explain=[("explain_nginx_then_reload", {})])
op("web.site.disable", C, ("Disable an nginx site", "nginx-ის საიტის გამორთვა"), ("Removes the link from sites-enabled; the site file itself stays (rm of the link).", "ბმულს შლის sites-enabled-იდან; თავად საიტის ფაილი რჩება (ბმულის rm)."),
   build=lambda ctx, p: [["rm", ENABLED + "/" + p["site"]]], params=[P("site", choices=(), dynamic="nginx_enabled")], root=True, risk="medium",
   check=lambda ctx, p: None if ctx.sysx.islink(ENABLED + "/" + p["site"]) else ("blocked_not_enabled", {}),
   explain=[("explain_nginx_then_reload", {})])


@_dsl.dynamic("certificates")
def _certs(ctx):
    out = ["/etc/nginx/ssl/" + f for f in ctx.sysx.listdir("/etc/nginx/ssl") if f.endswith((".crt", ".pem"))]
    out += ["/etc/ssl/certs/" + f for f in ctx.sysx.listdir("/etc/ssl/certs") if f == "selfsigned.crt"]
    out += ["/etc/letsencrypt/live/%s/fullchain.pem" % d for d in ctx.sysx.listdir("/etc/letsencrypt/live") if not d.startswith(".") and d != "README"]
    return out


op("ssl.cert.show", C, ("Show a certificate", "სერტიფიკატის ჩვენება"), ("Subject, issuer and the dates a certificate is valid (openssl x509 -noout ...).", "სერტიფიკატის სუბიექტი, გამცემი და მოქმედების თარიღები (openssl x509 -noout ...)."),
   argv=["@openssl", "x509", "-noout", "-subject", "-issuer", "-dates", "-in", "{cert}"], params=[P("cert", choices=(), dynamic="certificates")])


def _create_cert(ctx, p):
    cn = p["cn"]
    san = ("IP:%s" if cn.replace(".", "").isdigit() or ":" in cn else "DNS:%s") % cn
    return [["openssl", "req", "-x509", "-nodes", "-days", str(p["validity"]), "-newkey", "rsa:2048", "-keyout", CERT_KEY, "-out", CERT_CRT,
             "-subj", "/CN=" + cn, "-addext", "subjectAltName=" + san], ["chmod", "600", CERT_KEY]]


op("ssl.selfsigned.create", C, ("Create a self-signed certificate", "თვითხელმოწერილი სერტიფიკატის შექმნა"), ("Makes a key and certificate for a name or address (openssl req -x509) in /etc/ssl and sets the key to mode 600. It never overwrites an existing one.", "ქმნის გასაღებსა და სერტიფიკატს სახელისთვის ან მისამართისთვის (openssl req -x509) /etc/ssl-ში და გასაღებს 600-ს უყენებს. არსებულს არასოდეს გადააწერს."),
   build=_create_cert, params=[P("cn"), P("validity", lo=1, hi=3650, default=365)], root=True, risk="medium", timeout=120,
   check=lambda ctx, p: ("blocked_cert_exists", {"file": CERT_CRT}) if ctx.sysx.exists(CERT_CRT) or ctx.sysx.exists(CERT_KEY) else None)
