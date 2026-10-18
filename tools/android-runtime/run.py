#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from evidence import parse_instrumentation, validate_lane
from prepare import verify_consumer_sources


CONSUMER_CASES = {"io.github.rubixhacker.dyn4k.runtime." + name for name in (
    "ConsumerJourneyTest#geometryAndIdentity",
    "ConsumerJourneyTest#collisionAndExtension",
    "ConsumerJourneyTest#collisionModel",
    "ConsumerJourneyTest#dynamicsAndErrors",
    "ConsumerJourneyTest#worldAndCallbacks",
    "ConsumerJourneyTest#jointsAndExtension",
    "ConsumerJourneyTest#contacts",
)}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args, output=None, check=True):
    run = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(run.stdout)
    if check and run.returncode:
        raise RuntimeError(f"command failed ({run.returncode}): {' '.join(args)}: {run.stdout[-1200:]}")
    return run.stdout


def expected_portable(root, classes):
    expected = set()
    for module in ("dyn4k-core", "dyn4k"):
        directory = root / module / "build/test-results/jvmTest"
        reports = sorted(directory.glob("TEST-*.xml"))
        if not reports:
            raise ValueError(f"raw JVM case inventory missing: {directory}")
        source_times = [path.stat().st_mtime_ns for path in
                        (root / module / "src/commonTest/kotlin").rglob("*.kt")]
        if not source_times or any(report.stat().st_mtime_ns < max(source_times) for report in reports):
            raise ValueError(f"stale raw JVM case inventory: {directory}")
        for report in reports:
            tree = ET.parse(report)
            for case in tree.findall(".//testcase"):
                name = case.attrib.get("classname", "")
                if name in classes:
                    method = case.attrib.get("name", "").removesuffix("[jvm]")
                    identity = name + "#" + method
                    if identity in expected:
                        raise ValueError(f"duplicate JVM inventory case: {identity}")
                    expected.add(identity)
    if not expected or any(name not in {case.split("#")[0] for case in expected} for name in classes):
        raise ValueError("portable class absent from raw JVM inventory")
    return expected


def apk_path(app, flavor, build_type, test):
    directory = app / "build/outputs/apk"
    if test:
        directory /= f"androidTest/{flavor}/{build_type}"
    else:
        directory /= f"{flavor}/{build_type}"
    files = list(directory.glob("*.apk"))
    if len(files) != 1:
        raise ValueError(f"expected one APK at {directory}, found {len(files)}")
    return files[0]


