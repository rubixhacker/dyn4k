import argparse
import hashlib
import json
import re
import runpy
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath, PureWindowsPath


sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "compatibility"))
import windows_collision_focus as focus


REPO = Path(__file__).resolve().parents[3]
SCALAR = runpy.run_path(str(Path(__file__).with_name("validate-scalar-control.py")))
ENGINE_SOURCES = (
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/geometry/Vector2.kt",
    "dyn4k-core/src/commonMain/kotlin/org/dyn4j/geometry/NearestSqrt.kt",
    "dyn4k-core/src/nativeMain/kotlin/org/dyn4j/geometry/NearestSqrtPlatform.kt",
    "dyn4k-core/src/jvmMain/kotlin/org/dyn4j/geometry/NearestSqrtPlatform.kt",
    "dyn4k-core/src/androidMain/kotlin/org/dyn4j/geometry/NearestSqrtPlatform.kt",
    "dyn4k-core/src/jsMain/kotlin/org/dyn4j/geometry/NearestSqrtPlatform.kt",
    "dyn4k-core/src/wasmJsMain/kotlin/org/dyn4j/geometry/NearestSqrtPlatform.kt",
    "dyn4k-core/src/wasmWasiMain/kotlin/org/dyn4j/geometry/NearestSqrtPlatform.kt",
)
PROBE_SOURCE = "tools/diagnostic/windows_collision/SqrtOperationNativeProbe.kt"
JVM_PROBE_SOURCE = "tools/diagnostic/windows_collision/SqrtOperationJvmProbe.java"
PROBE_SOURCES = (PROBE_SOURCE, JVM_PROBE_SOURCE)
PROBE_INPUTS = (
    ("CirclePolygon.edge3", 4598175219545276415, 4602678819172646911),
    ("CapsuleSlice.epa4", 4607182418800017407, 4607182418800017407),
    ("CirclePolygon.epa3", 4607182418800017407, 4607182418800017407),
    ("CircleSegment.epa2", 4607182418800017407, 4607182418800017407),
    ("CircleSlice.epa35", 4607182418800017407, 4607182418800017407),
    ("PolygonCapsule.sat1", 4607182418800017407, 4607182418800017407),
    ("PolygonCapsule.sat4", 4607182418800017407, 4607182418800017407),
)
PROBE_NEIGHBORS = (
    (4602678819172646909, 4602678819172646910, 4602678819172646910,
     4602678819172646911, 4602678819172646911, 4602678819172646912,
     4602678819172646912, 4602678819172646913, 4602678819172646913),
    (4607182418800017405, 4607182418800017406, 4607182418800017406,
     4607182418800017407, 4607182418800017407, 4607182418800017408,
     4607182418800017408, 4607182418800017409, 4607182418800017409),
)
PROBE_EDGES = (
    (1, 2188749418902061056), (2, 2190614870947216333),
    (4503599627370495, 2305843009213693951),
    (4503599627370496, 2305843009213693952),
    (4598175219545276416, 4602678819172646912),
    (4607182418800017408, 4607182418800017408),
    (9218868437227405311, 6913025428013711359),
)
CORRECTED_GRADLE_COMMAND = (
    ".\\gradlew.bat", ":dyn4k-core:mingwX64Test",
    "--tests org.dyn4j.collision.narrowphase.WindowsCollisionIntermediateDiagnosticTest",
    *(f"--tests org.dyn4j.coverage.collision.shapes.a.{fixture}Test"
      for fixture in ("CapsuleSlice", "CirclePolygon", "CircleSegment", "CircleSlice",
                      "PolygonCapsule", "PolygonPolygon")),
    "--no-daemon --rerun-tasks --console=plain --info",
)


CONTROL_SUITE = "org.dyn4j.collision.narrowphase.WindowsCollisionPrecisionControlTest"
CONTROL_REPORT = f"TEST-mingwX64Test.{CONTROL_SUITE}.xml"
CONTROL_METHODS = {
    "capsuleSliceDetectGjkPc53": ("CapsuleSlice", "detectGjk"),
    "capsuleSliceGetClipManifoldPc53": ("CapsuleSlice", "getClipManifold"),
    "circlePolygonDetectGjkPc53": ("CirclePolygon", "detectGjk"),
    "circleSegmentDetectGjkPc53": ("CircleSegment", "detectGjk"),
    "circleSliceDetectGjkPc53": ("CircleSlice", "detectGjk"),
    "polygonCapsuleDetectSatPc53": ("PolygonCapsule", "detectSat"),
    "polygonCapsuleGetClipManifoldPc53": ("PolygonCapsule", "getClipManifold"),
    "polygonPolygonDetectSatPc53": ("PolygonPolygon", "detectSat"),
    "polygonPolygonGetClipManifoldPc53": ("PolygonPolygon", "getClipManifold"),
}
STATE_IDS = {f"{fixture}.{method}" for fixture, method in CONTROL_METHODS.values()} | {
    "scalarVectors", "trace"
}
SCALAR_IDS = (
    "CirclePolygon.edge3", "CapsuleSlice.epa4", "CirclePolygon.epa3",
    "CircleSegment.epa2", "CircleSlice.epa35", "PolygonCapsule.sat1",
    "PolygonCapsule.sat4",
)
SCALAR_INPUT_FIELDS = ("x", "y", "xSquared", "ySquared", "sum")
SCALAR_RESULT_FIELDS = ("sqrt", "reciprocal")


def keyed_line(line, prefix, fields):
    parts = line.split("\t")
    if parts[:2] != [prefix, "v1"] or len(parts) != len(fields) + 2:
        raise ValueError(f"unexpected {prefix} row shape")
    values = {}
    for part in parts[2:]:
        key, separator, value = part.partition("=")
        if not separator or key in values:
            raise ValueError(f"malformed or repeated {prefix} field")
        values[key] = value
    if set(values) != set(fields):
        raise ValueError(f"{prefix} field set differs: {set(values) ^ set(fields)}")
    return values


