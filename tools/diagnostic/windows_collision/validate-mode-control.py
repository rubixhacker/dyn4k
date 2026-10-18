from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import shutil
import sys
import tempfile
from pathlib import Path


SOURCE_DIRECTORY = Path(__file__).resolve().parent
SCALAR = runpy.run_path(str(SOURCE_DIRECTORY / "validate-scalar-control.py"))
MODES = (("debug-g", ["-g"]), ("default", []), ("optimized-opt", ["-opt"]))


class ModeValidationError(ValueError):
    pass


def read(directory: Path, name: str) -> str:
    return (directory / name).read_text(encoding="utf-8").strip()


def exited_zero(directory: Path, name: str) -> None:
    receipt = json.loads(read(directory, name))
    if receipt.get("state") != "EXITED" or receipt.get("childExitCode") != 0:
        raise ModeValidationError(f"{directory.name}: {name} is not a successful child exit")


def validate(directory: Path) -> None:
    SCALAR["validate_source_vectors"]()
    source = SOURCE_DIRECTORY / "WindowsCollisionScalarControl.kt"
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if read(directory, "source-sha256.txt") != f"{source_hash}  tools/diagnostic/windows_collision/{source.name}":
        raise ModeValidationError("source hash differs from the seven-vector producer")
    if SCALAR["VERSION_TOKEN"].search(read(directory, "kotlin-native-version.txt")) is None:
        raise ModeValidationError("Kotlin/Native 2.4.20 version token is missing")
    if read(directory, "version-exit-code.txt") != "0":
        raise ModeValidationError("Kotlin/Native version command did not exit zero")
    exited_zero(directory, "version-receipt.json")
    if read(directory, "mode-status.txt") != "OK":
        raise ModeValidationError("mode runner did not finish successfully")

    for name, flags in MODES:
        mode = directory / name
        if read(mode, "compiler-exit-code.txt") != "0" or read(mode, "run-exit-code.txt") != "0":
            raise ModeValidationError(f"{name}: compiler or executable did not exit zero")
        exited_zero(mode, "compiler-receipt.json")
        exited_zero(mode, "run-receipt.json")
        command = json.loads(read(mode, "compiler-command.json"))
        arguments = command.get("arguments")
        if command.get("mode") != name or command.get("sourceSha256") != source_hash:
            raise ModeValidationError(f"{name}: command identity or source hash differs")
        if Path(command.get("executable", "")).name.lower() != "kotlinc-native.bat":
            raise ModeValidationError(f"{name}: compiler executable differs")
        if not isinstance(arguments, list) or len(arguments) != 5 + len(flags):
            raise ModeValidationError(f"{name}: compiler argument count differs")
        if Path(arguments[0]).name != source.name or arguments[1:3] != ["-target", "mingw_x64"]:
            raise ModeValidationError(f"{name}: source or target differs")
        if arguments[3:-2] != flags or arguments[-2] != "-o":
            raise ModeValidationError(f"{name}: compiler mode differs")
        if Path(arguments[-1]).name != "windows-collision-scalar" or Path(arguments[-1]).parent != mode:
            raise ModeValidationError(f"{name}: compiler output path differs")
        executable = mode / "windows-collision-scalar.exe"
        expected_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
        if read(mode, "executable-sha256.txt") != f"{expected_hash}  {executable.name}":
            raise ModeValidationError(f"{name}: executable SHA-256 differs")
        try:
            SCALAR["_parse"](read(mode, "native-scalar.tsv"), "kotlin-native", name)
        except SCALAR["ScalarValidationError"] as error:
            raise ModeValidationError(f"{name}: {error}") from error


