import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cases import declared_cases
from receipt import Rejected, digest, inspect, records
from run import MATRIX_METHODS, PORTABLE, ROOT, clean_identity, extract_xml, git, runtime


PINNED_JAR_SHA256 = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
PINNED_SOURCE_REVISION = "058bf6d982a0fb89b54050f929f6ea9dae53b714"
BASELINE_PROJECT = PORTABLE / "baseline"


def verify_baseline_jar(path):
    if not Path(path).is_file() or digest(path) != PINNED_JAR_SHA256:
        raise Rejected("pinned dyn4j 6.0.0 JAR is absent or has changed bytes")
    return PINNED_JAR_SHA256


def fixture_source_sha256():
    names = sorted(path for directory in (PORTABLE / "src/commonMain/kotlin",
                                           PORTABLE / "src/commonTest/kotlin")
                   for path in directory.rglob("*.kt"))
    names += [BASELINE_PROJECT / "build.gradle.kts", BASELINE_PROJECT / "settings.gradle.kts"]
    result = hashlib.sha256()
    for path in names:
        result.update(str(path.relative_to(PORTABLE)).encode())
        result.update(b"\0")
        result.update(path.read_bytes())
        result.update(b"\0")
    return result.hexdigest()


def baseline_inventory(raw, xml):
    expected = {case["id"]: case for case in declared_cases()}
    observed = raw["per_case"]
    if observed.keys() != expected.keys():
        raise Rejected("baseline case identity differs from declared matrix")
    if raw["input_records"] != len(expected) or raw["completed_cases"] != len(expected):
        raise Rejected("baseline completed case count differs")
    if raw["states"] != sum(case["steps"] for case in expected.values()):
        raise Rejected("baseline state count differs")
    for case_id, case in expected.items():
        actual = observed[case_id]
        if (actual["inputs"] != 1 or actual["case_ends"] != 1 or
                actual["states"] != case["steps"]):
            raise Rejected(f"baseline case is incomplete: {case_id}")
        if case_id != "P-J-Angle-ratio-limits-off--1.0" and actual["tagged_nonfinite_values"]:
            raise Rejected(f"unexpected nonfinite baseline case: {case_id}")
    if any(xml.get(key) != expected_value for key, expected_value in
           (("tests", len(MATRIX_METHODS)), ("skipped", 0), ("failures", 0), ("errors", 0))):
        raise Rejected("baseline JUnit methods are incomplete")
    return {"cases": len(expected), "states": raw["states"],
            "tagged_nonfinite_values": sum(item["tagged_nonfinite_values"]
                                            for item in observed.values())}


