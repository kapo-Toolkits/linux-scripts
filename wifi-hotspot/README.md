# wifi-hotspot

WPA2 Wi-Fi Hotspot via NetworkManager, step by step — `hotspot.sh <step>`.
Wi-Fi Hotspot (WPA2) ეტაპობრივად: თითო ნაბიჯი = თითო ბრძანება.

Tested ✅ on **Linux Mint XFCE + Dell Precision M4700** (Intel Centrino Advanced-N 6205, `iwlwifi`, kernel 7.0.0-38, NM + `wpa_supplicant`, internet from Ethernet `eno1`). On other hardware treat results as ⚠️ unverified.

## თანმიმდევრობა ახალ ინსტალაციაზე / Fresh install order

```bash
./hotspot.sh check        # 1. ინტერფეისი, rfkill, AP მხარდაჭერა, dnsmasq-base
./hotspot.sh driver       # 2. iwlwifi swcrypto=1 + initramfs  → გადატვირთე
./hotspot.sh create       # 3. პროფილი (2.4 GHz, არხი 1, ipv4 shared)
./hotspot.sh test-open    # 4. ღია ქსელით შემოწმება (type AP, 10.42.0.1/24) — დიდხანს არ დატოვო
./hotspot.sh secure       # 5. WPA2 პაროლი (იკითხება უხილავად) + აწევა
```

`create` + `secure` ერთად: `./hotspot.sh setup`.

## GUI (English / ქართული)

```bash
python3 hotspot-gui.py
```

ნაგულისხმევად ინგლისურია, ზედა მარჯვენა ღილაკით ქართულზე გადაირთვება. ფანჯრიდან: SSID, პაროლი (ჩვენება/დამალვა), არხი, „Start at boot“, **Save profile**, **Start**, **Stop** და ლოგი. წინასწარ შექმნილი `Hotspot` პროფილის მონაცემებს თავისით ჩატვირთავს.
**Save profile** წაშლის და თავიდან შექმნის `Hotspot` პროფილს (იგივე პარამეტრებით, რაც `hotspot.sh create` + `secure`).
GUI არ აკეთებს `driver` და `docker-fix` ნაბიჯებს — ისინი sudo-ს საჭიროებს, გაუშვი `hotspot.sh`-ით.

დასაყენებლად (მენიუში ხატულით):

```bash
# from the repository root
./install.sh wifi-hotspot
```

## რომელი ადაპტერი და რომელი ქსელი / Which adapter, which network

Two Wi-Fi adapters, or cable + Wi-Fi? The window has two drop-downs (↻ rescans, e.g. after plugging in a USB adapter):

