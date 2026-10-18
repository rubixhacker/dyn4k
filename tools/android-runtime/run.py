#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from build_identity import current_java, verify_build_log_identity
from android_corpus import FINGERPRINTS, verify_xml_pins
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


def instrumentation_classes(prepared, flavor):
    selected = {"io.github.rubixhacker.dyn4k.runtime.ConsumerJourneyTest"}
    if flavor == "candidate":
        selected.add("io.github.rubixhacker.dyn4k.runtime.StagedKotlinConsumerTest")
        selected.update(prepared["portable_classes"])
    return tuple(sorted(selected))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_installed_apk(path, expected_sha256):
    observed = sha256(path)
    if observed != expected_sha256:
        raise ValueError("installed APK differs from built APK")
    return {"path": str(path), "sha256": observed}


def command(args, output=None, check=True):
    run = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(run.stdout)
    if check and run.returncode:
        raise RuntimeError(f"command failed ({run.returncode}): {' '.join(args)}: {run.stdout[-1200:]}")
    return run.stdout


def expected_portable(root, prepared):
    return set(verify_xml_pins(root, prepared)["case_ids"])


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
    app_copy = directory / "app.apk"
    test_copy = directory / "instrumentation.apk"
    shutil.copyfile(apk, app_copy)
    shutil.copyfile(test_apk, test_copy)
    result = {"flavor": flavor, "build_type": build_type, "package": package,
              "app_apk": {"path": str(app_copy), "sha256": sha256(app_copy)},
              "test_apk": {"path": str(test_copy), "sha256": sha256(test_copy)},
              "candidate_commit": prepared["candidate_commit"],
              "build_jdk": prepared["build_jdk"], "root_build": prepared["root_build"],
              "prepared_manifest": {"path": str(prepared_path), "sha256": prepared_checksum},
              "staged": prepared["staged"], "baseline_jar": prepared["baseline_jar"],
              "staged_roots": prepared["staged_roots"],
              "consumer_sources": prepared["consumer_sources"],
              "generated_consumer_sources": prepared["generated_consumer_sources"],
              "portable_jar": prepared["portable_jar"], "status": "FAILED"}
    try:
        verify_consumer_sources(root, prepared)
        if apk.stat().st_mtime_ns < prepared_path.stat().st_mtime_ns or test_apk.stat().st_mtime_ns < prepared_path.stat().st_mtime_ns:
            raise ValueError("APK predates prepared candidate inputs")
        if sha256(apk) != result["app_apk"]["sha256"] or \
                sha256(test_apk) != result["test_apk"]["sha256"]:
            raise ValueError("built APK changed during diagnostic snapshot")
        if build_type == "release":
            mapping = app / f"build/outputs/mapping/{flavor}Release/mapping.txt"
            if not mapping.is_file() or not mapping.stat().st_size:
                raise ValueError("R8 mapping missing")
            result["r8_mapping"] = {"path": str(mapping), "sha256": sha256(mapping)}
        command(adb + ["install", "-r", str(app_copy)], directory / "install-app.txt")
        command(adb + ["install", "-r", str(test_copy)], directory / "install-test.txt")
        result["package_path"] = command(adb + ["shell", "pm", "path", package], directory / "package-path.txt").strip()
        if not re.fullmatch(r"package:/data/app/[^\n]+/base\.apk", result["package_path"]):
            raise ValueError("installed package path absent")
        command(adb + ["pull", result["package_path"].removeprefix("package:"),
                       str(directory / "installed-base.apk")], directory / "pull-app.txt")
        result["installed_apk"] = verify_installed_apk(
            directory / "installed-base.apk", result["app_apk"]["sha256"])
        result["test_package_path"] = command(
            adb + ["shell", "pm", "path", package + ".test"],
            directory / "test-package-path.txt").strip()
        if not re.fullmatch(r"package:/data/app/[^\n]+/base\.apk", result["test_package_path"]):
            raise ValueError("installed instrumentation package path absent")
        command(adb + ["pull", result["test_package_path"].removeprefix("package:"),
                       str(directory / "installed-instrumentation.apk")],
                directory / "pull-instrumentation.txt")
        result["installed_test_apk"] = verify_installed_apk(
            directory / "installed-instrumentation.apk", result["test_apk"]["sha256"])
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
        classes = instrumentation_classes(prepared, flavor)
        result["selected_classes"] = classes
        instrument = subprocess.run(adb + ["shell", "am", "instrument", "-w", "-r",
                                       "-e", "class", ",".join(classes), runners[0]],
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        raw = instrument.stdout
        (directory / "instrumentation.txt").write_text(raw)
        result["instrumentation_exit_code"] = instrument.returncode
        parsed = parse_instrumentation(raw)
        result["cases"] = parsed
        expected_instrumentation = set(CONSUMER_CASES)
        if flavor == "candidate":
            expected_instrumentation.add("io.github.rubixhacker.dyn4k.runtime.StagedKotlinConsumerTest#sharedMutableIdentity")
            expected_instrumentation.update(case.split(":", 1)[1] for case in portable)
        validate_lane(parsed, set(), expected_instrumentation, instrument.returncode)
        if flavor == "candidate":
            result["portable_case_ids"] = sorted(portable)
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
    if prepared.get("build_jdk") != current_java():
        raise ValueError("diagnostic build JDK identity differs")
    verify_build_log_identity(prepared["root_build"])
    if command(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"]).strip():
        raise ValueError("candidate source checkout is dirty")
    for artifact in (*prepared["staged"].values(), *prepared["staged_roots"].values()):
        if sha256(Path(artifact["path"])) != artifact["sha256"]:
            raise ValueError("staged AAR checksum changed")
    for source, digest in prepared["consumer_sources"].items():
        if sha256(root / source) != digest:
            raise ValueError(f"consumer source changed: {source}")
    verify_consumer_sources(root, prepared)
    for item in (prepared["baseline_jar"], prepared["portable_jar"]):
        if sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"input checksum changed: {item['path']}")
    portable = expected_portable(root, prepared)
    sdk = Path(os.environ.get("ANDROID_HOME", "/var/home/stewart/Android/Sdk"))
    adb = [str(sdk / "platform-tools/adb"), "-P", "5038", "-s", "emulator-5558"]
    identity = {name: command(adb + ["shell", "getprop", name]).strip() for name in
                ("ro.build.fingerprint", "ro.build.version.sdk", "ro.product.cpu.abi",
                 "ro.product.cpu.abilist", "ro.product.model")}
    if identity["ro.build.version.sdk"] != args.expected_api or identity["ro.product.cpu.abi"] != args.expected_abi:
        raise ValueError(f"unexpected diagnostic emulator: {identity}")
    if args.expected_api in FINGERPRINTS and identity["ro.build.fingerprint"] != FINGERPRINTS[args.expected_api]:
        raise ValueError(f"unexpected Android image fingerprint: {identity}")
    evidence_root = args.output.resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)
    lanes = [run_lane(root, prepared, portable, flavor, args.build_type, evidence_root, adb,
                      args.prepared, prepared_checksum)
             for flavor in ("baseline", "candidate")]
    tree = command(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"]).strip()
    summary = {"candidate_commit": commit, "source_tree": tree, "runtime": identity, "portable_expected": len(portable),
               "build_jdk": prepared["build_jdk"], "root_build": prepared["root_build"],
               "prepared_manifest": {"path": str(args.prepared), "sha256": prepared_checksum},
               "staged": prepared["staged"], "baseline_jar": prepared["baseline_jar"],
               "staged_roots": prepared["staged_roots"],
               "consumer_sources": prepared["consumer_sources"],
               "generated_consumer_sources": prepared["generated_consumer_sources"], "lanes": lanes}
    (evidence_root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"runtime": identity, "lanes": [{"flavor": lane["flavor"], "status": lane["status"],
          "error": lane.get("error"), "counts": lane.get("cases", {})} for lane in lanes]}, sort_keys=True))
    if any(lane["status"] != "DIAGNOSTIC_PASSED" for lane in lanes):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
