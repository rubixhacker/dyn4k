from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "dyn4k-core/src/jvmConsumer/java"
FROZEN_COMMIT = "806db0b6ce40c6345054fc05a9ddb32da14cf153"
BASELINE_SHA = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
STDLIB_SHA = "2226de463d309d4a5500a481320b3dea515a6981dcae1def531fbc158884e25f"
BAD_ARCHIVE_SHA = "b53ae4c5e85bc5f37866e9ead1d0558e0128c8dde9542789f51f62b9d5a6e57b"
BAD_ARCHIVE = ROOT / "tools/compatibility/fixtures/world/bad-body-view-bc71.jar"
PROVIDERS = ("baseline", "jvm", "android")
RUNTIMES = ("jdk8", "jdk21")
SOURCE_SHA = {
    "WorldArrayListMutationAuditConsumer.java": "1ce3047ec5675693ef3425883502abb1c82e62a830f032492f10ce1b11c3c1f6",
    "WorldExtraMethodsConsumer.java": "121826bbe176e2a5ed98a77eebf94f4186103c769a538baa3034ef2f79515374",
    "WorldListSemanticsConsumer.java": "431da69f017462e51de3c5d7638ebe0056bec7141a9ad8d8a24694f1356ffc69",
    "WorldProtectedListConsumer.java": "96b8d49356b488fb76677d6e95a758ac60dfb0703350b4ca512b61b098fea107",
    "WorldResultHelperConsumer.java": "5165f0d65ba2dc8003037f40340b3c493fb60aeaa99362454fd245523baddeff",
    "WorldViewIteratorConsumer.java": "18f60d2e8a696e89f3b39a1b95c93dfc70dc230beea93a2a564a00b6daf2d1d4",
    "org/dyn4j/world/WorldAllListsProbe.java": "769784fe5cfa79552d79635566d5a0a3c20b44efd84fea773acef364a699a37a",
    "org/dyn4j/world/WorldLegacyViewsProbe.java": "b6dee65ff342ca333b802e68358fdb2e9cb0b01ea0f8dc4555db677e68891db3",
    "org/dyn4j/world/WorldNestedEmptyClearProbe.java": "575bba29efb16fd127825d813b8ecd23b34fc6d1688c948896fc4ca3d0f30d17",
    "org/dyn4j/world/WorldReentryProbe.java": "2cd724e1748529e3d8b3935844e8e01fefc5b5180eec27baf30f18eda397112b",
    "org/dyn4j/world/WorldSerializableViewsConsumer.java": "24244a72699342000afa48039ee48c0dfb4a73b7221128ef56050e512e008746",
    "org/dyn4j/world/WorldSortExceptionProbe.java": "4ec0e2cc2ab0939167149defe280baf0f617010edad578936eec66366fb9dbfb",
}
MODES = {
    "org.dyn4j.world.WorldProtectedListConsumer": (
        "protected-sublist", "reversed-range", "random-access", "sort", "replace-all"),
    "WorldResultHelperConsumer": ("different", "same", "convex-different", "convex-same"),
    "WorldListSemanticsConsumer": ("backing", "sublist", "empty", "empty-sort", "empty-removeIf"),
}
PACKAGED_ROOT_SOURCES = {"WorldArrayListMutationAuditConsumer.java",
                         "WorldProtectedListConsumer.java"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_modes() -> tuple[tuple[str, str | None], ...]:
    modes = []
    for relative in SOURCE_SHA:
        name = Path(relative).stem
        packaged = relative.startswith("org/dyn4j/world/") or relative in PACKAGED_ROOT_SOURCES
        main = "org.dyn4j.world." + name if packaged else name
        modes.extend((main, mode) for mode in MODES.get(main, (None,)))
    if len(modes) != 23 or len(set(modes)) != 23:
        raise ValueError("World execution inventory differs from frozen 23 modes")
    return tuple(modes)


def validate_sources(source_root: Path, expected: dict[str, str]) -> None:
    if not expected or len(expected) != len(set(expected)):
        raise ValueError("World source inventory is empty or duplicated")
    for relative, sha in expected.items():
        path = source_root / relative
        if path.is_symlink() or not path.is_file() or digest(path) != sha:
            raise ValueError(f"World source differs: {relative}")


def runlog_name(provider: str, runtime: str, index: int) -> str:
    return f"runs/{provider}-{runtime}-{index:02d}.json"


def validate_runs(rows: list[dict], output: Path) -> dict[tuple[str, str, str | None], str]:
    expected = {(provider, runtime, main, mode): runlog_name(provider, runtime, index)
                for provider in PROVIDERS for runtime in RUNTIMES
                for index, (main, mode) in enumerate(expected_modes())}
    if not isinstance(rows, list) or len(rows) != 138:
        raise ValueError("World execution matrix must contain exactly 138 paths")
    observed = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("World execution row is malformed")
        key = (row.get("provider"), row.get("runtime"), row.get("main"), row.get("mode"))
        if key in observed or key not in expected or row.get("log") != expected[key]:
            raise ValueError("World execution key or log path differs")
        path = output / expected[key]
        if path.is_symlink() or not path.is_file() or digest(path) != row.get("log_sha256"):
            raise ValueError("World execution raw log is missing or changed")
        raw = json.loads(path.read_text())
        command = raw.get("command")
        suffix = [key[2]] + ([key[3]] if key[3] is not None else [])
        if (raw.get("exit") != 0 or row.get("exit") != 0 or
                not isinstance(raw.get("stdout"), str) or not raw["stdout"] or
                not isinstance(raw.get("stderr"), str) or
                not isinstance(command, list) or len(command) < 4 or
                not command[0].endswith("/bin/java") or command[1] != "-cp" or
                command[-len(suffix):] != suffix):
            raise ValueError("World execution failed or raw process identity differs")
        observed[key] = raw["stdout"]
    if set(observed) != set(expected):
        raise ValueError("World execution keys are incomplete")
    for (provider, runtime, main, mode), stdout in observed.items():
        if provider != "baseline" and stdout != observed[("baseline", runtime, main, mode)]:
            raise ValueError(f"World stdout differs from same-runtime baseline: {provider} {runtime} {main} {mode}")
    return {(runtime, main, mode): stdout for (provider, runtime, main, mode), stdout
            in observed.items() if provider == "baseline"}


def validate_adverse_output(baseline: str, mutant: str) -> None:
    if ("bodies,empty=VALUE:" not in baseline or
            "bodies,empty=NotSerializableException:org.dyn4j.world.AbstractCollisionWorldKt$worldReadOnlyView$1"
            not in mutant or mutant == baseline):
        raise ValueError("World body-view adverse control did not expose the known serialization regression")


def seal_files(output: Path, recorded: dict[str, str]) -> dict[str, str]:
    if not isinstance(recorded, dict) or not recorded:
        raise ValueError("World raw file inventory is empty")
    actual = {path.relative_to(output).as_posix(): path for path in output.rglob("*")
              if path.is_file() and path != output / "result.json"}
    if set(actual) != set(recorded):
        raise ValueError("World raw file set differs")
    for relative, path in actual.items():
        if path.is_symlink() or digest(path) != recorded[relative]:
            raise ValueError(f"World raw file hash differs: {relative}")
    return dict(sorted(recorded.items()))


def validate_report(report: dict, output: Path, candidate_sha: str,
                    provider_hashes: dict[str, str]) -> dict[str, str]:
    if (report.get("status") != "PASSED" or report.get("candidate_sha") != candidate_sha or
            report.get("frozen_commit") != FROZEN_COMMIT or
            report.get("source_sha256") != SOURCE_SHA or
            report.get("artifacts") != provider_hashes or
            report.get("bad_archive_sha256") != BAD_ARCHIVE_SHA):
        raise ValueError("World report identity or source/archive hashes differ")
    validate_sources(SOURCE_ROOT, SOURCE_SHA)
    validate_sources(output / "sources", SOURCE_SHA)
    for provider, sha in provider_hashes.items():
        path = output / "archives" / f"{provider}.jar"
        if path.is_symlink() or not path.is_file() or digest(path) != sha:
            raise ValueError(f"World frozen {provider} archive differs")
    bad = output / "archives/bad-body-view-bc71.jar"
    if bad.is_symlink() or not bad.is_file() or digest(bad) != BAD_ARCHIVE_SHA:
        raise ValueError("World bad-body-view archive differs")
    tools = report.get("tools", {})
    for name, prefix in (("javac8", "javac 1.8"), ("java8", 'openjdk version "1.8'),
                         ("java21", 'openjdk version "21')):
        if not isinstance(tools.get(name), str) or not tools[name].startswith(prefix):
            raise ValueError(f"World {name} version differs")
    jdks = report.get("jdks")
    stdlib = report.get("stdlib")
    if (not isinstance(jdks, dict) or set(jdks) != set(RUNTIMES) or
            any(not isinstance(path, str) or not Path(path, "bin/java").is_file()
                for path in jdks.values()) or
            not isinstance(stdlib, dict) or stdlib.get("sha256") != STDLIB_SHA or
            not isinstance(stdlib.get("path"), str) or
            digest(Path(stdlib["path"])) != STDLIB_SHA):
        raise ValueError("World JDK or standard library identity differs")
    compiles = report.get("compiles")
    if not isinstance(compiles, dict) or set(compiles) != set(PROVIDERS):
        raise ValueError("World Java 8 compile inventory differs")
    for provider, compile_row in compiles.items():
        log = output / "compiles" / f"{provider}.json"
        if (compile_row.get("exit") != 0 or compile_row.get("log") != f"compiles/{provider}.json" or
                log.is_symlink() or not log.is_file() or digest(log) != compile_row.get("log_sha256") or
                json.loads(log.read_text()).get("exit") != 0):
            raise ValueError(f"World Java 8 source compilation failed: {provider}")
        command = json.loads(log.read_text()).get("command")
        expected_command = [str(Path(jdks["jdk8"]) / "bin/javac"), "-cp",
                            str(output / "archives" / f"{provider}.jar"), "-d",
                            str(output / "classes" / provider),
                            *(str(output / "sources" / relative) for relative in SOURCE_SHA)]
        if command != expected_command:
            raise ValueError(f"World Java 8 compile command differs: {provider}")
    baseline_outputs = validate_runs(report.get("runs"), output)
    for row in report["runs"]:
        provider, runtime, main, mode = (row[key] for key in ("provider", "runtime", "main", "mode"))
        classpath = os.pathsep.join((str(output / "classes" / provider),
                                     str(output / "archives" / f"{provider}.jar"),
                                     stdlib["path"]))
        expected_command = [str(Path(jdks[runtime]) / "bin/java"), "-cp", classpath, main]
        if mode is not None:
            expected_command.append(mode)
        if json.loads((output / row["log"]).read_text()).get("command") != expected_command:
            raise ValueError("World execution command differs from staged provider")
    adverse = report.get("adverse")
    if (not isinstance(adverse, dict) or set(adverse) != set(RUNTIMES) or
            any(not isinstance(row, dict) for row in adverse.values())):
        raise ValueError("World adverse runtime inventory differs")
    adverse_compile = output / "compiles/bad-body-view.json"
    if (not adverse_compile.is_file() or
            json.loads(adverse_compile.read_text()).get("exit") != 0):
        raise ValueError("World bad-body-view source compilation failed")
    bad_source = output / "sources/org/dyn4j/world/WorldSerializableViewsConsumer.java"
    bad_compile_command = [str(Path(jdks["jdk8"]) / "bin/javac"), "-cp", str(bad),
                           "-d", str(output / "classes/bad-body-view"), str(bad_source)]
    if json.loads(adverse_compile.read_text()).get("command") != bad_compile_command:
        raise ValueError("World bad-body-view compile command differs")
    for runtime, row in adverse.items():
        log_name = f"adverse/{runtime}.json"
        log = output / log_name
        if (row.get("log") != log_name or row.get("exit") != 0 or log.is_symlink() or
                not log.is_file() or digest(log) != row.get("log_sha256")):
            raise ValueError(f"World bad-body-view process differs: {runtime}")
        raw = json.loads(log.read_text())
        if raw.get("exit") != 0 or not isinstance(raw.get("stdout"), str):
            raise ValueError(f"World bad-body-view process failed: {runtime}")
        bad_classpath = os.pathsep.join((str(output / "classes/bad-body-view"),
                                         str(bad), stdlib["path"]))
        if raw.get("command") != [str(Path(jdks[runtime]) / "bin/java"), "-cp", bad_classpath,
                                  "org.dyn4j.world.WorldSerializableViewsConsumer"]:
            raise ValueError(f"World bad-body-view command differs: {runtime}")
        validate_adverse_output(baseline_outputs[(runtime,
                                "org.dyn4j.world.WorldSerializableViewsConsumer", None)],
                                raw["stdout"])
    return seal_files(output, report.get("files"))


def seal_world(output: Path, candidate_sha: str, provider_hashes: dict[str, str],
               report_sha: str) -> dict[str, str]:
    result = output / "result.json"
    if result.is_symlink() or not result.is_file() or digest(result) != report_sha:
        raise ValueError("World report is missing or changed before upload")
    report = json.loads(result.read_text())
    files = validate_report(report, output, candidate_sha, provider_hashes)
    return {"result.json": report_sha, **files}


def process(command: list[str], path: Path, timeout: int = 90) -> dict:
    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    raw = {"command": command, "exit": completed.returncode,
           "stdout": completed.stdout, "stderr": completed.stderr}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, indent=2) + "\n")
    return raw


