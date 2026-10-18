import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from receipt import (ASSERTIONS, EXPECTED_FINGERPRINT, GUEST_PROPERTIES,
                     TRUSTED_ADB_SHA256, elf_abi, sha256, trusted_adb,
                     validate_dependency_graph)


PIN_PATH = "tools/android-native-runtime/full-pins.json"
CORPUS_PATH = "tools/qualification/full-common-corpus.json"
VERSION = "0.1.0-alpha.1"
LANES = tuple((module, variant) for module in ("core", "facade", "consumer")
              for variant in ("debug", "optimized"))
STAGE_TASKS = (
    ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
    ":dyn4k:publishKotlinMultiplatformPublicationToStagingRepository",
    ":dyn4k-core:publishAndroidNativeX64PublicationToStagingRepository",
    ":dyn4k:publishAndroidNativeX64PublicationToStagingRepository",
)
TEST_TASKS = tuple(f":{module}:link{build}TestAndroidNativeX64"
                   for module in ("dyn4k-core", "dyn4k")
                   for build in ("Debug", "Release"))
CONSUMER_TASKS = ("linkDebugExecutableAndroidNativeX64",
                  "linkReleaseExecutableAndroidNativeX64")
ROOT_GRADLE = ("./gradlew", "--no-daemon", "--max-workers=2", "--rerun-tasks", "--console=plain")
GUEST_REMOTE = "/data/local/tmp/dyn4k-full-{module}-{variant}"
CASE_LINE = re.compile(r"^\[ RUN      \] ([A-Za-z_][\w.]+)$", re.M)
OK_LINE = re.compile(r"^\[       OK \] ([A-Za-z_][\w.]+) \(\d+ ms\)$", re.M)
PASS_LINE = re.compile(r"^\[  PASSED  \] (\d+) tests\.$", re.M)
TOTAL_LINE = re.compile(r"^\[==========\] (\d+) tests from \d+ test cases ran\. \(\d+ ms total\)$", re.M)


def digest_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def git(root, *args):
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if proc.returncode:
        raise ValueError(f"Git object unavailable: {args}: {proc.stderr.decode(errors='replace')}")
    return proc.stdout


def source_identity(root, require_clean=True):
    if require_clean and git(root, "status", "--porcelain", "--untracked-files=all").strip():
        raise ValueError("source worktree is not clean")
    source_sha = git(root, "rev-parse", "HEAD").decode().strip()
    source_tree = git(root, "rev-parse", "HEAD^{tree}").decode().strip()
    return source_sha, source_tree


def manifest_at(root, source_sha):
    raw = git(root, "show", f"{source_sha}:{CORPUS_PATH}")
    if (root / CORPUS_PATH).read_bytes() != raw:
        raise ValueError("working corpus manifest differs from committed source")
    manifest = json.loads(raw)
    if manifest.get("kind") != "full-common-corpus" or manifest.get("policy") != "production":
        raise ValueError("full production common corpus is required")
    sys.path.insert(0, str(root / "tools/qualification"))
    import full_corpus
    regenerated = full_corpus.make_manifest(full_corpus.scan_sources(root),
                                             manifest["original_mappings"], True, root)
    if regenerated != manifest:
        raise ValueError("source-derived corpus or mapping differs")
    if manifest["counts"]["mapped_original_methods"] != 2253 or manifest["counts"]["supplemental_methods"] != 259:
        raise ValueError("reviewed common corpus totals differ")
    return manifest, digest_bytes(raw)


def expected_cases(manifest, module):
    source_module = "dyn4k-core" if module == "core" else "dyn4k"
    return {case["classname"] + "." + case["method"]
            for case in manifest["cases"]
            if case["module"] == source_module and case["source_set"] == "commonTest"}


def executable_path(root, module, variant):
    if module == "consumer":
        build = "debugExecutable" if variant == "debug" else "releaseExecutable"
        return root / "consumers/android-native-runtime/build/bin/androidNativeX64" / build / "journey.kexe"
    source_module = "dyn4k-core" if module == "core" else "dyn4k"
    build = "debugTest" if variant == "debug" else "releaseTest"
    return root / source_module / "build/bin/androidNativeX64" / build / "test.kexe"


