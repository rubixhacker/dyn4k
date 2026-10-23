import argparse
import csv
import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

import independent_linux_observer


ORIGINAL_REVISION = "058bf6d982a0fb89b54050f929f6ea9dae53b714"
REVIEWED_MAP_COMMIT = "16923c101f4c5f99e9f80ff829da63e6d51c1298"
REVIEWED_MAP_SHA256 = "d20877be61398e65037b0ec3d61134d9922248f608c7901ffe589fed8dff5496"
MAP_PATH = "tools/qualification/full-common-original-map.tsv"
MANIFEST_PATH = "tools/qualification/full-common-corpus.json"
PAIR_PATH = "tools/qualification/full-common-reviewed-pairs.tsv"
PAIR_FIELDS = ("original", "disposition", "classname", "method", "reason",
               "review", "review_sha256")
REVIEWED_PAIRS_SHA256 = "f92af322e9e02fba179737bc9401e5bf50a40c39dd62bf8c847ce1dc0e6b8e60"
ARTIFACT_SUFFIXES = {".class", ".jar", ".klib", ".kexe", ".wasm", ".js"}
NODE_PROBE_PATH = "tools/qualification/node_runtime_probe.cjs"
HOSTS = (
    ("jvm", "jvmTest", "[jvm]"),
    ("linuxX64", "linuxX64Test", "[linuxX64]"),
    ("jsNode", "jsNodeTest", "[js, node]"),
    ("wasmJsNode", "wasmJsNodeTest", "[wasmJs, node]"),
    ("wasmWasiNode", "wasmWasiNodeTest", "[wasmWasi, node]"),
    ("androidHost", "testAndroidHostTest", ""),
)
GROUPS = tuple({"id": ("core-" if module == "dyn4k-core" else "") + host,
                "module": module, "host": host, "suffix": suffix,
                "class_prefix": "" if host in ("jvm", "androidHost") else task + ".",
                "pattern": f"{module}/build/test-results/{task}/TEST-*.xml"}
               for host, task, suffix in HOSTS
               for module in ("dyn4k-core", "dyn4k"))
NODE_GROUPS = {group["id"] for group in GROUPS
               if group["host"] in ("jsNode", "wasmJsNode", "wasmWasiNode")}
GRADLE_COMMAND = ["./gradlew", "--no-daemon", "--max-workers=1", "--rerun-tasks",
                  "--continue", "--console=plain"] + [
                      f":{module}:{task}" for _, task, _ in HOSTS
                      for module in ("dyn4k-core", "dyn4k")]


def node_group_for_argv(repository, argv):
    repository = Path(repository).resolve()
    if not isinstance(argv, list) or len(argv) < 2 or not all(
            isinstance(part, str) for part in argv):
        return None
    argv = node_process_argv(repository, argv)
    mocha = repository / "build/js/node_modules/mocha/bin/mocha.js"
    runner = repository / ("build/js/node_modules/kotlin-web-helpers/dist/"
                           "kotlin-test-nodejs-runner.js")
    for module in ("dyn4k-core", "dyn4k"):
        prefix = "core-" if module == "dyn4k-core" else ""
        payload = repository / (f"build/js/packages/dyn4k-{module}-test/kotlin/"
                                f"dyn4k-{module}-test.js")
        if (argv[1:3] == [str(mocha), str(payload)]
                and any(argv[index:index + 2] == ["--require", str(runner)]
                        for index in range(3, len(argv) - 1))):
            return (prefix + "jsNode", payload)
        for host, candidate in (
                ("wasmJsNode", repository / f"build/wasm/packages/dyn4k-{module}-test/"
                 "static/runUnitTests.mjs"),
                ("wasmWasiNode", repository / module / "build/compileSync/wasmWasi/"
                 "test/testDevelopmentExecutable/kotlin/static/runUnitTests.mjs")):
            if argv[1:] == [str(candidate)]:
                return (prefix + host, candidate)
    return None


def node_launch_loader(repository, argv):
    loader = Path(repository).resolve() / ("build/js/node_modules/source-map-support/"
                                          "register.js")
    return loader if argv[1:3] == ["--require", str(loader)] else None


def node_process_argv(repository, argv):
    if len(argv) > 2 and argv[1] == "--experimental-wasm-modules":
        argv = [argv[0], *argv[2:]]
    if node_launch_loader(repository, argv) is not None:
        return [argv[0], *argv[3:]]
    return argv


def node_task(group_id):
    module = "dyn4k-core" if group_id.startswith("core-") else "dyn4k"
    host = group_id.removeprefix("core-")
    return f":{module}:{host}Test"


def observe_node_request(repository, request_file, gradle_pid, gradle_start_ticks,
                         started_ns):
    repository = Path(repository).resolve()
    request_file = Path(request_file)
    if request_file.is_symlink() or request_file.stat().st_size > 8192:
        raise ValueError("Node request is linked or oversized")
    raw = request_file.read_bytes()
    request = json.loads(raw)
    pid, nonce = request["pid"], request["nonce"]
    if (type(pid) is not int or pid <= 0 or not isinstance(nonce, str)
            or not re.fullmatch(r"[0-9a-f]{32}", nonce)
            or request_file.name != f"{pid}-{nonce}.json"):
        raise ValueError("Node request identity differs")
    observed_ns = time.time_ns()
    image = independent_linux_observer._image(pid)
    normalized_argv = node_process_argv(repository, image["argv"])
    if (normalized_argv[1:] != request["argv"][1:] or
            Path(image["argv"][0]).resolve() != Path(request["argv"][0]).resolve()):
        raise ValueError("live Node command differs from request")
    selection = node_group_for_argv(repository, image["argv"])
    if selection is None:
        raise ValueError("Node command is not a selected test runner")
    group_id, payload = selection
    if Path(request["execPath"]).resolve() != Path(image["executable_path"]).resolve():
        raise ValueError("live Node image path differs from request")
    ancestry = []
    current = pid
    for _ in range(32):
        identity = independent_linux_observer._stat(current)
        ancestry.append({"pid": current, **identity})
        if current == gradle_pid:
            if identity["start_ticks"] != gradle_start_ticks:
                raise ValueError("Gradle process start identity differs")
            break
        if identity["parent_pid"] <= 1:
            raise ValueError("Node test process is outside selected Gradle tree")
        current = identity["parent_pid"]
    else:
        raise ValueError("Node test ancestry exceeds bound")
    if ancestry[0]["start_ticks"] != image["start_ticks"]:
        raise ValueError("Node start identity changed during observation")
    executable = Path(image["executable_path"])
    if digest(executable.read_bytes()) != image["executable_sha256"]:
        raise ValueError("live Node executable bytes changed")
    version_env = os.environ.copy()
    version_env.pop("NODE_OPTIONS", None)
    version_env.pop("DYN4K_NODE_OBSERVATION_DIR", None)
    version = subprocess.run([str(executable), "--version"], env=version_env,
                             capture_output=True, text=True, timeout=3, check=True).stdout.strip()
    if version != request["version"] or not re.fullmatch(r"v\d+\.\d+\.\d+", version):
        raise ValueError("live Node version differs from executable version")
    if digest(executable.read_bytes()) != image["executable_sha256"]:
        raise ValueError("Node executable bytes changed after version check")
    payload_stat = payload.stat()
    if not started_ns <= payload_stat.st_mtime_ns <= observed_ns:
        raise ValueError("Node test payload predates invocation")
    relative_payload = payload.relative_to(repository).as_posix()
    loader = node_launch_loader(repository, image["argv"])
    return {"group_id": group_id, "task": node_task(group_id),
            "pid": pid, "start_ticks": image["start_ticks"],
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "observed_ns": observed_ns, "ancestry": ancestry,
            "executable_path": image["executable_path"],
            "executable_sha256": image["executable_sha256"],
            "version": version, "argv": image["argv"],
            "requested_argv": request["argv"],
            "requested_exec_path": request["execPath"],
            "payload_path": relative_payload, "payload_sha256": digest(payload.read_bytes()),
            "launch_loader_path": loader.relative_to(repository).as_posix() if loader else None,
            "launch_loader_sha256": digest(loader.read_bytes()) if loader else None,
            "request_name": request_file.name, "request_sha256": digest(raw),
            "nonce": nonce}
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
TOKEN = re.compile(r"\bclass\s+([A-Za-z_]\w*)|@Test\b|\bfun\s+([A-Za-z_]\w*)|[{}]")
PACKAGE = re.compile(r"(?m)^\s*package\s+([A-Za-z_][\w.]*)\s*$")
REVIEW_DOCS = {
    "integrated_collision_model": "portable-collision-model-coverage.md",
    "integrated_polygon": "portable-polygon-coverage.md",
    "integrated_body": "portable-body-coverage.md",
    "integrated_joint_core": "portable-joints-core.md",
    "integrated_joint_modes": "portable-joints-modes.md",
    "integrated_epsilon": "portable-epsilon-coverage.md",
    "pending_shape_pairs_a": "portable-shape-pairs-a.md",
    "pending_shape_pairs_b": "portable-shape-pairs-b.md",
    "pending_world_core": "portable-world-core.md",
    "pending_world_support": "portable-world-support-contact.md",
    "pending_simulation": "portable-simulation-coverage.md",
    "pending_broadphase_body": "portable-detection-body.md",
    "pending_broadphase_item": "portable-detection-item.md",
    "pending_detection": "portable-detection-coverage.md",
}
BODY_RELATED_SUPPLEMENTS = {
    "BodyValueCoverageTest.controlledWrongForceGetterFailsThePortableOracle":
        "org.dyn4j.dynamics.ForceTest#createSuccess",
    "PhysicsBodyCoverageTest.atRestTimeResetsAndDisabledDetectionKeepsBodyAwake":
        "org.dyn4j.dynamics.AbstractPhysicsBodyTest#updateAtRestTime",
    "PhysicsBodyCoverageTest.bodyCopyDuplicatesProtectedStateAndPendingCollections":
        "org.dyn4j.dynamics.BodyTest#copy",
    "PhysicsBodyCoverageTest.fixtureMassCompositionIgnoresZeroDensity":
        "org.dyn4j.dynamics.AbstractPhysicsBodyTest#setMass",
    "PhysicsBodyCoverageTest.fixtureViewAndMassAreLiveAcrossRemoval":
        "org.dyn4j.dynamics.AbstractPhysicsBodyTest#addFixtureByConvexBodyFixture",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical_digest(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode())


def committed_bytes(repository, revision, path):
    return subprocess.check_output(["git", "-C", str(repository), "show",
                                    f"{revision}:{path}"], stderr=subprocess.PIPE)


def paired_rows(mapping):
    return [{field: row[field] for field in PAIR_FIELDS} for row in mapping]


def paired_bytes(mapping):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=PAIR_FIELDS, delimiter="\t",
                            lineterminator="\n")
    writer.writeheader()
    writer.writerows(paired_rows(mapping))
    return output.getvalue().encode()