* **Wi-Fi adapter** – the one that sends out the hotspot. Each entry shows model, driver, bus and whether its radio can host a hotspot at all (AP mode): many USB adapters (e.g. MediaTek MT7601U, `mt7601u`) cannot, and the window refuses to build the profile on them and says why. The adapter that can is preselected (or the one the saved profile already uses).
* **Share internet from** – *Automatic* (whatever the computer's default connection is, as NetworkManager does it) or one of the connected networks that have internet: the cable, or a **second Wi-Fi adapter connected to another network** (cable → Wi-Fi hotspot, or Wi-Fi (USB) → Wi-Fi hotspot (internal)). The hotspot adapter itself is never offered.

Choosing a network applies a small policy-routing rule (administrator password, asked once, only when the choice changes): only the **hotspot clients'** traffic goes through the chosen network, the computer's own traffic is not moved, and the rule disappears when that network or the hotspot goes down (a NetworkManager dispatcher script re-checks it on every network event). Choosing *Automatic* removes everything again. Command line:

```bash
./hotspot.sh devices              # adapters (which can host a hotspot) and shareable networks
IFACE=wlp3s0 ./hotspot.sh setup   # build the hotspot on a specific adapter
./hotspot.sh uplink eno1          # share the cable      |  ./hotspot.sh uplink wlx6070721c3312  → the second adapter
./hotspot.sh uplink auto          # back to automatic    |  ./hotspot.sh uplink  → show what is set
```

Files: `/etc/linux-scripts/hotspot-uplink`, `/etc/NetworkManager/dispatcher.d/90-linux-scripts-hotspot-uplink`, routing table 4242; `./install.sh --uninstall wifi-hotspot` removes them. The routing is tested against the real kernel (dummy interfaces in a privileged container, `tests/run-hotspot-uplink.sh`).

## დაკავშირებული მოწყობილობები / Connected devices

```bash
./hotspot.sh clients
```

GUI-ში ცხრილი ფანჯრის შუაში (ყოველ 3 წამში ახლდება): სახელი, IP, MAC, სიგნალი, დაკავშირების დრო, ჩამოტვირთული/გაგზავნილი მონაცემი.
Source: `iw dev <iface> station dump` (who is associated, signal, traffic), `ip neigh` (IP from the ARP table), and — if readable — dnsmasq's lease file for host names (`/var/lib/NetworkManager/dnsmasq-<iface>.leases`). Without that file the name shows “—”; the IP still appears.
⚠️ Parsing was tested against realistic captured-format fixtures and in the GUI; it has not been run against a live hotspot yet.

## QR კოდი ტელეფონისთვის / QR code for the phone

```bash
./hotspot.sh qr
```

GUI-ში ღილაკი **QR code / QR კოდი**. ტელეფონის კამერით დაასკანირეთ და Wi-Fi-ს ხელით აღარ აკრეფთ (Android და iPhone). კოდში პაროლიცაა — ვინც ნახავს, შეძლებს მიერთებას.
Generated in pure Python (`common/lsqr.py`, no packages needed), checked with a real QR decoder (zbar) for every size and for special characters / Georgian text. Terminal output is forced black-on-white so it scans on dark terminals too.

## ყოველდღიური / Daily

```bash
./hotspot.sh up | down | status
./hotspot.sh passwd            # პაროლის შეცვლა
./hotspot.sh ssid "NewName"    # სახელის შეცვლა
```

## დამატებითი / Extras

| Command | When |
|---|---|
| `docker-fix` | ტელეფონი უკავშირდება, ინტერნეტი არა, და `iptables -S FORWARD` აჩვენებს `-P FORWARD DROP` (Docker) |
| `autostart-on` / `autostart-off` | ჩატვირთვისას ავტომატური აწევა NM-ით |
| `service-on` | თუ `autostart-on` არ ამუშავდა: systemd სერვისი (10 წმ ლოდინით) |
| `logs` | `wpa_supplicant`-ის ბოლო ხაზები — რეალური შეცდომის მიზეზი |

ცვლადები: `IFACE`, `SSID`, `CHANNEL`, `CON`, `HOTSPOT_PSK` — მაგ. `IFACE=wlan0 SSID=Home ./hotspot.sh setup`. ინტერფეისი ავტომატურად ისაძებნება.

## რატომ ეს პარამეტრები / Why these settings

- `band bg`, `channel 1` — აუცილებლად 2.4 GHz; ცარიელი band-ისას NM-მა შეიძლება 5 GHz აირჩიოს, სადაც 6205-ზე AP არასანდოა.
- `powersave 2` — AP რეჟიმში სტაბილურობისთვის.
- `ipv4.method shared` — NM თავად აწვდის DHCP/DNS/NAT-ს (`10.42.0.1/24`); საჭიროა `dnsmasq-base`.
- `psk-flags 0` — პაროლი პროფილშია, სხვაგვარად `Secrets were required, but not provided`.
- `pmf 1` (disabled) — ამ ლეპტოპზე WPA2 ასე აიწია ⚠️ (არ შემოწმებულა ცალკე, რომელი პარამეტრი იყო გადამწყვეტი).
- `swcrypto=1` — iwlwifi-ს ჰარდვერული დაშიფვრა AP რეჟიმში ხშირად იწვევს პრობლემას: ტელეფონი უკავშირდება, IP არ მოაქვს. **არ გამოიყენო** `11n_disable=1` (Fedora-ზე სისტემა გადაიტვირთა).
- პაროლი: მხოლოდ ლათინური, 8–63 სიმბოლო.

## შეცდომები / Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `mismatching interface name` | არასწორი `ifname` | `IFACE=<სახელი> ./hotspot.sh create` |
| `Secrets were required, but not provided` | პაროლი სესიის საიდუმლოებშია | `./hotspot.sh secure` თავიდან |
| `802.1X supplicant took too long` | შეტყობინება ტყუის | `./hotspot.sh logs` — ეძებე `key setting validation failed` |
| `No suitable device found` | Wi-Fi გამორთულია | `nmcli radio wifi on; rfkill unblock wifi` |
| აიწია, ტელეფონს ინტერნეტი არ აქვს | Docker FORWARD DROP | `./hotspot.sh docker-fix` |
| უკავშირდება და წყდება, IP არ მოაქვს | დაშიფვრა/რადიო | `sudo tcpdump -i <iface> -n port 67 or port 68`, swcrypto, PMF |

თუ `secure` ჩავარდა: ჯერ `test-open` — თუ ღია აიწია, პრობლემა დაშიფვრაშია. შემდეგ სცადე swcrypto-ს მოხსნა (`sudo mv /etc/modprobe.d/iwlwifi-swcrypto.conf ~/` + `sudo update-initramfs -u` + reboot) ან `iwd` backend (მთელ Wi-Fi-ს ცვლის — უკან დასაბრუნებლად წაშალე `/etc/NetworkManager/conf.d/wifi_backend.conf` და ჩართე `wpa_supplicant`).

## გასათვალისწინებელი / Notes

- ინტერნეტი მოდის Ethernet-იდან — კაბელის გარეშე Hotspot აიწევს, ინტერნეტი არა.
- ერთი Wi-Fi ჩიპი: ან Hotspot, ან Wi-Fi კლიენტი. `autostart-on`-ის დროს სხვა Wi-Fi-ს ვერ დაუკავშირდები სანამ `down` არ გაუშვი.
- `hotspot.sh` პაროლს არსად ინახავს repo-ში; NM მას თავის პროფილში ინახავს.
- ღია ქსელი (`test-open`) ნებისმიერს აძლევს შენს ინტერნეტზე წვდომას — მხოლოდ ტესტისთვისაა.
