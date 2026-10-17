#!/usr/bin/env python3
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, log):
    result = subprocess.run(command, capture_output=True, text=True)
    log.write_text(result.stdout + result.stderr)
    return result.returncode, sha(log)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify-detection-original-java.py candidate.jar output-directory")
    candidate, output = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    upstream = Path("/tmp/dyn4k-upstream-6.0.0")
    source = upstream / "src/test/java/org/dyn4j/collision"
    runner = Path("/tmp/dyn4k-full-java-probe/CorpusReport.java")
    baseline = Path("/tmp/dyn4k-baseline-cache/dyn4j-6.0.0.jar")
    dependencies = [
        Path("/tmp/dyn4k-baseline-cache/deps/junit-4.13.1.jar"),
        Path("/tmp/dyn4k-baseline-cache/deps/hamcrest-core-1.3.jar"),
    ]
    stdlib = list(Path.home().joinpath(".gradle/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-stdlib/2.4.20").glob("*/kotlin-stdlib-2.4.20.jar"))
    if len(stdlib) != 1:
        raise SystemExit("one Kotlin stdlib archive required")
    dependencies += stdlib
    sources = sorted(source.rglob("*.java"))
    names = {
        "detectors": sorted(
            "org.dyn4j.collision." + package + "." + path.stem
            for package in ("broadphase", "narrowphase", "manifold", "continuous")
            for path in (source / package).glob("*Test.java")
        ),
        "shapes": sorted(
            "org.dyn4j.collision.shapes." + path.stem
            for path in (source / "shapes").glob("*Test.java")
            if not path.stem.startswith("Abstract")
        ),
    }
    report = {
        "source_revision": "058bf6d982a0fb89b54050f929f6ea9dae53b714",
        "source_sha256": {str(path.relative_to(upstream)): sha(path) for path in sources},
        "runner_sha256": sha(runner),
        "archive_sha256": {"baseline": sha(baseline), "candidate": sha(candidate)},
        "runs": [],
    }
    good = True
    for provider, archive in (("baseline", baseline), ("candidate", candidate)):
        classes = output / (provider + "-classes")
        classes.mkdir(exist_ok=True)
        classpath = ":".join(map(str, [archive, *dependencies]))
        command = ["/tmp/dyn4k-tools/jdk21/bin/javac", "-encoding", "UTF-8", "--release", "8",
                   "-cp", classpath, "-d", str(classes), *map(str, sources), str(runner)]
        log = output / (provider + "-compile.log")
        exit_code, log_hash = run(command, log)
        report["runs"].append({"provider": provider, "stage": "compile", "command": command,
                               "exit": exit_code, "log_sha256": log_hash})
        good &= exit_code == 0
        if exit_code:
            continue
        for runtime in ("jdk8", "jdk21"):
            for group, group_names in names.items():
                command = ["/tmp/dyn4k-tools/" + runtime + "/bin/java", "-cp", classpath + ":" + str(classes),
                           "CorpusReport", *group_names]
                log = output / f"{provider}-{runtime}-{group}.log"
                exit_code, log_hash = run(command, log)
                lines = log.read_text().splitlines()
                summary = [line for line in lines if line.startswith(("ACTUAL_TESTS=", "FAILURES=", "IGNORED="))]
                expected = 471 if group == "detectors" else 187
                passed = exit_code == 0 and summary == [f"ACTUAL_TESTS={expected}", "FAILURES=0", "IGNORED=0"]
                report["runs"].append({"provider": provider, "runtime": runtime, "stage": group,
                                       "classes": len(group_names), "command": command, "exit": exit_code,
                                       "summary": summary, "passed": passed, "log_sha256": log_hash})
                good &= passed
    report_file = output / "result.json"
    report_file.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"result": str(report_file), "sha256": sha(report_file), "runs": report["runs"]}, indent=2))
    if not good:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
