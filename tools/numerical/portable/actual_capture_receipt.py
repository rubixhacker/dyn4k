import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from urllib.parse import unquote, urlparse

from actual_arithmetic import (CaptureRejected, _FOCUSED_BOOLEAN_CASE,
                               _FOCUSED_BOOLEAN_METHOD, _PINNED_JAVA,
                               _STAGED_JAR, _unique_object, make_capture_receipt)
from actual_trace import (TraceRejected, _validate_calls, checked_projection,
                          normalize_rich_traces, rich_trace_arguments)
from boolean_rotation_jdi import (jdi_bridge, source_guard as jdi_source_guard,
                                  witness as jdi_witness)
from numeric_class_witness import build_agent, read_witness
from numeric_producer import (MAX_TRACE_MEMBER, class_map, select_worker_exec,
                              verify_build_runtime, verify_witness_classpath)
from numeric_producer_trace import (_events, successful_execve,
                                    verify_stable_input, verify_transport)
from prospective_compare import compare_host
from receipt import Rejected
from run import clean_identity, comparison_coverage


class FocusedRejected(CaptureRejected):
    pass


SCHEMA = "portable-arithmetic-capture-receipt/6"
TEST_CLASS = "portable.FocusedBooleanArithmeticSourceTest"
ROOT = Path(__file__).resolve().parents[3]
PORTABLE = Path(__file__).resolve().parent
FILE_NAMES = {
    "xml": "capture.xml", "stage_log": "stage.log", "gradle_log": "gradle.log",
    "execve_log": "execve.log", "artifact": "artifact.jar", "runtime": "runtime-java",
    "source": "source.tar", "worker_classpath": "worker-classpath.txt",
    "portable_classes": "portable-classes.zip",
    "worker_write_traces": "worker-write-traces.zip",
    "candidate_case": "joint-Revolute-LimitsEnabled-false.jsonl",
    "reference_case": "reference-case.jsonl",
    "jdi_helper_classes": "jdi-helper-classes.zip",
    "jdi_evidence": "jdi-evidence.zip",
    "jdi_helper_traces": "jdi-helper-traces.zip",
    "jdi_transport": "jdi-transport.json",
    "agent": "class-witness-agent.jar", "class_witness": "class-witness.log",
    "mirror": "mirror.log", "all_process_traces": "all-process-traces.zip",
    "metadata": "capture-metadata.json",
}
OBSERVER = "tools/numerical/portable/class_witness/NumericClassWitness.java"
JDK = Path("/tmp/dyn4k-tools/jdk21")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decoded(raw):
    try:
        return json.loads(raw, object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError, TypeError) as error:
        raise FocusedRejected("focused JSON is malformed") from error


def require(condition, reason):
    if not condition:
        raise FocusedRejected(reason)


def load_version6_archive(root):
    root = Path(root)
    try:
        require(root.is_dir() and not root.is_symlink(),
                "focused archive root differs")
        names = {path.name for path in root.iterdir()}
        variable = {name for name in names if re.fullmatch(
            r"worker-(?:class-load|arguments)-[1-9][0-9]*\.log", name)}
        expected = set(FILE_NAMES.values()) | {"receipt.json"} | variable
        require(names == expected and len(variable) == 2 and
                all(path.is_file() and not path.is_symlink()
                    for path in root.iterdir()),
                "focused archive inventory differs")
        require(len({name.split("-")[-1].removesuffix(".log") for name in variable}) == 1,
                "focused worker log PID differs")
        files = {key: (root / name).read_bytes() for key, name in FILE_NAMES.items()}
        files["worker_class_load"] = (root / next(
            name for name in variable if name.startswith("worker-class-load-"))).read_bytes()
        files["worker_arguments"] = (root / next(
            name for name in variable if name.startswith("worker-arguments-"))).read_bytes()
        receipt = decoded((root / "receipt.json").read_bytes())
        require(type(receipt) is dict and receipt.get("schema") == SCHEMA,
                "focused receipt version differs")
        return receipt, files
    except OSError as error:
        raise FocusedRejected("focused archive is unavailable") from error


