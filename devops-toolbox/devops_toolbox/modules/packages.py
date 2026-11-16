"""Updates and packages (MyDevOps tasks 5, 21 and 23), for Debian / Ubuntu (apt): refresh the lists, what can be upgraded, upgrade, install one of the
packages of the notes, what is installed, is a reboot needed, clean up, and reboot."""
from . import _dsl
from ._dsl import P, op
from .. import i18n

C = "pkg"
_dsl.category(C, "Updates and packages", "განახლებები და პაკეტები")
NOTES_PACKAGES = ("openssh-server", "nginx", "postgresql", "postgresql-contrib", "fail2ban", "htop", "glances", "net-tools", "wtmpdb", "git",
                  "curl", "vim", "docker.io", "chrony", "ufw", "unattended-upgrades", "sysstat")
i18n.add("warn_reboot", "The computer restarts at once: save your work, and note that SSH sessions and containers stop.",
         "კომპიუტერი მაშინვე გადაიტვირთება: შეინახეთ სამუშაო, SSH სესიები და კონტეინერები გაჩერდება.")
i18n.add("reboot_needed", "A reboot is needed (/var/run/reboot-required exists).", "გადატვირთვაა საჭირო (/var/run/reboot-required არსებობს).")
i18n.add("reboot_not_needed", "No reboot is needed.", "გადატვირთვა საჭირო არ არის.")
NONINTERACTIVE = ("DEBIAN_FRONTEND=noninteractive", "NEEDRESTART_MODE=a")      # no questions (the restart prompt would hang a window)

op("pkg.update", C, ("Refresh the package lists", "პაკეტების სიების განახლება"), ("Downloads the current package lists (apt-get update).", "ჩამოტვირთავს პაკეტების მიმდინარე სიებს (apt-get update)."),
   argv=["@apt-get", "update"], root=True, risk="low", timeout=300)
op("pkg.upgradable", C, ("What can be upgraded", "რისი განახლება შეიძლება"), ("The packages that have a newer version (apt list --upgradable).", "პაკეტები, რომლებსაც უფრო ახალი ვერსია აქვთ (apt list --upgradable)."),
   argv=["@apt", "list", "--upgradable"], post=lambda t: "\n".join(x for x in t.splitlines() if x and not x.startswith(("WARNING", "Listing"))) or "-")
op("pkg.upgrade", C, ("Upgrade all packages", "ყველა პაკეტის განახლება"), ("Installs every available update (apt-get upgrade -y, without questions).", "აყენებს ყველა ხელმისაწვდომ განახლებას (apt-get upgrade -y, კითხვების გარეშე)."),
   argv=["@apt-get", "upgrade", "-y"], env_vars=NONINTERACTIVE, root=True, risk="medium", timeout=1800)
op("pkg.install", C, ("Install a package", "პაკეტის დაყენება"), ("Installs one of the packages the notes use (apt-get install -y).", "აყენებს ერთ-ერთ პაკეტს, რომელსაც ჩანაწერები იყენებს (apt-get install -y)."),
   argv=["@apt-get", "install", "-y", "{package}"], env_vars=NONINTERACTIVE, params=[P("package", "choice", choices=NOTES_PACKAGES, default="htop")],
   root=True, risk="medium", timeout=1800)
op("pkg.installed", C, ("Are the notes' packages installed?", "ჩანაწერების პაკეტები დაყენებულია?"), ("The state of the packages the notes use (dpkg -l, only installed ones shown).", "ჩანაწერების პაკეტების მდგომარეობა (dpkg -l, ნაჩვენებია მხოლოდ დაყენებულები)."),
   build=lambda ctx, p: [["dpkg", "-l"] + list(NOTES_PACKAGES)], post=lambda t: "\n".join(x for x in t.splitlines() if x.startswith("ii")) or "-", ok_codes=(0, 1))


def _reboot(ctx, p):
    return i18n.t("en", "reboot_needed" if ctx.sysx.exists("/var/run/reboot-required") else "reboot_not_needed")


op("pkg.reboot.check", C, ("Is a reboot needed?", "გადატვირთვაა საჭირო?"), ("Looks for /var/run/reboot-required (after kernel or library updates).", "ეძებს /var/run/reboot-required-ს (ბირთვის ან ბიბლიოთეკების განახლების შემდეგ)."), native=_reboot)
op("pkg.autoremove.dry", C, ("What autoremove would delete", "რას წაშლიდა autoremove"), ("A simulation: packages nobody needs any more (apt-get -s autoremove). Nothing is removed.", "სიმულაცია: პაკეტები, რომლებიც აღარავის სჭირდება (apt-get -s autoremove). არაფერი იშლება."),
   argv=["@apt-get", "-s", "autoremove"])
op("pkg.clean", C, ("Clean the package cache", "პაკეტების ქეშის გასუფთავება"), ("Deletes downloaded .deb files (apt-get clean).", "შლის ჩამოტვირთულ .deb ფაილებს (apt-get clean)."), argv=["@apt-get", "clean"], root=True, risk="low")
op("pkg.autoclean", C, ("Remove obsolete package files", "მოძველებული პაკეტის ფაილების წაშლა"), ("Deletes cached packages that can no longer be downloaded (apt-get autoclean).", "შლის ქეშირებულ პაკეტებს, რომელთა ჩამოტვირთვა აღარ შეიძლება (apt-get autoclean)."), argv=["@apt-get", "autoclean"], root=True, risk="low")
op("pkg.autoremove", C, ("Remove unneeded packages", "ზედმეტი პაკეტების წაშლა"), ("Removes packages nobody needs any more (apt-get autoremove -y). Look at the simulation first.", "შლის პაკეტებს, რომლებიც აღარავის სჭირდება (apt-get autoremove -y). ჯერ სიმულაცია ნახეთ."),
   argv=["@apt-get", "autoremove", "-y"], env_vars=NONINTERACTIVE, root=True, risk="medium", timeout=900)
op("pkg.reboot.now", C, ("Reboot the computer", "კომპიუტერის გადატვირთვა"), ("Restarts the computer now (systemctl reboot).", "კომპიუტერს ახლავე გადატვირთავს (systemctl reboot)."),
   argv=["@systemctl", "reboot"], root=True, risk="high", warn=lambda ctx, p: [("warn_reboot", {})])
