#!/usr/bin/env python3
import json
import math
import re
import sys
from pathlib import Path


SCENES = {"Tracking": 9, "Pyramid": 121, "Crank": 4, "Billiards": 21, "Truck": 35}


def body(sample, index):
    return sample["bodies"][index]


def checks_for(scene, log_text, input_text, samples, parse_errors):
    checks = []

    def check(name, result, evidence=""):
        checks.append({"id": name, "status": "skipped" if result is None else "passed" if result else "failed", "evidence": evidence})

    def when_samples(name, predicate, evidence=""):
        try:
            check(name, bool(predicate()) if samples else None, evidence)
        except (KeyError, IndexError, TypeError, ValueError) as error:
            check(name, False, str(error))

    check("log_present", bool(log_text))
    check("snapshots_present", len(samples) >= 2, f"snapshots={len(samples)}")
    check("snapshots_parseable", not parse_errors, f"parse_errors={len(parse_errors)}")
    check("input_record_present", bool(input_text) and f"scene={scene}" in input_text)
    check("no_error_diagnostics", not re.search(r"Shouldn't happen|Exception|Error", log_text))
    check("clean_game_loop_shutdown", "OBSERVER_SHUTDOWN joined=true disposed=true" in log_text)

    def complete_and_finite():
        for sample in samples:
            if sample["scene"] != scene or sample["bodyCount"] != len(sample["bodies"]) or sample["jointCount"] != len(sample["joints"]):
                return False
            if [item["i"] for item in sample["bodies"]] != list(range(sample["bodyCount"])):
                return False
            if [item["i"] for item in sample["joints"]] != list(range(sample["jointCount"])):
                return False
            if sample["threadId"] <= 1 or not sample["ccdMode"]:
                return False
            for key in ("begin", "persist", "end", "toiCalls", "toiHits", "toiListenerHits", "resets", "steps"):
                if not isinstance(sample[key], int) or sample[key] < 0:
                    return False
            if not math.isfinite(sample["stepDt"]) or sample["stepDt"] < 0:
                return False
            for item in sample["bodies"]:
                if not isinstance(item["rest"], bool) or any(not math.isfinite(item[key]) for key in ("x", "y", "vx", "vy")):
                    return False
            for item in sample["joints"]:
                if not item["type"] or any(not math.isfinite(item[key]) for key in ("motorSpeed", "translation")):
                    return False
        return True

    when_samples("complete_finite_snapshots", complete_and_finite)
    when_samples("one_game_loop_thread", lambda: len({item["threadId"] for item in samples}) == 1)
    when_samples("time_progressed", lambda: all(b["nanos"] > a["nanos"] for a, b in zip(samples, samples[1:])))
    when_samples("steps_progressed", lambda: len(samples) >= 2 and samples[-1]["steps"] > samples[0]["steps"]
                 and all(b["steps"] >= a["steps"] for a, b in zip(samples, samples[1:])))
    when_samples("step_duration_valid", lambda: samples[-1]["stepDt"] > 0
                 and all(item["stepDt"] > 0 for item in samples if item["steps"] > 0))
    when_samples("expected_bodies", lambda: all(item["bodyCount"] == SCENES[scene] for item in samples))

    if scene == "Tracking":
        when_samples("contact_begin", lambda: samples[-1]["begin"] > 0)
        when_samples("contact_persist", lambda: samples[-1]["persist"] > 0)
        when_samples("contact_end", lambda: samples[-1]["end"] > 0)
        check("sample_contact_listener", "BEGIN:" in log_text and "END:" in log_text)
        check("contact_toggle_input", "key c" in input_text)
    elif scene == "Pyramid":
        when_samples("picking_joint", lambda: any(item["jointCount"] == 1 for item in samples))
        when_samples("drag_moved_body", lambda: any(item["jointCount"] == 1 and body(item, 60)["x"] != body(samples[0], 60)["x"] for item in samples))
        when_samples("reset_observed", lambda: any(item["resets"] > 0 and item["jointCount"] == 0 for item in samples))
        check("drag_and_reset_inputs", "drag left mouse" in input_text and "key r" in input_text)
    elif scene == "Crank":
        when_samples("four_joints", lambda: all(item["jointCount"] == 4 for item in samples))
        when_samples("joint_types", lambda: {joint["type"] for joint in samples[0]["joints"]} == {"RevoluteJoint", "PrismaticJoint"})
        when_samples("piston_motion", lambda: len({body(item, 3)["y"] for item in samples}) > 1)
    elif scene == "Billiards":
        shot_index = next((index for index in range(1, len(samples))
                           if any(body(earlier, 5)["rest"] for earlier in samples[:index])
                           and not body(samples[index], 5)["rest"]
                           and body(samples[index], 5)["vx"] != 0), None)
        when_samples("shot_moved_cue", lambda: shot_index is not None)
        when_samples("rack_collision", lambda: shot_index is not None and any(
            item["begin"] > samples[shot_index]["begin"]
            and any(body(item, i)["x"] != body(samples[0], i)["x"] for i in range(6, 21))
            for item in samples[shot_index + 1:]))
        when_samples("balls_settled", lambda: shot_index is not None and any(
            all(body(item, i)["rest"] for i in range(5, 21))
            for item in samples[shot_index + 1:] if item["toiHits"] > samples[shot_index]["toiHits"]))
        when_samples("ccd_detector_calls", lambda: samples[-1]["toiCalls"] > 0)
        when_samples("ccd_detector_hits", lambda: shot_index is not None and samples[-1]["toiHits"] > samples[shot_index]["toiHits"])
        when_samples("ccd_listener_hits", lambda: shot_index is not None and samples[-1]["toiListenerHits"] > samples[shot_index]["toiListenerHits"])
        when_samples("ccd_enabled", lambda: all(item["ccdMode"] != "NONE" for item in samples))
        check("cue_input", all(marker in input_text for marker in ("keydown plus", "keydown s", "keyup s")))
    elif scene == "Truck":
        when_samples("wheel_joints", lambda: all(item["jointCount"] == 2 and all(joint["type"] == "WheelJoint" for joint in item["joints"]) for item in samples))
        when_samples("drive_motor", lambda: any(any(joint["motorSpeed"] != 0 for joint in item["joints"]) for item in samples))
        when_samples("brake_motor", lambda: any(any(joint["motorSpeed"] != 0 for joint in item["joints"]) for item in samples) and all(joint["motorSpeed"] == 0 for joint in samples[-1]["joints"]))
        when_samples("chassis_moved", lambda: body(samples[-1], 2)["x"] != body(samples[0], 2)["x"])
        when_samples("ramp_crossed", lambda: min(body(item, 2)["x"] for item in samples) < 0 < max(body(item, 2)["x"] for item in samples))
        when_samples("brake_reduced_speed", lambda: abs(body(samples[-1], 2)["vx"]) < max(abs(body(item, 2)["vx"]) for item in samples))
        when_samples("suspension_moved", lambda: any(body(item, 2)["x"] > 0 and joint["translation"] != samples[0]["joints"][joint["i"]]["translation"] for item in samples[1:] for joint in item["joints"]))
        when_samples("cargo_moved", lambda: body(samples[-1], 10)["x"] != body(samples[0], 10)["x"] and any(body(item, 2)["x"] > 0 and body(item, 10)["y"] != body(samples[0], 10)["y"] for item in samples[1:]))
        when_samples("ccd_disabled", lambda: all(item["ccdMode"] == "NONE" and item["toiHits"] == 0 for item in samples))
        check("drive_and_brake_inputs", "keydown Right" in input_text and "key s" in input_text)
    return checks


