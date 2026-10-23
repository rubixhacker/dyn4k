import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from urllib.parse import unquote, urlparse

import actual_arithmetic
import actual_output_v6
from actual_arithmetic import (CaptureRejected, _FOCUSED_BOOLEAN_CASE,
                               _FOCUSED_BOOLEAN_METHOD, _PINNED_JAVA,
                               _STAGED_JAR, _unique_object, make_capture_receipt)
from actual_trace import (TraceRejected, _validate_calls, checked_projection,
                          normalize_rich_traces, rich_trace_arguments,
                          trace_exposes_environment)
from boolean_rotation_jdi import (jdi_bridge, source_guard as jdi_source_guard,
                                  witness as jdi_witness)
from numeric_class_witness import build_agent, read_witness
from numeric_producer import (MAX_TRACE_MEMBER, captured_file_identity, class_map, select_worker_exec,
                              verify_build_runtime, verify_witness_classpath)
from numeric_producer_trace import (_events, successful_execve,
                                    quoted, verify_stable_input, verify_transport)
from prospective_compare import compare_host
from receipt import Rejected
from run import comparison_coverage


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
    "jdi_helper_arguments": "jdi-helper-arguments.log",
    "jdi_transport": "jdi-transport.json",
    "agent": "class-witness-agent.jar", "class_witness": "class-witness.log",
    "mirror": "mirror.log", "all_process_traces": "all-process-traces.zip",
    "output_observer_traces": "output-observer-traces.zip",
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


def verify_launcher_input(metadata):
    path = jdi_bridge.JSPAWNHELPER
    expected = metadata.get("launcher_identity")
    after = metadata.get("launcher_after_identity")
    digest = metadata.get("launcher_sha256")
    try:
        current = captured_file_identity(path)
        data = path.read_bytes()
        current_sha256 = sha(data)
    except OSError as error:
        raise FocusedRejected("pinned JDK launcher is unavailable") from error
    require(type(expected) is dict and set(expected) == {
        "device_major", "device_minor", "inode", "size"} and
            all(type(value) is int and value >= 0 for value in expected.values()) and
            expected == after == current and expected["size"] == len(data) and
            digest == current_sha256 == jdi_bridge.JSPAWNHELPER_SHA256,
            "pinned JDK launcher identity or bytes differ")
    return digest


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
        receipt_bytes = (root / "receipt.json").read_bytes()
        for key, raw in files.items():
            if key not in {"source", "worker_write_traces", "jdi_helper_traces",
                           "all_process_traces", "output_observer_traces"}:
                require(not trace_exposes_environment(raw),
                        "focused archive exposed the environment")
        require(not trace_exposes_environment(receipt_bytes),
                "focused receipt exposed the environment")
        receipt = decoded(receipt_bytes)
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


def _class_witness(files, traces, selected, metadata, scratch, classpath,
                   environment):
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(files["source"]), mode="r:") as archive:
        entry = archive.extractfile(OBSERVER)
        require(entry is not None, "committed observer source is missing")
        source = entry.read()
    rebuilt = build_agent(source, JDK, scratch / "rebuilt-agent.jar",
                          scratch / "agent-compile", environment=environment)
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


def _helper_members(files, transport):
    classes = {}
    outputs = {}
    for field, target in (("jdi_helper_classes", classes),
                          ("jdi_evidence", outputs)):
        try:
            with zipfile.ZipFile(io.BytesIO(files[field])) as archive:
                names = archive.namelist()
                require(names and len(names) == len(set(names)) and
                        archive.testzip() is None and all(
                            name and not name.startswith("/") and
                            all(part not in ("", ".", "..") for part in name.split("/"))
                            for name in names), "JDI file inventory differs")
                target.update({name: archive.read(name) for name in names})
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            if isinstance(error, FocusedRejected):
                raise
            raise FocusedRejected("JDI file archive differs") from error
    require(all(re.fullmatch(r"RotationJdiProbe(?:\$[A-Za-z0-9_$]+)?\.class", name)
                for name in classes), "JDI helper class inventory differs")
    class_paths = {str(Path(transport["helper_classes_path"]) / name): data
                   for name, data in classes.items()}
    output_paths = {str(Path(transport["output_path"]) / name): data
                    for name, data in outputs.items()}
    return class_paths, output_paths