def klib_paths(root):
    staging = root / "build/staging-repository/io/github/rubixhacker"
    return {module: staging / f"{module}-androidnativex64/{VERSION}/{module}-androidnativex64-{VERSION}.klib"
            for module in ("dyn4k-core", "dyn4k")}


def tool_paths(root):
    sdk = Path("/home/stewart/Android/Sdk")
    native = Path("/var/home/stewart/.konan/kotlin-native-prebuilt-linux-x86_64-2.4.20")
    return {
        "adb": Path(trusted_adb()),
        "emulator": sdk / "emulator/emulator",
        "image": sdk / "system-images/android-37.0/google_apis_playstore/x86_64/source.properties",
        "system_image": sdk / "system-images/android-37.0/google_apis_playstore/x86_64/system.img",
        "ramdisk": sdk / "system-images/android-37.0/google_apis_playstore/x86_64/ramdisk.img",
        "ndk": sdk / "ndk/28.2.13676358/source.properties",
        "java": Path("/tmp/dyn4k-tools/jdk21/bin/java"),
        "konan": native / "konan/konan.properties",
        "native_compiler": native / "konan/lib/kotlin-native-compiler-embeddable.jar",
        "kgp": Path("/var/home/stewart/.gradle/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-gradle-plugin/2.4.20/d64b6d447eecf2b0f6d19bdd677cae3bbce37585/kotlin-gradle-plugin-2.4.20-gradle96.jar"),
        "gradle_wrapper": root / "gradle/wrapper/gradle-wrapper.jar",
        "gradle_core": Path("/var/home/stewart/.gradle/wrapper/dists/gradle-9.5.0-bin/bvnork1r7n8i6kp5cnkibsc9q/gradle-9.5.0/lib/gradle-core-9.5.0.jar"),
    }


def command(root, argv, *, env=None):
    proc = subprocess.run(argv, cwd=root, env=env, capture_output=True)
    return {"command": list(argv), "exit_code": proc.returncode,
            "stdout": proc.stdout, "stderr": proc.stderr}


def build_environment():
    env = os.environ.copy()
    env["JAVA_HOME"] = "/tmp/dyn4k-tools/jdk21"
    env["ANDROID_HOME"] = "/home/stewart/Android/Sdk"
    env["ANDROID_SDK_ROOT"] = env["ANDROID_HOME"]
    return env


def build_commands(root):
    consumer = ("./gradlew", "-p", "consumers/android-native-runtime", "--no-daemon",
                "--max-workers=2", "--rerun-tasks", "--console=plain",
                f"-PstagingRepository={root / 'build/staging-repository'}")
    return {"stage": ROOT_GRADLE + STAGE_TASKS,
            "tests": ROOT_GRADLE + TEST_TASKS,
            "consumer": consumer + CONSUMER_TASKS}


def graph_commands(root):
    common = ("./gradlew", "--no-daemon", "--console=plain")
    return {
        "core": common + (":dyn4k-core:dependencies", "--configuration", "androidNativeX64TestCompileKlibraries"),
        "facade": common + (":dyn4k:dependencies", "--configuration", "androidNativeX64TestCompileKlibraries"),
        "consumer": ("./gradlew", "-p", "consumers/android-native-runtime", "--no-daemon", "--console=plain",
                     f"-PstagingRepository={root / 'build/staging-repository'}", "dependencies", "--configuration",
                     "androidNativeX64CompileKlibraries"),
    }


def graph_section(raw, module):
    text = raw.decode("utf-8")
    header = "androidNativeX64CompileKlibraries -" if module == "consumer" else "androidNativeX64TestCompileKlibraries -"
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(header)]
    if len(starts) != 1:
        raise ValueError(f"missing or duplicate {module} dependency graph")
    end = starts[0] + 1
    while end < len(lines) and lines[end]:
        end += 1
    section = "\n".join(lines[starts[0]:end]) + "\n"
    if module == "consumer":
        validate_dependency_graph(section)
    elif "org.dyn4j:dyn4j" in section or "io.github.rubixhacker:" in section:
        raise ValueError("root test graph has an unapproved provider")
    return section


