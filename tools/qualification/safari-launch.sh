#!/bin/bash
set -euo pipefail

if [[ -n "${DYN4K_SAFARI_LAUNCH_CONTEXT:-}" ]]; then
  context="$DYN4K_SAFARI_LAUNCH_CONTEXT"
  /bin/mkdir -p "$context"
  /bin/cp "$1" "$context/redirect-$$.html"
  {
    /bin/date -u '+time=%Y-%m-%dT%H:%M:%SZ'
    /usr/bin/printf 'pid=%s ppid=%s input=%s\n' "$$" "$PPID" "$1"
    /usr/bin/printf 'command=/usr/bin/open -W -a /Applications/Safari.app\n'
    /bin/launchctl managername || true
  } > "$context/launch-$$.txt" 2>&1
  (
    for sample in 1 2 3 4 5; do
      /bin/sleep 2
      /usr/bin/printf 'sample=%s\n' "$sample"
      /bin/ps -axo pid,ppid,state,comm | /usr/bin/grep -E '[S]afari|[o]pen|[n]ode' || true
    done
  ) > "$context/process-$$.txt" 2>&1 &
  sampler_pid=$!
  if /usr/bin/open -W -a /Applications/Safari.app "$1" \
      > "$context/open-$$.stdout" 2> "$context/open-$$.stderr"; then
    open_status=0
  else
    open_status=$?
  fi
  if wait "$sampler_pid"; then
    sampler_status=0
  else
    sampler_status=$?
  fi
  samples_completed=$(/usr/bin/grep -c '^sample=' "$context/process-$$.txt" || true)
  /usr/bin/printf 'samples_completed=%s\nsampler_exit=%s\n' \
    "$samples_completed" "$sampler_status" > "$context/sample-state-$$.txt"
  /usr/bin/printf 'open_exit=%s\n' "$open_status" > "$context/launch-outcome-$$.txt"
  exit "$open_status"
fi

exec /usr/bin/open -W -a /Applications/Safari.app "$1"
