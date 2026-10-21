import hashlib
import json
import os
import struct
import subprocess
import zipfile
from pathlib import Path

from pulley_jdi_v1 import BASELINE_JAR_SHA256, Rejected, _digest, _json, _require, inspect_bundle
from pulley_jdi_inputs_v2 import (MAX_ARTIFACT_BYTES, bounded_file, inspect_classpath,
                                  verify_candidate_publication)
import run as portable_runner
from reference_diagnostic import projected_records
from frozen_weld_pulley import compare_records


CLASS_ENTRY = "org/dyn4j/dynamics/joint/PulleyJoint.class"
BOUND_CLASSES = {
    "pulley": ("provider", CLASS_ENTRY),
    "body": ("provider", "org/dyn4j/dynamics/Body.class"),
    "world": ("provider", "org/dyn4j/world/World.class"),
    "geometry": ("provider", "org/dyn4j/geometry/Geometry.class"),
    "case": ("fixture", "portable/PulleyPreparationJdiV1Test.class"),
    "recorder": ("fixture", "portable/NumericalRecorder.class"),
}
CONTROLLER = Path(__file__).with_name("PulleyJdiControllerV2.java")
CASE_ID = "P-JINT-Pulley-slack-transition-preparation-0"
CONTROLLER_CLASS_SHA256 = "a1a72bd5ea1c654cd5e8ee74e85a29cf8358bbb92cc66c2be6932c6992b7d4b8"
JDK = Path("/tmp/dyn4k-tools/jdk21")
BASELINE_REVISION = "058bf6d982a0fb89b54050f929f6ea9dae53b714"
BASELINE_SOURCE = Path("/tmp/dyn4k-upstream-6.0.0/src/main/java/org/dyn4j/dynamics/joint/PulleyJoint.java")
CANDIDATE_SOURCE = Path(__file__).resolve().parents[3] / "dyn4k-core/src/commonMain/kotlin/org/dyn4j/dynamics/joint/PulleyJoint.kt"


class Reader:
    def __init__(self, data):
        self.data = data
        self.offset = 0

    def take(self, count):
        end = self.offset + count
        _require(end <= len(self.data), "class file is truncated")
        result = self.data[self.offset:end]
        self.offset = end
        return result

    def u1(self):
        return self.take(1)[0]

    def u2(self):
        return struct.unpack(">H", self.take(2))[0]

    def u4(self):
        return struct.unpack(">I", self.take(4))[0]


def class_inventory(artifact, class_entry=CLASS_ENTRY):
    try:
        with zipfile.ZipFile(artifact) as archive:
            _require(archive.getinfo(class_entry).file_size < 1024 * 1024,
                     "bound class exceeds bound")
            data = archive.read(class_entry)
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise Rejected("Pulley artifact class is absent") from error
    reader = Reader(data)
    _require(reader.u4() == 0xCAFEBABE, "Pulley class magic differs")
    reader.take(4)
    count = reader.u2()
    pool_start = reader.offset
    names = {}
    index = 1
    while index < count:
        tag = reader.u1()
        if tag == 1:
            raw = reader.take(reader.u2())
            names[index] = raw.decode("utf-8", "surrogateescape")
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            reader.take(4)
        elif tag in (5, 6):
            reader.take(8)
            index += 1
        elif tag in (7, 8, 16, 19, 20):
            reader.take(2)
        elif tag == 15:
            reader.take(3)
        else:
            raise Rejected("Pulley constant-pool tag differs")
        index += 1
    pool = data[pool_start:reader.offset]
    reader.take(6)
    reader.take(2 * reader.u2())

    def skip_attributes():
        for _ in range(reader.u2()):
            reader.take(2)
            reader.take(reader.u4())

    for _ in range(reader.u2()):
        reader.take(6)
        skip_attributes()
    methods = {}
    for _ in range(reader.u2()):
        reader.take(2)
        name = names[reader.u2()]
        signature = names[reader.u2()]
        code = b""
        for _ in range(reader.u2()):
            attr = names[reader.u2()]
            raw = reader.take(reader.u4())
            if attr == "Code":
                body = Reader(raw)
                body.take(4)
                code = body.take(body.u4())
        key = (name, signature)
        _require(key not in methods, "duplicate Pulley method")
        methods[key] = code
    return pool, methods


