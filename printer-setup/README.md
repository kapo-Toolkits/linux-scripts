# printer-setup

GUI helper (English / ქართული) that takes you from "plugged in a printer" to "test page printed" on Linux/CUPS.
GUI ხელსაწყო (EN/KA): პრინტერის შეერთებიდან სატესტო გვერდის დაბეჭდვამდე.

## Run

```bash
python3 printer-setup-gui.py
```

Install as an app:

```bash
# from the repository root
./install.sh printer-setup
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
| Phones | shares a queue for Android / iPhone printing — see below |

## Phones tab — print from Android / iPhone (free)

Shares a printer that is already set up here (USB or network) with phones on the **same Wi-Fi / network**, without a paid app
(e.g. instead of “Hammer Print”). · ტელეფონიდან ბეჭდვა უფასოდ: კომპიუტერზე მიერთებული პრინტერის გაზიარება იმავე ქსელში.

| Button | What happens |
|---|---|
| **Check** | read-only, no password: `lpoptions -p Q` (`printer-is-shared`), `cupsctl` (`_share_printers`), `systemctl is-active avahi-daemon`; lists `ipp://<host>.local:631/printers/Q` and `ipp://<ip>:631/printers/Q` |
| **Share with phones** | after a confirmation, one `pkexec` run of a fixed script (queue name passed as an argument, checked to be an existing queue): `lpadmin -p Q -o printer-is-shared=true`, `cupsctl --share-printers` (CUPS' own *local network only* rule stays; no remote admin), `systemctl enable --now avahi-daemon`, and if ufw / firewalld is on: 631/tcp + 5353/udp |
| **Stop sharing** | `lpadmin -p Q -o printer-is-shared=false` |

On the phone:
- **Android** — Share / ⋮ → *Print* → *Select printer* → *All printers*. If nothing shows: Settings → Connected devices → Connection preferences → Printing → *Default Print Service* on, or install the free **Mopria Print Service**; last resort, *Add printer → by IP* with the address from the tab.
- **iPhone / iPad** — Share → *Print*; shared CUPS printers appear via AirPrint.

The computer must be on. Guest / “client isolation” Wi-Fi networks stop phones from seeing the computer.
Tested by `tests/real_printer_share_test.py` (real cupsd in a container: IPP *Get-Printer-Attributes* and *Create-Job* from outside succeed when shared and are refused when not).

## Why drivers are not bundled

Vendor drivers carry their own licences (often proprietary, redistribution not allowed) and go stale.
So the tool finds/inspects/installs them from the manufacturer instead. The **Guide** tab explains which download to pick.

## Lessons baked in (Epson L1250, Linux Mint 22)

- `escpr2` (ESC/P-R) had **no** L1250 — the right one was **“Epson Inkjet Printer Driver (ESC/P)” `epson-inkjet-printer-202101w`** (covers L3230/L3210/L3200/L1250/L1230/L1210).
- Epson's page offers look-alikes: **Utility** (ink levels only), **Source Code** (`.src.rpm`), **PC-Fax**, **Manual** — none prints.
- `curl`/`wget` get **HTTP 403** from the download server; use a browser.

⚠️ The vendor-page URL pattern for Epson (`download-center.epson.com/download/?device_id=…`) is built from a known working link; if it does not land on your model, search it on the site. Other vendors open a web search.
