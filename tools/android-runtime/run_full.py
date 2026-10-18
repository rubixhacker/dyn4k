#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from build_identity import (build_log_identity, current_java, validate_build_jdk,
                            verify_build_log_identity)
from android_corpus import (FINGERPRINTS, REFLECTIVE_FILTER_TYPES, load_suite,
                            verify_full_inputs, verify_xml_pins)
from full_evidence import validate_full_installed, validate_full_process_log, validate_full_r8
from prepare import verify_consumer_sources, verify_full_consumer_sources
from run import command, sha256, verify_installed_apk
from run_optimized import dex_evidence, snapshot_artifact


PROVIDER_GROUP = "io.github.rubixhacker"
PROVIDER_VERSION = "0.1.0-alpha.1"
GRAPH_COMPONENTS = {
    "project:full",
    *(f"{PROVIDER_GROUP}:{name}:{PROVIDER_VERSION}" for name in
      ("dyn4k-android", "dyn4k-core", "dyn4k-core-android")),
    "org.jetbrains.kotlin:kotlin-stdlib:2.4.20",
    "org.jetbrains:annotations:13.0",
    "org.jetbrains.kotlin:kotlin-test-junit:2.4.20",
    "org.jetbrains.kotlin:kotlin-test:2.4.20",
    "junit:junit:4.13.2",
    "org.hamcrest:hamcrest-core:1.3",
    "com.google.errorprone:error_prone_annotations:2.50.0",
}
GRAPH_EDGES = {
    "project:full io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1",
    "project:full io.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1",
    "project:full org.jetbrains.kotlin:kotlin-stdlib:2.4.20",
    "project:full org.jetbrains.kotlin:kotlin-test-junit:2.4.20",
    "project:full junit:junit:4.13.2",
    "project:full com.google.errorprone:error_prone_annotations:2.50.0",
    "io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1 io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1",
    "io.github.rubixhacker:dyn4k-android:0.1.0-alpha.1 org.jetbrains.kotlin:kotlin-stdlib:2.4.20",
    "io.github.rubixhacker:dyn4k-core:0.1.0-alpha.1 io.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1",
    "io.github.rubixhacker:dyn4k-core-android:0.1.0-alpha.1 org.jetbrains.kotlin:kotlin-stdlib:2.4.20",
    "org.jetbrains.kotlin:kotlin-stdlib:2.4.20 org.jetbrains:annotations:13.0",
    "org.jetbrains.kotlin:kotlin-test-junit:2.4.20 org.jetbrains.kotlin:kotlin-test:2.4.20",
    "org.jetbrains.kotlin:kotlin-test-junit:2.4.20 junit:junit:4.13.2",
    "org.jetbrains.kotlin:kotlin-test:2.4.20 org.jetbrains.kotlin:kotlin-stdlib:2.4.20",
    "junit:junit:4.13.2 org.hamcrest:hamcrest-core:1.3",
}
GRAPH_ARTIFACTS = GRAPH_COMPONENTS - {
    "project:full", f"{PROVIDER_GROUP}:dyn4k-core:{PROVIDER_VERSION}"}
API21_FINGERPRINTS = {
    "x86_64": "generic_x86_64/sdk_google_phone_x86_64/generic_x86_64:5.0.2/LSY66K/6695550:eng/test-keys",
    "x86": "generic_x86/sdk_google_phone_x86/generic_x86:5.0.2/LSY66K/6695550:eng/test-keys",
}


