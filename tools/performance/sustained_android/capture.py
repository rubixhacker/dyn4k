#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
import zipfile
from io import BytesIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PROJECT = ROOT / "consumers/performance/android-runtime"
MANIFEST = ROOT / "docs/research/performance-manifest-v1.json"
FIXTURE = ROOT / "consumers/performance/portable/src/commonMain/kotlin/performance/portable/Fixture.kt"
ANDROID_FIXTURE = PROJECT / "app/src/main/kotlin/performance/portable/Fixture.kt"
APP_ID = "io.github.rubixhacker.dyn4k.performance"
TEST_ID = APP_ID + ".test"
RUNNER = APP_ID + ".PerformanceInstrumentation"
EVIDENCE_AUTHORITY = APP_ID + ".evidence"
VERSION = "0.1.0-alpha.1"
STAGED = ("dyn4k-core-android", "dyn4k-android")
JDK = Path("/tmp/dyn4k-tools/jdk21")
GRADLE = Path("/tmp/dyn4k-tools/gradle-9.5.0/bin/gradle")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_archive(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    return path


def select_case(manifest, scenario, bodies=None):
    matches = [row for row in manifest["scenarios"] if row["id"] == scenario]
    if len(matches) != 1:
        raise ValueError("scenario is missing or duplicated in frozen manifest")
    row = matches[0]
    if row["api"] not in ("direct_kotlin", "compatibility") or row["size"] not in ("small", "medium"):
        raise ValueError("Android short process requires direct or compatibility, small or medium")
    if bodies is not None and row["dynamic_bodies"] != bodies:
        raise ValueError("dynamic body count differs from manifest")
    return row


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate_records(rows, scenario, source, nonce, api, abi, fingerprint,
                     steps, warmup, fixture, manifest, core, kotlin, build_type="debug",
                     provider_class="org.dyn4j.world.World"):
    case = select_case(json.loads(MANIFEST.read_text()), scenario)
    dynamic = case["dynamic_bodies"]
    family = case["family"]
    expected_bodies = dynamic + {"separated": 0, "pile": 1, "lifecycle": 1,
                                 "ccd": 2, "joint": dynamic}[family]
    expected_joints = (dynamic if family == "joint" else
                       (dynamic + 9) // 10 if family == "lifecycle" else 0)
    expected = {"nonce": nonce, "scenario": scenario, "source_commit": source,
                "build_type": build_type,
                "fixture_sha256": fixture, "manifest_sha256": manifest,
                "core_aar_sha256": core, "kotlin_aar_sha256": kotlin,
                "app_package": APP_ID, "test_package": TEST_ID,
                "evidence_authority": EVIDENCE_AUTHORITY,
                "provider_class": provider_class, "provider_loader_matches_target": True,
                "api_level": api,
                "abi": abi, "fingerprint": fingerprint}
    require(rows and all(isinstance(row, dict) and row.get("schema") == 1 for row in rows),
            "missing or invalid records")
    identity = rows[0]
    require(identity.get("type") == "identity" and
            all(identity.get(key) == value for key, value in expected.items()) and
            type(identity.get("pid")) is int and identity["pid"] > 0, "identity mismatch")
    cursor = 1

    def take(kind, phase=None, step=None):
        nonlocal cursor
        require(cursor < len(rows), "record order or missing record")
        row = rows[cursor]
        cursor += 1
        require(row.get("type") == kind and (phase is None or row.get("phase") == phase)
                and (step is None or row.get("step") == step), "record order or step mismatch")
        return row

    def clock(row, previous):
        begin, end = row.get("begin_ns"), row.get("end_ns")
        require(type(begin) is int and type(end) is int and begin > 0 and end > begin
                and begin > previous, "zero, invalid, or nonmonotonic clock")
        return end

    warm = take("construction", "warmup")
    require(warm.get("bodies") == expected_bodies and
            warm.get("joints") == expected_joints, "wrong fixture construction")
    previous = 0
    for step in range(warmup):
        previous = clock(take("clock", "warmup", step), previous)
    reset = take("reset")
    require(reset.get("after_warmup") == warmup and
            type(reset.get("warmup_world_id")) is int and
            type(reset.get("measure_world_id")) is int and
            reset["warmup_world_id"] != reset["measure_world_id"], "missing fixture reset")
    measured = take("construction", "measure")
    require(measured.get("bodies") == warm["bodies"] and
            measured.get("joints") == warm.get("joints"), "fixture reset changed construction")
    observed_active = 0
    for step in range(steps):
        tick = take("clock", "measure", step)
        previous = clock(tick, previous)
        sample = take("step", step=step)
        require(sample.get("begin_ns") == tick["begin_ns"] and
                sample.get("end_ns") == tick["end_ns"] and
                sample.get("duration_ns") == tick["end_ns"] - tick["begin_ns"] and
                type(sample.get("mutate_ns")) is int and 0 <= sample["mutate_ns"] <= sample["duration_ns"] and
                type(sample.get("late_ns")) is int and sample["late_ns"] >= 0 and
                sample.get("bodies") == expected_bodies and
                sample.get("joints") == expected_joints and
                type(sample.get("awake")) is int and 0 <= sample["awake"] <= measured["bodies"],
                "invalid step or clock")
        for key in ("linear_speed", "angular_speed"):
            value = sample.get(key)
            require(type(value) in (int, float) and value >= 0 and value < float("inf"),
                    "invalid activity")
        if sample["awake"] > 0:
            observed_active += 1
        if family == "separated":
            require(sample["awake"] == dynamic and
                    sample["linear_speed"] >= dynamic * 0.75 * 0.99,
                    "separated activity below source-defined velocity")
        for key in ("contact_begins", "contact_ends", "toi_events"):
            require(type(sample.get(key)) is int and sample[key] >= 0, "invalid event count")
        for key in ("broad_pairs", "contact_pairs", "contact_points"):
            expected_pair = step % (int(scenario.split(".")[-2][:-2])) == 0 or step == steps - 1
            require(type(sample.get(key)) is int and
                    (sample[key] >= 0 if expected_pair else sample[key] == -1), "invalid pair sample")
    run = take("run")
    require(cursor == len(rows) and run.get("steps") == steps and
            run.get("warmup_steps") == warmup and
            type(run.get("wall_ns")) is int and run["wall_ns"] > 0 and
            type(run.get("active_steps")) is int and run["active_steps"] == observed_active and
            run.get("qualification") == "unpassed", "invalid run summary")
    return identity["pid"]


def command(args, raw=None, check=True, env=None):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    if raw is not None:
        Path(raw).write_bytes(result.stdout)
    if check and result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {args[0]}")
    return result.stdout.decode("utf-8", "replace").strip()


def source_commit(expected):
    require(HEX40.fullmatch(expected) is not None, "source commit must be full SHA")
    actual = command(["git", "rev-parse", "HEAD"])
    require(actual == expected, "source commit mismatch")
    tracked = command(["git", "status", "--porcelain", "--untracked-files=normal"])
    require(not tracked, "source tree is dirty")
    return actual


def staged_paths(repository):
    paths = {}
    for name in STAGED:
        path = repository / "io/github/rubixhacker" / name / VERSION / f"{name}-{VERSION}.aar"
        require(path.is_file(), f"missing staged AAR: {path}")
        paths[name] = path
    return paths


def provider_name(mapping, build_type):
    if build_type == "debug":
        return "org.dyn4j.world.World"
    require(build_type == "release", "unknown build type")
    matches = re.findall(r"^org\.dyn4j\.world\.World -> ([^:]+):$",
                         Path(mapping).read_text(), re.MULTILINE)
    require(len(matches) == 1 and matches[0], "missing or ambiguous R8 World mapping")
    return matches[0]


def apk_has_class(apk, name):
    descriptor = ("L" + name.replace(".", "/") + ";").encode("ascii")
    with zipfile.ZipFile(apk) as archive:
        return any(descriptor in archive.read(entry) for entry in archive.namelist()
                   if re.fullmatch(r"classes[0-9]*\.dex", entry))


def contains_world_class(path):
    path = Path(path)
    if path.suffix not in (".jar", ".aar"):
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            if path.suffix == ".jar":
                return "org/dyn4j/world/World.class" in archive.namelist()
            for name in archive.namelist():
                if name == "classes.jar" or name.startswith("libs/") and name.endswith(".jar"):
                    with zipfile.ZipFile(BytesIO(archive.read(name))) as classes:
                        if "org/dyn4j/world/World.class" in classes.namelist():
                            return True
    except zipfile.BadZipFile as failure:
        raise ValueError(f"invalid resolved runtime artifact: {path}") from failure
    return False


def parse_dependency_graph(log, staged_hashes):
    graph = {scope: {"components": set(), "edges": [], "artifacts": []}
             for scope in ("app", "test")}
    for line in log.splitlines():
        match = re.fullmatch(r"DYN4K_GRAPH_(COMPONENT|EDGE|ARTIFACT) (app|test) (.+)", line)
        if not match:
            continue
        kind, scope, value = match.groups()
        group = graph[scope]
        if kind == "COMPONENT":
            group["components"].add(value)
        elif kind == "EDGE":
            parts = value.split(" ")
            require(len(parts) == 2, "invalid runtime dependency edge")
            group["edges"].append(tuple(parts))
        else:
            coordinate, path = value.split(" ", 1)
            path = str(Path(path).resolve(strict=True))
            group["artifacts"].append({"coordinate": coordinate, "path": path,
                                       "sha256": sha(path), "bytes": Path(path).stat().st_size,
                                       "contains_world": contains_world_class(path)})
    core = f"io.github.rubixhacker:dyn4k-core-android:{VERSION}"
    facade = f"io.github.rubixhacker:dyn4k-android:{VERSION}"
    providers = set()
    for scope, group in graph.items():
        components = group["components"]
        require("project:app" in components and group["edges"] and group["artifacts"],
                f"incomplete {scope} runtime graph")
        require(all(start in components and end in components for start, end in group["edges"]),
                f"unresolved {scope} runtime graph edge")
        require(all(item["coordinate"] in components for item in group["artifacts"]),
                f"unlisted {scope} runtime artifact")
        require(not any(item.startswith("org.dyn4j:dyn4j:") for item in components),
                "baseline provider in Android runtime graph")
        for item in group["artifacts"]:
            if item["contains_world"]:
                providers.add((item["coordinate"], item["sha256"]))
        group["components"] = sorted(components)
        group["edges"] = [list(edge) for edge in sorted(group["edges"])]
        group["artifacts"] = sorted(group["artifacts"], key=lambda item: (item["coordinate"], item["path"]))
    for name, coordinate in ((STAGED[0], core), (STAGED[1], facade)):
        matches = [item for item in graph["app"]["artifacts"] if item["coordinate"] == coordinate]
        require(len(matches) == 1 and matches[0]["sha256"] == staged_hashes[name],
                "resolved provider bytes do not match staged AAR inputs")
    require(providers == {(core, staged_hashes[STAGED[0]])},
            "missing or second World provider in runtime graph")
    return graph


def collect_instrumentation(instrument, archive, report, timeout, host_begin_ns):
    timed_out = False
    try:
        stdout, _ = instrument.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        instrument.kill()
        stdout, _ = instrument.communicate()
    host_end_ns = time.monotonic_ns()
    raw = archive / "instrumentation.raw"
    raw.write_bytes(stdout)
    report["raw"]["instrumentation"] = {"sha256": sha(raw), "bytes": len(stdout),
                                            "exit_code": instrument.returncode,
                                            "timed_out": timed_out}
    report["host_monotonic"] = {"begin_ns": host_begin_ns, "end_ns": host_end_ns}
    if timed_out:
        raise RuntimeError("instrumentation timeout")
    return stdout.decode("utf-8", "replace")


def build(args):
    source_commit(args.source_commit)
    output = Path(args.receipt).resolve()
    build_log = output.with_suffix(output.suffix + ".gradle.log")
    if output.exists() or build_log.exists():
        raise FileExistsError(output if output.exists() else build_log)
    output.parent.mkdir(parents=True, exist_ok=True)
    require(sha(FIXTURE) == sha(ANDROID_FIXTURE), "Android fixture differs from frozen portable fixture")
    repository = Path(args.staging_repository).resolve(strict=True)
    staged = staged_paths(repository)
    hashes = {name: sha(path) for name, path in staged.items()}
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.mkdir(exist_ok=False)
    env = dict(os.environ, JAVA_HOME=str(JDK), ANDROID_HOME=str(args.android_home),
               TMPDIR=str(temporary))
    require((JDK / "bin/java").is_file() and GRADLE.is_file(), "pinned JDK or Gradle missing")
    require(args.build_type in ("debug", "release"), "build type must be debug or release")
    java = command([str(JDK / "bin/java"), "-version"], env=env)
    require('version "21.' in java, "wrong JDK")
    gradle = command([str(GRADLE), "--version", "--offline"], env=env)
    require("Gradle 9.5" in gradle, "wrong Gradle")
    gradle_jvm_args = f"-Xmx2g -XX:MaxMetaspaceSize=2g -Djava.io.tmpdir={temporary}"
    variant = args.build_type.capitalize()
    log = command([str(GRADLE), "-p", str(PROJECT), ":app:providerArtifacts",
                   f":app:assemble{variant}", f":app:assemble{variant}AndroidTest",
                   "--offline", "--no-daemon", "--max-workers=2", "--console=plain",
                   f"-Dorg.gradle.jvmargs={gradle_jvm_args}",
                   f"-PstagingRepository={repository}",
                   f"-PperformanceTestBuildType={args.build_type}"], build_log, env=env)
    graph = parse_dependency_graph(log, hashes)
    providers = {name: next(item for item in graph["app"]["artifacts"]
                            if item["coordinate"] == f"io.github.rubixhacker:{name}:{VERSION}")
                 for name in STAGED}
    require({name: sha(path) for name, path in staged.items()} == hashes, "staged AAR changed during build")
    app = PROJECT / f"app/build/outputs/apk/{args.build_type}/app-{args.build_type}.apk"
    test = PROJECT / f"app/build/outputs/apk/androidTest/{args.build_type}/app-{args.build_type}-androidTest.apk"
    require(app.is_file() and test.is_file(), "missing built APK pair")
    mapping = PROJECT / "app/build/outputs/mapping/release/mapping.txt"
    runtime_name = provider_name(mapping, args.build_type)
    require(apk_has_class(app, runtime_name) and apk_has_class(test, runtime_name),
            "built APK pair lacks mapped World provider")
    receipt = {"schema": 1, "source_commit": args.source_commit, "build_type": args.build_type,
               "manifest_sha256": sha(MANIFEST), "fixture_sha256": sha(FIXTURE),
               "staging_repository": str(repository),
               "staged_aars": {name: {"path": str(path), "sha256": hashes[name]} for name, path in staged.items()},
               "resolved_aars": {name: {"path": providers[name]["path"], "sha256": providers[name]["sha256"]}
                                 for name in STAGED},
               "runtime_graph": graph,
               "provider_runtime_name": runtime_name,
               "r8_mapping": ({"path": str(mapping), "sha256": sha(mapping)}
                              if args.build_type == "release" else None),
               "app_apk": {"path": str(app), "sha256": sha(app)},
               "test_apk": {"path": str(test), "sha256": sha(test)},
               "build_log": {"path": str(build_log), "sha256": sha(build_log)},
               "gradle_jvm_args": gradle_jvm_args, "temporary_directory": str(temporary),
               "jdk": java, "gradle": "9.5.0",
               "qualification": "unpassed"}
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(output)


def capture(args):
    receipt = json.loads(Path(args.receipt).read_text())
    source_commit(receipt["source_commit"])
    manifest = json.loads(MANIFEST.read_text())
    case = select_case(manifest, args.scenario)
    require(args.api in (21, 37), "approved guest API must be 21 or 37")
    require(0 <= args.warmup_steps <= 600 * case["rate_hz"] and
            1 <= args.steps <= 5 * case["rate_hz"], "short process step bounds")
    require(sha(MANIFEST) == receipt["manifest_sha256"] and
            sha(FIXTURE) == receipt["fixture_sha256"] and
            sha(ANDROID_FIXTURE) == receipt["fixture_sha256"], "manifest or fixture changed")
    require(receipt["build_type"] in ("debug", "release"), "invalid build type")
    for name, item in receipt["staged_aars"].items():
        require(name in STAGED and sha(item["path"]) == item["sha256"], "staged AAR substituted")
    require(set(receipt["staged_aars"]) == set(STAGED), "missing staged AAR")
    hashes = {name: receipt["staged_aars"][name]["sha256"] for name in STAGED}
    require(sha(receipt["build_log"]["path"]) == receipt["build_log"]["sha256"],
            "build log substituted")
    require(parse_dependency_graph(Path(receipt["build_log"]["path"]).read_text(), hashes) ==
            receipt["runtime_graph"], "runtime graph substituted")
    require(set(receipt["resolved_aars"]) == set(STAGED) and
            all(sha(receipt["resolved_aars"][name]["path"]) ==
                receipt["staged_aars"][name]["sha256"] for name in STAGED),
            "resolved AAR substituted")
    for key in ("app_apk", "test_apk"):
        require(sha(receipt[key]["path"]) == receipt[key]["sha256"], "built APK substituted")
    mapping = receipt["r8_mapping"]
    require((mapping is None if receipt["build_type"] == "debug" else
             mapping is not None and sha(mapping["path"]) == mapping["sha256"]),
            "R8 mapping substituted")
    require(provider_name(mapping["path"] if mapping else None, receipt["build_type"]) ==
            receipt["provider_runtime_name"], "mapped provider changed")
    require(all(apk_has_class(receipt[key]["path"], receipt["provider_runtime_name"])
                for key in ("app_apk", "test_apk")), "APK lacks mapped World provider")
    archive = create_archive(args.archive)
    nonce = uuid.uuid4().hex
    adb = [args.adb, "-P", str(args.adb_port), "-s", args.serial]
    report = {"schema": 1, "capture_nonce": nonce, "case": case,
              "build_receipt": receipt, "serial": args.serial,
              "budget_metadata": {
                  "absolute_p99_seconds": manifest["budgets"]["absolute_p99_seconds"][str(case["rate_hz"])],
                  "incremental_peak_mib": manifest["budgets"]["incremental_peak_mib"][case["size"]],
                  "shim_vs_direct": manifest["budgets"]["shim_vs_direct"],
                  "jvm_baseline_comparison": "JVM only; not applicable to this Android capture",
              }, "raw": {}, "qualification": "unpassed", "status": "incomplete"}

    def run(label, *arguments, check=True):
        path = archive / f"{label}.raw"
        result = subprocess.run(adb + list(arguments), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        path.write_bytes(result.stdout)
        report["raw"][label] = {"sha256": sha(path), "exit_code": result.returncode}
        if check and result.returncode:
            raise RuntimeError(f"adb {label} failed ({result.returncode})")
        return result.stdout.decode("utf-8", "replace").strip()

    try:
        require(re.fullmatch(r"emulator-[0-9]+", args.serial) is not None and
                args.serial != "emulator-5558", "a task-owned emulator serial is required")
        require(args.adb_port > 0 and args.adb_port != 5038, "shared ART ADB port is forbidden")
        state = run("state", "get-state")
        require(state == "device", "guest is not ready")
        observed_avd = run("avd", "emu", "avd", "name").splitlines()[0]
        require(args.avd_name.startswith("dyn4k-performance-") and observed_avd == args.avd_name,
                "guest AVD is not task owned")
        api = int(run("api", "shell", "getprop", "ro.build.version.sdk"))
        abi = run("abi", "shell", "getprop", "ro.product.cpu.abi")
        fingerprint = run("fingerprint", "shell", "getprop", "ro.build.fingerprint")
        require(api == args.api and abi and fingerprint, "wrong or unidentified guest")
        report["guest"] = {"api": api, "abi": abi, "fingerprint": fingerprint}
        for key, package in (("app", APP_ID), ("test", TEST_ID)):
            old = run(f"{key}-before", "shell", "pm", "path", package, check=False)
            if old.startswith("package:"):
                run(f"{key}-uninstall", "uninstall", package)
            run(f"{key}-install", "install", "-r", receipt[f"{key}_apk"]["path"])
            installed = run(f"{key}-path", "shell", "pm", "path", package)
            paths = [line.removeprefix("package:") for line in installed.splitlines() if line.startswith("package:")]
            require(len(paths) == 1, "installed package has unexpected APK split count")
            remote = archive / f"{key}-installed.apk"
            installed_bytes = subprocess.run(adb + ["exec-out", "cat", paths[0]],
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            remote.write_bytes(installed_bytes.stdout)
            (archive / f"{key}-installed.stderr.raw").write_bytes(installed_bytes.stderr)
            report["raw"][f"{key}-installed"] = {"sha256": sha(remote),
                                                    "exit_code": installed_bytes.returncode}
            require(installed_bytes.returncode == 0, "cannot read installed APK bytes")
            require(sha(remote) == receipt[f"{key}_apk"]["sha256"], "installed APK bytes differ")
        extras = {"scenario": args.scenario, "source_commit": receipt["source_commit"],
                  "build_type": receipt["build_type"],
                  "manifest_sha256": receipt["manifest_sha256"],
                  "fixture_sha256": receipt["fixture_sha256"],
                  "core_aar_sha256": receipt["staged_aars"][STAGED[0]]["sha256"],
                  "kotlin_aar_sha256": receipt["staged_aars"][STAGED[1]]["sha256"],
                  "nonce": nonce, "steps": str(args.steps), "warmup_steps": str(args.warmup_steps)}
        invoke = ["shell", "am", "instrument", "-w", "-r"]
        for key, value in extras.items():
            invoke += ["-e", key, value]
        invoke += [f"{TEST_ID}/{RUNNER}"]
        host_begin_ns = time.monotonic_ns()
        instrument = subprocess.Popen(adb + invoke, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        observed_pids = set()
        for attempt in range(40):
            if instrument.poll() is not None:
                break
            observed = run(f"pidof-{attempt}", "shell", "pidof", APP_ID, check=False)
            observed_pids.update(int(item) for item in observed.split() if item.isdecimal())
            if observed_pids:
                break
            time.sleep(0.05)
        timeout = args.warmup_steps / case["rate_hz"] + args.steps / case["rate_hz"] + 60
        result = collect_instrumentation(instrument, archive, report, timeout, host_begin_ns)
        raw = run("records", "exec-out", "content", "read", "--uri",
                  f"content://{EVIDENCE_AUTHORITY}/performance-{nonce}.jsonl", check=False)
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        require("FAILURES" not in result and "shortMsg=" not in result and rows,
                "instrumentation failed or produced no records")
        pid = validate_records(rows, args.scenario, receipt["source_commit"], nonce,
                               api, abi, fingerprint, args.steps, args.warmup_steps,
                               receipt["fixture_sha256"], receipt["manifest_sha256"],
                               receipt["staged_aars"][STAGED[0]]["sha256"],
                               receipt["staged_aars"][STAGED[1]]["sha256"],
                               receipt["build_type"], receipt["provider_runtime_name"])
        require(instrument.returncode == 0 and observed_pids == {pid},
                "instrumentation process ID differs from observed guest process")
        report["pid"] = pid
        report["observed_pids"] = sorted(observed_pids)
        report["status"] = "captured"
    except Exception as failure:
        report["error"] = repr(failure)
        raise
    finally:
        (archive / "receipt.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--source-commit", required=True)
    b.add_argument("--staging-repository", required=True)
    b.add_argument("--android-home", default=os.environ.get("ANDROID_HOME", "/var/home/stewart/Android/Sdk"))
    b.add_argument("--receipt", required=True)
    b.add_argument("--build-type", choices=("debug", "release"), default="debug")
    c = sub.add_parser("capture")
    c.add_argument("--receipt", required=True)
    c.add_argument("--archive", required=True)
    c.add_argument("--scenario", required=True)
    c.add_argument("--api", type=int, required=True)
    c.add_argument("--serial", required=True)
    c.add_argument("--avd-name", required=True)
    c.add_argument("--adb", default="adb")
    c.add_argument("--adb-port", type=int, default=5039)
    c.add_argument("--steps", type=int, default=120)
    c.add_argument("--warmup-steps", type=int, default=60)
    args = parser.parse_args()
    try:
        globals()[args.command](args)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as failure:
        print(f"ERROR: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
