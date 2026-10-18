import argparse
import hashlib
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
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cases import declared_cases
from receipt import Rejected, digest, inspect, records
from run import (MATRIX_METHODS, PORTABLE, ROOT, _provider_classes,
                 clean_identity, extract_xml, git, method_case_ids, runtime_identity)


PINNED_JAR_SHA256 = "204ca8dd55626ad3727b82dacb37df1800c5eff0d6bb6e782b6e5af5162b2b3e"
PINNED_SOURCE_REVISION = "058bf6d982a0fb89b54050f929f6ea9dae53b714"
BASELINE_PROJECT = PORTABLE / "baseline"
ATTESTATION_SCHEMA = "portable-baseline-attestation/1"
WORKER_PROOF_SCHEMA = "portable-baseline-worker/3"
CLASSPATH_ENTRY_NAMES = (
    "gradle-worker.jar", "test", "main", "dyn4j-6.0.0.jar",
    "kotlin-test-junit-2.4.20.jar", "kotlin-test-2.4.20.jar",
    "kotlin-stdlib-2.4.20.jar", "annotations-13.0.jar",
    "junit-4.13.2.jar", "hamcrest-core-1.3.jar",
)
TAP_CLASS_NAMES = frozenset({
    "org/dyn4j/geometry/RotationOperationTap.class",
    "org/dyn4j/geometry/RotationOperationTap$Call.class",
    "org/dyn4j/geometry/RotationOperationTap$Capture.class",
    "org/dyn4j/geometry/RotationOperationTap$Observation.class",
    "org/dyn4j/geometry/RotationOperationTap$Observation$Rotation.class",
    "org/dyn4j/geometry/RotationOperationTap$Observation$ToiAccepted.class",
})


def verifier_source_sha256():
    source = hashlib.sha256()
    for name in ("baseline_capture.py", "run.py", "cases.py", "receipt.py"):
        path = PORTABLE / name
        source.update(name.encode() + b"\0" + path.read_bytes() + b"\0")
    return source.hexdigest()


def _manifest_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _require_raw_archive(root, result):
    methods = result.get("methods", [])
    raw_counts = result.get("raw_counts", {})
    if not isinstance(methods, list) or not all(
            isinstance(item, dict) for item in methods) or \
            not isinstance(raw_counts, dict):
        raise Rejected("baseline raw archive method or case inventory differs")
    cases = raw_counts.get("per_case", {})
    if not isinstance(cases, dict):
        raise Rejected("baseline raw archive method or case inventory differs")
    if [item.get("method") for item in methods] != list(MATRIX_METHODS) or \
            set(cases) != {case["id"] for case in declared_cases()}:
        raise Rejected("baseline raw archive method or case inventory differs")
    lane = root / "baseline-jvm"
    required = [root / "dyn4j-6.0.0.jar", lane / "trace.jsonl"]
    required.extend(lane / "xml" / f"{name}.xml" for name in MATRIX_METHODS)
    required.extend(lane / f"gradle-{name}.log" for name in MATRIX_METHODS)
    required.extend(lane / "cases" / f"{case['id']}.jsonl"
                    for case in declared_cases())
    for file in required:
        if not file.is_file():
            raise Rejected(f"baseline raw archive file is absent: {file}")


def _attestation_fields(root, checked, seal, result):
    for key in ("status", "trace_sha256", "source_sha256",
                "fixture_source_sha256", "baseline_jar_sha256", "case_sha256"):
        if checked.get(key) != seal.get(key):
            raise Rejected("baseline current verification differs from original seal")
    attested = {"schema": ATTESTATION_SCHEMA, "archive_root": str(root),
                "verifier_source_sha256": verifier_source_sha256(),
                "verified_sha256": digest(root / "verified.json"),
                "result_sha256": digest(root / "result.json"),
                "case_map_sha256": _manifest_sha256(seal["case_sha256"]),
                "method_evidence_sha256": _manifest_sha256(result["methods"]),
                "xml_trace_counts": checked["xml_trace_counts"],
                "method_processes_verified": checked["method_processes_verified"],
                "captured_process_proofs": checked["captured_process_proofs"],
                "observed_process_sha256": checked["observed_process_sha256"]}
    for key in ("status", "trace_sha256", "source_sha256",
                "fixture_source_sha256", "baseline_jar_sha256"):
        attested[key] = seal[key]
    return attested


def verify_attestation(root, path):
    root = Path(root).resolve()
    path = Path(path).resolve()
    if path.is_relative_to(root):
        raise Rejected("baseline attestation must be external to the archive")
    attested = json.loads(path.read_text())
    seal = json.loads((root / "verified.json").read_text())
    result = json.loads((root / "result.json").read_text())
    if not all(isinstance(value, dict) for value in (attested, seal, result)):
        raise Rejected("baseline attestation or archive metadata is malformed")
    if attested.get("schema") != ATTESTATION_SCHEMA or \
            attested.get("archive_root") != str(root):
        raise Rejected("current baseline attestation is absent or for another archive")
    if attested.get("verifier_source_sha256") != verifier_source_sha256():
        raise Rejected("baseline attestation verifier source differs")
    if attested.get("verified_sha256") != digest(root / "verified.json") or \
            attested.get("result_sha256") != digest(root / "result.json"):
        raise Rejected("baseline attestation original seal differs")
    for key in ("status", "trace_sha256", "source_sha256",
                "fixture_source_sha256", "baseline_jar_sha256"):
        if attested.get(key) != seal.get(key):
            raise Rejected("baseline attestation source binding differs")
    if attested.get("trace_sha256") != result.get("trace_sha256") or \
            attested.get("case_map_sha256") != _manifest_sha256(seal.get("case_sha256")) or \
            attested.get("method_evidence_sha256") != \
            _manifest_sha256(result.get("methods")):
        raise Rejected("baseline attestation trace, case, or method seal differs")
    _require_raw_archive(root, result)
    checked = verify_archive(root, write_verified=False)
    expected = _attestation_fields(root, checked, seal, result)
    if json.dumps(attested, sort_keys=True, separators=(",", ":"), allow_nan=False) != \
            json.dumps(expected, sort_keys=True, separators=(",", ":"), allow_nan=False):
        raise Rejected("baseline attestation differs from current raw archive verification")
    return attested


