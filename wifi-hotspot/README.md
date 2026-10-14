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
