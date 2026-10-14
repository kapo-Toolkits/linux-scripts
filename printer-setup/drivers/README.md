# Known-good drivers (manifest only — files are NOT in this repo)

Vendor driver files are **not** committed: for example Epson's licence (`COPYING.EPSON`, §2) forbids sharing/sublicensing the Software.
Download them from the manufacturer; this list tells you **which** file and how to check it.
`*.deb` files placed in this folder are git-ignored (local backup only).

| Printer | Package | Version | Where | Size | sha256 |
|---|---|---|---|---|---|
| Epson L1250 (also L1210, L1230, L3200, L3210, L3230) | `epson-inkjet-printer-202101w_1.0.3-1_amd64.deb` — “Epson Inkjet Printer Driver (ESC/P) for Linux” | 1.0.3 | [Epson download center](https://download-center.epson.com/download/?device_id=L1250+Series&os=DEBX64&region=US&language=en), Drivers → DEB x64 (use a browser; curl/wget get HTTP 403) | 1.93 MB | `a88f0701e3c44afa785029765677bcdf1a7bd7aa1d546b2c2fa1ea346085db1e` |

Check a download:

```bash
sha256sum epson-inkjet-printer-202101w_1.0.3-1_amd64.deb
```

A different hash can simply mean Epson published a newer build — then rely on the **Install downloaded .deb…** review in `printer-setup-gui.py`.

**Wrong files for L1250** (they do not print): `epson-inkjet-printer-escpr2` (no L1250 PPD), `epson-printer-utility` (ink levels only), `*.src.rpm` (source), PC-Fax, manuals.