def _trace_map(raw):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            names = [item.filename for item in members]
            require(names and len(names) == len(set(names)) and len(names) <= 1024 and
                    all(re.fullmatch(r"trace\.[1-9][0-9]*", name) for name in names) and
                    not any(stat.S_ISLNK(item.external_attr >> 16) for item in members) and
                    all(item.file_size <= MAX_TRACE_MEMBER for item in members) and
                    sum(item.file_size for item in members) <= 2 * 1024 * 1024 * 1024 and
                    archive.testzip() is None, "complete process trace inventory differs")
            return {name[6:]: archive.read(name) for name in names}
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as error:
        if isinstance(error, FocusedRejected):
            raise
        raise FocusedRejected("complete process traces are malformed") from error


def _legacy_files(files, worker):
    legacy = {key: files[key] for key in FILE_NAMES if key in {
        "xml", "stage_log", "gradle_log", "execve_log", "artifact", "runtime",
        "source", "worker_classpath", "portable_classes", "candidate_case",
        "reference_case"}}
    legacy.update({
        "worker_class_load": files["worker_class_load"],
        "worker_arguments": files["worker_arguments"],
        "worker_write_traces": worker["legacy_zip"],
    })
    return legacy


def _expected_classes(files):
    compiled = class_map(files["portable_classes"])
    expected = {}
    origins = {}
    class_root = PORTABLE / "build/classes/kotlin/jvm"
    for entry, data in compiled.items():
        source_set, member = entry.split("/", 1)
        name = member.removesuffix(".class")
        require(name not in expected, "duplicate compiled class provider")
        expected[name] = data
        origins[name] = class_root / source_set
    with zipfile.ZipFile(io.BytesIO(files["artifact"])) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and archive.testzip() is None,
                "staged engine class inventory differs")
        for member in names:
            if member.startswith("org/dyn4j/") and member.endswith(".class"):
                name = member.removesuffix(".class")
                require(name not in expected, "duplicate engine class provider")
                expected[name] = archive.read(member)
                origins[name] = _STAGED_JAR
    return expected, origins


def _origin_path(value):
    url = urlparse(value)
    require(url.scheme == "file" and not url.netloc and not url.query and
            not url.fragment, "loaded class origin is not a file")
    return Path(unquote(url.path)).resolve()


def _class_witness(files, traces, selected, metadata, scratch, classpath):
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(files["source"]), mode="r:") as archive:
        entry = archive.extractfile(OBSERVER)
        require(entry is not None, "committed observer source is missing")
        source = entry.read()
    rebuilt = build_agent(source, JDK, scratch / "rebuilt-agent.jar",
                          scratch / "agent-compile")
    require(rebuilt == files["agent"], "agent bytes differ from committed source")
    verify_witness_classpath(classpath, Path(metadata["agent_path"]),
                             sha(rebuilt), host="jvm")
    agent_path = Path(metadata["agent_path"])
    witness_path = Path(metadata["witness_path"])
    require(agent_path.name == "class-witness-agent.jar" and
            witness_path.name == "class-witness.log" and
            agent_path.parent == witness_path.parent,
            "agent input and witness paths differ")
    agent_read = verify_stable_input(
        traces, str(agent_path), metadata["agent_identity"], selected[0],
        rebuilt, selected[1:])
    witness_write = verify_transport(
        traces, str(witness_path), files["class_witness"], selected,
        mirror_identity=metadata["witness_identity"], shared_writers=True)
    expected, origins = _expected_classes(files)
    result = read_witness(files["class_witness"], expected, profile="boolean")
    loaded = {}
    helper_loaded = {}
    for line in files["worker_class_load"].decode("utf-8").splitlines():
        match = re.fullmatch(
            r"\[([0-9]+)\]\[info\]\[class,load\] ([^ ]+) source: (.*)", line)
        require(match is not None and match[1] == selected[0],
                "selected worker class load record differs")
        name = match[2].replace(".", "/")
        if name.startswith("dyn4k/witness/"):
            require(name not in helper_loaded, "duplicate agent helper load")
            helper_loaded[name] = match[3]
        elif name.startswith(("portable/", "org/dyn4j/")) and not re.fullmatch(
                r".+\$\$Lambda(?:\$[1-9][0-9]*)?/0x[0-9a-f]+", name):
            require(name in expected and name not in loaded,
                    "successful relevant class inventory differs")
            loaded[name] = match[3]
    witnessed = {row["name"]: row for row in result["definitions"]}
    require(set(loaded) == set(witnessed), "class definitions and successful loads differ")
    with zipfile.ZipFile(io.BytesIO(rebuilt)) as jar:
        agent_classes = {name.removesuffix(".class") for name in jar.namelist()
                         if name.endswith(".class")}
        agent_class = jar.read("dyn4k/witness/NumericClassWitness.class")
    require(set(helper_loaded) == agent_classes and
            {row["name"]: row["origin"] for row in result["helpers"]} == helper_loaded,
            "agent helper provider inventory differs")
    for name, location in loaded.items():
        require(location == witnessed[name]["origin"] and
                _origin_path(location) == origins[name].resolve(),
                "loaded class bytes or origin differ")
    for location in helper_loaded.values():
        require(_origin_path(location) == agent_path.resolve(),
                "agent helper loaded outside rebuilt provider")
    return result, agent_class, {
        "schema": result["schema"], "source_sha256": sha(source),
        "agent_sha256": sha(rebuilt), "witness_sha256": result["sha256"],
        "definition_count": len(witnessed),
        "definition_inventory_sha256": sha(json.dumps(
            result["definitions"], sort_keys=True).encode()),
        "agent_input_reads": agent_read["reads"],
        "witness_destination": witness_write["mirror_destination"],
        "helper_provider": agent_path.as_uri(),
    }


