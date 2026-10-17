from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

COMMIT = "058bf6d982a0fb89b54050f929f6ea9dae53b714"
BINARY_SHA256 = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
SOURCES_SHA256 = "83b47be47bdce27681139dab84937e0f586b70ab800dc494fbebed4b58893223"
BASE = "https://repo.maven.apache.org/maven2/org/dyn4j/dyn4j/6.0.0"
JUNIT = "https://repo.maven.apache.org/maven2/junit/junit/4.13.1/junit-4.13.1.jar"
HAMCREST = "https://repo.maven.apache.org/maven2/org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: Path, expected: str | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        temp = dest.with_suffix(dest.suffix + ".part")
        urllib.request.urlretrieve(url, temp)
        temp.replace(dest)
    if expected and digest(dest) != expected:
        dest.unlink(missing_ok=True)
        raise SystemExit(f"checksum mismatch for {dest.name}")
    if not dest.is_file() or not dest.stat().st_size:
        raise SystemExit(f"missing or empty artifact: {dest}")


def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    kwargs.setdefault("text", True)
    return subprocess.run(command, check=True, **kwargs)


def checked_out_sources(cache: Path) -> Path:
    source = cache / "dyn4j-source"
    if not (source / ".git").exists():
        run(["git", "clone", "--filter=blob:none", "https://github.com/dyn4j/dyn4j.git", str(source)])
    run(["git", "-C", str(source), "fetch", "origin", COMMIT])
    run(["git", "-C", str(source), "checkout", "--detach", COMMIT])
    actual = run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True).stdout.strip()
    if actual != COMMIT:
        raise SystemExit(f"source revision mismatch: {actual}")
    return source