def integer(value, label):
    if not re.fullmatch(r"[0-9]+", value):
        raise ValueError(f"{label} is not an unsigned integer: {value!r}")
    return int(value)


def raw_bits(value, label):
    decimal, separator, bits = value.rpartition("@")
    if not separator or not decimal or not re.fullmatch(r"-?[0-9]+", bits):
        raise ValueError(f"{label} is not decimal@bits")
    focus._number(value, label)
    return int(bits)


def state_records(lines):
    records = {}
    fields = ("id", "phase", "thread", "x87cw", "mxcsr", "status", "setStatus")
    for line in lines:
        if not line.startswith("DYN4K_COLLISION_FP_STATE\t"):
            continue
        row = keyed_line(line, "DYN4K_COLLISION_FP_STATE", fields)
        key = (row["id"], row["phase"])
        if row["id"] not in STATE_IDS or row["phase"] not in {"before", "pc53", "restored"} or key in records:
            raise ValueError(f"unexpected or duplicate floating-point state {key}")
        for field in ("thread", "x87cw", "mxcsr", "status"):
            row[field] = integer(row[field], f"{key} {field}")
        if row["setStatus"] != "na":
            row["setStatus"] = integer(row["setStatus"], f"{key} setStatus")
        records[key] = row
    expected = {(id_, phase) for id_ in STATE_IDS for phase in ("before", "pc53", "restored")}
    if set(records) != expected:
        raise ValueError(f"floating-point state set differs: missing={sorted(expected-set(records))}, extra={sorted(set(records)-expected)}")
    for id_ in STATE_IDS:
        before, active, restored = (records[(id_, phase)] for phase in ("before", "pc53", "restored"))
        if any(row["status"] != 0 for row in (before, active, restored)):
            raise ValueError(f"floating-point state read or restore failed for {id_}")
        if len({row["thread"] for row in (before, active, restored)}) != 1:
            raise ValueError(f"floating-point control moved threads for {id_}")
        expected_control_word = before["x87cw"] & ~0x0300 | 0x0200
        if active["x87cw"] != expected_control_word:
            raise ValueError(f"x87 control word differs beyond PC53 for {id_}")
        if before["mxcsr"] & ~0x3f != active["mxcsr"] & ~0x3f:
            raise ValueError(f"SSE control changed while setting PC53 for {id_}")
        if (before["x87cw"], before["mxcsr"] & ~0x3f) != (restored["x87cw"], restored["mxcsr"] & ~0x3f):
            raise ValueError(f"x87 state or SSE control bits were not restored for {id_}")
        if before["setStatus"] != "na" or active["setStatus"] != 0 or restored["setStatus"] != "na":
            raise ValueError(f"control call receipt is malformed for {id_}")
    return records


def scalar_records(lines, java_lines, states):
    fields = ("mode", "id", "thread", *SCALAR_INPUT_FIELDS, *SCALAR_RESULT_FIELDS)
    actual = {}
    for line in lines:
        if not line.startswith("DYN4K_COLLISION_FP_SCALAR\t"):
            continue
        row = keyed_line(line, "DYN4K_COLLISION_FP_SCALAR", fields)
        key = (row["mode"], row["id"])
        if row["mode"] not in {"before", "pc53"} or row["id"] not in SCALAR_IDS or key in actual:
            raise ValueError(f"unexpected or duplicate scalar control {key}")
        row["thread"] = integer(row["thread"], f"{key} thread")
        for name in (*SCALAR_INPUT_FIELDS, *SCALAR_RESULT_FIELDS):
            row[name] = raw_bits(row[name], f"{key} {name}")
        actual[key] = row
    expected = {(mode, id_) for mode in ("before", "pc53") for id_ in SCALAR_IDS}
    if set(actual) != expected:
        raise ValueError(f"scalar control set differs: missing={sorted(expected-set(actual))}")

    java = {}
    for line in java_lines:
        if not line.startswith("DYN4K_COLLISION_SCALAR\tv1\t"):
            continue
        parts = line.split("\t")
        if parts[2] != "provider=java":
            raise ValueError("Java scalar provider is not pinned Java")
        row = dict(part.split("=", 1) for part in parts[3:])
        if row["id"] in java:
            raise ValueError(f"duplicate Java scalar {row['id']}")
        java[row["id"]] = {name: raw_bits(row[name], f"Java {row['id']} {name}")
                           for name in (*SCALAR_INPUT_FIELDS, *SCALAR_RESULT_FIELDS)}
    if set(java) != set(SCALAR_IDS):
        raise ValueError("Java scalar ID set differs")

    result = []
    for id_ in SCALAR_IDS:
        before = actual[("before", id_)]
        active = actual[("pc53", id_)]
        if before["thread"] != states[("scalarVectors", "before")]["thread"] or active["thread"] != states[("scalarVectors", "pc53")]["thread"]:
            raise ValueError(f"scalar control moved threads for {id_}")
        for field in SCALAR_INPUT_FIELDS:
            if before[field] != java[id_][field] or active[field] != java[id_][field]:
                raise ValueError(f"represented scalar input differs from Java for {id_}.{field}")
        result.append({
            "id": id_,
            "sumBits": java[id_]["sum"],
            "beforeRootBits": before["sqrt"],
            "pc53RootBits": active["sqrt"],
            "javaRootBits": java[id_]["sqrt"],
            "beforeReciprocalBits": before["reciprocal"],
            "pc53ReciprocalBits": active["reciprocal"],
            "javaReciprocalBits": java[id_]["reciprocal"],
            "pc53MatchesJava": all(active[name] == java[id_][name] for name in SCALAR_RESULT_FIELDS),
        })
    return result