def write_attestation(root, path):
    root = Path(root).resolve()
    path = Path(path).resolve()
    if path.is_relative_to(root) or path.exists():
        raise Rejected("baseline attestation output must be new and external")
    checked = verify_archive(root, write_verified=False)
    seal = json.loads((root / "verified.json").read_text())
    result = json.loads((root / "result.json").read_text())
    attested = _attestation_fields(root, checked, seal, result)
    path.write_text(json.dumps(attested, indent=2, sort_keys=True) + "\n")
    return attested


def verify_baseline_jar(path):
    if not Path(path).is_file() or digest(path) != PINNED_JAR_SHA256:
        raise Rejected("pinned dyn4j 6.0.0 JAR is absent or has changed bytes")
    return PINNED_JAR_SHA256


def _verify_source_identity(result):
    if result["baseline_jar_sha256"] != PINNED_JAR_SHA256 or \
            result["baseline_source_revision"] != PINNED_SOURCE_REVISION:
        raise Rejected("baseline source identity differs")
    if result["fixture_source_sha256"] != fixture_source_sha256():
        raise Rejected("baseline fixture source differs")
    revision = result.get("candidate_recorder_commit")
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise Rejected("recorder source revision is invalid")
    try:
        if git("--no-replace-objects", "cat-file", "-t", revision).strip() != b"commit":
            raise Rejected("recorder source revision is invalid")
        source = hashlib.sha256(git("--no-replace-objects", "-c", "core.autocrlf=false", "archive",
                                    "--format=tar", revision)).hexdigest()
    except (OSError, subprocess.CalledProcessError) as error:
        raise Rejected("recorder source revision is unavailable") from error
    if source != result["source_sha256"]:
        raise Rejected("captured recorder source archive differs")


def fixture_source_sha256():
    tap = BASELINE_PROJECT / "src/main/kotlin/org/dyn4j/geometry/RotationOperationTap.kt"
    if not tap.is_file():
        raise Rejected("baseline operation tap source is absent")
    names = sorted(path for directory in (PORTABLE / "src/commonMain/kotlin",
                                           PORTABLE / "src/commonTest/kotlin",
                                           BASELINE_PROJECT / "src/main/kotlin")
                   for path in directory.rglob("*.kt"))
    names += [BASELINE_PROJECT / "build.gradle.kts", BASELINE_PROJECT / "settings.gradle.kts"]
    result = hashlib.sha256()
    for path in names:
        result.update(str(path.relative_to(PORTABLE)).encode())
        result.update(b"\0")
        result.update(path.read_bytes())
        result.update(b"\0")
    return result.hexdigest()


def _archived_bytes(path, proof_dir):
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(
            proof_dir.resolve()):
        raise Rejected("baseline worker proof file is absent or outside the archive")
    return path.read_bytes()


def _tap_classes(proof_dir, stub_root, expected_hashes, capture):
    archive = proof_dir / "tap-classes"
    if capture:
        classes = _provider_classes(stub_root)
        if set(classes) != TAP_CLASS_NAMES:
            raise Rejected("baseline operation tap class set differs")
        for name, data in classes.items():
            target = archive / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    names = {str(path.relative_to(archive)) for path in archive.rglob("*.class")}
    if names != TAP_CLASS_NAMES:
        raise Rejected("baseline archived operation tap class set differs")
    classes = {name: _archived_bytes(archive / name, proof_dir) for name in TAP_CLASS_NAMES}
    hashes = {name: hashlib.sha256(classes[name]).hexdigest() for name in sorted(classes)}
    if not capture and hashes != expected_hashes:
        raise Rejected("baseline archived operation tap class hash differs")
    return classes, hashes


def _worker_classpath(command, proof_dir, expected, capture):
    arguments = [token for token in command if token.startswith("@")]
    if len(arguments) != 1:
        raise Rejected("baseline worker argument file inventory differs")
    original = arguments[0][1:]
    archive = proof_dir / "worker-args-0.txt"
    if capture:
        source = Path(original)
        if not source.is_file():
            raise Rejected("baseline worker argument file is absent")
        proof_dir.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(source.read_bytes())
    data = _archived_bytes(archive, proof_dir)
    identity = {"original_path": original, "sha256": hashlib.sha256(data).hexdigest()}
    if not capture and identity != expected:
        raise Rejected("baseline archived worker argument file differs")
    tokens = []
    for token in command[1:]:
        tokens.extend(shlex.split(data.decode("utf-8")) if token == arguments[0] else [token])
    classpaths = [tokens[index + 1] for index, token in enumerate(tokens[:-1])
                  if token in ("-cp", "-classpath", "--class-path")]
    if len(classpaths) != 1:
        raise Rejected("baseline worker classpath is absent or ambiguous")
    raw_entries = classpaths[0].split(os.pathsep)
    entries = [Path(raw) for raw in raw_entries]
    if not all(path.is_absolute() and ".." not in path.parts and str(path) == raw
               for path, raw in zip(entries, raw_entries)):
        raise Rejected("baseline worker classpath path is not canonical")
    return entries, identity


