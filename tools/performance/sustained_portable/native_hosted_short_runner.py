import hashlib
import errno
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import time

root = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
evidence = (Path(os.environ["RUNNER_TEMP"]) / "performance-native-host-short").resolve()
evidence.mkdir(parents=True, exist_ok=True)
target = os.environ["TARGET"]
build = os.environ["BUILD"]
sha = os.environ["GITHUB_SHA"]
route = {"source_sha": sha, "target": target, "build": build,
         "runner_os": os.environ["RUNNER_OS"], "host": platform.uname()._asdict(),
         "run_id": os.environ["GITHUB_RUN_ID"],
         "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
         "qualification": "unpassed", "commands": {}, "scenarios": {},
         "memory_scenarios": {}}

def path_swap_command(root, output, target, selected, sha):
    command = [sys.executable, "-B",
               root / "tools/performance/sustained_portable/host_image_adverse.py",
               "--output", output]
    if target == "mingwX64":
        harness = Path(selected["harness"])
        expected = selected["bundle_sha256"].get(harness.name)
        if not expected:
            raise ValueError("inventory executable hash is missing")
        command.extend(["--control-image", harness, "--control-sha256", expected,
                        "--control-source-sha", sha])
    return command

def process_rows():
    listing = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,stat="],
                             capture_output=True, text=True, timeout=5, check=True)
    return {int(parts[0]): (int(parts[1]), parts[2])
            for line in listing.stdout.splitlines()
            if len(parts := line.split()) >= 3}

def descendants(parent, rows):
    found = set()
    pending = [parent]
    while pending:
        current = pending.pop()
        children = {pid for pid, (ppid, _) in rows.items() if ppid == current}
        found.update(children)
        pending.extend(children)
    return found

def raw_file(path):
    if not path.is_file():
        return {"status": "missing"}
    before = path.stat()
    size = before.st_size
    if size > 64 * 1024 * 1024:
        return {"bytes": size, "status": "hash_size_limit"}
    value = hashlib.sha256()
    read_bytes = 0
    with path.open("rb") as stream:
        while read_bytes < size + 1:
            block = stream.read(min(65536, size + 1 - read_bytes))
            if not block:
                break
            value.update(block)
            read_bytes += len(block)
    after = path.stat()
    identity = lambda row: (row.st_dev, row.st_ino, row.st_size,
                            row.st_mtime_ns, row.st_ctime_ns)
    if read_bytes != size or identity(before) != identity(after):
        return {"bytes": after.st_size, "read_bytes": read_bytes,
                "status": "changed_during_hash"}
    return {"bytes": read_bytes, "sha256": value.hexdigest()}

def sidecar_bytes(path):
    before = path.stat()
    if before.st_size > 8 * 1024 * 1024:
        raise ValueError("Native memory sidecar exceeds read limit")
    with path.open("rb") as stream:
        snapshot = stream.read(before.st_size + 1)
    after = path.stat()
    identity = lambda row: (row.st_dev, row.st_ino, row.st_size,
                            row.st_mtime_ns, row.st_ctime_ns)
    if len(snapshot) != before.st_size or identity(before) != identity(after):
        raise ValueError("Native memory sidecar changed during read")
    return snapshot

