from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import struct
import subprocess
import sys
import zipfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures/exception_serialization"
GOLDEN = HERE / "exception-public-api-projection.json"
DRIVER_SHA = "f0c76b86ca0f7e9b8eeeeb8265d51a0f627148578fc4d4baacdd1e6bab1038e1"
PROBE_SHA = "7ea22a8470adac3d78591bb4eaa872cb2f700e737c038d78e93031143a8e85b1"
BASELINE_SHA = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
STDLIB_SHA = "2226de463d309d4a5500a481320b3dea515a6981dcae1def531fbc158884e25f"
UIDS = {
    "ArgumentNullException": 7104871716542808869,
    "CopyException": 2434249738746680073,
    "EmptyCollectionException": 3188055341987092721,
    "SameObjectException": -2844289260493601312,
    "InvalidIndexException": 1297019115982655104,
    "ValueOutOfRangeException": -7115378379246433066,
    "ObjectAlreadyExistsException": 3414084132509765709,
    "ObjectAlreadyOwnedException": -7471557485578931121,
    "NullElementException": 4560521220204618552,
}
CASES = (
    "ArgumentNullException", "CopyException", "EmptyCollectionException",
    "SameObjectException", "InvalidIndexException", "ObjectAlreadyExistsException",
    "ObjectAlreadyOwnedException", "NullElementException-index",
    "NullElementException-name", "ValueOutOfRangeException-int",
    "ValueOutOfRangeException-double", "ValueOutOfRangeException-bound-int",
    "ValueOutOfRangeException-bound-double", "ValueOutOfRangeException-pair-int",
    "ValueOutOfRangeException-pair-double",
)
PROVIDERS = ("baseline", "jvm", "android")
RUNTIMES = ("jdk8", "jdk21")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_exception_report(report: dict, output: Path, provider_hashes: dict[str, str],
                              probe_hash: str, driver_hash: str, stdlib_hash: str) -> None:
    if (report.get("passed") is not True or report.get("failure_count") != 0 or
            report.get("baseline_sha256") != provider_hashes["baseline"] or
            report.get("probe_sha256") != probe_hash or
            report.get("driver_sha256") != driver_hash or
            report.get("stdlib_sha256") != stdlib_hash):
        raise ValueError("exception fixture status or input hashes differ")
    providers = report.get("providers")
    if (not isinstance(providers, dict) or set(providers) != set(PROVIDERS) or
            any(providers[name].get("sha256") != provider_hashes[name] for name in PROVIDERS)):
        raise ValueError("exception fixture provider hashes differ")
    if report.get("cases") != list(CASES):
        raise ValueError("exception constructor inventory differs")
    if (set(report.get("compiles", {})) != set(PROVIDERS) or
            any(report["compiles"][name].get("exit") != 0 for name in PROVIDERS) or
            set(report.get("versions", {})) != set(RUNTIMES) or
            any(report["versions"][name].get("exit") != 0 for name in RUNTIMES)):
        raise ValueError("exception fixture compiler or runtime failed")
    identities = report.get("identities")
    expected_identity_keys = {(provider, "org.dyn4j.exception." + name)
                              for provider in PROVIDERS for name in UIDS}
    if not isinstance(identities, list) or len(identities) != 27:
        raise ValueError("exception private UID inventory is incomplete")
    observed_identity_keys = set()
    for row in identities:
        key = (row.get("provider"), row.get("type"))
        name = row.get("type", "").removeprefix("org.dyn4j.exception.")
        uid = UIDS.get(name)
        if (key in observed_identity_keys or key not in expected_identity_keys or
                row.get("expected") != uid or row.get("exit") != 0 or
                row.get("matches") is not True or
                re.findall(r"^  private static final long serialVersionUID = (-?\d+)l;$",
                           row.get("stdout", ""), re.MULTILINE) != [str(uid)]):
            raise ValueError("exception private UID identity differs")
        observed_identity_keys.add(key)
    if observed_identity_keys != expected_identity_keys:
        raise ValueError("exception private UID identities are incomplete")
    runs = report.get("runs")
    if not isinstance(runs, list) or len(runs) != 636:
        raise ValueError("exception process matrix is incomplete")
    expected_ids = {(runtime, provider) for runtime in RUNTIMES for provider in PROVIDERS}
    expected_writes = {(runtime, provider, case) for runtime in RUNTIMES
                       for provider in PROVIDERS for case in CASES}
    expected_reads = {(writer_runtime, writer_provider, case, reader_runtime, reader_provider)
                      for writer_runtime in RUNTIMES for writer_provider in PROVIDERS
                      for case in CASES for reader_runtime in RUNTIMES
                      for reader_provider in PROVIDERS}
    ids, writes, reads = set(), set(), set()
    baseline_outputs = {}
    for row in runs:
        if row.get("exit") != 0 or row.get("matches") is not True:
            raise ValueError("exception process failed or did not match baseline")
        operation = row.get("operation")
        if operation == "ids":
            key = (row.get("runtime"), row.get("provider"))
            expected = "".join(f"{name}={uid}\n" for name, uid in UIDS.items())
            if key in ids or key not in expected_ids or row.get("stdout") != expected:
                raise ValueError("exception effective UID process differs")
            ids.add(key)
        elif operation == "write":
            key = (row.get("writer_runtime"), row.get("writer_provider"), row.get("case"))
            if (key in writes or key not in expected_writes or row.get("runtime") != key[0] or
                    row.get("provider") != key[1]):
                raise ValueError("exception writer process differs")
            command = row.get("command")
            stream = output / f"{key[0]}-{key[1]}-{key[2]}.ser"
            if (not isinstance(command, list) or len(command) < 2 or
                    command[-2:] != [str(stream), key[2]] or not stream.is_file() or
                    digest(stream) != row.get("stream_sha256")):
                raise ValueError("exception serialized stream is missing or changed")
            stdout = row.get("stdout", "")
            expected_type = key[2].split("-", 1)[0]
            if (not stdout.startswith(f"TYPE=org.dyn4j.exception.{expected_type}\nMESSAGE=") or
                    "\nCAUSE=java.lang.IllegalStateException:cause\n" not in stdout or
                    "\nSUPPRESSED=java.lang.IllegalArgumentException:suppressed\n" not in stdout or
                    not stdout.endswith("\nSTACK=Example:run:Example.java:12\n")):
                raise ValueError("exception writer payload is incomplete")
            writes.add(key)
            if key[1] == "baseline":
                baseline_outputs[(key[0], key[2])] = stdout
        elif operation == "read":
            key = (row.get("writer_runtime"), row.get("writer_provider"), row.get("case"),
                   row.get("runtime"), row.get("provider"))
            if key in reads or key not in expected_reads:
                raise ValueError("exception reader process differs")
            reads.add(key)
        else:
            raise ValueError("unknown exception process operation")
    if ids != expected_ids or writes != expected_writes or reads != expected_reads:
        raise ValueError("exception process keys are missing or duplicated")
    if {path.name for path in output.glob("*.ser")} != {
            f"{runtime}-{provider}-{case}.ser" for runtime, provider, case in expected_writes}:
        raise ValueError("exception serialized stream set differs")
    for row in runs:
        if row["operation"] in ("write", "read") and row.get("stdout") != baseline_outputs[
                (row["writer_runtime"], row["case"])]:
            raise ValueError("exception payload differs from pinned baseline")


