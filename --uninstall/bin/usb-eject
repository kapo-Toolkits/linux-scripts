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

# რომელი პროცესი იყენებს მიმაუნთების წერტილს / which processes hold a mount point
show_blockers() {
  local mp="$1" pid hit n=0
  echo "დისკს იყენებს / still in use by:" >&2
  if command -v lsof >/dev/null; then
    lsof -w +f -- "$mp" 2>/dev/null | head -20 >&2 && return
  fi
  if command -v fuser >/dev/null; then fuser -vm "$mp" >&2 2>&1 && return; fi
  for pid in /proc/[0-9]*; do
    hit=$( { readlink "$pid/cwd"; readlink "$pid"/fd/* ; } 2>/dev/null | grep -F -- "$mp" | head -1 || true)
    if [[ -n "$hit" ]]; then
      echo "  PID ${pid#/proc/}  $(cat "$pid/comm" 2>/dev/null)  ->  $hit" >&2; n=$((n+1))
    fi
  done
  [[ $n -gt 0 ]] || echo "  (ვერ ვხედავ — გაუშვით sudo-თი / not visible — try with sudo)" >&2
}

# ყველა მიმაუნთებული პარტიციის გამოამაუნთება
while read -r part mp; do
  [[ -z "$part" ]] && continue
  echo "umount $part"
  if ! udisksctl unmount -b "$part" && ! sudo umount "$part"; then
    show_blockers "$mp"
    echo "დახურეთ ეს პროგრამები და სცადეთ თავიდან. / Close these programs and try again." >&2
    exit 1
  fi
done < <(lsblk -lnpo NAME,MOUNTPOINT "$dev" | awk 'NF>1 {print $1, $2}')

sync
udisksctl power-off -b "$dev" || sudo udisksctl power-off -b "$dev"
echo "მზადაა — დისკი უსაფრთხოდ გამოირთო, კაბელის გამოძვრა შეიძლება."
