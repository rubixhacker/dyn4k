#!/usr/bin/env bash
set -u
run() { printf '\n$'; printf ' %q' "$@"; printf '\n'; "$@"; printf 'exit=%s\n' "$?"; }
run date -u +%FT%TZ
run uname -smr
run getconf GNU_LIBC_VERSION
run java -version
run node --version
run adb devices -l
run "${ANDROID_HOME:-/var/home/stewart/Android/Sdk}/emulator/emulator" -list-avds
run mobai devices list --json --timeout 5s
run gh api repos/rubixhacker/dyn4k/actions/runners --jq '{total_count,runners:[.runners[]|{name,os,status,labels:[.labels[].name]}]}'
run /var/home/stewart/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome --version
