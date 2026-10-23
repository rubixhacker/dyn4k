import argparse
import hashlib
import html
import io
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.parse
import zipfile
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from itertools import chain
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cases import declared_cases
from exact_consistency import audit_trace
from frozen_weld_pulley import KEYS as WELD_PULLEY_KEYS, compare_case as compare_weld_pulley
from physical import nominal_free, sleep_wake_rows
from prospective_compare import compare_host
from reference_diagnostic import diagnostic, portable_case_id
from receipt import Identity, Rejected, digest, records, seal, verify as verify_receipt


ROOT = Path(__file__).resolve().parents[3]
PORTABLE = Path(__file__).resolve().parent
STAGED = ROOT / "build/staging-repository/io/github/rubixhacker"
VERSION = "0.1.0-alpha.1"
BUILD_JDK = Path("/tmp/dyn4k-tools/jdk21")
HOST_TASKS = {
    "jvm": "jvmTest",
    "jvm8": "jvmTest",
    "android-host": "testAndroidHostTest",
    "linux-x64": "linuxX64Test",
    "node-js": "jsNodeTest",
    "node-wasm-js": "wasmJsNodeTest",
    "node-wasm-wasi": "wasmWasiNodeTest",
}
WASM_HOSTS = ("node-wasm-js", "node-wasm-wasi")
WASM_MODULE = "dyn4k-portable-numerical-consumer-test"
WASM_RUNNER = (f"import * as exports from '../kotlin/{WASM_MODULE}.mjs';\n"
               'if (typeof exports.startUnitTests !== "function") throw new Error("test entry is absent");\n'
               'exports.startUnitTests();\n').encode()
MATRIX_METHODS = (
    "geometryCollisionBoundaryAndScale",
    "freeMotionForcesDampingAndRestitution",
    "defaultContactsFrictionSleepAndWake",
    "configured30Repeat1", "configured30Repeat2",
    "configured60Repeat1", "configured60Repeat2",
    "configured120Repeat1", "configured120Repeat2",
    "everyJointWithInitialAndApplicableActiveModes",
    "independentJointBooleanModes",
    "independentJointNumericAndLimitModes",
    "baselineAngleNegativeRatioRemainsAnIsolatedPhysicalFailure",
    "continuousCollisionCasesAtFrozenRates",
    "longRunningFreeMotionInvariantScene",
)
MATRIX_METHOD_CASE_COUNTS = (75, 10, 3, 1, 1, 1, 1, 1, 1, 24, 102, 98, 1, 12, 1)


def method_case_ids(method):
    if method not in MATRIX_METHODS:
        raise Rejected(f"unknown numerical matrix method: {method}")
    index = MATRIX_METHODS.index(method)
    start = sum(MATRIX_METHOD_CASE_COUNTS[:index])
    end = start + MATRIX_METHOD_CASE_COUNTS[index]
    cases = declared_cases()
    if len(cases) != sum(MATRIX_METHOD_CASE_COUNTS):
        raise Rejected("method and declared case inventories differ")
    return [case["id"] for case in cases[start:end]]


STAGE_TASKS = (
    ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
    ":dyn4k-core:publishJvmPublicationToStagingRepository",
    ":dyn4k-core:publishAndroidPublicationToStagingRepository",
    ":dyn4k-core:publishLinuxX64PublicationToStagingRepository",
    ":dyn4k-core:publishJsPublicationToStagingRepository",
    ":dyn4k-core:publishWasmJsPublicationToStagingRepository",
    ":dyn4k-core:publishWasmWasiPublicationToStagingRepository",
)
ARTIFACT_NAME = {
    "jvm": ("jvm", "jar"),
    "jvm8": ("jvm", "jar"),
    "android-host": ("android", "aar"),
    "linux-x64": ("linuxx64", "klib"),
    "node-js": ("js", "klib"),
    "node-wasm-js": ("wasm-js", "klib"),
    "node-wasm-wasi": ("wasm-wasi", "klib"),
}
OTHER_LANES = (
    "android-device", "linux-arm64", "windows-x64", "macos-arm64", "ios-arm64",
    "ios-simulator-arm64", "ios-simulator-x64", "tvos-arm64", "tvos-simulator-arm64",
    "watchos-arm64", "watchos-device-arm64", "watchos-simulator-arm64",
    "android-native-arm32", "android-native-arm64", "android-native-x86", "android-native-x64",
)
CATALOG = ROOT / "tools/numerical/fixtures.json"
PROVENANCE_SCRIPT = PORTABLE / "provenance.gradle"
GENERATED_ROOTS = (
    b"", b"dyn4k/", b"dyn4k-core/", b"consumers/qualification/",
    b"consumers/qualification/portable/", b"tools/numerical/portable/",
    b"tools/numerical/portable/baseline/",
)
GENERATED_PREFIXES = tuple(root + directory + b"/" for root in GENERATED_ROOTS
                           for directory in (b"build", b".gradle", b".kotlin")) + (
                               b"tools/numerical/portable/__pycache__/",)
GENERATED_FILES = {b"tools/numerical/portable/kotlin-js-store/yarn.lock"}


def git(*args):
    return subprocess.run(("git", *args), cwd=ROOT, check=True, capture_output=True).stdout


def clean_identity():
    status = git("--no-replace-objects", "status", "--porcelain",
                 "--untracked-files=all").decode()
    dirty = status.splitlines()
    ignored = git("--no-replace-objects", "ls-files", "--others", "--ignored",
                  "--exclude-standard", "-z")
    dirty.extend("ignored " + os.fsdecode(path) for path in ignored.split(b"\0")
                 if path and path not in GENERATED_FILES
                 and not path.startswith(GENERATED_PREFIXES))
    if dirty:
        raise Rejected("source tree is dirty: " + ", ".join(dirty[:5]))
    return (git("--no-replace-objects", "rev-parse", "HEAD").decode().strip(),
            hashlib.sha256(git("--no-replace-objects", "-c", "core.autocrlf=false",
                               "archive", "--format=tar", "HEAD")).hexdigest())


def artifacts(host):
    paths = artifact_relative_paths(host)
    result = {role: STAGED / name for role, name in paths.items()}
    for path in result.values():
        if not path.is_file():
            raise Rejected(f"staged publication is absent: {path}")
    return result


def artifact_relative_paths(host):
    suffix, extension = ARTIFACT_NAME[host]
    return {"target": f"dyn4k-core-{suffix}/{VERSION}/dyn4k-core-{suffix}-{VERSION}.{extension}",
            "metadata": f"dyn4k-core/{VERSION}/dyn4k-core-{VERSION}.jar"}


def stage(output, commit, source_sha256):
    started = __import__("time").time()
    env = controlled_java_environment()
    command = [str(ROOT / "gradlew"), *STAGE_TASKS, "--rerun-tasks", "--no-daemon",
               "--console=plain", "-Dorg.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=1g"]
    with (output / "publication.log").open("x", encoding="utf-8") as log:
        completed = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, check=False)
    if completed.returncode:
        raise Rejected("staged publication build failed; see publication.log")
    if clean_identity() != (commit, source_sha256):
        raise Rejected("source changed during staged publication build")
    files = {str(path.relative_to(STAGED)): path
             for host in HOST_TASKS for path in artifacts(host).values()}
    if any(path.stat().st_mtime < started for path in files.values()):
        raise Rejected("staged publication is older than this build")
    manifest = {"candidate_commit": commit, "source_sha256": source_sha256,
                "artifact_sha256": {name: digest(path) for name, path in files.items()},
                "publication_log_sha256": digest(output / "publication.log")}
    (output / "publication.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def controlled_java_environment():
    env = os.environ.copy()
    for key in ("OLLAMA_API_KEY", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS", "JAVA_TOOL_OPTIONS",
                "CLASSPATH", "JAVA_OPTS", "GRADLE_OPTS", "JDK_HOME", "JRE_HOME",
                "ANDROID_SDK_ROOT", "GRADLE_JAVA_HOME", "KOTLIN_JAVA_HOME"):
        env.pop(key, None)
    env["JAVA_HOME"] = str(BUILD_JDK)
    env["ANDROID_HOME"] = "/var/home/stewart/Android/Sdk"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _provider_classes(path):
    path = Path(path)
    if path.is_dir():
        return {str(item.relative_to(path)): item.read_bytes()
                for item in path.rglob("*.class")
                if str(item.relative_to(path)).startswith("org/dyn4j/")}
    if not path.is_file() or not zipfile.is_zipfile(path):
        return {}
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()
                if name.startswith("org/dyn4j/") and name.endswith(".class")}


def _java_classpath(command, host=None):
    tokens = []
    argfiles = []
    for token in command[1:]:
        if token.startswith("@"):
            if host == "jvm8":
                raise Rejected("Java 8 worker argument file is unsupported")
            path = Path(token[1:]).resolve()
            if not path.is_file():
                raise Rejected("executed Java worker argument file is absent")
            argfiles.append(path)
            tokens.extend(shlex.split(path.read_text()))
        else:
            tokens.append(token)
    classpaths = [tokens[index + 1] for index, token in enumerate(tokens[:-1])
                  if token in ("-cp", "-classpath", "--class-path")]
    if len(classpaths) != 1:
        raise Rejected("executed Java worker classpath is absent or ambiguous")
    return [Path(entry).resolve() for entry in classpaths[0].split(os.pathsep)], argfiles


def _loaded_java_classes(log_path, expected, dependency, direct_path):
    loaded = {}
    inspected = {}
    with Path(log_path).open(encoding="utf-8", errors="replace") as source:
        for line in source:
            old = re.search(r'\[Loaded (org\.dyn4j\.[^ ]+) from (file:[^\]]+)\]', line)
            modern = re.search(r'\[class,load\] (org\.dyn4j\.[^ ]+) source: (file:[^ ]+)', line)
            found = old or modern
            if found is None:
                continue
            name = found.group(1).replace(".", "/") + ".class"
            origin = Path(urllib.parse.unquote(urllib.parse.urlparse(
                found.group(2)).path)).resolve()
            if origin not in inspected:
                inspected[origin] = _provider_classes(origin)
            if name not in expected or inspected[origin].get(name) != expected[name]:
                raise Rejected("loaded Java provider differs from staged dependency")
            loaded[name] = str(origin)
    if "org/dyn4j/geometry/Vector2.class" not in loaded:
        raise Rejected("loaded staged dependency class proof is absent")
    if direct_path and dependency.resolve() not in {Path(path) for path in loaded.values()}:
        raise Rejected("loaded Java provider path omits staged dependency")
    return loaded


def _java_worker_open_proof(command, dependency, execution_log):
    if execution_log is None or not Path(execution_log).is_file():
        raise Rejected("Java 8 worker process trace is absent")
    workers = []
    children = {}
    opened = []
    pending_clones = {}
    with Path(execution_log).open(encoding="utf-8", errors="replace") as source:
        for line in source:
            launched = re.match(r'^(\d+) execve\("([^"]+)",.*GradleWorkerMain.*\) = 0$', line)
            if launched and Path(launched.group(2)).resolve() == Path(command[0]).resolve():
                workers.append(launched.group(1))
            unfinished = re.match(r'^(\d+) (clone3?)\(.*<unfinished \.\.\.>$', line)
            if unfinished:
                pending_clones[unfinished.group(1)] = unfinished.group(2)
            cloned = re.match(r'^(\d+) clone3?\(.*\) = (\d+)$', line)
            resumed = re.match(r'^(\d+) <\.\.\. (clone3?) resumed>.*\) = (\d+)$', line)
            if resumed and pending_clones.pop(resumed.group(1), None) == resumed.group(2):
                children.setdefault(resumed.group(1), set()).add(resumed.group(3))
            if cloned:
                children.setdefault(cloned.group(1), set()).add(cloned.group(2))
            jar = re.match(r'^(\d+) openat\([^,]+, "([^"]+)",.*\) = \d+$', line)
            if jar and "dyn4k-core" in jar.group(2):
                opened.append((jar.group(1), Path(jar.group(2)).resolve()))
    if len(workers) != 1:
        raise Rejected(f"expected one Java 8 worker process, found {len(workers)}")
    descendants = {workers[0]}
    pending = [workers[0]]
    while pending:
        for child in children.get(pending.pop(), ()):
            if child not in descendants:
                descendants.add(child)
                pending.append(child)
    worker_jars = [path for pid, path in opened if pid in descendants]
    if dependency.resolve() not in worker_jars or \
            any(path != dependency.resolve() for path in worker_jars):
        raise Rejected("Java 8 worker did not open only the staged dependency")
    return {"worker_pid": workers[0], "opened_artifact_sha256": digest(dependency),
            "execution_log_sha256": digest(execution_log)}