def main():
    if len(sys.argv) != 5 or sys.argv[1] not in SCENES:
        raise SystemExit("usage: validate_scene.py SCENE OBSERVER_LOG INPUT_LOG RESULT_JSON")
    scene, log_path, input_path, result_path = sys.argv[1:]
    log_text = Path(log_path).read_text() if Path(log_path).exists() else ""
    input_text = Path(input_path).read_text() if Path(input_path).exists() else ""
    samples = []
    parse_errors = []
    for number, line in enumerate(log_text.splitlines(), 1):
        if line.startswith("OBS_JSON "):
            try:
                samples.append(json.loads(line[len("OBS_JSON "):]))
            except (ValueError, TypeError) as error:
                parse_errors.append(f"line {number}: {error}")
    checks = checks_for(scene, log_text, input_text, samples, parse_errors)
    result = {
        "scene": scene,
        "expected_checks": len(checks),
        "executed_checks": sum(item["status"] != "skipped" for item in checks),
        "passed_checks": sum(item["status"] == "passed" for item in checks),
        "failed_checks": sum(item["status"] == "failed" for item in checks),
        "unexecuted_checks": sum(item["status"] == "skipped" for item in checks),
        "samples": len(samples),
        "checks": checks,
        "parse_errors": parse_errors,
    }
    Path(result_path).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"VALIDATION scene={scene} expected={result['expected_checks']} executed={result['executed_checks']} failed={result['failed_checks']} unexecuted={result['unexecuted_checks']} samples={len(samples)}")
    return 0 if result["failed_checks"] == 0 and result["unexecuted_checks"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