def _entry_files(root):
    if root.is_symlink() or not root.is_dir():
        raise Rejected("baseline classpath entry is absent or linked")
    files = {}
    for path in root.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise Rejected("baseline classpath entry contains a link or special file")
        if path.is_file():
            files[str(path.relative_to(root))] = path.read_bytes()
    return files


def _has_versioned_dyn4j_class(path):
    if not zipfile.is_zipfile(path):
        return False
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.startswith("META-INF/versions/") and "/org/dyn4j/" in name and \
                    name.endswith(".class"):
                return True
    return False


def _classpath_archive(entries, proof_dir, expected, capture, stub_origin, jar_origin,
                       pinned, tap, jar):
    if len(entries) != len(CLASSPATH_ENTRY_NAMES) or [path.name for path in entries] != list(
            CLASSPATH_ENTRY_NAMES) or str(entries[1]) != str(Path(stub_origin).with_name("test")) or \
            str(entries[2]) != stub_origin or str(entries[3]) != jar_origin:
        raise Rejected("baseline JVM classpath entry order differs")
    archive = proof_dir / "classpath-entries"
    if proof_dir.is_symlink() or proof_dir.parent.is_symlink() or archive.is_symlink():
        raise Rejected("baseline classpath archive is linked")
    if capture:
        archive.mkdir(parents=True, exist_ok=False)
    if not archive.is_dir() or (not capture and {path.name for path in archive.iterdir()} != {
            f"{index:02d}" for index in range(len(entries))}):
        raise Rejected("baseline classpath archive entry set differs")
    inventory = []
    for index, entry in enumerate(entries):
        target = archive / f"{index:02d}"
        kind = "directory" if index in (1, 2) else "file"
        if capture:
            target.mkdir()
            if kind == "directory":
                files = _entry_files(entry)
                for name, data in files.items():
                    destination = target / "tree" / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(data)
            else:
                if entry.is_symlink() or not entry.is_file():
                    raise Rejected("baseline classpath file is absent or linked")
                (target / "payload").write_bytes(entry.read_bytes())
        if target.is_symlink() or not target.is_dir():
            raise Rejected("baseline classpath archive entry is absent or linked")
        if kind == "directory":
            if {path.name for path in target.iterdir()} != {"tree"}:
                raise Rejected("baseline classpath archive directory differs")
            files = _entry_files(target / "tree")
            payload = target / "tree"
        else:
            if {path.name for path in target.iterdir()} != {"payload"}:
                raise Rejected("baseline classpath archive file differs")
            data = _archived_bytes(target / "payload", proof_dir)
            files = {"payload": data}
            payload = target / "payload"
        row = {"path": str(entry), "kind": kind,
               "files": {name: hashlib.sha256(data).hexdigest()
                         for name, data in sorted(files.items())}}
        inventory.append(row)
        classes = _provider_classes(payload)
        if kind == "file" and _has_versioned_dyn4j_class(payload):
            raise Rejected("baseline archived classpath has a versioned dyn4j provider")
        if index == 2:
            if classes != tap:
                raise Rejected("baseline archived main output has unexpected dyn4j classes")
        elif index == 3:
            if files["payload"] != jar.read_bytes() or classes != pinned:
                raise Rejected("baseline archived pinned JAR differs")
        elif classes:
            raise Rejected("baseline archived classpath has an unexpected dyn4j provider")
    if not capture and inventory != expected:
        raise Rejected("baseline archived classpath entry inventory differs")
    if {path.name for path in archive.iterdir()} != {
            f"{index:02d}" for index in range(len(entries))}:
        raise Rejected("baseline classpath archive entry set differs")
    return inventory


def _loaded_baseline_classes(log, pinned, tap, jar_origin, tap_origin):
    loaded = {}
    with Path(log).open(encoding="utf-8", errors="replace") as source:
        for line in source:
            found = re.search(r"\[class,load\] (org\.dyn4j\.[^ ]+) source: (file:[^ ]+)", line)
            if found is None:
                continue
            name = found.group(1).replace(".", "/") + ".class"
            origin = os.path.normpath(urllib.parse.unquote(urllib.parse.urlparse(
                found.group(2)).path))
            expected_origin = jar_origin if name in pinned else tap_origin if name in tap else None
            if origin != expected_origin:
                raise Rejected("baseline loaded class origin differs")
            loaded[name] = origin
    if loaded.get("org/dyn4j/geometry/Vector2.class") != jar_origin or \
            loaded.get("org/dyn4j/geometry/RotationOperationTap.class") != tap_origin:
        raise Rejected("baseline loaded provider proof is absent")
    return loaded