def verify_boolean_startup(raw, selected, metadata, port):
    prefix = f"[{selected[0]}][info][arguments] "
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise FocusedRejected("selected worker startup encoding differs") from error
    require(len(lines) == 5 and all(line.startswith(prefix) for line in lines),
            "selected worker startup inventory differs")
    rows = [line[len(prefix):] for line in lines]
    require(rows[0] == "VM Arguments:" and rows[1].startswith("jvm_args: ") and
            rows[2].startswith("java_command: " +
                               "worker.org.gradle.process.internal.worker.GradleWorkerMain ") and
            rows[4] == "Launcher Type: SUN_STANDARD",
            "selected worker startup records differ")
    flags = rows[1].removeprefix("jvm_args: ").split()
    expected_agent = ("-javaagent:" + metadata["agent_path"] + "=boolean:" +
                      metadata["witness_path"])
    jdwp = ("-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,"
            f"address=127.0.0.1:{port}")
    exact = {expected_agent, jdwp, jdi_bridge.FORK_LAUNCH_OPTION,
             "-XX:+DisableAttachMechanism", "-Xshare:off",
             "-XX:-UsePerfData", "-Xmx512m", "-Dfile.encoding=UTF-8",
             "-Duser.country", "-Duser.language=en", "-Duser.variant", "-ea",
             "-Dportable.booleanMirror=" + metadata["mirror_path"]}
    prefixes = ("-Djava.io.tmpdir=", "-Dorg.gradle.internal.worker.tmpdir=",
                "-Xlog:arguments=info:file=", "-Xlog:class+load=info:file=")
    require(len(flags) == len(set(flags)) and
            all(flag in exact or flag.startswith(prefixes) for flag in flags) and
            all(flags.count(flag) == 1 for flag in (
                expected_agent, jdwp, jdi_bridge.FORK_LAUNCH_OPTION,
                "-XX:+DisableAttachMechanism", "-Xshare:off",
                "-Dportable.booleanMirror=" + metadata["mirror_path"])) and
            sum(flag.startswith("-javaagent") for flag in flags) == 1 and
            sum(flag.startswith("-agentlib") for flag in flags) == 1 and
            not any(flag.startswith(("-agentpath", "-Xrunjdwp", "-Xbootclasspath",
                                     "--patch-module", "-Djava.system.class.loader=",
                                     "-XX:SharedArchiveFile")) for flag in flags),
            "selected worker startup agent inventory differs")
    argv = selected[2]
    require(argv.count(expected_agent) == 1 and argv.count(jdwp) == 1 and
            sum(option.startswith("-javaagent") for option in argv) == 1 and
            sum(option.startswith("-agentlib") for option in argv) == 1 and
            not any(option.startswith(("-agentpath", "-Xrunjdwp"))
                    for option in argv),
            "traced worker startup agent inventory differs")
    return {"worker_agent": expected_agent, "jdwp_option": jdwp,
            "effective_option_count": len(flags)}


def verify_helper_startup(raw, helper_pid, argv, argument_path):
    prefix = f"[{helper_pid}][info][arguments] "
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise FocusedRejected("JDI helper startup encoding differs") from error
    require(len(lines) == 5 and all(line.startswith(prefix) for line in lines),
            "JDI helper effective startup inventory differs")
    rows = [line[len(prefix):] for line in lines]
    logging = ("-Xlog:arguments=info:file=" + argument_path +
               ":pid,level,tags:filecount=0")
    temp_option = argv[3]
    require(rows[0] == "VM Arguments:" and rows[1].startswith("jvm_args: ") and
            rows[2] == "java_command: " + " ".join(argv[6:]) and
            rows[3] == "java_class_path (initial): " + argv[5] and
            rows[4] == "Launcher Type: SUN_STANDARD",
            "JDI helper startup records differ")
    flags = rows[1].removeprefix("jvm_args: ").split()
    require(flags.count(logging) == 1 and flags.count(temp_option) in (1, 2) and
            all(flag in (logging, temp_option, "--add-modules=jdk.jdi")
                for flag in flags) and
            not any(flag.startswith(("-javaagent", "-agentlib", "-agentpath",
                                     "-Xrunjdwp", "-Xbootclasspath", "--patch-module",
                                     "-Djava.system.class.loader=")) for flag in flags) and
            not any(flag.startswith(("-javaagent", "-agentlib", "-agentpath",
                                       "-Xrunjdwp")) for flag in argv),
            "JDI helper startup agent inventory differs")
    return {"helper_pid": helper_pid, "effective_option_count": len(flags),
            "argument_path": argument_path}


