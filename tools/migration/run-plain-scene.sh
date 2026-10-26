#!/usr/bin/env bash
set -euo pipefail
scene="${1:?scene required}"
case "$scene" in Tracking|Pyramid|Crank|Billiards|Truck) ;; *) exit 2 ;; esac
evidence="${PLAIN_EVIDENCE_DIR:-/work/evidence/plain}/$scene"
mkdir -p "$evidence"
taskset -pc $$ >"$evidence/affinity.log"
if [[ -n "${MIGRATION_CPUSET:-}" ]]; then
    [[ "$(taskset -pc $$)" == *"$MIGRATION_CPUSET" ]] || exit 5
fi
export DISPLAY=:99
Xvfb :99 -screen 0 1024x768x24 -nolisten tcp >"$evidence/xvfb.log" 2>&1 &
xvfb_pid=$!
wm_pid=''
app_pid=''
cleanup() {
    if [[ -n "$app_pid" ]] && kill -0 "$app_pid" 2>/dev/null; then
        kill "$app_pid" 2>/dev/null || true
        sleep 0.2
        kill -KILL "$app_pid" 2>/dev/null || true
        wait "$app_pid" 2>/dev/null || true
    fi
    if [[ -n "$wm_pid" ]]; then kill "$wm_pid" 2>/dev/null || true; fi
    kill "$xvfb_pid" 2>/dev/null || true
    wait "$xvfb_pid" 2>/dev/null || true
}
trap cleanup EXIT
for attempt in $(seq 1 50); do
    if xdpyinfo >/dev/null 2>&1; then break; fi
    sleep 0.1
done
xdpyinfo >/dev/null
openbox >"$evidence/window-manager.log" 2>&1 &
wm_pid=$!
sleep 0.2
kill -0 "$wm_pid"
classes="${PLAIN_CLASSES_DIR:-/work/classes-plain}"
dependencies="${DEPENDENCY_CP:-/work/lib/dyn4j-6.0.0.jar:/work/lib/jogl-all-2.3.2.jar:/work/lib/gluegen-rt-2.3.2.jar}"
printf 'main=org.dyn4j.samples.%s\nclasspath=%s:%s:/work/samples/src/main/java\n' "$scene" "$classes" "$dependencies" >"$evidence/launch.txt"
/jdk/bin/java -Djava.awt.headless=false -cp "$classes:$dependencies:/work/samples/src/main/java" "org.dyn4j.samples.$scene" >"$evidence/application.log" 2>&1 &
app_pid=$!
taskset -pc "$app_pid" >>"$evidence/affinity.log"
window=''
for attempt in $(seq 1 100); do
    window="$(xdotool search --name "^$scene$" 2>/dev/null | head -1 || true)"
    if [[ -n "$window" ]]; then break; fi
    if ! kill -0 "$app_pid" 2>/dev/null; then break; fi
    sleep 0.1
done
if [[ -z "$window" ]]; then
    printf 'window_found=false\n' >"$evidence/inputs.log"
    printf '{"close_requested":false,"exited_after_close":false,"forced_termination":true,"exit_code":null,"failure":"window missing"}\n' >"$evidence/termination.json"
    env -u OLLAMA_API_KEY TMPDIR="${TMPDIR:?private scratch required}" python3 -B /work/tools/migration/validate_plain.py "$scene" "$evidence" || true
    exit 3
fi
printf 'scene=%s window=%s display=%s\n' "$scene" "$window" "$DISPLAY" >"$evidence/inputs.log"
sleep 2
if [[ "$scene" != Truck ]]; then
    import -window root "$evidence/initial.png"
    xdotool mousemove --window "$window" 400 300 click 1
fi
case "$scene" in
    Tracking)
        printf 't~2s key c: show contacts\n' >>"$evidence/inputs.log"
        xdotool key c
        sleep 3
        ;;
    Pyramid)
        printf 't~2s drag left mouse: (388,365) -> (520,270), hold 1s; then key r: reset\n' >>"$evidence/inputs.log"
        xdotool mousemove --window "$window" 388 365 mousedown 1
        sleep 0.2
        xdotool mousemove --window "$window" 520 270
        sleep 1
        xdotool mouseup 1
        import -window root "$evidence/interaction.png"
        sleep 1
        xdotool key r
        sleep 1
        ;;
    Crank)
        printf 't~2s no control; observe motor motion\n' >>"$evidence/inputs.log"
        sleep 3
        ;;
    Billiards)
        printf 't~2s keydown plus 0.6s, keyup plus, keydown s 0.4s, keyup s: cue shot\n' >>"$evidence/inputs.log"
        xdotool keydown plus
        sleep 0.6
        xdotool keyup plus
        sleep 0.2
        xdotool keydown s
        sleep 0.4
        xdotool keyup s
        sleep 1
        ;;
    Truck)
        printf 'keydown Right 7s, keyup Right; key s 1s: brake; public blank-strip camera drag\n' >>"$evidence/inputs.log"
        env -u OLLAMA_API_KEY TMPDIR="${TMPDIR:?private scratch required}" python3 -B \
            /work/tools/migration/truck_camera.py "$window" "$evidence"
        ;;
esac
if [[ "$scene" != Truck ]]; then import -window root "$evidence/after-input.png"; fi
case "$scene" in Billiards) sleep 8 ;; *) sleep 3 ;; esac
import -window root "$evidence/late.png"
printf 'Alt+F4 requested after late frame\n' >>"$evidence/inputs.log"
xdotool windowactivate "$window"
sleep 0.1
xdotool key --clearmodifiers Alt+F4
exited=false
for attempt in $(seq 1 20); do
    if ! kill -0 "$app_pid" 2>/dev/null; then
        exited=true
        break
    fi
    sleep 0.1
done
if [[ "$exited" != true ]]; then
    printf 'WM_DELETE_WINDOW requested after Alt+F4 did not close the process\n' >>"$evidence/inputs.log"
    xdotool windowclose "$window" || true
    for attempt in $(seq 1 50); do
        if ! kill -0 "$app_pid" 2>/dev/null; then
            exited=true
            break
        fi
        sleep 0.1
    done
fi
if [[ "$exited" != true ]]; then
    printf '{"close_requested":true,"exited_after_close":false,"forced_termination":true,"exit_code":null,"failure":"close did not exit after Alt+F4 and WM_DELETE_WINDOW"}\n' >"$evidence/termination.json"
    env -u OLLAMA_API_KEY TMPDIR="${TMPDIR:?private scratch required}" python3 -B /work/tools/migration/validate_plain.py "$scene" "$evidence" || true
    exit 4
fi
status=0
wait "$app_pid" || status=$?
app_pid=''
printf '{"close_requested":true,"exited_after_close":true,"forced_termination":false,"exit_code":%s,"failure":null}\n' "$status" >"$evidence/termination.json"
validation_status=0
env -u OLLAMA_API_KEY TMPDIR="${TMPDIR:?private scratch required}" python3 -B /work/tools/migration/validate_plain.py "$scene" "$evidence" || validation_status=$?
if (( status != 0 )); then exit "$status"; fi
exit "$validation_status"