def baseline_runtime(log, jar, proof_dir, recorded=None):
    commands = []
    with Path(log).open(encoding="utf-8") as stream:
        for line in stream:
            if "Starting process 'Gradle Test Executor" in line and " Command: " in line:
                commands.append(shlex.split(line.rsplit(" Command: ", 1)[1]))
    if len(commands) != 1:
        raise Rejected("baseline JVM worker command is absent or ambiguous")
    command = commands[0]
    executable = Path(command[0]).resolve()
    if not executable.is_file():
        raise Rejected("baseline JVM executable is absent")
    version = subprocess.run((str(executable), "-version"), capture_output=True,
                             text=True, check=False)
    version_text = [line for line in (version.stdout + version.stderr).splitlines()
                    if line.startswith('openjdk version "')]
    if version.returncode or len(version_text) != 1 or \
            not version_text[0].startswith('openjdk version "21.'):
        raise Rejected("baseline JVM worker is not Java 21")
    proof_dir = Path(proof_dir)
    if recorded is not None and (not isinstance(recorded, dict) or
                                 not isinstance(recorded.get("dependency"), dict) or
                                 recorded["dependency"].get("schema") != WORKER_PROOF_SCHEMA):
        raise Rejected("baseline worker proof schema differs")
    recorded_dependency = recorded["dependency"] if recorded is not None else None
    entries, argument = _worker_classpath(
        command, proof_dir,
        recorded_dependency.get("argument_file") if recorded_dependency is not None else None,
        capture=recorded is None)
    jar = Path(jar).resolve()
    verify_baseline_jar(jar)
    pinned = _provider_classes(jar)
    if set(pinned) & TAP_CLASS_NAMES:
        raise Rejected("pinned dyn4j JAR contains baseline tap classes")
    if recorded_dependency is None:
        stub_origin = str((BASELINE_PROJECT / "build/classes/kotlin/main").resolve())
        jar_origin = str(jar)
    else:
        providers = recorded_dependency.get("providers", [])
        if len(providers) != 2 or [item.get("kind") for item in providers] != [
                "baseline-operation-tap", "pinned-dyn4j"]:
            raise Rejected("baseline recorded provider inventory differs")
        stub_origin = providers[0].get("path")
        jar_origin = providers[1].get("path")
        if not all(isinstance(path, str) and Path(path).is_absolute()
                   for path in (stub_origin, jar_origin)):
            raise Rejected("baseline recorded provider origin differs")
    tap, tap_hashes = _tap_classes(
        proof_dir, Path(stub_origin),
        recorded_dependency.get("tap_classes") if recorded_dependency is not None else None,
        capture=recorded is None)
    if set(tap) & set(pinned):
        raise Rejected("baseline operation tap overlaps pinned dyn4j")
    if [str(entry) for entry in entries].count(stub_origin) != 1 or \
            [str(entry) for entry in entries].count(jar_origin) != 1 or \
            entries.index(Path(stub_origin)) >= entries.index(Path(jar_origin)):
        raise Rejected("baseline JVM classpath provider order differs")
    inventory = _classpath_archive(
        entries, proof_dir,
        recorded_dependency.get("classpath_entries") if recorded_dependency is not None else None,
        capture=recorded is None, stub_origin=stub_origin, jar_origin=jar_origin,
        pinned=pinned, tap=tap, jar=jar)
    providers = [
        {"kind": "baseline-operation-tap", "path": stub_origin,
         "sha256": hashlib.sha256(b"".join(tap[name] for name in sorted(tap))).hexdigest(),
         "classes": len(tap)},
        {"kind": "pinned-dyn4j", "path": jar_origin,
         "sha256": digest(jar), "classes": len(pinned)},
    ]
    loaded = _loaded_baseline_classes(log, pinned, tap, jar_origin, stub_origin)
    if recorded_dependency is not None and \
            [str(entry) for entry in entries] != recorded_dependency.get("classpath"):
        raise Rejected("baseline recorded classpath differs")
    return {"host": "jvm", "os": platform.platform(), "machine": platform.machine(),
            "device": False, "executable": str(executable),
            "executable_sha256": digest(executable), "version": version_text[0],
            "process_executions": 1, "worker_command": command,
            "dependency": {"schema": WORKER_PROOF_SCHEMA,
                           "classpath": [str(entry) for entry in entries],
                           "providers": providers, "dependency_sha256": digest(jar),
                           "loaded_classes": loaded, "argument_file": argument,
                           "tap_classes": tap_hashes, "classpath_entries": inventory}}


def baseline_inventory(raw, xml):
    expected = {case["id"]: case for case in declared_cases()}
    observed = raw["per_case"]
    if observed.keys() != expected.keys():
        raise Rejected("baseline case identity differs from declared matrix")
    if raw["input_records"] != len(expected) or raw["completed_cases"] != len(expected):
        raise Rejected("baseline completed case count differs")
    if raw["states"] != sum(case["steps"] for case in expected.values()):
        raise Rejected("baseline state count differs")
    for case_id, case in expected.items():
        actual = observed[case_id]
        if (actual["inputs"] != 1 or actual["case_ends"] != 1 or
                actual["states"] != case["steps"]):
            raise Rejected(f"baseline case is incomplete: {case_id}")
        if case_id != "P-J-Angle-ratio-limits-off--1.0" and actual["tagged_nonfinite_values"]:
            raise Rejected(f"unexpected nonfinite baseline case: {case_id}")
    if any(xml.get(key) != expected_value for key, expected_value in
           (("tests", len(MATRIX_METHODS)), ("skipped", 0), ("failures", 0), ("errors", 0))):
        raise Rejected("baseline JUnit methods are incomplete")
    return {"cases": len(expected), "states": raw["states"],
            "tagged_nonfinite_values": sum(item["tagged_nonfinite_values"]
                                            for item in observed.values())}