def collect_pin_inputs(root, graphs):
    return {
        "schema": 2,
        "corpus_sha256": sha256(root / CORPUS_PATH),
        "guest_fingerprint": EXPECTED_FINGERPRINT,
        "tools": {name: sha256(path) for name, path in tool_paths(root).items()},
        "klibs": {module: sha256(path) for module, path in klib_paths(root).items()},
        "executables": {f"{module}-{variant}": sha256(executable_path(root, module, variant))
                        for module, variant in LANES},
        "graphs": {module: digest_bytes(graph_section(graphs[module], module).encode())
                   for module in graph_commands(root)},
    }


def load_pins(root, source_sha):
    raw = git(root, "show", f"{source_sha}:{PIN_PATH}")
    if (root / PIN_PATH).read_bytes() != raw:
        raise ValueError("working full pin file differs from committed source")
    pins = json.loads(raw)
    if pins.get("schema") != 2 or set(pins.get("executables", {})) != {f"{m}-{v}" for m, v in LANES}:
        raise ValueError("full build pin manifest is incomplete")
    return pins, digest_bytes(raw)


def read_record(record):
    path = Path(record["path"])
    raw = path.read_bytes()
    if digest_bytes(raw) != record.get("sha256"):
        raise ValueError(f"raw evidence hash differs: {path}")
    return raw


def save_record(output, name, raw):
    path = output / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"path": str(path), "sha256": digest_bytes(raw)}


def save_command(output, name, proc):
    return {"command": proc["command"], "exit_code": proc["exit_code"],
            "stdout": save_record(output, name + ".stdout", proc["stdout"]),
            "stderr": save_record(output, name + ".stderr", proc["stderr"])}


def parse_list(raw):
    names = []
    suite = None
    for line in raw.decode("utf-8").splitlines():
        if line.startswith("  "):
            if suite is None or not re.fullmatch(r"  [A-Za-z_]\w*", line):
                raise ValueError("native test listing has an invalid method")
            names.append(suite + "." + line.strip())
        elif line.endswith(".") and re.fullmatch(r"[A-Za-z_][\w.]*\.", line):
            suite = line[:-1]
        else:
            raise ValueError("native test listing has unexpected output")
    if not names:
        raise ValueError("native test listing is empty")
    return names


def parse_test_run(raw):
    text = raw.decode("utf-8")
    running = CASE_LINE.findall(text)
    passed = OK_LINE.findall(text)
    totals = TOTAL_LINE.findall(text)
    summaries = PASS_LINE.findall(text)
    if (not running or running != passed or len(totals) != 1 or len(summaries) != 1
            or int(totals[0]) != len(running) or int(summaries[0]) != len(running)
            or re.search(r"(?m)^\[\s*(?:FAILED|SKIPPED|DISABLED)\s*\]", text)):
        raise ValueError("native test result lines or totals differ")
    return running


def check_cases(observed, expected):
    counts = Counter(observed)
    missing = expected - set(counts)
    extra = set(counts) - expected
    duplicates = {name for name, count in counts.items() if count != 1}
    if missing or extra or duplicates:
        raise ValueError(f"native cases differ: missing={len(missing)}, extra={len(extra)}, duplicate={len(duplicates)}")
    return len(observed)


def guest_query(root, adb):
    prefix = [adb, "-P", "5038", "-s", "emulator-5558"]
    devices = command(root, [adb, "-P", "5038", "devices", "-l"])
    if devices["exit_code"] or devices["stderr"]:
        raise ValueError("isolated ADB device query failed")
    device_lines = [line for line in devices["stdout"].decode().splitlines() if line.startswith("emulator-")]
    if len(device_lines) != 1 or device_lines[0].split()[:2] != ["emulator-5558", "device"]:
        raise ValueError("isolated ADB server has an unexpected device")
    observations = {}
    for prop in GUEST_PROPERTIES:
        proc = command(root, prefix + ["shell", "getprop", prop])
        if proc["exit_code"] or proc["stderr"]:
            raise ValueError(f"guest property query failed: {prop}")
        observations[prop] = proc
    return {"devices": devices, "observations": observations}