def allowed_generated_path(relative):
    parts = Path(relative).parts
    if not parts:
        return False
    if parts[0] in (".gradle", ".kotlin", "build", "kotlin-js-store", ".omo"):
        return True
    if (len(parts) > 1 and parts[0] in ("dyn4k-core", "dyn4k")
            and parts[1] in (".gradle", ".kotlin", "build", "kotlin-js-store")):
        return True
    if "src" in parts:
        return False
    if ".pytest_cache" in parts:
        return True
    return "__pycache__" in parts and parts[-1].endswith(".pyc")


def candidate_checkout_problems(repository, candidate_sha):
    repository = Path(repository)
    problems = []
    head = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"],
                                   text=True).strip()
    if head != candidate_sha:
        problems.append("candidate SHA differs from checkout")
    tracked = subprocess.check_output(["git", "-C", str(repository), "status",
                                       "--porcelain=v1", "--untracked-files=no"],
                                      text=True).strip()
    if tracked:
        problems.append("tracked candidate tree is dirty: " + tracked[:300])
    untracked = set()
    for ignored in (False, True):
        command = ["git", "-C", str(repository), "ls-files", "--others",
                   "--exclude-standard", "-z"]
        if ignored:
            command.append("--ignored")
        raw = subprocess.check_output(command)
        untracked.update(path for path in raw.decode("utf-8", "surrogateescape").split("\0")
                         if path)
    for path in sorted(untracked):
        if not allowed_generated_path(path):
            problems.append(f"untracked candidate input: {path}")
    return problems


def executable_identity(path, size, modified_ns):
    return {"path": path, "sha256": digest(Path(path).read_bytes()),
            "size": size, "modified_ns": modified_ns}


def capture_environment(repository):
    repository = Path(repository)
    executables = {}
    for name, command in (("java", ["-version"]), ("node", ["--version"])):
        found = shutil.which(name)
        if not found:
            executables[name] = None
            continue
        path = Path(found).resolve()
        stat = path.stat()
        identity = executable_identity(str(path), stat.st_size, stat.st_mtime_ns).copy()
        completed = subprocess.run([str(path), *command], capture_output=True,
                                   text=True, check=False)
        identity["version"] = (completed.stdout + completed.stderr).strip()
        identity["exit_code"] = completed.returncode
        executables[name] = identity
    wrapper = {}
    for relative in ("gradlew", "gradle/wrapper/gradle-wrapper.jar",
                     "gradle/wrapper/gradle-wrapper.properties"):
        path = repository / relative
        wrapper[relative] = digest(path.read_bytes()) if path.is_file() else None
    sdk = Path(os.environ["ANDROID_HOME"]) / "source.properties" if os.environ.get("ANDROID_HOME") else None
    return {"system": platform.system(), "machine": platform.machine(),
            "java_home": os.environ.get("JAVA_HOME"),
            "android_home": os.environ.get("ANDROID_HOME"),
            "android_sdk_source_sha256": digest(sdk.read_bytes()) if sdk and sdk.is_file() else None,
            "executables": executables, "gradle_wrapper": wrapper}


