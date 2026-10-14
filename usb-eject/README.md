# usb-eject

Safely unmount and power off USB drives on Linux — as a CLI script or a small GUI (English / ქართული).

უსაფრთხო unmount და გამორთვა USB დისკებისთვის — ტერმინალის სკრიპტი ან პატარა GUI.

## Files

| File | What it does |
|---|---|
| `usb-eject.sh` | CLI: unmount all partitions → `sync` → `udisksctl power-off` |
| `usb-eject-gui.py` | Tkinter GUI, English by default with a Georgian toggle; installs `tkinter` on first run if missing |
| `usb-eject-gui.desktop` | App-menu launcher for the GUI |

## Requirements

`python3` (GUI only), `udisks2` (`udisksctl`), `lsblk`. Present on most desktop distros.

## Install

```bash
# from the repository root
./install.sh usb-eject
```

## Usage

```bash
usb-eject            # picks the only USB drive automatically
usb-eject /dev/sdb   # a specific drive
usb-eject-gui        # GUI
```

## Manual steps (what the scripts do)

```bash
sudo umount /dev/sdb1                 # unmount partitions, not the whole disk
sync
sudo udisksctl power-off -b /dev/sdb  # `eject` is for optical media, not USB HDDs
```