def guest_values(guest):
    values = {GUEST_PROPERTIES[prop]: proc["stdout"].decode().strip()
              for prop, proc in guest["observations"].items()}
    if (values.get("avd_name") != "dyn4k_api37_play_x64" or values.get("api") != "37"
            or values.get("fingerprint") != EXPECTED_FINGERPRINT or values.get("primary_abi") != "x86_64"
            or values.get("boot_completed") != "1" or "x86_64" not in values.get("abi_list", "").split(",")):
        raise ValueError("stale or wrong Android Native x64 guest")
    return values


def save_guest(output, guest):
    return {"devices": save_command(output, "guest/devices", guest["devices"]),
            "observations": {prop: save_command(output, f"guest/{prop}", proc)
                             for prop, proc in guest["observations"].items()},
            "values": guest_values(guest)}


def validate_command_record(record, argv):
    if record.get("command") != list(argv) or record.get("exit_code") != 0:
        raise ValueError("recorded command differs or failed")
    return read_record(record["stdout"]), read_record(record["stderr"])


def build_task_marker(task):
    return "> Task " + (task if task.startswith(":") else ":" + task)


def validate_deployment_output(push, push_err, chmod_err, remote_out, remote_err, expected_hash):
    if (b"1 file pushed" not in push + push_err or b"failed" in (push + push_err).lower()
            or chmod_err or remote_err or remote_out.decode().split()[0] != expected_hash):
        raise ValueError("deployed executable bytes differ")


def validate_guest(record, root):
    adb = trusted_adb()
    devices, stderr = validate_command_record(record["devices"], [adb, "-P", "5038", "devices", "-l"])
    device_lines = [line for line in devices.decode().splitlines() if line.startswith("emulator-")]
    if stderr or len(device_lines) != 1 or device_lines[0].split()[:2] != ["emulator-5558", "device"]:
        raise ValueError("guest device listing differs")
    observations = {}
    if set(record.get("observations", {})) != set(GUEST_PROPERTIES):
        raise ValueError("guest property observations are incomplete")
    for prop in GUEST_PROPERTIES:
        stdout, stderr = validate_command_record(record["observations"][prop],
                                                 [adb, "-P", "5038", "-s", "emulator-5558", "shell", "getprop", prop])
        if stderr:
            raise ValueError("guest property query has stderr")
        observations[prop] = {"stdout": stdout}
    values = guest_values({"observations": observations})
    if values != record.get("values"):
        raise ValueError("guest values differ from raw observations")


