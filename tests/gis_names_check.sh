#!/bin/sh
# Runs INSIDE a container: refreshes the package index and checks that every given package exists. usage: gis_names_check.sh PM NAME...
pm=$1; shift
bad=0
case $pm in
  apt-get) apt-get update -qq >/dev/null 2>&1 ;;
  dnf)     dnf -q makecache >/dev/null 2>&1 ;;
  pacman)  pacman -Sy --noconfirm >/dev/null 2>&1 ;;
  zypper)  zypper -q --gpg-auto-import-keys refresh >/dev/null 2>&1 ;;
esac
for n in "$@"; do
  case $pm in
    apt-get) c=$(apt-cache policy "$n" 2>/dev/null | awk '/Candidate/{print $2}'); [ -n "$c" ] && [ "$c" != "(none)" ] ;;
    dnf)     dnf -q list --available "$n" >/dev/null 2>&1 ;;
    pacman)  pacman -Si "$n" >/dev/null 2>&1 ;;
    zypper)  zypper -n install --dry-run "$n" >/dev/null 2>&1 ;;
  esac
  if [ $? -eq 0 ]; then echo "PASS $pm $n"; else echo "FAIL $pm $n (not found in this distribution's repositories)"; bad=1; fi
done
exit $bad
