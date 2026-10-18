import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


TARGET = "mingwX64Test"
SUITES = {
    "org.dyn4j.collision.narrowphase.WindowsCollisionIntermediateDiagnosticTest":
        "TEST-mingwX64Test.org.dyn4j.collision.narrowphase.WindowsCollisionIntermediateDiagnosticTest.xml",
    "org.dyn4j.coverage.collision.shapes.a.CapsuleSliceTest":
        "TEST-mingwX64Test.org.dyn4j.coverage.collision.shapes.a.CapsuleSliceTest.xml",
    "org.dyn4j.coverage.collision.shapes.a.CirclePolygonTest":
        "TEST-mingwX64Test.org.dyn4j.coverage.collision.shapes.a.CirclePolygonTest.xml",
    "org.dyn4j.coverage.collision.shapes.a.CircleSegmentTest":
        "TEST-mingwX64Test.org.dyn4j.coverage.collision.shapes.a.CircleSegmentTest.xml",
    "org.dyn4j.coverage.collision.shapes.a.CircleSliceTest":
        "TEST-mingwX64Test.org.dyn4j.coverage.collision.shapes.a.CircleSliceTest.xml",
    "org.dyn4j.coverage.collision.shapes.a.PolygonCapsuleTest":
        "TEST-mingwX64Test.org.dyn4j.coverage.collision.shapes.a.PolygonCapsuleTest.xml",
    "org.dyn4j.coverage.collision.shapes.a.PolygonPolygonTest":
        "TEST-mingwX64Test.org.dyn4j.coverage.collision.shapes.a.PolygonPolygonTest.xml",
}
ORIGINAL_CASES = {
    suite: {
        f"{method}[mingwX64]"
        for method in ("detectSat", "detectGjk", "gjkDistance", "getClipManifold")
    }
    for suite in (
        "org.dyn4j.coverage.collision.shapes.a.CapsuleSliceTest",
        "org.dyn4j.coverage.collision.shapes.a.CirclePolygonTest",
        "org.dyn4j.coverage.collision.shapes.a.CircleSegmentTest",
        "org.dyn4j.coverage.collision.shapes.a.CircleSliceTest",
        "org.dyn4j.coverage.collision.shapes.a.PolygonCapsuleTest",
        "org.dyn4j.coverage.collision.shapes.a.PolygonPolygonTest",
    )
}
DIAGNOSTIC_CASES = {
    "capsuleSlice[mingwX64]",
    "circlePolygon[mingwX64]",
    "circleSegment[mingwX64]",
    "circleSlice[mingwX64]",
    "polygonCapsule[mingwX64]",
    "polygonPolygon[mingwX64]",
}
IDENTITY_FIELDS = ("fixture", "method", "phase", "order", "step", "algorithm")


def _identity(record, provider):
    fields = record.split("\t")
    if len(fields) < 3 or fields[:2] != ["DYN4K_COLLISION_DIAGNOSTIC", "v2"]:
        raise ValueError("record is not a v2 collision diagnostic")
    values = {}
    for field in fields[2:]:
        if "=" in field:
            key, value = field.split("=", 1)
            values[key] = value
    if values.get("provider") != provider:
        raise ValueError(f"unexpected record provider: {values.get('provider')}")
    try:
        return tuple(values[field] for field in IDENTITY_FIELDS)
    except KeyError as error:
        raise ValueError(f"record is missing identity field: {error.args[0]}") from error


def _records(lines, provider, label):
    records = [line for line in lines if line.startswith("DYN4K_COLLISION_DIAGNOSTIC\tv2\t")]
    if len(records) != 72:
        raise ValueError(f"expected 72 {label} v2 rows, found {len(records)}")
    identities = [_identity(record, provider) for record in records]
    if len(set(identities)) != 72:
        raise ValueError(f"{label} v2 rows contain duplicate identities")
    return records, set(identities)