def validate_result(result, root):
    root = root.resolve()
    source_sha = result["source_sha"]
    if result.get("schema") != 2 or result.get("status") != "RUNTIME_PASSED" or result.get("root") != str(root):
        raise ValueError("full receipt status, schema, or root differs")
    if git(root, "rev-parse", f"{source_sha}^{{tree}}").decode().strip() != result.get("source_tree"):
        raise ValueError("source tree differs from Git object")
    if source_identity(root) != (source_sha, result["source_tree"]):
        raise ValueError("source checkout drifted from the executed commit")
    manifest, manifest_hash = manifest_at(root, source_sha)
    if manifest_hash != result.get("corpus_sha256"):
        raise ValueError("committed corpus hash differs")
    pins, pin_hash = load_pins(root, source_sha)
    if pin_hash != result.get("pin_sha256") or pins["corpus_sha256"] != manifest_hash:
        raise ValueError("committed full pins differ")
    if pins["guest_fingerprint"] != EXPECTED_FINGERPRINT or pins["tools"]["adb"] != TRUSTED_ADB_SHA256:
        raise ValueError("trusted guest or ADB pin differs")
    for name, path in tool_paths(root).items():
        if sha256(path) != pins["tools"].get(name):
            raise ValueError(f"toolchain or Android image differs: {name}")
    commands = build_commands(root)
    if set(result.get("builds", {})) != set(commands):
        raise ValueError("build receipts are incomplete")
    for name, argv in commands.items():
        stdout, stderr = validate_command_record(result["builds"][name], argv)
        log = (stdout + stderr).decode("utf-8")
        tasks = {"stage": STAGE_TASKS, "tests": TEST_TASKS, "consumer": CONSUMER_TASKS}[name]
        if "BUILD SUCCESSFUL" not in log or any(build_task_marker(task) not in log for task in tasks):
            raise ValueError(f"{name} build tasks are absent")
    graph_argv = graph_commands(root)
    if set(result.get("graphs", {})) != set(graph_argv):
        raise ValueError("dependency reports are incomplete")
    graphs = {}
    for module, argv in graph_argv.items():
        stdout, stderr = validate_command_record(result["graphs"][module], argv)
        if stderr or b"BUILD SUCCESSFUL" not in stdout:
            raise ValueError("Gradle dependency query failed")
        graphs[module] = stdout
        if digest_bytes(graph_section(stdout, module).encode()) != pins["graphs"].get(module):
            raise ValueError(f"{module} Gradle dependency graph differs")
    for module, path in klib_paths(root).items():
        if sha256(path) != pins["klibs"].get(module):
            raise ValueError(f"staged {module} KLIB differs")
    for module, variant in LANES:
        path = executable_path(root, module, variant)
        if sha256(path) != pins["executables"].get(f"{module}-{variant}") or elf_abi(path) != "x86_64":
            raise ValueError(f"{module} {variant} ELF differs")
    validate_guest(result["guest"], root)
    if set(result.get("lanes", {})) != {f"{m}-{v}" for m, v in LANES}:
        raise ValueError("six native guest lanes are required")
    total = 0
    adb = trusted_adb()
    prefix = [adb, "-P", "5038", "-s", "emulator-5558"]
    for module, variant in LANES:
        key = f"{module}-{variant}"
        lane = result["lanes"][key]
        path = executable_path(root, module, variant)
        remote = GUEST_REMOTE.format(module=module, variant=variant)
        push, push_err = validate_command_record(lane["push"], prefix + ["push", str(path), remote])
        _, chmod_err = validate_command_record(lane["chmod"], prefix + ["shell", "chmod", "700", remote])
        remote_out, remote_err = validate_command_record(lane["remote_hash"], prefix + ["shell", "sha256sum", remote])
        validate_deployment_output(push, push_err, chmod_err, remote_out, remote_err,
                                   pins["executables"][key])
        if module != "consumer":
            listed, list_err = validate_command_record(lane["list"], prefix + ["shell", remote, "--ktest_list_tests"])
            if list_err:
                raise ValueError(f"{key} test listing has stderr")
            check_cases(parse_list(listed), expected_cases(manifest, module))
            argv = prefix + ["shell", remote, "--ktest_logger=GTEST"]
        else:
            if "list" in lane:
                raise ValueError("consumer has an unexpected test listing")
            argv = prefix + ["shell", remote]
        stdout, stderr = validate_command_record(lane["process"], argv)
        if stderr or not stdout:
            raise ValueError(f"{key} process stderr or stdout differs")
        if module == "consumer":
            expected = [f"ASSERT {label}" for label in ASSERTIONS] + [f"NATIVE_RESULT PASS {len(ASSERTIONS)}"]
            if stdout.decode().splitlines() != expected or lane.get("case_count") != len(ASSERTIONS):
                raise ValueError("staged consumer assertions differ")
        else:
            count = check_cases(parse_test_run(stdout), expected_cases(manifest, module))
            if lane.get("case_count") != count:
                raise ValueError(f"{key} case count differs")
            total += count
    if total != 2 * (2454 + 58) or result.get("total_common_cases") != total:
        raise ValueError("full native corpus total differs")
    if result.get("mapped_common_executions") != 2 * 2253 or result.get("supplemental_common_executions") != 2 * 259:
        raise ValueError("mapped or supplemental case totals differ")
    return {"status": "CONSISTENCY_ONLY", "total_common_cases": total,
            "consumer_assertions": 2 * len(ASSERTIONS)}


