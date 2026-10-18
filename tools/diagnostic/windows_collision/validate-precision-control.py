import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "compatibility"))
import windows_collision_focus as focus


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
        if active["x87cw"] & 0x0300 != 0x0200:
            raise ValueError(f"x87 precision did not reach PC53 for {id_}")
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
    failed = case.find("failure")
    errored = case.find("error")
    if failed is not None and errored is not None:
        raise ValueError("a case has both failure and error")
    detail = failed if failed is not None else errored
    if detail is None:
        return None
    lines = (detail.text or "").splitlines()
    return detail.attrib.get("message") or (lines[0] if lines else f"{detail.tag} without message")


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
    print("PRECISION_CONTROL_SELF_TEST_OK cases=11")


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
    commands.add_parser("self-test")
    args = parser.parse_args()
    try:
        if args.command == "self-test":
            self_test()
        else:
            validate(args)
    except (AssertionError, ET.ParseError, OSError, ValueError) as error:
        print(f"PRECISION_CONTROL_VALIDATION_FAILED {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
