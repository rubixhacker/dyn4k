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
from run import (MATRIX_METHODS, PORTABLE, ROOT, clean_identity, extract_xml, git,
                 method_case_ids, runtime, runtime_identity)


PINNED_JAR_SHA256 = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
PINNED_SOURCE_REVISION = "058bf6d982a0fb89b54050f929f6ea9dae53b714"
BASELINE_PROJECT = PORTABLE / "baseline"
ATTESTATION_SCHEMA = "portable-baseline-attestation/1"


def verifier_source_sha256():
    source = hashlib.sha256()
    for name in ("baseline_capture.py", "run.py", "cases.py", "receipt.py"):
        path = PORTABLE / name
        source.update(name.encode() + b"\0" + path.read_bytes() + b"\0")
    return source.hexdigest()


def _manifest_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _require_raw_archive(root, result):
    methods = result.get("methods", [])
    raw_counts = result.get("raw_counts", {})
    if not isinstance(methods, list) or not all(
            isinstance(item, dict) for item in methods) or \
            not isinstance(raw_counts, dict):
        raise Rejected("baseline raw archive method or case inventory differs")
    cases = raw_counts.get("per_case", {})
    if not isinstance(cases, dict):
        raise Rejected("baseline raw archive method or case inventory differs")
    if [item.get("method") for item in methods] != list(MATRIX_METHODS) or \
            set(cases) != {case["id"] for case in declared_cases()}:
        raise Rejected("baseline raw archive method or case inventory differs")
    lane = root / "baseline-jvm"
    required = [root / "dyn4j-6.0.0.jar", lane / "trace.jsonl"]
    required.extend(lane / "xml" / f"{name}.xml" for name in MATRIX_METHODS)
    required.extend(lane / f"gradle-{name}.log" for name in MATRIX_METHODS)
    required.extend(lane / "cases" / f"{case['id']}.jsonl"
                    for case in declared_cases())
    for file in required:
        if not file.is_file():
            raise Rejected(f"baseline raw archive file is absent: {file}")


def _attestation_fields(root, checked, seal, result):
    for key in ("status", "trace_sha256", "source_sha256",
                "fixture_source_sha256", "baseline_jar_sha256", "case_sha256"):
        if checked.get(key) != seal.get(key):
            raise Rejected("baseline current verification differs from original seal")
    attested = {"schema": ATTESTATION_SCHEMA, "archive_root": str(root),
                "verifier_source_sha256": verifier_source_sha256(),
                "verified_sha256": digest(root / "verified.json"),
                "result_sha256": digest(root / "result.json"),
                "case_map_sha256": _manifest_sha256(seal["case_sha256"]),
                "method_evidence_sha256": _manifest_sha256(result["methods"]),
                "xml_trace_counts": checked["xml_trace_counts"],
                "method_processes_verified": checked["method_processes_verified"],
                "captured_process_proofs": checked["captured_process_proofs"],
                "observed_process_sha256": checked["observed_process_sha256"]}
    for key in ("status", "trace_sha256", "source_sha256",
                "fixture_source_sha256", "baseline_jar_sha256"):
        attested[key] = seal[key]
    return attested


def verify_attestation(root, path):
    root = Path(root).resolve()
    path = Path(path).resolve()
    if path.is_relative_to(root):
        raise Rejected("baseline attestation must be external to the archive")
    attested = json.loads(path.read_text())
    seal = json.loads((root / "verified.json").read_text())
    result = json.loads((root / "result.json").read_text())
    if not all(isinstance(value, dict) for value in (attested, seal, result)):
        raise Rejected("baseline attestation or archive metadata is malformed")
    if attested.get("schema") != ATTESTATION_SCHEMA or \
            attested.get("archive_root") != str(root):
        raise Rejected("current baseline attestation is absent or for another archive")
    if attested.get("verifier_source_sha256") != verifier_source_sha256():
        raise Rejected("baseline attestation verifier source differs")
    if attested.get("verified_sha256") != digest(root / "verified.json") or \
            attested.get("result_sha256") != digest(root / "result.json"):
        raise Rejected("baseline attestation original seal differs")
    for key in ("status", "trace_sha256", "source_sha256",
                "fixture_source_sha256", "baseline_jar_sha256"):
        if attested.get(key) != seal.get(key):
            raise Rejected("baseline attestation source binding differs")
    if attested.get("trace_sha256") != result.get("trace_sha256") or \
            attested.get("case_map_sha256") != _manifest_sha256(seal.get("case_sha256")) or \
            attested.get("method_evidence_sha256") != \
            _manifest_sha256(result.get("methods")):
        raise Rejected("baseline attestation trace, case, or method seal differs")
    _require_raw_archive(root, result)
    checked = verify_archive(root, write_verified=False)
    expected = _attestation_fields(root, checked, seal, result)
    if json.dumps(attested, sort_keys=True, separators=(",", ":"), allow_nan=False) != \
            json.dumps(expected, sort_keys=True, separators=(",", ":"), allow_nan=False):
        raise Rejected("baseline attestation differs from current raw archive verification")
    return attested


