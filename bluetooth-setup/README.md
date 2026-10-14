# bluetooth-setup

Bilingual (English / ქართული) GUI for BlueZ: **see which Bluetooth adapter works and what it can do, scan, pair, connect.**
ორენოვანი GUI: რომელი Bluetooth ადაპტერი მუშაობს, რას უჭერს მხარს, ძებნა, დაწყვილება, დაკავშირება.

```bash
python3 bluetooth-setup-gui.py        # or, after ./install.sh bluetooth-setup, from the menu
```

Needs only BlueZ (`bluetoothctl`); `pactl` is optional (audio output), `pkexec` optional (software re-plug).

## Why it exists (the dongle problem)

Cheap USB dongles are often old or fake CSR clones. The tool reads each controller from BlueZ (`bluetoothctl mgmt.info`):

| Shows | Meaning |
|---|---|
| **Bluetooth 2.0 + EDR**, features `BR/EDR` | *Classic only*: fine for speakers/headsets, but **cannot talk to Low-Energy-only mice/keyboards**, and has no SSP |
| **4.0+**, features `BR/EDR LE SSP` | does everything |
| **NOT initialised** + kernel reason | e.g. `command 0x1004 tx timeout`, or USB errors `-71/-32` → bad port/hub/contact or a faulty dongle |
| “Unbranded CSR clone” | works, but limited |

Several dongles can be plugged at once; the **Active controller** box chooses which one scans and pairs.
**Software re-plug…** disables/re-enables the dongle's USB port (like unplugging it; asks for the admin password).

## Pair

1. Put the device in pairing mode (it blinks) → **Scan 15 s** → select it → **Pair & connect**.
2. PIN/passkey prompts appear in the window: *confirm a number*, *type a code on the keyboard*, *enter a PIN* (try 0000/1234).
3. Speakers: **Use as audio output**.

Implementation: one interactive `bluetoothctl --agent KeyboardDisplay` child process; its lines are parsed (`[NEW]`, `[CHG] … RSSI`, `Confirm passkey`, `Pairing successful`, …).

## Status

⚠️ Parsers, kernel-log hints and the agent protocol are unit-tested with transcripts and a fake `bluetoothctl`
(controller data from a real machine with two dongles). Pairing with real hardware (JBL speaker, keyboard, mouse) has **not** been run yet.