def inventory(source: Path, binary: Path, output: Path) -> dict[str, object]:
    prod = sorted((source / "src/main/java").rglob("*.java"))
    tests = sorted((source / "src/test/java").rglob("*.java"))
    if len(prod) != 268 or len(tests) != 199:
        raise SystemExit(f"unaccounted source files: production={len(prod)} tests={len(tests)}")
    names = run(["jar", "tf", str(binary)], capture_output=True).stdout.splitlines()
    classes = sorted(n[:-6].replace("/", ".") for n in names if n.endswith(".class") and not n.endswith("module-info.class"))
    signatures: dict[str, str] = {}
    for name in classes:
        result = run(["javap", "-classpath", str(binary), "-protected", "-s", name], capture_output=True)
        signatures[name] = result.stdout
    data = {
        "baseline": {"coordinate": "org.dyn4j:dyn4j:6.0.0", "commit": COMMIT,
                     "binary_sha256": digest(binary), "sources_sha256": SOURCES_SHA256},
        "production_java_files": [str(p.relative_to(source)) for p in prod],
        "test_java_files": [str(p.relative_to(source)) for p in tests],
        "test_annotations": sum(p.read_text(errors="replace").count("@Test") for p in tests),
        "types": classes,
        "public_protected_jvm_signatures": signatures,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


def execute(source: Path, binary: Path, cache: Path, output: Path) -> dict[str, object]:
    deps = cache / "deps"
    junit, hamcrest = deps / "junit-4.13.1.jar", deps / "hamcrest-core-1.3.jar"
    fetch(JUNIT, junit)
    fetch(HAMCREST, hamcrest)
    test_src = sorted((source / "src/test/java").rglob("*.java"))
    test_classes = [p for p in test_src if "@Test" in p.read_text(errors="replace") or "@RunWith" in p.read_text(errors="replace")]
    if not test_classes:
        raise SystemExit("empty test suite")
    work = cache / "run"
    if work.exists():
        shutil.rmtree(work)
    classes = work / "classes"
    classes.mkdir(parents=True)
    cp = os.pathsep.join(map(str, [binary, junit, hamcrest]))
    all_test_sources = [str(p) for p in test_src]
    argfile = work / "test-sources.args"
    argfile.write_text("\n".join('"' + p.replace('"', '\\"') + '"' for p in all_test_sources) + "\n")
    run(["javac", "-encoding", "UTF-8", "-source", "8", "-target", "8", "-cp", cp,
         "-d", str(classes), "@" + str(argfile)])
    resources = source / "src/test/resources"
    if resources.exists():
        shutil.copytree(resources, classes, dirs_exist_ok=True)
    class_names = sorted({
        ".".join(p.relative_to(source / "src/test/java").with_suffix("").parts)
        for p in test_classes
    })
    report_class = work / "BaselineJUnitReport.java"
    report_class.write_text('''import org.junit.runner.JUnitCore;\nimport org.junit.runner.Result;\npublic final class BaselineJUnitReport {\n public static void main(String[] args) { Result r = new JUnitCore().run(load(args));\n  System.out.println("ACTUAL_TESTS=" + r.getRunCount()); System.out.println("FAILURES=" + r.getFailureCount());\n  System.out.println("IGNORED=" + r.getIgnoreCount()); if (!r.wasSuccessful()) { r.getFailures().forEach(System.err::println); System.exit(1); } }\n static Class<?>[] load(String[] names) { try { Class<?>[] c = new Class<?>[names.length]; for (int i=0;i<names.length;i++) c[i]=Class.forName(names[i]); return c; } catch(Exception e) { throw new RuntimeException(e); } }\n}\n''')
    run(["javac", "-cp", os.pathsep.join([cp, str(classes)]), "-d", str(classes), str(report_class)])
    result = subprocess.run(["java", "-cp", os.pathsep.join([cp, str(classes)]),
                             "BaselineJUnitReport", *class_names], check=False,
                            capture_output=True, text=True)
    lines = result.stdout.splitlines()
    actual = int(next(line.split("=", 1)[1] for line in lines if line.startswith("ACTUAL_TESTS=")))
    failures = int(next(line.split("=", 1)[1] for line in lines if line.startswith("FAILURES=")))
    if actual == 0:
        raise SystemExit("empty executed suite")
    summary = {"commit": COMMIT, "binary_sha256": digest(binary), "test_files": len(test_src),
               "test_classes": len(class_names), "actual_executed_cases": actual, "failures": failures,
               "ignored": int(next(line.split("=", 1)[1] for line in lines if line.startswith("IGNORED="))),
               "process_exit_code": result.returncode, "output": result.stdout, "stderr": result.stderr}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n")
    if result.returncode != 0 or failures != 0:
        raise SystemExit("upstream baseline suite failed; see the retained run summary")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the pinned dyn4j baseline corpus.")
    parser.add_argument("--cache", type=Path, default=Path(".cache/baseline"))
    parser.add_argument("--inventory", type=Path, default=Path("docs/verification/baseline-inventory.json"))
    parser.add_argument("--summary", type=Path, default=Path("docs/verification/baseline-run.json"))
    parser.add_argument("--candidate", type=Path, help="compare candidate JAR public/protected signatures")
    parser.add_argument("--inventory-only", action="store_true")
    args = parser.parse_args()
    cache = args.cache.resolve()
    binary = cache / "dyn4j-6.0.0.jar"
    sources_jar = cache / "dyn4j-6.0.0-sources.jar"
    fetch(BASE + "/dyn4j-6.0.0.jar", binary, BINARY_SHA256)
    fetch(BASE + "/dyn4j-6.0.0-sources.jar", sources_jar, SOURCES_SHA256)
    source = checked_out_sources(cache)
    data = inventory(source, binary, args.inventory.resolve())
    if args.candidate:
        candidate_file = cache / "candidate-inventory.json"
        inventory(source, args.candidate.resolve(), candidate_file)
        candidate = json.loads(candidate_file.read_text())["public_protected_jvm_signatures"]
        baseline = data["public_protected_jvm_signatures"]
        missing = sorted(set(baseline) - set(candidate))
        mismatched = sorted(k for k in set(baseline) & set(candidate) if baseline[k] != candidate[k])
        print(json.dumps({"missing_types": missing, "signature_mismatches": mismatched}, indent=2))
        if missing or mismatched:
            raise SystemExit(1)
    if not args.inventory_only:
        summary = execute(source, binary, cache, args.summary.resolve())
        print(json.dumps(summary, indent=2))
    print(f"inventory: {args.inventory.resolve()}")


if __name__ == "__main__":
    main()
