from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path


FIXTURE = Path(__file__).resolve().parents[2] / "compatibility/fixtures/named_module"
SUCCESS = "Named module consumer passed"
BASELINE_SHA256 = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def consumer(jar: Path, dependencies: list[Path], classes: Path) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str] | None]:
    classes.mkdir(parents=True, exist_ok=True)
    module_path = ":".join(str(path) for path in [jar, *dependencies])
    compiled = run("javac", "--release", "9", "--module-path", module_path,
                   "-d", str(classes), str(FIXTURE / "module-info.java"),
                   str(FIXTURE / "example/Main.java"))
    executed = (run("java", "--module-path", f"{module_path}:{classes}",
                    "-m", "dyn4k.migration.probe/example.Main")
                if compiled.returncode == 0 else None)
    return compiled, executed


def assert_pass(jar: Path, dependencies: list[Path], classes: Path, label: str) -> None:
    compiled, executed = consumer(jar, dependencies, classes)
    require(compiled.returncode == 0, f"{label}: {compiled.stderr}")
    require(executed is not None and executed.returncode == 0, f"{label}: {executed}")
    require(executed is not None and executed.stdout.strip() == SUCCESS, f"{label}: {executed.stdout if executed else ''}")
    print(f"PASS {label}: unchanged modular source compiled and ran")


def assert_rejected(jar: Path, dependencies: list[Path], classes: Path,
                    expected: str, label: str) -> None:
    compiled, executed = consumer(jar, dependencies, classes)
    output = compiled.stdout + compiled.stderr + (executed.stdout + executed.stderr if executed else "")
    require(expected in output, f"{label}: expected {expected!r}, got {output!r}")
    require(compiled.returncode != 0 or executed is None or executed.returncode != 0,
            f"{label}: broken module ran successfully")
    print(f"PASS {label}: {expected}")


def repack(source: Path, destination: Path, replacement: bytes | None) -> None:
    descriptor = "module-info.class"
    with zipfile.ZipFile(source) as source_jar, zipfile.ZipFile(destination, "w") as output:
        for item in source_jar.infolist():
            if item.filename == descriptor:
                if replacement is not None:
                    output.writestr(item, replacement)
            else:
                output.writestr(item, source_jar.read(item))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--stdlib", type=Path, required=True)
    parser.add_argument("--java8", type=Path, required=True)
    args = parser.parse_args()
    require(hashlib.sha256(args.baseline.read_bytes()).hexdigest() == BASELINE_SHA256,
            "baseline JAR SHA-256 differs from dyn4j 6.0.0")
    version = run(str(args.java8), "-version")
    require(version.returncode == 0 and re.search(r'\bversion "(?:1\.8\.|8(?:\.|"))',
                                                  version.stdout + version.stderr) is not None,
            "Java 8 runtime path is required")
    with tempfile.TemporaryDirectory(prefix="dyn4k-module-negatives-") as directory:
        root = Path(directory)
        assert_pass(args.baseline, [], root / "baseline", "baseline")
        assert_pass(args.candidate, [args.stdlib], root / "candidate", "candidate")

        wrong_name = root / "wrong-name.jar"
        repack(args.candidate, wrong_name, None)
        assert_rejected(wrong_name, [args.stdlib], root / "wrong-name-classes",
                        "module not found: org.dyn4j", "wrong module name")

        source = root / "module-info.java"
        source.write_text("module org.dyn4j { requires kotlin.stdlib; exports org.dyn4j; }\n")
        descriptor_classes = root / "descriptor"
        descriptor_classes.mkdir()
        compiled = run("javac", "--release", "9", "--module-path", str(args.stdlib),
                       "--patch-module", f"org.dyn4j={args.candidate}",
                       "-d", str(descriptor_classes), str(source))
        require(compiled.returncode == 0, compiled.stderr)
        missing_export = root / "missing-export.jar"
        repack(args.candidate, missing_export, (descriptor_classes / "module-info.class").read_bytes())
        assert_rejected(missing_export, [args.stdlib], root / "missing-export-classes",
                        "does not export", "missing geometry export")

        assert_rejected(args.candidate, [], root / "missing-runtime",
                        "Module kotlin.stdlib not found", "missing Kotlin runtime")

        classpath_classes = root / "java8-classes"
        classpath_classes.mkdir()
        compiled = run("javac", "--release", "8", "-cp", f"{args.candidate}:{args.stdlib}",
                       "-d", str(classpath_classes), str(FIXTURE / "example/Main.java"))
        require(compiled.returncode == 0, compiled.stderr)
        executed = run(str(args.java8), "-cp", f"{args.candidate}:{args.stdlib}:{classpath_classes}",
                       "example.Main")
        require(executed.returncode == 0 and executed.stdout.strip() == SUCCESS, executed.stderr)
        print("PASS Java 8 classpath: unchanged source compiled and ran")


if __name__ == "__main__":
    main()