def self_test() -> int:
    SCALAR["validate_source_vectors"]()
    source = SOURCE_DIRECTORY / "WindowsCollisionScalarControl.kt"
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)

        def fixture(name: str) -> Path:
            directory = root / name
            directory.mkdir()
            (directory / "source-sha256.txt").write_text(
                f"{source_hash}  tools/diagnostic/windows_collision/{source.name}\n", encoding="utf-8"
            )
            (directory / "kotlin-native-version.txt").write_text("Kotlin/Native: 2.4.20\n", encoding="utf-8")
            (directory / "version-exit-code.txt").write_text("0\n", encoding="utf-8")
            (directory / "version-receipt.json").write_text(
                json.dumps({"state": "EXITED", "childExitCode": 0}), encoding="utf-8"
            )
            (directory / "mode-status.txt").write_text("OK\n", encoding="utf-8")
            rows = "\n".join(SCALAR["_row"]("kotlin-native", *case) for case in SCALAR["EXPECTED"]) + "\n"
            for mode_name, flags in MODES:
                mode = directory / mode_name
                mode.mkdir()
                (mode / "compiler-exit-code.txt").write_text("0\n", encoding="utf-8")
                (mode / "run-exit-code.txt").write_text("0\n", encoding="utf-8")
                (mode / "compiler-receipt.json").write_text(
                    json.dumps({"state": "EXITED", "childExitCode": 0}), encoding="utf-8"
                )
                (mode / "run-receipt.json").write_text(
                    json.dumps({"state": "EXITED", "childExitCode": 0}), encoding="utf-8"
                )
                executable = mode / "windows-collision-scalar.exe"
                executable.write_bytes(f"MZ{mode_name}".encode())
                (mode / "executable-sha256.txt").write_text(
                    f"{hashlib.sha256(executable.read_bytes()).hexdigest()}  {executable.name}\n", encoding="utf-8"
                )
                (mode / "native-scalar.tsv").write_text(rows, encoding="utf-8")
                (mode / "compiler-command.json").write_text(json.dumps({
                    "mode": mode_name,
                    "executable": "C:/konan/bin/kotlinc-native.bat",
                    "arguments": [str(source), "-target", "mingw_x64", *flags, "-o", str(mode / "windows-collision-scalar")],
                    "sourceSha256": source_hash,
                }), encoding="utf-8")
            return directory

        validate(fixture("positive"))
        adverse = (
            ("missing mode", lambda d: shutil.rmtree(d / "default")),
            ("wrong flag", lambda d: (d / "debug-g" / "compiler-command.json").write_text(
                read(d / "debug-g", "compiler-command.json").replace('"-g"', '"-opt"'), encoding="utf-8")),
            ("changed executable", lambda d: (d / "default" / "windows-collision-scalar.exe").write_bytes(b"changed")),
            ("wrong input bits", lambda d: (d / "optimized-opt" / "native-scalar.tsv").write_text(
                read(d / "optimized-opt", "native-scalar.tsv").replace("@-4621899953565315924", "@0", 1),
                encoding="utf-8")),
            ("missing row", lambda d: (d / "default" / "native-scalar.tsv").write_text(
                "\n".join(read(d / "default", "native-scalar.tsv").splitlines()[:-1]), encoding="utf-8")),
            ("failed compiler", lambda d: (d / "debug-g" / "compiler-exit-code.txt").write_text("1\n", encoding="utf-8")),
            ("failed runner", lambda d: (d / "optimized-opt" / "run-exit-code.txt").write_text("1\n", encoding="utf-8")),
            ("wrong source", lambda d: (d / "source-sha256.txt").write_text("0" * 64, encoding="utf-8")),
            ("timed-out compiler", lambda d: (d / "debug-g" / "compiler-receipt.json").write_text(
                json.dumps({"state": "TIMEOUT", "childExitCode": -9}), encoding="utf-8")),
            ("timed-out executable", lambda d: (d / "optimized-opt" / "run-receipt.json").write_text(
                json.dumps({"state": "TIMEOUT", "childExitCode": -9}), encoding="utf-8")),
        )
        for index, (label, mutate) in enumerate(adverse):
            directory = fixture(f"adverse-{index}")
            mutate(directory)
            try:
                validate(directory)
            except (ModeValidationError, OSError, ValueError):
                continue
            raise AssertionError(f"adverse mode control was accepted: {label}")
    print(f"MODE_CONTROL_SELF_TEST_OK positive=1 adverse={len(adverse)} modes=3 rows=7")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("validate")
    check.add_argument("--directory", required=True, type=Path)
    commands.add_parser("self-test")
    args = parser.parse_args()
    try:
        if args.command == "self-test":
            return self_test()
        validate(args.directory)
        print("MODE_CONTROL_VALIDATION_OK modes=3 rows=21 inputs=exact arithmetic=observations")
        return 0
    except (OSError, ValueError, AssertionError, KeyError, TypeError) as error:
        print(f"MODE_CONTROL_VALIDATION_FAILED {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