def failure(case):
    errored = case.find("error")
    if errored is not None:
        raise ValueError(f"XML error is not an assertion failure: {case.attrib.get('name')}")
    failed = case.find("failure")
    if failed is None:
        return None
    lines = (failed.text or "").splitlines()
    return failed.attrib.get("message") or (lines[0] if lines else "failure without message")


def baseline_and_controlled(native_directory, controlled_root):
    controlled_cases = controlled_root.findall("testcase")
    expected_names = {f"{name}[mingwX64]" for name in CONTROL_METHODS} | {
        "scalarVectorsPc53[mingwX64]", "tracePc53[mingwX64]"
    }
    cases = {case.attrib.get("name"): case for case in controlled_cases}
    if len(controlled_cases) != 11 or set(cases) != expected_names or any(case.find("skipped") is not None for case in controlled_cases):
        raise ValueError("controlled case set is incomplete, duplicated, or skipped")

    baseline_failures = set()
    result = []
    original_suites = {}
    for fixture in sorted({fixture for fixture, _ in CONTROL_METHODS.values()}):
        report = Path(native_directory) / (
            f"TEST-mingwX64Test.org.dyn4j.coverage.collision.shapes.a.{fixture}Test.xml"
        )
        root = ET.parse(report).getroot()
        original_cases = root.findall("testcase")
        names = [case.attrib.get("name") for case in original_cases]
        expected = {f"{method}[mingwX64]" for method in ("detectSat", "detectGjk", "gjkDistance", "getClipManifold")}
        if len(names) != 4 or set(names) != expected or any(case.find("skipped") is not None for case in original_cases):
            raise ValueError(f"original suite case set differs for {fixture}")
        original_suites[fixture] = {case.attrib["name"]: case for case in original_cases}
        baseline_failures.update(
            (fixture, name.removesuffix("[mingwX64]"))
            for name, case in original_suites[fixture].items() if failure(case) is not None
        )
    for controlled_method, (fixture, original_method) in CONTROL_METHODS.items():
        original_name = f"{original_method}[mingwX64]"
        original_failure = failure(original_suites[fixture][original_name])
        controlled_failure = failure(cases[f"{controlled_method}[mingwX64]"])
        result.append({
            "fixture": fixture, "method": original_method,
            "baseline": "FAIL" if original_failure else "PASS",
            "baselineMessage": original_failure,
            "pc53": "FAIL" if controlled_failure else "PASS",
            "pc53Message": controlled_failure,
        })
    expected_failures = set(CONTROL_METHODS.values())
    if baseline_failures != expected_failures:
        raise ValueError(f"original nine-case failure set changed: {sorted(baseline_failures)}")
    return result, cases


def validate(args):
    controlled_xml = Path(args.controlled_directory) / CONTROL_REPORT
    controlled_root = ET.parse(controlled_xml).getroot()
    if controlled_root.tag != "testsuite" or controlled_root.attrib.get("name") != f"mingwX64Test.{CONTROL_SUITE}":
        raise ValueError("controlled suite identity differs")
    outcomes, cases = baseline_and_controlled(args.native_directory, controlled_root)
    system_output = controlled_root.find("system-out")
    if system_output is None or system_output.text is None:
        raise ValueError("controlled suite has no raw output")
    lines = system_output.text.splitlines()
    states = state_records(lines)
    scalars = scalar_records(lines, Path(args.java_scalars).read_text(encoding="utf-8").splitlines(), states)
    trace_rows, controlled_ids = focus._records(lines, "dyn4k", "PC53 Native")
    java_rows, java_ids = focus._records(Path(args.java_trace).read_text(encoding="utf-8").splitlines(), "dyn4j-6.0.0", "Java")
    if controlled_ids != java_ids:
        raise ValueError("PC53 trace identities differ from pinned Java")
    Path(args.controlled_trace).write_text("\n".join(trace_rows) + "\n", encoding="utf-8")
    result = {
        "sourceSha": args.source_sha,
        "baselineFailures": 9,
        "controlledFailures": sum(item["pc53"] == "FAIL" for item in outcomes),
        "controlledDiagnosticCases": {
            name: "FAIL" if failure(cases[f"{name}[mingwX64]"]) else "PASS"
            for name in ("scalarVectorsPc53", "tracePc53")
        },
        "traceRows": len(trace_rows), "javaTraceRows": len(java_rows),
        "scalarRows": len(scalars), "stateRows": len(states),
        "scalars": scalars,
        "states": [states[key] for key in sorted(states)],
        "originalAssertions": outcomes,
    }
    Path(args.result).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"PRECISION_CONTROL_RECORDS_OK baselineFailures=9 controlledFailures={result['controlledFailures']} "
          f"scalarCase={result['controlledDiagnosticCases']['scalarVectorsPc53']} "
          f"traceCase={result['controlledDiagnosticCases']['tracePc53']} "
          f"controlledRows={len(trace_rows)} scalarIDs={len(scalars)} stateRows={len(states)}")


def corrected_xml_cases(native_directory):
    reports = sorted(Path(native_directory).glob("TEST-*.xml"))
    if {path.name for path in reports} != set(focus.SUITES.values()) or len(reports) != 7:
        raise ValueError("corrected route requires exactly seven same-run XML suites")
    result = []
    for suite, filename in focus.SUITES.items():
        root = ET.parse(Path(native_directory) / filename).getroot()
        expected_cases = focus.DIAGNOSTIC_CASES if suite.endswith("WindowsCollisionIntermediateDiagnosticTest") else focus.ORIGINAL_CASES[suite]
        cases = root.findall("testcase")
        if root.tag != "testsuite" or root.attrib.get("name") != f"mingwX64Test.{suite}":
            raise ValueError(f"corrected suite identity differs: {suite}")
        if len(cases) != len(expected_cases) or {case.attrib.get("name") for case in cases} != expected_cases:
            raise ValueError(f"corrected case set incomplete or duplicated: {suite}")
        for counter, expected in (("tests", len(expected_cases)), ("failures", 0), ("errors", 0), ("skipped", 0)):
            if root.attrib.get(counter) != str(expected):
                raise ValueError(f"corrected {suite} {counter} counter differs")
        for case in cases:
            if any(case.find(tag) is not None for tag in ("failure", "error", "skipped")):
                raise ValueError(f"corrected case did not pass: {suite}.{case.attrib.get('name')}")
            result.append(f"{suite}.{case.attrib['name']}")
    if len(result) != 30:
        raise ValueError("corrected route has an incomplete 30-case XML set")
    return result


