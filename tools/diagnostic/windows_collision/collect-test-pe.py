from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(path: Path, value: str) -> None:
    path.write_text(value.rstrip("\n") + "\n", encoding="utf-8")


def find_objdump() -> list[str] | None:
    for name in ("llvm-objdump.exe", "objdump.exe", "llvm-objdump", "objdump"):
        found = shutil.which(name)
        if found:
            return [found]
    return None


def inspect(tool: list[str] | None, flag: str, executable: Path, output: Path, label: str) -> bool:
    if tool is None:
        write(output.with_name(f"{label}-status.txt"), "UNAVAILABLE: llvm-objdump and objdump not found")
        return False
    command = [*tool, flag, str(executable)]
    write(output.with_name(f"{label}-command.txt"), "\n".join(command))
    try:
        with output.open("wb") as stdout, output.with_name(f"{label}-stderr.log").open("wb") as stderr:
            result = subprocess.run(command, stdout=stdout, stderr=stderr, check=False)
        write(output.with_name(f"{label}-exit-code.txt"), str(result.returncode))
        if result.returncode != 0:
            write(output.with_name(f"{label}-status.txt"), f"FAILED: tool exit {result.returncode}")
            return False
        if output.stat().st_size == 0:
            write(output.with_name(f"{label}-status.txt"), "FAILED: tool produced no output")
            return False
        if label == "imports" and "DLL Name:" not in output.read_text(encoding="utf-8", errors="replace"):
            write(output.with_name(f"{label}-status.txt"), "FAILED: PE import list is absent")
            return False
        write(output.with_name(f"{label}-status.txt"), "OK")
        return True
    except OSError as error:
        write(output.with_name(f"{label}-status.txt"), f"UNAVAILABLE: {error}")
        return False


def collect(test_directory: Path, output_directory: Path, gradle_log: Path, gradle_command: Path,
            build_file: Path, objdump: list[str] | None) -> bool:
    output_directory.mkdir(parents=True, exist_ok=True)
    write(output_directory / "test-executable-search.txt", str(test_directory.resolve()))
    candidates = sorted(test_directory.rglob("*.exe")) if test_directory.is_dir() else []
    write(output_directory / "test-executable-candidates.txt", "\n".join(str(path) for path in candidates) or "NONE")

    context = ["focused Gradle command:"]
    context.append(gradle_command.read_text(encoding="utf-8") if gradle_command.is_file() else "UNAVAILABLE")
    context.append("build.gradle.kts SHA-256:")
    context.append(sha256(build_file) if build_file.is_file() else "UNAVAILABLE")
    context.append("compiler/link lines from Gradle --info console:")
    if gradle_log.is_file():
        needles = ("compileTestKotlinMingwX64", "linkDebugTestMingwX64", "Run tool:",
                   "compiler arguments", "compilerArgs", "konanc", "Kotlin/Native compiler")
        lines = [line for line in gradle_log.read_text(encoding="utf-8", errors="replace").splitlines()
                 if any(needle.lower() in line.lower() for needle in needles)]
        context.extend(lines or ["UNAVAILABLE: no compiler or link command lines emitted"])
        commands = [line for line in lines if ("konanc" in line.lower() or "compiler arguments" in line.lower()
                                               or "compilerargs" in line.lower())
                    and ("-target" in line or "-produce" in line)
                    and ("-output" in line or "-o " in line)]
        write(output_directory / "compiler-link-invocation-status.txt",
              "OBSERVED: complete command line in compiler-link-context.txt" if commands else
              "UNAVAILABLE: complete compiler/link command line not emitted by Gradle --info")
    else:
        context.append("UNAVAILABLE: Gradle console missing")
        write(output_directory / "compiler-link-invocation-status.txt", "UNAVAILABLE: Gradle console missing")
    write(output_directory / "compiler-link-context.txt", "\n".join(context))

    if len(candidates) != 1:
        write(output_directory / "test-executable-status.txt",
              f"UNAVAILABLE: expected one debugTest PE, found {len(candidates)}")
        for index, candidate in enumerate(candidates):
            retained = output_directory / f"candidate-{index}-{candidate.name}"
            shutil.copy2(candidate, retained)
            write(output_directory / f"candidate-{index}-sha256.txt", f"{sha256(retained)}  {retained.name}")
        return False

    retained = output_directory / candidates[0].name
    shutil.copy2(candidates[0], retained)
    write(output_directory / "test-executable-sha256.txt", f"{sha256(retained)}  {retained.name}")
    write(output_directory / "test-executable-status.txt", "OK")
    imports_ok = inspect(objdump, "-p", retained, output_directory / "test-imports.txt", "imports")
    disassembly_ok = inspect(objdump, "-d", retained, output_directory / "test-disassembly.txt", "disassembly")
    return imports_ok and disassembly_ok


