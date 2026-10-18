import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare

import receipt
import nominal_zero
import default_policy


ROOT = Path(__file__).resolve().parents[3]


def consumer(fixture, output):
    key = fixture["key"]
    if key == "nominal-free-motion":
        return "calibration", f"{output} motion {fixture['id']}"
    if key.startswith("default-sleep-"):
        return "default", str(output)
    if key.startswith("configured-"):
        _, hz, repetition = key.split("-")
        return "configured", f"{output} {hz} {repetition[1:]}"
    if key == "weld-enabled-equal":
        return "calibration", f"{output} joints {fixture['id']}"
    if key.startswith("pulley-"):
        return "calibration", f"{output} joints P-JINT-Pulley-slack-transition"
    raise compare.Rejected("unrecognized fixture consumer")


def capture(args):
    fixture = receipt.load_fixture(args.fixture, ROOT / "tools/numerical/fixtures.json")
    receipt.clean_commit()
    if not receipt.ARTIFACT.is_file():
        raise compare.Rejected("staged JVM artifact is missing")
    output = Path(args.output).resolve()
    if output.exists():
        raise compare.Rejected("output directory already exists")
    project, arguments = consumer(fixture, output)
    output.mkdir(parents=True)
    command = [str(ROOT / "gradlew"), "-p", "tools/numerical/candidate", "--no-daemon",
               f":{project}:run", f"--args={arguments}"]
    with (output / "run.log").open("x", encoding="utf-8") as log:
        completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                   check=False)
    if completed.returncode:
        raise compare.Rejected(f"staged consumer exited {completed.returncode}; see run.log")
    trace = output / fixture["reference"]["file"]
    if not trace.is_file():
        raise compare.Rejected("staged consumer omitted the frozen fixture member")
    counts = receipt.inspect(trace, fixture)
    seal_args = argparse.Namespace(fixture=args.fixture, trace=str(trace), reference=args.reference,
                                   artifact=None, output=str(output / "receipt.json"))
    evidence = receipt.seal(seal_args, fixture, counts)
    if args.fixture == "nominal-free-motion":
        outcome = nominal_zero.compare_pair(fixture, args.reference, trace, output / "receipt.json",
                                            evidence["source_sha256"], evidence["artifact_sha256"],
                                            evidence["candidate_commit"])
    elif args.fixture.startswith("default-sleep-"):
        outcome = default_policy.compare_pair(fixture, args.reference, trace, output / "receipt.json",
                                              evidence["source_sha256"], evidence["artifact_sha256"],
                                              evidence["candidate_commit"])
    else:
        outcome = compare.compare(fixture, args.reference, trace, output / "receipt.json",
                                  evidence["source_sha256"], evidence["artifact_sha256"],
                                  evidence["candidate_commit"])
    with (output / "comparison.json").open("x", encoding="utf-8") as stream:
        json.dump(outcome, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return {"status": outcome["status"], "trace": str(trace),
            "trace_sha256": evidence["trace_sha256"], "counts": counts,
            "comparison": outcome}


def main():
    parser = argparse.ArgumentParser(description="Capture and compare one frozen staged JVM fixture")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = capture(args)
    except (compare.Rejected, OSError, KeyError, TypeError, ValueError,
            subprocess.CalledProcessError) as error:
        result = {"status": "FAILED", "reason": str(error)}
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "PASSED" else 1)


if __name__ == "__main__":
    main()
