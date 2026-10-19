#!/usr/bin/env python3
import argparse
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

import qualify
import stage


NATIVE_TARGETS = {
    "macosArm64": ("Darwin", "arm64", None),
    "iosSimulatorArm64": ("Darwin", "arm64", "iOS"),
    "tvosSimulatorArm64": ("Darwin", "arm64", "tvOS"),
    "watchosSimulatorArm64": ("Darwin", "arm64", "watchOS"),
    "iosX64": ("Darwin", "x86_64", "iOS"),
    "mingwX64": ("Windows", "AMD64", None),
}
TARGETS = (*NATIVE_TARGETS, "jsSafari")


def runtime_status(target, observed):
    if target not in TARGETS or not isinstance(observed, dict):
        return "FAILED", "unknown target or invalid runtime observation"
    system, machine, simulator = NATIVE_TARGETS.get(
        target, ("Darwin", "arm64", None))
    if observed.get("system") != system or observed.get("machine", "").lower() != machine.lower():
        return "FAILED", "runner OS or architecture differs from selected target"
    version = str(observed.get("os_version", ""))
    if system == "Darwin":
        if not version.startswith("26."):
            return "FAILED", "macOS 26 runner identity is missing"
        if observed.get("xcode_version") != "26.5":
            return "FAILED", "selected Xcode differs from pinned 26.5"
        build = observed.get("xcode_build")
        if not isinstance(build, str) or re.fullmatch(r"Build version [0-9A-Za-z]+", build) is None:
            return "FAILED", "selected Xcode build observation is missing or malformed"
    elif not version.startswith("10.0.26100"):
        return "FAILED", "Windows Server 2025 build 26100 identity is missing"
    if simulator and not observed.get("simulators", {}).get(simulator):
        return "UNAVAILABLE", f"no available {simulator} simulator on selected runner"
    if target == "jsSafari":
        safari = str(observed.get("safari_version", ""))
        driver = str(observed.get("safaridriver_version", ""))
        if not safari or not driver:
            return "UNAVAILABLE", "Safari or SafariDriver is absent"
        if safari not in driver:
            return "FAILED", "SafariDriver version differs from installed Safari"
    return "READY", "selected runtime is available"


def run_capture(command):
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result


def read_command(command):
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def tool_version(command, pattern):
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        return ""
    match = re.search(pattern, result.stdout + "\n" + result.stderr)
    return match.group(1) if match else ""


def discover_runtime(target):
    system = platform.system()
    observed = {"system": system, "machine": platform.machine(),
                "os_version": read_command(["sw_vers", "-productVersion"])
                if system == "Darwin" else platform.version(),
                "runner_image_os": os.environ.get("ImageOS", ""),
                "runner_image_version": os.environ.get("ImageVersion", ""),
                "java_version": tool_version(["java", "-version"], r'version "([^"]+)"')}
    if observed["system"] == "Darwin":
        xcode = read_command(["xcodebuild", "-version"])
        match = re.fullmatch(r"Xcode ([0-9]+(?:\.[0-9]+)*)\nBuild version [0-9A-Za-z]+", xcode)
        observed["xcode_version"] = match.group(1) if match else ""
        observed["xcode_build"] = xcode.splitlines()[-1] if xcode else ""
        observed["simulators"] = {}
        if target in NATIVE_TARGETS and NATIVE_TARGETS[target][2]:
            raw = read_command(["xcrun", "simctl", "list", "-j", "devices", "available"])
            if raw:
                devices = json.loads(raw).get("devices", {})
                for runtime, entries in devices.items():
                    for family in ("iOS", "tvOS", "watchOS"):
                        if f".{family}-" in runtime:
                            observed["simulators"].setdefault(family, []).extend(
                                {"name": device.get("name"), "udid": device.get("udid"),
                                 "runtime": runtime} for device in entries
                                if device.get("isAvailable", True))
        if target == "jsSafari":
            observed["safari_version"] = read_command(
                ["defaults", "read", "/Applications/Safari.app/Contents/Info", "CFBundleShortVersionString"])
            observed["safaridriver_version"] = read_command(["safaridriver", "--version"])
    return observed


def target_hashes(staging, target):
    hashes = {}
    for module in qualify.MODULES:
        path = staging / qualify.target_binary_path(module, target)
        sidecar = path.with_name(path.name + ".sha256")
        if not path.is_file() or not sidecar.is_file():
            raise ValueError(f"{module} target binary or checksum is missing")
        actual = qualify.digest(path)
        if sidecar.read_text().strip().lower() != actual:
            raise ValueError(f"{module} target binary checksum differs from staged file")
        hashes[module] = actual
    return hashes