def corrected_scalar_rows(native_text, java_text):
    SCALAR["validate_source_vectors"]()
    SCALAR["validate"](native_text, java_text)
    native = native_text.splitlines()
    java = java_text.splitlines()
    observations = []
    fields = ("provider", "id", *SCALAR_INPUT_FIELDS, *SCALAR_RESULT_FIELDS, "normalized")
    computed_fields = ("xSquared", "ySquared", "sum", *SCALAR_RESULT_FIELDS)
    for native_line, java_line in zip(native, java, strict=True):
        n = keyed_line(native_line, "DYN4K_COLLISION_SCALAR", fields)
        j = keyed_line(java_line, "DYN4K_COLLISION_SCALAR", fields)
        if n["provider"] != "kotlin-native" or j["provider"] != "java" or n["id"] != j["id"]:
            raise ValueError("corrected scalar provider or ID differs")
        bits = {}
        normalized_bits = []
        for row in (n, j):
            provider = row["provider"]
            bits[provider] = {field: raw_bits(row[field], f"{provider} {row['id']}.{field}")
                              for field in (*SCALAR_INPUT_FIELDS, *SCALAR_RESULT_FIELDS)}
            normalized = row["normalized"].split(",")
            if len(normalized) != 2:
                raise ValueError("corrected normalized scalar pair is incomplete")
            normalized_bits.append(tuple(raw_bits(value, f"{provider} normalized") for value in normalized))
        for field in ("x", "y"):
            if bits["kotlin-native"][field] != bits["java"][field]:
                raise ValueError(f"corrected Native/Java input bits differ: {n['id']}.{field}")
        observations.append({
            "id": n["id"],
            "inputBits": {field: bits["java"][field] for field in ("x", "y")},
            "native": {field: n[field] for field in (*computed_fields, "normalized")},
            "java": {field: j[field] for field in (*computed_fields, "normalized")},
            "computedBitEqual": {
                **{field: bits["kotlin-native"][field] == bits["java"][field] for field in computed_fields},
                "normalized": normalized_bits[0] == normalized_bits[1],
            },
        })
    if tuple(row["id"] for row in observations) != SCALAR_IDS:
        raise ValueError("corrected scalar row order differs")
    return observations


def corrected_source_hashes(directory, source_sha):
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("candidate source SHA is malformed")
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                          capture_output=True, check=True, timeout=10, text=True).stdout.strip()
    if head != source_sha:
        raise ValueError("candidate source SHA differs from checkout")
    lines = (Path(directory) / "source-sha256.txt").read_text(encoding="utf-8").splitlines()
    paths = (*ENGINE_SOURCES, *PROBE_SOURCES)
    if len(lines) != len(paths):
        raise ValueError("corrected source hash receipt is incomplete")
    for line, relative in zip(lines, paths, strict=True):
        current = (REPO / relative).read_bytes()
        committed_blob = subprocess.run(["git", "-C", str(REPO), "rev-parse", f"{source_sha}:{relative}"],
                                        capture_output=True, check=True, timeout=10, text=True).stdout.strip()
        checkout_blob = subprocess.run(["git", "-C", str(REPO), "hash-object", f"--path={relative}", relative],
                                       capture_output=True, check=True, timeout=10, text=True).stdout.strip()
        expected = hashlib.sha256(current).hexdigest()
        if checkout_blob != committed_blob or line != f"{expected}  {relative}":
            raise ValueError(f"corrected source differs from committed object or receipt: {relative}")
    return len(paths)


def corrected_probe_rows(text):
    def signed_bits(value):
        if not re.fullmatch(r"-?[0-9]+", value):
            raise ValueError("corrected probe raw bits are malformed")
        parsed = int(value)
        if not -(1 << 63) <= parsed < (1 << 63):
            raise ValueError("corrected probe raw bits exceed binary64 width")
        return parsed

    rows = text.splitlines()
    if len(rows) != 33:
        raise ValueError(f"corrected probe output is partial or extra: rows={len(rows)}")
    observed = []
    for row, (case_id, sum_bits, root_bits) in zip(rows[:7], PROBE_INPUTS, strict=True):
        parts = row.split("\t")
        if len(parts) != 7 or parts[:3] != ["input", case_id, str(sum_bits)]:
            raise ValueError(f"corrected probe input identity differs: {case_id}")
        baseline, forced_up, corrected_forced, corrected = (signed_bits(part) for part in parts[3:])
        if forced_up != root_bits + 1 or corrected_forced != root_bits or corrected != root_bits:
            raise ValueError(f"corrected probe root bits differ: {case_id}")
        observed.append({"id": case_id, "sumBits": sum_bits, "baselineRootBits": baseline,
                         "correctedRootBits": corrected})
    centers = (PROBE_INPUTS[0][1], PROBE_INPUTS[1][1])
    for center, expected_roots in enumerate(PROBE_NEIGHBORS):
        for index, expected in enumerate(expected_roots):
            parts = rows[7 + center * 9 + index].split("\t")
            if len(parts) != 6 or parts[:5] != ["neighbor", str(center), str(index - 4),
                                                   str(centers[center] + index - 4), str(expected)]:
                raise ValueError(f"corrected probe neighbor differs: {center}.{index}")
            signed_bits(parts[5])
    for index, (bits, expected) in enumerate(PROBE_EDGES):
        parts = rows[25 + index].split("\t")
        if len(parts) != 4 or parts[:3] != ["edge", str(bits), str(expected)]:
            raise ValueError(f"corrected probe edge differs: {index}")
        signed_bits(parts[3])
    if rows[32] != "PASS inputs=7 neighbors=18 edges=7 specials=6 fallback=6 forcedDirections=both":
        raise ValueError("corrected probe completion marker differs")
    return observed


