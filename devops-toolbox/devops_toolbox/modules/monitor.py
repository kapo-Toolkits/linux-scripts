"""Monitoring and performance (MyDevOps tasks 12, 20, 23 and 25): uptime and load, memory, the busiest processes, disk I/O, limits, swappiness,
the time zone and time synchronisation. (htop and glances are interactive full-screen programs: start those in a terminal.)"""
import platform
import re

from . import _dsl
from ._dsl import P, head, op
from .. import i18n

C = "mon"
_dsl.category(C, "Monitoring and performance", "მონიტორინგი და წარმადობა")
i18n.add("blocked_zone_unknown", "Unknown time zone. Use the form Region/City, e.g. Asia/Tbilisi.", "უცნობი დროის სარტყელი. გამოიყენეთ ფორმა Region/City, მაგ. Asia/Tbilisi.")
i18n.add("explain_swappiness", "Takes effect now and is lost at the next reboot (persistent changes go in /etc/sysctl.conf, which you edit yourself).",
         "მაშინვე მოქმედებს და გადატვირთვისას იკარგება (მუდმივი ცვლილებები /etc/sysctl.conf-შია, რომელსაც თავად ცვლით).")

op("mon.uptime", C, ("Uptime and load", "მუშაობის დრო და დატვირთვა"), ("How long the computer has been up and the load averages (uptime).", "რამდენი ხანია მუშაობს კომპიუტერი და საშუალო დატვირთვა (uptime)."), argv=["@uptime"])
op("mon.mem", C, ("Memory", "მეხსიერება"), ("RAM and swap use (free -h).", "RAM-ისა და swap-ის გამოყენება (free -h)."), argv=["@free", "-h"])
op("mon.cpus", C, ("Number of CPUs", "პროცესორების რაოდენობა"), ("How many processing units the system has (nproc).", "რამდენი დამუშავების ერთეული აქვს სისტემას (nproc)."), argv=["@nproc"])
op("mon.top.cpu", C, ("Busiest processes (CPU)", "ყველაზე დატვირთული პროცესები (CPU)"), ("The 10 processes using most CPU (ps aux --sort=-%cpu).", "10 პროცესი, რომელიც ყველაზე მეტ CPU-ს იყენებს (ps aux --sort=-%cpu)."),
   argv=["@ps", "aux", "--sort=-%cpu"], post=head(11))
op("mon.top.mem", C, ("Busiest processes (memory)", "ყველაზე დატვირთული პროცესები (მეხსიერება)"), ("The 10 processes using most memory (ps aux --sort=-%mem).", "10 პროცესი, რომელიც ყველაზე მეტ მეხსიერებას იყენებს (ps aux --sort=-%mem)."),
   argv=["@ps", "aux", "--sort=-%mem"], post=head(11))
op("mon.io", C, ("Disk activity", "დისკის აქტივობა"), ("Three samples of disk load (iostat -x 1 3); needs the sysstat package.", "დისკის დატვირთვის სამი გაზომვა (iostat -x 1 3); საჭიროა sysstat პაკეტი."),
   argv=["@iostat", "-x", "1", "3"], timeout=30)


def _ulimit(ctx, p):
    r = ctx.sysx.rlimit_nofile()
    return "open files (ulimit -n): soft=%s hard=%s" % r if r else "-"


op("mon.ulimit", C, ("Open-file limit", "ღია ფაილების ლიმიტი"), ("The limit on open files for programs started from this tool (ulimit -n).", "ღია ფაილების ლიმიტი ამ ხელსაწყოდან გაშვებული პროგრამებისთვის (ulimit -n)."), native=_ulimit)
op("mon.swappiness", C, ("Swappiness", "Swappiness"), ("How eagerly the kernel swaps memory out (cat /proc/sys/vm/swappiness).", "რამდენად ხალისით გადააქვს ბირთვს მეხსიერება swap-ში (cat /proc/sys/vm/swappiness)."),
   native=lambda ctx, p: (ctx.sysx.read_text("/proc/sys/vm/swappiness") or "-").strip())
op("mon.swappiness.set", C, ("Set swappiness", "Swappiness-ის დაყენება"), ("Sets vm.swappiness for the running system (sysctl vm.swappiness=N), e.g. 10 on a server.", "მოქმედი სისტემისთვის ადგენს vm.swappiness-ს (sysctl vm.swappiness=N), მაგ. 10 სერვერზე."),
   build=lambda ctx, p: [["sysctl", "vm.swappiness=%d" % p["swappiness"]]], params=[P("swappiness", lo=0, hi=100, default=10)], root=True, risk="medium", explain=[("explain_swappiness", {})])
op("mon.timezone", C, ("Time and time zone", "დრო და დროის სარტყელი"), ("Local time, time zone and whether the clock is synchronised (timedatectl).", "ადგილობრივი დრო, დროის სარტყელი და სინქრონიზებულია თუ არა საათი (timedatectl)."), argv=["@timedatectl"])


def _zone_check(ctx, p):
    z = p["zone"]
    if not re.fullmatch(r"[A-Za-z_]+(/[A-Za-z0-9_+-]+){1,2}", z) or not ctx.sysx.isfile("/usr/share/zoneinfo/" + z):
        return ("blocked_zone_unknown", {})
    return None


op("mon.timezone.set", C, ("Set the time zone", "დროის სარტყლის დაყენება"), ("Changes the system time zone (timedatectl set-timezone).", "ცვლის სისტემის დროის სარტყელს (timedatectl set-timezone)."),
   argv=["@timedatectl", "set-timezone", "{zone}"], params=[P("zone", "text", default="Asia/Tbilisi")], check=_zone_check, root=True, risk="medium")
op("mon.chrony", C, ("Time synchronisation", "დროის სინქრონიზაცია"), ("How far the clock is from the time servers (chronyc tracking).", "რამდენად შორსაა საათი დროის სერვერებისგან (chronyc tracking)."), argv=["@chronyc", "tracking"])
op("mon.chrony.step", C, ("Correct the clock now", "საათის დაუყოვნებლივ გასწორება"), ("Steps the clock to the correct time at once (chronyc makestep).", "საათს მაშინვე სწორ დროზე სვამს (chronyc makestep)."), argv=["@chronyc", "makestep"], root=True, risk="medium")
op("sys.info", C, ("System information", "სისტემის ინფორმაცია"), ("Distribution, kernel, architecture and Python version.", "დისტრიბუცია, ბირთვი, არქიტექტურა და Python-ის ვერსია."),
   native=lambda ctx, p: "\n".join([(ctx.sysx.read_text("/etc/os-release") or "").split("PRETTY_NAME=")[-1].split("\n")[0].strip('"') if "PRETTY_NAME=" in (ctx.sysx.read_text("/etc/os-release") or "") else "-",
                                     "kernel " + platform.release(), "arch " + platform.machine(), "python " + platform.python_version()]))
