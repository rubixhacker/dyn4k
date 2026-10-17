#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import tempfile
from pathlib import Path

from analyze import activity_status
from candidate_runner import API, CORE, IDENTITY, STAGING, check_route, verify_hashes
from measure import sha256, validate_csv


def rejected(action):
    try:
        action()
    except ValueError as exc:
        return {"status": "rejected_as_expected", "reason": str(exc)}
    raise AssertionError("negative control was accepted")


def mutate_csv(source, target, changes):
    with source.open(newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows = list(reader)
    for row in rows:
        row.update(changes)
    with target.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-evidence", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    pilot_root = Path(args.pilot_evidence).resolve()
    evidence = json.loads((pilot_root / "evidence.json").read_text())
    observed = next(item for item in evidence["results"] if item["workload_id"] ==
                    "separated.default.small.60hz.direct_kotlin" and item["mode"] == "timing")
    source = pilot_root / observed["raw"]
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    identity = json.loads(IDENTITY.read_text())
    core = STAGING / CORE
    api = STAGING / API
    controls = {
        "missing_direct_route": rejected(lambda: check_route("direct_kotlin", [core], STAGING)),
        "crossed_compatibility_route": rejected(lambda: check_route("compatibility", [core, api], STAGING)),
    }
    with tempfile.TemporaryDirectory() as folder:
        upstream = Path(folder) / "dyn4j-6.0.0.jar"
        upstream.write_bytes(b"upstream negative control")
        controls["upstream_provider"] = rejected(
            lambda: check_route("compatibility", [core, upstream], STAGING))
        stale = Path(folder) / core.name
        stale.write_bytes(core.read_bytes())
        expected = {str(stale): hashlib.sha256(stale.read_bytes()).hexdigest()}
        stale.write_bytes(stale.read_bytes() + b"stale")
        controls["stale_artifact"] = rejected(lambda: verify_hashes(expected))
    empty = out / "synthetic-empty-scene.csv"
    inactive = out / "synthetic-inactive-scene.csv"
    mutate_csv(source, empty, {"body_count": "0", "awake_count": "0",
                               "linear_speed_sum_m_per_s": "0"})
    controls["empty_scene"] = rejected(
        lambda: validate_csv(empty, "separated", "default", "small", 60,
                             observed["samples"], "timing"))
    rows = mutate_csv(source, inactive, {"awake_count": "0", "linear_speed_sum_m_per_s": "0"})
    validate_csv(inactive, "separated", "default", "small", 60, observed["samples"], "timing")
    status = activity_status(rows, "separated", "default", 100, 60)
    if status != "invalid":
        raise AssertionError(f"inactive scene was accepted: {status}")
    controls["inactive_scene"] = {"status": "rejected_as_expected", "reason": "activity invalid"}
    result = {"schema": 1, "qualification": "unpassed", "source_raw": source.name,
              "source_sha256": sha256(source), "candidate_identity_sha256": sha256(IDENTITY),
              "core_artifact_sha256": identity["sha256"][str(core)],
              "synthetic_empty_sha256": sha256(empty),
              "synthetic_inactive_sha256": sha256(inactive), "controls": controls}
    (out / "negative-controls.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"controls": len(controls), "all_rejected": True,
                      "output": str(out), "qualification": "unpassed"}))


if __name__ == "__main__":
    main()