def _java_dependency_proof(host, command, dependency, log_path, proof_dir=None,
                           require_loaded=False, execution_log=None):
    entries, argfiles = _java_classpath(command, host)
    if not dependency.is_file():
        raise Rejected("staged dependency artifact is absent")
    if host == "android-host":
        with zipfile.ZipFile(dependency) as outer:
            staged = outer.read("classes.jar")
        with zipfile.ZipFile(io.BytesIO(staged)) as inner:
            expected = {name: inner.read(name) for name in inner.namelist()
                        if name.startswith("org/dyn4j/") and name.endswith(".class")}
    else:
        if host != "jvm8" and dependency.resolve() not in entries:
            raise Rejected("executed classpath omits staged dependency")
        expected = _provider_classes(dependency)
    if not expected or "org/dyn4j/geometry/Vector2.class" not in expected:
        raise Rejected("staged dependency provider classes are absent")
    providers = []
    for entry in entries:
        classes = _provider_classes(entry)
        if not classes:
            continue
        if any(expected.get(name) != value for name, value in classes.items()):
            raise Rejected("executed classpath provider differs from staged dependency")
        providers.append({"path": str(entry), "sha256": digest(entry) if entry.is_file() else
                          hashlib.sha256(b"".join(classes[name] for name in sorted(classes))).hexdigest(),
                          "classes": len(classes)})
    loaded = (_loaded_java_classes(log_path, expected, dependency,
                                   host != "android-host")
              if host == "jvm8" or proof_dir is not None or require_loaded else {})
    if not providers and not loaded:
        raise Rejected("executed classpath has no staged provider classes")
    archived = []
    if proof_dir is not None:
        proof_dir = Path(proof_dir)
        proof_dir.mkdir(parents=True, exist_ok=True)
        for index, path in enumerate(argfiles):
            target = proof_dir / f"worker-args-{index}.txt"
            shutil.copyfile(path, target)
            archived.append({"path": str(target), "sha256": digest(target)})
    result = {"classpath": [str(entry) for entry in entries], "providers": providers,
              "dependency_sha256": digest(dependency), "loaded_classes": loaded,
              "argument_files": archived}
    if host == "jvm8":
        result["worker_open"] = _java_worker_open_proof(command, dependency, execution_log)
    return result


def _native_cache_input(path):
    return (path.is_absolute() and len(path.parts) >= 9 and
            path.parts[-9:-5] == (".gradle", "caches", "modules-2", "files-2.1") and
            path.parts[-5:-2] == ("io.github.rubixhacker", "dyn4k-core-linuxx64", VERSION) and
            re.fullmatch(r"[0-9a-f]{40}", path.parts[-2]) is not None and
            path.name == f"dyn4k-core-linuxX64Main-{VERSION}.klib")


def _compiled_dependency_proof(host, log_path, dependency, input_files=None,
                               original_dependency=None):
    if not dependency.is_file():
        raise Rejected("staged dependency artifact is absent")
    expected_sha = digest(dependency)
    artifact_path = Path(original_dependency) if original_dependency is not None else dependency.resolve()
    required = {
        "linux-x64": (":compileKotlinLinuxX64", ":compileTestKotlinLinuxX64",
                      ":linkDebugTestLinuxX64"),
        "node-js": (":compileKotlinJs", ":compileTestKotlinJs",
                    ":compileTestDevelopmentExecutableKotlinJs"),
        "node-wasm-js": (":compileKotlinWasmJs", ":compileTestKotlinWasmJs",
                         ":compileTestDevelopmentExecutableKotlinWasmJs"),
        "node-wasm-wasi": (":compileKotlinWasmWasi", ":compileTestKotlinWasmWasi",
                           ":compileTestDevelopmentExecutableKotlinWasmWasi"),
    }[host]
    found = []
    with Path(log_path).open(encoding="utf-8", errors="replace") as source:
        for line in source:
            if not line.startswith("NUMERICAL_PROOF_INPUT "):
                continue
            item = json.loads(line.split(" ", 1)[1])
            if item["task"] not in required:
                continue
            path = Path(item["path"])
            if not path.is_absolute() or ".." in path.parts or str(path) != item["path"]:
                raise Rejected("executed compiler input path is unsafe")
            if input_files is None:
                path = path.resolve()
            if path != artifact_path and not (
                    _native_cache_input(path) if input_files is not None and
                    host == "linux-x64" else "io.github.rubixhacker" in path.parts and
                    any(part.startswith("dyn4k-core-") for part in path.parts)):
                raise Rejected("executed compiler input is outside staged publication resolution")
            source = input_files.get(str(path)) if input_files is not None else path
            if source is None or not source.is_file() or digest(source) != expected_sha or \
                    item["sha256"] != expected_sha or \
                    item["bytes"] != dependency.stat().st_size:
                raise Rejected("executed compiler input differs from staged dependency")
            found.append(item)
    if not set(required) <= {item["task"] for item in found}:
        raise Rejected("executed compiler staged dependency proof is incomplete")
    if host == "linux-x64" and [item["task"] for item in found] != list(required):
        raise Rejected("native compiler proof task sequence differs")
    if input_files is not None and set(input_files) != {item["path"] for item in found}:
        raise Rejected("retained compiler input set differs from execution")
    return {"artifact": str(artifact_path), "artifact_sha256": expected_sha,
            "tasks": found, "provenance_script_sha256": digest(PROVENANCE_SCRIPT)}


def _executed_node_bundle(host, execution_log, executable, payload_files=None):
    if execution_log is None or not Path(execution_log).is_file():
        raise Rejected("executed Node test process log is absent")
    marker = ("dyn4k-portable-numerical-consumer-test.js" if host == "node-js" else
              "runUnitTests.mjs")
    executed = []
    with Path(execution_log).open(encoding="utf-8", errors="replace") as source:
        for line in source:
            if "execve(" not in line or not line.rstrip().endswith("= 0") or \
                    marker not in line or "--dryRun" in line:
                continue
            if host == "node-js" and "--reporter" not in line:
                continue
            paths = re.findall(r'"([^"\n]+)"', line)
            if not paths or Path(paths[0]).resolve() != executable:
                continue
            matching = [Path(value).resolve() for value in paths[1:]
                        if value.endswith(marker)]
            if len(matching) != 1:
                raise Rejected("executed Node test bundle command is ambiguous")
            executed.append(matching[0])
    if len(executed) != 1:
        raise Rejected(f"expected one executed Node test worker, found {len(executed)}")
    bundle = executed[0]
    bundle_file = payload_files.get(str(bundle)) if payload_files is not None else bundle
    if bundle_file is None or not bundle_file.is_file():
        raise Rejected("executed Node test bundle is absent")
    payloads = [bundle]
    if host == "node-js":
        core = bundle.with_name("dyn4k-dyn4k-core.js")
        if "dyn4k-dyn4k-core.js" not in bundle_file.read_text():
            raise Rejected("executed Node bundle omits linked core module")
        payloads.append(core)
    else:
        module_name = "dyn4k-portable-numerical-consumer-test.mjs"
        candidates = (bundle.parent.parent / module_name,
                      bundle.parent.parent / "kotlin" / module_name)
        existing = [path for path in candidates if path.is_file()]
        if len(existing) != 1:
            raise Rejected("executed Wasm module is absent or ambiguous")
        module = existing[0]
        wasm = module.with_suffix(".wasm")
        if module.name not in bundle.read_text() or wasm.name not in module.read_text():
            raise Rejected("executed Wasm bundle omits linked module")
        payloads.extend((module, wasm))
    if any((payload_files.get(str(path)) if payload_files is not None else path) is None or
           not (payload_files.get(str(path)) if payload_files is not None else path).is_file()
           for path in payloads):
        raise Rejected("executed Node linked payload is absent")
    return {"command_bundle": str(bundle),
            "payload_sha256": {str(path): digest(payload_files[str(path)] if
                               payload_files is not None else path) for path in payloads},
            "process_executions": len(executed)}


def _java_version_line(probe):
    if probe.returncode:
        raise Rejected("Java version probe failed")
    build = r'[0-9]+(?:\.[0-9]+)*(?:_[0-9]+)?(?:[+-][0-9A-Za-z._-]+)?'
    vendor = r'(?: \([A-Za-z][A-Za-z0-9._-]*\)| [A-Za-z][A-Za-z0-9._-]*-[0-9][A-Za-z0-9.+_-]*)?'
    runtime_line = rf'(?:OpenJDK|Java\(TM\) SE) Runtime Environment{vendor}\s*\(build {build}\)'
    vm_line = (rf'(?:OpenJDK|Java HotSpot\(TM\)) (?:64-Bit|32-Bit) Server VM{vendor}'
               rf'\s*\(build {build}(?:, [A-Za-z][A-Za-z ,]*)?\)')
    versions = []
    for line in (probe.stdout + probe.stderr).splitlines():
        matched = re.fullmatch(r'(?:openjdk|java) version "\d+(?:\.\d+){2,3}(?:_\d+)?"'
                               r'(?: (?P<date>\d{4}-\d{2}-\d{2})(?: LTS)?)?', line)
        if matched:
            if matched.group("date"):
                try:
                    date.fromisoformat(matched.group("date"))
                except ValueError as error:
                    raise Rejected("malformed Java version date") from error
            versions.append(line)
        elif line.startswith(("openjdk version", "java version")):
            raise Rejected("malformed Java version line")
        elif not versions:
            if line.startswith("Picked up JAVA_TOOL_OPTIONS: ") or \
                    re.fullmatch(r'\[(?:Opened|Loaded) .+\]', line) or \
                    re.fullmatch(r'\[\d+(?:\.\d+)?s\]\[info\]\[class,load\] .+', line):
                continue
            raise Rejected("unexpected Java version preamble")
        elif not re.fullmatch(runtime_line, line) and not re.fullmatch(vm_line, line):
            raise Rejected("unexpected Java version output")
    if not versions:
        raise Rejected("Java version line is absent")
    if len(versions) != 1:
        raise Rejected("multiple Java version lines")
    return versions[0]


