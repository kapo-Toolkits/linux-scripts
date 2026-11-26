# autostart

**Autostart Manager** (English / ქართული): the programs that start when you log in — see them, turn them on or off, add your own,
remove them, and start or stop one right now. No administrator password.
პროგრამები, რომლებიც სისტემაში შესვლისას ეშვება: ნახვა, ჩართვა / გამორთვა, დამატება, წაშლა, ახლავე გაშვება ან გათიშვა.

```bash
python3 autostart-gui.py          # from this folder
./install.sh autostart            # from the repository root: command autostart-manager + menu entry
```

Requires `python3-tk`. Works on every desktop that follows the XDG Autostart standard (Cinnamon, GNOME, KDE, XFCE, MATE, LXQt).

## What it shows

| Column | Meaning |
|---|---|
| Starts | ✔ yes, or why not: *off*, *not for this desktop* (`OnlyShowIn` / `NotShowIn`), *program not installed* (`TryExec`) |
| Where | *yours* (`~/.config/autostart`), *system* (`/etc/xdg/autostart`), *system (changed by you)* |
| Running now | one of your own processes is that program right now |

⚠ marks parts of the desktop itself (PolicyKit agent, keyring, settings / power / notification daemons, screen locker …):
turning one off asks again, because it can break sign-in, passwords, sound or power after the next login.

## How it changes things

- **Turn off** a system entry → a copy in `~/.config/autostart` with `Hidden=true` and `X-GNOME-Autostart-enabled=false`
  (what the desktops' own *Startup Applications* do). **Turn on** again → that copy is removed. System files are never written.
- **Add program…** copies an application's launcher from the menu; **Add command…** writes a new entry
  (`Exec` is run without a shell, like every launcher; optional delay `X-GNOME-Autostart-Delay`, honoured by GNOME / Cinnamon).
- **Remove** deletes only *your* file: an entry you added goes away; on a changed system entry it is **Reset to system**.
- **Start now** runs the entry's command (no shell). **Stop now** sends SIGTERM to your own processes of that program after a
  question — matched by exact path, or by name; an interpreter (`sh`, `python3`) or a helper (`systemctl`, `flatpak`, …) is never
  a target by itself, so it cannot stop an unrelated shell.

Changes apply from the next login. Not covered: system services (`systemctl`) — that is the DevOps Toolbox's *Services* theme.
