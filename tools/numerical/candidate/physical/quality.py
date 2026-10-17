import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import compare
import weld_pulley_quality as frozen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import receipt


ROOT = Path(__file__).resolve().parents[4]


def audit(case, trace, declaration, manifest, commit, artifact_hash, capture_hash):
    frozen.phases(declaration)
    expected_counts = {"inputs": 1, "event": 3 * declaration["steps_per_case"],
                       "state": declaration["steps_per_case"]}
    if manifest["cases"][case]["counts"] != expected_counts:
        raise compare.Rejected("frozen case counts differ")
    rows = compare.records(trace)
    try:
        _, header = next(rows)
    except StopIteration as error:
        raise compare.Rejected("empty candidate trace") from error
    required = {"kind": "inputs", "case": case,
                "declaration_sha256": manifest["declaration_sha256"],
                "capture_sha256": capture_hash,
                "source_revision": commit,
                "jar_sha256": artifact_hash,
                "step_seconds": declaration["step_seconds"],
                "steps": declaration["steps_per_case"]}
    if header != required:
        raise compare.Rejected("candidate input header or identity differs")
    metrics = {key: {"checked": 0, "failed": 0, "maximum": "0", "first_failure": None}
               for key in declaration["cases"][case]["metrics"]}
    maxima = {key: 0 for key in metrics}
    for step in range(1, declaration["steps_per_case"] + 1):
        for order, callback in enumerate(frozen.CALLBACKS):
            try:
                _, row = next(rows)
            except StopIteration as error:
                raise compare.Rejected("missing candidate callback") from error
            if row != {"kind": "event", "step": step, "order": order, "callback": callback}:
                raise compare.Rejected(f"callback differs at step {step}, order {order}")
        try:
            _, row = next(rows)
        except StopIteration as error:
            raise compare.Rejected("missing candidate state") from error
        if row.keys() != {"kind", "step", "state"} or row["kind"] != "state" or row["step"] != step:
            raise compare.Rejected(f"state order or schema differs at step {step}")
        values = frozen.weld(row["state"]) if case == "weld-spring-equal" else frozen.pulley(row["state"])
        phase = "excitation" if step <= declaration["phases"][0][2] else "long-run"
        for name, (lower, upper) in values.items():
            metric = metrics[name]
            metric["checked"] += 1
            maxima[name] = max(maxima[name], upper)
            ceiling = frozen.limit(declaration, case, name)
            if lower <= ceiling < upper:
                raise compare.Rejected(f"physical enclosure straddles limit at step {step}")
            if lower > ceiling:
                metric["failed"] += 1
                if metric["first_failure"] is None:
                    metric["first_failure"] = {"step": step, "phase": phase,
                                               "value_enclosure": [frozen.shown(lower), frozen.shown(upper)],
                                               "limit": str(ceiling)}
    try:
        next(rows)
    except StopIteration:
        pass
    else:
        raise compare.Rejected("extra candidate records")
    for name, maximum in maxima.items():
        metrics[name]["maximum"] = frozen.shown(maximum)
    return {"status": "PHYSICAL_FAILED" if any(item["failed"] for item in metrics.values()) else "PHYSICAL_PASSED",
            "scope": "CANDIDATE_STAGED_JVM", "case": case, "counts": expected_counts,
            "metrics": metrics}


def main():
    parser = argparse.ArgumentParser(description="Audit candidate Weld/Pulley represented geometry")
    parser.add_argument("--case", required=True, choices=("weld-spring-equal", "pulley-taut"))
    parser.add_argument("--trace", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()
    declaration_path = ROOT / "tools/numerical/weld-pulley-physical-declaration.json"
    manifest_path = ROOT / "tools/numerical/weld-pulley-physical-manifest.json"
    capture_path = ROOT / "tools/numerical/candidate/physical/WeldPulleyPhysicalCapture.java"
    try:
        declaration_bytes = declaration_path.read_bytes()
        declaration = compare.parse(declaration_bytes)
        manifest = compare.parse(manifest_path.read_bytes())
        if frozen.sha(declaration_bytes) != manifest["declaration_sha256"]:
            raise compare.Rejected("frozen physical declaration hash differs")
        commit = receipt.clean_commit()
        artifact_hash = receipt.sha256(receipt.ARTIFACT.read_bytes())
        capture_hash = receipt.sha256(capture_path.read_bytes())
        result = audit(args.case, args.trace, declaration, manifest, commit, artifact_hash, capture_hash)
        evidence = {"candidate_commit": commit, "source_sha256": receipt.source_hash(),
                    "source_hash_method": "SHA-256 of git archive --format=tar HEAD",
                    "artifact_sha256": artifact_hash, "artifact_path": str(receipt.ARTIFACT.relative_to(ROOT)),
                    "capture_sha256": capture_hash, "build_config_sha256": receipt.build_config_hash(),
                    "runtime": receipt.runtime_identity(), "trace_sha256": receipt.sha256(Path(args.trace).read_bytes()),
                    "reference_trace_sha256": manifest["cases"][args.case]["gzip_sha256"],
                    "expected_counts": result["counts"], "executed_counts": result["counts"],
                    "skipped": 0, "physical": result}
        with Path(args.receipt).open("x", encoding="utf-8") as stream:
            json.dump(evidence, stream, sort_keys=True, indent=2)
            stream.write("\n")
    except (compare.Rejected, OSError, KeyError, ValueError, TypeError) as error:
        result = {"status": "INVALID", "scope": "CANDIDATE_STAGED_JVM", "reason": str(error)}
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "PHYSICAL_PASSED" else
                     2 if result["status"] == "PHYSICAL_FAILED" else 1)


if __name__ == "__main__":
    main()