def runtime(host, log_path, execution_log=None, dependency=None, proof_dir=None,
            require_loaded=False, native_bundle=None, node_modules=None, node_bundle=None):
    if host in WASM_HOSTS:
        method = Path(log_path).stem.removeprefix("gradle-")
        lane = Path(log_path).parent
        runner = _bundle_file(lane, f"producer-bundle/{method}/static/runUnitTests.mjs")
        if method not in MATRIX_METHODS or execution_log is None or not runner.is_file() or \
                runner.read_bytes() != WASM_RUNNER:
            raise Rejected("direct Wasm method or runner identity differs")
        executed = []
        with Path(execution_log).open(encoding="utf-8", errors="replace") as source:
            for line in source:
                found = re.search(r'\bexecve\("([^"]+)", \[(.*?)\], .*\) = 0$', line)
                if found and "runUnitTests.mjs" in found.group(2):
                    executed.append((Path(found.group(1)).resolve(),
                                     re.findall(r'"([^"\n]*)"', found.group(2))))
        if len(executed) != 1:
            raise Rejected(f"expected one direct Wasm worker, found {len(executed)}")
        binary, arguments = executed[0]
        if len(arguments) != 4:
            raise Rejected("direct Wasm worker command differs")
        original_runner = _recorded_absolute_path(arguments[1])
        if len(original_runner.parents) < 4:
            raise Rejected("direct Wasm worker command differs")
        original_lane = original_runner.parents[3]
        if original_runner != original_lane / "producer-bundle" / method / \
                "static/runUnitTests.mjs":
            raise Rejected("direct Wasm worker command differs")
        command = wasm_command(method, binary, original_runner)
        if arguments != command or not binary.is_file():
            raise Rejected("direct Wasm worker command differs")
        source_hashes = {}
        payload_hashes = {}
        for name, source in wasm_payload_paths(host).items():
            archived = _bundle_file(lane, f"producer-bundle/{method}/kotlin/{name}")
            if not archived.is_file() or not source.is_file() or \
                    digest(archived) != digest(source):
                raise Rejected(f"direct Wasm linked payload differs: {name}")
            source_hashes[str(source)] = digest(source)
            payload_hashes[str(original_lane / "producer-bundle" / method / "kotlin" / name)] = \
                digest(archived)
        stream = lane / f"native-output-{method}.log"
        xml = lane / "xml" / f"{method}.xml"
        node_stream_xml(method, stream, xml)
        probe = subprocess.run((str(binary), "--version"), capture_output=True,
                               text=True, check=False)
        if probe.returncode or not probe.stdout.strip():
            raise Rejected("direct Wasm Node version probe failed")
        return {"host": host, "os": platform.platform(), "machine": platform.machine(),
                "device": False, "executable": str(binary),
                "executable_sha256": digest(binary), "version": probe.stdout.strip(),
                "process_executions": 1, "worker_command": command,
                "worker_command_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
                "build_log_sha256": digest(log_path),
                "execution_log_sha256": digest(execution_log),
                "native_output_sha256": digest(stream), "xml_sha256": digest(xml),
                "bundle": {"runner_sha256": digest(runner),
                           "payload_sha256": payload_hashes,
                           "compiler_output_sha256": source_hashes},
                "dependency": _compiled_dependency_proof(host, log_path, Path(dependency))}
    if host == "node-js" and node_modules is not None:
        method = Path(log_path).stem.removeprefix("gradle-")
        if method not in MATRIX_METHODS or execution_log is None:
            raise Rejected("direct Node method identity or process trace is absent")
        executed = []
        with Path(execution_log).open(encoding="utf-8", errors="replace") as source:
            for line in source:
                found = re.search(r'\bexecve\("([^"]+)", \[(.*?)\], .*\) = 0$', line)
                if found and "mocha.js" in found.group(2) and "--reporter" in found.group(2):
                    executed.append((Path(found.group(1)).resolve(),
                                     re.findall(r'"([^"\n]*)"', found.group(2))))
        if len(executed) != 1:
            raise Rejected(f"expected one direct Node worker, found {len(executed)}")
        executable, arguments = executed[0]
        retained = node_bundle["files"] if node_bundle is not None else None
        command = node_command(method, node_modules, executable,
                               node_bundle["original_bundle"] if node_bundle is not None else None)
        binary = node_bundle["binary"] if node_bundle is not None else executable
        if arguments != command or not binary.is_file():
            raise Rejected("direct Node worker command differs")
        stream = Path(log_path).parent / f"native-output-{method}.log"
        xml = Path(log_path).parent / "xml" / f"{method}.xml"
        node_stream_xml(method, stream, xml)
        bundle = _executed_node_bundle(host, execution_log, executable, retained)
        probe = subprocess.run((str(binary), "--version"), capture_output=True,
                               text=True, check=False)
        if probe.returncode or not probe.stdout.strip():
            raise Rejected("direct Node version probe failed")
        return {"host": host, "os": platform.platform(), "machine": platform.machine(),
                "device": False, "executable": str(executable),
                "executable_sha256": digest(binary), "version": probe.stdout.strip(),
                "process_executions": 1, "worker_command": command,
                "worker_command_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
                "build_log_sha256": digest(log_path),
                "execution_log_sha256": digest(execution_log),
                "native_output_sha256": digest(stream), "xml_sha256": digest(xml),
                "bundle": bundle,
                "runner_module_sha256": {command[index]: digest(retained[command[index]] if
                                         retained is not None else Path(command[index]))
                                         for index in (2, 3, 8, 10)},
                "dependency": _compiled_dependency_proof(host, log_path, Path(dependency),
                    input_files={node_bundle["original_artifact"]: Path(dependency)}
                    if node_bundle is not None else None,
                    original_dependency=node_bundle["original_artifact"]
                    if node_bundle is not None else None)}
    if host == "linux-x64":
        if native_bundle is None:
            binaries = list((PORTABLE / "build/bin/linuxX64").rglob("*.kexe"))
            if len(binaries) != 1:
                raise Rejected(f"expected one Linux x64 test binary, found {len(binaries)}")
            binary = binaries[0].resolve()
            binary_bytes = binary
            binary_mtime_ns = binary.stat().st_mtime_ns
            producer_platform = {"os": platform.platform(), "machine": platform.machine(),
                                 "version": platform.platform()}
        else:
            binary = Path(native_bundle["binary"]["original_path"])
            binary_bytes = native_bundle["binary_file"]
            binary_mtime_ns = native_bundle["binary"]["mtime_ns"]
            producer_platform = native_bundle["platform"]
            if digest(binary_bytes) != native_bundle["binary"]["sha256"]:
                raise Rejected("retained native executable differs")
        if execution_log is None or not Path(execution_log).is_file():
            raise Rejected("executed native test binary log is absent")
        executed = []
        with Path(execution_log).open(encoding="utf-8") as stream:
            for line in stream:
                found = re.search(r'\bexecve\("([^"]+\.kexe)", \[(.*?)\], .*\)\s+=\s+0$', line)
                if found:
                    executed.append((Path(found.group(1)).resolve() if native_bundle is None
                                     else Path(found.group(1)),
                                     re.findall(r'"([^"\n]*)"', found.group(2))))
        if len(executed) != 1:
            raise Rejected(f"expected one executed native test binary, found {len(executed)}")
        if executed[0][0] != binary:
            raise Rejected("executed native test binary does not match linked binary")
        method = Path(log_path).stem.removeprefix("gradle-")
        if method not in MATRIX_METHODS:
            raise Rejected("native method identity is absent")
        command = native_command(method, binary)
        if executed[0][1] != command:
            raise Rejected("executed native method command differs")
        build_started = None
        with Path(log_path).open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if line.startswith("NUMERICAL_BUILD_STARTED_NS "):
                    if build_started is not None:
                        raise Rejected("native build start is ambiguous")
                    build_started = int(line.split()[1])
        if build_started is None or binary_mtime_ns < build_started:
            raise Rejected("native test binary is stale")
        if dependency is None:
            raise Rejected("staged dependency proof is absent")
        lane = Path(log_path).parent
        stream = lane / f"native-output-{method}.log"
        xml = lane / "xml" / f"{method}.xml"
        native_stream_xml(method, stream, xml)
        return {"host": host, **producer_platform,
                "device": False, "executable": str(binary), "executable_sha256": digest(binary_bytes),
                "binary_mtime_ns": binary_mtime_ns,
                "process_executions": len(executed),
                "worker_command": command,
                "worker_command_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
                "build_log_sha256": digest(log_path),
                "execution_log_sha256": digest(execution_log),
                "native_output_sha256": digest(stream), "xml_sha256": digest(xml),
                "dependency": _compiled_dependency_proof(
                    host, log_path, Path(dependency),
                    native_bundle["input_files"] if native_bundle is not None else None,
                    native_bundle["target_original_path"] if native_bundle is not None else None)}
    needle = "Starting process 'command '" if host.startswith("node-") else "Starting process 'Gradle Test Executor"
    commands = []
    node_marker = ("dyn4k-portable-numerical-consumer-test.js" if host == "node-js"
                   else "runUnitTests.mjs")
    with Path(log_path).open(encoding="utf-8") as stream:
        for line in stream:
            if needle in line and " Command: " in line:
                candidate = shlex.split(line.rsplit(" Command: ", 1)[1])
                if candidate and (not host.startswith("node-") or
                                  (Path(candidate[0]).name == "node" and
                                   any(node_marker in argument for argument in candidate[1:]))):
                    commands.append(candidate)
    if not commands:
        raise Rejected(f"no executed test runtime command in Gradle log for {host}")
    if len(commands) != 1:
        raise Rejected(f"expected one test worker command for {host}, found {len(commands)}")
    resolved = Path(commands[0][0]).resolve()
    if not resolved.is_file():
        raise Rejected(f"executed runtime is missing: {resolved}")
    result = {"host": host, "os": platform.platform(), "machine": platform.machine(),
              "device": False, "executable": str(resolved), "executable_sha256": digest(resolved)}
    command = (str(resolved), "--version") if host.startswith("node-") else (str(resolved), "-version")
    probe = subprocess.run(command, capture_output=True, text=True, check=False)
    if host.startswith("node-"):
        result["version"] = ((probe.stdout + probe.stderr).strip().splitlines()[0]
                             if probe.stdout or probe.stderr else "UNAVAILABLE")
    else:
        result["version"] = _java_version_line(probe)
    if host == "jvm8" and 'version "1.8.' not in result["version"]:
        raise Rejected("JVM 8 lane did not execute on Java 8")
    if host in ("jvm", "android-host") and 'version "21.' not in result["version"]:
        raise Rejected(f"{host} lane did not execute on Java 21")
    if dependency is None:
        raise Rejected("staged dependency proof is absent")
    dependency = Path(dependency)
    if host.startswith("node-"):
        result["dependency"] = _compiled_dependency_proof(host, log_path, dependency)
        result["bundle"] = _executed_node_bundle(host, execution_log, resolved)
        result["process_executions"] = result["bundle"]["process_executions"]
        result["worker_command"] = commands[0]
        return result
    result["process_executions"] = len(commands)
    result["worker_command"] = commands[0]
    result["dependency"] = _java_dependency_proof(host, commands[0], dependency,
                                                   log_path, proof_dir,
                                                   require_loaded, execution_log)
    return result


def runtime_identity(row):
    return {key: value for key, value in row.items()
            if key not in ("worker_command", "worker_command_sha256", "dependency", "bundle",
                           "process_executions", "build_log_sha256", "execution_log_sha256",
                           "native_output_sha256", "xml_sha256", "binary_mtime_ns")}


def extract_xml(host, output, method=None, source=None):
    if source is None:
        directory = PORTABLE / "build/test-results" / HOST_TASKS[host]
        matching = sorted(directory.glob("TEST-*PortableMatrixTest*.xml"))
        if len(matching) != 1:
            raise Rejected(f"expected one matrix XML for {host}, found {len(matching)}")
        source = matching[0]
    with source.open("rb") as stream:
        stream.readline()
        suite = stream.readline().decode()
    attributes = dict(re.findall(r'([a-z]+)="([^"]*)"', suite))
    if method is None:
        shutil.copyfile(source, output / "matrix.xml")
    else:
        xml_dir = output / "xml"
        xml_dir.mkdir(exist_ok=True)
        archived = xml_dir / f"{method}.xml"
        if source.resolve() != archived.resolve():
            shutil.move(source, archived)
    trace = output / "trace.jsonl"
    cases = output / "cases"
    cases.mkdir(exist_ok=True)
    expected = {item["id"] for item in declared_cases()}
    observed = {}
    input_records = 0
    method_order = method_case_ids(method) if method is not None else None
    case_stream = None
    active_case = None
    archived = output / "xml" / f"{method}.xml" if method is not None else source
    with archived.open("r", encoding="utf-8") as stream, trace.open(
            "a" if method is not None and trace.exists() else "x", encoding="utf-8") as target:
        try:
            for line in stream:
                if "NUMERICAL_JSON " not in line:
                    continue
                payload = line.split("NUMERICAL_JSON ", 1)[1].split("]]>", 1)[0].rstrip("\r\n")
                row = json.loads(payload, parse_constant=lambda value: (_ for _ in ()).throw(Rejected(value)))
                target.write(payload + "\n")
                case_id = row.get("id")
                if row.get("kind") == "inputs":
                    if method_order is not None and (input_records >= len(method_order) or
                            row.get("id") != method_order[input_records]):
                        raise Rejected(f"numerical method case order differs: {method}")
                    input_records += 1
                if case_id in expected:
                    count = observed.setdefault(case_id, {"inputs": 0, "states": 0,
                                                           "events": 0, "endpoints": 0,
                                                           "case_ends": 0, "tagged_nonfinite_values": 0})
                    kind = row.get("kind")
                    field = {"inputs": "inputs", "state": "states", "event": "events",
                             "endpoint": "endpoints", "case-end": "case_ends"}.get(kind)
                    if field is not None:
                        count[field] += 1
                    count["tagged_nonfinite_values"] += payload.count('"nonfinite":')
                if row.get("kind") == "inputs":
                    if case_stream is not None:
                        case_stream.close()
                    active_case = row.get("id")
                    case_stream = ((cases / f"{active_case}.jsonl").open("x", encoding="utf-8")
                                   if active_case in expected else None)
                if case_stream is not None and row.get("id") == active_case:
                    case_stream.write(payload + "\n")
                    if row.get("kind") == "case-end":
                        case_stream.close()
                        case_stream = None
                        active_case = None
        finally:
            if case_stream is not None:
                case_stream.close()
    if method_order is not None and input_records != len(method_order):
        raise Rejected(f"numerical method case order is incomplete: {method}")
    raw_counts = {"expected_cases": len(expected), "input_records": input_records,
                  "observed_cases": len(observed),
                  "completed_cases": sum(item["case_ends"] == 1 for item in observed.values()),
                  "states": sum(item["states"] for item in observed.values()),
                  "tagged_nonfinite_values": sum(item["tagged_nonfinite_values"] for item in observed.values()),
                  "per_case": observed}
    return trace, attributes, raw_counts