def self_test() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        test_directory = root / "debugTest"
        test_directory.mkdir()
        log = root / "gradle.log"
        write(log, "> Task :dyn4k-core:linkDebugTestMingwX64\nRun tool: konanc -target mingw_x64 -o test")
        command = root / "gradle-command.txt"
        write(command, ".\\gradlew.bat :dyn4k-core:mingwX64Test --info")
        build_file = root / "build.gradle.kts"
        write(build_file, "mingwX64()")
        executable = test_directory / "test.exe"
        executable.write_bytes(b"MZtest")
        stub = root / "objdump.py"
        write(stub, "import sys\nprint('DLL Name: msvcrt.dll' if sys.argv[1] == '-p' else 'sqrtsd')")
        tool = [sys.executable, str(stub)]
        if not collect(test_directory, root / "positive", log, command, build_file, tool):
            raise AssertionError("one PE and working inspection tools were rejected")
        if sha256(root / "positive" / "test.exe") != sha256(executable):
            raise AssertionError("retained PE hash changed")
        if "linkDebugTestMingwX64" not in (root / "positive" / "compiler-link-context.txt").read_text():
            raise AssertionError("link context was not retained")
        if not (root / "positive" / "compiler-link-invocation-status.txt").read_text().startswith("OBSERVED"):
            raise AssertionError("complete compiler command was not identified")
        write(log, "> Task :dyn4k-core:linkDebugTestMingwX64\nRun tool: konanc")
        if not collect(test_directory, root / "partial-command", log, command, build_file, tool):
            raise AssertionError("partial compiler log blocked PE retention")
        if not (root / "partial-command" / "compiler-link-invocation-status.txt").read_text().startswith("UNAVAILABLE"):
            raise AssertionError("partial compiler command was reported as complete")
        if collect(test_directory, root / "missing-tool", log, command, build_file, None):
            raise AssertionError("missing inspection tool was accepted")
        if not (root / "missing-tool" / "disassembly-status.txt").is_file():
            raise AssertionError("missing disassembly status was not retained")
        empty_stub = root / "empty-objdump.py"
        write(empty_stub, "pass")
        if collect(test_directory, root / "empty-output", log, command, build_file,
                   [sys.executable, str(empty_stub)]):
            raise AssertionError("empty import and disassembly output was accepted")
        executable.unlink()
        if collect(test_directory, root / "missing-pe", log, command, build_file, tool):
            raise AssertionError("missing debugTest PE was accepted")
        (test_directory / "a.exe").write_bytes(b"MZa")
        (test_directory / "b.exe").write_bytes(b"MZb")
        if collect(test_directory, root / "ambiguous-pe", log, command, build_file, tool):
            raise AssertionError("ambiguous debugTest PEs were accepted")
        if len(list((root / "ambiguous-pe").glob("candidate-*.exe"))) != 2:
            raise AssertionError("ambiguous PEs were not retained")
    print("TEST_PE_COLLECTION_SELF_TEST_OK positive=2 adverse=4")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("collect")
    command.add_argument("--test-directory", required=True, type=Path)
    command.add_argument("--output-directory", required=True, type=Path)
    command.add_argument("--gradle-log", required=True, type=Path)
    command.add_argument("--gradle-command", required=True, type=Path)
    command.add_argument("--build-file", required=True, type=Path)
    commands.add_parser("self-test")
    args = parser.parse_args()
    if args.command == "self-test":
        return self_test()
    try:
        ok = collect(args.test_directory, args.output_directory, args.gradle_log,
                     args.gradle_command, args.build_file, find_objdump())
    except (OSError, ValueError) as error:
        args.output_directory.mkdir(parents=True, exist_ok=True)
        write(args.output_directory / "collector-status.txt", f"FAILED: {error}")
        print(f"TEST_PE_COLLECTION_FAILED {error}", file=sys.stderr)
        return 1
    write(args.output_directory / "collector-status.txt", "OK" if ok else "FAILED: see status files")
    print("TEST_PE_COLLECTION_OK" if ok else "TEST_PE_COLLECTION_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