def resident_probe_errors_complete(resident, capture, execution, selected_target):
    expected_method = {"macosArm64": "proc_pidinfo_task_resident",
                       "mingwX64": "GetProcessMemoryInfo_working_set"}.get(selected_target)
    if expected_method is None or resident.get("method") != expected_method:
        return False
    samples = resident["samples"]
    declared_samples = capture["rss_observation"].get("samples")
    if (type(samples) is not list or not samples or
            type(declared_samples) is not int or declared_samples != len(samples) or
            any(type(sample) is not list or len(sample) != 2 or
                type(sample[0]) is not int or type(sample[1]) is not int or
                sample[1] <= 0 for sample in samples)):
        return False
    started = execution.get("started_monotonic_ns")
    ended = execution.get("ended_monotonic_ns")
    if (type(started) is not int or type(ended) is not int or started >= ended or
            execution.get("termination") != "natural" or
            type(execution.get("exit_code")) is not int or execution["exit_code"] != 0 or
            any(sample[0] < started or sample[0] > ended for sample in samples) or
            any(left[0] > right[0] for left, right in zip(samples, samples[1:]))):
        return False
    errors = resident["errors"]
    if not isinstance(errors, list):
        return False
    if (type(capture["rss_observation"]["errors"]) is not int or
            capture["rss_observation"]["errors"] != len(errors)):
        return False
    if not errors:
        return True
    if selected_target != "macosArm64" or len(errors) != 1:
        return False
    row = errors[0]
    if (not isinstance(row, dict) or
            row.get("classification") != "terminal_esrch_exit_confirmed" or
            type(row.get("errno")) is not int or
            row.get("errno") != errno.ESRCH or
            type(row.get("exit_code")) is not int or row["exit_code"] != 0 or
            type(row.get("returncode_at_error")) is not int or
            row["returncode_at_error"] != 0 or
            type(row.get("returncode_checked_monotonic_ns")) is not int or
            row.get("returncode_checked_monotonic_ns") !=
                row.get("exit_observed_monotonic_ns") or
            type(row.get("error")) is not str or
            "macOS process resident bytes unavailable" not in row.get("error", "")):
        return False
    stamps = (started, row["monotonic_ns"],
              row["error_observed_monotonic_ns"], row["exit_observed_monotonic_ns"],
              ended)
    return (all(type(stamp) is int for stamp in stamps) and
            list(stamps) == sorted(stamps) and
            stamps[3] - stamps[2] <= 1_000_000 and
            all(sample[0] < row["monotonic_ns"] for sample in samples))