def _xml_mirror(files):
    root = ET.fromstring(files["xml"])
    outputs = root.findall("system-out")
    require(len(outputs) == 1 and outputs[0].text is not None and
            files["mirror"].endswith(b"\n") and
            outputs[0].text.encode("utf-8") == files["mirror"],
            "complete direct mirror and XML order differ")
    return sha(files["mirror"])


def _proof(files, legacy, metadata, raw_traces, traces, events, worker, helper,
           aborted):
    require(type(metadata) is dict and set(metadata) == {
        "schema", "command", "trace_arguments", "response_path", "agent_path",
        "witness_path", "mirror_path", "class_load_path", "argument_path",
        "agent_identity", "witness_identity", "mirror_identity",
        "argument_identity", "class_load_identity",
        "response_identity", "agent_after_identity",
        "artifact_identity", "artifact_after_identity",
        "runtime_identity", "runtime_after_identity",
        "worker_pid", "exit_code"} and
        metadata["schema"] == "focused-arithmetic-capture/6" and
        metadata["trace_arguments"] == rich_trace_arguments() and
        metadata["exit_code"] == 0, "focused capture metadata differs")
    protected = {metadata[key] for key in (
        "response_path", "agent_path", "witness_path", "mirror_path",
        "class_load_path", "argument_path")}
    selected = select_worker_exec(traces, _PINNED_JAVA)
    require(int(selected[0]) == metadata["worker_pid"] ==
            legacy["worker_pid"], "selected worker identity differs")
    build_runtime = verify_build_runtime(traces, selected)
    command = metadata["command"]
    require(type(command) is list and command and
            all(type(value) is str for value in command) and
            command[0] == str(ROOT / "gradlew") and
            command.count("jvmTest") == 1 and
            command.count("--tests") == 1 and
            command[command.index("--tests") + 1] ==
            TEST_CLASS + "." + _FOCUSED_BOOLEAN_METHOD and
            all(command.count(flag) == 1 for flag in (
                "--rerun-tasks", "--no-daemon", "--offline", "--max-workers=1")) and
            all(command.count(option) == 1 for option in (
                "-PportableClassWitnessAgent=" + metadata["agent_path"],
                "-PportableClassWitnessOutput=boolean:" + metadata["witness_path"],
                "-PportableBooleanMirror=" + metadata["mirror_path"])) and
            command.count("-PportableRepository=" + str(
                ROOT / "build/staging-repository")) == 1,
            "focused target command differs")
    executions = sorted(f"{tid} {call}" for _, tid, _, call in events
                        if call.startswith(("execve(", "execveat(")))
    require(files["execve_log"] == ("\n".join(executions) + "\n").encode(),
            "projected process log differs from retained raw trace")
    root_pid = None
    for tid, raw in traces.items():
        if any(" execve(" in line and
               successful_execve(line.split(" ", 1)[1]) ==
               (command[0], tuple(command))
               for line in raw.decode("utf-8").splitlines()):
            require(root_pid is None, "focused traced invocation is ambiguous")
            root_pid = tid
    require(root_pid is not None, "focused traced invocation differs")
    with zipfile.ZipFile(io.BytesIO(files["worker_write_traces"])) as archive:
        for name in archive.namelist():
            require(raw_traces.get(name[6:]) == archive.read(name),
                    "retained worker trace differs from full process trace")
    response_path = metadata["response_path"]
    require("@" + response_path in selected[2] and
            files["worker_classpath"].endswith(b"\n"),
            "selected worker response bytes differ")
    require(metadata["agent_identity"] == metadata["agent_after_identity"] and
            metadata["artifact_identity"] == metadata["artifact_after_identity"] and
            metadata["runtime_identity"] == metadata["runtime_after_identity"],
            "protected capture input identity changed")
    response_read = verify_stable_input(
        traces, response_path, metadata["response_identity"], selected[0],
        files["worker_classpath"], selected[1:], allow_external_readers=True)
    worker_arguments = files["worker_arguments"].decode("utf-8")
    required_agent = "-javaagent:" + metadata["agent_path"] + "=" + (
        "boolean:" + metadata["witness_path"])
    require(worker_arguments.count(required_agent) == 1 and
            worker_arguments.count("-agentlib:jdwp=") == 1 and
            worker_arguments.count("-Dportable.booleanMirror=" +
                                   metadata["mirror_path"]) == 1 and
            not any(token in worker_arguments for token in (
                "-agentpath:", "-Xbootclasspath", "--patch-module",
                "-Djava.system.class.loader=")),
            "selected worker code provider or output options differ")
    mirror = verify_transport(
        traces, metadata["mirror_path"], files["mirror"], selected,
        response_path, files["worker_classpath"],
        mirror_identity=metadata["mirror_identity"])
    require(mirror["worker_pid"] == selected[0] and mirror["parent_pids"],
            "direct mirror worker ancestry differs")
    arguments = verify_transport(
        traces, metadata["argument_path"], files["worker_arguments"], selected,
        mirror_identity=metadata["argument_identity"],
        exclusive=False, shared_writers=True)
    class_load = verify_transport(
        traces, metadata["class_load_path"], files["worker_class_load"], selected,
        mirror_identity=metadata["class_load_identity"],
        exclusive=False, shared_writers=True)
    temporary_root = Path(os.environ.get("TMPDIR", ""))
    require(temporary_root.is_absolute() and
            temporary_root.resolve().is_relative_to(Path.home().resolve()),
            "focused verifier temporary root differs")
    with tempfile.TemporaryDirectory(dir=temporary_root) as directory:
        witness, agent_class, witness_proof = _class_witness(
            files, traces, selected, metadata, Path(directory),
            legacy["worker_classpath_entries"])
    with zipfile.ZipFile(io.BytesIO(files["artifact"])) as artifact:
        transform = artifact.read("org/dyn4j/geometry/Transform.class")
    from actual_arithmetic import focused_wheel_stream
    _, markers = focused_wheel_stream(files["xml"])
    observation = jdi_bridge.verify_jdi_archive(
        files["jdi_evidence"], transform, "org.dyn4j.geometry.Transform", 1800,
        markers, agent_class, witness["focus"])
    transport = decoded(files["jdi_transport"])
    require(type(transport) is dict and set(transport) == {
        "schema", "port", "worker_pid", "helper_pid", "helper_classes_path",
        "output_path", "temp_path", "live_socket_owner"} and
        transport["schema"] == "boolean-jdi-transport/1" and
        transport["worker_pid"] == int(selected[0]) and
        transport["live_socket_owner"] is True,
        "focused JDI transport declaration differs")
    expected_command = [
        str(ROOT / "gradlew"), "jvmTest", "--tests",
        TEST_CLASS + "." + _FOCUSED_BOOLEAN_METHOD,
        "-PportableRepository=" + str(ROOT / "build/staging-repository"),
        "-PportableWorkerClassLoadLog=" + str(
            Path(metadata["class_load_path"]).parent / "worker-class-load-%p.log"),
        "--rerun-tasks", "--no-daemon", "--console=plain", "--offline",
        "--info", "-Pkotlin.compiler.execution.strategy=in-process",
        "-PportableBooleanJdiPort=" + str(transport["port"]),
        "-PportableBooleanJdiMethod=" + _FOCUSED_BOOLEAN_METHOD,
        "-PportableClassWitnessAgent=" + metadata["agent_path"],
        "-PportableClassWitnessOutput=boolean:" + metadata["witness_path"],
        "-PportableBooleanMirror=" + metadata["mirror_path"],
        "--max-workers=1",
    ]
    require(command == expected_command, "focused target command inventory differs")
    paths = [transport[key] for key in ("helper_classes_path", "output_path", "temp_path")]
    require(all(type(path) is str and Path(path).is_absolute() and
                Path(path).resolve().is_relative_to(Path.home().resolve())
                for path in paths), "focused JDI helper path differs")
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(files["source"]), mode="r:") as source:
        for name, digest in jdi_source_guard.PINNED_FILES.items():
            member = source.extractfile(name)
            require(member is not None and sha(member.read()) == digest,
                    "JDI caller source schedule differs")
        helper_source = source.extractfile(
            "tools/numerical/portable/boolean_rotation_jdi/RotationJdiProbe.java")
        require(helper_source is not None, "JDI helper committed source is missing")
        helper_source = helper_source.read()
    with tempfile.TemporaryDirectory(dir=temporary_root) as directory:
        _, compiled = jdi_bridge.compile_helper(helper_source, Path(directory))
    require(compiled == files["jdi_helper_classes"],
            "JDI helper class bytes differ from committed source")
    argv = [str(JDK / "bin/java"), "--add-modules", "jdk.jdi",
            "-Djava.io.tmpdir=" + paths[2], "-cp", paths[0],
            "RotationJdiProbe", "attach", paths[1], "127.0.0.1",
            str(transport["port"]), "org.dyn4j.geometry.Transform", "1800", "600"]
    jdi_transport = jdi_bridge.verify_jdi_transport(
        worker["legacy_zip"], helper["legacy_zip"], transport["port"],
        int(selected[0]), transport["helper_pid"], argv)
    jdi_files = jdi_bridge.verify_jdi_file_writes(
        helper["legacy_zip"], files["jdi_evidence"], paths[1])
    sites = jdi_bridge.derive_call_sites(files["artifact"])
    identity = {"schema": jdi_witness.SCHEMA, "pid": int(selected[0]),
                "case_id": _FOCUSED_BOOLEAN_CASE,
                "source_sha256": sha(files["source"]),
                "jar_sha256": sha(files["artifact"]),
                "loaded_code_sha256": sha(transform),
                "marker_sha256": legacy["summary"]["operations_sha256"],
                "calls": observation["calls"]}
    operation = jdi_witness.verify_stream(identity, {
        **{key: identity[key] for key in (
            "pid", "case_id", "source_sha256", "jar_sha256",
            "loaded_code_sha256", "marker_sha256")},
        "markers": markers, "caller_code_indices": sites})
    require(operation == {"status": "UNPASSED_WORKER_BINDING",
                          "qualification": "UNPASSED", "calls_checked": 1800},
            "JDI caller, receiver, thread or arithmetic stream differs")
    return {
        "status": "PASSED_FOCUSED_METHOD_EVIDENCE",
        "qualification": "UNPASSED",
        "selected_worker_pid": int(selected[0]),
        "build_runtime_sha256": build_runtime,
        "mirror_sha256": _xml_mirror(files),
        "mirror_destination": mirror["mirror_destination"],
        "response_reads": response_read["reads"],
        "agent": witness_proof,
        "argument_destination": arguments["mirror_destination"],
        "class_load_destination": class_load["mirror_destination"],
        "loader_bridge": observation["loader_bridge"],
        "jdi_transport": jdi_transport["status"],
        "jdi_files": jdi_files["status"],
        "source_sites": sites,
        "calls_checked": 1800,
        "worker_raw_sha256": worker["raw_sha256"],
        "helper_raw_sha256": helper["raw_sha256"],
        "all_process_raw_sha256": sha(files["all_process_traces"]),
        "aborted_socket_or_wait_calls": len(aborted),
    }