def angle_failure(lane):
    case = lane / "cases/P-J-Angle-ratio-limits-off--1.0.jsonl"
    first_nonfinite_step = None
    first_angular_velocity_nonfinite_step = None
    first_nonfinite_fields = []

    def tagged_fields(value, path):
        if isinstance(value, dict):
            if "nonfinite" in value:
                yield path
            else:
                for key, child in value.items():
                    yield from tagged_fields(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from tagged_fields(child, f"{path}[{index}]")

    for row in records(case, allow_tagged_nonfinite=True):
        if row.get("kind") != "state":
            continue
        if first_nonfinite_step is None:
            first_nonfinite_fields = list(tagged_fields(row["state"], "state"))
            if first_nonfinite_fields:
                first_nonfinite_step = row["step"]
        if first_angular_velocity_nonfinite_step is None and any(
                isinstance(body.get("angularVelocity"), dict) and
                "nonfinite" in body["angularVelocity"]
                for body in row["state"]["bodies"]):
            first_angular_velocity_nonfinite_step = row["step"]
        if first_nonfinite_step is not None and first_angular_velocity_nonfinite_step is not None:
            break
    if first_nonfinite_step != 87:
        raise Rejected(f"baseline Angle first nonfinite step changed: {first_nonfinite_step}")
    if first_angular_velocity_nonfinite_step != 171:
        raise Rejected("baseline Angle angular velocity first nonfinite step changed: " +
                       str(first_angular_velocity_nonfinite_step))
    return {"status": "FAILED_PHYSICAL", "case_id": "P-J-Angle-ratio-limits-off--1.0",
            "first_nonfinite_step": first_nonfinite_step,
            "first_nonfinite_fields": first_nonfinite_fields,
            "first_angular_velocity_nonfinite_step": first_angular_velocity_nonfinite_step}


def verify_method_files(lane, methods):
    if len({item["method"] for item in methods}) != len(methods):
        raise Rejected("duplicate baseline method")
    for item in methods:
        if item["gradle_exit"]:
            raise Rejected(f"baseline method failed: {item['method']}")
        method = item["method"]
        for file, field, label in ((lane / "xml" / f"{method}.xml", "xml_sha256", "XML"),
                                   (lane / f"gradle-{method}.log", "log_sha256", "log")):
            if not file.is_file() or digest(file) != item[field]:
                raise Rejected(f"baseline {label} hash differs: {method}")


def verify_case_slices(lane, expected_ids):
    expected_ids = set(expected_ids)
    if not expected_ids:
        raise Rejected("baseline case set is empty")
    active = None
    seen = set()
    case_stream = None
    try:
        with (lane / "trace.jsonl").open("rb") as stream:
            for line in stream:
                row = json.loads(line)
                case_id = row.get("id")
                if row.get("kind") == "inputs":
                    if active is not None or case_id not in expected_ids or case_id in seen:
                        raise Rejected("baseline trace case identity differs")
                    active = case_id
                    case_stream = (lane / "cases" / f"{case_id}.jsonl").open("rb")
                if active != case_id or case_stream is None or case_stream.readline() != line:
                    raise Rejected(f"baseline case slice differs: {case_id}")
                if row.get("kind") == "case-end":
                    if case_stream.read(1):
                        raise Rejected(f"baseline case slice has extra records: {case_id}")
                    case_stream.close()
                    case_stream = None
                    seen.add(case_id)
                    active = None
    finally:
        if case_stream is not None:
            case_stream.close()
    if active is not None or seen != expected_ids:
        raise Rejected("baseline case slice set differs")
    return {case_id: digest(lane / "cases" / f"{case_id}.jsonl") for case_id in sorted(seen)}


def verify_archive(output):
    result = json.loads((output / "result.json").read_text())
    lane = output / "baseline-jvm"
    verify_baseline_jar(output / "dyn4j-6.0.0.jar")
    if result["baseline_jar_sha256"] != PINNED_JAR_SHA256 or \
            result["baseline_source_revision"] != PINNED_SOURCE_REVISION:
        raise Rejected("baseline source identity differs")
    if result["fixture_source_sha256"] != fixture_source_sha256():
        raise Rejected("baseline fixture source differs")
    source = hashlib.sha256(git("archive", "--format=tar",
                                result["candidate_recorder_commit"])).hexdigest()
    if source != result["source_sha256"]:
        raise Rejected("captured recorder source archive differs")
    if [item["method"] for item in result["methods"]] != list(MATRIX_METHODS):
        raise Rejected("baseline method inventory differs")
    verify_method_files(lane, result["methods"])
    runtime_identity = result["runtime"]
    if runtime_identity["method_executions"] != len(MATRIX_METHODS) or \
            digest(runtime_identity["executable"]) != runtime_identity["executable_sha256"]:
        raise Rejected("baseline JVM execution identity differs")
    inventory = baseline_inventory(result["raw_counts"], result["xml"])
    if inventory != result["inventory"]:
        raise Rejected("baseline recorded inventory differs")
    inspected = inspect(lane / "trace.jsonl", declared_cases(), allow_tagged_nonfinite=True)
    if inspected["executed_cases"] != inventory["cases"] or \
            inspected["states"] != inventory["states"]:
        raise Rejected("baseline trace inventory differs")
    case_sha256 = verify_case_slices(lane, result["raw_counts"]["per_case"])
    verified = {
        "status": "CAPTURED_WITH_FAILED_ANGLE_PHYSICAL", "qualification": "UNPASSED",
        "capture_status": result["status"], "capture_reason": result.get("reason"),
        "candidate_recorder_commit": result["candidate_recorder_commit"],
        "source_sha256": result["source_sha256"],
        "fixture_source_sha256": result["fixture_source_sha256"],
        "baseline_source_revision": PINNED_SOURCE_REVISION,
        "baseline_jar_sha256": PINNED_JAR_SHA256,
        "runtime": runtime_identity, "xml": result["xml"], "inventory": inventory,
        "trace_counts": inspected, "trace_sha256": digest(lane / "trace.jsonl"),
        "case_sha256": case_sha256, "angle_physical": angle_failure(lane),
        "methods": result["methods"],
    }
    (output / "verified.json").write_text(json.dumps(verified, indent=2, sort_keys=True) + "\n")
    return verified


def capture(output, baseline_jar):
    commit, source_sha256 = clean_identity()
    fixture_sha256 = fixture_source_sha256()
    verify_baseline_jar(baseline_jar)
    output.mkdir(parents=True, exist_ok=False)
    jar = output / "dyn4j-6.0.0.jar"
    shutil.copyfile(baseline_jar, jar)
    verify_baseline_jar(jar)
    lane = output / "baseline-jvm"
    lane.mkdir()
    result = {"status": "FAILED", "qualification": "UNPASSED",
              "candidate_recorder_commit": commit, "source_sha256": source_sha256,
              "fixture_source_sha256": fixture_sha256,
              "baseline_source_revision": PINNED_SOURCE_REVISION,
              "baseline_jar_sha256": PINNED_JAR_SHA256, "methods": []}
    raw = {"expected_cases": len(declared_cases()), "input_records": 0,
           "completed_cases": 0, "states": 0, "tagged_nonfinite_values": 0,
           "per_case": {}}
    xml = {key: 0 for key in ("tests", "skipped", "failures", "errors")}
    runtimes = []
    try:
        for method in MATRIX_METHODS:
            started = time.time()
            command = [str(ROOT / "gradlew"), "-p", str(BASELINE_PROJECT), "test",
                       "--tests", f"portable.PortableMatrixTest.{method}",
                       f"-PbaselineJar={jar}", "--rerun", "--no-daemon",
                       "--console=plain", "--info",
                       "-Dorg.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=1g"]
            log = lane / f"gradle-{method}.log"
            with log.open("x", encoding="utf-8") as stream:
                completed = subprocess.run(command, cwd=ROOT, env=os.environ.copy(),
                                           stdout=stream, stderr=subprocess.STDOUT,
                                           check=False)
            method_result = {"method": method, "gradle_exit": completed.returncode,
                             "log_sha256": digest(log)}
            result["methods"].append(method_result)
            matching = sorted((BASELINE_PROJECT / "build/test-results/test").glob(
                "TEST-*PortableMatrixTest*.xml"))
            if len(matching) != 1 or matching[0].stat().st_mtime < started:
                method_result["reason"] = "baseline XML is missing or stale"
                continue
            _, attributes, counts = extract_xml("jvm", lane, method, matching[0])
            method_result["xml"] = attributes
            method_result["xml_sha256"] = digest(lane / "xml" / f"{method}.xml")
            method_result["completed_cases"] = counts["completed_cases"]
            for key in xml:
                xml[key] += int(attributes.get(key, "-1"))
            for key in ("input_records", "completed_cases", "states", "tagged_nonfinite_values"):
                raw[key] += counts[key]
            if raw["per_case"].keys() & counts["per_case"].keys():
                raise Rejected("baseline case appears in more than one method")
            raw["per_case"].update(counts["per_case"])
            runtimes.append(runtime("jvm", log))
        result["xml"] = xml
        result["raw_counts"] = raw
        if any(item["gradle_exit"] for item in result["methods"]):
            raise Rejected("baseline test method failed")
        if not runtimes or len(runtimes) != len(MATRIX_METHODS) or any(
                row != runtimes[0] for row in runtimes[1:]):
            raise Rejected("baseline methods lack one consistent executed JVM")
        result["runtime"] = {**runtimes[0], "method_executions": len(runtimes)}
        result["inventory"] = baseline_inventory(raw, xml)
        result["angle_physical"] = angle_failure(lane)
        if clean_identity() != (commit, source_sha256) or fixture_source_sha256() != fixture_sha256:
            raise Rejected("portable recorder source changed during baseline capture")
        result["trace_sha256"] = digest(lane / "trace.jsonl")
        result["status"] = "CAPTURED_WITH_FAILED_ANGLE_PHYSICAL"
    except (Rejected, OSError, EOFError, KeyError, IndexError, TypeError, ValueError) as error:
        result["reason"] = str(error)
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-jar", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()
    if args.verify_existing:
        if not args.output.is_dir():
            parser.error("existing baseline output is absent")
        verified = verify_archive(args.output.resolve())
        print(json.dumps({key: value for key, value in verified.items()
                          if key not in ("methods", "case_sha256")}, sort_keys=True))
        return 0
    if args.baseline_jar is None:
        parser.error("--baseline-jar is required for capture")
    if args.output.exists():
        parser.error("output already exists")
    result = capture(args.output.resolve(), args.baseline_jar.resolve())
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("methods", "raw_counts")}, sort_keys=True))
    return 0 if result["status"] == "CAPTURED_WITH_FAILED_ANGLE_PHYSICAL" else 1


if __name__ == "__main__":
    sys.exit(main())