def command_path(raw):
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise ValueError("corrected probe command path is malformed")
    if re.match(r"^[A-Za-z]:\\", raw):
        components = raw.split("\\")[1:]
        if "/" in raw or any(not part or part in (".", "..") or part.endswith((".", " ")) or
                             re.search(r'[<>:"|?*]', part) for part in components):
            raise ValueError("corrected probe Windows command path is malformed")
        return "windows", tuple(part.casefold() for part in PureWindowsPath(raw).parts)
    if raw.startswith("/"):
        components = raw.split("/")[1:]
        if "\\" in raw or any(not part or part in (".", "..") for part in components):
            raise ValueError("corrected probe POSIX command path is malformed")
        return "posix", PurePosixPath(raw).parts
    raise ValueError("corrected probe command path is not absolute")


def command_source_root(raw, relative):
    kind, parts = command_path(raw)
    suffix = tuple(part.casefold() for part in PureWindowsPath(relative).parts) if kind == "windows" else \
        PurePosixPath(relative).parts
    if len(parts) <= len(suffix) or parts[-len(suffix):] != suffix:
        raise ValueError(f"corrected probe source suffix differs: {relative}")
    root = parts[:-len(suffix)]
    local = command_path(str(REPO / relative))
    if kind == "posix":
        if (kind, parts) != local:
            raise ValueError(f"corrected probe source root differs: {relative}")
    elif (kind, parts) != local and \
            (len(root) != 4 or root[1:] != ("a", "dyn4k", "dyn4k")):
        raise ValueError(f"corrected probe Windows checkout root differs: {relative}")
    return kind, root


def command_output_root(raw, mode, local_mode, source_root):
    kind, parts = command_path(raw)
    if kind == "posix":
        if (kind, parts) != command_path(str(local_mode / "sqrt-operation-probe")):
            raise ValueError(f"{mode} compiler output differs from retained mode")
        return kind, parts[:-2]
    suffix = ("windows-collision-focus", "corrected-probe", mode, "sqrt-operation-probe")
    if len(parts) <= len(suffix) or parts[-len(suffix):] != suffix:
        raise ValueError(f"{mode} Windows compiler output suffix differs")
    root = parts[:-len(suffix)]
    local = command_path(str(local_mode / "sqrt-operation-probe"))
    if (kind, parts) != local and (len(root) != 3 or root[1:] != ("a", "_temp")):
        raise ValueError(f"{mode} Windows runner temp root differs")
    if source_root[0] != kind or source_root[1][0] != root[0]:
        raise ValueError(f"{mode} source and output drives differ")
    return kind, root


def corrected_java_output(raw, local_directory):
    prefix = "-OutputDirectory "
    if not isinstance(raw, str) or not raw.startswith(prefix):
        raise ValueError("corrected Java output option differs")
    kind, parts = command_path(raw[len(prefix):])
    if (kind, parts) == command_path(str(local_directory)):
        return
    if kind != "windows" or len(parts) != 5 or parts[1:] != (
            "a", "_temp", "windows-collision-focus", "java"):
        raise ValueError("corrected Java output root or suffix differs")


