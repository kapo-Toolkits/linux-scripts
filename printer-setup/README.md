# printer-setup

GUI helper (English / ქართული) that takes you from "plugged in a printer" to "test page printed" on Linux/CUPS.
GUI ხელსაწყო (EN/KA): პრინტერის შეერთებიდან სატესტო გვერდის დაბეჭდვამდე.

## Run

```bash
python3 printer-setup-gui.py
```

Install as an app:

```bash
sudo install -m 755 printer-setup-gui.py /usr/local/bin/printer-setup
sudo install -m 644 printer-setup.desktop /usr/share/applications/
```

Requires `python3-tk` and CUPS (`lpinfo`, `lpadmin`, `lp`) — present on Mint/Ubuntu desktops.

## What it does

| Step | Action |
|---|---|
| 1 Detect | `lpinfo -v`: USB printers (`usb://…`) and network ones (`dnssd://…`) |
| 2 Driver | searches **installed** PPDs with a word-bounded model match (so `L1250` won't match Brother `HL-1250`); **apt drivers** installs the vendor's distro packages (`printer-driver-escpr`, `hplip`, …) |
| 3 Missing? | opens the vendor download page; **Install downloaded .deb…** shows name, sha256, control info, whether any file mentions your model, the full file list **and the install scripts** — installs only after you confirm |
| 4 Add | `lpadmin` with the chosen PPD, or **driverless** (`-m everywhere`) for network printers |
| 5 Test | prints CUPS' test page |

## Why drivers are not bundled

Vendor drivers carry their own licences (often proprietary, redistribution not allowed) and go stale.
So the tool finds/inspects/installs them from the manufacturer instead. The **Guide** tab explains which download to pick.

## Lessons baked in (Epson L1250, Linux Mint 22)

- `escpr2` (ESC/P-R) had **no** L1250 — the right one was **“Epson Inkjet Printer Driver (ESC/P)” `epson-inkjet-printer-202101w`** (covers L3230/L3210/L3200/L1250/L1230/L1210).
- Epson's page offers look-alikes: **Utility** (ink levels only), **Source Code** (`.src.rpm`), **PC-Fax**, **Manual** — none prints.
- `curl`/`wget` get **HTTP 403** from the download server; use a browser.

⚠️ The vendor-page URL pattern for Epson (`download-center.epson.com/download/?device_id=…`) is built from a known working link; if it does not land on your model, search it on the site. Other vendors open a web search.