def validate_provider_artifacts(graph, prepared):
    sections = {}
    for variant in ("debug", "release"):
        components = re.findall(rf"(?m)^DYN4K_GRAPH_COMPONENT {variant} (\S+)$", graph)
        edges = re.findall(rf"(?m)^DYN4K_GRAPH_EDGE {variant} (\S+ \S+)$", graph)
        artifacts = re.findall(rf"(?m)^DYN4K_GRAPH_ARTIFACT {variant} (\S+) (\S+)$", graph)
        begin = f"DYN4K_GRAPH_BEGIN {variant}"
        end = f"DYN4K_GRAPH_END {variant} {len(components)} {len(edges)} {len(artifacts)}"
        if graph.count(begin) != 1 or graph.count(end) != 1 or \
                len(components) != len(set(components)) or set(components) != GRAPH_COMPONENTS or \
                len(edges) != len(set(edges)) or set(edges) != GRAPH_EDGES or \
                len(artifacts) != len(set(artifacts)) or \
                {coordinate for coordinate, _ in artifacts} != GRAPH_ARTIFACTS:
            raise ValueError(f"incomplete or wrong {variant} runtime dependency graph")
        providers = {}
        for coordinate, path_text in artifacts:
            group, artifact, version = coordinate.split(":")
            if group == "org.dyn4j" or artifact == "dyn4j":
                raise ValueError("second baseline provider in runtime graph")
            if group == PROVIDER_GROUP:
                if coordinate != f"{PROVIDER_GROUP}:{artifact}:{PROVIDER_VERSION}" or \
                        artifact not in prepared["staged"]:
                    raise ValueError("wrong staged provider coordinates")
                path = Path(path_text)
                if path.suffix != ".aar" or sha256(path) != prepared["staged"][artifact]["sha256"]:
                    raise ValueError(f"wrong resolved staged AAR: {artifact}")
                providers[artifact] = {"coordinate": coordinate, "path": str(path),
                                       "sha256": sha256(path)}
        if set(providers) != set(prepared["staged"]):
            raise ValueError("wrong staged AAR provider set")
        sections[variant] = {"components": len(components), "edges": len(edges),
                             "artifacts": len(artifacts), "providers": providers}
    if sections["debug"]["providers"] != sections["release"]["providers"]:
        raise ValueError("debug and release provider bytes differ")
    return sections