def make_version6_receipt(files, commit, runtime_executable=_PINNED_JAVA):
    require(type(files) is dict and set(files) == set(FILE_NAMES) |
            {"worker_class_load", "worker_arguments"} and
            all(type(value) is bytes and value for value in files.values()),
            "version 6 source file inventory differs")
    require(runtime_executable == _PINNED_JAVA,
            "focused runtime executable differs")
    require(clean_identity() == (commit, sha(files["source"])),
            "focused source is not the clean running revision")
    metadata = decoded(files["metadata"])
    require(type(metadata) is dict and set(metadata) == {
        "schema", "command", "trace_arguments", "response_path", "agent_path",
        "witness_path", "mirror_path", "class_load_path", "argument_path",
        "agent_identity", "witness_identity", "mirror_identity",
        "argument_identity", "class_load_identity", "response_identity",
        "agent_after_identity", "artifact_identity", "artifact_after_identity",
        "runtime_identity", "runtime_after_identity", "worker_pid", "exit_code"} and
        all(type(metadata[key]) is str and metadata[key].startswith("/") for key in (
            "response_path", "agent_path", "witness_path", "mirror_path",
            "class_load_path", "argument_path")),
        "focused capture metadata inventory differs")
    protected = {metadata[key] for key in (
        "response_path", "agent_path", "witness_path", "mirror_path",
        "class_load_path", "argument_path")}
    raw_traces = _trace_map(files["all_process_traces"])
    traces, aborted = normalize_rich_traces(raw_traces)
    events = _events(traces, protected)
    _validate_calls(events, protected)
    worker = checked_projection(files["worker_write_traces"], protected)
    helper = checked_projection(files["jdi_helper_traces"], protected)
    legacy_files = _legacy_files(files, worker)
    legacy = make_capture_receipt(
        legacy_files, _FOCUSED_BOOLEAN_METHOD, commit,
        [_FOCUSED_BOOLEAN_CASE], runtime_executable, TEST_CLASS)
    proof = _proof(files, legacy, metadata, raw_traces, traces, events,
                   worker, helper, aborted)
    return {"schema": SCHEMA, "candidate_commit": commit,
            "method": _FOCUSED_BOOLEAN_METHOD,
            "source_archive_sha256": sha(files["source"]),
            "artifact_sha256": sha(files["artifact"]),
            "runtime_sha256": sha(files["runtime"]),
            "case_sha256": sha(files["candidate_case"]),
            "files": {FILE_NAMES[key]: sha(files[key]) for key in FILE_NAMES} |
                     {f"worker-class-load-{metadata['worker_pid']}.log":
                      sha(files["worker_class_load"]),
                      f"worker-arguments-{metadata['worker_pid']}.log":
                      sha(files["worker_arguments"])},
            "legacy_receipt": legacy, "proof": proof,
            "status": "PASSED_FOCUSED_METHOD_EVIDENCE",
            "qualification": "UNPASSED"}