def _helper_argv(transport):
    paths = [transport[key] for key in (
        "helper_classes_path", "output_path", "temp_path")]
    return [str(JDK / "bin/java"), "--add-modules", "jdk.jdi",
            "-Djava.io.tmpdir=" + paths[2], "-cp", paths[0],
            "RotationJdiProbe", "attach", paths[1], "127.0.0.1",
            str(transport["port"]), "org.dyn4j.geometry.Transform", "1800", "600"]


def _output_proof(files, metadata, traces, events, worker, transport, environment,
                  verified_class_reads):
    _xml_mirror(files)
    selected = select_worker_exec(traces, _PINNED_JAVA)
    with zipfile.ZipFile(io.BytesIO(files["worker_write_traces"])) as archive:
        worker_raw = {name[6:]: archive.read(name) for name in archive.namelist()}
    worker_traces, worker_aborted = normalize_rich_traces(worker_raw)
    require(not worker_aborted, "version 6 protected worker output call is incomplete")
    worker_events = _events(worker_traces, ())
    helper_raw = jdi_bridge._trace_members(
        files["jdi_helper_traces"], version6_raw=True)
    helper_traces, helper_aborted = normalize_rich_traces({
        str(pid): raw.encode() for pid, raw in helper_raw.items()})
    require(not helper_aborted, "version 6 protected helper output call is incomplete")
    helper_events = _events(helper_traces, ())
    argv = _helper_argv(transport)
    helper_selected = (str(transport["helper_pid"]), argv[0], tuple(argv))
    spec = (
        ("mirror", worker_traces, worker_events, selected, "mirror_path", "mirror",
         "mirror_identity"),
        ("worker_arguments", worker_traces, worker_events, selected,
         "argument_path", "worker_arguments", "argument_identity"),
        ("worker_class_load", worker_traces, worker_events, selected,
         "class_load_path", "worker_class_load", "class_load_identity"),
        ("helper_arguments", helper_traces, helper_events, helper_selected,
         "helper_argument_path", "jdi_helper_arguments", "helper_argument_identity"),
    )
    checked = {}
    for role, scope, scope_events, execution, path_key, data_key, identity_key in spec:
        path = metadata[path_key]
        data = files[data_key]
        expected_identity = metadata[identity_key]
        transport_check = verify_transport(
            scope, path, data, execution,
            metadata["response_path"] if role == "mirror" else None,
            files["worker_classpath"] if role == "mirror" else None,
            exclusive=role == "mirror", shared_writers=role != "mirror",
            mirror_identity=expected_identity if role == "mirror" else None,
            allow_initial_log_seek=role != "mirror")
        lifetime = actual_output_v6.prove_file_lifetime(
            scope, scope_events, execution[0], path, data, expected_identity, role)
        require(transport_check["mirror_destination"] == path and
                (role != "mirror" or
                 (transport_check["mirror_writer_tid"],
                  transport_check["mirror_fd"]) ==
                 (lifetime["writer_tid"], lifetime["writer_fd"])),
                "version 6 output destination binding differs")
        checked[role] = {"transport": transport_check, "lifetime": lifetime}
    current_interpreter = Path(sys.executable).resolve()
    try:
        interpreter_identity = captured_file_identity(current_interpreter)
        interpreter_digest = sha(current_interpreter.read_bytes())
    except OSError as error:
        raise FocusedRejected("version 6 observer interpreter is unavailable") from error
    require(metadata["observer_interpreter_path"] == str(current_interpreter) and
            metadata["observer_interpreter_identity"] ==
            metadata["observer_interpreter_after_identity"] == interpreter_identity and
            metadata["observer_interpreter_sha256"] == interpreter_digest and
            metadata["observer_exit_code"] == 0 and
            metadata["observer_environment_sha256"] ==
            actual_output_v6.declared_environment_hash(environment),
            "version 6 observer interpreter or declared environment differs")
    paths = tuple(metadata[key] for key in (
        "mirror_path", "argument_path", "class_load_path", "helper_argument_path"))
    require(metadata["observer_command"] == list(actual_output_v6.observer_command(
        str(current_interpreter), paths)),
        "version 6 observer source or argv differs")
    observer = actual_output_v6.verify_observer(
        files["output_observer_traces"], str(current_interpreter), paths,
        {role: metadata[key] for role, key in (
            ("mirror", "mirror_identity"),
            ("worker_arguments", "argument_identity"),
            ("worker_class_load", "class_load_identity"),
            ("helper_arguments", "helper_argument_identity"))},
        events, helper_events)
    mirror = checked["mirror"]["transport"]
    socket_keys, sockets = actual_output_v6.prove_socket_writers(
        worker_traces, worker_events, selected[0],
        (mirror["mirror_writer_tid"], mirror["mirror_fd"]),
        verified_class_reads, worker["legacy_zip"])
    require(all(proof["projected_bound"] for proof in sockets),
            "version 6 socket projection is unbound")
    binding = actual_arithmetic.V6WriterBinding(
        sha(worker["legacy_zip"]),
        (mirror["mirror_writer_tid"], mirror["mirror_fd"]), socket_keys)
    return checked, observer, sockets, binding