def _lines(path, maximum):
    _digest(path, maximum)
    return Path(path).read_text(encoding="utf-8").splitlines()


def _properties(path):
    result = {}
    for line in _lines(path, 4096):
        key, separator, value = line.partition("=")
        _require(separator and key and key not in result, "controller property differs")
        result[key] = value
    return result


def inspect_loaded_code(directory, artifact, class_entry=CLASS_ENTRY, strict=False):
    directory = Path(directory)
    pool, expected = class_inventory(artifact, class_entry)
    _digest(directory / "constant-pool.bin", 1024 * 1024)
    _require((directory / "constant-pool.bin").read_bytes() == pool,
             "loaded class constant pool differs")
    lines = _lines(directory / "methods.tsv", 64 * 1024)
    _require(len(lines) == len(expected), "loaded Pulley method count differs")
    seen = set()
    for line in lines:
        parts = line.split("\t")
        _require(len(parts) == 3, "loaded method inventory differs")
        name, signature, file = parts
        key = name, signature
        _require(key in expected and key not in seen and
                 file == f"method-{len(seen)}.bin", "loaded method identity differs")
        seen.add(key)
        path = directory / file
        _require(path.is_file() and not path.is_symlink() and
                 path.stat().st_size <= 128 * 1024 and
                 path.read_bytes() == expected[key], "loaded class method bytes differ")
    _require(seen == set(expected), "loaded class method inventory incomplete")
    _require(len(list(directory.glob("method-*.bin"))) == len(expected),
             "extra loaded class method bytes")
    if strict:
        _require({path.name for path in directory.iterdir()} ==
                 {"constant-pool.bin", "methods.tsv"} |
                 {f"method-{index}.bin" for index in range(len(expected))},
                 "extra loaded class evidence")
    return {"methods": len(seen), "pool_sha256": hashlib.sha256(pool).hexdigest()}