def run_lane(root, prepared, portable, flavor, build_type, evidence_root, adb, prepared_path, prepared_checksum):
    app = root / "consumers/android-runtime/app"
    apk = apk_path(app, flavor, build_type, False)
    test_apk = apk_path(app, flavor, build_type, True)
    package = f"io.github.rubixhacker.dyn4k.runtime.{flavor}"
    directory = evidence_root / f"{flavor}-{build_type}"
    directory.mkdir(parents=True, exist_ok=True)
    result = {"flavor": flavor, "build_type": build_type, "package": package,
              "app_apk": {"path": str(apk), "sha256": sha256(apk)},
              "test_apk": {"path": str(test_apk), "sha256": sha256(test_apk)},
              "candidate_commit": prepared["candidate_commit"],
              "prepared_manifest": {"path": str(prepared_path), "sha256": prepared_checksum},
              "staged": prepared["staged"], "baseline_jar": prepared["baseline_jar"],
              "consumer_sources": prepared["consumer_sources"],
              "generated_consumer_sources": prepared["generated_consumer_sources"],
              "portable_jar": prepared["portable_jar"], "status": "FAILED"}
    try:
        verify_consumer_sources(root, prepared)
        if apk.stat().st_mtime_ns < prepared_path.stat().st_mtime_ns or test_apk.stat().st_mtime_ns < prepared_path.stat().st_mtime_ns:
            raise ValueError("APK predates prepared candidate inputs")
        if build_type == "release":
            mapping = app / f"build/outputs/mapping/{flavor}Release/mapping.txt"
            if not mapping.is_file() or not mapping.stat().st_size:
                raise ValueError("R8 mapping missing")
            result["r8_mapping"] = {"path": str(mapping), "sha256": sha256(mapping)}
        command(adb + ["install", "-r", str(apk)], directory / "install-app.txt")
        command(adb + ["install", "-r", str(test_apk)], directory / "install-test.txt")
        result["package_path"] = command(adb + ["shell", "pm", "path", package], directory / "package-path.txt").strip()
        if not result["package_path"].startswith("package:"):
            raise ValueError("installed package path absent")
        result["package_info"] = command(adb + ["shell", "dumpsys", "package", package], directory / "package.txt")[:8000]
        command(adb + ["logcat", "-c"])
        command(adb + ["shell", "am", "start", "-W", "-n", package + "/io.github.rubixhacker.dyn4k.runtime.RuntimeActivity"], directory / "launch.txt")
        result["process"] = command(adb + ["shell", "pidof", package], directory / "process.txt").strip()
        if not result["process"]:
            raise ValueError("installed app process absent")
        instrumentation = command(adb + ["shell", "pm", "list", "instrumentation"], directory / "instrumentations.txt")
        runners = [line.split(" ")[0].removeprefix("instrumentation:") for line in instrumentation.splitlines()
                   if "(target=" + package + ")" in line]
        if len(runners) != 1:
            raise ValueError(f"instrumentation runner mismatch: {runners}")
        instrument = subprocess.run(adb + ["shell", "am", "instrument", "-w", "-r", runners[0]],
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        raw = instrument.stdout
        (directory / "instrumentation.txt").write_text(raw)
        result["instrumentation_exit_code"] = instrument.returncode
        parsed = parse_instrumentation(raw)
        result["cases"] = parsed
        expected_instrumentation = set(CONSUMER_CASES)
        if flavor == "candidate":
            expected_instrumentation.add("io.github.rubixhacker.dyn4k.runtime.StagedKotlinConsumerTest#sharedMutableIdentity")
            expected_instrumentation.update(portable)
        validate_lane(parsed, set(), expected_instrumentation, instrument.returncode)
        verify_consumer_sources(root, prepared)
        if sha256(prepared_path) != prepared_checksum:
            raise ValueError("prepared manifest changed during installed run")
        result["status"] = "DIAGNOSTIC_PASSED"
    except (RuntimeError, ValueError) as failure:
        result["error"] = str(failure)
    finally:
        command(adb + ["logcat", "-d"], directory / "logcat.txt", check=False)
        (directory / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-type", choices=("debug", "release"), required=True)
    parser.add_argument("--expected-api", choices=("21", "36", "37"), default="36")
    parser.add_argument("--expected-abi", choices=("x86_64", "x86", "arm64-v8a", "armeabi-v7a"), default="x86_64")
    args = parser.parse_args()
    root = args.repo.resolve()
    prepared_bytes = args.prepared.read_bytes()
    prepared = json.loads(prepared_bytes)
    prepared_checksum = hashlib.sha256(prepared_bytes).hexdigest()
    commit = command(["git", "-C", str(root), "rev-parse", "HEAD"]).strip()
    if commit != prepared["candidate_commit"]:
        raise ValueError("candidate commit differs from prepared artifacts")
    if command(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"]).strip():
        raise ValueError("candidate source checkout is dirty")
    for artifact in prepared["staged"].values():
        if sha256(Path(artifact["path"])) != artifact["sha256"]:
            raise ValueError("staged AAR checksum changed")
    for source, digest in prepared["consumer_sources"].items():
        if sha256(root / source) != digest:
            raise ValueError(f"consumer source changed: {source}")
    verify_consumer_sources(root, prepared)
    for item in (prepared["baseline_jar"], prepared["portable_jar"]):
        if sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"input checksum changed: {item['path']}")
    portable = expected_portable(root, set(prepared["portable_classes"]))
    sdk = Path(os.environ.get("ANDROID_HOME", "/var/home/stewart/Android/Sdk"))
    adb = [str(sdk / "platform-tools/adb"), "-P", "5038", "-s", "emulator-5558"]
    identity = {name: command(adb + ["shell", "getprop", name]).strip() for name in
                ("ro.build.fingerprint", "ro.build.version.sdk", "ro.product.cpu.abi",
                 "ro.product.cpu.abilist", "ro.product.model")}
    if identity["ro.build.version.sdk"] != args.expected_api or identity["ro.product.cpu.abi"] != args.expected_abi:
        raise ValueError(f"unexpected diagnostic emulator: {identity}")
    evidence_root = args.output.resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)
    lanes = [run_lane(root, prepared, portable, flavor, args.build_type, evidence_root, adb,
                      args.prepared, prepared_checksum)
             for flavor in ("baseline", "candidate")]
    tree = command(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"]).strip()
    summary = {"candidate_commit": commit, "source_tree": tree, "runtime": identity, "portable_expected": len(portable),
               "prepared_manifest": {"path": str(args.prepared), "sha256": prepared_checksum},
               "staged": prepared["staged"], "baseline_jar": prepared["baseline_jar"],
               "consumer_sources": prepared["consumer_sources"],
               "generated_consumer_sources": prepared["generated_consumer_sources"], "lanes": lanes}
    (evidence_root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"runtime": identity, "lanes": [{"flavor": lane["flavor"], "status": lane["status"],
          "error": lane.get("error"), "counts": lane.get("cases", {})} for lane in lanes]}, sort_keys=True))
    if any(lane["status"] != "DIAGNOSTIC_PASSED" for lane in lanes):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