def public_projection(archives: dict[str, Path], javap: Path, output: Path) -> dict:
    golden = json.loads(GOLDEN.read_text())
    if set(golden.get("types", {})) != {"org.dyn4j.exception." + name for name in UIDS}:
        raise ValueError("exception public API reference inventory differs")
    output.mkdir(parents=True, exist_ok=True)
    observed = {}
    for provider in ("jvm", "android"):
        for name, expected in golden["types"].items():
            result = subprocess.run([str(javap), "-public", "-classpath", str(archives[provider]), name],
                                    capture_output=True, text=True, timeout=60)
            path = output / f"{provider}-{name.rsplit('.', 1)[-1]}.txt"
            path.write_text(result.stdout + result.stderr)
            if result.returncode or hashlib.sha256(result.stdout.encode()).hexdigest() != expected:
                raise ValueError(f"exception public API projection differs: {provider} {name}")
            observed[f"{provider}:{name}"] = digest(path)
    (output / "result.json").write_text(json.dumps({"reference_sha256": digest(GOLDEN),
                                                    "observations": observed}, indent=2) + "\n")
    return observed


def seal_exception(output: Path, expected: dict[str, str], summary_sha: str) -> dict[str, str]:
    summary_path = output / "result.json"
    if not summary_path.is_file() or digest(summary_path) != summary_sha:
        raise ValueError("exception summary is missing or changed before upload")
    summary = json.loads(summary_path.read_text())
    if summary.get("status") != "PASSED" or summary.get("providers") != expected:
        raise ValueError("exception gate did not pass for the staged archives")
    paths = {"result.json": summary_path}
    fixture_path = output / "fixture/result.json"
    if not fixture_path.is_file() or digest(fixture_path) != summary["fixture"]["report_sha256"]:
        raise ValueError("exception fixture report is missing or changed")
    fixture = json.loads(fixture_path.read_text())
    validate_exception_report(fixture, output / "fixture", expected,
                              PROBE_SHA, DRIVER_SHA, STDLIB_SHA)
    paths["fixture/result.json"] = fixture_path
    for provider, archive_hash in expected.items():
        frozen = output / "fixture" / f"{provider}.jar"
        if not frozen.is_file() or digest(frozen) != archive_hash:
            raise ValueError(f"exception frozen {provider} archive differs")
        paths[f"fixture/{provider}.jar"] = frozen
    for stream in (output / "fixture").glob("*.ser"):
        paths[f"fixture/{stream.name}"] = stream

    public_path = output / "public-api/result.json"
    if not public_path.is_file() or digest(public_path) != summary["public_api"]["report_sha256"]:
        raise ValueError("exception public API report is missing or changed")
    public = json.loads(public_path.read_text())
    if public.get("reference_sha256") != digest(GOLDEN) or len(public.get("observations", {})) != 18:
        raise ValueError("exception public API reference or count differs")
    paths["public-api/result.json"] = public_path
    expected_keys = {f"{provider}:{name}" for provider in ("jvm", "android")
                     for name in json.loads(GOLDEN.read_text())["types"]}
    if set(public["observations"]) != expected_keys:
        raise ValueError("exception public API observation keys differ")
    expected_public = set()
    for key, expected_hash in public["observations"].items():
        provider, name = key.split(":", 1)
        file = output / "public-api" / f"{provider}-{name.rsplit('.', 1)[-1]}.txt"
        if not file.is_file() or digest(file) != expected_hash:
            raise ValueError("exception public API output is missing or changed")
        expected_public.add(file.name)
        paths[f"public-api/{file.name}"] = file
    if {path.name for path in (output / "public-api").glob("*.txt")} != expected_public:
        raise ValueError("exception public API output file set differs")

    uid_path = output / "uid-adverse/result.json"
    uid = summary["adverse"]["uid"]
    if not uid_path.is_file() or digest(uid_path) != uid["report_sha256"]:
        raise ValueError("exception UID adverse report is missing or changed")
    uid_report = json.loads(uid_path.read_text())
    if (uid_report.get("passed") is not False or
            uid_report.get("failure_count") != uid["failure_count"] or
            len(uid_report.get("runs", [])) != 636):
        raise ValueError("exception UID adverse control differs")
    paths["uid-adverse/result.json"] = uid_path
    for relative, expected_hash in (("uid-mutant.jar", uid["mutant_sha256"]),
                                    ("payload-mutant.ser", summary["adverse"]["payload"]["mutant_sha256"]),
                                    ("payload-adverse.log", summary["adverse"]["payload"]["read_log_sha256"])):
        path = output / relative
        if not path.is_file() or digest(path) != expected_hash:
            raise ValueError(f"exception adverse raw file differs: {relative}")
        paths[relative] = path
    return {name: digest(path) for name, path in sorted(paths.items())}