def corrected_probe_modes(directory):
    root = Path(directory)
    modes = (("debug-g", ("-g",)), ("default", ()), ("optimized-opt", ("-opt",)))
    if (root / "probe-exit-code.txt").read_text(encoding="utf-8").strip() != "0":
        raise ValueError("corrected probe runner did not complete")
    if {path.name for path in root.iterdir() if path.is_dir()} != {name for name, _ in modes}:
        raise ValueError("corrected probe mode set differs")
    results = {}
    compiler_path = source_root = output_root = None
    for name, flags in modes:
        mode = root / name
        for phase in ("compiler", "run"):
            if (mode / f"{phase}-exit-code.txt").read_text(encoding="utf-8").strip() != "0":
                raise ValueError(f"{name} {phase} did not exit zero")
            receipt = json.loads((mode / f"{phase}-receipt.json").read_text(encoding="utf-8"))
            if receipt.get("state") != "EXITED" or receipt.get("childExitCode") != 0:
                raise ValueError(f"{name} {phase} receipt is not a successful child exit")
            if not (mode / ("compiler-stdout.log" if phase == "compiler" else "probe-stdout.tsv")).is_file():
                raise ValueError(f"{name} {phase} stdout missing")
            if not (mode / ("compiler-stderr.log" if phase == "compiler" else "probe-stderr.log")).is_file():
                raise ValueError(f"{name} {phase} stderr missing")
            results[f"{name}-{phase}-receipt"] = receipt
        command = json.loads((mode / "compiler-command.json").read_text(encoding="utf-8"))
        arguments = command.get("arguments")
        if command.get("mode") != name:
            raise ValueError(f"{name} compiler identity differs")
        actual_compiler = command_path(command.get("executable"))
        kind, parts = actual_compiler
        if kind == "windows":
            if len(parts) != 7 or parts[1] != "users" or parts[-4:] != (
                    ".konan", "kotlin-native-prebuilt-windows-x86_64-2.4.20", "bin", "kotlinc-native.bat"):
                raise ValueError(f"{name} Windows compiler distribution differs")
        elif parts[-2:] != ("bin", "kotlinc-native.bat"):
            raise ValueError(f"{name} compiler identity differs")
        if compiler_path is None:
            compiler_path = actual_compiler
        elif actual_compiler != compiler_path:
            raise ValueError(f"{name} compiler differs from the other modes")
        if not isinstance(arguments, list) or len(arguments) != 9 + len(flags) or \
                any(not isinstance(argument, str) for argument in arguments):
            raise ValueError(f"{name} compiler argument count differs")
        common, native, probe = arguments[2:5]
        if arguments[:2] != ["-Xmulti-platform", f"-Xcommon-sources={common}"] or \
                arguments[5:7] != ["-target", "mingw_x64"] or \
                arguments[7:-2] != list(flags) or arguments[-2] != "-o":
            raise ValueError(f"{name} compiler mode, target, or output differs")
        for actual, expected in zip((common, native, probe), (ENGINE_SOURCES[1], ENGINE_SOURCES[2], PROBE_SOURCE), strict=True):
            actual_root = command_source_root(actual, expected)
            if source_root is None:
                source_root = actual_root
            elif actual_root != source_root:
                raise ValueError(f"{name} compiler source root differs: {expected}")
        if source_root[0] != kind:
            raise ValueError(f"{name} compiler and source path forms differ")
        actual_output_root = command_output_root(arguments[-1], name, mode, source_root)
        if output_root is None:
            output_root = actual_output_root
        elif actual_output_root != output_root:
            raise ValueError(f"{name} output root differs from the other modes")
        if results[f"{name}-compiler-receipt"].get("command") != [command["executable"], *arguments]:
            raise ValueError(f"{name} compiler receipt command differs")
        executable = mode / "sqrt-operation-probe.exe"
        expected_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
        if (mode / "executable-sha256.txt").read_text(encoding="utf-8").strip() != f"{expected_hash}  {executable.name}":
            raise ValueError(f"{name} executable hash differs")
        run_command = results[f"{name}-run-receipt"].get("command")
        if not isinstance(run_command, list) or len(run_command) != 1 or \
                command_path(run_command[0]) != command_path(arguments[-1] + ".exe"):
            raise ValueError(f"{name} executed PE differs from retained PE")
        results[name] = corrected_probe_rows((mode / "probe-stdout.tsv").read_text(encoding="utf-8"))
    return {name: results[name] for name, _ in modes}


def validate_corrected(args):
    native = Path(args.native_directory)
    probe = Path(args.probe_directory)
    if (native / "gradle-exit-code.txt").read_text(encoding="utf-8").strip() != "0":
        raise ValueError("corrected focused Gradle test did not exit zero")
    gradle_receipt = json.loads((native / "gradle-receipt.json").read_text(encoding="utf-8"))
    gradle_command = (native / "gradle-command.txt").read_text(encoding="utf-8").splitlines()
    if tuple(gradle_command) != CORRECTED_GRADLE_COMMAND or \
            gradle_receipt.get("state") != "EXITED" or gradle_receipt.get("childExitCode") != 0 or \
            gradle_receipt.get("command") != ["cmd.exe", "/d", "/s", "/c", " ".join(gradle_command)]:
        raise ValueError("corrected focused Gradle command or child receipt differs")
    for name in ("gradle-stdout.log", "gradle-stderr.log", "gradle-console.log"):
        if not (native / name).is_file():
            raise ValueError(f"corrected focused Gradle output missing: {name}")
    if not (native / "gradle-stdout.log").read_bytes():
        raise ValueError("corrected focused Gradle stdout is empty")
    if (native / "test-pe-collector-exit-code.txt").read_text(encoding="utf-8").strip() != "0":
        raise ValueError("corrected debugTest PE collection did not exit zero")
    test_pe = native / "test-pe" / "test.exe"
    if (test_pe.parent / "test-executable-status.txt").read_text(encoding="utf-8").strip() != "OK":
        raise ValueError("corrected debugTest PE status differs")
    test_hash = hashlib.sha256(test_pe.read_bytes()).hexdigest()
    if (test_pe.parent / "test-executable-sha256.txt").read_text(encoding="utf-8").strip() != f"{test_hash}  test.exe":
        raise ValueError("corrected debugTest PE hash differs")
    cases = corrected_xml_cases(native)
    source_count = corrected_source_hashes(probe, args.source_sha)
    java_directory = Path(args.java_trace).parent
    if (java_directory / "java-exit-code.txt").read_text(encoding="utf-8").strip() != "0":
        raise ValueError("corrected pinned Java control did not exit zero")
    for name in ("java-command.txt", "java-stdout.log", "java-stderr.log", "java-console.log"):
        if not (java_directory / name).is_file():
            raise ValueError(f"corrected pinned Java output missing: {name}")
    java_command = (java_directory / "java-command.txt").read_text(encoding="utf-8").splitlines()
    if len(java_command) != 5 or java_command[0] != ".\\tools\\diagnostic\\windows_collision\\run-java-control.ps1" or \
            not java_command[1].startswith("-JdkHome ") or \
            not java_command[2].endswith("dyn4j-6.0.0.jar") or \
            not java_command[3].startswith("-BaselineSource "):
        raise ValueError("corrected pinned Java command is partial or differs")
    corrected_java_output(java_command[4], java_directory)
    if not (java_directory / "java-stdout.log").read_bytes():
        raise ValueError("corrected pinned Java stdout is empty")
    if (java_directory.parent / "baseline-source-revision.txt").read_text(encoding="utf-8").strip() != \
            "058bf6d982a0fb89b54050f929f6ea9dae53b714":
        raise ValueError("corrected pinned Java source revision differs")
    java_stdout = (java_directory / "java-stdout.log").read_text(encoding="utf-8")
    if "PINNED_DYN4J_CONTROL jarSha256=204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e " \
            "sourceRevision=058bf6d982a0fb89b54050f929f6ea9dae53b714" not in java_stdout:
        raise ValueError("corrected pinned Java JAR or source receipt differs")
    java_trace = Path(args.java_trace).read_text(encoding="utf-8")
    native_trace = native / "mingwX64-collision-diagnostics.tsv"
    _, _, native_rows, java_rows = focus.validate(native, args.java_trace, native_trace)
    if native_rows != 72 or java_rows != 72 or not java_trace.strip():
        raise ValueError("corrected trace rows incomplete")
    scalars = corrected_scalar_rows(Path(args.native_scalars).read_text(encoding="utf-8"),
                                    Path(args.java_scalars).read_text(encoding="utf-8"))
    version = (Path(args.native_scalars).parent / "kotlin-native-version.txt").read_text(encoding="utf-8")
    if SCALAR["VERSION_TOKEN"].search(version) is None:
        raise ValueError("corrected Kotlin/Native compiler version differs")
    modes = corrected_probe_modes(probe)
    result = {"route": "corrected-production", "sourceSha": args.source_sha,
              "originalAndDiagnosticPasses": len(cases), "nativeTraceRows": native_rows,
              "javaTraceRows": java_rows, "scalarIDs": [row["id"] for row in scalars],
              "scalarObservations": scalars, "engineSourceHashes": source_count - len(PROBE_SOURCES),
              "probeSourceHashes": len(PROBE_SOURCES),
              "debugTestPeSha256": test_hash, "probeModes": modes}
    Path(args.result).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("CORRECTED_COLLISION_RECORDS_OK xmlCases=30 originalFailures=0 "
          "nativeRows=72 javaRows=72 scalarIDs=7 probeModes=3 engineSources=8 probeSources=2")


