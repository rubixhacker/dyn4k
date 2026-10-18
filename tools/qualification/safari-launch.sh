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
  /usr/bin/printf 'open_state=pending\n' > "$context/launch-outcome-$$.txt"
  (
    set +e
    sampler_status=0
    for sample in 1 2 3 4 5; do
      if ! /bin/sleep 2 || ! /usr/bin/printf 'sample=%s\n' "$sample"; then
        sampler_status=1
        break
      fi
      /bin/ps -axo pid,ppid,state,comm | /usr/bin/grep -E '[S]afari|[o]pen|[n]ode' || true
    done
    samples_completed=$(/usr/bin/grep -c '^sample=' "$context/process-$$.txt" || true)
    printf -v expected 'samples_completed=%s\nsampler_exit=%s\n' \
      "$samples_completed" "$sampler_status"
    publication_error=sample_state_write_failed
    if /usr/bin/printf 'samples_completed=%s\nsampler_exit=%s\n' \
        "$samples_completed" "$sampler_status" > "$context/sample-state-$$.tmp"; then
      publication_error=sample_state_verify_failed
      if /usr/bin/cmp -s "$context/sample-state-$$.tmp" <(printf '%s' "$expected"); then
        publication_error=sample_state_rename_failed
        if /bin/mv "$context/sample-state-$$.tmp" "$context/sample-state-$$.txt"; then
          exit "$sampler_status"
        fi
      fi
    fi
    /usr/bin/printf '%s\n' "$publication_error" >&2
    /bin/rm -f "$context/sample-state-$$.tmp" || \
      /usr/bin/printf 'sample_state_cleanup_failed\n' >&2
    exit 1
  ) > "$context/process-$$.txt" 2>&1 &
  sampler_pid=$!
  if /usr/bin/open -W -a /Applications/Safari.app "$1" \
      > "$context/open-$$.stdout" 2> "$context/open-$$.stderr"; then
    open_status=0
  else
    open_status=$?
  fi
  if wait "$sampler_pid"; then
    sampler_result=0
  else
    sampler_result=$?
  fi
  /usr/bin/printf 'open_state=finished\nopen_exit=%s\n' "$open_status" \
    > "$context/launch-outcome-$$.tmp"
  /bin/mv "$context/launch-outcome-$$.tmp" "$context/launch-outcome-$$.txt"
  if [[ "$open_status" -ne 0 ]]; then
    exit "$open_status"
  fi
  exit "$sampler_result"
fi

exec /usr/bin/open -W -a /Applications/Safari.app "$1"