def absent_lane(output, name, commit, source_sha256, status, reason):
    lane = output / name
    lane.mkdir(parents=True, exist_ok=False)
    result = {"host": name, "status": status, "reason": reason,
              "candidate_commit": commit, "source_sha256": source_sha256,
              "expected_cases": len(declared_cases()), "executed_cases": 0,
              "skipped": 0, "qualification": "UNPASSED"}
    (lane / "receipt.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def other_lane_status(name):
    if name == "android-device":
        return "NOT_RUN", "This consumer executed Android host tests only"
    if name == "android-native-x64":
        return "NOT_RUN", "This consumer has no Android Native x64 task; the separate ELF harness is available"
    return "UNAVAILABLE", "Target runtime is not available to this consumer on this Bazzite host"


def _compare_frozen_one(job):
    key, source, candidate, baseline_root, candidate_cases, baseline_attestation = job
    try:
        if not candidate.is_file():
            raise Rejected("matching portable case trace is absent")
        if key in WELD_PULLEY_KEYS:
            predecessors = {
                "pulley-preparation-1": "pulley-preparation-0",
                "pulley-slack-transition": "pulley-preparation-1"}
            producer = (baseline_root / "baseline-jvm/cases" /
                        f"{portable_case_id(key)}.jsonl" if baseline_root else None)
            prior_key = predecessors.get(key)
            prior_producer = (baseline_root / "baseline-jvm/cases" /
                              f"{portable_case_id(prior_key)}.jsonl"
                              if baseline_root and prior_key else None)
            prior_candidate = (candidate_cases / f"{portable_case_id(prior_key)}.jsonl"
                               if prior_key else None)
            if producer is not None and not producer.is_file():
                producer = None
            if prior_producer is not None and not prior_producer.is_file():
                prior_producer = None
            if prior_candidate is not None and not prior_candidate.is_file():
                prior_candidate = None
            return compare_weld_pulley(key, source, candidate,
                                       previous_reference=prior_producer,
                                       previous_candidate=prior_candidate,
                                       reference_producer=producer,
                                       baseline_root=baseline_root,
                                       baseline_attestation=baseline_attestation)
        return diagnostic(key, source, candidate)
    except (Rejected, OSError, EOFError, StopIteration, KeyError, TypeError, ValueError) as error:
        return {"fixture_key": key, "status": "FAILED",
                "reason": str(error), "qualification": "UNPASSED"}


def comparison_coverage():
    declared = {case["id"] for case in declared_cases()}
    catalog = json.loads(CATALOG.read_text())
    mapped = {portable_case_id(fixture["key"]) for fixture in catalog["fixtures"]}
    if not mapped <= declared:
        raise Rejected(f"frozen mapping has undeclared portable cases: {sorted(mapped - declared)}")
    unreferenced = sorted(declared - mapped)
    return {"status": "UNPASSED_REFERENCE_COVERAGE" if unreferenced else
            "COMPLETE_FROZEN_REFERENCE_COVERAGE",
            "declared_cases": len(declared), "frozen_reference_cases": len(mapped),
            "frozen_case_ids": sorted(mapped),
            "unreferenced_cases": len(unreferenced),
            "unreferenced_case_ids": unreferenced,
            "qualification": "UNPASSED"}


def compare_frozen(lane, reference_dirs, baseline_root=None, baseline_attestation=None):
    catalog = json.loads(CATALOG.read_text())
    resolved = []
    jobs = []
    for fixture in catalog["fixtures"]:
        key = fixture["key"]
        filename = fixture["reference"]["file"]
        source = next((directory / filename for directory in reference_dirs
                       if (directory / filename).is_file()), None)
        if source is None:
            resolved.append({"fixture_key": key, "status": "UNAVAILABLE_REFERENCE",
                             "expected_reference_sha256": fixture["reference"]["gzip_sha256"],
                             "qualification": "UNPASSED"})
        else:
            jobs.append((key, source, lane / "cases" / f"{portable_case_id(key)}.jsonl",
                         baseline_root, lane / "cases", baseline_attestation))
            resolved.append(None)
    if jobs:
        with ProcessPoolExecutor(max_workers=min(4, len(jobs))) as pool:
            compared = iter(pool.map(_compare_frozen_one, jobs))
            results = [entry if entry is not None else next(compared) for entry in resolved]
    else:
        results = resolved
    (lane / "frozen-comparison.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    return results


def _audit_exact_one(job):
    trace, case_id, outer_hz, configured = job
    return audit_trace(trace, case_id, outer_hz, configured)


def check_exact_consistency(lane):
    jobs = [(lane / "cases" / f"contacts-default-{hz}.jsonl",
             f"S-sleep-wake-hz{hz}", hz, False) for hz in (30, 60, 120)]
    jobs += [(lane / "cases" / f"contacts-configured-{hz}-r{repetition}.jsonl",
              f"Q-sleep-wake-outer{hz}-repeat{repetition}", hz, True)
             for hz in (30, 60, 120) for repetition in (1, 2)]
    with ProcessPoolExecutor(max_workers=4) as pool:
        cases = list(pool.map(_audit_exact_one, jobs))
    result = {"status": "PASSED" if all(item["status"] == "PASSED" for item in cases)
              else "FAILED", "cases": cases, "qualification": "UNPASSED",
              "semantic_source_revision": "44dd7cf05502fa4b5fdc3523e3271c3cba335de8"}
    (lane / "exact-consistency.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def selected_jdk8_home(home):
    if home is None:
        raise Rejected("explicit Java 8 home is required")
    path = Path(home)
    if (not path.is_absolute() or path.resolve() != path or not path.is_dir() or
            not (path / "bin/java").is_file() or not (path / "bin/javac").is_file()):
        raise Rejected("explicit Java 8 home must be a real JDK directory")
    version = subprocess.run([str(path / "bin/java"), "-version"], capture_output=True,
                             text=True, timeout=10, check=False,
                             env=controlled_java_environment())
    if version.returncode or 'version "1.8.' not in _java_version_line(version):
        raise Rejected("explicit Java 8 home has the wrong runtime")
    return path


def method_command(host, method, lane, jdk8_home=None, trace_jvm8=True):
    if method not in MATRIX_METHODS:
        raise Rejected(f"unknown numerical matrix method: {method}")
    task = (":linkDebugTestLinuxX64" if host == "linux-x64" else
            ":jsTestTestDevelopmentExecutableCompileSync" if host == "node-js" else
            ":wasmJsTestTestDevelopmentExecutableCompileSync" if host == "node-wasm-js" else
            ":compileTestDevelopmentExecutableKotlinWasmWasi" if host == "node-wasm-wasi" else
            HOST_TASKS[host])
    command = [str(ROOT / "gradlew"), "-p", str(PORTABLE), task]
    if host not in ("linux-x64", "node-js", *WASM_HOSTS):
        command.extend(("--tests", f"portable.PortableMatrixTest.{method}"))
    command.extend((
               f"-PportableRepository={ROOT / 'build/staging-repository'}",
               "--rerun-tasks", "--no-daemon", "--console=plain", "--info",
               "-Dorg.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=1g",
               "--init-script", str(PROVENANCE_SCRIPT)))
    if host == "jvm8":
        jdk8_home = selected_jdk8_home(jdk8_home)
        command.extend(("-PportableJvm8=true",
                        "-Dorg.gradle.java.installations.paths=" + str(jdk8_home)))
    execution_log = None
    if host == "linux-x64" or host in WASM_HOSTS:
        command.append("-Pkotlin.compiler.execution.strategy=in-process")
    if host == "jvm8" and trace_jvm8:
        tracer = shutil.which("strace")
        if tracer is None:
            raise Rejected("strace is unavailable for native process binding")
        execution_log = lane / f"native-exec-{method}.log"
        calls = "trace=process,openat" if host == "jvm8" else "trace=execve"
        command.append("-Pkotlin.compiler.execution.strategy=in-process")
        command = [tracer, "-f", "-s", "65535", "-e", calls, "-o",
                   str(execution_log), *command]
    return command, execution_log


def wasm_payload_paths(host):
    target = "wasmJs" if host == "node-wasm-js" else "wasmWasi"
    source = PORTABLE / "build/compileSync" / target / "test/testDevelopmentExecutable/kotlin"
    names = [f"{WASM_MODULE}.mjs", f"{WASM_MODULE}.wasm", "custom-formatters.js"]
    if host == "node-wasm-js":
        names += [f"{WASM_MODULE}.import-object.mjs", f"{WASM_MODULE}.js-builtins.mjs"]
    return {name: source / name for name in names}


def wasm_command(method, binary, runner):
    if method not in MATRIX_METHODS:
        raise Rejected(f"unknown numerical matrix method: {method}")
    return [str(binary), str(runner), "--include", f"portable.PortableMatrixTest.{method}"]


def run_wasm_method(host, method, lane, env, started):
    tracer = shutil.which("strace")
    executable = shutil.which("node", path=env.get("PATH"))
    if tracer is None or executable is None:
        raise Rejected("Node or strace is unavailable for direct Wasm execution")
    bundle = lane / "producer-bundle" / method
    kotlin = bundle / "kotlin"
    kotlin.mkdir(parents=True)
    sources = wasm_payload_paths(host)
    for name, source in sources.items():
        if not source.is_file() or source.stat().st_mtime_ns < started:
            raise Rejected(f"current Wasm linked payload is absent or stale: {name}")
        _copy_bundle_file(source, bundle, f"kotlin/{name}")
    static = bundle / "static"
    static.mkdir()
    runner = static / "runUnitTests.mjs"
    runner.write_bytes(WASM_RUNNER)
    command = wasm_command(method, Path(executable).resolve(), runner)
    execution_log = lane / f"native-exec-{method}.log"
    stream = lane / f"native-output-{method}.log"
    node_env = env.copy()
    node_env.pop("NODE_OPTIONS", None)
    with stream.open("xb") as output:
        completed = subprocess.run([tracer, "-f", "-s", "65535", "-e", "trace=execve",
                                    "-o", str(execution_log), *command],
                                   cwd=bundle, env=node_env, stdout=output,
                                   stderr=subprocess.STDOUT, check=False)
    if completed.returncode:
        raise Rejected(f"direct Wasm method exited {completed.returncode}")
    xml_dir = lane / "xml"
    xml_dir.mkdir(exist_ok=True)
    node_stream_xml(method, stream, xml_dir / f"{method}.xml", create=True)
    return execution_log


def retain_wasm_publications(lane, target_artifacts):
    bundle = lane / "producer-bundle"
    bundle.mkdir()
    for role, source in target_artifacts.items():
        archived = _copy_bundle_file(source, bundle, f"publications/{role}{source.suffix}")
        if digest(archived) != digest(source):
            raise Rejected(f"retained Wasm {role} publication differs")


def node_command(method, modules, executable, bundle=None):
    modules = Path(modules).resolve()
    bundle = (Path(bundle) if bundle is not None else
              PORTABLE / "build/compileSync/js/test/testDevelopmentExecutable/kotlin" /
              "dyn4k-portable-numerical-consumer-test.js")
    helpers = Path(modules) / "kotlin-web-helpers/dist"
    return [str(executable), "--require", str(Path(modules) / "source-map-support/register.js"),
            str(Path(modules) / "mocha/bin/mocha.js"), str(bundle),
            "--include", f"portable.PortableMatrixTest.{method}",
            "--reporter", str(helpers / "mocha-kotlin-reporter.js"),
            "--require", str(helpers / "kotlin-test-nodejs-runner.js"),
            "--timeout", "90m"]


def run_node_method(method, lane, env, modules):
    tracer = shutil.which("strace")
    executable = shutil.which("node", path=env.get("PATH"))
    if tracer is None or executable is None:
        raise Rejected("Node or strace is unavailable for direct method execution")
    command = node_command(method, modules, Path(executable).resolve())
    if any(not Path(command[index]).is_file() for index in (2, 3, 4, 8, 10)):
        raise Rejected("cached Node test bundle or runner module is absent")
    execution_log = lane / f"native-exec-{method}.log"
    stream = lane / f"native-output-{method}.log"
    node_env = env.copy()
    node_env.pop("NODE_OPTIONS", None)
    node_env["NODE_PATH"] = str(Path(modules).resolve())
    with stream.open("xb") as output:
        completed = subprocess.run([tracer, "-f", "-s", "65535", "-e", "trace=execve",
                                    "-o", str(execution_log), *command],
                                   cwd=PORTABLE, env=node_env, stdout=output,
                                   stderr=subprocess.STDOUT, check=False)
    if completed.returncode:
        raise Rejected(f"direct Node method exited {completed.returncode}")
    xml_dir = lane / "xml"
    xml_dir.mkdir(exist_ok=True)
    node_stream_xml(method, stream, xml_dir / f"{method}.xml", create=True)
    return execution_log


def build_node_method(method, lane, env):
    started = time.time_ns()
    command, _ = method_command("node-js", method, lane)
    log = lane / f"gradle-{method}.log"
    with log.open("x", encoding="utf-8") as stream:
        completed = subprocess.run(command, cwd=ROOT, env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, check=False)
    return started, log, completed.returncode


def method_xml_source(host, lane, method, started):
    if host in ("linux-x64", "node-js", *WASM_HOSTS):
        reports = [lane / "xml" / f"{method}.xml"]
    else:
        reports = sorted((PORTABLE / "build/test-results" / HOST_TASKS[host]).glob(
            "TEST-*PortableMatrixTest*.xml"))
    if len(reports) != 1 or not reports[0].is_file() or \
            reports[0].stat().st_mtime_ns < started:
        raise Rejected("matrix XML is missing or stale")
    return reports[0]


def native_command(method, binary):
    if method not in MATRIX_METHODS:
        raise Rejected(f"unknown numerical matrix method: {method}")
    if not Path(binary).is_absolute() or ".." in Path(binary).parts:
        raise Rejected("native executable path is unsafe")
    return [str(binary),
            f"--ktest_filter=portable.PortableMatrixTest.{method}",
            "--ktest_logger=GTEST"]


def native_stream_xml(method, source, xml, create=False):
    name = f"portable.PortableMatrixTest.{method}".encode()
    header = (b'<?xml version="1.0" encoding="UTF-8"?>\n'
              b'<testsuite name="portable.PortableMatrixTest" tests="1" skipped="0" failures="0" errors="0">\n'
              b'<testcase classname="portable.PortableMatrixTest" name="' +
              html.escape(method).encode() + b'"/>\n<system-out><![CDATA[\n')
    footer = b']]></system-out>\n</testsuite>\n'
    started = finished = passed = rows = 0
    state = 0
    with Path(source).open("rb") as raw, Path(xml).open("xb" if create else "rb") as report:
        def emit(value):
            if create:
                report.write(value)
            elif report.read(len(value)) != value:
                raise Rejected("native XML differs from raw stream")

        emit(header)
        for line in raw:
            if not line.endswith(b"\n"):
                raise Rejected("native output is truncated")
            if line.startswith(b"[ RUN      ] "):
                if state != 0 or line.rstrip(b"\r\n").split(b"] ", 1)[1] != name:
                    raise Rejected("native test method start differs")
                started += 1
                state = 1
            elif line.startswith(b"[       OK ] "):
                if state != 1 or not line.startswith(b"[       OK ] " + name + b" ("):
                    raise Rejected("native test method finish differs")
                finished += 1
                state = 2
            elif line.startswith(b"[  PASSED  ] "):
                if state != 2 or line.rstrip(b"\r\n") != b"[  PASSED  ] 1 tests.":
                    raise Rejected("native test pass event differs")
                passed += 1
                state = 3
            elif line.startswith((b"[  FAILED  ] ", b"[  SKIPPED ] ")):
                raise Rejected("native test failed or skipped")
            elif line.startswith((b"NUMERICAL_JSON ", b"NUMERICAL_PROBE_JSON ")):
                if state != 1 or b"]]>" in line:
                    raise Rejected("native numerical row is outside its test")
                line.decode("utf-8")
                emit(line)
                if line.startswith(b"NUMERICAL_JSON "):
                    rows += 1
        emit(footer)
        if not create and report.read(1):
            raise Rejected("native XML has extra bytes")
    if (started, finished, passed) != (1, 1, 1) or rows == 0:
        raise Rejected("native test event stream is incomplete")
    return rows


def node_stream_xml(method, source, xml, create=False):
    name = method.encode()
    header = (b'<?xml version="1.0" encoding="UTF-8"?>\n'
              b'<testsuite name="portable.PortableMatrixTest" tests="1" skipped="0" failures="0" errors="0">\n'
              b'<testcase classname="portable.PortableMatrixTest" name="' +
              html.escape(method).encode() + b'"/>\n<system-out><![CDATA[\n')
    footer = b']]></system-out>\n</testsuite>\n'
    started = finished = rows = 0
    with Path(source).open("rb") as raw, Path(xml).open("xb" if create else "rb") as report:
        def emit(value):
            if create:
                report.write(value)
            elif report.read(len(value)) != value:
                raise Rejected("Node XML differs from raw stream")

        emit(header)
        for line in raw:
            if not line.endswith(b"\n"):
                raise Rejected("Node output is truncated")
            if line.startswith(b"##teamcity[testStarted "):
                if b"name='" + name + b"'" not in line or started or finished:
                    raise Rejected("Node test start differs")
                started += 1
            elif line.startswith(b"##teamcity[testFinished "):
                if b"name='" + name + b"'" not in line or started != 1 or finished:
                    raise Rejected("Node test finish differs")
                finished += 1
            elif line.startswith((b"##teamcity[testFailed ", b"##teamcity[testIgnored ")):
                raise Rejected("Node test failed or skipped")
            elif line.startswith((b"NUMERICAL_JSON ", b"NUMERICAL_PROBE_JSON ")):
                if started != 1 or finished or b"]]>" in line:
                    raise Rejected("Node numerical row is outside its test")
                line.decode("utf-8")
                emit(line)
                if line.startswith(b"NUMERICAL_JSON "):
                    rows += 1
        emit(footer)
        if not create and report.read(1):
            raise Rejected("Node XML has extra bytes")
    if (started, finished) != (1, 1) or rows == 0:
        raise Rejected("Node test event stream is incomplete")
    return rows


def run_native_method(method, lane, binary, env):
    tracer = shutil.which("strace")
    if tracer is None:
        raise Rejected("strace is unavailable for native process binding")
    execution_log = lane / f"native-exec-{method}.log"
    stream = lane / f"native-output-{method}.log"
    command = [tracer, "-f", "-s", "65535", "-e", "trace=execve", "-o",
               str(execution_log), *native_command(method, binary)]
    with stream.open("xb") as output:
        completed = subprocess.run(command, cwd=PORTABLE, env=env, stdout=output,
                                   stderr=subprocess.STDOUT, check=False)
    if completed.returncode:
        raise Rejected(f"native method exited {completed.returncode}")
    xml_dir = lane / "xml"
    xml_dir.mkdir(exist_ok=True)
    native_stream_xml(method, stream, xml_dir / f"{method}.xml", create=True)
    return execution_log


def _bundle_file(bundle, relative):
    if not isinstance(relative, str) or not relative or len(relative) > 512 or \
            Path(relative).is_absolute() or \
            any(part in ("", ".", "..") for part in relative.split("/")) or \
            any(len(part) > 255 for part in relative.split("/")) or "\\" in relative:
        raise Rejected("native bundle path is unsafe")
    bundle = Path(bundle)
    candidate = bundle / relative
    if bundle.is_symlink() or any(path.is_symlink() for path in (candidate, *candidate.parents)
                                  if path == bundle or bundle in path.parents):
        raise Rejected("native bundle path is a symlink")
    if not candidate.resolve().is_relative_to(bundle.resolve()):
        raise Rejected("native bundle path escapes archive")
    if candidate.is_file() and candidate.stat().st_nlink != 1:
        raise Rejected("native bundle file has an external hard link")
    return candidate


def _native_archive_file(output, relative):
    return _bundle_file(output, f"linux-x64/{relative}")


def _copy_bundle_file(source, bundle, relative):
    source = Path(source)
    if not source.is_file() or source.is_symlink():
        raise Rejected("native bundle source is absent or linked")
    target = _bundle_file(bundle, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as stream, target.open("xb") as output:
        shutil.copyfileobj(stream, output, 1024 * 1024)
    return target


def node_bundle_paths(process):
    command = process["worker_command"]
    bundle = _recorded_absolute_path(process["bundle"]["command_bundle"])
    artifact = _recorded_absolute_path(process["dependency"]["artifact"])
    if command[4] != str(bundle):
        raise Rejected("Node command bundle differs from process proof")
    return {"artifact": artifact, "bundle": bundle,
            "core": bundle.with_name("dyn4k-dyn4k-core.js"),
            **{f"runner-{index}": _recorded_absolute_path(command[index])
               for index in (2, 3, 8, 10)}}


def retain_node_bundle(lane, method, process):
    bundle = lane / "producer-bundle"
    bundle.mkdir()
    files = {}
    expected = {"artifact": process["dependency"]["artifact_sha256"],
                "bundle": process["bundle"]["payload_sha256"][process["bundle"]["command_bundle"]],
                "core": process["bundle"]["payload_sha256"][str(
                    Path(process["bundle"]["command_bundle"]).with_name("dyn4k-dyn4k-core.js"))],
                **{f"runner-{index}": process["runner_module_sha256"][process["worker_command"][index]]
                   for index in (2, 3, 8, 10)}}
    for role, original in node_bundle_paths(process).items():
        relative = f"files/{role}{original.suffix}"
        archived = _copy_bundle_file(original, bundle, relative)
        if digest(archived) != expected[role]:
            raise Rejected("retained Node producer input differs")
        files[role] = {"original_path": str(original), "bundle_path": relative,
                       "sha256": expected[role], "bytes": archived.stat().st_size}
    manifest = {"schema": "portable-node-producer-bundle/1", "method": method,
                "node_modules": str(Path(process["worker_command"][3]).parents[2]),
                "files": files}
    path = bundle / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return digest(path)


def load_node_bundle(lane, method, process, manifest_sha256, binary, selected):
    bundle = lane / "producer-bundle"
    manifest_path = _bundle_file(bundle, "manifest.json")
    if manifest_path.stat().st_size > 100_000 or digest(manifest_path) != manifest_sha256:
        raise Rejected("retained Node manifest differs")
    manifest = json.loads(manifest_path.read_text())
    paths = node_bundle_paths(process)
    if set(manifest) != {"schema", "method", "node_modules", "files"} or \
            manifest["schema"] != "portable-node-producer-bundle/1" or \
            manifest["method"] != method or set(manifest["files"]) != set(paths):
        raise Rejected("retained Node manifest identity differs")
    files = {}
    for role, original in paths.items():
        item = manifest["files"][role]
        if set(item) != {"original_path", "bundle_path", "sha256", "bytes"} or \
                item["original_path"] != str(original):
            raise Rejected("retained Node input identity differs")
        archived = _bundle_file(bundle, item["bundle_path"])
        if not archived.is_file() or archived.stat().st_size != item["bytes"] or \
                digest(archived) != item["sha256"]:
            raise Rejected("retained Node input bytes differ")
        files[str(original)] = archived
    for role in ("artifact", "bundle", "core"):
        sha = selected[role]
        if manifest["files"][role]["sha256"] != sha:
            raise Rejected(f"externally selected Node {role} hash differs")
    if digest(binary) != process["executable_sha256"] or digest(binary) != selected["node"]:
        raise Rejected("selected Node binary differs from executed binary")
    if manifest["node_modules"] != str(Path(process["worker_command"][3]).parents[2]):
        raise Rejected("retained Node module root differs")
    return {"files": files, "binary": binary, "original_artifact": str(paths["artifact"]),
            "original_bundle": str(paths["bundle"]), "node_modules": manifest["node_modules"],
            "artifact": files[str(paths["artifact"])]}


def _publication_names():
    return {name for host in HOST_TASKS for name in artifact_relative_paths(host).values()}


def start_native_bundle(output, lane, commit, source_sha256):
    publication = json.loads((output / "publication.json").read_text())
    names = _publication_names()
    if publication.get("candidate_commit") != commit or \
            publication.get("source_sha256") != source_sha256 or \
            set(publication.get("artifact_sha256", {})) != names:
        raise Rejected("native publication manifest differs")
    bundle = lane / "producer-bundle"
    bundle.mkdir()
    files = {}
    for name in sorted(names):
        original = STAGED / name
        archived = _copy_bundle_file(original, bundle, f"publications/{name}")
        sha = digest(archived)
        if sha != publication["artifact_sha256"][name]:
            raise Rejected("retained staged publication differs")
        files[name] = {"original_path": str(original.resolve()),
                       "bundle_path": f"publications/{name}",
                       "sha256": sha, "bytes": archived.stat().st_size}
    return {"schema": "portable-native-producer-bundle/1",
            "candidate_commit": commit, "source_sha256": source_sha256,
            "producer_root": str(ROOT.resolve()), "stage_root": str(STAGED.resolve()),
            "platform": {"os": platform.platform(), "machine": platform.machine(),
                         "version": platform.platform()},
            "publication_sha256": digest(output / "publication.json"),
            "publications": files, "methods": {}}


def retain_native_method(bundle, manifest, method, process):
    if method in manifest["methods"]:
        raise Rejected("native bundle method is duplicated")
    binary = Path(process["executable"])
    expected = PORTABLE / "build/bin/linuxX64/debugTest/test.kexe"
    if binary != expected.resolve() or digest(binary) != process["executable_sha256"] or \
            binary.stat().st_mtime_ns != process["binary_mtime_ns"]:
        raise Rejected("executed native binary differs before retention")
    binary_relative = f"methods/{method}/test.kexe"
    binary_copy = _copy_bundle_file(binary, bundle, binary_relative)
    inputs = {}
    for item in process["dependency"]["tasks"]:
        original = Path(item["path"])
        if str(original) in inputs:
            continue
        if not _native_cache_input(original) and original != STAGED / \
                artifact_relative_paths("linux-x64")["target"]:
            raise Rejected("native compiler input path differs")
        relative = f"inputs/{item['sha256']}.klib"
        archived = _bundle_file(bundle, relative)
        if not archived.exists():
            _copy_bundle_file(original, bundle, relative)
        if digest(archived) != item["sha256"] or archived.stat().st_size != item["bytes"]:
            raise Rejected("retained native compiler input differs")
        inputs[str(original)] = {"bundle_path": relative, "sha256": item["sha256"],
                                 "bytes": item["bytes"]}
    if not inputs:
        raise Rejected("native compiler input bundle is empty")
    manifest["methods"][method] = {
        "binary": {"original_path": str(binary), "bundle_path": binary_relative,
                   "sha256": digest(binary_copy), "bytes": binary_copy.stat().st_size,
                   "mtime_ns": binary.stat().st_mtime_ns},
        "compiler_inputs": inputs,
        "process_sha256": hashlib.sha256(json.dumps(process, sort_keys=True).encode()).hexdigest()}


def finish_native_bundle(lane, manifest):
    if set(manifest["methods"]) != set(MATRIX_METHODS):
        raise Rejected("native producer bundle method set is incomplete")
    path = lane / "producer-bundle/manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return digest(path)


def _recorded_absolute_path(value):
    if not isinstance(value, str) or len(value) > 4096 or not Path(value).is_absolute() or \
            ".." in Path(value).parts or str(Path(value)) != value:
        raise Rejected("native producer path is unsafe")
    return Path(value)


def load_native_bundle(output, publication, commit, source_sha256, result):
    manifest_path = _native_archive_file(output, "producer-bundle/manifest.json")
    if manifest_path.stat().st_size > 1_000_000:
        raise Rejected("native bundle manifest is too large")
    if digest(manifest_path) != result.get("native_bundle_sha256"):
        raise Rejected("native bundle manifest hash differs")
    manifest = json.loads(manifest_path.read_text())
    if set(manifest) != {"schema", "candidate_commit", "source_sha256", "producer_root",
                         "stage_root", "platform", "publication_sha256", "publications",
                         "methods"} or manifest["schema"] != "portable-native-producer-bundle/1" or \
            manifest["candidate_commit"] != commit or manifest["source_sha256"] != source_sha256 or \
            manifest["publication_sha256"] != digest(output / "publication.json"):
        raise Rejected("native bundle identity differs")
    producer_root = _recorded_absolute_path(manifest["producer_root"])
    stage_root = _recorded_absolute_path(manifest["stage_root"])
    if stage_root != producer_root / "build/staging-repository/io/github/rubixhacker":
        raise Rejected("native bundle staged root differs")
    producer_platform = manifest["platform"]
    if not isinstance(producer_platform, dict) or set(producer_platform) != \
            {"os", "machine", "version"} or any(not isinstance(value, str) or not value
                                               for value in producer_platform.values()):
        raise Rejected("native producer platform identity differs")
    names = _publication_names()
    if set(publication.get("artifact_sha256", {})) != names or \
            set(manifest["publications"]) != names:
        raise Rejected("native publication file set differs")
    publications = {}
    for name in sorted(names):
        item = manifest["publications"][name]
        if not isinstance(item, dict) or set(item) != \
                {"original_path", "bundle_path", "sha256", "bytes"} or \
                _recorded_absolute_path(item["original_path"]) != stage_root / name or \
                item["bundle_path"] != f"publications/{name}" or \
                item["sha256"] != publication["artifact_sha256"][name] or \
                type(item["bytes"]) is not int or item["bytes"] <= 0:
            raise Rejected("native staged publication entry differs")
        path = _native_archive_file(output, f"producer-bundle/{item['bundle_path']}")
        if not path.is_file() or path.stat().st_size != item["bytes"] or \
                digest(path) != item["sha256"]:
            raise Rejected("retained staged publication bytes differ")
        publications[name] = path
    if set(manifest["methods"]) != set(MATRIX_METHODS):
        raise Rejected("native bundle method set differs")
    methods = {}
    target_name = artifact_relative_paths("linux-x64")["target"]
    for method in MATRIX_METHODS:
        item = manifest["methods"][method]
        if not isinstance(item, dict) or set(item) != \
                {"binary", "compiler_inputs", "process_sha256"}:
            raise Rejected("native method bundle entry differs")
        binary = item["binary"]
        if not isinstance(binary, dict) or set(binary) != \
                {"original_path", "bundle_path", "sha256", "bytes", "mtime_ns"} or \
                _recorded_absolute_path(binary["original_path"]) != producer_root / \
                "tools/numerical/portable/build/bin/linuxX64/debugTest/test.kexe" or \
                binary["bundle_path"] != f"methods/{method}/test.kexe" or \
                type(binary["bytes"]) is not int or binary["bytes"] <= 0 or \
                type(binary["mtime_ns"]) is not int or binary["mtime_ns"] <= 0:
            raise Rejected("native executable bundle identity differs")
        binary_file = _native_archive_file(output, f"producer-bundle/{binary['bundle_path']}")
        if not binary_file.is_file() or binary_file.stat().st_size != binary["bytes"] or \
                digest(binary_file) != binary["sha256"]:
            raise Rejected("retained native executable bytes differ")
        inputs = item["compiler_inputs"]
        if not isinstance(inputs, dict) or not inputs:
            raise Rejected("native compiler input bundle is empty")
        input_files = {}
        for original, entry in inputs.items():
            path = _recorded_absolute_path(original)
            if path != stage_root / target_name and not _native_cache_input(path):
                raise Rejected("native compiler input origin differs")
            if not isinstance(entry, dict) or set(entry) != {"bundle_path", "sha256", "bytes"} or \
                    not isinstance(entry["sha256"], str) or \
                    re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None or \
                    entry["bundle_path"] != f"inputs/{entry['sha256']}.klib" or \
                    type(entry["bytes"]) is not int or entry["bytes"] <= 0:
                raise Rejected("native compiler input bundle path differs")
            archived = _native_archive_file(output, f"producer-bundle/{entry['bundle_path']}")
            if not archived.is_file() or archived.stat().st_size != entry["bytes"] or \
                    digest(archived) != entry["sha256"]:
                raise Rejected("retained native compiler input bytes differ")
            input_files[original] = archived
        if not isinstance(item["process_sha256"], str) or \
                re.fullmatch(r"[0-9a-f]{64}", item["process_sha256"]) is None:
            raise Rejected("native process bundle hash differs")
        methods[method] = {"binary": binary, "binary_file": binary_file,
                           "input_files": input_files, "platform": producer_platform,
                           "target_original_path": str(stage_root / target_name),
                           "process_sha256": item["process_sha256"]}
    return publications, methods, manifest


def execute(host, output, commit, source_sha256, reference_dirs,
            prospective_baseline=None, frozen_baseline=None,
            frozen_attestation=None, prospective_attestation=None,
            arithmetic_captures=None, node_modules=None, jdk8_home=None):
    lane = output / host
    lane.mkdir(parents=True, exist_ok=False)
    target_artifacts = artifacts(host)
    artifact_sha256 = {name: digest(path) for name, path in target_artifacts.items()}
    env = controlled_java_environment() if host == "jvm8" else os.environ.copy()
    if host == "jvm8":
        jdk8_home = selected_jdk8_home(jdk8_home)
    env.setdefault("ANDROID_HOME", str(Path.home() / "Android/Sdk"))
    if host in ("jvm", "jvm8", "android-host"):
        env["JAVA_TOOL_OPTIONS"] = (env.get("JAVA_TOOL_OPTIONS", "") +
                                    " -verbose:class").strip()
    outcome = {"host": host, "task": HOST_TASKS[host], "gradle_exit": 0,
               "status": "PASSED",
               "qualification": "UNPASSED", "frozen_comparison": "NOT_RUN",
               "candidate_commit": commit, "source_sha256": source_sha256,
               "artifact_sha256": artifact_sha256,
               "comparison_coverage": comparison_coverage(),
               "prospective_reference": {
                   "status": "NOT_RUN" if prospective_baseline else "UNAVAILABLE_REFERENCE",
                   "qualification": "UNPASSED", "cases": 0,
                   "reason": ("Host trace is not sealed" if prospective_baseline else
                              "No verified pinned baseline archive was supplied")}}
    trace = None
    try:
        if host in WASM_HOSTS:
            retain_wasm_publications(lane, target_artifacts)
        attributes = {key: 0 for key in ("tests", "skipped", "failures", "errors")}
        raw_counts = {"expected_cases": len(declared_cases()), "input_records": 0,
                      "observed_cases": 0, "completed_cases": 0, "states": 0,
                      "tagged_nonfinite_values": 0, "per_case": {}}
        bundle_manifest = (start_native_bundle(output, lane, commit, source_sha256)
                           if host == "linux-x64" else None)
        methods = []
        runtimes = []
        for method in MATRIX_METHODS:
            if host == "node-js":
                started, log_path, gradle_exit = build_node_method(method, lane, env)
                execution_log = None
            else:
                started = time.time_ns()
                command, execution_log = method_command(host, method, lane, jdk8_home)
                log_path = lane / f"gradle-{method}.log"
                with log_path.open("x", encoding="utf-8") as log:
                    if host == "linux-x64":
                        log.write(f"NUMERICAL_BUILD_STARTED_NS {started}\n")
                        log.flush()
                    completed = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                               stderr=subprocess.STDOUT, check=False)
                gradle_exit = completed.returncode
            method_result = {"method": method, "gradle_exit": gradle_exit,
                             "log_sha256": digest(log_path)}
            methods.append(method_result)
            if gradle_exit:
                outcome["gradle_exit"] = gradle_exit
                outcome["status"] = "FAILED"
            if host == "linux-x64" and not gradle_exit:
                binaries = list((PORTABLE / "build/bin/linuxX64").rglob("*.kexe"))
                if len(binaries) != 1 or binaries[0].stat().st_mtime_ns < started:
                    method_result["reason"] = "native test binary is absent or stale"
                    outcome["status"] = "FAILED"
                    continue
                try:
                    execution_log = run_native_method(method, lane, binaries[0], env)
                except Rejected as error:
                    method_result["reason"] = str(error)
                    outcome["status"] = "FAILED"
                    continue
            if host == "node-js" and not gradle_exit:
                try:
                    execution_log = run_node_method(method, lane, env, node_modules or
                        PORTABLE / "build/js/node_modules")
                except Rejected as error:
                    method_result["reason"] = str(error)
                    outcome["status"] = "FAILED"
                    continue
            if host in WASM_HOSTS and not gradle_exit:
                try:
                    execution_log = run_wasm_method(host, method, lane, env, started)
                except Rejected as error:
                    method_result["reason"] = str(error)
                    outcome["status"] = "FAILED"
                    continue
            if execution_log is not None and execution_log.is_file():
                method_result["execution_log_sha256"] = digest(execution_log)
            try:
                xml = method_xml_source(host, lane, method, started)
            except Rejected as error:
                method_result["reason"] = str(error)
                outcome["status"] = "FAILED"
                continue
            try:
                trace, row_attributes, row_counts = extract_xml(host, lane, method, xml)
            except (Rejected, OSError, ValueError) as error:
                method_result["reason"] = str(error)
                outcome["status"] = "FAILED"
                continue
            method_result["xml"] = row_attributes
            method_result["xml_sha256"] = digest(lane / "xml" / f"{method}.xml")
            method_result["cases"] = row_counts["completed_cases"]
            for key in attributes:
                attributes[key] += int(row_attributes.get(key, "-1"))
            for key in ("input_records", "completed_cases", "states", "tagged_nonfinite_values"):
                raw_counts[key] += row_counts[key]
            duplicate = raw_counts["per_case"].keys() & row_counts["per_case"].keys()
            if duplicate:
                raise Rejected(f"case appears in more than one test method: {sorted(duplicate)[:5]}")
            raw_counts["per_case"].update(row_counts["per_case"])
            try:
                executed = runtime(host, log_path, execution_log,
                                   target_artifacts["target"],
                                   lane / "process-proof" / method,
                                   node_modules=(node_modules or PORTABLE / "build/js/node_modules")
                                   if host == "node-js" else None)
                if host == "jvm8" and executed["executable"] != str(jdk8_home / "bin/java"):
                    raise Rejected("Java 8 worker differs from selected JDK home")
                method_result["process"] = executed
                if bundle_manifest is not None:
                    retain_native_method(lane / "producer-bundle", bundle_manifest,
                                         method, executed)
                runtimes.append(runtime_identity(executed))
            except Rejected as error:
                method_result["reason"] = str(error)
                outcome["status"] = "FAILED"
        outcome["methods"] = methods
        raw_counts["observed_cases"] = len(raw_counts["per_case"])
        outcome["xml"] = attributes
        outcome["raw_counts"] = raw_counts
        outcome["started_cases"] = raw_counts["observed_cases"]
        outcome["executed_cases"] = raw_counts["completed_cases"]
        outcome["incomplete_cases"] = sorted(case_id for case_id, counts in
                                             raw_counts["per_case"].items()
                                             if counts["case_ends"] != 1)
        outcome["failed_methods"] = [item["method"] for item in methods
                                     if item["gradle_exit"] or "reason" in item]
        outcome["completed_methods"] = sum("process" in item and
            item.get("cases") == len(method_case_ids(item["method"])) for item in methods)
        if not runtimes:
            raise Rejected("no executed target runtime was bound")
        executed_runtime = runtimes[0]
        if any(row != executed_runtime for row in runtimes[1:]):
            raise Rejected("test methods used different target runtimes")
        executed_runtime["method_executions"] = len(runtimes)
        executed_runtime["dependency_sha256"] = artifact_sha256["target"]
        executed_runtime["method_process_sha256"] = hashlib.sha256(json.dumps(
            [item["process"] for item in methods if "process" in item],
            sort_keys=True).encode()).hexdigest()
        if bundle_manifest is not None:
            outcome["native_bundle_sha256"] = finish_native_bundle(lane, bundle_manifest)
        outcome["runtime"] = executed_runtime
        comparisons = compare_frozen(lane, reference_dirs, frozen_baseline,
                                     frozen_attestation)
        outcome["frozen_comparison_results"] = {
            "available": sum(item["status"] != "UNAVAILABLE_REFERENCE" for item in comparisons),
            "unavailable": sum(item["status"] == "UNAVAILABLE_REFERENCE" for item in comparisons),
            "failed": sum(item["status"].startswith("FAILED") for item in comparisons),
            "unpassed": sum(item["status"].startswith("UNPASSED") for item in comparisons),
            "passed": sum(item["status"] == "PASSED_APPROVED_PROJECTION" for item in comparisons)}
        outcome["frozen_comparison"] = (
            "PASSED_APPROVED_PROJECTION" if all(item["status"] ==
                "PASSED_APPROVED_PROJECTION" for item in comparisons) else "UNPASSED")
        physical = nominal_free(lane / "cases/long-free-60.jsonl")
        outcome["physical"] = physical
        sleep_ids = ([f"contacts-default-{hz}" for hz in (30, 60, 120)] +
                     [f"contacts-configured-{hz}-r{repetition}"
                      for hz in (30, 60, 120) for repetition in (1, 2)])
        sleep = sleep_wake_rows(chain.from_iterable(
            records(lane / "cases" / f"{case_id}.jsonl", allow_tagged_nonfinite=True)
            for case_id in sleep_ids if (lane / "cases" / f"{case_id}.jsonl").is_file()))
        outcome["sleep_wake_physical"] = sleep
        exact_consistency = check_exact_consistency(lane)
        outcome["exact_consistency"] = exact_consistency
        if outcome["status"] == "FAILED":
            raise Rejected("one or more method tasks failed or lacked current XML")
        if any(int(attributes.get(key, "-1")) != expected for key, expected in
               (("tests", 15), ("skipped", 0), ("failures", 0), ("errors", 0))):
            raise Rejected(f"matrix XML reports incomplete tests: {attributes}")
        if clean_identity() != (commit, source_sha256):
            raise Rejected("source changed during host execution")
        identity = Identity(commit, source_sha256, artifact_sha256, executed_runtime)
        sealed = seal(trace, declared_cases(), identity, target_artifacts)
        (lane / "receipt.json").write_text(json.dumps(sealed, indent=2, sort_keys=True) + "\n")
        outcome.update({"xml": attributes, "counts": sealed["counts"], "trace_sha256": sealed["trace_sha256"],
                        "artifact_sha256": identity.artifact_sha256})
        outcome["angle_physical"] = {
            "status": "FAILED_PHYSICAL" if sealed["counts"]["known_nonfinite_cases"] else "NO_NONFINITE",
            "known_nonfinite_cases": sealed["counts"]["known_nonfinite_cases"]}
        if sealed["counts"]["known_nonfinite_cases"]:
            outcome["status"] = "FAILED"
            outcome.setdefault("failure_reasons", []).append("Angle nonfinite physical case failed")
        if prospective_baseline is not None:
            prospective = compare_host(prospective_baseline, lane,
                                       outcome["comparison_coverage"]["frozen_case_ids"],
                                       prospective_attestation, arithmetic_captures)
            outcome["prospective_reference"] = {
                key: value for key, value in prospective.items() if key != "results"}
            if prospective["failed"]:
                outcome["status"] = "FAILED"
                outcome.setdefault("failure_reasons", []).append(
                    "prospective baseline comparison failed")
        if physical["status"] != "PASSED" or sleep["status"] != "PHYSICAL_PASSED":
            outcome["status"] = "FAILED"
            outcome.setdefault("failure_reasons", []).append("physical diagnostic failed")
        if exact_consistency["status"] != "PASSED":
            outcome["status"] = "FAILED"
            outcome.setdefault("failure_reasons", []).append(
                "exact consistency diagnostic failed")
        if "failure_reasons" in outcome:
            outcome["reason"] = "; ".join(outcome["failure_reasons"])
    except (Rejected, OSError, ValueError, KeyError) as error:
        outcome["status"] = "FAILED"
        outcome["reason"] = str(error)
    if trace is not None and "trace_sha256" not in outcome:
        outcome["trace_sha256"] = digest(trace)
    if not (lane / "receipt.json").exists():
        (lane / "receipt.json").write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n")
    (lane / "result.json").write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n")
    return outcome


def verify_linux_native_archive(output):
    from baseline_capture import verify_case_slices, verify_xml_trace

    commit, source_sha256 = clean_identity()
    publication_path = _bundle_file(output, "publication.json")
    publication_log = _bundle_file(output, "publication.log")
    publication = json.loads(publication_path.read_text())
    if publication["candidate_commit"] != commit or publication["source_sha256"] != source_sha256 or \
            digest(publication_log) != publication["publication_log_sha256"]:
        raise Rejected("native publication identity differs")
    lane = output / "linux-x64"
    result = json.loads(_native_archive_file(output, "result.json").read_text())
    receipt = json.loads(_native_archive_file(output, "receipt.json").read_text())
    publications, bundled_methods, manifest = load_native_bundle(
        output, publication, commit, source_sha256, result)
    methods = result["methods"]
    if [item["method"] for item in methods] != list(MATRIX_METHODS):
        raise Rejected("native method inventory differs")
    target_artifacts = {role: publications[name] for role, name in
                        artifact_relative_paths("linux-x64").items()}
    artifact_sha256 = {name: digest(path) for name, path in target_artifacts.items()}
    if receipt["artifact_sha256"] != artifact_sha256 or \
            result["artifact_sha256"] != artifact_sha256:
        raise Rejected("native staged artifact identity differs")
    proofs = []
    for item in methods:
        method = item["method"]
        if item["gradle_exit"] or item.get("cases") != len(method_case_ids(method)):
            raise Rejected(f"native method did not complete: {method}")
        build_log = _native_archive_file(output, f"gradle-{method}.log")
        execution_log = _native_archive_file(output, f"native-exec-{method}.log")
        _native_archive_file(output, f"native-output-{method}.log")
        xml = _native_archive_file(output, f"xml/{method}.xml")
        for path, field in ((build_log, "log_sha256"),
                            (execution_log, "execution_log_sha256"),
                            (xml, "xml_sha256")):
            if digest(path) != item[field]:
                raise Rejected(f"native method file differs: {method}: {field}")
        proof = runtime("linux-x64", build_log, execution_log, target_artifacts["target"],
                        native_bundle=bundled_methods[method])
        if hashlib.sha256(json.dumps(proof, sort_keys=True).encode()).hexdigest() != \
                bundled_methods[method]["process_sha256"]:
            raise Rejected(f"native bundled process hash differs: {method}")
        if item.get("process") != proof:
            raise Rejected(f"native method process proof differs: {method}")
        proofs.append(proof)
    identities = [runtime_identity(proof) for proof in proofs]
    if any(identity != identities[0] for identity in identities[1:]):
        raise Rejected("native methods used different runtime producers")
    runtime_proof = {**identities[0], "method_executions": len(proofs),
                     "dependency_sha256": artifact_sha256["target"],
                     "method_process_sha256": hashlib.sha256(json.dumps(
                         proofs, sort_keys=True).encode()).hexdigest()}
    if receipt["runtime"] != runtime_proof or result["runtime"] != runtime_proof:
        raise Rejected("native runtime inventory differs")
    trace = _native_archive_file(output, "trace.jsonl")
    for case in declared_cases():
        _native_archive_file(output, f"cases/{case['id']}.jsonl")
    verify_xml_trace(lane, [{**item, "completed_cases": item["cases"]} for item in methods],
                     result["raw_counts"], receipt["trace_sha256"])
    verify_case_slices(lane, result["raw_counts"]["per_case"])
    identity = Identity(commit, source_sha256, artifact_sha256, runtime_proof)
    expected_paths = {role: str(Path(manifest["stage_root"]) / name) for role, name in
                      artifact_relative_paths("linux-x64").items()}
    if receipt.get("artifact_paths") != expected_paths:
        raise Rejected("native original staged artifact paths differ")
    archived_receipt = {**receipt, "artifact_paths": {role: str(path) for role, path in
                                                   target_artifacts.items()}}
    verify_receipt(archived_receipt, trace, declared_cases(),
                   identity, target_artifacts)
    return {"status": "PASSED_PRODUCER_REPLAY", "qualification": "UNPASSED",
            "candidate_commit": commit, "methods": len(methods),
            "cases": receipt["counts"]["executed_cases"]}


def verify_wasm_archive(output, host):
    from baseline_capture import verify_case_slices, verify_xml_trace

    if host not in WASM_HOSTS:
        raise Rejected("Wasm replay host differs")
    commit, source_sha256 = clean_identity()
    publication = json.loads(_bundle_file(output, "publication.json").read_text())
    if publication.get("candidate_commit") != commit or \
            publication.get("source_sha256") != source_sha256 or \
            digest(_bundle_file(output, "publication.log")) != publication.get("publication_log_sha256"):
        raise Rejected("Wasm publication identity differs")
    lane = output / host
    result = json.loads(_bundle_file(lane, "result.json").read_text())
    receipt = json.loads(_bundle_file(lane, "receipt.json").read_text())
    cases = declared_cases()
    trace = _bundle_file(lane, "trace.jsonl")
    for case in cases:
        _bundle_file(lane, f"cases/{case['id']}.jsonl")
    methods = result.get("methods", [])
    if [item.get("method") for item in methods] != list(MATRIX_METHODS) or \
            result.get("candidate_commit") != commit or \
            result.get("source_sha256") != source_sha256 or \
            result.get("executed_cases") != len(cases) or \
            result.get("failed_methods"):
        raise Rejected("Wasm method or source inventory differs")
    artifacts_in_archive = {}
    for role, name in artifact_relative_paths(host).items():
        original = STAGED / name
        archived = _bundle_file(lane, f"producer-bundle/publications/{role}{original.suffix}")
        if digest(archived) != publication["artifact_sha256"][name]:
            raise Rejected(f"Wasm retained {role} publication differs")
        artifacts_in_archive[role] = archived
    if receipt.get("artifact_sha256") != result.get("artifact_sha256") or \
            result["artifact_sha256"] != {role: digest(path) for role, path in
                                          artifacts_in_archive.items()}:
        raise Rejected("Wasm staged artifact identity differs")
    proofs = []
    for item in methods:
        method = item["method"]
        if item.get("gradle_exit") or item.get("cases") != len(method_case_ids(method)):
            raise Rejected(f"Wasm method did not complete: {method}")
        log = _bundle_file(lane, f"gradle-{method}.log")
        execution = _bundle_file(lane, f"native-exec-{method}.log")
        stream = _bundle_file(lane, f"native-output-{method}.log")
        xml = _bundle_file(lane, f"xml/{method}.xml")
        for path, field in ((log, "log_sha256"), (execution, "execution_log_sha256"),
                            (xml, "xml_sha256")):
            if digest(path) != item.get(field):
                raise Rejected(f"Wasm method file differs: {method}: {field}")
        process = item["process"]
        if digest(stream) != process["native_output_sha256"] or \
                digest(log) != process["build_log_sha256"] or \
                digest(execution) != process["execution_log_sha256"] or \
                digest(xml) != process["xml_sha256"]:
            raise Rejected(f"Wasm process file differs: {method}")
        node_stream_xml(method, stream, xml)
        command = process["worker_command"]
        original_runner = _recorded_absolute_path(command[1])
        original_lane = original_runner.parents[3]
        if original_runner != original_lane / "producer-bundle" / method / \
                "static/runUnitTests.mjs" or command != wasm_command(
                    method, _recorded_absolute_path(command[0]), original_runner):
            raise Rejected(f"Wasm worker command differs: {method}")
        worker_lines = []
        with execution.open(encoding="utf-8", errors="replace") as source:
            for line in source:
                found = re.search(r'\bexecve\("([^"]+)", \[(.*?)\], .*\) = 0$', line)
                if found and "runUnitTests.mjs" in found.group(2):
                    worker_lines.append((found.group(1), re.findall(r'"([^"\n]*)"',
                                                                found.group(2))))
        if worker_lines != [(command[0], command)]:
            raise Rejected(f"Wasm executed worker differs: {method}")
        version = subprocess.run((command[0], "--version"), capture_output=True,
                                 text=True, check=False)
        if digest(Path(command[0])) != process["executable_sha256"] or \
                version.returncode or version.stdout.strip() != process["version"] or \
                process.get("process_executions") != 1 or \
                process.get("worker_command_sha256") != hashlib.sha256(
                    json.dumps(command).encode()).hexdigest():
            raise Rejected(f"Wasm executed Node binary differs: {method}")
        runner = _bundle_file(lane, f"producer-bundle/{method}/static/runUnitTests.mjs")
        if runner.read_bytes() != WASM_RUNNER or \
                digest(runner) != process["bundle"]["runner_sha256"]:
            raise Rejected(f"Wasm retained runner differs: {method}")
        expected_payloads = {}
        expected_sources = {}
        linked_root = ("wasmJs" if host == "node-wasm-js" else "wasmWasi")
        source_suffix = Path("tools/numerical/portable/build/compileSync") / linked_root / \
            "test/testDevelopmentExecutable/kotlin"
        for name in wasm_payload_paths(host):
            archived = _bundle_file(lane, f"producer-bundle/{method}/kotlin/{name}")
            original = original_lane / "producer-bundle" / method / "kotlin" / name
            expected_payloads[str(original)] = digest(archived)
            sources = [Path(path) for path in process["bundle"]["compiler_output_sha256"]
                       if Path(path).name == name]
            if len(sources) != 1 or sources[0].parts[-len(source_suffix.parts)-1:] != \
                    (*source_suffix.parts, name):
                raise Rejected(f"Wasm linked source path differs: {method}: {name}")
            expected_sources[str(sources[0])] = digest(archived)
        if process["bundle"]["payload_sha256"] != expected_payloads or \
                process["bundle"]["compiler_output_sha256"] != expected_sources:
            raise Rejected(f"Wasm retained linked payload differs: {method}")
        dependency = _compiled_dependency_proof(host, log, artifacts_in_archive["target"],
                    input_files={entry["path"]: artifacts_in_archive["target"] for entry in
                                 process["dependency"]["tasks"]},
                    original_dependency=process["dependency"]["artifact"])
        if dependency != process["dependency"]:
            raise Rejected(f"Wasm compiler dependency differs: {method}")
        proofs.append(process)
    runtime_proof = {**runtime_identity(proofs[0]), "method_executions": len(proofs),
                     "dependency_sha256": digest(artifacts_in_archive["target"]),
                     "method_process_sha256": hashlib.sha256(json.dumps(
                         proofs, sort_keys=True).encode()).hexdigest()}
    if runtime_proof != result.get("runtime") or runtime_proof != receipt.get("runtime"):
        raise Rejected("Wasm runtime inventory differs")
    raw_counts = result["raw_counts"]
    verify_xml_trace(lane, [{**item, "completed_cases": item["cases"]} for item in methods],
                     raw_counts, receipt["trace_sha256"])
    verify_case_slices(lane, raw_counts["per_case"])
    archived_receipt = {**receipt,
                        "artifact_paths": {role: str(path) for role, path in
                                           artifacts_in_archive.items()}}
    verify_receipt(archived_receipt, trace, cases,
                   Identity(commit, source_sha256, result["artifact_sha256"], runtime_proof),
                   artifacts_in_archive)
    return {"status": "PASSED_PRODUCER_REPLAY", "qualification": "UNPASSED",
            "host": host, "candidate_commit": commit, "methods": len(methods),
            "cases": receipt["counts"]["executed_cases"]}


def capture_node_method(output, method, modules):
    commit, source_sha256 = clean_identity()
    modules = Path(modules).resolve()
    output.mkdir(parents=True)
    lane = output / "node-js"
    lane.mkdir()
    target = artifacts("node-js")["target"]
    env = os.environ.copy()
    env.setdefault("ANDROID_HOME", str(Path.home() / "Android/Sdk"))
    started, log, gradle_exit = build_node_method(method, lane, env)
    if gradle_exit:
        raise Rejected(f"Node compiler exited {gradle_exit}")
    execution = run_node_method(method, lane, env, modules)
    xml = method_xml_source("node-js", lane, method, started)
    trace, attributes, counts = extract_xml("node-js", lane, method, xml)
    counts["expected_cases"] = len(method_case_ids(method))
    process = runtime("node-js", log, execution, target, node_modules=modules)
    from baseline_capture import verify_case_slices, verify_xml_trace
    verify_xml_trace(lane, [{"method": method, "completed_cases": counts["completed_cases"]}],
                     counts, digest(trace))
    case_hashes = verify_case_slices(lane, method_case_ids(method))
    if attributes != {"name": "portable.PortableMatrixTest", "tests": "1", "skipped": "0",
                      "failures": "0", "errors": "0"} or \
            counts["completed_cases"] != len(method_case_ids(method)):
        raise Rejected("focused Node method did not complete")
    if clean_identity() != (commit, source_sha256):
        raise Rejected("focused Node source identity differs after execution")
    bundle_sha256 = retain_node_bundle(lane, method, process)
    if clean_identity() != (commit, source_sha256):
        raise Rejected("focused Node source identity differs before sealing")
    result = {"status": "PASSED_PRODUCER", "qualification": "UNPASSED",
              "candidate_commit": commit, "source_sha256": source_sha256,
              "method": method, "node_modules": str(modules),
              "artifact_sha256": digest(target), "process": process,
              "node_bundle_sha256": bundle_sha256,
              "xml": attributes, "raw_counts": counts,
              "log_sha256": digest(log), "execution_log_sha256": digest(execution),
              "native_output_sha256": digest(lane / f"native-output-{method}.log"),
              "xml_sha256": digest(xml), "trace_sha256": digest(trace),
              "case_sha256": case_hashes}
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def verify_node_method_archive(output, binary, selected):
    from baseline_capture import verify_case_slices, verify_xml_trace

    result = json.loads((output / "result.json").read_text())
    method = result["method"]
    if method not in MATRIX_METHODS or result["status"] != "PASSED_PRODUCER" or \
            result["qualification"] != "UNPASSED" or \
            (result["candidate_commit"], result["source_sha256"]) != clean_identity():
        raise Rejected("focused Node source identity differs")
    lane = output / "node-js"
    log = lane / f"gradle-{method}.log"
    execution = lane / f"native-exec-{method}.log"
    stream = lane / f"native-output-{method}.log"
    xml = lane / "xml" / f"{method}.xml"
    trace = lane / "trace.jsonl"
    for path, field in ((log, "log_sha256"), (execution, "execution_log_sha256"),
                        (stream, "native_output_sha256"), (xml, "xml_sha256"),
                        (trace, "trace_sha256")):
        if digest(path) != result[field]:
            raise Rejected(f"focused Node archive file differs: {field}")
    frozen = load_node_bundle(lane, method, result["process"],
                              result["node_bundle_sha256"], binary, selected)
    if digest(frozen["artifact"]) != result["artifact_sha256"]:
        raise Rejected("focused Node staged artifact differs")
    process = runtime("node-js", log, execution, frozen["artifact"],
                      node_modules=Path(frozen["node_modules"]), node_bundle=frozen)
    if process != result["process"]:
        raise Rejected("focused Node process proof differs")
    counts = result["raw_counts"]
    verify_xml_trace(lane, [{"method": method, "completed_cases": counts["completed_cases"]}],
                     counts, result["trace_sha256"])
    if verify_case_slices(lane, method_case_ids(method)) != result["case_sha256"] or \
            counts["completed_cases"] != len(method_case_ids(method)):
        raise Rejected("focused Node case slices differ")
    return {"status": "PASSED_PRODUCER_REPLAY", "qualification": "UNPASSED",
            "candidate_commit": result["candidate_commit"], "method": method,
            "cases": counts["completed_cases"], "states": counts["states"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--verify-linux-native-existing", action="store_true")
    parser.add_argument("--verify-wasm-existing", action="store_true")
    parser.add_argument("--node-method", choices=MATRIX_METHODS)
    parser.add_argument("--verify-node-method-existing", action="store_true")
    parser.add_argument("--node-executable", type=Path)
    parser.add_argument("--expected-node-sha256")
    parser.add_argument("--expected-artifact-sha256")
    parser.add_argument("--expected-bundle-sha256")
    parser.add_argument("--expected-core-sha256")
    parser.add_argument("--hosts", nargs="+", choices=HOST_TASKS, default=list(HOST_TASKS))
    parser.add_argument("--jdk8-home", type=Path)
    parser.add_argument("--reference-dir", type=Path, action="append", default=[])
    parser.add_argument("--prospective-baseline", type=Path)
    parser.add_argument("--prospective-attestation", type=Path)
    parser.add_argument("--arithmetic-captures", type=Path)
    parser.add_argument("--node-modules", type=Path,
                        help="cached Node test modules for file-backed JS execution")
    parser.add_argument("--frozen-baseline", type=Path)
    parser.add_argument("--frozen-attestation", type=Path)
    args = parser.parse_args()
    if ("jvm8" in args.hosts and not (args.verify_linux_native_existing or
            args.verify_wasm_existing or args.node_method or
            args.verify_node_method_existing)):
        try:
            args.jdk8_home = selected_jdk8_home(args.jdk8_home)
        except Rejected as error:
            parser.error(str(error))
    if args.prospective_baseline is not None and args.prospective_attestation is None:
        parser.error("--prospective-baseline requires --prospective-attestation")
    if args.prospective_attestation is not None and args.prospective_baseline is None:
        parser.error("--prospective-attestation requires --prospective-baseline")
    if args.arithmetic_captures is not None and args.prospective_baseline is None:
        parser.error("--arithmetic-captures requires --prospective-baseline")
    output = Path(args.output).resolve()
    if args.node_method and args.verify_node_method_existing:
        parser.error("focused Node capture and replay are separate operations")
    selected = {"node": args.expected_node_sha256,
                "artifact": args.expected_artifact_sha256,
                "bundle": args.expected_bundle_sha256,
                "core": args.expected_core_sha256}
    if args.verify_node_method_existing and (args.node_executable is None or
            any(value is None for value in selected.values()) or
            any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in
                selected.values())):
        parser.error("focused Node replay requires executable and four selected SHA-256 values")
    if args.node_method or args.verify_node_method_existing:
        try:
            result = (capture_node_method(output, args.node_method,
                      args.node_modules or PORTABLE / "build/js/node_modules")
                      if args.node_method else verify_node_method_archive(output,
                          args.node_executable.resolve(), selected))
            print(json.dumps(result, sort_keys=True))
            return 0
        except (Rejected, OSError, ValueError, KeyError, TypeError) as error:
            print(json.dumps({"status": "FAILED", "reason": str(error)}, sort_keys=True))
            return 1
    if args.verify_linux_native_existing:
        try:
            result = verify_linux_native_archive(output)
            print(json.dumps(result, sort_keys=True))
            return 0
        except (Rejected, OSError, ValueError, KeyError, TypeError) as error:
            print(json.dumps({"status": "FAILED", "reason": str(error)}, sort_keys=True))
            return 1
    if args.verify_wasm_existing:
        try:
            if not args.hosts or any(host not in WASM_HOSTS for host in args.hosts):
                raise Rejected("Wasm replay requires only Wasm Node hosts")
            results = [verify_wasm_archive(output, host) for host in args.hosts]
            print(json.dumps(results, sort_keys=True))
            return 0
        except (Rejected, OSError, ValueError, KeyError, TypeError) as error:
            print(json.dumps({"status": "FAILED", "reason": str(error)}, sort_keys=True))
            return 1
    if output.exists():
        parser.error("output already exists")
    try:
        commit, source_sha256 = clean_identity()
        output.mkdir(parents=True)
        try:
            publication = stage(output, commit, source_sha256)
        except Rejected as error:
            results = [absent_lane(output, host, commit, source_sha256, "NOT_RUN",
                                   f"Staged publication failed: {error}") for host in HOST_TASKS]
            results += [absent_lane(output, name, commit, source_sha256, "NOT_RUN",
                                    f"Staged publication failed: {error}") for name in OTHER_LANES]
            summary = {"commit": commit, "source_sha256": source_sha256,
                       "status": "FAILED", "reason": str(error), "lanes": results}
            (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
            print(json.dumps(summary, sort_keys=True))
            return 1
        reference_dirs = args.reference_dir or [Path("/tmp/dyn4k-configured-control/baseline-trace")]
        results = [execute(host, output, commit, source_sha256, reference_dirs,
                           args.prospective_baseline, args.frozen_baseline,
                           args.frozen_attestation, args.prospective_attestation,
                           args.arithmetic_captures, args.node_modules, args.jdk8_home)
                   for host in args.hosts]
        for host in HOST_TASKS:
            if host not in args.hosts:
                results.append(absent_lane(output, host, commit, source_sha256, "NOT_RUN",
                                           "Host task was not selected for this invocation"))
        for name in OTHER_LANES:
            status, reason = other_lane_status(name)
            results.append(absent_lane(output, name, commit, source_sha256, status, reason))
        summary = {"commit": commit, "source_sha256": source_sha256,
                   "publication": publication, "lanes": results}
        (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(json.dumps(summary, sort_keys=True))
        return 0 if all(result["status"] == "PASSED" for result in results if result["host"] in args.hosts) else 1
    except (Rejected, OSError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "FAILED", "reason": str(error)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