def xml_error_self_test():
    controlled = ET.Element("testsuite")
    for name in (*CONTROL_METHODS, "scalarVectorsPc53", "tracePc53"):
        ET.SubElement(controlled, "testcase", name=f"{name}[mingwX64]")
    with tempfile.TemporaryDirectory() as temporary:
        native = Path(temporary)
        methods = ("detectSat", "detectGjk", "gjkDistance", "getClipManifold")
        for fixture in sorted({fixture for fixture, _ in CONTROL_METHODS.values()}):
            suite = ET.Element("testsuite")
            for method in methods:
                case = ET.SubElement(suite, "testcase", name=f"{method}[mingwX64]")
                if (fixture, method) in CONTROL_METHODS.values():
                    ET.SubElement(case, "failure", message="original assertion")
            ET.ElementTree(suite).write(native / (
                f"TEST-mingwX64Test.org.dyn4j.coverage.collision.shapes.a.{fixture}Test.xml"
            ), encoding="utf-8")
        outcomes, _ = baseline_and_controlled(native, controlled)
        assert len(outcomes) == 9 and all(item["baseline"] == "FAIL" and item["pc53"] == "PASS"
                                          for item in outcomes)

        report = native / "TEST-mingwX64Test.org.dyn4j.coverage.collision.shapes.a.CapsuleSliceTest.xml"
        original_bytes = report.read_bytes()
        suite = ET.fromstring(original_bytes)
        case = next(case for case in suite.findall("testcase") if case.get("name") == "detectGjk[mingwX64]")
        case.remove(case.find("failure"))
        ET.SubElement(case, "error", message="runtime error")
        ET.ElementTree(suite).write(report, encoding="utf-8")
        try:
            baseline_and_controlled(native, controlled)
        except ValueError as error:
            assert "XML error" in str(error)
        else:
            raise AssertionError("an original XML error counted as an assertion failure")
        report.write_bytes(original_bytes)

        controlled_case = controlled.find("testcase")
        ET.SubElement(controlled_case, "error", message="control setup error")
        try:
            baseline_and_controlled(native, controlled)
        except ValueError as error:
            assert "XML error" in str(error)
        else:
            raise AssertionError("a controlled XML error counted as an assertion outcome")


def ordinary_selection_self_test():
    repository = Path(__file__).resolve().parents[3]
    ordinary = repository / (
        "dyn4k-core/src/mingwX64Test/kotlin/org/dyn4j/collision/narrowphase/"
        "WindowsCollisionPrecisionControlTest.kt"
    )
    diagnostic = repository / "dyn4k-core/diagnostic/windows-collision/WindowsCollisionPrecisionControlTest.kt"
    build = (repository / "dyn4k-core/build.gradle.kts").read_text(encoding="utf-8")
    focused = (repository / "tools/diagnostic/windows_collision/run-focused-controls.ps1").read_text(encoding="utf-8")
    gate = (
        'if (providers.gradleProperty("windowsCollisionPrecisionDiagnostic").orNull == "true") {',
        'named("mingwX64Test") {',
        'kotlin.srcDir("diagnostic/windows-collision")',
    )
    if ordinary.exists() or not diagnostic.is_file() or not all(part in build for part in gate) \
            or "-PwindowsCollisionPrecisionDiagnostic=true" not in focused:
        raise AssertionError("the precision tests are not restricted to the diagnostic source route")

    sys.path.insert(0, str(repository / "tools/qualification"))
    import full_hosted

    manifest = json.loads((repository / full_hosted.MANIFEST).read_text(encoding="utf-8"))
    selected = full_hosted.expected_cases(manifest, "dyn4k-core")
    extra = (CONTROL_SUITE, "tracePc53")
    if extra in selected:
        raise AssertionError("the frozen ordinary selection includes a diagnostic method")
    with tempfile.TemporaryDirectory() as temporary:
        report = Path(temporary) / "TEST-extra.xml"
        suite = ET.Element("testsuite", tests="1", failures="0", errors="0", skipped="0", time="0.0")
        ET.SubElement(suite, "testcase", classname=f"mingwX64Test.{CONTROL_SUITE}",
                      name="tracePc53[mingwX64]", time="0.0")
        ET.ElementTree(suite).write(report, encoding="utf-8")
        modified = report.stat().st_mtime_ns
        try:
            full_hosted.read_reports([report], selected, "mingwX64", modified - 1, modified + 1)
        except ValueError as error:
            if str(extra) not in str(error):
                raise AssertionError("ordinary selection rejected the report for another reason") from error
        else:
            raise AssertionError("ordinary full-hosted selection accepted an extra diagnostic method")


