"""Disk space and logs (MyDevOps task 21 and 13): free space and inodes, the biggest folders and files, old log files (list first, then delete),
the systemd journal (size, vacuum), and a logrotate dry run."""
import re

from . import _dsl
from ._dsl import P, op
from .. import i18n

C = "disk"
_dsl.category(C, "Disk and logs", "დისკი და ჟურნალები")
DIRS = ("/", "/var", "/var/lib", "/var/log", "/home", "/opt", "/tmp", "/srv")
i18n.add("warn_delete_logs", "Deletes the log files listed by 'Old log files'. Look at that list first.", "შლის ჟურნალის ფაილებს, რომლებიც „ძველი ჟურნალის ფაილების“ სიაშია. ჯერ ის სია ნახეთ.")


def human(n):
    n = float(n)
    for unit in ("B", "K", "M", "G", "T"):
        if n < 1024 or unit == "T":
            return ("%d%s" % (n, unit)) if unit == "B" else ("%.1f%s" % (n, unit))
        n /= 1024.0


def _sorted_sizes(scale, limit):
    def f(text):
        rows = []
        for ln in text.splitlines():
            m = re.match(r"^(\d+)\t(.+)$", ln)
            if m:
                rows.append((int(m.group(1)) * scale, m.group(2)))
        rows.sort(reverse=True)
        return "\n".join("%8s  %s" % (human(s), path) for s, path in rows[:limit]) or "-"
    return f


op("disk.df", C, ("Free disk space", "თავისუფალი დისკის ადგილი"), ("Size, used and free space of each file system (df -h).", "თითო ფაილური სისტემის ზომა, დაკავებული და თავისუფალი ადგილი (df -h)."), argv=["@df", "-h"])
op("disk.inodes", C, ("Free inodes", "თავისუფალი inode-ები"), ("Inode use of the root file system (df -i /): a disk can be 'full' of tiny files.", "root ფაილური სისტემის inode-ების გამოყენება (df -i /): დისკი შეიძლება პატარა ფაილებით გაივსოს."), argv=["@df", "-i", "/"])
op("disk.du", C, ("Biggest folders", "ყველაზე დიდი საქაღალდეები"), ("The 10 biggest folders one level below a folder (du -x --max-depth=1, sorted); needs administrator rights to see all.", "ერთი საქაღალდის ქვეშ 10 ყველაზე დიდი საქაღალდე (du -x --max-depth=1, დალაგებული); ყველაფრის სანახავად საჭიროა ადმინისტრატორის უფლება."),
   argv=["@du", "-xk", "--max-depth=1", "{dir}"], params=[P("dir", "choice", choices=DIRS, default="/var")], root=True, post=_sorted_sizes(1024, 10), timeout=300)
op("disk.big", C, ("Biggest files", "ყველაზე დიდი ფაილები"), ("The 20 biggest files above a size (find -xdev -type f -size +N, sorted).", "20 ყველაზე დიდი ფაილი მოცემულ ზომაზე მეტი (find -xdev -type f -size +N, დალაგებული)."),
   build=lambda ctx, p: [["find", p["dir"], "-xdev", "-type", "f", "-size", "+" + p["size"], "-printf", "%s\t%p\n"]],
   params=[P("dir", "choice", choices=DIRS, default="/var"), P("size", "choice", choices=("10M", "50M", "100M", "500M", "1G"), default="50M")], root=True,
   post=_sorted_sizes(1, 20), timeout=300)
op("disk.old.list", C, ("Old log files", "ძველი ჟურნალის ფაილები"), ("Files in /var/log older than N days (find /var/log -type f -mtime +N -print). Only lists; nothing is deleted.", "/var/log-ში N დღეზე ძველი ფაილები (find /var/log -type f -mtime +N -print). მხოლოდ ჩამოთვლის; არაფერი იშლება."),
   build=lambda ctx, p: [["find", "/var/log", "-type", "f", "-mtime", "+%d" % p["days"], "-print"]], params=[P("days", lo=1, hi=3650, default=30)], root=True)
op("disk.old.delete", C, ("Delete old log files", "ძველი ჟურნალის ფაილების წაშლა"), ("Deletes the files in /var/log older than N days (find ... -delete).", "შლის /var/log-ში N დღეზე ძველ ფაილებს (find ... -delete)."),
   build=lambda ctx, p: [["find", "/var/log", "-type", "f", "-mtime", "+%d" % p["days"], "-delete"]], params=[P("days", lo=1, hi=3650, default=30)], root=True, risk="high",
   warn=lambda ctx, p: [("warn_delete_logs", {})])
op("jr.usage", C, ("Journal size", "ჟურნალის ზომა"), ("How much disk the systemd journal uses (journalctl --disk-usage).", "რამდენ დისკს იყენებს systemd ჟურნალი (journalctl --disk-usage)."), argv=["@journalctl", "--disk-usage"])
op("jr.vacuum.time", C, ("Shrink the journal by age", "ჟურნალის შემცირება ასაკით"), ("Deletes journal entries older than a period (journalctl --vacuum-time).", "შლის ჟურნალის ჩანაწერებს, რომლებიც პერიოდზე ძველია (journalctl --vacuum-time)."),
   build=lambda ctx, p: [["journalctl", "--vacuum-time=" + p["vacuum"]]], params=[P("vacuum", "choice", choices=("2d", "7d", "30d", "90d"), default="30d")], root=True, risk="medium")
op("jr.vacuum.size", C, ("Shrink the journal by size", "ჟურნალის შემცირება ზომით"), ("Keeps the journal under a size (journalctl --vacuum-size).", "ჟურნალს მოცემულ ზომაზე ნაკლებს ტოვებს (journalctl --vacuum-size)."),
   build=lambda ctx, p: [["journalctl", "--vacuum-size=" + p["vacuum"]]], params=[P("vacuum", "choice", choices=("100M", "200M", "500M", "1G"), default="500M")], root=True, risk="medium")


@_dsl.dynamic("logrotate_configs")
def _logrotate(ctx):
    return [f for f in ctx.sysx.listdir("/etc/logrotate.d") if not f.startswith(".") and "." not in f]


op("logrotate.debug", C, ("Logrotate dry run", "Logrotate-ის სატესტო გაშვება"), ("Shows what logrotate would do for one configuration, without doing it (logrotate -d).", "აჩვენებს, რას გააკეთებდა logrotate ერთი კონფიგურაციისთვის, გაკეთების გარეშე (logrotate -d)."),
   build=lambda ctx, p: [["logrotate", "-d", "/etc/logrotate.d/" + p["config"]]], params=[P("config", choices=(), dynamic="logrotate_configs")], root=True)
