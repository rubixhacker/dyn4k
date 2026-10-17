#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

from candidate_runner import IDENTITY, ROOT
from manifest import V1_MANIFEST_SHA256, validate_ccd_fixture_revision
from measure import sha256


REVISION = ROOT / "docs/research/performance-ccd-fixture-v2.json"
TRACE = ROOT / "docs/research/performance-ccd-order-v1/result.json"


def expected_record(identity, identity_hash):
    fixture = json.loads(REVISION.read_text())
    validate_ccd_fixture_revision(fixture)
    trace = json.loads(TRACE.read_text())
    if (trace["source_commit"] != identity["source_commit"] or
            trace["candidate_identity_sha256"] != identity_hash or
            trace["manifest_sha256"] != V1_MANIFEST_SHA256):
        raise ValueError("fixture revision trace identity differs")
    trace_tool = "tools/performance/ccd_route_trace.py"
    committed = subprocess.run(["git", "show", f"{identity['source_commit']}:{trace_tool}"],
                               cwd=ROOT, capture_output=True, check=True).stdout
    committed_trace_tool = hashlib.sha256(committed).hexdigest()
    if trace["trace_tool_sha256"] != committed_trace_tool or sha256(ROOT / trace_tool) != committed_trace_tool:
        raise ValueError("fixture revision trace tool differs")
    raw_root = TRACE.parent
    identities = []
    for route in fixture["body_hash"]["routes"]:
        item = trace["identity"][route]
        raw = raw_root / item["raw"]
        if sha256(raw) != item["sha256"]:
            raise ValueError(f"fixture revision identity raw differs: {route}")
        with raw.open(newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != ["creation_index", "hash_code", "world_center_x", "world_center_y", "bullet"]:
                raise ValueError(f"fixture revision identity channels differ: {route}")
            rows = list(reader)
        if len(rows) != item["rows"] or len(rows) != 27:
            raise ValueError(f"fixture revision identity row count differs: {route}")
        if [int(row["creation_index"]) for row in rows] != list(range(27)) or [int(row["hash_code"]) for row in rows] != list(range(27)):
            raise ValueError(f"fixture revision body hash differs: {route}")
        identities.append(rows)
    if identities[0] != identities[1] or identities[0] != identities[2]:
        raise ValueError("fixture revision route identities differ")
    harness = ROOT / "tools/performance/BaselinePilot.java"
    direct = ROOT / "consumers/performance/src/main/kotlin/performance/DirectFixture.kt"
    return {
        "schema": 1,
        "fixture_version": fixture["version"],
        "fixture_sha256": sha256(REVISION),
        "base_manifest_sha256": V1_MANIFEST_SHA256,
        "candidate_identity_sha256": identity_hash,
        "source_commit": identity["source_commit"],
        "harness_sha256": identity["sha256"][str(harness)],
        "direct_fixture_sha256": identity["sha256"][str(direct)],
        "trace_result_sha256": sha256(TRACE),
        "identity_raw_sha256": trace["identity"]["baseline"]["sha256"],
        "qualification": "unpassed",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    args = parser.parse_args()
    archive = Path(args.archive).resolve()
    identity = json.loads(IDENTITY.read_text())
    record = expected_record(identity, sha256(IDENTITY))
    if sha256(archive / "candidate-identity-at-pilot.json") != record["candidate_identity_sha256"]:
        raise ValueError("fixture revision archive identity differs")
    output = archive / "fixture-revision.json"
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(output), "fixture_version": record["fixture_version"],
                      "fixture_sha256": record["fixture_sha256"], "qualification": "unpassed"}))


if __name__ == "__main__":
    main()