def replay_version6(archive):
    receipt, files = load_version6_archive(archive)
    expected = make_version6_receipt(files, receipt["candidate_commit"])
    require(receipt == expected, "version 6 receipt or raw proof differs")
    return expected


def verify_existing(archive, lane, baseline, attestation):
    lane = Path(lane)
    require(lane.name == "jvm" and Path(baseline).is_dir() and
            Path(attestation).is_file(), "whole JVM lane inputs differ")
    whole = compare_host(
        baseline, lane, comparison_coverage()["frozen_case_ids"],
        attestation, arithmetic_captures=None)
    focused = replay_version6(archive)
    lane_receipt = decoded((lane / "receipt.json").read_bytes())
    require(focused["candidate_commit"] == lane_receipt.get("candidate_commit") and
            focused["source_archive_sha256"] ==
            whole.get("candidate_source_sha256") and
            focused["artifact_sha256"] ==
            lane_receipt.get("artifact_sha256", {}).get("target") and
            focused["runtime_sha256"] ==
            lane_receipt.get("runtime", {}).get("executable_sha256"),
            "focused source, artifact or runtime differs from sealed lane")
    try:
        case = (lane / "cases" / (_FOCUSED_BOOLEAN_CASE + ".jsonl")).read_bytes()
        captured = (Path(archive) / FILE_NAMES["candidate_case"]).read_bytes()
    except OSError as error:
        raise FocusedRejected("focused case or validated lane case is unavailable") from error
    require(sha(case) == focused["case_sha256"] and case == captured,
            "focused case differs from whole sealed lane")
    return {"status": "PASSED_FOCUSED_METHOD_EVIDENCE",
            "qualification": "UNPASSED", "method": _FOCUSED_BOOLEAN_METHOD,
            "case_sha256": focused["case_sha256"],
            "whole_lane_status": whole["status"],
            "receipt_sha256": sha((Path(archive) / "receipt.json").read_bytes())}