def self_test():
    example = [
        "DYN4K_COLLISION_FP_STATE\tv1\tid=trace\tphase=before\tthread=7\tx87cw=895\tmxcsr=8064\tstatus=0\tsetStatus=na",
        "DYN4K_COLLISION_FP_STATE\tv1\tid=trace\tphase=pc53\tthread=7\tx87cw=639\tmxcsr=8064\tstatus=0\tsetStatus=0",
        "DYN4K_COLLISION_FP_STATE\tv1\tid=trace\tphase=restored\tthread=7\tx87cw=895\tmxcsr=8064\tstatus=0\tsetStatus=na",
    ]
    lines = []
    for id_ in sorted(STATE_IDS):
        lines.extend(line.replace("id=trace", f"id={id_}") for line in example)
    assert len(state_records(lines)) == 3 * len(STATE_IDS)
    sticky_flags = [
        line.replace("phase=restored\tthread=7\tx87cw=895\tmxcsr=8064", "phase=restored\tthread=7\tx87cw=895\tmxcsr=8096")
        if "id=trace" in line else line for line in lines
    ]
    assert len(state_records(sticky_flags)) == 3 * len(STATE_IDS)
    active_sticky_flags = [
        line.replace("phase=pc53\tthread=7\tx87cw=639\tmxcsr=8064", "phase=pc53\tthread=7\tx87cw=639\tmxcsr=8096")
        if "id=trace" in line else line for line in lines
    ]
    assert len(state_records(active_sticky_flags)) == 3 * len(STATE_IDS)
    for altered in (
        lines[:-1],
        [line.replace("phase=restored\tthread=7\tx87cw=895", "phase=restored\tthread=7\tx87cw=639") if "id=trace" in line else line for line in lines],
        [line.replace("phase=pc53\tthread=7", "phase=pc53\tthread=8") if "id=trace" in line else line for line in lines],
        [line.replace("phase=restored\tthread=7\tx87cw=895\tmxcsr=8064\tstatus=0", "phase=restored\tthread=7\tx87cw=895\tmxcsr=8064\tstatus=1") if "id=trace" in line else line for line in lines],
        [line.replace("phase=pc53\tthread=7\tx87cw=639", "phase=pc53\tthread=7\tx87cw=895") if "id=trace" in line else line for line in lines],
        [line.replace("phase=pc53\tthread=7\tx87cw=639", "phase=pc53\tthread=7\tx87cw=1663") if "id=trace" in line else line for line in lines],
        [line.replace("phase=restored\tthread=7\tx87cw=895\tmxcsr=8064", "phase=restored\tthread=7\tx87cw=895\tmxcsr=16256") if "id=trace" in line else line for line in lines],
    ):
        try:
            state_records(altered)
        except ValueError:
            pass
        else:
            raise AssertionError("an adverse precision state was accepted")
    states = state_records(lines)
    one = "1.0@4607182418800017408"
    zero = "0.0@0"
    values = f"x={one}\ty={zero}\txSquared={one}\tySquared={zero}\tsum={one}\tsqrt={one}\treciprocal={one}"
    controls = [
        f"DYN4K_COLLISION_FP_SCALAR\tv1\tmode={mode}\tid={id_}\tthread=7\t{values}"
        for mode in ("before", "pc53") for id_ in SCALAR_IDS
    ]
    java = [f"DYN4K_COLLISION_SCALAR\tv1\tprovider=java\tid={id_}\t{values}"
            for id_ in SCALAR_IDS]
    assert len(scalar_records(controls, java, states)) == 7
    for altered in (
        controls[:-1],
        [line.replace(f"sum={one}", f"sum={zero}") if "mode=pc53\tid=CirclePolygon.edge3" in line else line for line in controls],
    ):
        try:
            scalar_records(altered, java, states)
        except ValueError:
            pass
        else:
            raise AssertionError("an adverse scalar record was accepted")
    xml_error_self_test()
    ordinary_selection_self_test()
    print("PRECISION_CONTROL_SELF_TEST_OK stateRows=33 scalarIDs=7 xmlErrorsRejected=2 ordinaryExtraRejected=1 roundingMutationRejected=1")


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("validate")
    command.add_argument("--native-directory", required=True)
    command.add_argument("--controlled-directory", required=True)
    command.add_argument("--java-trace", required=True)
    command.add_argument("--java-scalars", required=True)
    command.add_argument("--controlled-trace", required=True)
    command.add_argument("--result", required=True)
    command.add_argument("--source-sha", required=True)
    corrected = commands.add_parser("validate-corrected")
    corrected.add_argument("--native-directory", required=True)
    corrected.add_argument("--java-trace", required=True)
    corrected.add_argument("--native-scalars", required=True)
    corrected.add_argument("--java-scalars", required=True)
    corrected.add_argument("--probe-directory", required=True)
    corrected.add_argument("--result", required=True)
    corrected.add_argument("--source-sha", required=True)
    commands.add_parser("self-test")
    args = parser.parse_args()
    try:
        if args.command == "self-test":
            self_test()
        elif args.command == "validate-corrected":
            validate_corrected(args)
        else:
            validate(args)
    except (AssertionError, ET.ParseError, OSError, ValueError, subprocess.SubprocessError,
            KeyError, TypeError) as error:
        print(f"PRECISION_CONTROL_VALIDATION_FAILED {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