def inspect_capture(directory, artifact=None):
    directory = Path(directory)
    _require(directory.is_dir() and not directory.is_symlink(), "capture is absent or linked")
    artifact = Path(artifact) if artifact else directory / "artifact.jar"
    manifest = _json(directory / "capture-v2.json", {
        "schema", "profile", "source_revision", "source_sha256", "artifact_sha256",
        "controller_sha256", "controller_class_sha256", "classpath_sha256",
        "worker_sha256", "case_sha256", "events_sha256", "process_sha256",
        "loaded_pool_sha256", "loaded_methods_sha256", "java_sha256", "live_sha256",
        "classpath_entries_sha256", "publication_sha256", "publication_log_sha256",
        "source_archive_sha256",
        "fixture_commit", "fixture_archive_sha256", "sidecar_build_stdout_sha256",
        "sidecar_build_stderr_sha256", "sidecar_classpath_sha256",
    })
    _require(manifest["schema"] == "pulley-jdi-capture/2" and
             manifest["profile"] in ("baseline", "candidate"),
             "capture version or profile differs")
    artifact = bounded_file(artifact, MAX_ARTIFACT_BYTES)
    _require(_digest(artifact, MAX_ARTIFACT_BYTES) == manifest["artifact_sha256"],
             "artifact hash differs")
    source = BASELINE_SOURCE if manifest["profile"] == "baseline" else CANDIDATE_SOURCE
    _require(_digest(source) == manifest["source_sha256"], "provider source differs")
    if manifest["profile"] == "baseline":
        _require(manifest["artifact_sha256"] == BASELINE_JAR_SHA256,
                 "pinned baseline artifact differs")
        _require(manifest["source_revision"] == BASELINE_REVISION,
                 "pinned baseline source revision differs")
        repository = Path("/tmp/dyn4k-upstream-6.0.0")
    else:
        repository = Path(__file__).resolve().parents[3]
    environment = {key: value for key, value in os.environ.items()
                   if key != "OLLAMA_API_KEY"}
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                       cwd=repository, env=environment, text=True).strip()
    _require(manifest["source_revision"] == revision,
             "provider source revision differs")
    _require(not subprocess.check_output(["git", "status", "--porcelain"],
                                         cwd=repository, env=environment),
             "provider source checkout is dirty")
    _require(_digest(JDK / "bin/java") == manifest["java_sha256"],
             "pinned Java runtime differs")
    _require(_digest(CONTROLLER) == manifest["controller_sha256"],
             "reviewed controller source differs")
    for name, field, maximum in (
        ("worker.json", "worker_sha256", 16 * 1024),
        ("case.jsonl", "case_sha256", 16 * 1024 * 1024),
        ("events.jsonl", "events_sha256", 64 * 1024),
        ("process.properties", "process_sha256", 4096),
        ("constant-pool.bin", "loaded_pool_sha256", 128 * 1024),
        ("methods.tsv", "loaded_methods_sha256", 64 * 1024),
        ("live.json", "live_sha256", 4096),
    ):
        _require(_digest(directory / name, maximum) == manifest[field],
                 f"{name} hash differs")
    _require(_digest(directory / "controller-classes/PulleyJdiControllerV2.class") ==
             manifest["controller_class_sha256"] == CONTROLLER_CLASS_SHA256,
             "reviewed controller binary differs")
    _require(_digest(directory / "classpath.txt", 64 * 1024) ==
             manifest["classpath_sha256"], "worker classpath differs")
    classpath_receipt = _json(directory / "classpath-entries.json",
                              {"schema", "entries"})
    _require(_digest(directory / "classpath-entries.json", 64 * 1024) ==
             manifest["classpath_entries_sha256"] and
             classpath_receipt["schema"] == "pulley-jdi-classpath/2" and
             isinstance(classpath_receipt["entries"], list),
             "classpath receipt differs")
    archived_entries = inspect_classpath(directory / "classpath.txt", artifact,
                                         directory / "classpath/000.jar",
                                         directory / "classpath")
    _require(len(archived_entries) == len(classpath_receipt["entries"]) and
             all({key: entry[key] for key in ("role", "index", "sha256", "size")} ==
                 {key: prior[key] for key in ("role", "index", "sha256", "size")}
                 for entry, prior in zip(archived_entries, classpath_receipt["entries"])),
             "retained classpath bytes or roles differ")
    fixture_commit, fixture_archive = portable_runner.clean_identity()
    _require(manifest["fixture_commit"] == fixture_commit and
             manifest["fixture_archive_sha256"] == fixture_archive,
             "focused fixture source identity differs")
    for name, field in (("sidecar-build.stdout", "sidecar_build_stdout_sha256"),
                        ("sidecar-build.stderr", "sidecar_build_stderr_sha256")):
        _require(_digest(directory / name, 2 * 1024 * 1024) == manifest[field],
                 "focused sidecar build log differs")
    sidecar_classpath = directory / "sidecar-classpath.txt"
    _require(_digest(sidecar_classpath, 64 * 1024) ==
             manifest["sidecar_classpath_sha256"] and
             sidecar_classpath.read_text() ==
             os.pathsep.join(entry["path"] for entry in classpath_receipt["entries"]) + "\n",
             "focused sidecar classpath receipt differs")
    if manifest["profile"] == "candidate":
        publication = verify_candidate_publication(artifact,
                                                    directory / "publication.json")
        _require((manifest["publication_sha256"] == publication["record_sha256"] and
                  manifest["publication_log_sha256"] == publication["log_sha256"] and
                  manifest["source_archive_sha256"] == publication["source_archive_sha256"]),
                 "candidate publication binding differs")
    else:
        _require(all(manifest[field] is None for field in
                     ("publication_sha256", "publication_log_sha256",
                      "source_archive_sha256")),
                 "baseline publication declaration differs")
    details = inspect_loaded_code(directory, artifact)
    loaded_root = directory / "loaded"
    _require(loaded_root.is_dir() and not loaded_root.is_symlink() and
             {path.name for path in loaded_root.iterdir()} == set(BOUND_CLASSES),
             "loaded class inventory differs")
    for label, (role, class_entry) in BOUND_CLASSES.items():
        source_jar = artifact if role == "provider" else directory / "classpath/000.jar"
        inspect_loaded_code(loaded_root / label, source_jar, class_entry, strict=True)
    process = _properties(directory / "process.properties")
    _require(set(process) == {"schema", "controller_pid", "worker_pid", "parent_pid",
                             "entry_count", "breakpoint_count", "class_count",
                             "class_source_name", "class_loader_id", "exit_code",
                             "nonce", "java_home", "bound_class_count"},
             "controller process schema differs")
    worker = _json(directory / "worker.json", {"schema", "pid", "case_id", "step",
                        "nonce", "case_sha256", "artifact_sha256", "class_source_uri"})
    live = _json(directory / "live.json", {"schema", "runner_pid", "controller_pid",
                                         "worker_pid", "controller_exit", "nonce"})
    _require(live["schema"] == "pulley-jdi-live/2" and
             type(live["runner_pid"]) is int and live["runner_pid"] > 0 and
             type(live["controller_pid"]) is int and
             type(live["worker_pid"]) is int and
             type(live["controller_exit"]) is int and live["controller_exit"] == 0 and
             live["controller_pid"] == int(process["controller_pid"]) and
             live["worker_pid"] == worker["pid"] and
             live["nonce"] == worker["nonce"], "live process declaration differs")
    _require(process["schema"] == "pulley-jdi-process/2" and
             process["java_home"] == "/tmp/dyn4k-tools/jdk21" and
             process["controller_pid"].isdigit() and
             process["worker_pid"].isdigit() and
             process["parent_pid"] == process["controller_pid"] and
             int(process["worker_pid"]) == worker["pid"] and
             process["nonce"] == worker["nonce"] and
             process["entry_count"] == "1" and
             process["breakpoint_count"] == "1" and
             process["class_count"] == "1" and
             process["bound_class_count"] == str(len(BOUND_CLASSES)) and
             process["exit_code"] == "0",
             "controller process or call count differs")
    source_name = "PulleyJoint.java" if manifest["profile"] == "baseline" else "PulleyJoint.kt"
    _require(process["class_source_name"] == source_name and
             process["class_loader_id"].isdigit(), "loaded class source differs")
    preflight = inspect_bundle(directory / "case.jsonl", directory / "worker.json",
                               directory / "events.jsonl", directory / "jdi.json", artifact)
    return {"status": "UNPASSED_LIVE_OR_REPLAY_PROOF", "case_id": CASE_ID,
            "worker_pid": worker["pid"], "methods": details["methods"],
            "case_sha256": preflight["case_sha256"],
            "artifact_sha256": preflight["artifact_sha256"],
            "frozen_policy_status": "UNPASSED_NOT_EVALUATED"}


def compare_indexed_onecase(reference, baseline_capture, candidate_capture,
                            expected_reference_sha256):
    reference = Path(reference)
    baseline = Path(baseline_capture) / "case.jsonl"
    candidate = Path(candidate_capture) / "case.jsonl"
    _require(_digest(reference, 16 * 1024 * 1024) == expected_reference_sha256,
             "indexed baseline case hash differs")
    baseline_status = inspect_capture(baseline_capture)
    candidate_status = inspect_capture(candidate_capture)
    _require(_digest(baseline, 16 * 1024 * 1024) == expected_reference_sha256,
             "focused baseline worker differs from indexed case bytes")
    comparison = compare_records("pulley-preparation-0",
                                 projected_records(reference),
                                 projected_records(candidate), require_coverage=True)
    return {"indexed_case_sha256": expected_reference_sha256,
            "baseline_witness": baseline_status["status"],
            "candidate_witness": candidate_status["status"],
            "frozen_comparison": comparison,
            "target_math_status": "UNPASSED_LIVE_OR_REPLAY_PROOF"}