def write_attestation(root, path):
    root = Path(root).resolve()
    path = Path(path).resolve()
    if path.is_relative_to(root) or path.exists():
        raise Rejected("baseline attestation output must be new and external")
    checked = verify_archive(root, write_verified=False)
    seal = json.loads((root / "verified.json").read_text())
    result = json.loads((root / "result.json").read_text())
    attested = _attestation_fields(root, checked, seal, result)
    path.write_text(json.dumps(attested, indent=2, sort_keys=True) + "\n")
    return attested


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


def verify_xml_trace(lane, methods, raw_counts, trace_sha256):
    trace = lane / "trace.jsonl"
    if digest(trace) != trace_sha256:
        raise Rejected("baseline original trace hash differs")
    observed = {}
    totals = {"input_records": 0, "completed_cases": 0, "states": 0,
              "tagged_nonfinite_values": 0, "events": 0, "endpoints": 0}
    with trace.open("rb") as whole:
        for method in methods:
            completed = 0
            started = 0
            active = None
            method_order = method_case_ids(method["method"])
            xml = lane / "xml" / f"{method['method']}.xml"
            with xml.open("rb") as source:
                for line in source:
                    if b"NUMERICAL_JSON " not in line:
                        continue
                    payload = line.split(b"NUMERICAL_JSON ", 1)[1].split(b"]]>", 1)[0].rstrip(b"\r\n")
                    if whole.readline() != payload + b"\n":
                        raise Rejected("baseline XML differs from whole trace")
                    row = json.loads(payload)
                    case_id = row.get("id")
                    kind = row.get("kind")
                    if kind == "inputs":
                        if active is not None or started >= len(method_order) or \
                                case_id != method_order[started]:
                            raise Rejected("baseline XML method case order differs")
                        started += 1
                        active = case_id
                    elif active != case_id:
                        raise Rejected("baseline XML row is outside its method case")
                    if kind == "case-end":
                        active = None
                    if case_id not in raw_counts["per_case"]:
                        raise Rejected("baseline XML has an undeclared case")
                    count = observed.setdefault(case_id, {"inputs": 0, "states": 0,
                        "events": 0, "endpoints": 0, "case_ends": 0,
                        "tagged_nonfinite_values": 0})
                    field = {"inputs": "inputs", "state": "states", "event": "events",
                             "endpoint": "endpoints", "case-end": "case_ends"}.get(kind)
                    if field is not None:
                        count[field] += 1
                        if field == "case_ends":
                            completed += 1
                            totals["completed_cases"] += 1
                        elif field == "inputs":
                            totals["input_records"] += 1
                        else:
                            totals[field] += 1
                    tagged = payload.count(b'"nonfinite":')
                    count["tagged_nonfinite_values"] += tagged
                    totals["tagged_nonfinite_values"] += tagged
            if active is not None or started != len(method_order) or \
                    completed != method["completed_cases"]:
                raise Rejected(f"baseline XML method case count differs: {method['method']}")
        if whole.read(1):
            raise Rejected("baseline XML is shorter than whole trace")
    if observed != raw_counts["per_case"]:
        raise Rejected("baseline XML per-case counts differ from capture")
    if any(totals[key] != raw_counts[key] for key in
           ("input_records", "completed_cases", "states", "tagged_nonfinite_values")):
        raise Rejected("baseline XML totals differ from capture")
    if raw_counts["expected_cases"] != len(observed):
        raise Rejected("baseline XML expected case count differs")
    return totals


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