def mutate_uid(source: Path, target: Path) -> None:
    name = "org/dyn4j/exception/ArgumentNullException.class"
    before = struct.pack(">q", UIDS["ArgumentNullException"])
    after = struct.pack(">q", UIDS["ArgumentNullException"] + 1)
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w") as mutated:
        for item in original.infolist():
            contents = original.read(item.filename)
            if item.filename == name:
                if contents.count(before) != 1:
                    raise ValueError("UID mutation target was not unique")
                contents = contents.replace(before, after)
            mutated.writestr(item, contents)
    if digest(source) == digest(target):
        raise ValueError("UID mutation did not change the archive")


def execute(args: argparse.Namespace) -> dict:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary = {"status": "FAILED", "errors": [], "fixture": {}, "public_api": {}, "adverse": {}}
    archives = {"baseline": args.baseline.resolve(), "jvm": args.jvm.resolve(),
                "android": args.android.resolve()}
    expected = {name: digest(path) for name, path in archives.items()}
    if expected["baseline"] != BASELINE_SHA or digest(args.stdlib) != STDLIB_SHA:
        raise ValueError("exception baseline or Kotlin standard library hash differs")
    driver = FIXTURE / "verify.py"
    probe = FIXTURE / "ExceptionSerializationProbe.java"
    if digest(driver) != DRIVER_SHA or digest(probe) != PROBE_SHA:
        raise ValueError("reviewed exception fixture source hash differs")

    def fixture_run(destination: Path, jvm: Path, log: Path) -> tuple[subprocess.CompletedProcess, dict]:
        command = [sys.executable, str(driver), "--baseline", str(archives["baseline"]),
                   "--jvm", str(jvm), "--android", str(archives["android"]),
                   "--java8", str(args.java8.resolve()), "--java21", str(args.java21.resolve()),
                   "--stdlib", str(args.stdlib.resolve()), "--output", str(destination)]
        process = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        log.write_text(process.stdout + process.stderr)
        report_path = destination / "result.json"
        if not report_path.is_file():
            raise ValueError(f"exception fixture did not write {report_path}")
        return process, json.loads(report_path.read_text())

    fixture_output = output / "fixture"
    green, report = fixture_run(fixture_output, archives["jvm"], output / "fixture.log")
    if green.returncode:
        raise ValueError("exception serialization fixture failed")
    validate_exception_report(report, fixture_output, expected, PROBE_SHA, DRIVER_SHA, STDLIB_SHA)
    summary["fixture"] = {"report_sha256": digest(fixture_output / "result.json"),
                          "processes": len(report["runs"]), "identities": len(report["identities"]),
                          "stream_count": len(list(fixture_output.glob("*.ser")))}
    observed = public_projection(archives, args.java21 / "bin/javap", output / "public-api")
    summary["public_api"] = {"report_sha256": digest(output / "public-api/result.json"),
                             "observations": len(observed)}

    mutant = output / "uid-mutant.jar"
    mutate_uid(archives["jvm"], mutant)
    uid_output = output / "uid-adverse"
    red, adverse_report = fixture_run(uid_output, mutant, output / "uid-adverse.log")
    if (red.returncode == 0 or adverse_report.get("passed") is not False or
            adverse_report.get("failure_count", 0) < 1 or len(adverse_report.get("runs", [])) != 636 or
            not any(row.get("provider") == "jvm" and
                    row.get("type") == "org.dyn4j.exception.ArgumentNullException" and
                    row.get("matches") is False for row in adverse_report.get("identities", []))):
        raise ValueError("UID mutation was not rejected by the complete fixture")
    summary["adverse"]["uid"] = {"mutant_sha256": digest(mutant),
                                  "report_sha256": digest(uid_output / "result.json"),
                                  "failure_count": adverse_report["failure_count"]}

    stream = fixture_output / "jdk8-baseline-ArgumentNullException.ser"
    original = stream.read_bytes()
    marker = b"t\x00\x05cause"
    if original.count(marker) != 1:
        raise ValueError("payload mutation target was not unique")
    payload = output / "payload-mutant.ser"
    payload.write_bytes(original.replace(marker, b"t\x00\x05cauze"))
    classpath = ":".join((str(fixture_output / "classes/jvm"),
                          str(fixture_output / "jvm.jar"), str(args.stdlib.resolve())))
    observed = subprocess.run([str(args.java8 / "bin/java"), "-cp", classpath,
                               "ExceptionSerializationProbe", "read", str(payload),
                               "ArgumentNullException"], capture_output=True, text=True, timeout=60)
    (output / "payload-adverse.log").write_text(observed.stdout + observed.stderr)
    if observed.returncode or "CAUSE=java.lang.IllegalStateException:cauze\n" not in observed.stdout:
        raise ValueError("payload mutation did not reach the Java reader")
    changed = copy.deepcopy(report)
    row = next(row for row in changed["runs"] if row.get("operation") == "read" and
               row.get("writer_runtime") == "jdk8" and row.get("writer_provider") == "baseline" and
               row.get("case") == "ArgumentNullException" and row.get("runtime") == "jdk8" and
               row.get("provider") == "jvm")
    row["stdout"] = observed.stdout
    try:
        validate_exception_report(changed, fixture_output, expected, PROBE_SHA, DRIVER_SHA, STDLIB_SHA)
    except ValueError as error:
        summary["adverse"]["payload"] = {"mutant_sha256": digest(payload),
                                          "validator_rejection": str(error),
                                          "read_log_sha256": digest(output / "payload-adverse.log")}
    else:
        raise ValueError("changed serialized payload passed the CI validator")
    summary["providers"] = expected
    summary["status"] = "PASSED"
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the reviewed exception serialization fixture.")
    for name in ("baseline", "jvm", "android", "java8", "java21", "stdlib", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    try:
        result = execute(args)
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired,
            zipfile.BadZipFile) as error:
        result = {"status": "FAILED", "errors": [str(error)]}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "errors": result.get("errors", [])}, indent=2))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
