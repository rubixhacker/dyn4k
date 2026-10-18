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
from receipt import Rejected, digest, records
from run import MATRIX_METHODS, PORTABLE, ROOT, clean_identity, extract_xml, runtime


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
    for row in records(case, allow_tagged_nonfinite=True):
        if row.get("kind") == "state" and '"nonfinite":' in json.dumps(row, separators=(",", ":")):
            if row["step"] != 171:
                raise Rejected(f"baseline Angle first nonfinite step changed: {row['step']}")
            return {"status": "FAILED_PHYSICAL", "first_nonfinite_step": row["step"],
                    "case_id": row["id"]}
    raise Rejected("baseline Angle nonfinite control is absent")


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
    parser.add_argument("--baseline-jar", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    result = capture(args.output.resolve(), args.baseline_jar.resolve())
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("methods", "raw_counts")}, sort_keys=True))
    return 0 if result["status"] == "CAPTURED_WITH_FAILED_ANGLE_PHYSICAL" else 1


if __name__ == "__main__":
    sys.exit(main())