def verify_archive(output, write_verified=True):
    result = json.loads((output / "result.json").read_text())
    lane = output / "baseline-jvm"
    if result["status"] not in ("CAPTURED_WITH_FAILED_ANGLE_PHYSICAL", "FAILED") or \
            (result["status"] == "FAILED" and result.get("reason") !=
             "baseline Angle first nonfinite step changed: 87"):
        raise Rejected("baseline capture failed for an unrelated reason")
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
    xml_trace_counts = verify_xml_trace(lane, result["methods"], result["raw_counts"],
                                        result["trace_sha256"])
    recorded_runtime = result["runtime"]
    if recorded_runtime["method_executions"] != len(MATRIX_METHODS) or \
            digest(recorded_runtime["executable"]) != recorded_runtime["executable_sha256"]:
        raise Rejected("baseline JVM execution identity differs")
    observed_processes = []
    for method in result["methods"]:
        recorded = method.get("process")
        process = runtime("jvm", lane / f"gradle-{method['method']}.log",
                          dependency=output / "dyn4j-6.0.0.jar",
                          require_loaded=recorded is not None)
        if any(recorded_runtime.get(key) != value for key, value in
               runtime_identity(process).items()):
            raise Rejected("baseline method runtime identity differs")
        if recorded is not None:
            archived = recorded.get("dependency", {}).get("argument_files", [])
            for file in archived:
                if digest(file["path"]) != file["sha256"]:
                    raise Rejected("baseline captured argument file differs")
            normalized = json.loads(json.dumps(recorded))
            normalized["dependency"]["argument_files"] = []
            if normalized != process:
                raise Rejected("baseline recorded worker command differs")
        observed_processes.append(process)
    if recorded_runtime.get("dependency_sha256", PINNED_JAR_SHA256) != PINNED_JAR_SHA256:
        raise Rejected("baseline runtime dependency hash differs")
    if "method_process_sha256" in recorded_runtime and \
            hashlib.sha256(json.dumps([item["process"] for item in result["methods"]],
                                   sort_keys=True).encode()).hexdigest() != \
            recorded_runtime["method_process_sha256"]:
        raise Rejected("baseline recorded process inventory differs")
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
        "runtime": recorded_runtime, "xml": result["xml"], "inventory": inventory,
        "xml_trace_counts": xml_trace_counts,
        "method_processes_verified": len(observed_processes),
        "captured_process_proofs": sum("process" in item for item in result["methods"]),
        "observed_process_sha256": _manifest_sha256(observed_processes),
        "trace_counts": inspected, "trace_sha256": digest(lane / "trace.jsonl"),
        "case_sha256": case_sha256, "angle_physical": angle_failure(lane),
        "methods": result["methods"],
    }
    if write_verified:
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
    env = os.environ.copy()
    env["JAVA_TOOL_OPTIONS"] = (env.get("JAVA_TOOL_OPTIONS", "") +
                                " -verbose:class").strip()
    try:
        for method in MATRIX_METHODS:
            started = time.time()
            command = [str(ROOT / "gradlew"), "-p", str(BASELINE_PROJECT), "test",
                       "--tests", f"portable.PortableMatrixTest.{method}",
                       f"-PbaselineJar={jar}", "--rerun-tasks", "--no-daemon",
                       "--console=plain", "--info",
                       "-Dorg.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=1g"]
            log = lane / f"gradle-{method}.log"
            with log.open("x", encoding="utf-8") as stream:
                completed = subprocess.run(command, cwd=ROOT, env=env,
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
            executed = runtime("jvm", log, dependency=jar,
                               proof_dir=lane / "process-proof" / method)
            method_result["process"] = executed
            runtimes.append(runtime_identity(executed))
        result["xml"] = xml
        result["raw_counts"] = raw
        if any(item["gradle_exit"] for item in result["methods"]):
            raise Rejected("baseline test method failed")
        if not runtimes or len(runtimes) != len(MATRIX_METHODS) or any(
                row != runtimes[0] for row in runtimes[1:]):
            raise Rejected("baseline methods lack one consistent executed JVM")
        result["runtime"] = {**runtimes[0], "method_executions": len(runtimes)}
        result["runtime"]["dependency_sha256"] = PINNED_JAR_SHA256
        result["runtime"]["method_process_sha256"] = hashlib.sha256(json.dumps(
            [item["process"] for item in result["methods"]],
            sort_keys=True).encode()).hexdigest()
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
    parser.add_argument("--attest-existing", action="store_true")
    parser.add_argument("--attestation", type=Path)
    args = parser.parse_args()
    if args.verify_existing and args.attest_existing:
        parser.error("choose one existing-archive verification mode")
    if args.attest_existing:
        if not args.output.is_dir() or args.attestation is None:
            parser.error("existing archive and external attestation path are required")
        print(json.dumps(write_attestation(args.output, args.attestation), sort_keys=True))
        return 0
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