def execute(label, argv, timeout=300):
    output = evidence / label
    output.parent.mkdir(parents=True, exist_ok=True)
    stdout_path = output.with_suffix(".stdout.bin")
    stderr_path = output.with_suffix(".stderr.bin")
    record = {"argv": [str(part) for part in argv], "timeout_seconds": timeout,
              "stdout": str(stdout_path.relative_to(evidence)),
              "stderr": str(stderr_path.relative_to(evidence))}
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
                       if os.name == "nt" else {"start_new_session": True})
            process = subprocess.Popen(record["argv"], cwd=root,
                                       stdout=stdout, stderr=stderr, **options)
            record["pid"] = process.pid
            try:
                record["exit_code"] = process.wait(timeout=timeout)
                record["termination"] = "natural"
            except subprocess.TimeoutExpired:
                record["error"] = "timeout"
                try:
                    if os.name == "nt":
                        kill_stdout = output.with_suffix(".termination.stdout.bin")
                        kill_stderr = output.with_suffix(".termination.stderr.bin")
                        record["tree_kill_stdout"] = str(kill_stdout.relative_to(evidence))
                        record["tree_kill_stderr"] = str(kill_stderr.relative_to(evidence))
                        with kill_stdout.open("wb") as out, kill_stderr.open("wb") as err:
                            killer = subprocess.Popen(
                                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                stdout=out, stderr=err)
                            try:
                                record["tree_kill_exit_code"] = killer.wait(timeout=20)
                            except subprocess.TimeoutExpired:
                                killer.kill()
                                killer.wait(timeout=5)
                                record["tree_kill_error"] = "taskkill deadline"
                    else:
                        os.killpg(process.pid, signal.SIGSTOP)
                        record["process_group_stop"] = "SIGSTOP"
                        tracked = set()
                        for _ in range(4):
                            found = descendants(process.pid, process_rows())
                            fresh = found - tracked
                            for pid in fresh:
                                try:
                                    os.kill(pid, signal.SIGSTOP)
                                except ProcessLookupError:
                                    pass
                            tracked.update(fresh)
                            if not fresh:
                                break
                        else:
                            record["tree_kill_error"] = "descendants did not quiesce"
                        record["descendant_pids"] = sorted(tracked)
                        for pid in sorted(tracked, reverse=True):
                            try:
                                os.kill(pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                        os.killpg(process.pid, signal.SIGKILL)
                        record["process_group_signal"] = "SIGKILL"
                except (OSError, ValueError, subprocess.CalledProcessError,
                        subprocess.TimeoutExpired) as error:
                    record["tree_kill_error"] = str(error)
                    if os.name != "nt":
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                try:
                    record["exit_code"] = process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        record["exit_code"] = process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        record["exit_code"] = None
                    record["tree_kill_error"] = "wrapper required direct kill"
                if os.name != "nt" and "descendant_pids" in record:
                    try:
                        deadline = time.monotonic() + 2
                        while True:
                            rows = process_rows()
                            remaining = [pid for pid in record["descendant_pids"]
                                         if pid in rows and not rows[pid][1].startswith("Z")]
                            if not remaining or time.monotonic() >= deadline:
                                break
                            time.sleep(0.05)
                        record["remaining_descendant_pids"] = remaining
                        if remaining:
                            record["tree_kill_error"] = "descendants survived deadline cleanup"
                    except (OSError, subprocess.CalledProcessError,
                            subprocess.TimeoutExpired) as error:
                        record["tree_kill_error"] = "descendant verification failed: " + str(error)
                if record.get("tree_kill_error"):
                    record["termination"] = "deadline_tree_unverified"
                elif os.name == "nt":
                    record["termination"] = (
                        "deadline_tree_signaled" if record.get("tree_kill_exit_code") == 0
                        else "deadline_tree_unverified")
                else:
                    record["termination"] = (
                        "deadline_observed_tree_stopped"
                        if record.get("process_group_signal") == "SIGKILL"
                        and not record.get("remaining_descendant_pids")
                        else "deadline_tree_unverified")
    except OSError as error:
        with stderr_path.open("ab") as stderr:
            stderr.write((str(error) + "\n").encode())
        record.update(exit_code=None, error="launch or termination failed",
                      termination="unverified")
    output.with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n")
    route["commands"][label] = record
    return record.get("exit_code") == 0 and "error" not in record, stdout_path, stderr_path

def require(label, argv, timeout=300):
    passed, stdout, stderr = execute(label, argv, timeout)
    if not passed:
        raise RuntimeError(label + " failed; see retained command output")
    return stdout.read_bytes() + stderr.read_bytes() if label.startswith("setup/") else b""

try:
    actual_sha = require("setup/checkout", ["git", "rev-parse", "HEAD"]).decode().strip()
    if actual_sha != sha:
        raise RuntimeError("checkout differs from GITHUB_SHA")
    selected_runner = (root / "tools/performance/sustained_portable/native_hosted_short_runner.py").resolve()
    if Path(__file__).resolve() != selected_runner:
        raise RuntimeError("hosted runner differs from checked-out workspace")
    if require("setup/status", ["git", "status", "--porcelain", "--untracked-files=all"]).strip():
        raise RuntimeError("checkout is not clean")
    host = platform.system()
    machine = platform.machine().lower()
    expected = {"macosArm64": ("Darwin", "arm64"),
                "mingwX64": ("Windows", "amd64")}
    if (host, machine) != expected[target]:
        raise RuntimeError(f"selected target and host differ: {target}, {host}, {machine}")
    java = require("setup/java", ["java", "-version"]).decode(errors="replace")
    if not re.search(r'\bversion "21(?:\.|\")', java):
        raise RuntimeError("selected JDK is not 21")
    wrapper = root / ("gradlew.bat" if host == "Windows" else "gradlew")
    gradle = require("setup/gradle", [wrapper, "--version"]).decode(errors="replace")
    if [line for line in gradle.splitlines() if line.startswith("Gradle ")] != ["Gradle 9.5.0"]:
        raise RuntimeError("selected Gradle is not 9.5.0")
    require("setup/python", [sys.executable, "--version"])
    if host == "Darwin":
        if not Path(os.environ["DEVELOPER_DIR"]).is_dir():
            raise RuntimeError("selected Xcode directory is missing")
        xcode = require("setup/xcode", ["xcodebuild", "-version"]).decode(errors="replace")
        if "Xcode 26.4.1" not in xcode.splitlines():
            raise RuntimeError("selected Xcode is not 26.4.1")

    staging = (root / "build/staging-repository").resolve()
    stage_root = staging / ".qualification/native-host-short"
    stage_receipt = stage_root / "receipt.json"
    stage_log = stage_root / "stage.log"
    require("stage/command", [sys.executable, "-B", root / "tools/qualification/stage.py",
                              "--candidate-sha", sha, "--target", target,
                              "--output", stage_receipt, "--console", stage_log], 2400)
    repository_uri = staging.as_uri()
    require("build/consumer", [wrapper, "-p", root / "consumers/performance/portable",
                               "--no-daemon", "--console=plain", "--rerun-tasks",
                               f"-PperformanceRepository={repository_uri}",
                               f"-PportableNativeHostTarget={target}",
                               f"-PportableNativeHostBuild={build}",
                               "portableNativeHostBuildInventory"], 2400)
    inventory = (root / "consumers/performance/portable/build/portable-inventory" /
                 f"{target}-{build}.json").resolve()
    selected = json.loads(inventory.read_text())
    if (selected.get("source_sha"), selected.get("target"), selected.get("build"),
        selected.get("gradle"), selected.get("kgp")) != (sha, target, build, "9.5.0", "2.4.20"):
        raise RuntimeError("consumer inventory identity differs from dispatch")
    harness = Path(selected["harness"])
    if not harness.is_absolute() or not harness.is_file():
        raise RuntimeError("selected executable is missing")
    (evidence / "build").mkdir(exist_ok=True)
    shutil.copy2(inventory, evidence / "build/inventory.json")
    (evidence / "build/selected.json").write_text(json.dumps({
        "source_sha": sha, "target": target, "build": build,
        "harness": str(harness), "bundle_sha256": selected["bundle_sha256"],
        "resolved_artifacts": selected["resolved_artifacts"],
        "staging_repository": str(staging), "staging_uri": repository_uri,
    }, indent=2) + "\n")

    image_control, _, _ = execute("setup/path-swap-command", path_swap_command(
        root, evidence / "setup/path-swap.json", target, selected, sha), 45)
    route["path_swap_control_passed"] = image_control
    for api in ("direct_kotlin", "compatibility"):
        for mode in ("timing", "memory"):
            base = evidence / "captures" / ("memory" if mode == "memory" else "")
            archive = (base / api).resolve()
            label = f"captures/{'memory/' if mode == 'memory' else ''}{api}-command"
            passed, _, _ = execute(label, [sys.executable, "-B",
                root / "tools/performance/sustained_portable/native_host_capture.py",
                "--inventory", inventory, "--publication-root", staging,
                "--target", target, "--build", build,
                "--scenario", f"separated.default.small.30hz.{api}",
                "--mode", mode, "--archive", archive,
                "--steps", "30", "--warmup", "3"], 120)
            receipt = archive / "capture.json"
            result = {"exit_zero": passed, "capture_receipt": receipt.is_file(),
                      "archive": str(archive.relative_to(evidence))}
            if mode == "memory":
                result["status"] = "failed"
                result["sidecars"] = {
                    name: (archive / name).is_file() for name in
                    ("capture.json", "execution.json", "run.json",
                     "stdout.raw", "stderr.raw", "rss.json", "rss.csv", "heap.csv")}
                try:
                    capture = json.loads(sidecar_bytes(receipt))
                    execution = json.loads(sidecar_bytes(archive / "execution.json"))
                    resident = json.loads(sidecar_bytes(archive / "rss.json"))
                    run = json.loads(sidecar_bytes(archive / "run.json"))
                    result.update(pid=execution["pid"],
                                  process_image_identity=capture["process_image_identity"],
                                  observed_image=capture["observed_image"],
                                  rss_observation=capture["rss_observation"],
                                  managed_heap_observation=capture["managed_heap_observation"])
                    if passed:
                        checked = {name: raw_file(archive / name) for name in
                                   ("execution.json", "stdout.raw", "stderr.raw",
                                    "rss.json", "rss.csv", "heap.csv")}
                        if (any("sha256" not in item for item in checked.values()) or
                            checked["execution.json"]["sha256"] != capture["execution_sha256"] or
                            checked["stdout.raw"]["sha256"] != execution["stdout_sha256"] or
                            checked["stderr.raw"]["sha256"] != execution["stderr_sha256"] or
                            checked["rss.json"]["sha256"] !=
                                capture["rss_observation"]["rss_json_sha256"] or
                            checked["heap.csv"]["sha256"] !=
                                capture["managed_heap_observation"]["heap_csv_sha256"]):
                            raise ValueError("Native memory sidecar bytes differ from receipts")
                        rss_csv = sidecar_bytes(archive / "rss.csv").decode().splitlines()
                        if rss_csv != (["monotonic_ns,resident_bytes"] +
                                       [f"{stamp},{resident_bytes}" for stamp, resident_bytes
                                        in resident["samples"]]):
                            raise ValueError("Native resident CSV differs from sampled bytes")
                        if (capture["mode"] != "memory" or run["mode"] != "memory" or
                            capture["source_sha"] != sha or capture["target"] != target or
                            capture["build"] != build or capture["scenario"]["api"] != api or
                            any(type(pid) is not int or pid <= 0 for pid in
                                (execution["pid"], capture["pid"], resident["pid"])) or
                            execution["pid"] != capture["pid"] or resident["pid"] != execution["pid"] or
                            capture["process_image_identity"] != "observed" or
                            execution["raw_collection"] != "selected_process_exited" or
                            execution["termination"] != "natural" or execution["exit_code"] != 0 or
                            capture["managed_heap_observation"]["status"] !=
                                "observed_kotlin_heap_after_collection" or
                            capture["managed_heap_observation"]["stages"] != 3 or
                            run["qualification"] != "unpassed" or
                            any(not (archive / name).is_file() for name in
                                ("stdout.raw", "stderr.raw", "rss.csv", "heap.csv"))):
                            raise ValueError("Native memory receipt or sidecar identity differs")
                        result["status"] = (
                            "observed_diagnostic" if
                            capture["rss_observation"]["status"] == "observed_diagnostic" and
                            resident["status"] == "observed_diagnostic" and
                            capture["rss_observation"]["samples"] == len(resident["samples"]) and
                            len(resident["samples"]) > 0 and
                            resident_probe_errors_complete(resident, capture, execution, target)
                            else "unavailable_or_partial")
                        if result["status"] == "observed_diagnostic" and resident["errors"]:
                            result["terminal_rss_probe"] = resident["errors"][0]
                except (OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
                    result["error"] = str(error)
                route["memory_scenarios"][api] = result
            else:
                route["scenarios"][api] = result
            if not passed or (mode == "memory" and result["status"] != "observed_diagnostic"):
                raw = {}
                for name in ("stdout.raw", "stderr.raw"):
                    path = archive / name
                    try:
                        raw[name] = raw_file(path)
                    except OSError as error:
                        raw[name] = {"status": "unreadable", "error": str(error)}
                try:
                    execution_receipt = json.loads(
                        sidecar_bytes(archive / "execution.json"))
                    raw_collection = (execution_receipt.get("raw_collection", "incomplete")
                                      if isinstance(execution_receipt, dict) else "incomplete")
                except (OSError, ValueError, UnicodeError):
                    raw_collection = "incomplete"
                if (route["commands"][label].get("error") == "timeout" or
                        any("sha256" not in item for item in raw.values())):
                    raw_collection = "incomplete"
                failure = {"qualification": "unpassed", "source_sha": sha,
                           "target": target, "build": build, "scenario": api,
                           "mode": mode, "command": route["commands"][label], "raw": raw,
                           "raw_collection": raw_collection, "result": result}
                (base / f"{api}-failure.json").write_text(
                    json.dumps(failure, indent=2) + "\n")
    if (not image_control or
            not all(row["exit_zero"] for row in route["scenarios"].values()) or
            not all(row["status"] == "observed_diagnostic"
                    for row in route["memory_scenarios"].values())):
        raise RuntimeError("one or more Native host controls failed")
except (KeyError, ValueError, OSError, RuntimeError) as error:
    route["error"] = str(error)
finally:
    if "stage_receipt" in locals() and stage_receipt.is_file():
        (evidence / "stage").mkdir(exist_ok=True)
        shutil.copy2(stage_receipt, evidence / "stage/receipt.json")
    if "stage_log" in locals() and stage_log.is_file():
        (evidence / "stage").mkdir(exist_ok=True)
        shutil.copy2(stage_log, evidence / "stage/stage.log")
    (evidence / "route-result.json").write_text(json.dumps(route, indent=2) + "\n")
if "error" in route:
    sys.exit(1)
