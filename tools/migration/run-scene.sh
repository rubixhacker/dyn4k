#!/usr/bin/env bash
set -euo pipefail
scene="$1"
seconds="${2:-12}"
case "$scene" in Tracking|Pyramid|Crank|Billiards|Truck) ;; *) exit 2 ;; esac
evidence="${EVIDENCE_DIR:-/work/evidence}/$scene"
mkdir -p "$evidence"
export DISPLAY=:99
Xvfb :99 -screen 0 1024x768x24 -nolisten tcp >"$evidence/xvfb.log" 2>&1 &
xvfb_pid=$!
wm_pid=''
observer_pid=''
trap 'if [[ -n "$observer_pid" ]]; then kill "$observer_pid" 2>/dev/null || true; fi; if [[ -n "$wm_pid" ]]; then kill "$wm_pid" 2>/dev/null || true; fi; kill "$xvfb_pid" 2>/dev/null || true' EXIT
for attempt in $(seq 1 50); do
    if xdpyinfo >/dev/null 2>&1; then break; fi
    sleep 0.1
done
xdpyinfo >/dev/null
openbox >"$evidence/window-manager.log" 2>&1 &
wm_pid=$!
sleep 0.2
kill -0 "$wm_pid"
dependencies="${DEPENDENCY_CP:-/work/lib/dyn4j-6.0.0.jar:/work/lib/jogl-all-2.3.2.jar:/work/lib/gluegen-rt-2.3.2.jar}"
classes="${CLASSES_DIR:-/work/classes}"
/jdk/bin/java -Djava.awt.headless=false -cp "$classes:$dependencies:/work/samples/src/main/java" org.dyn4j.samples.framework.SceneObserver "$scene" "$seconds" >"$evidence/observer.log" 2>&1 &
observer_pid=$!
window=''
for attempt in $(seq 1 100); do
    window="$(xdotool search --name "^$scene$" 2>/dev/null | head -1 || true)"
    if [[ -n "$window" ]]; then break; fi
    if ! kill -0 "$observer_pid" 2>/dev/null; then break; fi
    sleep 0.1
done
if [[ -z "$window" ]]; then
    wait "$observer_pid" || true
    python3 /work/tools/migration/validate_scene.py "$scene" "$evidence/observer.log" "$evidence/inputs.log" "$evidence/validation.json" || true
    exit 3
fi
printf 'scene=%s window=%s display=%s\n' "$scene" "$window" "$DISPLAY" >"$evidence/inputs.log"
xdotool windowactivate --sync "$window"
sleep 2
import -window root "$evidence/initial.png"
xdotool mousemove --window "$window" 400 300 click 1
case "$scene" in
    Tracking)
        printf 't~2s key c: show contacts\n' >>"$evidence/inputs.log"
        xdotool key c
        ;;
    Pyramid)
        printf 't~2s drag left mouse: (388,365) -> (520,270), hold 1s; t~5s key r: reset\n' >>"$evidence/inputs.log"
        xdotool mousemove --window "$window" 388 365 mousedown 1
        sleep 0.2
        xdotool mousemove --window "$window" 520 270
        sleep 1
        xdotool mouseup 1
        import -window root "$evidence/interaction.png"
        sleep 1
        xdotool keydown r
        sleep 0.2
        xdotool keyup r
        ;;
    Crank)
        printf 't~2s no control; observe motor motion\n' >>"$evidence/inputs.log"
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
        ;;
    Truck)
        printf 't~2s keydown Right 7s, keyup Right; key s 1s: brake\n' >>"$evidence/inputs.log"
        xdotool keydown Right
        sleep 7
        xdotool keyup Right
        import -window root "$evidence/drive.png"
        xdotool keydown s
        sleep 1
        xdotool keyup s
        ;;
esac
sleep 1
import -window root "$evidence/after-input.png"
observer_status=0
wait "$observer_pid" || observer_status=$?
observer_pid=''
validation_status=0
python3 /work/tools/migration/validate_scene.py "$scene" "$evidence/observer.log" "$evidence/inputs.log" "$evidence/validation.json" || validation_status=$?
if (( observer_status != 0 || validation_status != 0 )); then
    exit 1
fi