def bounded_inventory(raw, xml, method):
    ids = method_case_ids(method)
    cases = {case["id"]: case for case in declared_cases() if case["id"] in set(ids)}
    if raw["expected_cases"] != len(ids) or set(raw["per_case"]) != set(ids) or \
            raw["input_records"] != len(ids) or raw["completed_cases"] != len(ids) or \
            raw["states"] != sum(case["steps"] for case in cases.values()):
        raise Rejected("bounded baseline method inventory differs")
    for case_id, case in cases.items():
        observed = raw["per_case"][case_id]
        if observed["inputs"] != 1 or observed["case_ends"] != 1 or \
                observed["states"] != case["steps"] or observed["tagged_nonfinite_values"]:
            raise Rejected(f"bounded baseline case is incomplete: {case_id}")
    if any(int(xml.get(key, -1)) != value for key, value in
           (("tests", 1), ("skipped", 0), ("failures", 0), ("errors", 0))):
        raise Rejected("bounded baseline JUnit method is incomplete")
    return {"method": method, "cases": len(ids), "states": raw["states"]}


def angle_failure(lane):
    case = lane / "cases/P-J-Angle-ratio-limits-off--1.0.jsonl"
    first_nonfinite_step = None
    first_angular_velocity_nonfinite_step = None
    first_nonfinite_fields = []

    def tagged_fields(value, path):
        if isinstance(value, dict):
            if "nonfinite" in value:
                yield path
            else:
                for key, child in value.items():
                    yield from tagged_fields(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from tagged_fields(child, f"{path}[{index}]")

    for row in records(case, allow_tagged_nonfinite=True):
        if row.get("kind") != "state":
            continue
        if first_nonfinite_step is None:
            first_nonfinite_fields = list(tagged_fields(row["state"], "state"))
            if first_nonfinite_fields:
                first_nonfinite_step = row["step"]
        if first_angular_velocity_nonfinite_step is None and any(
                isinstance(body.get("angularVelocity"), dict) and
                "nonfinite" in body["angularVelocity"]
                for body in row["state"]["bodies"]):
            first_angular_velocity_nonfinite_step = row["step"]
        if first_nonfinite_step is not None and first_angular_velocity_nonfinite_step is not None:
            break
    if first_nonfinite_step != 87:
        raise Rejected(f"baseline Angle first nonfinite step changed: {first_nonfinite_step}")
    if first_angular_velocity_nonfinite_step != 171:
        raise Rejected("baseline Angle angular velocity first nonfinite step changed: " +
                       str(first_angular_velocity_nonfinite_step))
    return {"status": "FAILED_PHYSICAL", "case_id": "P-J-Angle-ratio-limits-off--1.0",
            "first_nonfinite_step": first_nonfinite_step,
            "first_nonfinite_fields": first_nonfinite_fields,
            "first_angular_velocity_nonfinite_step": first_angular_velocity_nonfinite_step}


def verify_method_files(lane, methods):
    if len({item["method"] for item in methods}) != len(methods):
        raise Rejected("duplicate baseline method")
    for item in methods:
        if item["gradle_exit"]:
            raise Rejected(f"baseline method failed: {item['method']}")
        method = item["method"]
        for file, field, label in ((lane / "xml" / f"{method}.xml", "xml_sha256", "XML"),
                                   (lane / f"gradle-{method}.log", "log_sha256", "log")):
            if not file.is_file() or digest(file) != item[field]:
                raise Rejected(f"baseline {label} hash differs: {method}")


def verify_xml_trace(lane, methods, raw_counts, trace_sha256):
    trace = lane / "trace.jsonl"
    if digest(trace) != trace_sha256:
        raise Rejected("baseline original trace hash differs")
    observed = {}
    totals = {"input_records": 0, "completed_cases": 0, "states": 0,
              "tagged_nonfinite_values": 0, "events": 0, "endpoints": 0}
    with trace.open("rb") as whole:
        for method in methods:
            completed = 0
            started = 0
            active = None
            method_order = method_case_ids(method["method"])
            xml = lane / "xml" / f"{method['method']}.xml"
            with xml.open("rb") as source:
                for line in source:
                    if b"NUMERICAL_JSON " not in line:
                        continue
                    payload = line.split(b"NUMERICAL_JSON ", 1)[1].split(b"]]>", 1)[0].rstrip(b"\r\n")
                    if whole.readline() != payload + b"\n":
                        raise Rejected("baseline XML differs from whole trace")
                    row = json.loads(payload)
                    case_id = row.get("id")
                    kind = row.get("kind")
                    if kind == "inputs":
                        if active is not None or started >= len(method_order) or \
                                case_id != method_order[started]:
                            raise Rejected("baseline XML method case order differs")
                        started += 1
                        active = case_id
                    elif active != case_id:
                        raise Rejected("baseline XML row is outside its method case")
                    if kind == "case-end":
                        active = None
                    if case_id not in raw_counts["per_case"]:
                        raise Rejected("baseline XML has an undeclared case")
                    count = observed.setdefault(case_id, {"inputs": 0, "states": 0,
                        "events": 0, "endpoints": 0, "case_ends": 0,
                        "tagged_nonfinite_values": 0})
                    field = {"inputs": "inputs", "state": "states", "event": "events",
                             "endpoint": "endpoints", "case-end": "case_ends"}.get(kind)
                    if field is not None:
                        count[field] += 1
                        if field == "case_ends":
                            completed += 1
                            totals["completed_cases"] += 1
                        elif field == "inputs":
                            totals["input_records"] += 1
                        else:
                            totals[field] += 1
                    tagged = payload.count(b'"nonfinite":')
                    count["tagged_nonfinite_values"] += tagged
                    totals["tagged_nonfinite_values"] += tagged
            if active is not None or started != len(method_order) or \
                    completed != method["completed_cases"]:
                raise Rejected(f"baseline XML method case count differs: {method['method']}")
        if whole.read(1):
            raise Rejected("baseline XML is shorter than whole trace")
    if observed != raw_counts["per_case"]:
        raise Rejected("baseline XML per-case counts differ from capture")
    if any(totals[key] != raw_counts[key] for key in
           ("input_records", "completed_cases", "states", "tagged_nonfinite_values")):
        raise Rejected("baseline XML totals differ from capture")
    if raw_counts["expected_cases"] != len(observed):
        raise Rejected("baseline XML expected case count differs")
    return totals


def verify_case_slices(lane, expected_ids):
    expected_ids = set(expected_ids)
    if not expected_ids:
        raise Rejected("baseline case set is empty")
    active = None
    seen = set()
    case_stream = None
    try:
        with (lane / "trace.jsonl").open("rb") as stream:
            for line in stream:
                row = json.loads(line)
                case_id = row.get("id")
                if row.get("kind") == "inputs":
                    if active is not None or case_id not in expected_ids or case_id in seen:
                        raise Rejected("baseline trace case identity differs")
                    active = case_id
                    case_stream = (lane / "cases" / f"{case_id}.jsonl").open("rb")
                if active != case_id or case_stream is None or case_stream.readline() != line:
                    raise Rejected(f"baseline case slice differs: {case_id}")
                if row.get("kind") == "case-end":
                    if case_stream.read(1):
                        raise Rejected(f"baseline case slice has extra records: {case_id}")
                    case_stream.close()
                    case_stream = None
                    seen.add(case_id)
                    active = None
    finally:
        if case_stream is not None:
            case_stream.close()
    if active is not None or seen != expected_ids:
        raise Rejected("baseline case slice set differs")
    return {case_id: digest(lane / "cases" / f"{case_id}.jsonl") for case_id in sorted(seen)}


def verify_archive(output, write_verified=True):
    result = json.loads((output / "result.json").read_text())
    lane = output / "baseline-jvm"
    if result["status"] not in ("CAPTURED_WITH_FAILED_ANGLE_PHYSICAL", "FAILED") or \
            (result["status"] == "FAILED" and result.get("reason") !=
             "baseline Angle first nonfinite step changed: 87"):
        raise Rejected("baseline capture failed for an unrelated reason")
    verify_baseline_jar(output / "dyn4j-6.0.0.jar")
    _verify_source_identity(result)
    if [item["method"] for item in result["methods"]] != list(MATRIX_METHODS):
        raise Rejected("baseline method inventory differs")
    verify_method_files(lane, result["methods"])
    xml_trace_counts = verify_xml_trace(lane, result["methods"], result["raw_counts"],
                                        result["trace_sha256"])
    recorded_runtime = result["runtime"]
    if recorded_runtime["method_executions"] != len(MATRIX_METHODS) or \
            digest(recorded_runtime["executable"]) != recorded_runtime["executable_sha256"]:
        raise Rejected("baseline JVM execution identity differs")
    observed_processes = []
    for method in result["methods"]:
        recorded = method.get("process")
        if not isinstance(recorded, dict):
            raise Rejected("baseline method process proof is absent")
        process = baseline_runtime(lane / f"gradle-{method['method']}.log",
                                   output / "dyn4j-6.0.0.jar",
                                   lane / "process-proof" / method["method"], recorded)
        if any(recorded_runtime.get(key) != value for key, value in
               runtime_identity(process).items()):
            raise Rejected("baseline method runtime identity differs")
        if recorded != process:
            raise Rejected("baseline recorded worker command differs")
        observed_processes.append(process)
    if recorded_runtime.get("dependency_sha256", PINNED_JAR_SHA256) != PINNED_JAR_SHA256:
        raise Rejected("baseline runtime dependency hash differs")
    if "method_process_sha256" in recorded_runtime and \
            hashlib.sha256(json.dumps([item["process"] for item in result["methods"]],
                                   sort_keys=True).encode()).hexdigest() != \
            recorded_runtime["method_process_sha256"]:
        raise Rejected("baseline recorded process inventory differs")
    inventory = baseline_inventory(result["raw_counts"], result["xml"])
    if inventory != result["inventory"]:
        raise Rejected("baseline recorded inventory differs")
    inspected = inspect(lane / "trace.jsonl", declared_cases(), allow_tagged_nonfinite=True)
    if inspected["executed_cases"] != inventory["cases"] or \
            inspected["states"] != inventory["states"]:
        raise Rejected("baseline trace inventory differs")
    case_sha256 = verify_case_slices(lane, result["raw_counts"]["per_case"])
    verified = {
        "status": "CAPTURED_WITH_FAILED_ANGLE_PHYSICAL", "qualification": "UNPASSED",
        "capture_status": result["status"], "capture_reason": result.get("reason"),
        "candidate_recorder_commit": result["candidate_recorder_commit"],
        "source_sha256": result["source_sha256"],
        "fixture_source_sha256": result["fixture_source_sha256"],
        "baseline_source_revision": PINNED_SOURCE_REVISION,
        "baseline_jar_sha256": PINNED_JAR_SHA256,
        "runtime": recorded_runtime, "xml": result["xml"], "inventory": inventory,
        "xml_trace_counts": xml_trace_counts,
        "method_processes_verified": len(observed_processes),
        "captured_process_proofs": sum("process" in item for item in result["methods"]),
        "observed_process_sha256": _manifest_sha256(observed_processes),
        "trace_counts": inspected, "trace_sha256": digest(lane / "trace.jsonl"),
        "case_sha256": case_sha256, "angle_physical": angle_failure(lane),
        "methods": result["methods"],
    }
    if write_verified:
        (output / "verified.json").write_text(json.dumps(verified, indent=2, sort_keys=True) + "\n")
    return verified


def verify_bounded_archive(output):
    output = Path(output)
    result = json.loads((output / "result.json").read_text())
    if result.get("status") != "BOUNDED_METHOD" or result.get("qualification") != "UNPASSED":
        raise Rejected("bounded baseline capture status differs")
    method = result.get("bounded_method")
    if method not in MATRIX_METHODS or [item.get("method") for item in result["methods"]] != [method]:
        raise Rejected("bounded baseline method identity differs")
    lane = output / "baseline-jvm"
    jar = output / "dyn4j-6.0.0.jar"
    verify_baseline_jar(jar)
    _verify_source_identity(result)
    methods = result["methods"]
    verify_method_files(lane, methods)
    trace = lane / "trace.jsonl"
    if digest(trace) != result["trace_sha256"]:
        raise Rejected("bounded baseline trace hash differs")
    raw = result["raw_counts"]
    inventory = bounded_inventory(raw, result["xml"], method)
    if inventory != result["inventory"]:
        raise Rejected("bounded baseline recorded inventory differs")
    xml_counts = verify_xml_trace(lane, methods, raw, result["trace_sha256"])
    if xml_counts != result["xml_trace_counts"]:
        raise Rejected("bounded baseline XML trace counts differ")
    case_hashes = verify_case_slices(lane, method_case_ids(method))
    if case_hashes != result["case_sha256"]:
        raise Rejected("bounded baseline case slice hashes differ")
    cases = [case for case in declared_cases() if case["id"] in set(method_case_ids(method))]
    trace_counts = inspect(trace, cases)
    if trace_counts != result["trace_counts"]:
        raise Rejected("bounded baseline trace inspection differs")
    xml = lane / "xml" / f"{method}.xml"
    if b"PROSPECTIVE_ROTATION_JSON " in xml.read_bytes() or \
            b"PROSPECTIVE_BINDING_JSON " in xml.read_bytes():
        raise Rejected("bounded old-source baseline has prospective observations")
    recorded = methods[0].get("process")
    if not isinstance(recorded, dict):
        raise Rejected("bounded baseline process proof is absent")
    observed = baseline_runtime(lane / f"gradle-{method}.log", jar,
                                lane / "process-proof" / method, recorded)
    if observed != recorded:
        raise Rejected("bounded baseline recorded process differs")
    runtime = result["runtime"]
    if runtime.get("method_executions") != 1 or \
            runtime.get("dependency_sha256") != PINNED_JAR_SHA256 or \
            runtime.get("method_process_sha256") != hashlib.sha256(json.dumps(
                [recorded], sort_keys=True).encode()).hexdigest() or \
            any(runtime.get(key) != value for key, value in runtime_identity(observed).items()):
        raise Rejected("bounded baseline runtime identity differs")
    return {"status": "BOUNDED_VERIFIED", "qualification": "UNPASSED",
            "method": method, "inventory": inventory, "xml": result["xml"],
            "xml_trace_counts": xml_counts, "trace_counts": trace_counts,
            "case_sha256": case_hashes, "trace_sha256": result["trace_sha256"],
            "baseline_jar_sha256": PINNED_JAR_SHA256,
            "fixture_source_sha256": result["fixture_source_sha256"],
            "source_sha256": result["source_sha256"],
            "candidate_recorder_commit": result["candidate_recorder_commit"],
            "process_sha256": _manifest_sha256(observed)}


def capture(output, baseline_jar, bounded_method=None):
    if bounded_method is not None and bounded_method not in MATRIX_METHODS:
        raise Rejected("unknown bounded baseline method")
    methods = (bounded_method,) if bounded_method is not None else MATRIX_METHODS
    commit, source_sha256 = clean_identity()
    fixture_sha256 = fixture_source_sha256()
    verify_baseline_jar(baseline_jar)
    output.mkdir(parents=True, exist_ok=False)
    jar = output / "dyn4j-6.0.0.jar"
    shutil.copyfile(baseline_jar, jar)
    verify_baseline_jar(jar)
    lane = output / "baseline-jvm"
    lane.mkdir()
    result = {"status": "FAILED", "qualification": "UNPASSED",
              "candidate_recorder_commit": commit, "source_sha256": source_sha256,
              "fixture_source_sha256": fixture_sha256,
              "baseline_source_revision": PINNED_SOURCE_REVISION,
              "baseline_jar_sha256": PINNED_JAR_SHA256, "methods": []}
    raw = {"expected_cases": len(method_case_ids(bounded_method)) if bounded_method is not None
           else len(declared_cases()), "input_records": 0,
           "completed_cases": 0, "states": 0, "tagged_nonfinite_values": 0,
           "per_case": {}}
    xml = {key: 0 for key in ("tests", "skipped", "failures", "errors")}
    runtimes = []
    env = os.environ.copy()
    env["JAVA_TOOL_OPTIONS"] = (env.get("JAVA_TOOL_OPTIONS", "") +
                                " -verbose:class").strip()
    try:
        for method in methods:
            started = time.time()
            command = [str(ROOT / "gradlew"), "-p", str(BASELINE_PROJECT), "test",
                       "--tests", f"portable.PortableMatrixTest.{method}",
                       f"-PbaselineJar={jar}", "--rerun-tasks", "--no-daemon",
                       "--console=plain", "--info",
                       "-Dorg.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=1g"]
            if bounded_method is not None:
                command.append("--offline")
            log = lane / f"gradle-{method}.log"
            with log.open("x", encoding="utf-8") as stream:
                completed = subprocess.run(command, cwd=ROOT, env=env,
                                           stdout=stream, stderr=subprocess.STDOUT,
                                           check=False)
            method_result = {"method": method, "gradle_exit": completed.returncode,
                             "log_sha256": digest(log)}
            result["methods"].append(method_result)
            matching = sorted((BASELINE_PROJECT / "build/test-results/test").glob(
                "TEST-*PortableMatrixTest*.xml"))
            if len(matching) != 1 or matching[0].stat().st_mtime < started:
                method_result["reason"] = "baseline XML is missing or stale"
                continue
            _, attributes, counts = extract_xml("jvm", lane, method, matching[0])
            method_result["xml"] = attributes
            method_result["xml_sha256"] = digest(lane / "xml" / f"{method}.xml")
            method_result["completed_cases"] = counts["completed_cases"]
            for key in xml:
                xml[key] += int(attributes.get(key, "-1"))
            for key in ("input_records", "completed_cases", "states", "tagged_nonfinite_values"):
                raw[key] += counts[key]
            if raw["per_case"].keys() & counts["per_case"].keys():
                raise Rejected("baseline case appears in more than one method")
            raw["per_case"].update(counts["per_case"])
            executed = baseline_runtime(log, jar,
                                        proof_dir=lane / "process-proof" / method)
            method_result["process"] = executed
            runtimes.append(runtime_identity(executed))
        result["xml"] = xml
        result["raw_counts"] = raw
        if any(item["gradle_exit"] for item in result["methods"]):
            raise Rejected("baseline test method failed")
        if not runtimes or len(runtimes) != len(methods) or any(
                row != runtimes[0] for row in runtimes[1:]):
            raise Rejected("baseline methods lack one consistent executed JVM")
        result["runtime"] = {**runtimes[0], "method_executions": len(runtimes)}
        result["runtime"]["dependency_sha256"] = PINNED_JAR_SHA256
        result["runtime"]["method_process_sha256"] = hashlib.sha256(json.dumps(
            [item["process"] for item in result["methods"]],
            sort_keys=True).encode()).hexdigest()
        if bounded_method is None:
            result["inventory"] = baseline_inventory(raw, xml)
            result["angle_physical"] = angle_failure(lane)
        else:
            result["bounded_method"] = bounded_method
            result["inventory"] = bounded_inventory(raw, xml, bounded_method)
        if clean_identity() != (commit, source_sha256) or fixture_source_sha256() != fixture_sha256:
            raise Rejected("portable recorder source changed during baseline capture")
        result["trace_sha256"] = digest(lane / "trace.jsonl")
        if bounded_method is None:
            result["status"] = "CAPTURED_WITH_FAILED_ANGLE_PHYSICAL"
        else:
            result["xml_trace_counts"] = verify_xml_trace(
                lane, result["methods"], raw, result["trace_sha256"])
            result["case_sha256"] = verify_case_slices(lane, method_case_ids(bounded_method))
            cases = [case for case in declared_cases()
                     if case["id"] in set(method_case_ids(bounded_method))]
            result["trace_counts"] = inspect(lane / "trace.jsonl", cases)
            xml_file = lane / "xml" / f"{bounded_method}.xml"
            if b"PROSPECTIVE_ROTATION_JSON " in xml_file.read_bytes() or \
                    b"PROSPECTIVE_BINDING_JSON " in xml_file.read_bytes():
                raise Rejected("bounded old-source baseline has prospective observations")
            result["status"] = "BOUNDED_METHOD"
    except (Rejected, OSError, EOFError, KeyError, IndexError, TypeError, ValueError) as error:
        result["reason"] = str(error)
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-jar", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-existing", action="store_true")
    parser.add_argument("--verify-bounded-existing", action="store_true")
    parser.add_argument("--attest-existing", action="store_true")
    parser.add_argument("--attestation", type=Path)
    parser.add_argument("--method", choices=MATRIX_METHODS)
    args = parser.parse_args()
    if sum((args.verify_existing, args.verify_bounded_existing,
            args.attest_existing)) > 1:
        parser.error("choose one existing-archive verification mode")
    if args.method is not None and (args.verify_existing or args.verify_bounded_existing or
                                    args.attest_existing):
        parser.error("--method is only for a new bounded capture")
    if args.attest_existing:
        if not args.output.is_dir() or args.attestation is None:
            parser.error("existing archive and external attestation path are required")
        print(json.dumps(write_attestation(args.output, args.attestation), sort_keys=True))
        return 0
    if args.verify_existing:
        if not args.output.is_dir():
            parser.error("existing baseline output is absent")
        verified = verify_archive(args.output.resolve())
        print(json.dumps({key: value for key, value in verified.items()
                          if key not in ("methods", "case_sha256")}, sort_keys=True))
        return 0
    if args.verify_bounded_existing:
        if not args.output.is_dir():
            parser.error("existing bounded baseline output is absent")
        verified = verify_bounded_archive(args.output.resolve())
        print(json.dumps({key: value for key, value in verified.items()
                          if key != "case_sha256"}, sort_keys=True))
        return 0
    if args.baseline_jar is None:
        parser.error("--baseline-jar is required for capture")
    if args.output.exists():
        parser.error("output already exists")
    result = capture(args.output.resolve(), args.baseline_jar.resolve(), args.method)
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("methods", "raw_counts")}, sort_keys=True))
    return 0 if result["status"] in ("CAPTURED_WITH_FAILED_ANGLE_PHYSICAL",
                                      "BOUNDED_METHOD") else 1


if __name__ == "__main__":
    sys.exit(main())
