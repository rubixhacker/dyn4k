#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from optimized_evidence import validate_installed_case, validate_provider, validate_r8
from prepare import verify_consumer_sources
from run import adb_for_serial, command, selected_emulator_serial, sha256


def snapshot_artifact(source, destination, expected_sha):
    if sha256(source) != expected_sha:
        raise ValueError(f"build artifact changed before snapshot: {source}")
    shutil.copyfile(source, destination)
    if sha256(destination) != expected_sha:
        raise ValueError(f"build artifact changed during snapshot: {source}")
    return {"path": str(destination), "sha256": expected_sha, "build_output_path": str(source)}


def dex_evidence(apk, directory, sdk):
    descriptors = set()
    files = []
    with zipfile.ZipFile(apk) as archive:
        names = sorted(name for name in archive.namelist() if re.fullmatch(r"classes\d*\.dex", name))
        if not names:
            raise ValueError("optimized APK has no DEX bytecode")
        for name in names:
            destination = directory / name
            destination.write_bytes(archive.read(name))
            dexdump = directory / (name + ".dexdump.txt")
            output = command([str(sdk / "build-tools/36.0.0/dexdump"), "-f", str(destination)], dexdump)
            descriptors.update(re.findall(r"Class descriptor\s+: '([^']+)'", output))
            files.append({"path": str(destination), "sha256": sha256(destination),
                          "dexdump": str(dexdump), "dexdump_sha256": sha256(dexdump)})
    if not descriptors:
        raise ValueError("DEX class descriptor inventory empty")
    return descriptors, files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--provider-graph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-type", choices=("debug", "release"), required=True)
    parser.add_argument("--expected-api", choices=("21", "36", "37"), required=True)
    parser.add_argument("--expected-abi", choices=("x86_64", "x86", "arm64-v8a", "armeabi-v7a"), default="x86_64")
    parser.add_argument("--emulator-serial", type=selected_emulator_serial, default="emulator-5558")
    args = parser.parse_args()
    root = args.repo.resolve()
    prepared_bytes = args.prepared.read_bytes()
    prepared = json.loads(prepared_bytes)
    prepared_checksum = hashlib.sha256(prepared_bytes).hexdigest()
    commit = command(["git", "-C", str(root), "rev-parse", "HEAD"]).strip()
    if commit != prepared["candidate_commit"] or command(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"]).strip():
        raise ValueError("optimized source is dirty or differs from prepared candidate commit")
    for artifact in (*prepared["staged"].values(), *prepared["staged_roots"].values()):
        if sha256(Path(artifact["path"])) != artifact["sha256"]:
            raise ValueError("staged AAR checksum changed")
    verify_consumer_sources(root, prepared)
    graph = args.provider_graph.read_text()
    validate_provider(graph)
    if args.provider_graph.stat().st_mtime_ns < args.prepared.stat().st_mtime_ns:
        raise ValueError("optimized provider graph predates prepared candidate")

    app = root / "consumers/android-runtime/optimized"
    build_type = args.build_type
    apk_dir = app / f"build/outputs/apk/{build_type}"
    test_dir = app / f"build/outputs/apk/androidTest/{build_type}"
    apks = list(apk_dir.glob("*.apk"))
    test_apks = list(test_dir.glob("*.apk"))
    if len(apks) != 1 or len(test_apks) != 1:
        raise ValueError("optimized app or instrumentation APK missing or duplicated")
    apk, test_apk = apks[0], test_apks[0]
    if any(path.stat().st_mtime_ns < args.prepared.stat().st_mtime_ns for path in (apk, test_apk)):
        raise ValueError("optimized APK predates prepared candidate")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sdk = Path(os.environ.get("ANDROID_HOME", "/var/home/stewart/Android/Sdk"))
    adb = adb_for_serial(sdk, args.emulator_serial)
    identity = {name: command(adb + ["shell", "getprop", name]).strip() for name in
                ("ro.build.fingerprint", "ro.build.version.sdk", "ro.product.cpu.abi",
                 "ro.product.cpu.abilist", "ro.product.model")}
    if identity["ro.build.version.sdk"] != args.expected_api or identity["ro.product.cpu.abi"] != args.expected_abi:
        raise ValueError(f"unexpected emulator: {identity}")
    app_snapshot = snapshot_artifact(apk, output / "app.apk", sha256(apk))
    test_snapshot = snapshot_artifact(test_apk, output / "instrumentation.apk", sha256(test_apk))
    graph_snapshot = snapshot_artifact(args.provider_graph, output / "provider-graph.txt", sha256(args.provider_graph))
    result = {"status": "FAILED", "candidate_commit": commit,
              "emulator_serial": args.emulator_serial,
              "source_tree": command(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"]).strip(),
              "runtime": identity, "build_type": build_type,
              "prepared_manifest": {"path": str(args.prepared), "sha256": prepared_checksum},
              "staged": prepared["staged"], "staged_roots": prepared["staged_roots"],
              "consumer_sources": prepared["consumer_sources"],
              "generated_consumer_sources": prepared["generated_consumer_sources"],
              "provider_graph": graph_snapshot,
              "app_apk": app_snapshot, "test_apk": test_snapshot}
    try:
        if build_type == "release":
            mapping_dir = app / "build/outputs/mapping/release"
            evidence = {}
            for name in ("configuration.txt", "mapping.txt", "usage.txt"):
                path = mapping_dir / name
                evidence[name] = snapshot_artifact(path, output / name, sha256(path))
            descriptors, files = dex_evidence(Path(app_snapshot["path"]), output, sdk)
            mapped = validate_r8((output / "configuration.txt").read_text(),
                                 (output / "mapping.txt").read_text(),
                                 (output / "usage.txt").read_text(), descriptors)
            result["r8"] = {"files": evidence, "mapped_path": mapped, "dex": files}
        command(adb + ["install", "-r", app_snapshot["path"]], output / "install-app.txt")
        command(adb + ["install", "-r", test_snapshot["path"]], output / "install-test.txt")
        package = "io.github.rubixhacker.dyn4k.optimized"
        result["package_path"] = command(adb + ["shell", "pm", "path", package], output / "package-path.txt").strip()
        if not result["package_path"].startswith("package:/data/app/"):
            raise ValueError("installed optimized app package path missing")
        command(adb + ["shell", "dumpsys", "package", package], output / "package.txt")
        command(adb + ["logcat", "-c"])
        command(adb + ["shell", "am", "start", "-W", "-n", package + "/.OptimizedActivity"], output / "launch.txt")
        result["process"] = command(adb + ["shell", "pidof", package], output / "process.txt").strip()
        if not result["process"]:
            raise ValueError("optimized app process absent")
        runners = command(adb + ["shell", "pm", "list", "instrumentation"], output / "instrumentations.txt")
        matches = [line.split(" ")[0].removeprefix("instrumentation:") for line in runners.splitlines()
                   if "(target=" + package + ")" in line]
        if len(matches) != 1:
            raise ValueError("optimized instrumentation runner mismatch")
        executed = subprocess.run(adb + ["shell", "am", "instrument", "-w", "-r", matches[0]],
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (output / "instrumentation.txt").write_text(executed.stdout)
        result["instrumentation_exit_code"] = executed.returncode
        result["cases"] = validate_installed_case(executed.stdout, executed.returncode)
        verify_consumer_sources(root, prepared)
        if sha256(args.prepared) != prepared_checksum:
            raise ValueError("prepared manifest changed during optimized installed run")
        result["status"] = "PASSED"
    except (RuntimeError, ValueError, OSError) as failure:
        result["error"] = str(failure)
    finally:
        command(adb + ["logcat", "-d"], output / "logcat.txt", check=False)
        (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "cases": result.get("cases"),
                      "error": result.get("error")}, sort_keys=True))
    if result["status"] != "PASSED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