def validate(native_directory, java_tsv, native_tsv):
    native_directory = Path(native_directory)
    reports = sorted(native_directory.glob("TEST-*.xml"))
    expected_names = set(SUITES.values())
    actual_names = {path.name for path in reports}
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        unexpected = sorted(actual_names - expected_names)
        raise ValueError(f"Native XML report set mismatch; missing={missing}, unexpected={unexpected}")

    diagnostic_records = None
    for suite_name, report_name in SUITES.items():
        report_path = native_directory / report_name
        root = ET.parse(report_path).getroot()
        expected_suite_id = f"{TARGET}.{suite_name}"
        if root.tag != "testsuite" or root.attrib.get("name") != expected_suite_id:
            raise ValueError(
                f"wrong suite identity in {report_name}: {root.attrib.get('name')}"
            )
        if suite_name.endswith("WindowsCollisionIntermediateDiagnosticTest"):
            test_cases = root.findall("testcase")
            cases = {case.attrib.get("name") for case in test_cases}
            if cases != DIAGNOSTIC_CASES or len(test_cases) != 6:
                raise ValueError(f"diagnostic case set mismatch: {sorted(cases)}")
            if any(case.find("skipped") is not None for case in test_cases):
                raise ValueError("diagnostic suite contains skipped cases")
            system_output = root.find("system-out")
            if system_output is None or system_output.text is None:
                raise ValueError("diagnostic suite has no system-out trace")
            diagnostic_records = system_output.text.splitlines()
        else:
            test_cases = root.findall("testcase")
            case_ids = [case.attrib.get("name") for case in test_cases]
            expected_cases = ORIGINAL_CASES[suite_name]
            if set(case_ids) != expected_cases or len(case_ids) != len(expected_cases):
                missing = sorted(expected_cases - set(case_ids))
                unexpected = sorted(set(case_ids) - expected_cases)
                raise ValueError(
                    f"original suite case set mismatch in {suite_name}; "
                    f"missing={missing}, unexpected={unexpected}"
                )
            skipped = sorted(
                case.attrib.get("name")
                for case in test_cases
                if case.find("skipped") is not None
            )
            if skipped:
                raise ValueError(f"original suite contains skipped cases in {suite_name}: {skipped}")

    if diagnostic_records is None:
        raise ValueError("diagnostic report was not processed")
    native_rows, native_identities = _records(diagnostic_records, "dyn4k", "Native")
    java_rows, java_identities = _records(
        Path(java_tsv).read_text(encoding="utf-8").splitlines(), "dyn4j-6.0.0", "Java"
    )
    if native_identities != java_identities:
        missing_native = sorted(java_identities - native_identities)
        missing_java = sorted(native_identities - java_identities)
        raise ValueError(
            f"Native/Java identity mismatch; missing_native={missing_native}, "
            f"missing_java={missing_java}"
        )

    destination = Path(native_tsv)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="\n") as output:
        output.write("\n".join(native_rows) + "\n")
    return len(reports), len(DIAGNOSTIC_CASES), len(native_rows), len(java_rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate focused mingwX64 collision evidence.")
    commands = parser.add_subparsers(dest="command", required=True)
    validate_command = commands.add_parser("validate")
    validate_command.add_argument("--native-directory", required=True)
    validate_command.add_argument("--java-tsv", required=True)
    validate_command.add_argument("--native-tsv", required=True)
    status_command = commands.add_parser("status")
    status_command.add_argument("--gradle-exit-code", required=True)
    status_command.add_argument("--java-exit-code", required=True)
    status_command.add_argument("--collection-status", type=int, required=True)
    status_command.add_argument("--validation-status", type=int, required=True)
    args = parser.parse_args(argv)

    if args.command == "status":
        failed = (
            args.gradle_exit_code != "0"
            or args.java_exit_code != "0"
            or args.collection_status != 0
            or args.validation_status != 0
        )
        if failed:
            print(
                "WINDOWS_COLLISION_FOCUS_FAILED "
                f"gradle={args.gradle_exit_code} java={args.java_exit_code} "
                f"collection={args.collection_status} validation={args.validation_status}"
            )
            return 1
        print("WINDOWS_COLLISION_FOCUS_PASSED gradle=0 java=0 collection=0 validation=0")
        return 0

    try:
        suites, cases, native_rows, java_rows = validate(
            args.native_directory, args.java_tsv, args.native_tsv
        )
    except (OSError, ET.ParseError, ValueError) as error:
        print(f"WINDOWS_COLLISION_FOCUS_VALIDATION_FAILED: {error}", file=sys.stderr)
        return 1
    print(
        "WINDOWS_COLLISION_FOCUS_VALIDATION_OK "
        f"suites={suites} diagnosticCases={cases} nativeRows={native_rows} "
        f"javaRows={java_rows} identityParity=exact"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
