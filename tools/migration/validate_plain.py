#!/usr/bin/env python3
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

from truck_timeline import FRAMES as TRUCK_FRAMES, validate as validate_truck_timeline


SCENES = {"Tracking", "Pyramid", "Crank", "Billiards", "Truck"}
EXPECTED = {"Tracking": 10, "Pyramid": 10, "Crank": 9, "Billiards": 9, "Truck": 19}
INPUT_MARKERS = {
    "Tracking": ("key c",),
    "Pyramid": ("drag left mouse", "key r"),
    "Crank": ("observe motor motion",),
    "Billiards": ("keydown plus", "keydown s", "keyup s"),
    "Truck": ("keydown Right", "key s"),
}


def read_text(path):
    try:
        return path.read_text()
    except OSError:
        return ""


def read_png(path):
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 24 or data[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return {"width": width, "height": height, "sha256": hashlib.sha256(data).hexdigest()}


def validate(scene, directory):
    checks = []

    def check(name, passed, evidence=""):
        checks.append({"id": name, "status": "passed" if passed else "failed", "evidence": evidence})

    log = read_text(directory / "application.log")
    inputs = read_text(directory / "inputs.log")
    launch = read_text(directory / "launch.txt")
    try:
        termination = json.loads(read_text(directory / "termination.json"))
    except json.JSONDecodeError:
        termination = {}
    check("original_main_recorded", f"main=org.dyn4j.samples.{scene}" in launch)
    classpath = next((line.split("=", 1)[1] for line in launch.splitlines() if line.startswith("classpath=")), "")
    check("plain_classpath", bool(classpath) and not any(token in classpath for token in
          ("/work/classes:", "SceneObserver", "HookWeaver", "javassist")), classpath)
    check("application_initialized", "Controls:" in log)
    check("no_application_error", not re.search(r"Shouldn't happen|Exception|Error", log))
    check("input_recorded", f"scene={scene}" in inputs and all(marker in inputs for marker in INPUT_MARKERS[scene]))
    check("controlled_close", termination.get("close_requested") is True and termination.get("exited_after_close") is True
          and termination.get("forced_termination") is False and termination.get("exit_code") == 0)
    frames = {}
    for name in ("initial", "after-input", "late"):
        frame = read_png(directory / f"{name}.png")
        frames[name] = frame
        check(f"{name}_frame", frame is not None and frame["width"] == 1024 and frame["height"] == 768,
              str(frame) if frame else "missing or invalid PNG")
    if scene == "Tracking":
        check("own_contact_listener", "BEGIN:" in log and "END:" in log)
    if scene == "Pyramid":
        frame = read_png(directory / "interaction.png")
        frames["interaction"] = frame
        check("interaction_frame", frame is not None and frame["width"] == 1024 and frame["height"] == 768)
    if scene == "Truck":
        for name in TRUCK_FRAMES:
            if name in frames:
                continue
            frame = read_png(directory / f"{name}.png")
            frames[name] = frame
            check(f"{name}_frame", frame is not None and frame["width"] == 1024 and frame["height"] == 768)
        timeline_ok, timeline_evidence = validate_truck_timeline(directory)
        check("truck_timeline", timeline_ok, timeline_evidence)
    failed = sum(item["status"] == "failed" for item in checks)
    return {"scene": scene, "mode": "plain-original-main", "expected": len(checks), "executed": len(checks),
            "failed": failed, "unexecuted": 0, "passed": len(checks) - failed, "checks": checks,
            "frames": frames, "visual_review_status": "UNREVIEWED",
            "visual_physics_review": "reported separately; frame presence is not physics evidence"}


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--summary":
        root = Path(sys.argv[2])
        scenes = {}
        for scene in sorted(SCENES):
            try:
                result = json.loads(read_text(root / scene / "plain-validation.json"))
            except json.JSONDecodeError:
                result = {}
            scenes[scene] = {"expected": EXPECTED[scene], "executed": result.get("executed", 0),
                             "failed": result.get("failed", 0),
                             "unexecuted": EXPECTED[scene] - result.get("executed", 0)}
        totals = {key: sum(item[key] for item in scenes.values()) for key in ("expected", "executed", "failed", "unexecuted")}
        summary = {"mode": "plain-original-main", "scenes": scenes, "totals": totals}
        (root / "check-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(totals))
        raise SystemExit(1 if totals["failed"] or totals["unexecuted"] else 0)
    if len(sys.argv) != 3 or sys.argv[1] not in SCENES:
        raise SystemExit("usage: validate_plain.py SCENE EVIDENCE_DIR")
    directory = Path(sys.argv[2])
    result = validate(sys.argv[1], directory)
    (directory / "plain-validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"{result['scene']}: {result['passed']}/{result['expected']} plain checks; failed={result['failed']}")
    raise SystemExit(1 if result["failed"] else 0)


if __name__ == "__main__":
    main()