def node_observation_problems(repository, evidence_root, binding, started, finished):
    if binding.get("schema", 1) == 1:
        return []
    if binding.get("schema") != 2:
        return ["unknown common corpus binding schema"]
    repository, evidence_root = Path(repository).resolve(), Path(evidence_root).resolve()
    observations = binding.get("node_observations")
    if not isinstance(observations, list):
        return ["actual Node process observations are absent"]
    problems = []
    if binding.get("observation_platform") != "linux":
        problems.append("actual Node process observation is unsupported on this host")
    if binding.get("node_observation_errors"):
        problems.append("Node process observation failed during capture")
    probe = repository / NODE_PROBE_PATH
    if (not probe.is_file() or
            binding.get("node_probe_sha256") != digest(probe.read_bytes())):
        problems.append("Node startup probe source hash differs")
    directory = (evidence_root / "node-observations" if evidence_root != repository else
                 Path(binding.get("node_observation_dir", "")))
    if not directory.is_dir() or directory.is_symlink():
        return [*problems, "Node observation raw directory is absent or linked"]
    seen_groups, seen_processes, expected_files = set(), set(), set()
    for row in observations:
        try:
            group_id = row["group_id"]
            if group_id not in NODE_GROUPS or group_id in seen_groups:
                raise ValueError("missing, wrong, or duplicate Node group")
            seen_groups.add(group_id)
            pid, start_ticks = row["pid"], row["start_ticks"]
            if (type(pid) is not int or type(start_ticks) is not int or
                    pid <= 0 or start_ticks <= 0 or
                    (row["boot_id"], pid, start_ticks) in seen_processes):
                raise ValueError("duplicate or invalid Node process identity")
            seen_processes.add((row["boot_id"], pid, start_ticks))
            if (type(started) is not int or type(finished) is not int or
                    not started <= row["observed_ns"] <= finished):
                raise ValueError("stale Node process observation")
            if row["task"] != node_task(group_id):
                raise ValueError("Node task differs from group")
            selection = node_group_for_argv(repository, row["argv"])
            if selection is None or selection[0] != group_id:
                raise ValueError("Node command differs from selected group")
            payload = selection[1]
            relative_payload = payload.relative_to(repository).as_posix()
            if row["payload_path"] != relative_payload:
                raise ValueError("Node payload path differs from command")
            evidence_payload = evidence_root / relative_payload
            if (not evidence_payload.is_file() or evidence_payload.is_symlink() or
                    digest(evidence_payload.read_bytes()) != row["payload_sha256"]):
                raise ValueError("Node test payload bytes differ")
            if not started <= evidence_payload.stat().st_mtime_ns <= finished:
                raise ValueError("Node test payload is outside invocation window")
            loader = node_launch_loader(repository, row["argv"])
            loader_path = loader.relative_to(repository).as_posix() if loader else None
            if row["launch_loader_path"] != loader_path:
                raise ValueError("Node launch loader differs from command")
            if loader is not None and digest((evidence_root / loader_path).read_bytes()) != row[
                    "launch_loader_sha256"]:
                raise ValueError("Node launch loader bytes differ")
            if loader is None and row["launch_loader_sha256"] is not None:
                raise ValueError("unexpected Node launch loader hash")
            if row["report_sha256"] != canonical_digest(binding["reports"][group_id]):
                raise ValueError("Node group raw report binding differs")
            ancestry = row["ancestry"]
            if (not isinstance(ancestry, list) or not ancestry or len(ancestry) > 32 or
                    ancestry[0]["pid"] != pid or
                    ancestry[0]["start_ticks"] != start_ticks or
                    ancestry[-1]["pid"] != binding["gradle_pid"] or
                    ancestry[-1]["start_ticks"] != binding["gradle_start_ticks"] or
                    any(first["parent_pid"] != second["pid"] for first, second in
                        zip(ancestry, ancestry[1:]))):
                raise ValueError("Node process is outside observed Gradle ancestry")
            request_name = row["request_name"]
            if (request_name != f'{pid}-{row["nonce"]}.json' or
                    not re.fullmatch(r"[0-9a-f]{32}", row["nonce"])):
                raise ValueError("Node request name or nonce differs")
            ack_name = request_name.removesuffix(".json") + ".ack"
            expected_files.update((request_name, ack_name))
            request_file, ack_file = directory / request_name, directory / ack_name
            if (request_file.is_symlink() or ack_file.is_symlink() or
                    digest(request_file.read_bytes()) != row["request_sha256"] or
                    ack_file.read_text() != row["nonce"] or
                    digest(ack_file.read_bytes()) != row["ack_sha256"]):
                raise ValueError("Node startup request or acknowledgement differs")
            if (not started <= request_file.stat().st_mtime_ns <= finished or
                    not started <= ack_file.stat().st_mtime_ns <= finished):
                raise ValueError("Node startup request or acknowledgement is stale")
            request = json.loads(request_file.read_text())
            if (request != {"pid": pid, "nonce": row["nonce"],
                            "argv": row["requested_argv"],
                            "execPath": row["requested_exec_path"],
                            "version": row["version"]}):
                raise ValueError("Node startup request differs from live observation")
            if (row["requested_argv"][1:] !=
                    node_process_argv(repository, row["argv"])[1:] or
                    Path(row["requested_argv"][0]).resolve() !=
                    Path(row["argv"][0]).resolve() or
                    Path(row["requested_exec_path"]).resolve() !=
                    Path(row["executable_path"]).resolve()):
                raise ValueError("Node request command or executable differs")
            executable = Path(row["executable_path"])
            if (not executable.is_file() or executable.is_symlink() or
                    digest(executable.read_bytes()) != row["executable_sha256"]):
                raise ValueError("observed Node executable bytes changed")
            version_env = os.environ.copy()
            version_env.pop("NODE_OPTIONS", None)
            version_env.pop("DYN4K_NODE_OBSERVATION_DIR", None)
            actual_version = subprocess.run([str(executable), "--version"],
                                            env=version_env, capture_output=True,
                                            text=True, timeout=3, check=True).stdout.strip()
            if row["version"] != actual_version:
                raise ValueError("observed Node version differs from executable")
            if digest(executable.read_bytes()) != row["executable_sha256"]:
                raise ValueError("observed Node executable changed during replay")
        except (KeyError, OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
            problems.append(f"Node process binding differs: {error}")
    if seen_groups != NODE_GROUPS:
        problems.append(f"actual Node process groups missing: {sorted(NODE_GROUPS - seen_groups)}")
    if {path.name for path in directory.iterdir()} != expected_files:
        problems.append("Node observation raw file inventory differs")
    return problems


def capture_artifacts(repository, started_ns, finished_ns):
    repository = Path(repository)
    artifacts = []
    for module in ("dyn4k-core", "dyn4k"):
        root = repository / module / "build"
        for path in sorted(root.rglob("*")):
            if (path.is_file() and path.suffix in ARTIFACT_SUFFIXES
                    and started_ns <= path.stat().st_mtime_ns <= finished_ns):
                artifacts.append({"module": module,
                                  "path": path.relative_to(repository).as_posix(),
                                  "sha256": digest(path.read_bytes())})
    return artifacts


def artifact_binding_problems(repository, binding, started, finished, strict_paths,
                              check_mtime=True):
    artifacts = binding.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return ["candidate artifact binding is absent"]
    problems = []
    modules = set()
    names = set()
    for item in artifacts:
        try:
            module, name, bound = item["module"], item["path"], item["sha256"]
            path = Path(name)
            if module not in ("dyn4k-core", "dyn4k") or path.is_absolute() or ".." in path.parts:
                raise ValueError("invalid artifact path or module")
            if strict_paths and path.parts[:2] != (module, "build"):
                raise ValueError("candidate artifact is outside module build output")
            if name in names:
                raise ValueError("duplicate candidate artifact")
            names.add(name)
            source = repository / path
            if digest(source.read_bytes()) != bound:
                raise ValueError("candidate artifact SHA-256 differs")
            if (check_mtime and type(started) is int and type(finished) is int and
                    not started <= source.stat().st_mtime_ns <= finished):
                raise ValueError("candidate artifact is outside invocation window")
            modules.add(module)
        except (KeyError, OSError, TypeError, ValueError) as error:
            problems.append(f"candidate artifact binding differs: {error}")
    if modules != {"dyn4k-core", "dyn4k"}:
        problems.append("candidate artifacts are required for both modules")
    return problems


def archived_environment_problems(repository, environment, require_checkout):
    if not isinstance(environment, dict):
        return ["candidate environment receipt is absent"]
    if not require_checkout:
        return []
    problems = []
    wrappers = environment.get("gradle_wrapper")
    wrappers = wrappers if isinstance(wrappers, dict) else {}
    for relative in ("gradlew", "gradle/wrapper/gradle-wrapper.jar",
                     "gradle/wrapper/gradle-wrapper.properties"):
        path = repository / relative
        if not path.is_file() or wrappers.get(relative) != digest(path.read_bytes()):
            problems.append(f"candidate Gradle wrapper hash differs: {relative}")
    for name in ("java", "node"):
        executables = environment.get("executables")
        identity = executables.get(name) if isinstance(executables, dict) else None
        if (not isinstance(identity, dict)
                or not isinstance(identity.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", identity["sha256"])
                or identity.get("exit_code") != 0
                or not identity.get("version")):
            problems.append(f"candidate {name} identity receipt is invalid")
    return problems


def candidate_input_problems(repository, candidate_sha, manifest, mapping,
                             manifest_path=None, mapping_path=None,
                             check_checkout=True):
    problems = candidate_checkout_problems(repository, candidate_sha) if check_checkout else []
    paths = ((MANIFEST_PATH, manifest_path), (MAP_PATH, mapping_path))
    for relative, supplied in paths:
        canonical = repository / relative
        supplied = Path(supplied) if supplied is not None else canonical
        if supplied.resolve() != canonical.resolve():
            problems.append(f"untracked or alternate candidate input: {supplied}")
        try:
            committed = committed_bytes(repository, candidate_sha, relative)
            if supplied.read_bytes() != committed or canonical.read_bytes() != committed:
                problems.append(f"candidate commit bytes differ: {relative}")
            parsed = (json.loads(committed) if relative == MANIFEST_PATH else
                      list(csv.DictReader(io.StringIO(committed.decode()), delimiter="\t")))
            if parsed != (manifest if relative == MANIFEST_PATH else mapping):
                problems.append(f"candidate commit content differs: {relative}")
        except (OSError, UnicodeError, ValueError, subprocess.CalledProcessError) as error:
            problems.append(f"candidate commit input unavailable: {relative}: {error}")
    try:
        if candidate_sha == REVIEWED_MAP_COMMIT:
            reviewed = committed_bytes(repository, REVIEWED_MAP_COMMIT, MAP_PATH)
            if digest(reviewed) != REVIEWED_MAP_SHA256:
                problems.append("independently reviewed pair map hash differs")
            audited_rows = paired_rows(list(csv.DictReader(
                io.StringIO(reviewed.decode()), delimiter="\t")))
        else:
            reviewed = committed_bytes(repository, candidate_sha, PAIR_PATH)
            if reviewed != (repository / PAIR_PATH).read_bytes():
                problems.append("candidate commit bytes differ: " + PAIR_PATH)
            if digest(reviewed) != REVIEWED_PAIRS_SHA256:
                problems.append("independently reviewed pair map hash differs")
            audited_rows = list(csv.DictReader(io.StringIO(reviewed.decode()), delimiter="\t"))
        audited = {row["original"]: row for row in audited_rows}
        actual_rows = paired_rows(mapping)
        actual = {row["original"]: row for row in actual_rows}
        if len(audited) != len(audited_rows) or len(actual) != len(actual_rows):
            problems.append("duplicate original identity in reviewed pair map")
        for original in sorted(set(audited) | set(actual)):
            if audited.get(original) != actual.get(original):
                problems.append(f"reviewed pair differs: {original}")
    except (OSError, UnicodeError, ValueError, subprocess.CalledProcessError) as error:
        problems.append(f"independently reviewed pair map unavailable: {error}")
    return problems


def mask_noncode(source):
    result = list(source)
    index = 0
    while index < len(source):
        end = index
        if source.startswith("//", index):
            end = source.find("\n", index)
            if end < 0:
                end = len(source)
        elif source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end < 0:
                raise ValueError("unterminated block comment")
            end += 2
        elif source.startswith('"""', index):
            end = source.find('"""', index + 3)
            if end < 0:
                raise ValueError("unterminated raw string")
            end += 3
        elif source[index] in ('"', "'"):
            quote = source[index]
            end = index + 1
            while end < len(source):
                if source[end] == "\\":
                    end += 2
                elif source[end] == quote:
                    end += 1
                    break
                else:
                    end += 1
            if end > len(source) or source[end - 1] != quote:
                raise ValueError("unterminated string")
        if end > index:
            for offset in range(index, end):
                if source[offset] != "\n":
                    result[offset] = " "
            index = end
        else:
            index += 1
    return "".join(result)


def scan_sources(repository):
    repository = Path(repository)
    cases = []
    for module in ("dyn4k-core", "dyn4k"):
        for source_set in ("commonTest", "jvmTest"):
            root = repository / module / "src" / source_set / "kotlin"
            for path in sorted(root.rglob("*.kt")):
                raw = path.read_bytes()
                code = mask_noncode(raw.decode("utf-8"))
                package = PACKAGE.search(code)
                tokens = list(TOKEN.finditer(code))
                annotations = len(re.findall(r"@Test\b", code))
                depth = 0
                classes = []
                pending_class = None
                pending_test = False
                discovered = 0
                for token in tokens:
                    if token.group(1):
                        pending_class = token.group(1)
                    elif token.group(0) == "{":
                        depth += 1
                        if pending_class:
                            classes.append((pending_class, depth))
                            pending_class = None
                    elif token.group(0) == "}":
                        if classes and classes[-1][1] == depth:
                            classes.pop()
                        depth -= 1
                        if depth < 0:
                            raise ValueError(f"unbalanced source braces: {path}")
                    elif token.group(0) == "@Test":
                        if pending_test:
                            raise ValueError(f"consecutive test annotations: {path}")
                        pending_test = True
                    elif token.group(2) and pending_test:
                        if not package or not classes:
                            raise ValueError(f"test has no package or class: {path}")
                        classname = package.group(1) + "." + "$".join(
                            item[0] for item in classes)
                        relative = path.relative_to(repository).as_posix()
                        cases.append({"module": module, "source_set": source_set,
                                      "classname": classname, "method": token.group(2),
                                      "path": relative, "sha256": digest(raw),
                                      "line": code.count("\n", 0, token.start()) + 1,
                                      "hosts": ["jvm"] if source_set == "jvmTest"
                                      else [host for host, _, _ in HOSTS]})
                        pending_test = False
                        discovered += 1
                if pending_test or discovered != annotations:
                    raise ValueError(f"unresolved test annotation in {path}")
    if not cases or len({(c["module"], c["classname"], c["method"])
                         for c in cases}) != len(cases):
        raise ValueError("empty or duplicate common test inventory")
    return sorted(cases, key=lambda c: (c["module"], c["classname"], c["method"]))


def scan_test_tree(repository):
    repository = Path(repository)
    files = []
    for module in ("dyn4k-core", "dyn4k"):
        for source_set in ("commonTest", "jvmTest", "androidHostTest", "jsTest",
                           "nativeTest", "wasmJsTest", "wasmWasiTest"):
            root = repository / module / "src" / source_set
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    files.append({"path": path.relative_to(repository).as_posix(),
                                  "sha256": digest(path.read_bytes())})
    return sorted(files, key=lambda item: item["path"])


def source_tree_digest(source_files):
    return canonical_digest([(item["path"], item["sha256"]) for item in source_files])


def expected_cases(manifest, group):
    return {(group["class_prefix"] + case["classname"],
             case["method"] + group["suffix"])
            for case in manifest["cases"]
            if case["module"] == group["module"] and group["host"] in case["hosts"]}


def make_manifest(cases, mappings, production=False, repository=None):
    by_identity = {(case["module"], case["classname"], case["method"]): case
                   for case in cases}
    destinations = defaultdict(list)
    unresolved = []
    jvm_only = []
    for mapping in mappings:
        status = mapping["disposition"]
        if status == "JVM_ONLY":
            jvm_only.append(mapping)
        elif status == "PORTABLE":
            key = ("dyn4k-core", mapping["classname"], mapping["method"])
            if key not in by_identity or by_identity[key]["source_set"] != "commonTest":
                unresolved.append({"original": mapping["original"],
                                   "reason": "mapped common method is absent"})
            else:
                destinations[key].append(mapping["original"])
        else:
            unresolved.append({"original": mapping["original"],
                               "reason": mapping.get("reason", "unmapped")})
    decorated = []
    original_ids = {mapping["original"] for mapping in mappings}
    related_found = set()
    for case in cases:
        key = (case["module"], case["classname"], case["method"])
        related_key = case["classname"].split(".")[-1] + "." + case["method"]
        related = BODY_RELATED_SUPPLEMENTS.get(related_key)
        if related and case["module"] == "dyn4k-core" and related in original_ids:
            related_found.add(related_key)
        else:
            related = None
        decorated.append({**case, "originals": sorted(destinations.get(key, [])),
                          "related_original": related,
                          "kind": "mapped-original" if destinations.get(key)
                          else "platform-only" if case["source_set"] != "commonTest"
                          else "supplemental"})
    if production and len(related_found) != len(BODY_RELATED_SUPPLEMENTS):
        unresolved.append({"reason": "reviewed Body supplemental links are absent"})
    source_files = (scan_test_tree(repository) if repository is not None else
                    [{"path": path, "sha256": sha} for path, sha in sorted({
                        (case["path"], case["sha256"]) for case in cases})])
    return {"schema": 1, "kind": "full-common-corpus",
            "policy": "production" if production else "fixture",
            "source_tree_sha256": source_tree_digest(source_files),
            "source_files": source_files, "cases": decorated,
            "original_mappings": mappings, "jvm_only": jvm_only,
            "unresolved": unresolved,
            "counts": {"total_methods": len(cases),
                       "mapped_original_methods": len(destinations),
                       "mapped_original_identities": sum(len(v) for v in destinations.values()),
                       "reviewed_source_linked_methods": len(destinations) + len(related_found),
                       "related_supplemental_methods": len(related_found),
                       "supplemental_methods": sum(c["kind"] == "supplemental" for c in decorated),
                       "platform_only_methods": sum(c["kind"] == "platform-only" for c in decorated),
                       "jvm_only_original_identities": len(jvm_only),
                       "unresolved_mappings": len(unresolved)}}


def review_provenance(repository, owner, source_class, reference=None):
    if reference:
        path = reference
    elif owner == "pending_core_combined":
        shape_classes = {"AbstractShapeTest", "PolygonTest", "TriangleTest", "LinkTest",
                         "CapsuleTest", "EllipseTest", "HalfEllipseTest", "SliceTest",
                         "CircleTest", "RectangleTest", "RayTest", "SegmentTest",
                         "MassTest", "IntervalTest", "AABBTest", "FeatureTest",
                         "WoundTest", "RobustGeometryTest"}
        name = source_class.split(".")[-1]
        document = ("portable-geometry-factory.md" if name == "GeometryTest"
                    else "portable-geometry-shapes.md" if name in shape_classes
                    else "portable-foundation-coverage.md")
        path = "docs/verification/" + document
    else:
        path = "docs/verification/" + REVIEW_DOCS[owner]
    if not (Path(repository) / path).is_file():
        raise ValueError(f"missing reviewed report: {path}")
    return path, digest((Path(repository) / path).read_bytes())


def jvm_only_reason(original):
    source_class, method = original.split("#", 1)
    if original == "org.dyn4j.VersionTest#main":
        return "Captures System.out through Java PrintStream and ByteArrayOutputStream"
    if source_class.endswith(("CollisionBodyAABBProducerTest", "CollisionItemAABBProducerTest")):
        return "Calls a Java producer with null body, fixture, or result arguments"
    if source_class.endswith(("DistanceJointTest", "PulleyJointTest")):
        return "Passes null to a constructor body argument that is nonnull in common Kotlin"
    if method.endswith("NullArray") or method == "nullArray":
        return "Passes a null Java vararg array unavailable in common Kotlin"
    if source_class.endswith("Matrix22Test"):
        return "Passes null to a Java constructor parameter that is nonnull in common Kotlin"
    if "NullPoint" in method or method == "createNullPoints":
        return "Passes null to a geometry point parameter that is nonnull in common Kotlin"
    raise ValueError(f"unreviewed JVM-only disposition: {original}")


def reconcile_originals(repository, upstream, audit):
    repository, upstream = Path(repository), Path(upstream)
    revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"],
                                       text=True).strip()
    if revision != ORIGINAL_REVISION:
        raise ValueError("upstream source revision differs from pinned baseline")
    with Path(audit).open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    if len(rows) != 2385 or len({row["original_identity"] for row in rows}) != 2385:
        raise ValueError("reviewed original audit must have 2,385 unique executions")
    cases = [case for case in scan_sources(repository) if case["module"] == "dyn4k-core"]
    by_short = defaultdict(list)
    for case in cases:
        by_short[(case["classname"].split(".")[-1], case["method"])].append(case)
    overrides = {}
    detection = repository / "dyn4k-core/src/commonTest/kotlin/org/dyn4j/coverage/collision/detection/resources/source-case-map.tsv"
    with detection.open(newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if row["disposition"] == "PORTABLE":
                overrides[row["original_case"]] = (row["portable_case"].replace("#", "."),
                                                    detection.relative_to(repository).as_posix())
    support = repository / "docs/verification/portable-world-support-contact.md"
    for line in support.read_text().splitlines():
        columns = line.split("|")
        if len(columns) < 4:
            continue
        original = re.search(r"`(org\.dyn4j\.[\w.]+)`", columns[1])
        target = re.search(r"`(org\.dyn4j\.[\w.]+)`", columns[2])
        if original and target and "Test." in original.group(1):
            source_class, method = original.group(1).rsplit(".", 1)
            overrides[source_class + "#" + method] = (
                target.group(1), support.relative_to(repository).as_posix())
    mappings = []
    for row in rows:
        original = row["original_identity"]
        source_class, expanded_method = original.split("#", 1)
        method = expanded_method.split("[", 1)[0]
        source_path = "src/test/java/" + source_class.replace(".", "/") + ".java"
        source_file = upstream / source_path
        if not source_file.is_file():
            raise ValueError(f"missing pinned Java source: {source_path}")
        source_bytes = source_file.read_bytes()
        java = mask_noncode(source_bytes.decode("utf-8"))
        function = re.search(r"\bvoid\s+" + re.escape(method) + r"\s*\(", java)
        line = java.count("\n", 0, function.start()) + 1 if function else 0
        item = {"original": original, "original_source": source_path,
                "original_sha256": digest(source_bytes), "original_line": line,
                "disposition": "JVM_ONLY" if row["disposition"] == "JVM_ONLY" else "UNMAPPED",
                "review": row["owner"]}
        if row["disposition"] == "JVM_ONLY":
            item["reason"] = jvm_only_reason(original)
            item["review"], item["review_sha256"] = review_provenance(
                repository, row["owner"], source_class)
            mappings.append(item)
            continue
        selected = None
        reference = None
        direct = row["counterpart_or_reason"] if row["disposition"] == "PORTABLE" else None
        override = overrides.get(original)
        if override:
            direct, reference = override
        elif source_class == "org.dyn4j.geometry.GeometryTest":
            direct = "GeometryFactoryCoverageTest." + method
            reference = "docs/verification/portable-geometry-factory.md"
        if direct:
            names = re.findall(r"(?:[A-Za-z_]\w*\.)+[A-Za-z_]\w*", direct)
            if names:
                classname, target_method = names[0].rsplit(".", 1)
                candidates = by_short.get((classname.split(".")[-1], target_method), [])
                if "." in classname and classname.startswith("org."):
                    candidates = [case for case in candidates if case["classname"] == classname]
                if len(candidates) == 1:
                    selected = candidates[0]
        if selected is None:
            candidates = [case for case in cases if case["method"] == method]
            original_short = source_class.split(".")[-1]
            original_stem = original_short.removesuffix("Test").removeprefix("Abstract")
            ranked = []
            for case in candidates:
                short = case["classname"].split(".")[-1]
                stem = (short.removesuffix("Test").removesuffix("Coverage")
                        .removesuffix("Core").removeprefix("Upstream").removeprefix("Abstract"))
                score = 0
                if short == original_short:
                    score = 5
                elif stem == original_stem:
                    score = 4
                elif short in ("CollisionWorldCoreCoverageTest", "PhysicsWorldCoreCoverageTest"):
                    if original_short in ("AbstractCollisionWorldTest", "AbstractPhysicsWorldTest") and stem == original_stem.removesuffix("World") + "World":
                        score = 3
                if score:
                    ranked.append((score, case))
            if ranked:
                highest = max(score for score, _ in ranked)
                leaders = [case for score, case in ranked if score == highest]
                if len(leaders) == 1:
                    selected = leaders[0]
        if selected:
            item.update(disposition="PORTABLE", classname=selected["classname"],
                        method=selected["method"], review=reference or row["owner"])
        else:
            item["reason"] = "no unique reviewed common destination"
        item["review"], item["review_sha256"] = review_provenance(
            repository, row["owner"], source_class, reference)
        mappings.append(item)
    return mappings


def verify_reports(repository, manifest, candidate_sha, binding, reports,
                   mapping=None, upstream=None, require_checkout=False,
                   manifest_path=None, mapping_path=None, evidence_root=None):
    repository = Path(repository)
    evidence_root = Path(evidence_root) if evidence_root is not None else repository
    problems = []
    if manifest.get("kind") != "full-common-corpus" or manifest.get("schema") != 1:
        problems.append("full corpus manifest is invalid")
    if not SHA40.fullmatch(candidate_sha):
        problems.append("candidate SHA is invalid")
    if binding.get("candidate_sha") != candidate_sha:
        problems.append("candidate SHA differs from report binding")
    if binding.get("manifest_sha256") != canonical_digest(manifest):
        problems.append("manifest hash differs from report binding")
    if binding.get("schema", 1) not in (1, 2):
        problems.append("unknown common corpus binding schema")
    started = binding.get("started_ns")
    finished = binding.get("finished_ns")
    if (type(started) is not int or type(finished) is not int
            or started <= 0 or finished < started):
        problems.append("fresh report invocation window is invalid")
    command = binding.get("command")
    if command != GRADLE_COMMAND or type(binding.get("exit_code")) is not int or binding["exit_code"] != 0:
        problems.append("complete fresh Gradle invocation is missing or failed")
    log_path = binding.get("log")
    try:
        if not isinstance(log_path, str) or not log_path:
            raise ValueError("log path is absent")
        log_file = evidence_root / "gradle.log" if evidence_root != repository else Path(log_path)
        if not log_file.is_absolute():
            log_file = repository / log_file
        raw_log = log_file.read_bytes()
        if digest(raw_log) != binding.get("log_sha256"):
            raise ValueError("log SHA-256 differs")
        if (b"BUILD SUCCESSFUL" not in raw_log or
                any(("> Task " + task).encode() not in raw_log
                    for task in GRADLE_COMMAND[6:])):
            raise ValueError("successful twelve-task Gradle output is absent")
    except (OSError, ValueError) as error:
        problems.append(f"Gradle log binding differs: {error}")
    try:
        if evidence_root != repository:
            problems.extend(archived_environment_problems(
                repository, binding.get("environment"), require_checkout))
        else:
            environment = capture_environment(repository)
            if binding.get("environment") != environment:
                problems.append("candidate environment or tool identity differs")
            if require_checkout and (any(value is None for value in environment["gradle_wrapper"].values())
                                     or any(value is None or value["exit_code"] != 0
                                            for value in environment["executables"].values())):
                problems.append("candidate environment lacks required Gradle, Java, or Node tool identity")
    except (OSError, UnicodeError, ValueError) as error:
        problems.append(f"candidate environment or tool identity unavailable: {error}")
    problems.extend(artifact_binding_problems(evidence_root, binding, started, finished,
                                               require_checkout, evidence_root == repository))
    if mapping is not None and mapping != manifest.get("original_mappings"):
        problems.append("reviewed original map differs from manifest")
    if manifest.get("policy") == "production":
        if require_checkout and upstream is None:
            problems.append("pinned original source checkout is required")
        problems.extend(candidate_input_problems(
            repository, candidate_sha, manifest,
            mapping if mapping is not None else manifest.get("original_mappings", []),
            manifest_path, mapping_path, check_checkout=require_checkout))
    if upstream is not None:
        revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"],
                                           text=True).strip()
        if revision != ORIGINAL_REVISION:
            problems.append("pinned original source revision differs")
        original_rows = manifest.get("original_mappings", [])
        identities = [item.get("original") for item in original_rows]
        if len(identities) != len(set(identities)):
            problems.append("duplicate reviewed original identity")
        original_files = {}
        review_files = {}
        for item in original_rows:
            path = item.get("original_source", "")
            review = item.get("review", "")
            original_class = item.get("original", "").split("#", 1)[0]
            if path != "src/test/java/" + original_class.replace(".", "/") + ".java":
                problems.append(f"original identity source path differs: {item.get('original')}")
            if path not in original_files:
                source_file = Path(upstream) / path
                original_files[path] = source_file.read_bytes() if source_file.is_file() else None
            if review not in review_files:
                review_file = repository / review
                review_files[review] = review_file.read_bytes() if review_file.is_file() else None
            raw = original_files[path]
            if raw is None or digest(raw) != item.get("original_sha256"):
                problems.append(f"pinned original source hash differs: {path}")
            else:
                lines = raw.decode("utf-8").splitlines()
                line = int(item.get("original_line", 0))
                method = item.get("original", "").split("#")[-1].split("[")[0]
                if not 1 <= line <= len(lines) or not re.search(
                        r"\bvoid\s+" + re.escape(method) + r"\s*\(", lines[line - 1]):
                    problems.append(f"original declaration line differs: {item.get('original')}")
            if review_files[review] is None or digest(review_files[review]) != item.get("review_sha256"):
                problems.append(f"reviewed mapping report hash differs: {review}")
    if require_checkout and manifest.get("policy") != "production":
        problems.extend(candidate_checkout_problems(repository, candidate_sha))
    try:
        scanned = scan_sources(repository)
        regenerated = make_manifest(scanned, mapping if mapping is not None
                                    else manifest["original_mappings"],
                                    manifest.get("policy") == "production", repository)
        if regenerated != manifest:
            problems.append("source inventory or reviewed mapping differs from manifest")
        tree = source_tree_digest(scan_test_tree(repository))
        if tree != manifest.get("source_tree_sha256") or tree != binding.get("source_tree_sha256"):
            problems.append("source tree hash differs from report binding")
    except (KeyError, OSError, UnicodeError, ValueError) as error:
        problems.append(f"source inventory invalid: {error}")
    counts = manifest.get("counts", {})
    if counts.get("unresolved_mappings") != 0 or manifest.get("unresolved"):
        problems.append("unresolved original mappings")
    if manifest.get("policy") == "production":
        if (len(manifest["original_mappings"]) != 2385
                or counts.get("mapped_original_methods") != 2253
                or counts.get("reviewed_source_linked_methods") != 2258
                or counts.get("related_supplemental_methods") != 5
                or counts.get("mapped_original_identities") != 2353
                or counts.get("jvm_only_original_identities") != 32):
            problems.append("reviewed original mapping totals differ from frozen corpus")
    group_ids = {group["id"] for group in GROUPS}
    if set(reports) != group_ids or set(binding.get("reports", {})) != group_ids:
        problems.append("all six core and facade report groups are required")
    groups = []
    total = 0
    for group in GROUPS:
        group_id = group["id"]
        expected = expected_cases(manifest, group)
        paths = reports.get(group_id, [])
        bound = binding.get("reports", {}).get(group_id, {})
        names = {str(Path(path).relative_to(evidence_root)) for path in paths}
        if not paths or len(names) != len(paths) or set(bound) != names:
            problems.append(f"missing or extra report files: {group_id}")
        seen = Counter()
        failures = errors = skipped = 0
        hashes = {}
        for path in paths:
            path = Path(path)
            name = str(path.relative_to(evidence_root))
            try:
                raw = path.read_bytes()
                file_hash = digest(raw)
                hashes[name] = file_hash
                if bound.get(name) != file_hash:
                    problems.append(f"report hash differs from source binding: {name}")
                if (evidence_root == repository and type(started) is int and type(finished) is int
                        and not started <= path.stat().st_mtime_ns <= finished):
                    problems.append(f"report predates or postdates invocation: {name}")
                suite = ET.fromstring(raw)
                if suite.tag != "testsuite":
                    raise ValueError("XML root is not testsuite")
                suite_cases = list(suite.iter("testcase"))
                observed = {"tests": len(suite_cases),
                            "failures": sum(c.find("failure") is not None for c in suite_cases),
                            "errors": sum(c.find("error") is not None for c in suite_cases),
                            "skipped": sum(c.find("skipped") is not None for c in suite_cases)}
                for key, value in observed.items():
                    if suite.get(key) is None or int(suite.get(key)) != value:
                        raise ValueError(f"XML {key} count differs from cases")
                duration = float(suite.get("time", "nan"))
                if not 0 <= duration < float("inf"):
                    raise ValueError("suite duration is invalid")
                for case in suite_cases:
                    classname, method = case.get("classname"), case.get("name")
                    if not classname or not method or not 0 <= float(case.get("time", "nan")) < float("inf"):
                        raise ValueError("case identity or duration is invalid")
                    seen[classname, method] += 1
                failures += observed["failures"]
                errors += observed["errors"]
                skipped += observed["skipped"]
            except (OSError, ET.ParseError, TypeError, ValueError) as error:
                problems.append(f"invalid XML {name}: {error}")
        missing = sorted(expected - set(seen))
        extra = sorted(set(seen) - expected)
        duplicates = sorted(case for case, count in seen.items() if count != 1)
        if missing:
            problems.append(f"missing {len(missing)} expected cases in {group_id}: {missing[:3]}")
        if extra:
            problems.append(f"unexpected {len(extra)} cases in {group_id}: {extra[:3]}")
        if duplicates:
            problems.append(f"duplicate cases in {group_id}: {duplicates[:3]}")
        if failures or errors or skipped:
            problems.append(f"failed, errored, or skipped cases in {group_id}")
        total += sum(seen.values())
        groups.append({"id": group_id, "expected": len(expected), "reported": sum(seen.values()),
                       "mapped_original_methods": sum(c["kind"] == "mapped-original"
                                                      for c in manifest["cases"]
                                                      if c["module"] == group["module"]
                                                      and group["host"] in c["hosts"]),
                       "supplemental_cases": sum(c["kind"] == "supplemental"
                                                 for c in manifest["cases"]
                                                 if c["module"] == group["module"]
                                                 and group["host"] in c["hosts"]),
                       "platform_only_cases": sum(c["kind"] == "platform-only"
                                                  for c in manifest["cases"]
                                                  if c["module"] == group["module"]
                                                  and group["host"] in c["hosts"]),
                       "failures": failures, "errors": errors, "skipped": skipped,
                       "report_sha256": hashes})
        if binding.get("schema") == 2 and group_id in NODE_GROUPS:
            observed_nodes = binding.get("node_observations")
            observed_nodes = observed_nodes if isinstance(observed_nodes, list) else []
            matches = [row for row in observed_nodes if isinstance(row, dict)
                       and row.get("group_id") == group_id]
            groups[-1]["node_runtime"] = ({"status": "OBSERVED_UNSIGNED",
                                            "version": matches[0].get("version"),
                                            "executable_path": matches[0].get("executable_path"),
                                            "executable_sha256": matches[0].get("executable_sha256"),
                                            "pid": matches[0].get("pid"),
                                            "start_ticks": matches[0].get("start_ticks")}
                                           if len(matches) == 1 else {"status": "UNPASSED"})
    problems.extend(node_observation_problems(repository, evidence_root, binding,
                                              started, finished))
    result = {"schema": 2 if binding.get("schema") == 2 else 1,
              "kind": "full-common-corpus-verification",
              "candidate_sha": candidate_sha, "source_tree_sha256": manifest.get("source_tree_sha256"),
              "manifest_sha256": canonical_digest(manifest),
              "status": "UNPASSED" if problems else "PASSED", "problems": problems,
              "total_cases": total, "mapped_original_methods": counts.get("mapped_original_methods"),
              "reviewed_source_linked_methods": counts.get("reviewed_source_linked_methods"),
              "supplemental_cases": counts.get("supplemental_methods"),
              "platform_only_cases": counts.get("platform_only_methods"),
              "jvm_only_original_identities": counts.get("jvm_only_original_identities"),
              "groups": groups}
    return result


def archive_relative(name):
    if (not isinstance(name, str) or not name or "\\" in name or ":" in name
            or name.startswith("/")):
        raise ValueError(f"invalid archive path: {name}")
    relative = PurePosixPath(name)
    if relative.as_posix() != name or ".." in relative.parts or "." in relative.parts:
        raise ValueError(f"invalid archive path: {name}")
    return Path(*relative.parts)


def archive_status(candidate_sha, problems, corpus=None):
    return {"schema": 1, "kind": "full-common-archive-verification",
            "candidate_sha": candidate_sha, "status": "UNPASSED" if problems else "PASSED",
            "problems": problems, "corpus": corpus}


def package_archive(repository, archive, manifest, mapping, candidate_sha, binding,
                    reports, upstream=None, require_checkout=False,
                    manifest_path=None, mapping_path=None):
    repository, archive = Path(repository), Path(archive)
    result = verify_reports(repository, manifest, candidate_sha, binding, reports,
                            mapping=mapping, upstream=upstream,
                            require_checkout=require_checkout,
                            manifest_path=manifest_path, mapping_path=mapping_path)
    if result["status"] != "PASSED":
        raise ValueError("complete common corpus did not verify: " + "; ".join(result["problems"]))
    archive.mkdir(parents=True, exist_ok=True)
    evidence = archive / "evidence"
    if evidence.exists():
        raise ValueError("archive evidence directory already exists")
    evidence.mkdir()

    def write(name, data):
        target = evidence / archive_relative(name)
        if target.exists():
            raise ValueError(f"duplicate archive path: {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def copy(name, source):
        target = evidence / archive_relative(name)
        if target.exists() or source.is_symlink() or not source.is_file():
            raise ValueError(f"missing, linked, or duplicate archive input: {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    manifest_bytes = (Path(manifest_path).read_bytes() if manifest_path else
                      (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
    if mapping_path:
        mapping_bytes = Path(mapping_path).read_bytes()
    else:
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(mapping[0]), delimiter="\t",
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(mapping)
        mapping_bytes = stream.getvalue().encode()
    write("binding.json", (json.dumps(binding, indent=2, sort_keys=True) + "\n").encode())
    write("manifest.json", manifest_bytes)
    write("mapping.tsv", mapping_bytes)
    write("mapping.json", (json.dumps(mapping, indent=2, sort_keys=True) + "\n").encode())
    write("verified.json", (json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
    if manifest.get("policy") == "production":
        copy("reviewed-pairs.tsv", repository / PAIR_PATH)
    log = Path(binding["log"])
    copy("gradle.log", log if log.is_absolute() else repository / log)
    for item in binding["artifacts"]:
        name = item["path"]
        copy(name, repository / archive_relative(name))
    for bound in binding["reports"].values():
        for name in bound:
            copy(name, repository / archive_relative(name))
    if binding.get("schema") == 2:
        observation_dir = Path(binding["node_observation_dir"])
        loader_paths = set()
        for row in binding["node_observations"]:
            for name in (row["request_name"], row["request_name"].removesuffix(".json") + ".ack"):
                copy("node-observations/" + name, observation_dir / name)
            copy(row["payload_path"], repository / archive_relative(row["payload_path"]))
            if row["launch_loader_path"] is not None:
                loader_paths.add(row["launch_loader_path"])
        for name in sorted(loader_paths):
            copy(name, repository / archive_relative(name))

    files = {}
    for path in sorted(archive.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"linked archive input: {path}")
        if path.is_file() and path != archive / "archive-index.json":
            name = path.relative_to(archive).as_posix()
            files[name] = {"sha256": digest(path.read_bytes()),
                           "mtime_ns": path.stat().st_mtime_ns}
    index = {"schema": 1, "kind": "full-common-archive", "candidate_sha": candidate_sha,
             "original_revision": ORIGINAL_REVISION if upstream is not None else None,
             "bound_artifacts": sorted(item["path"] for item in binding["artifacts"]),
             "bound_reports": {group: sorted(bound) for group, bound in binding["reports"].items()},
             "files": files}
    (archive / "archive-index.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    return index


def verify_archive(archive, repository, candidate_sha, upstream=None, require_checkout=True):
    archive, repository = Path(archive), Path(repository)
    problems = []
    try:
        index = json.loads((archive / "archive-index.json").read_text())
        if (index.get("schema") != 1 or index.get("kind") != "full-common-archive"
                or index.get("candidate_sha") != candidate_sha):
            problems.append("archive candidate SHA or schema differs")
        if require_checkout and index.get("original_revision") != ORIGINAL_REVISION:
            problems.append("archive original revision differs")
        actual = {}
        for path in archive.rglob("*"):
            name = path.relative_to(archive).as_posix()
            archive_relative(name)
            if path.is_symlink():
                problems.append(f"linked archive member: {name}")
            elif path.is_file() and name != "archive-index.json":
                actual[name] = path
        recorded = index.get("files", {})
        if not isinstance(recorded, dict) or set(recorded) != set(actual):
            problems.append("archive file inventory differs")
        else:
            for name, path in actual.items():
                item = recorded[name]
                if (not isinstance(item, dict) or item.get("sha256") != digest(path.read_bytes())
                        or type(item.get("mtime_ns")) is not int or item["mtime_ns"] <= 0):
                    problems.append(f"archive byte or timestamp receipt differs: {name}")
        if problems:
            return archive_status(candidate_sha, problems)
        evidence = archive / "evidence"
        binding = json.loads((evidence / "binding.json").read_text())
        manifest = json.loads((evidence / "manifest.json").read_text())
        mapping = json.loads((evidence / "mapping.json").read_text())
        expected = {"binding.json", "manifest.json", "mapping.tsv", "mapping.json", "verified.json",
                    "gradle.log"}
        if manifest.get("policy") == "production":
            expected.add("reviewed-pairs.tsv")
            with (evidence / "mapping.tsv").open(newline="") as stream:
                if list(csv.DictReader(stream, delimiter="\t")) != mapping:
                    problems.append("archive mapping content differs")
            for archive_name, repo_name in (("manifest.json", MANIFEST_PATH),
                                            ("mapping.tsv", MAP_PATH),
                                            ("reviewed-pairs.tsv", PAIR_PATH)):
                if (evidence / archive_name).read_bytes() != committed_bytes(
                        repository, candidate_sha, repo_name):
                    problems.append(f"archive candidate source differs: {repo_name}")
        artifacts = [item["path"] for item in binding["artifacts"]]
        bound_reports = {group: sorted(bound) for group, bound in binding["reports"].items()}
        if index.get("bound_artifacts") != sorted(artifacts) or index.get("bound_reports") != bound_reports:
            problems.append("archive binding inventory differs")
        expected.update(artifacts)
        expected.update(name for bound in bound_reports.values() for name in bound)
        if binding.get("schema") == 2:
            for row in binding["node_observations"]:
                expected.add(row["payload_path"])
                if row["launch_loader_path"] is not None:
                    expected.add(row["launch_loader_path"])
                expected.add("node-observations/" + row["request_name"])
                expected.add("node-observations/" +
                             row["request_name"].removesuffix(".json") + ".ack")
        started, finished = binding.get("started_ns"), binding.get("finished_ns")
        timed = [*artifacts, *(name for bound in bound_reports.values() for name in bound)]
        if binding.get("schema") == 2:
            timed.extend(row["payload_path"] for row in binding["node_observations"])
        for name in timed:
            mtime = recorded.get("evidence/" + name, {}).get("mtime_ns")
            if (type(started) is not int or type(finished) is not int
                    or type(mtime) is not int or not started <= mtime <= finished):
                problems.append(f"archive invocation timestamp differs: {name}")
        actual_evidence = {path.relative_to(evidence).as_posix()
                           for path in evidence.rglob("*") if path.is_file()}
        if actual_evidence != expected:
            problems.append("archive evidence file set differs")
        for name in expected:
            archive_relative(name)
        if problems:
            return archive_status(candidate_sha, problems)
        reports = {group["id"]: [evidence / archive_relative(name)
                                  for name in binding["reports"].get(group["id"], {})]
                   for group in GROUPS}
        corpus = verify_reports(repository, manifest, candidate_sha, binding, reports,
                                mapping=mapping, upstream=upstream,
                                require_checkout=require_checkout,
                                manifest_path=repository / MANIFEST_PATH if require_checkout else None,
                                mapping_path=repository / MAP_PATH if require_checkout else None,
                                evidence_root=evidence)
        if corpus["status"] != "PASSED":
            problems.extend(corpus["problems"])
        if json.loads((evidence / "verified.json").read_text()) != corpus:
            problems.append("archive verification receipt differs")
        return archive_status(candidate_sha, problems, corpus)
    except (KeyError, OSError, TypeError, ValueError, subprocess.CalledProcessError) as error:
        return archive_status(candidate_sha, [f"archive unavailable or invalid: {error}"])


def main():
    parser = argparse.ArgumentParser(description="Source-derived full common corpus gate")
    sub = parser.add_subparsers(dest="operation", required=True)
    inventory = sub.add_parser("inventory")
    inventory.add_argument("--repository", type=Path, default=Path("."))
    inventory.add_argument("--mapping", type=Path, required=True)
    inventory.add_argument("--output", type=Path, required=True)
    inventory.add_argument("--report", type=Path)
    pairs = sub.add_parser("seal-pairs")
    pairs.add_argument("--mapping", type=Path, required=True)
    pairs.add_argument("--output", type=Path, required=True)
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--repository", type=Path, default=Path("."))
    reconcile.add_argument("--upstream", type=Path, required=True)
    reconcile.add_argument("--audit", type=Path, required=True)
    reconcile.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--repository", type=Path, default=Path("."))
    verify.add_argument("--candidate-sha", required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--mapping", type=Path, required=True)
    verify.add_argument("--upstream", type=Path, required=True)
    verify.add_argument("--binding", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)
    package = sub.add_parser("package-archive")
    package.add_argument("--repository", type=Path, default=Path("."))
    package.add_argument("--candidate-sha", required=True)
    package.add_argument("--manifest", type=Path, required=True)
    package.add_argument("--mapping", type=Path, required=True)
    package.add_argument("--upstream", type=Path, required=True)
    package.add_argument("--binding", type=Path, required=True)
    package.add_argument("--archive", type=Path, required=True)
    archived = sub.add_parser("verify-archive")
    archived.add_argument("--repository", type=Path, default=Path("."))
    archived.add_argument("--candidate-sha", required=True)
    archived.add_argument("--upstream", type=Path, required=True)
    archived.add_argument("--archive", type=Path, required=True)
    archived.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--repository", type=Path, default=Path("."))
    run.add_argument("--candidate-sha", required=True)
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--mapping", type=Path, required=True)
    run.add_argument("--upstream", type=Path, required=True)
    run.add_argument("--binding", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--log", type=Path, required=True)
    run.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.operation == "verify-archive":
        result = verify_archive(args.archive, args.repository, args.candidate_sha,
                                upstream=args.upstream)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"status": result["status"], "problems": result["problems"]}))
        return 0 if result["status"] == "PASSED" else 1
    if args.operation == "seal-pairs":
        raw_map = args.mapping.read_bytes()
        if digest(raw_map) != REVIEWED_MAP_SHA256:
            raise ValueError("mapping bytes differ from independently reviewed map")
        mapping = list(csv.DictReader(io.StringIO(raw_map.decode()), delimiter="\t"))
        sealed = paired_bytes(mapping)
        if digest(sealed) != REVIEWED_PAIRS_SHA256:
            raise ValueError("pairing bytes differ from independently reviewed pairs")
        args.output.write_bytes(sealed)
        print(json.dumps({"reviewed_pairs": len(mapping), "sha256": digest(sealed)}))
        return 0
    if args.operation == "reconcile":
        mappings = reconcile_originals(args.repository, args.upstream, args.audit)
        fields = ("original", "original_source", "original_sha256", "original_line",
                  "disposition", "classname", "method", "reason", "review",
                  "review_sha256")
        with args.output.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t",
                                    lineterminator="\n")
            writer.writeheader()
            writer.writerows(mappings)
        print(json.dumps({"total": len(mappings), "dispositions": dict(Counter(
            row["disposition"] for row in mappings))}, sort_keys=True))
        return 0 if all(row["disposition"] != "UNMAPPED" for row in mappings) else 1
    if args.operation == "inventory":
        with args.mapping.open(newline="") as stream:
            mappings = list(csv.DictReader(stream, delimiter="\t"))
        manifest = make_manifest(scan_sources(args.repository), mappings,
                                 production=True, repository=args.repository)
        args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        if args.report:
            groups = [{"id": group["id"], "expected": len(expected_cases(manifest, group)),
                       "module": group["module"], "host": group["host"]}
                      for group in GROUPS]
            report = {"schema": 1, "kind": "full-common-corpus-inventory",
                      "qualification_status": "NOT_RUN",
                      "inventory_status": "UNPASSED" if manifest["unresolved"] else "MAPPED",
                      "source_tree_sha256": manifest["source_tree_sha256"],
                      "manifest_sha256": canonical_digest(manifest),
                      "map_file_sha256": digest(args.mapping.read_bytes()),
                      "counts": manifest["counts"], "source_files": len(manifest["source_files"]),
                      "original_source_files": len({row["original_source"] for row in mappings}),
                      "review_reports": len({row["review"] for row in mappings}),
                      "expected_host_executions": sum(group["expected"] for group in groups),
                      "groups": groups, "unresolved": manifest["unresolved"]}
            args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(manifest["counts"], sort_keys=True))
        return 0 if not manifest["unresolved"] else 1
    manifest = json.loads(args.manifest.read_text())
    with args.mapping.open(newline="") as stream:
        mapping = list(csv.DictReader(stream, delimiter="\t"))
    if manifest.get("policy") != "production":
        raise ValueError("production full corpus manifest is required")
    if args.operation == "package-archive":
        binding = json.loads(args.binding.read_text())
        reports = {group["id"]: sorted(args.repository.glob(group["pattern"]))
                   for group in GROUPS}
        index = package_archive(args.repository, args.archive, manifest, mapping,
                                args.candidate_sha, binding, reports,
                                upstream=args.upstream, require_checkout=True,
                                manifest_path=args.manifest, mapping_path=args.mapping)
        print(json.dumps({"status": "PASSED", "files": len(index["files"]),
                          "candidate_sha": args.candidate_sha}))
        return 0
    if args.operation == "run":
        command = args.command[1:] if args.command and args.command[0] == "--" else args.command
        if command != GRADLE_COMMAND:
            raise ValueError("run command must exactly invoke all twelve Gradle host tasks")
        repository = args.repository.resolve()
        input_problems = candidate_input_problems(repository, args.candidate_sha,
                                                   manifest, mapping,
                                                   args.manifest, args.mapping)
        if input_problems:
            raise ValueError("candidate input is not reviewed: " + "; ".join(input_problems))
        if make_manifest(scan_sources(repository), mapping, production=True,
                         repository=repository) != manifest:
            raise ValueError("source inventory or reviewed map differs before run")
        if subprocess.check_output(["git", "-C", str(args.upstream), "rev-parse", "HEAD"],
                                   text=True).strip() != ORIGINAL_REVISION:
            raise ValueError("upstream source revision differs from pinned baseline")
        for group in GROUPS:
            for path in repository.glob(group["pattern"]):
                path.unlink()
        started = time.time_ns()
        observation_dir = args.binding.resolve().with_suffix(".node-observations")
        observation_dir.mkdir(mode=0o700)
        gradle_env = os.environ.copy()
        gradle_env.pop("NODE_OPTIONS", None)
        gradle_env.pop("DYN4K_NODE_OBSERVATION_DIR", None)
        if sys.platform == "linux":
            gradle_env["NODE_OPTIONS"] = "--require=" + str(repository / NODE_PROBE_PATH)
            gradle_env["DYN4K_NODE_OBSERVATION_DIR"] = str(observation_dir)
        node_observations, observation_errors, seen_requests = [], [], set()
        with args.log.open("wb") as log_stream:
            process = subprocess.Popen(command, cwd=repository, env=gradle_env,
                                       stdout=log_stream, stderr=subprocess.STDOUT)
            gradle_pid = process.pid
            gradle_start_ticks = (independent_linux_observer._stat(gradle_pid)["start_ticks"]
                                  if sys.platform == "linux" else None)
            deadline = time.monotonic() + 90 * 60
            while process.poll() is None:
                if time.monotonic() > deadline:
                    process.kill()
                    observation_errors.append("complete Gradle invocation exceeded 90 minutes")
                    break
                for request_file in sorted(observation_dir.glob("*.json")):
                    if request_file.name in seen_requests:
                        continue
                    seen_requests.add(request_file.name)
                    try:
                        row = observe_node_request(repository, request_file,
                                                   gradle_pid, gradle_start_ticks, started)
                        acknowledgement = observation_dir / request_file.name.replace(
                            ".json", ".ack")
                        acknowledgement.write_text(row["nonce"])
                        row["ack_sha256"] = digest(acknowledgement.read_bytes())
                        node_observations.append(row)
                    except (OSError, ValueError, KeyError, TypeError,
                            subprocess.SubprocessError) as error:
                        observation_errors.append(f"{request_file.name}: {error}")
                time.sleep(0.01)
            process.wait()
        finished = time.time_ns()
        report_paths = {group["id"]: sorted(repository.glob(group["pattern"]))
                        for group in GROUPS}
        bound_reports = {group_id: {
            str(path.relative_to(repository)): digest(path.read_bytes())
            for path in paths} for group_id, paths in report_paths.items()}
        for row in node_observations:
            row["report_sha256"] = canonical_digest(bound_reports[row["group_id"]])
        binding = {"schema": 2, "candidate_sha": args.candidate_sha,
                   "manifest_sha256": canonical_digest(manifest),
                   "source_tree_sha256": manifest["source_tree_sha256"],
                   "started_ns": started, "finished_ns": finished,
                   "command": command, "exit_code": process.returncode,
                   "log": str(args.log), "log_sha256": digest(args.log.read_bytes()),
                   "environment": capture_environment(repository),
                   "artifacts": capture_artifacts(repository, started, finished),
                   "reports": bound_reports, "observation_platform": sys.platform,
                   "node_probe_sha256": digest((repository / NODE_PROBE_PATH).read_bytes()),
                   "node_observation_dir": str(observation_dir),
                   "gradle_pid": gradle_pid, "gradle_start_ticks": gradle_start_ticks,
                   "node_observations": node_observations,
                   "node_observation_errors": observation_errors}
        args.binding.write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n")
    else:
        binding = json.loads(args.binding.read_text())
    reports = {group["id"]: sorted(args.repository.glob(group["pattern"])) for group in GROUPS}
    result = verify_reports(args.repository, manifest, args.candidate_sha,
                            binding, reports, mapping=mapping, upstream=args.upstream,
                            require_checkout=True, manifest_path=args.manifest,
                            mapping_path=args.mapping)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "problems": result["problems"]}))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
