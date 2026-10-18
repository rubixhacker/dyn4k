import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare

import exact_consistency
import nominal_zero
import receipt


def recorder_sources(fixture):
    if fixture["key"] == "nominal-free-motion":
        root = Path(__file__).resolve().parent
        return sorted((root / "calibration").glob("*.java")) + [root / "runtime" / "RuntimeStamp.java"]
    return exact_consistency.recorder_sources(fixture)


def diagnostic(args):
    fixture = receipt.load_fixture(args.fixture, Path(__file__).resolve().parents[1] / "fixtures.json")
    reference = compare.audit_reference(fixture, args.reference)
    if reference["status"] != "PASSED":
        raise compare.Rejected("frozen reference audit failed: " + reference["reason"])
    counts = compare.check_counts(compare.records(args.trace), fixture, reference=False)
    observed = exact_consistency.identity(args.trace, args.artifact, args.source_commit,
                                          recorder_sources(fixture))
    runtime = dict(observed["runtime"])
    runtime["process_command_sha256"] = observed["process_sha256"]
    runtime["runtime_stamp_sha256"] = observed["runtime_stamp_sha256"]
    bound = {
        "fixture_key": args.fixture,
        "source_sha256": observed["source_archive_sha256"],
        "source_hash_method": "SHA-256 of git archive --format=tar source_commit",
        "artifact_sha256": observed["artifact_sha256"],
        "artifact_path": observed["artifact_path"],
        "candidate_commit": args.source_commit,
        "trace_sha256": observed["trace_sha256"],
        "reference_source_revision": fixture["baseline_source_revision"],
        "reference_artifact_sha256": fixture["baseline_jar_sha256"],
        "reference_trace_sha256": fixture["reference"]["gzip_sha256"],
        "expected_counts": fixture["counts"],
        "executed_counts": counts,
        "skipped": 0,
        "build_config_sha256": receipt.build_config_hash(),
        "runtime": runtime,
    }
    if set(bound) != receipt.RECEIPT_FIELDS:
        raise compare.Rejected("diagnostic receipt schema differs")
    output = Path(args.output)
    output.mkdir(exist_ok=False)
    receipt_path = output / "receipt.json"
    with receipt_path.open("x") as stream:
        json.dump(bound, stream, sort_keys=True, indent=2)
        stream.write("\n")
    if args.fixture == "nominal-free-motion":
        outcome = nominal_zero.compare_pair(fixture, args.reference, args.trace, receipt_path,
                                            observed["source_archive_sha256"], observed["artifact_sha256"],
                                            args.source_commit)
    else:
        outcome = compare.compare(fixture, args.reference, args.trace, receipt_path,
                                  observed["source_archive_sha256"], observed["artifact_sha256"],
                                  args.source_commit)
    report = {"scope": "COHERENT_STAGED_JVM_DIAGNOSTIC_NOT_FINAL_INTEGRATION",
              "identity": observed, "reference": reference,
              "zero": outcome.get("nominal_positive_zero"), "comparison": outcome}
    with (output / "result.json").open("x") as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return report


def main():
    parser = argparse.ArgumentParser(description="Compare a coherent staged JVM trace")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = diagnostic(args)
        status = result["comparison"]["status"]
        output = {"status": status, "output": args.output,
                  "trace_sha256": result["identity"]["trace_sha256"]}
    except (compare.Rejected, OSError, ValueError, KeyError, TypeError) as error:
        output = {"status": "FAILED", "reason": str(error)}
    print(json.dumps(output, sort_keys=True))
    raise SystemExit(0 if output["status"] == "PASSED" else 1)


if __name__ == "__main__":
    main()
