import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


EXPECTED_IDS = {
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
BASELINE_SHA256 = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args):
    command = [str(arg) for arg in args]
    completed = subprocess.run(command, text=True, capture_output=True)
    return {"command": command, "exit": completed.returncode,
            "stdout": completed.stdout, "stderr": completed.stderr}


def main():
    parser = argparse.ArgumentParser(description="Check pinned exception streams across staged archives")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--jvm", type=Path, required=True)
    parser.add_argument("--android", type=Path, required=True)
    parser.add_argument("--java8", type=Path, required=True, help="JDK 8 home")
    parser.add_argument("--java21", type=Path, required=True, help="JDK 21 home")
    parser.add_argument("--stdlib", type=Path, required=True, help="Kotlin stdlib JAR")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previous-jvm", type=Path)
    parser.add_argument("--previous-android", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    providers = {}
    for name, source in (("baseline", args.baseline), ("jvm", args.jvm), ("android", args.android)):
        frozen = args.output / (name + ".jar")
        frozen.write_bytes(source.read_bytes())
        providers[name] = {"source": str(source.resolve()), "path": str(frozen.resolve()), "sha256": digest(frozen)}
    if providers["baseline"]["sha256"] != BASELINE_SHA256:
        raise ValueError("baseline JAR does not match dyn4j 6.0.0 pin")

    source = Path(__file__).with_name("ExceptionSerializationProbe.java")
    classes = args.output / "classes"
    classes.mkdir()
    javac = args.java8 / "bin/javac"
    java = {"jdk8": args.java8 / "bin/java", "jdk21": args.java21 / "bin/java"}
    javap = args.java21 / "bin/javap"
    compiles = {}
    for provider, artifact in providers.items():
        target = classes / provider
        target.mkdir()
        compiles[provider] = run(javac, "-cp", artifact["path"], "-d", target, source)
    versions = {name: run(binary, "-version") for name, binary in java.items()}
    identities = []
    public_api = []
    previous = {"jvm": args.previous_jvm, "android": args.previous_android}
    for provider, artifact in providers.items():
        for name, expected in EXPECTED_IDS.items():
            fqcn = "org.dyn4j.exception." + name
            entry = run(javap, "-p", "-constants", "-classpath", artifact["path"], fqcn)
            pattern = r"^  private static final long serialVersionUID = (-?\d+)l;$"
            values = re.findall(pattern, entry["stdout"], re.MULTILINE)
            entry.update(provider=provider, type=fqcn, expected=expected,
                         matches=entry["exit"] == 0 and values == [str(expected)])
            identities.append(entry)
            if previous.get(provider):
                before = run(javap, "-public", "-classpath", previous[provider], fqcn)
                after = run(javap, "-public", "-classpath", artifact["path"], fqcn)
                public_api.append({"provider": provider, "type": fqcn, "before": before,
                                   "after": after, "matches": before["exit"] == after["exit"] == 0
                                   and before["stdout"] == after["stdout"]})

    runs = []

    def probe(runtime, provider, operation, case=None, stream=None):
        classpath = ":".join((str(classes / provider), providers[provider]["path"], str(args.stdlib)))
        command = (java[runtime], "-cp", classpath, "ExceptionSerializationProbe", operation)
        if case is not None:
            command += (stream, case)
        result = run(*command)
        result.update(runtime=runtime, provider=provider, operation=operation, case=case)
        runs.append(result)
        return result

    for runtime in java:
        for provider in providers:
            observed = probe(runtime, provider, "ids")
            expected = "".join("{}={}\n".format(name, value) for name, value in EXPECTED_IDS.items())
            observed["matches"] = observed["exit"] == 0 and observed["stdout"] == expected

    for writer_runtime in java:
        for case in CASES:
            baseline = None
            for writer_provider in providers:
                stream = args.output / (writer_runtime + "-" + writer_provider + "-" + case + ".ser")
                written = probe(writer_runtime, writer_provider, "write", case, stream)
                written["writer_runtime"] = writer_runtime
                written["writer_provider"] = writer_provider
                written["matches"] = written["exit"] == 0 and stream.is_file()
                if not written["matches"]:
                    continue
                written["stream_sha256"] = digest(stream)
                if writer_provider == "baseline":
                    baseline = written["stdout"]
                written["matches"] = baseline is not None and written["stdout"] == baseline
                for reader_runtime in java:
                    for reader_provider in providers:
                        observed = probe(reader_runtime, reader_provider, "read", case, stream)
                        observed.update(writer_runtime=writer_runtime, writer_provider=writer_provider,
                                        matches=observed["exit"] == 0 and observed["stdout"] == baseline)

    failures = ([item for item in identities + public_api + runs if not item["matches"]]
                + [item for item in compiles.values() if item["exit"] != 0]
                + [item for item in versions.values() if item["exit"] != 0])
    report = {"providers": providers, "baseline_sha256": BASELINE_SHA256,
              "probe_sha256": digest(source), "driver_sha256": digest(Path(__file__)),
              "stdlib_sha256": digest(args.stdlib), "versions": versions,
              "compiles": compiles, "identities": identities, "public_api": public_api,
              "cases": CASES, "runs": runs, "failure_count": len(failures),
              "passed": not failures}
    result = args.output / "result.json"
    result.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "failure_count": len(failures),
                      "runs": len(runs), "result": str(result),
                      "result_sha256": digest(result)}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
