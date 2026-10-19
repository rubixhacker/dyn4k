#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import full_klib_consumer as klib
import independent_gates
import independent_linux_observer as observer


LANES = {f"linuxX64:Linux x64:current:{mode}" for mode in ("debug-g", "optimized-opt")}
SCHEMA = "linux-observed-klib/1"


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def _read(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError(f"record is not one regular file: {path}")
    raw = path.read_bytes()
    value = observer._parse_json(raw)
    if raw != _json(value):
        raise ValueError(f"record has noncanonical bytes: {path}")
    return value


def _sha(path):
    return observer._sha_file(path)


def _version(command):
    return subprocess.check_output(command, stderr=subprocess.STDOUT, text=True)


def _selection(repository, candidate, lane, staging, gradle, node, java_home,
               gradle_user_home, konan_data_dir):
    if lane not in LANES:
        raise ValueError("only current Linux x64 debug-g and optimized-opt are supported")
    repository = Path(repository).resolve(strict=True)
    staging = Path(staging).resolve(strict=True)
    gradle = Path(gradle).resolve(strict=True)
    node = Path(node).resolve(strict=True)
    java_home = Path(java_home).resolve(strict=True)
    gradle_user_home = Path(gradle_user_home).resolve(strict=True)
    konan_data_dir = Path(konan_data_dir).absolute()
    if klib.git(repository, "rev-parse", "HEAD").decode().strip() != candidate:
        raise ValueError("source checkout differs from exact candidate")
    if klib.git(repository, "status", "--porcelain").strip():
        raise ValueError("source checkout is not clean")
    java = java_home / "bin/java"
    java_version = next((line for line in _version([str(java), "-version"]).splitlines()
                         if 'version "21' in line), "")
    if not java_version or "Gradle 9.5.0" not in _version([str(gradle), "--version"]):
        raise ValueError("JDK 21 or Gradle 9.5.0 pin differs")
    native_home = konan_data_dir / "kotlin-native-prebuilt-linux-x86_64-2.4.20"
    native_executable = native_home / "bin/kotlinc-native"
    native_compiler = native_home / "konan/lib/kotlin-native-compiler-embeddable.jar"
    native_version = "\n".join(line for line in _version([str(native_executable), "-version"]).splitlines()
                               if line.startswith(("info: kotlinc-native", "Kotlin/Native:")))
    if "Kotlin/Native: 2.4.20" not in native_version:
        raise ValueError("Kotlin/Native 2.4.20 pin differs")
    observation = {"system": platform.system(), "kernel_release": platform.release(),
                   "machine": platform.machine(), "glibc": platform.libc_ver()[1],
                   "node_version": _version([str(node), "--version"]).strip()}
    klib.validate_runtime(lane, observation)
    hashes = {module: _sha(klib.staged_binary(staging, module, "linuxx64"))
              for module in klib.MODULES}
    toolchain = {
        "java_home": str(java_home), "java_version": java_version,
        "java_sha256": _sha(java), "gradle_version": "Gradle 9.5.0",
        "gradle_sha256": _sha(gradle), "node_version": observation["node_version"],
        "node_sha256": _sha(node), "gradle_user_home": str(gradle_user_home),
        "kgp_version": "2.4.20",
        "kotlin_native": {"home": str(native_home), "version": native_version,
                          "executable_sha256": _sha(native_executable),
                          "compiler_sha256": _sha(native_compiler)},
    }
    inputs = klib.input_bytes(repository, candidate, lane)
    manifest, selected = klib.contract(repository, lane)
    return {"schema": SCHEMA, "candidate_sha": candidate, "lane": lane,
            "mode": lane.rsplit(":", 1)[1], "source_tree": klib.git(
                repository, "rev-parse", f"{candidate}^{{tree}}").decode().strip(),
            "java_tool_options": "-XX:ActiveProcessorCount=2",
            "repository": str(repository), "staging": str(staging),
            "gradle": str(gradle), "node": str(node), "java_home": str(java_home),
            "gradle_user_home": str(gradle_user_home),
            "konan_data_dir": str(konan_data_dir),
            "runtime_identity": klib.observed_runtime_identity(observation, java_version),
            "runtime_observation": observation, "toolchain": toolchain,
            "staged_artifacts": hashes,
            "source_inventory_sha256": klib.sha(inputs["source-inventory.tsv"]),
            "approved_contract_sha256": independent_gates.digest(selected),
            "approved_manifest_sha256": independent_gates.digest(manifest),
            "launcher_sha256": _sha(gradle)}


def _launcher_binding(rows, build, selection):
    gradle = selection["gradle"]
    if (build["executable_sha256"] != selection["toolchain"]["java_sha256"]
            or "qualificationEvidence" not in build["argv"]
            or selection["lane"] not in build["argv"]):
        raise ValueError("selected Gradle Java image or task argv differs")
    build_images = [row for row in rows if row["kind"] == "image" and
                    row["pid"] == build["pid"]]
    selected = [row for row in build_images if row["executable_sha256"] ==
                build["executable_sha256"] and row["argv"] == build["argv"]]
    if len(selected) != 1:
        raise ValueError("selected Gradle Java image is absent or ambiguous")
    java_image = selected[0]
    scripts = [row for row in build_images if row["seq"] < java_image["seq"] and
               gradle in row["argv"] and row["executable_path"] != build["executable_path"]]
    if not scripts or selection["launcher_sha256"] != _sha(gradle):
        raise ValueError("Gradle script-to-Java exec binding is absent")
    script = scripts[-1]
    if not script["argv"] or not any(arg.endswith("/sh") for arg in script["argv"][:1]):
        raise ValueError("Gradle launcher did not execute in a shell image")
    return script, java_image


def _derive(root, selection, repository):
    root = Path(root)
    archive = root / "producer"
    witness = observer.verify(root / "observer")
    rows = [observer._parse_json(line) for line in
            (root / "observer/events.jsonl").read_bytes().splitlines()]
    receipt = _read(archive / "receipt.json")
    if (witness["status"] != "OBSERVED_UNSIGNED" or witness["qualification"] != "unqualified"
            or witness["candidate_sha"] != selection["candidate_sha"]
            or witness["lane"] != selection["lane"]
            or witness["runtime_identity"] != selection["runtime_identity"]
            or witness["staged_artifacts"] != selection["staged_artifacts"]
            or receipt["candidate_sha"] != selection["candidate_sha"]
            or receipt["source_tree"] != selection["source_tree"]
            or receipt["toolchain"] != selection["toolchain"]
            or receipt["source_inventory_sha256"] != selection["source_inventory_sha256"]):
        raise ValueError("observer, source, or producer identity differs")
    if (receipt["process"]["pid"] != witness["build"]["pid"]
            or receipt["process"]["parent_pid"] != rows[0]["root_pid"]
            or receipt["process"]["exit_code"] != 0):
        raise ValueError("producer Gradle PID differs from observed build")
    build = witness["build"]
    script, java_image = _launcher_binding(rows, build, selection)
    gradle = selection["gradle"]
    build_exit = next(row for row in rows if row["kind"] == "exit" and row["pid"] == build["pid"])
    start_wall = java_image.get("observed_wall_ns")
    end_wall = build_exit.get("observed_wall_ns")
    if not all(type(value) is int and value > 0 for value in (start_wall, end_wall)):
        raise ValueError("observer wall-clock process interval is absent")
    raw = {}
    observed_ids = {}
    for short, module in (("core", "dyn4k-core"), ("facade", "dyn4k")):
        runtime = _read(archive / f"runtime/{short}.json")
        executable = archive / f"runtime/{short}.program"
        process = witness["processes"][short]
        if (runtime["command"] != [process["executable_path"]]
                or runtime["executable_sha256"] != process["executable_sha256"]
                or _sha(executable) != process["executable_sha256"]
                or process["exit_code"] != 0
                or not build["started_ns"] <= process["started_ns"] <=
                process["finished_ns"] <= build["finished_ns"]):
            raise ValueError(f"{short} live image differs from retained program or build interval")
        selected = klib._selected_cases(archive / "inputs" / f"{short}-cases.tsv")
        ids = []
        for relative in receipt["raw_consumer_xml"]:
            if not relative.startswith(f"reports/raw/{short}/"):
                continue
            path = archive / relative
            if not start_wall <= path.stat().st_mtime_ns <= end_wall:
                raise ValueError(f"raw {short} XML lies outside observed build interval")
            measured, _ = klib._report(path.read_bytes(), "linuxX64", selected)
            ids.extend(measured)
            raw[relative] = _sha(path)
        if len(ids) != (2465 if short == "core" else 58) or len(set(ids)) != len(ids):
            raise ValueError(f"original {short} method identities are incomplete")
        observed_ids[short] = len(ids)
    if len(raw) != len(receipt["raw_consumer_xml"]):
        raise ValueError("raw XML inventory differs")
    archive_sha = independent_gates.archive_digest(archive)
    if archive_sha != witness["archive_sha256"]:
        raise ValueError("transported archive differs from observed seal")
    gate = klib.verify(archive, repository, selection["candidate_sha"], selection["lane"],
                       selection["staged_artifacts"], selection["runtime_identity"],
                       archive_sha, selection["toolchain"])
    return {"schema": SCHEMA, "status": "OBSERVED_UNSIGNED", "qualification": "unqualified",
            "candidate_sha": selection["candidate_sha"], "lane": selection["lane"],
            "source_tree": selection["source_tree"], "mode": selection["mode"],
            "archive_sha256": archive_sha,
            "event_log_sha256": witness["event_log_sha256"],
            "staged_artifacts": selection["staged_artifacts"],
            "source_inventory_sha256": selection["source_inventory_sha256"],
            "approved_contract_sha256": selection["approved_contract_sha256"],
            "approved_manifest_sha256": selection["approved_manifest_sha256"],
            "toolchain": selection["toolchain"], "runtime_identity": selection["runtime_identity"],
            "java_tool_options": selection["java_tool_options"],
            "launcher": {"path": gradle, "sha256": selection["launcher_sha256"],
                         "shell_image_sha256": script["executable_sha256"],
                         "shell_argv": script["argv"], "java_image_sha256":
                         build["executable_sha256"], "java_argv": build["argv"],
                         "pid": build["pid"], "start_ticks": build["start_ticks"]},
            "processes": {"build": build, **witness["processes"]},
            "raw_xml_sha256": raw, "original_method_counts": observed_ids,
            "coverage": witness["coverage"], "public_staged_consumer": gate}


def capture(args):
    selection = _selection(args.repository, args.candidate_sha, args.lane, args.staging,
                           args.gradle, args.node, args.java_home, args.gradle_user_home,
                           args.konan_data_dir)
    root = Path(args.output).absolute()
    if root.exists():
        raise ValueError("route output already exists")
    if root.is_relative_to(Path(args.repository).resolve()):
        raise ValueError("route output aliases source checkout")
    root.mkdir(mode=0o700)
    (root / "selection.json").write_bytes(_json(selection))
    archive = root / "producer"
    work = root / "producer-build"
    mode = klib.mode_path(args.lane)
    command = [sys.executable, str(Path(klib.__file__).resolve()), "run",
               "--repository", selection["repository"], "--candidate-sha", args.candidate_sha,
               "--lane", args.lane, "--staging", selection["staging"], "--output", str(archive),
               "--gradle", selection["gradle"], "--node", selection["node"],
               "--expected-core-sha256", selection["staged_artifacts"]["dyn4k-core"],
               "--expected-facade-sha256", selection["staged_artifacts"]["dyn4k"]]
    observer_command = [sys.executable, str(Path(observer.__file__).resolve()), "capture",
                        "--output", str(root / "observer"), "--candidate-sha", args.candidate_sha,
                        "--lane", args.lane, "--runtime-identity", selection["runtime_identity"],
                        "--mode", selection["mode"], "--archive", str(archive),
                        "--build-executable", f"{selection['java_home']}/bin/java",
                        "--build-argv-contains", "qualificationEvidence",
                        "--build-argv-contains", args.lane,
                        "--artifact", f"dyn4k-core={klib.staged_binary(Path(selection['staging']), 'dyn4k-core', 'linuxx64')}",
                        "--artifact", f"dyn4k={klib.staged_binary(Path(selection['staging']), 'dyn4k', 'linuxx64')}",
                        "--expect-generated", f"core={work}/core/bin/linuxX64/{mode}/test.kexe",
                        "--expect-generated", f"facade={work}/facade/bin/linuxX64/{mode}/test.kexe",
                        "--max-processes", "1024", "--max-events", "8192",
                        "--max-log-bytes", str(16 * 1024 * 1024),
                        "--timeout", str(args.timeout), "--", *command]
    env = os.environ.copy()
    env.update({"JAVA_HOME": selection["java_home"],
                "GRADLE_USER_HOME": selection["gradle_user_home"],
                "KONAN_DATA_DIR": selection["konan_data_dir"],
                "ANDROID_HOME": str(Path(args.android_home).resolve(strict=True)),
                "TMPDIR": str(Path(args.tmpdir).resolve(strict=True)),
                "PATH": f"{selection['java_home']}/bin:{env['PATH']}",
                "JAVA_TOOL_OPTIONS": selection["java_tool_options"],
                "PYTHONDONTWRITEBYTECODE": "1"})
    with (root / "observer-cli.stdout").open("wb") as stdout, (root / "observer-cli.stderr").open("wb") as stderr:
        result = subprocess.run(observer_command, env=env, stdout=stdout, stderr=stderr,
                                check=False)
    if result.returncode:
        raise ValueError(f"observer capture failed with {result.returncode}; see {root / 'observer-cli.stderr'}")
    record = _derive(root, selection, Path(args.repository).resolve())
    (root / "record.json").write_bytes(_json(record))
    return record


def verify(root, repository):
    root = Path(root).absolute()
    if root.is_symlink() or ".." in root.parts:
        raise ValueError("route root is symbolic or uses traversal")
    selection = _read(root / "selection.json")
    record = _read(root / "record.json")
    current = _selection(repository, selection["candidate_sha"], selection["lane"],
                         selection["staging"], selection["gradle"], selection["node"],
                         selection["java_home"], selection["gradle_user_home"],
                         selection["konan_data_dir"])
    if current != selection:
        raise ValueError("route selection differs from live exact-source and tool measurements")
    actual = _derive(root, selection, Path(repository).resolve(strict=True))
    if actual != record:
        raise ValueError("route record differs from independently replayed evidence")
    return actual


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    run = sub.add_parser("capture")
    for name in ("repository", "candidate-sha", "lane", "staging", "output", "gradle",
                 "node", "java-home", "gradle-user-home", "konan-data-dir", "android-home",
                 "tmpdir"):
        run.add_argument(f"--{name}", required=True)
    run.add_argument("--timeout", type=float, default=1200)
    replay = sub.add_parser("verify")
    replay.add_argument("--root", required=True)
    replay.add_argument("--repository", required=True)
    args = parser.parse_args(argv)
    result = capture(args) if args.action == "capture" else verify(args.root, args.repository)
    print(json.dumps({"status": result["status"], "qualification": result["qualification"],
                      "lane": result["lane"], "archive_sha256": result["archive_sha256"],
                      "event_log_sha256": result["event_log_sha256"],
                      "original_method_counts": result["original_method_counts"],
                      "coverage": result["coverage"]}, sort_keys=True))


if __name__ == "__main__":
    main()