def _proof(files, legacy, metadata, raw_traces, traces, events, worker, helper,
           aborted, output_proofs, output_observer, socket_proofs,
           environment=None):
    if environment is None:
        from capture_actual import child_environment
        environment = child_environment(focused=True)
    require(type(metadata) is dict and set(metadata) == {
        "schema", "command", "trace_arguments", "response_path", "agent_path",
        "witness_path", "mirror_path", "class_load_path", "argument_path",
        "agent_identity", "witness_identity", "mirror_identity",
        "argument_identity", "class_load_identity",
        "response_identity", "agent_after_identity",
        "artifact_identity", "artifact_after_identity",
        "runtime_identity", "runtime_after_identity",
        "launcher_identity", "launcher_after_identity", "launcher_sha256",
        "helper_class_before", "helper_class_after",
        "helper_argument_path", "helper_argument_identity",
        "observer_interpreter_path", "observer_interpreter_identity",
        "observer_interpreter_after_identity", "observer_interpreter_sha256",
        "observer_command", "observer_environment_sha256",
        "observer_exit_code",
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
    jdi_bridge.verify_gradle_fork_parent_v6(
        events, int(selected[0]), int(root_pid))
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
    mirror = output_proofs["mirror"]["transport"]
    require(mirror["worker_pid"] == selected[0] and mirror["parent_pids"],
            "direct mirror worker ancestry differs")
    arguments = output_proofs["worker_arguments"]["transport"]
    class_load = output_proofs["worker_class_load"]["transport"]
    temporary_root = Path(os.environ.get("TMPDIR", ""))
    require(temporary_root.is_absolute() and
            temporary_root.resolve().is_relative_to(Path.home().resolve()),
            "focused verifier temporary root differs")
    with tempfile.TemporaryDirectory(dir=temporary_root) as directory:
        witness, agent_class, witness_proof = _class_witness(
            files, traces, selected, metadata, Path(directory),
            legacy["worker_classpath_entries"], environment)
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
        _, compiled = jdi_bridge.compile_helper(
            helper_source, Path(directory), environment=environment, jdk_home=JDK)
    require(compiled == files["jdi_helper_classes"],
            "JDI helper class bytes differ from committed source")
    argv = _helper_argv(transport)
    startup = verify_boolean_startup(files["worker_arguments"], selected, metadata,
                                     transport["port"])
    class_paths, _ = _helper_members(files, transport)
    require(type(metadata["helper_class_before"]) is dict and
            type(metadata["helper_class_after"]) is dict and
            set(metadata["helper_class_before"]) ==
            set(metadata["helper_class_after"]) ==
            {Path(path).name for path in class_paths} and
            metadata["helper_class_before"] == metadata["helper_class_after"],
            "JDI helper class input identity changed")
    helper_traces, _ = normalize_rich_traces(_trace_map(files["jdi_helper_traces"]))
    require(metadata["helper_argument_path"] ==
            str(Path(transport["temp_path"]) / "jdi-helper-arguments.log"),
            "JDI helper startup log path differs")
    require(type(metadata["helper_argument_identity"]) is dict and
            set(metadata["helper_argument_identity"]) == {
                "device_major", "device_minor", "inode", "size"} and
            metadata["helper_argument_identity"]["size"] ==
            len(files["jdi_helper_arguments"]),
            "JDI helper startup log identity differs")
    helper_argument = output_proofs["helper_arguments"]["transport"]
    helper_startup = verify_helper_startup(
        files["jdi_helper_arguments"], transport["helper_pid"], argv,
        metadata["helper_argument_path"])
    helper_reads = {}
    for path, data in class_paths.items():
        identity = metadata["helper_class_before"][Path(path).name]
        require(type(identity) is dict and set(identity) == {
            "device_major", "device_minor", "inode", "size"} and
            all(type(value) is int and value >= 0 for value in identity.values()) and
            identity["size"] == len(data), "JDI helper class identity differs")
        observed = any(path in line for trace in helper_traces.values()
                       for line in trace.decode().splitlines())
        if observed:
            helper_reads[Path(path).name] = verify_stable_input(
                helper_traces, path, identity, str(transport["helper_pid"]), data,
                (argv[0], tuple(argv)), require_full_read=True)
    require("RotationJdiProbe.class" in helper_reads,
            "executed JDI helper main class input is missing")
    jdi_transport = jdi_bridge.verify_jdi_transport_v6(
        files["worker_write_traces"], files["jdi_helper_traces"], transport["port"],
        int(selected[0]), transport["helper_pid"], argv,
        launcher_sha256=metadata["launcher_sha256"],
        protected_paths=protected | {metadata["helper_argument_path"]} |
        set(class_paths))
    jdi_files = jdi_bridge.verify_jdi_file_writes(
        helper["legacy_zip"], files["jdi_evidence"], paths[1])
    sites = jdi_bridge.derive_call_sites(files["artifact"], environment=environment)
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
        "jdi_helper_input_reads": {name: value["reads"] for name, value in
                                   helper_reads.items()},
        "worker_startup": startup,
        "helper_startup": helper_startup,
        "helper_argument_destination": helper_argument["mirror_destination"],
        "output_observer": output_observer["status"],
        "output_observer_raw_sha256": output_observer["trace_sha256"],
        "auxiliary_socket_count": len(socket_proofs),
        "source_sites": sites,
        "calls_checked": 1800,
        "worker_raw_sha256": worker["raw_sha256"],
        "helper_raw_sha256": helper["raw_sha256"],
        "all_process_raw_sha256": sha(files["all_process_traces"]),
        "aborted_socket_or_wait_calls": len(aborted),
    }


def _raw_projections(files, protected, output_paths):
    worker = checked_projection(files["worker_write_traces"], protected,
                                version6_raw=True)
    helper = checked_projection(files["jdi_helper_traces"], protected,
                                strict_outputs=set(output_paths), version6_raw=True)
    return worker, helper


def _verified_compiled_marker_reads(files, worker_pid, class_bytes, origins,
                                    witnessed):
    candidates = {}
    for name, data in class_bytes.items():
        origin = origins[name]
        if (name.startswith("portable/") and origin != _STAGED_JAR and
                any(prefix in data for prefix in actual_arithmetic._WITNESS_PREFIXES) and
                name in witnessed):
            require(_origin_path(witnessed[name]["origin"]) == origin.resolve(),
                    "marker class provider differs from witnessed origin")
            candidates[str(origin / (name + ".class"))] = data
    require(candidates, "compiled marker class inventory differs")
    with zipfile.ZipFile(io.BytesIO(files["worker_write_traces"])) as archive:
        raw = {name[6:]: archive.read(name) for name in archive.namelist()}
    traces, _ = normalize_rich_traces(raw)
    selected = select_worker_exec(traces, _PINNED_JAVA)
    require(selected[0] == str(worker_pid), "marker class selected worker differs")
    selected_reads = {}
    for tid, trace in traces.items():
        for index, record in enumerate(trace.decode("utf-8").splitlines()):
            call = record.split(" ", 1)[1]
            if not call.startswith("read(") or not any(
                    prefix.decode() in call for prefix in
                    actual_arithmetic._WITNESS_PREFIXES):
                continue
            match = re.fullmatch(r'read\(([0-9]+)<([^<>]+)>, '
                                 r'("(?:\\.|[^"\\])*"), ([0-9]+)\) = ([0-9]+)',
                                 call)
            if match is None or match[2] not in candidates:
                continue
            payload = quoted(match[3])
            require(len(payload) == int(match[5]) and
                    len(payload) <= int(match[4]),
                    "compiled marker class read is incomplete")
            selected_reads.setdefault(match[2], []).append((tid, index, match[1]))
    verified = set()
    for path, records in selected_reads.items():
        identities = set()
        for tid, trace in traces.items():
            if not any(row[0] == tid for row in records):
                continue
            for record in trace.decode("utf-8").splitlines():
                call = record.split(" ", 1)[1]
                if not call.startswith('stat("' + path + '", ') or not call.endswith(") = 0"):
                    continue
                device = re.search(r'st_dev=makedev\(([^)]+)\)', call)
                inode = re.search(r'st_ino=([0-9]+)', call)
                size = re.search(r'st_size=([0-9]+)', call)
                require(device is not None and inode is not None and size is not None and
                        "st_mode=S_IFREG" in call,
                        "compiled marker class stat differs")
                parts = [value.strip() for value in device[1].split(",")]
                require(len(parts) == 2 and all(re.fullmatch(
                    r'(?:0x[0-9a-f]+|[0-9]+)', value) for value in parts),
                    "compiled marker class device differs")
                numbers = tuple(int(value, 16 if value.startswith("0x") else 10)
                                for value in parts)
                identities.add((*numbers, int(inode[1]), int(size[1])))
        require(len(identities) == 1 and next(iter(identities))[3] ==
                len(candidates[path]), "compiled marker class identity differs")
        major, minor, inode, size = next(iter(identities))
        verify_stable_input(traces, path, {"device_major": major,
                            "device_minor": minor, "inode": inode, "size": size},
                            selected[0], candidates[path], selected[1:])
        for tid, index, fd in records:
            calls = [line.split(" ", 1)[1] for line in
                     traces[tid].decode("utf-8").splitlines()]
            opened = any(re.fullmatch(r'open(?:at|at2)?\(.*\) = ' + fd +
                            '<' + re.escape(path) + '>', call)
                         for call in calls[:index])
            checked_fd = any(re.fullmatch(r'fstat\(' + fd + '<' +
                             re.escape(path) + r'>, \{.*st_size=' +
                             str(len(candidates[path])) + r'[^}]*\}\) = 0', call)
                             for call in calls[:index])
            closed = any(re.fullmatch(r'close\(' + fd + '<' +
                            re.escape(path) + r'>\) = 0', call)
                         for call in calls[index + 1:])
            require(opened and checked_fd and closed,
                    "compiled marker class descriptor lifecycle differs")
            verified.add((tid, index))
    return frozenset(verified), set(candidates)


def make_version6_receipt(files, commit, runtime_executable=_PINNED_JAVA):
    require(type(files) is dict and set(files) == set(FILE_NAMES) |
            {"worker_class_load", "worker_arguments"} and
            all(type(value) is bytes and value for value in files.values()),
            "version 6 source file inventory differs")
    require(runtime_executable == _PINNED_JAVA,
            "focused runtime executable differs")
    from capture_actual import child_environment, clean_source
    environment = child_environment(focused=True)
    require(clean_source(focused=True) == commit,
            "focused source is not the clean running revision")
    require(actual_arithmetic._source_archive(commit, environment=environment) ==
            files["source"],
            "focused source is not the clean running revision")
    metadata = decoded(files["metadata"])
    require(type(metadata) is dict and set(metadata) == {
        "schema", "command", "trace_arguments", "response_path", "agent_path",
        "witness_path", "mirror_path", "class_load_path", "argument_path",
        "agent_identity", "witness_identity", "mirror_identity",
        "argument_identity", "class_load_identity", "response_identity",
        "agent_after_identity", "artifact_identity", "artifact_after_identity",
        "runtime_identity", "runtime_after_identity",
        "launcher_identity", "launcher_after_identity", "launcher_sha256",
        "helper_class_before",
        "helper_class_after", "helper_argument_path", "helper_argument_identity",
        "observer_interpreter_path", "observer_interpreter_identity",
        "observer_interpreter_after_identity", "observer_interpreter_sha256",
        "observer_command", "observer_environment_sha256",
        "observer_exit_code",
        "worker_pid", "exit_code"} and
        all(type(metadata[key]) is str and metadata[key].startswith("/") for key in (
            "response_path", "agent_path", "witness_path", "mirror_path",
            "class_load_path", "argument_path", "helper_argument_path")),
        "focused capture metadata inventory differs")
    transport = decoded(files["jdi_transport"])
    require(type(transport) is dict and set(transport) == {
        "schema", "port", "worker_pid", "helper_pid", "helper_classes_path",
        "output_path", "temp_path", "live_socket_owner"},
        "focused JDI transport declaration differs")
    class_paths, output_paths = _helper_members(files, transport)
    protected = {metadata[key] for key in (
        "response_path", "agent_path", "witness_path", "mirror_path",
        "class_load_path", "argument_path", "helper_argument_path")} | \
        set(class_paths) | set(output_paths)
    raw_traces = _trace_map(files["all_process_traces"])
    require(not any(trace_exposes_environment(raw) for raw in raw_traces.values()),
            "complete process traces exposed the environment")
    traces, aborted = normalize_rich_traces(raw_traces)
    events = _events(traces, protected)
    _validate_calls(events, protected, version6_raw=True)
    verify_launcher_input(metadata)
    jdi_bridge.verify_worker_launch_v6(
        events, metadata["worker_pid"], launcher_sha256=metadata["launcher_sha256"],
        protected_paths=protected)
    expected_classes, origins = _expected_classes(files)
    witness = read_witness(files["class_witness"], expected_classes, profile="boolean")
    witnessed = {row["name"]: row for row in witness["definitions"]}
    class_paths = {str(origins[name] / (name + ".class")) for name, data in
                   expected_classes.items() if name.startswith("portable/") and
                   origins[name] != _STAGED_JAR and name in witnessed and any(
                   prefix in data for prefix in actual_arithmetic._WITNESS_PREFIXES)}
    worker, helper = _raw_projections(files, protected | class_paths, output_paths)
    verified_reads, selected_paths = _verified_compiled_marker_reads(
        files, metadata["worker_pid"], expected_classes, origins, witnessed)
    require(selected_paths == class_paths, "compiled marker class protection differs")
    output_proofs, output_observer, socket_proofs, binding = _output_proof(
        files, metadata, traces, events, worker, transport, environment,
        verified_reads)
    legacy_files = _legacy_files(files, worker)
    legacy = make_capture_receipt(
        legacy_files, _FOCUSED_BOOLEAN_METHOD, commit,
        [_FOCUSED_BOOLEAN_CASE], runtime_executable, TEST_CLASS,
        environment=environment, verified_class_reads=verified_reads,
        v6_writer_binding=binding)
    proof = _proof(files, legacy, metadata, raw_traces, traces, events,
                   worker, helper, aborted, output_proofs, output_observer,
                   socket_proofs, environment)
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
