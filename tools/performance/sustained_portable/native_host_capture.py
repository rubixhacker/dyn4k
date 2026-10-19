import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import capture


def selected_artifact(inventory, module, target):
    return capture.native_artifacts(inventory, target)[module]["path"]


def selected_xcodebuild_path(developer_dir, find_output):
    developer = Path(developer_dir)
    expected = str(developer / "usr/bin/xcodebuild")
    if (not developer.is_absolute() or developer.parts[-2:] != ("Contents", "Developer")
            or ".." in developer.parts
            or find_output not in (expected + "\n", expected + "\r\n")):
        raise ValueError("Apple toolchain selected DEVELOPER_DIR binding is invalid")
    return expected


def validate_apple_toolchain_receipt(receipt):
    if not isinstance(receipt, dict) or set(receipt) != {
            "format", "source_sha", "producer_tree", "inventory_sha256",
            "developer_dir", "xcodebuild_path", "xcrun_find_argv", "xcrun_find_output",
            "xcode_version_argv", "xcode_version"}:
        raise ValueError("Apple toolchain receipt is missing or malformed")
    if receipt["format"] != "portable-apple-toolchain-v1" \
            or not re.fullmatch(r"[0-9a-f]{40}", receipt["source_sha"]) \
            or not re.fullmatch(r"[0-9a-f]{40}", receipt["producer_tree"]) \
            or not re.fullmatch(r"[0-9a-f]{64}", receipt["inventory_sha256"]):
        raise ValueError("Apple toolchain source binding is invalid")
    selected_path = selected_xcodebuild_path(receipt["developer_dir"], receipt["xcrun_find_output"])
    if (receipt["xcodebuild_path"] != selected_path
            or receipt["xcrun_find_argv"] != ["xcrun", "--find", "xcodebuild"]
            or receipt["xcode_version_argv"] != [selected_path, "-version"]):
        raise ValueError("Apple toolchain selected DEVELOPER_DIR binding is invalid")
    lines = receipt["xcode_version"].splitlines()
    if (len(lines) != 2 or lines[0] != "Xcode 26.5"
            or re.fullmatch(r"Build version [0-9A-Za-z]+", lines[1]) is None):
        raise ValueError("selected Xcode differs from pinned 26.5 or has invalid build")
    return receipt


def observe_apple_toolchain(source_sha, producer_tree, inventory_sha256):
    selected = os.environ.get("DEVELOPER_DIR", "")
    if not selected or not Path(selected).is_absolute() or not Path(selected).is_dir():
        raise ValueError("set DEVELOPER_DIR to the installed Xcode Developer directory")
    developer = str(Path(selected).resolve())
    find_argv = ["xcrun", "--find", "xcodebuild"]
    def observe(argv):
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise ValueError(f"Apple toolchain observation failed: {argv}: {result.stderr.strip()}")
        return result.stdout
    find_output = observe(find_argv)
    selected_path = selected_xcodebuild_path(developer, find_output)
    version_argv = [selected_path, "-version"]
    version_output = observe(version_argv)
    receipt = {"format": "portable-apple-toolchain-v1", "source_sha": source_sha,
               "producer_tree": producer_tree, "inventory_sha256": inventory_sha256,
               "developer_dir": developer, "xcodebuild_path": selected_path,
               "xcrun_find_argv": find_argv, "xcrun_find_output": find_output,
               "xcode_version_argv": version_argv, "xcode_version": version_output}
    return validate_apple_toolchain_receipt(receipt)


def verify_apple_toolchain_archive(archive):
    sidecar = archive / "apple-toolchain.json"
    if not sidecar.is_file():
        raise ValueError("archived Apple toolchain sidecar is missing")
    receipt = validate_apple_toolchain_receipt(json.loads(sidecar.read_text()))
    inventory_path = archive / "build-inventory.json"
    inventory = json.loads(inventory_path.read_text())
    record = json.loads((archive / "capture.json").read_text())
    if (record.get("target") != "macosArm64"
            or record.get("source_sha") != receipt["source_sha"]
            or record.get("producer_tree") != receipt["producer_tree"]
            or inventory.get("source_sha") != receipt["source_sha"]
            or inventory.get("producer_tree") != receipt["producer_tree"]
            or capture.digest(inventory_path) != receipt["inventory_sha256"]
            or record.get("build_inventory_sha256") != receipt["inventory_sha256"]
            or record.get("apple_toolchain") != {"receipt_sha256": capture.digest(sidecar),
                                                  "developer_dir": receipt["developer_dir"],
                                                  "xcode_version": receipt["xcode_version"]}):
        raise ValueError("archived Apple toolchain differs from source-bound capture")
    return receipt


def main():
    if sys.argv[1:2] == ["verify"]:
        verify_parser = argparse.ArgumentParser(description="Replay archived macOS Xcode observation")
        verify_parser.add_argument("verify")
        verify_parser.add_argument("--archive", type=Path, required=True)
        verify_args = verify_parser.parse_args()
        try:
            verify_apple_toolchain_archive(verify_args.archive)
        except (OSError, ValueError, KeyError, TypeError) as error:
            verify_parser.exit(1, f"qualification: unpassed; {error}\n")
        print(json.dumps({"apple_toolchain": "verified", "archive": str(verify_args.archive)}))
        return
    parser = argparse.ArgumentParser(description="Capture one Native host producer run")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--publication-root", type=Path, required=True)
    parser.add_argument("--source-link-receipt", type=Path)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--target", choices=sorted(capture.NATIVE_HOST_TARGETS), required=True)
    parser.add_argument("--build", choices=("development", "optimized"), required=True)
    parser.add_argument("--mode", choices=("timing", "memory"), default="timing")
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--warmup", type=int, required=True)
    parser.add_argument("--host-timeout-seconds", type=float, default=45.0)
    args = parser.parse_args()
    try:
        inventory_path = capture.required_file(str(args.inventory), "build inventory")
        inventory = json.loads(inventory_path.read_text())
        if inventory.get("target") != args.target or inventory.get("build") != args.build:
            raise ValueError("selected Native inventory target or build differs")
        harness = inventory["harness"]
        command = [sys.executable, str(Path(capture.__file__).resolve()),
                   "--archive", str(args.archive), "--inventory", str(inventory_path),
                   "--publication-root", str(args.publication_root),
                   "--scenario", args.scenario, "--target", args.target,
                   "--build", args.build, "--source-sha", inventory["source_sha"],
                   "--mode", args.mode,
                   "--runtime", harness, "--harness", harness,
                   "--core", selected_artifact(inventory, "dyn4k-core", args.target),
                   "--kotlin", selected_artifact(inventory, "dyn4k", args.target),
                   "--steps", str(args.steps), "--warmup", str(args.warmup),
                   "--host-timeout-seconds", str(args.host_timeout_seconds)]
        if args.source_link_receipt is not None:
            command += ["--source-link-receipt", str(args.source_link_receipt)]
        if args.target == "macosArm64":
            receipt = observe_apple_toolchain(inventory["source_sha"],
                                              inventory["producer_tree"], capture.digest(inventory_path))
            with tempfile.TemporaryDirectory() as temporary:
                sidecar = Path(temporary) / "apple-toolchain.json"
                sidecar.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
                returncode = subprocess.call(command + ["--apple-toolchain-receipt", str(sidecar)])
            raise SystemExit(returncode)
        raise SystemExit(subprocess.call(command))
    except (KeyError, ValueError, OSError) as error:
        parser.exit(1, f"qualification: unpassed; {error}\n")


if __name__ == "__main__":
    main()
