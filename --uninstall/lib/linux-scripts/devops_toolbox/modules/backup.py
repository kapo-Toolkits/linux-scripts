"""Backups and cron (MyDevOps tasks 11, 12, 21 and 24): your crontab, a backup of the web files and nginx configuration, the list of your backups, a
check that the newest archive is readable, and deleting old backups (list first). Everything lives in ~/backups; nothing is copied elsewhere."""
import os
import tarfile
import time

from . import _dsl
from ._dsl import P, op
from .. import i18n

C = "bk"
_dsl.category(C, "Backup and cron", "ბექაპი და cron")
DIR = "backups"
EXT = (".tar.gz", ".sql")
i18n.add("warn_backup_keys", "The archive includes /etc/nginx, which may contain your TLS private keys: keep ~/backups private (it is created with mode 700).",
         "არქივი შეიცავს /etc/nginx-ს, რომელშიც შეიძლება თქვენი TLS პირადი გასაღებები იყოს: ~/backups პირადი გაიხადეთ (იქმნება 700 რეჟიმით).")
i18n.add("warn_delete_backups", "Deletes the files listed by 'Old backups'. Look at that list first.", "შლის ფაილებს, რომლებიც „ძველი ბექაპების“ სიაშია. ჯერ ის სია ნახეთ.")
i18n.add("bk_none", "There are no backups in ~/backups.", "~/backups-ში ბექაპები არ არის.")


def _files(ctx):
    d = os.path.join(ctx.sysx.home, DIR)
    return [(f, os.path.join(d, f)) for f in ctx.sysx.listdir(d) if f.endswith(EXT) and ctx.sysx.isfile(os.path.join(d, f)) and not ctx.sysx.islink(os.path.join(d, f))]


def _list(ctx, p):
    rows = ["%10s  %s" % (_size(ctx.sysx.file_size(path)), name) for name, path in _files(ctx)]
    return "\n".join(rows) or i18n.t("en", "bk_none")


def _size(n):
    n = float(n)
    for u in ("B", "K", "M", "G"):
        if n < 1024 or u == "G":
            return "%d%s" % (n, u) if u == "B" else "%.1f%s" % (n, u)
        n /= 1024


def _old(ctx, days):
    now = time.time()
    return [(n, pth) for n, pth in _files(ctx) if ctx.sysx.file_age_days(pth, now) > days]


op("cron.list", C, ("Your crontab", "თქვენი crontab"), ("Your scheduled jobs, numbered (crontab -l).", "თქვენი დაგეგმილი დავალებები, დანომრილი (crontab -l)."),
   argv=["@crontab", "-l"], ok_codes=(0, 1), post=lambda t: "\n".join("%3d  %s" % (i, ln) for i, ln in enumerate(t.splitlines(), 1)))
op("bk.list", C, ("Your backups", "თქვენი ბექაპები"), ("The .tar.gz and .sql files in ~/backups with their sizes.", "~/backups-ში .tar.gz და .sql ფაილები ზომებით."), native=_list)


def _verify(ctx, p):
    files = _files(ctx)
    tars = [(n, pth) for n, pth in files if n.endswith(".tar.gz")]
    if not tars:
        return i18n.t("en", "bk_none")
    name, path = max(tars, key=lambda x: os.lstat(x[1]).st_mtime)
    with tarfile.open(path, "r:gz") as tar:               # reading the member list proves the archive is not cut off; nothing is extracted
        names = tar.getnames()
    return "%s: OK, %d entries\n%s" % (name, len(names), "\n".join(names[:20]))


op("bk.verify", C, ("Check the newest backup", "უახლესი ბექაპის შემოწმება"), ("Opens the newest .tar.gz and lists what is inside (tar -tzf). Nothing is extracted.", "ხსნის უახლეს .tar.gz-ს და ჩამოთვლის შიგთავსს (tar -tzf). არაფერი იხსნება."), native=_verify)
op("bk.old.list", C, ("Old backups", "ძველი ბექაპები"), ("Backups in ~/backups older than N days (only lists).", "~/backups-ში N დღეზე ძველი ბექაპები (მხოლოდ ჩამოთვლის)."),
   native=lambda ctx, p: "\n".join(n for n, _ in _old(ctx, p["days"])) or "-", params=[P("days", lo=1, hi=3650, default=30)])


def _prune(ctx, p):
    gone = []
    for name, path in _old(ctx, p["days"]):
        ctx.sysx.remove(path)
        gone.append(name)
    return "deleted %d file(s)\n%s" % (len(gone), "\n".join(gone))


op("bk.old.delete", C, ("Delete old backups", "ძველი ბექაპების წაშლა"), ("Deletes the backups in ~/backups older than N days (regular files only, links are never followed).", "შლის ~/backups-ში N დღეზე ძველ ბექაპებს (მხოლოდ ჩვეულებრივი ფაილები, ბმულებს არ მიჰყვება)."),
   native=_prune, params=[P("days", lo=1, hi=3650, default=30)], risk="high", warn=lambda ctx, p: [("warn_delete_backups", {})])


def _web_backup(ctx, p):
    d = os.path.join(ctx.sysx.home, DIR)
    out = os.path.join(d, "web_%s.tar.gz" % time.strftime("%Y-%m-%d_%H-%M-%S"))
    me = ctx.sysx.username()
    return [["mkdir", "-p", "-m", "700", d], ["tar", "-czf", out, "/var/www/html", "/etc/nginx"], ["chown", me + ":" + me, out]]


op("bk.web", C, ("Back up the web files", "ვებ ფაილების ბექაპი"), ("Archives /var/www/html and /etc/nginx into ~/backups (tar -czf) and gives you the file.", "არქივში ათავსებს /var/www/html-სა და /etc/nginx-ს ~/backups-ში (tar -czf) და ფაილს თქვენ გადმოგცემთ."),
   build=_web_backup, root=True, risk="medium", timeout=600, check=lambda ctx, p: None if ctx.sysx.username() else ("blocked_nothing_found", {}),
   warn=lambda ctx, p: [("warn_backup_keys", {})])
