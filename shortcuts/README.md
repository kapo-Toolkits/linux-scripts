# shortcuts

Simple bilingual (English / ქართული) window: **tick toolkit programs and put their launchers on the Desktop** — or take them off again.
მარტივი ორენოვანი ფანჯარა: მონიშნეთ პროგრამები და დააგდეთ მათი იარლიყები სამუშაო მაგიდაზე, ან მოხსენით.

```bash
python3 shortcuts/shortcuts-gui.py          # from this checkout
./install.sh shortcuts                      # or install it: menu entry + the command toolkit-shortcuts
```

| Column | Meaning |
|---|---|
| **Available as** | *installed* (the command from `./install.sh`), *from this folder* (runs the program in this checkout), or *not available* |
| **On Desktop** | whether the launcher file is already on your Desktop |

Buttons: **Put on Desktop**, **Remove from Desktop**, select all / none, **Open Desktop folder**.

## What it does exactly

- One `.desktop` launcher per program in your Desktop folder (`xdg-user-dir DESKTOP`, else `~/Desktop`), marked executable and
  trusted (`gio set … metadata::trusted`). If your desktop still says “untrusted launcher”: right-click → *Allow Launching*.
- Points to the **installed command with an absolute path** (`~/.local/bin` is preferred over `/usr/local/bin`), otherwise to
  the program in this checkout, so it works from a menu click even when `~/.local/bin` is not in the session's PATH.
- **Never touches anything that is not a launcher of this toolkit**: a file is replaced/removed only if it carries our
  `X-Toolkit-Id` marker or its `Exec=` runs one of these programs (so launchers made earlier by `install.sh --desktop` are
  recognised too). A file with the same name that belongs to something else is reported and left alone.
- The checkout is found via `$TOOLKIT_ROOT`, the folder around the program, or `~/.config/linux-scripts/root`
  (written by `install.sh`), so an installed copy still knows where the not-yet-installed programs are.

Programs: USB Safe Eject, Wi-Fi Hotspot, Printer Setup, QGIS Installer, Bluetooth Setup, PrintHub.