def run_pin(root, output):
    env = build_environment()
    graphs = {}
    for module, argv in graph_commands(root).items():
        proc = command(root, argv, env=env)
        if proc["exit_code"]:
            raise ValueError(f"{module} dependency query failed")
        graphs[module] = proc["stdout"]
    pins = collect_pin_inputs(root, graphs)
    output.write_text(json.dumps(pins, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"pin_proposal": str(output), "executables": pins["executables"]}, sort_keys=True))


def run_live(root, output):
    output.mkdir(parents=True, exist_ok=True)
    result = {"schema": 2, "status": "UNPASSED", "root": str(root),
              "started_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        source_sha, source_tree = source_identity(root)
        result.update(source_sha=source_sha, source_tree=source_tree)
        _, result["corpus_sha256"] = manifest_at(root, source_sha)
        pins, result["pin_sha256"] = load_pins(root, source_sha)
        env = build_environment()
        result["builds"] = {}
        for name, argv in build_commands(root).items():
            proc = command(root, argv, env=env)
            result["builds"][name] = save_command(output, f"build/{name}", proc)
            if proc["exit_code"]:
                raise ValueError(f"{name} build failed: {proc['stderr'].decode(errors='replace')[-500:]}")
        result["graphs"] = {}
        for module, argv in graph_commands(root).items():
            proc = command(root, argv, env=env)
            result["graphs"][module] = save_command(output, f"graph/{module}", proc)
            if proc["exit_code"]:
                raise ValueError(f"{module} dependency query failed")
        if source_identity(root) != (source_sha, source_tree):
            raise ValueError("source checkout changed during build")
        current = collect_pin_inputs(root, {module: read_record(item["stdout"])
                                            for module, item in result["graphs"].items()})
        if current != pins:
            raise ValueError("final source build outputs, tools, or graphs differ from committed pins")
        adb = trusted_adb()
        guest = guest_query(root, adb)
        result["guest"] = save_guest(output, guest)
        result["lanes"] = {}
        for module, variant in LANES:
            key = f"{module}-{variant}"
            path = executable_path(root, module, variant)
            remote = GUEST_REMOTE.format(module=module, variant=variant)
            prefix = [adb, "-P", "5038", "-s", "emulator-5558"]
            lane = {}
            for name, argv in (("push", prefix + ["push", str(path), remote]),
                               ("chmod", prefix + ["shell", "chmod", "700", remote]),
                               ("remote_hash", prefix + ["shell", "sha256sum", remote])):
                proc = command(root, argv)
                lane[name] = save_command(output, f"lanes/{key}/{name}", proc)
                if proc["exit_code"]:
                    raise ValueError(f"{key} {name} failed")
            if module != "consumer":
                proc = command(root, prefix + ["shell", remote, "--ktest_list_tests"])
                lane["list"] = save_command(output, f"lanes/{key}/list", proc)
                if proc["exit_code"]:
                    raise ValueError(f"{key} list failed")
                argv = prefix + ["shell", remote, "--ktest_logger=GTEST"]
            else:
                argv = prefix + ["shell", remote]
            proc = command(root, argv)
            lane["process"] = save_command(output, f"lanes/{key}/process", proc)
            lane["case_count"] = len(CASE_LINE.findall(proc["stdout"].decode(errors="replace"))) if module != "consumer" else len(ASSERTIONS)
            result["lanes"][key] = lane
        result["total_common_cases"] = sum(lane["case_count"] for key, lane in result["lanes"].items()
                                           if not key.startswith("consumer-"))
        result["mapped_common_executions"] = 2 * 2253
        result["supplemental_common_executions"] = 2 * 259
        result["status"] = "RUNTIME_PASSED"
        result["replay"] = validate_result(result, root)
    except (OSError, ValueError, KeyError, UnicodeError, IndexError, TypeError) as error:
        result["status"] = "UNPASSED"
        result["error"] = str(error)
    result["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result.get(key) for key in ("status", "source_sha", "total_common_cases", "error")}, sort_keys=True))
    return 0 if result["status"] == "RUNTIME_PASSED" else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("pin", "run", "verify"))
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    if args.action == "pin":
        run_pin(root, args.output.resolve())
    elif args.action == "run":
        return run_live(root, args.output.resolve())
    else:
        result = json.loads(args.output.read_text())
        print(json.dumps(validate_result(result, root), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
