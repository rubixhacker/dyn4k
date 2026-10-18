from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


EXPECTED = (
    ("CirclePolygon.edge3", -4621899953565315924, -4625196817309499400),
    ("CapsuleSlice.epa4", 4603460912955918154, -4617903595553423057),
    ("CirclePolygon.epa3", -4619490269450149183, -4618227961596862473),
    ("CircleSegment.epa2", -4621644133008675367, -4617140533381304871),
    ("CircleSlice.epa35", 4606804953716818183, 4598831979030654181),
    ("PolygonCapsule.sat1", -4624133661653997234, 4606741575090066687),
    ("PolygonCapsule.sat4", 4605462196814083239, -4619902518423102882),
)
PREFIX = "DYN4K_COLLISION_SCALAR"
FIELDS = ("id", "x", "y", "xSquared", "ySquared", "sum", "sqrt", "reciprocal", "normalized")
RAW_NUMBER = re.compile(r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?@(-?\d+)")
VERSION_TOKEN = re.compile(r"(?<![\w.+-])2\.4\.20(?![\w.+-])")
KOTLIN_VECTOR = re.compile(r'ScalarInput\("([^\"]+)", (-?\d+)L, (-?\d+)L\)')
JAVA_VECTOR = re.compile(r'\{"([^\"]+)", (-?\d+)L, (-?\d+)L\}')


class ScalarValidationError(ValueError):
    pass


def validate_source_vectors() -> None:
    source_dir = Path(__file__).parent
    kotlin_text = (source_dir / "WindowsCollisionScalarControl.kt").read_text(encoding="utf-8")
    java_text = (source_dir / "WindowsCollisionScalarJavaControl.java").read_text(encoding="utf-8")
    kotlin_vectors = tuple((case_id, int(x), int(y)) for case_id, x, y in KOTLIN_VECTOR.findall(kotlin_text))
    java_vectors = tuple((case_id, int(x), int(y)) for case_id, x, y in JAVA_VECTOR.findall(java_text))
    if kotlin_vectors != EXPECTED or java_vectors != EXPECTED:
        raise ScalarValidationError("validator vectors differ from the committed Kotlin or Java control vectors")


def _parse(text: str, provider: str, label: str) -> list[tuple[str, str, str]]:
    lines = text.splitlines()
    if len(lines) != len(EXPECTED):
        raise ScalarValidationError(f"{label}: expected 7 rows, found {len(lines)}")
    parsed: list[tuple[str, str, str]] = []
    for index, (line, expected) in enumerate(zip(lines, EXPECTED, strict=True)):
        columns = line.split("\t")
        if len(columns) != 3 + len(FIELDS):
            raise ScalarValidationError(f"{label}: row {index + 1} has {len(columns)} columns")
        if columns[0] != PREFIX or columns[1] != "v1" or columns[2] != f"provider={provider}":
            raise ScalarValidationError(f"{label}: row {index + 1} has an invalid prefix, version, or provider")
        values: dict[str, str] = {}
        for name, column in zip(FIELDS, columns[3:], strict=True):
            key, separator, value = column.partition("=")
            if not separator or key != name or not value:
                raise ScalarValidationError(f"{label}: row {index + 1} has an invalid {name} field")
            values[name] = value
        expected_id, expected_x, expected_y = expected
        if values["id"] != expected_id:
            raise ScalarValidationError(f"{label}: row {index + 1} expected id {expected_id}, found {values['id']}")
        input_bits: list[str] = []
        for axis, expected_bits in (("x", expected_x), ("y", expected_y)):
            match = RAW_NUMBER.fullmatch(values[axis])
            if match is None:
                raise ScalarValidationError(f"{label}: row {index + 1} has malformed {axis} raw-bit value")
            bits = match.group(1)
            if bits != str(expected_bits):
                raise ScalarValidationError(
                    f"{label}: row {index + 1} {axis} bits expected {expected_bits}, found {bits}"
                )
            input_bits.append(bits)
        parsed.append((values["id"], input_bits[0], input_bits[1]))
    return parsed


def validate(native_text: str, java_text: str) -> None:
    native_inputs = _parse(native_text, "kotlin-native", "Native")
    java_inputs = _parse(java_text, "java", "Java")
    if native_inputs != java_inputs:
        raise ScalarValidationError("Native and Java input identities or raw bits differ")


def _row(provider: str, case_id: str, x_bits: int, y_bits: int) -> str:
    return "\t".join(
        (
            PREFIX,
            "v1",
            f"provider={provider}",
            f"id={case_id}",
            f"x=0.0@{x_bits}",
            f"y=0.0@{y_bits}",
            "xSquared=observed",
            "ySquared=observed",
            "sum=observed",
            "sqrt=observed",
            "reciprocal=observed",
            "normalized=observed",
        )
    )


def self_test() -> int:
    validate_source_vectors()
    native = [_row("kotlin-native", *case) for case in EXPECTED]
    java = [_row("java", *case) for case in EXPECTED]
    validate("\n".join(native) + "\n", "\n".join(java) + "\n")

    def rejected(name: str, native_rows: list[str], java_rows: list[str]) -> None:
        try:
            validate("\n".join(native_rows) + "\n", "\n".join(java_rows) + "\n")
        except ScalarValidationError:
            return
        raise AssertionError(f"adverse control was accepted: {name}")

    cases: list[tuple[str, list[str], list[str]]] = []
    cases.append(("reordered ids", [native[1], native[0], *native[2:]], java))
    cases.append(("unexpected id", [native[0].replace("CirclePolygon.edge3", "wrong.id", 1), *native[1:]], java))
    cases.append(("wrong provider", [native[0].replace("provider=kotlin-native", "provider=java", 1), *native[1:]], java))
    cases.append(("missing field", [native[0].replace("\txSquared=observed", "", 1), *native[1:]], java))
    cases.append(("wrong expected input bits", [native[0].replace("x=0.0@-4621899953565315924", "x=0.0@0", 1), *native[1:]], java))
    cases.append(("Native/Java input mismatch", native, [java[0].replace("y=0.0@-4625196817309499400", "y=0.0@1", 1), *java[1:]]))
    cases.append(("extra field", [native[0] + "\textra=unexpected", *native[1:]], java))
    for name, adverse_native, adverse_java in cases:
        rejected(name, adverse_native, adverse_java)

    if not VERSION_TOKEN.search("Kotlin/Native: 2.4.20") or not VERSION_TOKEN.search("2.4.20"):
        raise AssertionError("valid Kotlin/Native version token was rejected")
    for value in ("2.4.201", "2.4.20-dev", "2.4.20foo", "2.4.20+build", "2.4.20.1"):
        if VERSION_TOKEN.search(value):
            raise AssertionError(f"adverse version token was accepted: {value}")
    print(f"SCALAR_VALIDATOR_SELF_TEST_OK positive=1 adverse={len(cases) + 5} arithmetic=observations")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    validate_command = commands.add_parser("validate")
    validate_command.add_argument("--native", required=True, type=Path)
    validate_command.add_argument("--java", required=True, type=Path)
    commands.add_parser("self-test")
    args = parser.parse_args()
    try:
        if args.command == "self-test":
            return self_test()
        validate_source_vectors()
        validate(args.native.read_text(encoding="utf-8"), args.java.read_text(encoding="utf-8"))
        print("SCALAR_CONTROL_VALIDATION_OK rows=7 inputs=exact arithmetic=observations")
        return 0
    except (OSError, ScalarValidationError, AssertionError) as error:
        print(f"SCALAR_CONTROL_VALIDATION_FAILED {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