def execute(args: argparse.Namespace) -> dict:
    output = args.output.resolve()
    if any(output.iterdir()):
        raise ValueError("World output directory must be empty")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != args.candidate_sha:
        raise ValueError("World candidate SHA differs from checkout")
    validate_sources(SOURCE_ROOT, SOURCE_SHA)
    if digest(args.stdlib) != STDLIB_SHA or digest(BAD_ARCHIVE) != BAD_ARCHIVE_SHA:
        raise ValueError("World standard library or adverse archive hash differs")
    jdks = {"jdk8": args.java8.resolve(), "jdk21": args.java21.resolve()}
    tools = {}
    for name, command in (("javac8", args.java8 / "bin/javac"),
                          ("java8", args.java8 / "bin/java"),
                          ("java21", args.java21 / "bin/java")):
        version = subprocess.run([str(command.resolve()), "-version"], capture_output=True,
                                 text=True, timeout=30)
        if version.returncode:
            raise ValueError(f"World {name} is unavailable")
        tools[name] = (version.stdout + version.stderr).splitlines()[0]
    archives = {"baseline": args.baseline.resolve(), "jvm": args.jvm.resolve(),
                "android": args.android.resolve()}
    hashes = {provider: digest(path) for provider, path in archives.items()}
    if hashes["baseline"] != BASELINE_SHA or any(hashes[name] == BASELINE_SHA
                                                  for name in ("jvm", "android")):
        raise ValueError("World baseline or candidate archive identity differs")
    report = {"status": "FAILED", "candidate_sha": args.candidate_sha,
              "frozen_commit": FROZEN_COMMIT, "source_sha256": SOURCE_SHA,
              "artifacts": hashes, "bad_archive_sha256": BAD_ARCHIVE_SHA,
              "tools": tools, "jdks": {name: str(path) for name, path in jdks.items()},
              "stdlib": {"path": str(args.stdlib.resolve()), "sha256": STDLIB_SHA},
              "compiles": {}, "runs": [], "adverse": {}, "files": {}}
    for relative in SOURCE_SHA:
        target = output / "sources" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE_ROOT / relative, target)
    for provider, original in archives.items():
        frozen = output / "archives" / f"{provider}.jar"
        frozen.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, frozen)
        if digest(frozen) != hashes[provider]:
            raise ValueError(f"World {provider} archive changed while copying")
        with zipfile.ZipFile(frozen) as jar:
            if jar.testzip() is not None or (provider != "baseline" and not any(
                    name.endswith(".kotlin_module") for name in jar.namelist())):
                raise ValueError(f"World {provider} archive is invalid")
    shutil.copyfile(BAD_ARCHIVE, output / "archives/bad-body-view-bc71.jar")
    sources = [str(output / "sources" / relative) for relative in SOURCE_SHA]
    for provider in PROVIDERS:
        classes = output / "classes" / provider
        classes.mkdir(parents=True)
        command = [str(jdks["jdk8"] / "bin/javac"), "-cp",
                   str(output / "archives" / f"{provider}.jar"), "-d", str(classes), *sources]
        name = f"compiles/{provider}.json"
        raw = process(command, output / name, timeout=120)
        report["compiles"][provider] = {"exit": raw["exit"], "log": name,
                                        "log_sha256": digest(output / name)}
        if raw["exit"]:
            raise ValueError(f"World Java 8 source compilation failed: {provider}")
    for provider in PROVIDERS:
        for runtime in RUNTIMES:
            for index, (main, mode) in enumerate(expected_modes()):
                classpath = os.pathsep.join((str(output / "classes" / provider),
                                             str(output / "archives" / f"{provider}.jar"),
                                             str(args.stdlib.resolve())))
                command = [str(jdks[runtime] / "bin/java"), "-cp", classpath, main]
                if mode is not None:
                    command.append(mode)
                name = runlog_name(provider, runtime, index)
                raw = process(command, output / name)
                report["runs"].append({"provider": provider, "runtime": runtime,
                                       "main": main, "mode": mode, "exit": raw["exit"],
                                       "log": name, "log_sha256": digest(output / name)})
    baseline_outputs = validate_runs(report["runs"], output)
    bad_classes = output / "classes/bad-body-view"
    bad_classes.mkdir(parents=True)
    bad_source = output / "sources/org/dyn4j/world/WorldSerializableViewsConsumer.java"
    bad_jar = output / "archives/bad-body-view-bc71.jar"
    raw = process([str(jdks["jdk8"] / "bin/javac"), "-cp", str(bad_jar), "-d",
                   str(bad_classes), str(bad_source)], output / "compiles/bad-body-view.json", 120)
    if raw["exit"]:
        raise ValueError("World bad-body-view source compilation failed")
    for runtime in RUNTIMES:
        classpath = os.pathsep.join((str(bad_classes), str(bad_jar), str(args.stdlib.resolve())))
        command = [str(jdks[runtime] / "bin/java"), "-cp", classpath,
                   "org.dyn4j.world.WorldSerializableViewsConsumer"]
        name = f"adverse/{runtime}.json"
        raw = process(command, output / name)
        report["adverse"][runtime] = {"exit": raw["exit"], "log": name,
                                      "log_sha256": digest(output / name)}
        if raw["exit"]:
            raise ValueError(f"World bad-body-view process failed: {runtime}")
        validate_adverse_output(baseline_outputs[(runtime,
                                "org.dyn4j.world.WorldSerializableViewsConsumer", None)],
                                raw["stdout"])
    report["files"] = {path.relative_to(output).as_posix(): digest(path)
                       for path in output.rglob("*") if path.is_file()}
    report["status"] = "PASSED"
    validate_report(report, output, args.candidate_sha, hashes)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run and seal frozen World Java compatibility fixtures.")
    parser.add_argument("--candidate-sha", required=True)
    for name in ("baseline", "jvm", "android", "java8", "java21", "stdlib", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        report = execute(args)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, json.JSONDecodeError,
            subprocess.TimeoutExpired, zipfile.BadZipFile) as error:
        report = {"status": "FAILED", "candidate_sha": args.candidate_sha,
                  "errors": [str(error)],
                  "partial_runs": len(list(args.output.glob("runs/*.json"))),
                  "partial_files": sorted(path.relative_to(args.output).as_posix()
                                          for path in args.output.rglob("*") if path.is_file())}
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "errors": report.get("errors", []),
                      "runs": len(report.get("runs", [])) or report.get("partial_runs", 0)}, indent=2))
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
