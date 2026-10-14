#!/usr/bin/env bash
# USB დისკის უსაფრთხო გამორთვა: unmount ყველა პარტიციის -> sync -> power-off
# გამოყენება:  ./usb-eject.sh            (აირჩევს ერთადერთ USB დისკს ავტომატურად)
#              ./usb-eject.sh /dev/sdb   (კონკრეტული დისკი)

set -euo pipefail

dev="${1:-}"

if [[ -z "$dev" ]]; then
  # ვეძებთ მოხსნად/USB დისკებს (სისტემური დისკი არ შედის)
  mapfile -t found < <(lsblk -dno NAME,TRAN,TYPE | awk '$2=="usb" && $3=="disk" {print "/dev/"$1}')
  if [[ ${#found[@]} -eq 0 ]]; then echo "USB დისკი ვერ მოიძებნა."; exit 1; fi
  if [[ ${#found[@]} -gt 1 ]]; then
    echo "რამდენიმე USB დისკია, მიუთითეთ ერთი:"; printf '  %s\n' "${found[@]}"; exit 1
  fi
  dev="${found[0]}"
fi

[[ -b "$dev" ]] || { echo "$dev არ არის დისკი."; exit 1; }
echo "დისკი: $dev"; lsblk "$dev"

# ყველა მიმაუნთებული პარტიციის გამოამაუნთება
while read -r part; do
  [[ -z "$part" ]] && continue
  echo "umount $part"
  udisksctl unmount -b "$part" || sudo umount "$part"
done < <(lsblk -lnpo NAME,MOUNTPOINT "$dev" | awk 'NF>1 {print $1}')

sync
udisksctl power-off -b "$dev" || sudo udisksctl power-off -b "$dev"
echo "მზადაა — დისკი უსაფრთხოდ გამოირთო, კაბელის გამოძვრა შეიძლება."
