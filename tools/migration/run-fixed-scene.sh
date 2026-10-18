#!/usr/bin/env bash
set -euo pipefail
export DISPLAY=:99
Xvfb :99 -screen 0 1024x768x24 -nolisten tcp >&2 &
display_pid=$!
trap 'kill "$display_pid" 2>/dev/null || true' EXIT
for attempt in $(seq 1 50); do
    if xdpyinfo >/dev/null 2>&1; then break; fi
    sleep 0.1
done
xdpyinfo >/dev/null
/jdk/bin/java -XX:+UnlockExperimentalVMOptions -XX:hashCode=2 \
    -Djava.awt.headless=false -cp "/work/classes:$DEPENDENCY_CP" \
    org.dyn4j.samples.framework.BilliardsReplay "$@"