def hosted_status(target, candidate_sha, runtime, source_probe, consumer_probe, hashes, manifest):
    status, reason = runtime_status(target, runtime)
    if status != "READY":
        return status, reason
    if not isinstance(hashes, dict) or set(hashes) != set(qualify.MODULES) or any(
            not qualify.SHA64.fullmatch(str(value)) for value in hashes.values()):
        return "PROBE_FAILED", "both staged target binary hashes are required"
    groups = {group["id"]: group for group in manifest["groups"]}
    consumer_id = f"consumer-{target}"
    required = [(consumer_probe, len(qualify.expected_probe_cases(
        manifest, groups[consumer_id])), "staged consumer", (consumer_id,))]
    if target != "jsSafari":
        source_ids = (f"core-{target}", target)
        count = sum(len(qualify.expected_probe_cases(manifest, groups[group_id]))
                    for group_id in source_ids)
        required.insert(0, (source_probe, count, "source probe", source_ids))
    for probe, expected, name, group_ids in required:
        if not isinstance(probe, dict):
            return "PROBE_FAILED", f"{name} report is missing"
        if (probe.get("candidate_sha") != candidate_sha
                or probe.get("status") != "PROBE_PASSED"
                or probe.get("expected") != expected or probe.get("executed") != expected
                or probe.get("failures") != 0 or probe.get("errors") != 0
                or probe.get("skipped") != 0
                or type(probe.get("reported")) is not int
                or probe.get("reported") < expected
                or probe.get("exit_code") != 0):
            return "PROBE_FAILED", f"{name} is stale, partial, failed, or skipped"
        try:
            qualify.validate_probe_accounting(probe, manifest, group_ids)
        except ValueError as error:
            return "PROBE_FAILED", f"{name} accounting is invalid: {error}"
    return "PROBE_PASSED", "frozen source and staged consumer cases executed"


def gradle_wrapper(repository):
    return str(repository / ("gradlew.bat" if os.name == "nt" else "gradlew"))


def selected_groups(manifest, ids):
    groups = [group for group in manifest["groups"] if group["id"] in ids]
    if len(groups) != len(ids):
        raise ValueError("frozen hosted probe group is missing")
    return {**manifest, "groups": groups}, [group["report_pattern"] for group in groups]


def run_hosted(target, candidate_sha, output):
    repository = Path(__file__).resolve().parents[2]
    staging = repository / "build/staging-repository"
    result = {"candidate_sha": candidate_sha, "target": target, "status": "NOT_RUN",
              "runtime": {}, "source_probe": None, "consumer_probe": None,
              "artifact_hashes": {}, "reason": "probe not started"}
    try:
        qualify.require_clean_checkout(repository, candidate_sha)
        if target not in TARGETS:
            raise ValueError("unknown hosted target")
        runtime = discover_runtime(target)
        result["runtime"] = runtime
        runtime_state, reason = runtime_status(target, runtime)
        if runtime_state != "READY":
            result.update(status=runtime_state, reason=reason)
            return result
        artifact_target = "js" if target == "jsSafari" else target
        wrapper = gradle_wrapper(repository)
        result["runtime"]["gradle_version"] = tool_version([wrapper, "--version"], r"Gradle ([0-9.]+)")
        build = (repository / "build.gradle.kts").read_text()
        kgp = re.search(r'kotlin\("multiplatform"\) version "([^"]+)"', build)
        result["runtime"]["kgp_declared_version"] = kgp.group(1) if kgp else ""
        stage_dir = staging / ".qualification" / target
        receipt_path = stage_dir / "receipt.json"
        console_path = stage_dir / "stage.log"
        receipt = stage.run_stage(repository, candidate_sha, (artifact_target,),
                                  receipt_path, console_path)
        result["stage_command"] = receipt["command"]
        result["stage_receipt_sha256"] = qualify.digest(receipt_path)
        if receipt["status"] != "PASSED":
            result.update(status="PROBE_FAILED", reason=receipt.get("reason", "staging failed"))
            return result
        audit = qualify.audit_staging(staging, candidate_sha, (artifact_target,),
                                      repository / "LICENSE.md", receipt_path, console_path)
        audit_path = stage_dir / "audit.json"
        audit_path.write_text(json.dumps(audit, indent=2) + "\n")
        result["stage_audit_sha256"] = qualify.digest(audit_path)
        if audit["status"] != "PASSED":
            result.update(status="PROBE_FAILED", reason="staged publication audit failed: " + "; ".join(audit["errors"]))
            return result
        result["artifact_hashes"] = target_hashes(staging, artifact_target)
        manifest = qualify.load_json_strict(repository / "tools/qualification/foundation-probes.json")
        if target != "jsSafari":
            source_manifest, source_reports = selected_groups(manifest, (f"core-{target}", target))
            source_command = [wrapper, "--no-daemon", "--console=plain",
                              f":dyn4k-core:{target}Test", f":dyn4k:{target}Test"]
            result["source_probe"] = qualify.run_probe(
                source_command, source_reports, candidate_sha,
                output.with_name(output.stem + "-source.json"), source_manifest)
        consumer_manifest, consumer_reports = selected_groups(manifest, (f"consumer-{target}",))
        consumer_command = [wrapper, "-p", str(repository / "consumers/qualification/portable"),
                            "--no-daemon", "--console=plain",
                            "jsBrowserTest" if target == "jsSafari" else f"{target}Test",
                            f"-PqualificationRepository={staging}"]
        if target == "jsSafari":
            consumer_command.append("-PqualificationSafari=true")
        result["consumer_probe"] = qualify.run_probe(
            consumer_command, consumer_reports, candidate_sha,
            output.with_name(output.stem + "-consumer.json"), consumer_manifest)
        result["status"], result["reason"] = hosted_status(
            target, candidate_sha, runtime, result["source_probe"],
            result["consumer_probe"], result["artifact_hashes"], manifest)
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        result.update(status="PROBE_FAILED", reason=str(error))
    finally:
        output.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", choices=("run",))
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--target", required=True, choices=TARGETS)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run_hosted(args.target, args.candidate_sha, args.output)
    print(json.dumps(result))
    return 0 if result["status"] == "PROBE_PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