def verify_candidate(root, prepared):
    if prepared.get("build_jdk") != current_java():
        raise ValueError("prepared JDK identity differs")
    verify_build_log_identity(prepared["root_build"])
    commit = command(["git", "-C", str(root), "rev-parse", "HEAD"]).strip()
    if prepared.get("candidate_commit") != commit or command(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"]).strip():
        raise ValueError("full optimized source is dirty or differs from prepared candidate")
    suite, _ = load_suite(root)
    jvm_xml = verify_xml_pins(root, prepared)
    verify_full_inputs(root, suite, prepared["full_inputs"])
    verify_consumer_sources(root, prepared)
    verify_full_consumer_sources(root, prepared)
    for artifact in (*prepared["staged"].values(), *prepared["staged_roots"].values(),
                     prepared["baseline_jar"], prepared["portable_jar"]):
        if sha256(Path(artifact["path"])) != artifact["sha256"]:
            raise ValueError(f"prepared input changed: {artifact['path']}")
    return commit, suite, jvm_xml


def apk_path(app, build_type, test=False):
    directory = app / "build/outputs/apk" / (f"androidTest/{build_type}" if test else build_type)
    found = list(directory.glob("*.apk"))
    if len(found) != 1:
        raise ValueError(f"full app APK missing or ambiguous: {directory}")
    return found[0]


def validate_runtime(identity, expected_api, expected_abi, boot_completed):
    fingerprint = (API21_FINGERPRINTS.get(expected_abi) if expected_api == "21"
                   else FINGERPRINTS.get(expected_api))
    if identity.get("ro.build.version.sdk") != expected_api or \
            identity.get("ro.product.cpu.abi") != expected_abi or \
            not fingerprint or identity.get("ro.build.fingerprint") != fingerprint or \
            boot_completed != "1":
        raise ValueError(f"wrong installed runtime: {identity}")


def validate_api21_process_log(log, package, expected_abi, before_pid):
    escaped = re.escape(package)
    all_starts = list(re.finditer(
        rf"(?m)^[A-Z]/ActivityManager\(\s*\d+\): Start proc {escaped}(?=\s|$)[^\n]*$",
        log))
    activities = list(re.finditer(
        rf"(?m)^[A-Z]/ActivityManager\(\s*\d+\): Start proc {escaped} for activity "
        rf"{escaped}/\.FullActivity: [^\n]*$", log))
    starts = list(re.finditer(
        rf"(?m)^[A-Z]/ActivityManager\(\s*\d+\): Start proc {escaped} for added application "
        rf"{escaped}: [^\n]*$",
        log))
    finishes = list(re.finditer(
        rf"(?m)^I/ActivityManager\(\s*\d+\): Force stopping {escaped} "
        r"appid=(\d+) user=\d+: finished inst$", log))
    if len(all_starts) != 2 or len(activities) != 1 or len(starts) != 1 or \
            all_starts[0].start() != activities[0].start() or \
            all_starts[1].start() != starts[0].start() or len(finishes) != 1 or \
            not isinstance(before_pid, str) or not before_pid.isdigit() or \
            activities[0].start() >= starts[0].start() or \
            starts[0].start() >= finishes[0].start():
        raise ValueError("instrumentation process identity or normal shutdown missing")
    activity = re.fullmatch(
        rf"I/ActivityManager\(\s*\d+\): Start proc {escaped} for activity "
        rf"{escaped}/\.FullActivity: pid=(\d+) uid=(\d+) gids=\{{[\d, ]*\}} abi=(\S+)",
        activities[0].group().rstrip("\r"))
    if not activity or activity.group(1) != before_pid or activity.group(3) != expected_abi:
        raise ValueError("instrumentation process identity or normal shutdown missing")
    started = re.fullmatch(
        rf"I/ActivityManager\(\s*\d+\): Start proc {escaped} for added application "
        rf"{escaped}: pid=(\d+) uid=(\d+) gids=\{{[\d, ]*\}} abi=(\S+)",
        starts[0].group().rstrip("\r"))
    if not started or started.group(3) != expected_abi or \
            started.group(2) != activity.group(2) or \
            finishes[0].group(1) != started.group(2):
        raise ValueError("instrumentation process identity or normal shutdown missing")
    kill_line = (rf"(?m)^[A-Z]/ActivityManager\(\s*\d+\): Killing "
                 rf"[^\n]*:{escaped}/[^\n]*$")

    def killed_pid(section):
        lines = re.findall(kill_line, section)
        if len(lines) != 1:
            raise ValueError("instrumentation process identity or normal shutdown missing")
        killed = re.fullmatch(
            rf"I/ActivityManager\(\s*\d+\): Killing (\d+):{escaped}/\S+ "
            rf"\(adj \d+\): stop {escaped}", lines[0].rstrip("\r"))
        if not killed:
            raise ValueError("instrumentation process identity or normal shutdown missing")
        return killed.group(1)

    if killed_pid(log[activities[0].end():starts[0].start()]) != before_pid or \
            re.search(kill_line, log[starts[0].end():finishes[0].start()]) or \
            killed_pid(log[finishes[0].end():]) != started.group(1):
        raise ValueError("instrumentation process identity or normal shutdown missing")
    return started.group(1)


def api21_process_pid(process_list, package, required=True):
    lines = process_list.splitlines()
    if not lines or lines[0].split()[:2] != ["USER", "PID"] or \
            lines[0].split()[-1:] != ["NAME"]:
        raise ValueError("API 21 app process list is invalid")
    selected = [line.split() for line in lines[1:] if line.split() and line.split()[-1] == package]
    if len(selected) > 1 or (required and len(selected) != 1):
        raise ValueError("API 21 app process identity is missing or ambiguous")
    if not selected:
        return None
    if len(selected[0]) < 3 or not selected[0][1].isdigit() or int(selected[0][1]) <= 0:
        raise ValueError("API 21 app process PID is invalid")
    return selected[0][1]


def build_artifacts(app, provider_artifacts):
    paths = {f"{kind}-{build}-apk": apk_path(app, build, kind == "test")
             for build in ("debug", "release") for kind in ("app", "test")}
    paths.update({name: app / "build/outputs/mapping/release" / name
                  for name in ("configuration.txt", "mapping.txt", "usage.txt")})
    paths["provider-artifacts"] = provider_artifacts
    return paths


def seal_build(root, prepared_path, provider_artifacts, debug_build_log, release_build_log, output):
    prepared_bytes = prepared_path.read_bytes()
    prepared = json.loads(prepared_bytes)
    commit, _, _ = verify_candidate(root, prepared)
    validate_provider_artifacts(provider_artifacts.read_text(), prepared)
    provider_build = build_log_identity(provider_artifacts, require_marker=True)
    build_logs = {"debug": build_log_identity(debug_build_log),
                  "release": build_log_identity(release_build_log),
                  "provider": provider_build}
    paths = build_artifacts(root / "consumers/android-runtime/full", provider_artifacts)
    if any(path.stat().st_mtime_ns < prepared_path.stat().st_mtime_ns for path in paths.values()):
        raise ValueError("full build artifact predates prepared candidate")
    receipt = {"candidate_commit": commit,
               "prepared_sha256": hashlib.sha256(prepared_bytes).hexdigest(),
               "build_jdk": prepared["build_jdk"], "build_logs": build_logs,
               "artifacts": {name: {"path": str(path), "sha256": sha256(path)}
                             for name, path in paths.items()}}
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def verify_build_receipt(root, prepared_path, provider_artifacts, receipt_path):
    receipt = json.loads(receipt_path.read_text())
    prepared = json.loads(prepared_path.read_text())
    if receipt.get("build_jdk") != prepared.get("build_jdk") or \
            receipt.get("build_jdk") != current_java() or \
            set(receipt.get("build_logs", {})) != {"debug", "release", "provider"}:
        raise ValueError("full APK build JDK identity differs")
    for name, record in receipt["build_logs"].items():
        if name == "provider" and record.get("path") != str(provider_artifacts):
            raise ValueError("provider graph build log differs")
        verify_build_log_identity(record, require_marker=name == "provider")
    if receipt.get("candidate_commit") != command(["git", "-C", str(root), "rev-parse", "HEAD"]).strip() or \
            receipt.get("prepared_sha256") != sha256(prepared_path):
        raise ValueError("full APK build receipt is stale")
    paths = build_artifacts(root / "consumers/android-runtime/full", provider_artifacts)
    if set(receipt.get("artifacts", {})) != set(paths):
        raise ValueError("full APK build receipt artifact set differs")
    for name, path in paths.items():
        if receipt["artifacts"][name] != {"path": str(path), "sha256": sha256(path)}:
            raise ValueError(f"wrong APK or R8 build artifact: {name}")
    return receipt


def run(args):
    root = args.repo.resolve()
    prepared_bytes = args.prepared.read_bytes()
    prepared = json.loads(prepared_bytes)
    prepared_sha = hashlib.sha256(prepared_bytes).hexdigest()
    commit, suite, jvm_xml = verify_candidate(root, prepared)
    graph = args.provider_artifacts.read_text()
    provider = validate_provider_artifacts(graph, prepared)
    if args.provider_artifacts.stat().st_mtime_ns < args.prepared.stat().st_mtime_ns:
        raise ValueError("provider artifact receipt predates prepared candidate")
    verify_build_receipt(root, args.prepared, args.provider_artifacts, args.build_receipt)
    app = root / "consumers/android-runtime/full"
    apk = apk_path(app, args.build_type)
    test_apk = apk_path(app, args.build_type, True)
    if any(path.stat().st_mtime_ns < args.prepared.stat().st_mtime_ns for path in (apk, test_apk)):
        raise ValueError("full app APK predates prepared candidate")
    sdk = Path(os.environ.get("ANDROID_HOME", "/var/home/stewart/Android/Sdk"))
    adb = [str(sdk / "platform-tools/adb"), "-P", "5038", "-s", "emulator-5558"]
    identity = {key: command(adb + ["shell", "getprop", key]).strip() for key in
                ("ro.build.fingerprint", "ro.build.version.sdk", "ro.product.cpu.abi",
                 "ro.product.cpu.abilist", "ro.product.model")}
    validate_runtime(identity, args.expected_api, args.expected_abi,
                     command(adb + ["shell", "getprop", "sys.boot_completed"]).strip())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    app_copy = snapshot_artifact(apk, output / "app.apk", sha256(apk))
    test_copy = snapshot_artifact(test_apk, output / "instrumentation.apk", sha256(test_apk))
    graph_copy = snapshot_artifact(args.provider_artifacts, output / "provider-artifacts.txt",
                                   sha256(args.provider_artifacts))
    result = {"status": "FAILED", "candidate_commit": commit,
              "source_tree": command(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"]).strip(),
              "runtime": identity, "build_type": args.build_type,
              "prepared_manifest": {"path": str(args.prepared), "sha256": prepared_sha},
              "build_receipt": {"path": str(args.build_receipt), "sha256": sha256(args.build_receipt)},
              "build_jdk": prepared["build_jdk"],
              "build_logs": json.loads(args.build_receipt.read_text())["build_logs"],
              "suite_manifest": prepared["suite_manifest"], "jvm_xml": jvm_xml,
              "staged": prepared["staged"], "resolved_providers": provider,
              "staged_roots": prepared["staged_roots"],
              "provider_artifacts": graph_copy, "app_apk": app_copy, "test_apk": test_copy,
              "portable_jar": prepared["portable_jar"]}
    try:
        descriptors, dex_files = dex_evidence(Path(app_copy["path"]), output, sdk)
        result["dex"] = dex_files
        if args.build_type == "release":
            debug_apk = apk_path(app, "debug")
            debug_copy = snapshot_artifact(debug_apk, output / "debug-app.apk", sha256(debug_apk))
            (output / "debug-dex").mkdir(exist_ok=True)
            debug_descriptors, debug_dex_files = dex_evidence(Path(debug_copy["path"]),
                                                               output / "debug-dex", sdk)
            result["debug_app_apk"] = debug_copy
            result["debug_dex"] = debug_dex_files
            mapping_dir = app / "build/outputs/mapping/release"
            r8_files = {}
            for name in ("configuration.txt", "mapping.txt", "usage.txt"):
                source = mapping_dir / name
                r8_files[name] = snapshot_artifact(source, output / name, sha256(source))
            allowed = {case["classname"] for case in suite["cases"] if case["scope"] == "portable"}
            allowed.update(REFLECTIVE_FILTER_TYPES)
            result["r8"] = {"files": r8_files, "transformation": validate_full_r8(
                (output / "configuration.txt").read_text(), (output / "mapping.txt").read_text(),
                (output / "usage.txt").read_text(), debug_descriptors, descriptors,
                allowed_test_classes=allowed)}
        command(adb + ["install", "-r", app_copy["path"]], output / "install-app.txt")
        command(adb + ["install", "-r", test_copy["path"]], output / "install-test.txt")
        package = "io.github.rubixhacker.dyn4k.full"
        package_path = command(adb + ["shell", "pm", "path", package], output / "package-path.txt").strip()
        if not re.fullmatch(r"package:/data/app/[^\n]+/base\.apk", package_path):
            raise ValueError("installed full app package path is absent")
        remote_apk = package_path.removeprefix("package:")
        command(adb + ["pull", remote_apk, str(output / "installed-base.apk")], output / "pull-app.txt")
        result["installed_apk"] = verify_installed_apk(
            output / "installed-base.apk", app_copy["sha256"])
        result["package_path"] = package_path
        test_package_path = command(adb + ["shell", "pm", "path", package + ".test"],
                                    output / "test-package-path.txt").strip()
        if not re.fullmatch(r"package:/data/app/[^\n]+/base\.apk", test_package_path):
            raise ValueError("installed full instrumentation package path is absent")
        command(adb + ["pull", test_package_path.removeprefix("package:"),
                       str(output / "installed-instrumentation.apk")],
                output / "pull-instrumentation.txt")
        result["installed_test_apk"] = verify_installed_apk(
            output / "installed-instrumentation.apk", test_copy["sha256"])
        result["test_package_path"] = test_package_path
        command(adb + ["shell", "dumpsys", "package", package], output / "package.txt")
        command(adb + ["logcat", "-c"])
        command(adb + ["shell", "am", "start", "-W", "-n", package + "/.FullActivity"],
                output / "launch.txt")
        before_pid = (api21_process_pid(command(adb + ["shell", "ps"],
                                                output / "process-before.txt"), package)
                      if args.expected_api == "21" else
                      command(adb + ["shell", "pidof", package],
                              output / "process-before.txt").strip())
        if not before_pid:
            raise ValueError("full app process absent before instrumentation")
        runners = command(adb + ["shell", "pm", "list", "instrumentation"],
                          output / "instrumentations.txt")
        matches = [line.split(" ")[0].removeprefix("instrumentation:") for line in runners.splitlines()
                   if "(target=" + package + ")" in line]
        if len(matches) != 1:
            raise ValueError("full instrumentation runner mismatch")
        executed = subprocess.run(adb + ["shell", "am", "instrument", "-w", "-r", matches[0]],
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        raw_path = output / "instrumentation.txt"
        raw_path.write_text(executed.stdout)
        result["instrumentation"] = {"path": str(raw_path), "sha256": sha256(raw_path),
                                     "exit_code": executed.returncode, "runner": matches[0]}
        expected = set(jvm_xml["case_ids"])
        expected.update(f"external-java:{name}#main" for name in
                        ("GeometryConsumer", "DetectionConsumer", "CollisionModelConsumer",
                         "DynamicsConsumer", "WorldConsumer", "JointConsumer", "ContactConsumer"))
        expected.add("external-kotlin:io.github.rubixhacker.dyn4k.full.FullKotlinJourney#run")
        result["cases"] = validate_full_installed(executed.stdout, expected, executed.returncode)
        log = command(adb + ["logcat", "-d"], output / "logcat.txt")
        instrumentation_pid = (validate_api21_process_log(log, package, args.expected_abi, before_pid)
                               if args.expected_api == "21" else
                               validate_full_process_log(log, package))
        after_pid = (api21_process_pid(command(adb + ["shell", "ps"],
                                               output / "process-after.txt"), package, required=False)
                     if args.expected_api == "21" else
                     command(adb + ["shell", "pidof", package],
                             output / "process-after.txt", check=False).strip())
        if args.expected_api == "21" and after_pid is not None:
            raise ValueError("API 21 app process remains after instrumentation shutdown")
        result["process"] = {"before": before_pid, "instrumentation": instrumentation_pid,
                             "after": after_pid or None}
        verify_candidate(root, prepared)
        if sha256(args.prepared) != prepared_sha or sha256(args.provider_artifacts) != graph_copy["sha256"]:
            raise ValueError("full optimized input changed during installed run")
        verify_build_receipt(root, args.prepared, args.provider_artifacts, args.build_receipt)
        result["status"] = "PASSED"
    except (RuntimeError, ValueError, OSError) as failure:
        result["error"] = str(failure)
    finally:
        command(adb + ["logcat", "-d"], output / "logcat.txt", check=False)
        (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--provider-artifacts", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path)
    parser.add_argument("--debug-build-log", type=Path)
    parser.add_argument("--release-build-log", type=Path)
    parser.add_argument("--seal-build", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-type", choices=("debug", "release"))
    parser.add_argument("--expected-api", choices=("21", "36", "37"))
    parser.add_argument("--expected-abi", choices=("x86_64", "x86", "arm64-v8a", "armeabi-v7a"),
                        default="x86_64")
    args = parser.parse_args()
    if args.seal_build:
        if not args.debug_build_log or not args.release_build_log:
            parser.error("--seal-build requires both build logs")
        receipt = seal_build(args.repo.resolve(), args.prepared, args.provider_artifacts,
                             args.debug_build_log, args.release_build_log, args.output)
        print(json.dumps({"candidate_commit": receipt["candidate_commit"],
                          "artifacts": len(receipt["artifacts"])}, sort_keys=True))
        return
    if not args.build_type or not args.expected_api or not args.build_receipt:
        parser.error("installed run requires --build-type, --expected-api, and --build-receipt")
    result = run(args)
    print(json.dumps({"status": result["status"], "error": result.get("error"),
                      "cases": len(result.get("cases", {}).get("portable", {}).get("cases", {}))},
                     sort_keys=True))
    if result["status"] != "PASSED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
