import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from receipt import Rejected
from numeric_class_witness import build_agent, read_witness
from numeric_producer_trace import verify_stable_input
from jdk8_test_runtime import selected_test_jdk8_home


SOURCE = Path(__file__).with_name("class_witness") / "NumericClassWitness.java"
JDK_HOME_ENV = "DYN4K_CLASS_WITNESS_JDK_HOME"


def configured_jdk_home():
    if JDK_HOME_ENV in os.environ:
        supplied = os.environ[JDK_HOME_ENV]
        if not supplied.strip():
            raise RuntimeError(f"{JDK_HOME_ENV} must name a JDK directory")
        jdk_home = Path(supplied)
    else:
        jdk_home = Path("/tmp/dyn4k-tools/jdk21")

    if not jdk_home.is_dir():
        raise RuntimeError(f"{JDK_HOME_ENV} is not a JDK directory: {jdk_home}")
    for tool in ("java", "javac"):
        executable = jdk_home / "bin" / tool
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise RuntimeError(f"{JDK_HOME_ENV} lacks executable bin/{tool}: {jdk_home}")
    return jdk_home


JDK = configured_jdk_home()


def record(name="portable/PortableMatrixTest", value=b"class", origin="file:/fixture/"):
    return ("CLASS\t1\t" + name + "\t" + hashlib.sha256(value).hexdigest()
            + "\tL1\t" + origin + "\tjava:1\n").encode()


def witness(rows=None, status="OK", loaded=None):
    callback = record() if rows is None else rows
    snapshot = (b"LOADED\t1\tportable/PortableMatrixTest\tL1\tfile:/fixture/\n"
                if loaded is None else loaded)
    helpers = b"".join(("HELPER\t" + name + "\tsystem\tfile:/agent/\n").encode()
                       for name in ("dyn4k/witness/NumericClassWitness",
                                    "dyn4k/witness/NumericClassWitness$Observer",
                                    "dyn4k/witness/NumericClassWitness$1"))
    body = b"BEGIN\tclass-witness/2\n" + helpers + callback + b"SEALED\t1\n" + snapshot
    end = f"END\t{status}\t1\t"
    return body + (end + f"{len(body) + len(end) + 21:020d}\n").encode()


def _retain_unverified_pilot_traces(evidence, traces, metadata):
    if not evidence.is_dir() or any(evidence.iterdir()):
        raise AssertionError("pilot diagnostic directory must be empty")
    files = {"worker-traces.zip": traces["worker-trace"],
             "helper-traces.zip": traces["helper-trace"]}
    for name, data in files.items():
        with (evidence / name).open("xb") as target:
            target.write(data)
    diagnostic = {
        "schema": "focused-boolean-toy-pilot-diagnostic/1",
        **metadata,
        "status": "UNVERIFIED",
        "qualification": "UNPASSED",
        "files": {name: hashlib.sha256(data).hexdigest()
                  for name, data in files.items()},
        "raw_bytes": {name: len(data) for name, data in files.items()},
    }
    with (evidence / "diagnostic.json").open("x") as target:
        json.dump(diagnostic, target, indent=2, sort_keys=True)
        target.write("\n")


def _verify_toy_transport(selected_jdk, worker_archive, helper_archive, port,
                          worker_pid, helper_pid, helper_command):
    from boolean_rotation_jdi import jdi_bridge
    with patch.object(jdi_bridge, "JDK21", selected_jdk):
        return jdi_bridge.verify_jdi_transport_v6(
            worker_archive, helper_archive, port, worker_pid, helper_pid,
            helper_command, focused=False)


class ClassWitnessTest(unittest.TestCase):
    def test_toy_transport_uses_selected_jdk_identity(self):
        from boolean_rotation_jdi import jdi_bridge
        selected = Path("/opt/test-selected-jdk")
        command = [str(selected / "bin/java"), "--add-modules", "jdk.jdi",
                   "-Djava.io.tmpdir=/home/test", "-cp", "/home/test/classes",
                   "RotationJdiProbe", "attach-loader", "/home/test/output",
                   "127.0.0.1", "40001", "org.dyn4j.geometry.Transform", "0"]
        production_jdk = jdi_bridge.JDK21
        with self.assertRaisesRegex(jdi_bridge.EvidenceRejected,
                                    "JDI process trace archive is malformed"):
            _verify_toy_transport(selected, b"", b"", 40001, 101, 102, command)
        self.assertEqual(jdi_bridge.JDK21, production_jdk)

    def test_unverified_pilot_raw_traces_are_retained(self):
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            evidence = Path(directory)
            traces = {"worker-trace": b"worker raw\n",
                      "helper-trace": b"helper raw\n"}
            _retain_unverified_pilot_traces(
                evidence, traces, {"port": 40001, "helper_command": ["java"],
                                   "worker_returncode": 0, "helper_returncode": 0})
            self.assertEqual((evidence / "worker-traces.zip").read_bytes(),
                             traces["worker-trace"])
            self.assertEqual((evidence / "helper-traces.zip").read_bytes(),
                             traces["helper-trace"])
            diagnostic = json.loads((evidence / "diagnostic.json").read_text())
            self.assertEqual(diagnostic["status"], "UNVERIFIED")
            self.assertEqual(diagnostic["files"]["worker-traces.zip"],
                             hashlib.sha256(traces["worker-trace"]).hexdigest())
            self.assertEqual(diagnostic["port"], 40001)

    def test_boolean_profile_requires_transform_terminal_identity(self):
        transform = b"transform-class"
        digest = hashlib.sha256(transform).hexdigest().encode()
        helpers = b"".join(("HELPER\t" + name + "\tsystem\tfile:/agent/\n").encode()
                           for name in ("dyn4k/witness/NumericClassWitness",
                                        "dyn4k/witness/NumericClassWitness$Observer",
                                        "dyn4k/witness/NumericClassWitness$1"))
        prefix = (b"BEGIN\tclass-witness/3\n" + helpers +
                  b"CLASS\t1\torg/dyn4j/geometry/Transform\t" + digest +
                  b"\tL1\tfile:/engine/\tjava:1\nSEALED\t1\n" +
                  b"LOADED\t1\torg/dyn4j/geometry/Transform\tL1\tfile:/engine/\n" +
                  b"FOCUS\torg/dyn4j/geometry/Transform\tL1\t1\n")
        ending = b"END\tOK\t1\t"
        raw = prefix + ending + f"{len(prefix) + len(ending) + 21:020d}\n".encode()
        expected = {"org/dyn4j/geometry/Transform": transform}
        observed = read_witness(raw, expected, profile="boolean")
        self.assertEqual(observed["focus"], {"name": "org/dyn4j/geometry/Transform",
                                              "loader": "L1", "ordinal": 1})
        for changed in (raw.replace(b"\tL1\t1\nEND", b"\tL2\t1\nEND"),
                        raw.replace(b"\tL1\t1\nEND", b"\tL1\t2\nEND"),
                        raw.replace(b"FOCUS\t", b"OTHER\t")):
            with self.subTest(changed=changed[-90:]), self.assertRaises(Rejected):
                read_witness(changed, expected, profile="boolean")
        with self.assertRaises(Rejected):
            read_witness(witness(), {"portable/PortableMatrixTest": b"class"},
                         profile="boolean")

    def test_boolean_profile_observes_non_system_loader_through_real_jdi(self):
        from actual_trace import (checked_projection, normalize_rich_traces,
                                  rich_trace_arguments)
        from boolean_rotation_jdi import jdi_bridge
        from boolean_rotation_jdi.loaded_code import verify_probe_code
        from numeric_producer import captured_file_identity
        from numeric_producer_trace import (successful_execve, verify_stable_input,
                                            verify_transport)
        environment = os.environ.copy()
        environment.pop("OLLAMA_API_KEY", None)
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            root = Path(directory)
            source = root / "source"
            classes = root / "classes"
            source.mkdir()
            classes.mkdir()
            bodies = {
                "portable/FocusedBooleanArithmeticSourceTest": "public class FocusedBooleanArithmeticSourceTest {}",
                "portable/RevoluteLimitsFalseCaptureTest": "public class RevoluteLimitsFalseCaptureTest {}",
                "portable/NumericalRecorder": "public class NumericalRecorder {}",
                "org/dyn4j/geometry/Transform": "public class Transform {}",
            }
            sources = []
            for name, body in bodies.items():
                path = source / (name + ".java")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("package " + name.rsplit("/", 1)[0].replace("/", ".")
                                + "; " + body)
                sources.append(path)
            main = source / "Main.java"
            main.write_text(
                "import java.net.URLClassLoader; import java.nio.file.Paths; "
                "public class Main { public static void main(String[] a) throws Exception { "
                "URLClassLoader loader = new URLClassLoader(new java.net.URL[]{"
                "Paths.get(a[0]).toUri().toURL()}, null); "
                "Class.forName(\"portable.FocusedBooleanArithmeticSourceTest\", true, loader); "
                "Class.forName(\"portable.RevoluteLimitsFalseCaptureTest\", true, loader); "
                "Class.forName(\"portable.NumericalRecorder\", true, loader); "
                "Class.forName(\"org.dyn4j.geometry.Transform\", true, loader); } }")
            built = subprocess.run([str(JDK / "bin/javac"), "--release", "8",
                                    "-d", str(classes), str(main),
                                    *map(str, sources)], capture_output=True, timeout=30,
                                   env=environment)
            self.assertEqual(built.returncode, 0, built.stderr.decode())
            agent = root / "agent.jar"
            built_agent = build_agent(SOURCE.read_bytes(), JDK, agent, root / "agent-build")
            agent_before = captured_file_identity(agent)
            runtime_before = captured_file_identity(JDK / "bin/java")
            with patch.dict(os.environ, {"DYN4K_JDI_JDK_HOME": str(JDK)}):
                helper, helper_zip = jdi_bridge.compile_helper(
                    (Path(__file__).parent / "boolean_rotation_jdi/RotationJdiProbe.java").read_bytes(),
                    root / "helper-build")
            with zipfile.ZipFile(io.BytesIO(helper_zip)) as compiled_helper:
                helper_members = {name: compiled_helper.read(name)
                                  for name in compiled_helper.namelist()}
            helper_before = {name: captured_file_identity(helper / name)
                             for name in helper_members}
            with socket.socket() as reserved:
                reserved.bind(("127.0.0.1", 0))
                port = reserved.getsockname()[1]
            witness_path = root / "witness.log"
            tracer = shutil.which("strace")
            self.assertIsNotNone(tracer)
            target = subprocess.Popen([tracer, *rich_trace_arguments(),
                "-o", str(root / "worker-trace"),
                str(JDK / "bin/java"),
                f"-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:{port}",
                "-javaagent:" + str(agent) + "=boolean:" + str(witness_path),
                "-cp", str(classes), "Main", str(classes)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
            try:
                output = root / "jdi-output"
                helper_arguments = root / "jdi-helper-arguments.log"
                helper_environment = environment.copy()
                helper_environment["JAVA_TOOL_OPTIONS"] = (
                    "-Djava.io.tmpdir=" + str(root) +
                    " -Xlog:arguments=info:file=" + str(helper_arguments) +
                    ":pid,level,tags:filecount=0")
                helper_command = [str(JDK / "bin/java"), "--add-modules", "jdk.jdi",
                                  "-Djava.io.tmpdir=" + str(root),
                                  "-cp", str(helper), "RotationJdiProbe", "attach-loader",
                                  str(output), "127.0.0.1", str(port),
                                  "org.dyn4j.geometry.Transform", "0"]
                observed = subprocess.run([tracer, *rich_trace_arguments(),
                    "-o", str(root / "helper-trace"),
                    *helper_command], capture_output=True, timeout=60,
                    env=helper_environment)
                stdout, stderr = target.communicate(timeout=60)
            finally:
                if target.poll() is None:
                    target.kill()
                    target.communicate()
            retained_traces = {}
            for prefix in ("worker-trace", "helper-trace"):
                archived = io.BytesIO()
                with zipfile.ZipFile(archived, "w") as trace_zip:
                    for trace_file in sorted(root.glob(prefix + ".*")):
                        trace_zip.writestr(
                            "trace." + trace_file.name.rsplit(".", 1)[1],
                            trace_file.read_bytes())
                retained_traces[prefix] = archived.getvalue()
            evidence_path = os.environ.get("DYN4K_FOCUSED_PILOT_EVIDENCE")
            if evidence_path is not None:
                _retain_unverified_pilot_traces(
                    Path(evidence_path), retained_traces,
                    {"port": port, "helper_command": helper_command,
                     "worker_returncode": target.returncode,
                     "helper_returncode": observed.returncode})
            self.assertEqual(observed.returncode, 0, observed.stderr.decode())
            self.assertEqual(target.returncode, 0, stderr.decode())
            helper_argument_before = captured_file_identity(helper_arguments)
            expected = {name: (classes / (name + ".class")).read_bytes()
                        for name in bodies}
            record = read_witness(witness_path.read_bytes(), expected, profile="boolean")
            focus = record["focus"]
            self.assertRegex(focus["loader"], r"L[1-9][0-9]*")
            transform_code = verify_probe_code(
                output, expected["org/dyn4j/geometry/Transform"],
                "org.dyn4j.geometry.Transform")
            self.assertEqual(transform_code["status"], "MATCHED_JDI_LOADED_CODE")
            with zipfile.ZipFile(io.BytesIO(built_agent)) as compiled_agent:
                agent_class = compiled_agent.read(
                    "dyn4k/witness/NumericClassWitness.class")
            agent_code = verify_probe_code(
                output / "agent-code", agent_class,
                "dyn4k.witness.NumericClassWitness")
            self.assertEqual(agent_code["status"], "MATCHED_JDI_LOADED_CODE")
            transform_id = int((output / "class.txt").read_text().splitlines()[2])
            agent_id = int((output / "agent-code/class.txt").read_text().splitlines()[2])
            bridge = jdi_bridge.verify_loader_bridge(
                (output / "loader.tsv").read_bytes(), transform_id, agent_id, focus)
            self.assertGreater(bridge["loader_object_id"], 0)
            for prefix, expected_call in (("worker-trace", b"bind("),
                                          ("helper-trace", b"connect(")):
                archived = retained_traces[prefix]
                protected = ({str(agent), str(witness_path)} if prefix == "worker-trace"
                             else ({str(path) for path in output.rglob("*") if path.is_file()} |
                                   {str(helper / name) for name in helper_members} |
                                   {str(helper_arguments)}))
                projected = checked_projection(
                    archived, protected,
                    strict_outputs=({str(path) for path in output.rglob("*")
                                     if path.is_file()} if prefix == "helper-trace"
                                    else ()))
                self.assertGreater(projected["raw_bytes"], 0)
                with zipfile.ZipFile(io.BytesIO(projected["legacy_zip"])) as legacy:
                    self.assertTrue(any(expected_call in legacy.read(name)
                                        for name in legacy.namelist()))
                if prefix == "worker-trace":
                    with zipfile.ZipFile(io.BytesIO(archived)) as raw_zip:
                        traces = {name[6:]: raw_zip.read(name)
                                  for name in raw_zip.namelist()}
                    normalized, _ = normalize_rich_traces(traces)
                    selected = []
                    for tid, data in normalized.items():
                        for line in data.decode().splitlines():
                            if " execve(" not in line:
                                continue
                            executed = successful_execve(line.split(" ", 1)[1])
                            if executed is not None and executed[0] == str(JDK / "bin/java") \
                                    and "Main" in executed[1]:
                                selected.append((tid, *executed))
                    self.assertEqual(len(selected), 1)
                    worker = selected[0]
                    input_proof = verify_stable_input(
                        normalized, str(agent), captured_file_identity(agent),
                        worker[0], built_agent, worker[1:])
                    self.assertGreater(input_proof["reads"], 0)
                    output_proof = verify_transport(
                        normalized, str(witness_path), witness_path.read_bytes(),
                        worker, mirror_identity=captured_file_identity(witness_path),
                        shared_writers=True)
                    self.assertEqual(output_proof["mirror_destination"],
                                     str(witness_path))
            with zipfile.ZipFile(io.BytesIO(retained_traces["helper-trace"])) as raw_zip:
                helper_raw = {name[6:]: raw_zip.read(name)
                              for name in raw_zip.namelist()}
            helper_traces, _ = normalize_rich_traces(helper_raw)
            helper_executions = [(tid, successful_execve(line.split(" ", 1)[1]))
                                 for tid, data in helper_traces.items()
                                 for line in data.decode().splitlines()
                                 if " execve(" in line and "RotationJdiProbe" in line]
            self.assertEqual(len(helper_executions), 1)
            helper_pid = int(helper_executions[0][0])
            self.assertEqual(helper_executions[0][1],
                             (helper_command[0], tuple(helper_command)))
            transport_proof = _verify_toy_transport(
                JDK,
                retained_traces["worker-trace"], retained_traces["helper-trace"],
                port, int(worker[0]), helper_pid, helper_command)
            self.assertEqual(transport_proof["status"], "PROVED_JDI_RAW_EXCHANGE")
            helper_after = {}
            helper_input_reads = {}
            for name, data in helper_members.items():
                helper_after[name] = captured_file_identity(helper / name)
                self.assertEqual(helper_after[name], helper_before[name])
                self.assertEqual((helper / name).read_bytes(), data)
                path = str(helper / name)
                if any(path in line for trace in helper_traces.values()
                       for line in trace.decode().splitlines()):
                    proof = verify_stable_input(
                        helper_traces, path, helper_before[name], str(helper_pid),
                        data, (helper_command[0], tuple(helper_command)),
                        require_full_read=True)
                    self.assertGreater(proof["reads"], 0)
                    helper_input_reads[name] = proof["reads"]
                    if name == "RotationJdiProbe.class":
                        with self.assertRaises(Rejected):
                            verify_stable_input(
                                helper_traces, path, helper_before[name], str(helper_pid),
                                bytes([data[0] ^ 1]) + data[1:],
                                (helper_command[0], tuple(helper_command)),
                                require_full_read=True)
            with zipfile.ZipFile(io.BytesIO(retained_traces["helper-trace"])) as raw_zip:
                helper_projected = checked_projection(
                    retained_traces["helper-trace"],
                    {str(path) for path in output.rglob("*") if path.is_file()} |
                    {str(helper / name) for name in helper_members} |
                    {str(helper_arguments)},
                    strict_outputs={str(path) for path in output.rglob("*")
                                    if path.is_file()})
            helper_log = verify_transport(
                helper_traces, str(helper_arguments), helper_arguments.read_bytes(),
                (str(helper_pid), helper_command[0], tuple(helper_command)),
                exclusive=False, shared_writers=True, allow_initial_log_seek=True)
            self.assertEqual(helper_log["mirror_destination"], str(helper_arguments))
            self.assertEqual(captured_file_identity(helper_arguments),
                             helper_argument_before)
            from actual_capture_receipt import verify_helper_startup
            self.assertEqual(verify_helper_startup(
                helper_arguments.read_bytes(), helper_pid, helper_command,
                str(helper_arguments))["helper_pid"], helper_pid)
            jdi_zip = io.BytesIO()
            with zipfile.ZipFile(jdi_zip, "w") as archive:
                for path in sorted(path for path in output.rglob("*") if path.is_file()):
                    archive.writestr(path.relative_to(output).as_posix(), path.read_bytes())
            jdi_file_proof = jdi_bridge.verify_jdi_file_writes(
                helper_projected["legacy_zip"], jdi_zip.getvalue(),
                output)
            self.assertEqual(jdi_file_proof["status"],
                             "MATCHED_JDI_FILE_WRITES_UNPASSED_LOADER")
            self.assertEqual(captured_file_identity(agent), agent_before)
            self.assertEqual(captured_file_identity(JDK / "bin/java"), runtime_before)
            if evidence_path is not None:
                evidence = Path(evidence_path)
                self.assertEqual({path.name for path in evidence.iterdir()},
                                 {"worker-traces.zip", "helper-traces.zip",
                                  "diagnostic.json"})
                payloads = {
                    "agent.jar": built_agent,
                    "class-witness.log": witness_path.read_bytes(),
                    "helper-classes.zip": helper_zip,
                    "jdi-helper-arguments.log": helper_arguments.read_bytes(),
                }
                jdi_zip = io.BytesIO()
                with zipfile.ZipFile(jdi_zip, "w") as archive:
                    for path in sorted(path for path in output.rglob("*") if path.is_file()):
                        archive.writestr(path.relative_to(output).as_posix(), path.read_bytes())
                payloads["jdi-output.zip"] = jdi_zip.getvalue()
                for name, data in payloads.items():
                    with (evidence / name).open("xb") as target:
                        target.write(data)
                summary = {
                    "schema": "focused-boolean-toy-pilot/1",
                    "status": "PASSED_TOY_LOADER_AND_TRANSPORT",
                    "qualification": "UNPASSED",
                    "agent_before": agent_before,
                    "agent_after": captured_file_identity(agent),
                    "runtime_before": runtime_before,
                    "runtime_after": captured_file_identity(JDK / "bin/java"),
                    "loader_label": focus["loader"],
                    "loader_object_id": bridge["loader_object_id"],
                    "definition_ordinal": focus["ordinal"],
                    "agent_input_reads": input_proof["reads"],
                    "helper_class_before": helper_before,
                    "helper_class_after": helper_after,
                    "helper_input_reads": helper_input_reads,
                    "helper_argument_before": helper_argument_before,
                    "helper_argument_after": captured_file_identity(helper_arguments),
                    "helper_argument_destination": helper_log["mirror_destination"],
                    "raw_jdi_transport": transport_proof,
                    "jdi_file_writes": jdi_file_proof,
                    "witness_destination": output_proof["mirror_destination"],
                    "files": {**{name: hashlib.sha256(data).hexdigest()
                                  for name, data in payloads.items()},
                              **{name + "s.zip": hashlib.sha256(data).hexdigest()
                                  for name, data in retained_traces.items()}},
                }
                with (evidence / "pilot.json").open("x") as target:
                    json.dump(summary, target, indent=2, sort_keys=True)
                    target.write("\n")

    def test_rebuild_is_deterministic_and_capabilities_are_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            one = build_agent(SOURCE.read_bytes(), JDK, root / "one.jar", root / "one")
            two = build_agent(SOURCE.read_bytes(), JDK, root / "two.jar", root / "two")
            self.assertEqual(one, two)
            self.assertEqual((root / "one.jar").read_bytes(), one)
            self.assertNotIn(b"Can-Redefine-Classes", one)
            self.assertNotIn(b"Can-Retransform-Classes", one)

    def test_records_are_strict_and_complete(self):
        expected = {"portable/PortableMatrixTest": b"class"}
        good = witness()
        self.assertEqual(read_witness(good, expected)["definitions"][0]["thread"], "java:1")
        self.assertEqual(read_witness(good, expected)["loaded"][0]["loader"], "L1")
        failures = (good.replace(b"END\tOK", b"END\tFAIL"), good[:-31],
                    good.replace(hashlib.sha256(b"class").hexdigest().encode(), b"0" * 64),
                    good.replace(b"file:/fixture/", b"file:/shadow/"),
                    good.replace(b"java:1", b"os:1"),
                    witness(record() + record().replace(b"CLASS\t1", b"CLASS\t2")),
                    good.replace(b"NumericClassWitness$1", b"NumericClassWitness$2"),
                    good.replace(b"NumericClassWitness$Observer", b"NumericClassWitness$1"),
                    witness(loaded=b""),
                    witness(loaded=b"LOADED\t1\tportable/PortableMatrixTest\tL2\tfile:/fixture/\n"),
                    witness(loaded=b"LOADED\t1\tportable/PortableMatrixTest\tL1\tfile:/shadow/\n"))
        for invalid in failures:
            with self.subTest(invalid=invalid[:40]), self.assertRaises(Rejected):
                read_witness(invalid, expected, {"portable/PortableMatrixTest": "file:/fixture/"})

    def test_real_jvm_callback_precedes_successful_load(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = root / "agent.jar"
            build_agent(SOURCE.read_bytes(), JDK, agent, root / "build-agent")
            classes = root / "classes"
            package = root / "source" / "portable"
            classes.mkdir()
            package.mkdir(parents=True)
            sources = {
                "NumericProbeMatrixTest": "public class NumericProbeMatrixTest {}",
                "PortableMatrixTest": ("public class PortableMatrixTest { public static int answer() { "
                                       "java.util.function.IntSupplier generated = () -> 75; "
                                       "return generated.getAsInt(); } }"),
                "NumericalRecorder": "public class NumericalRecorder {}",
                "Ordinary$$Lambda$Name": "public class Ordinary$$Lambda$Name {}",
            }
            for name, body in sources.items():
                (package / (name + ".java")).write_text("package portable; " + body)
            main = root / "source" / "Main.java"
            main.write_text("public class Main { public static void main(String[] a) throws Exception { "
                            "Class.forName(\"portable.NumericProbeMatrixTest\"); "
                            "Class.forName(\"portable.NumericalRecorder\"); "
                            "Class.forName(\"portable.Ordinary$$Lambda$Name\"); "
                            "System.out.println(portable.PortableMatrixTest.answer()); } }")
            javac = subprocess.run([str(JDK / "bin/javac"), "--release", "8", "-d", str(classes),
                                    str(main), *map(str, sorted(package.glob("*.java")))],
                                   capture_output=True, check=False)
            self.assertEqual(javac.returncode, 0, javac.stderr.decode())
            expected = {"portable/" + path.stem: path.read_bytes()
                        for path in package.glob("*.java")
                        for path in [classes / "portable" / (path.stem + ".class")]}
            witness_path = root / "witness.log"
            command = [str(JDK / "bin/java"), "-XX:+DisableAttachMechanism", "-Xshare:off",
                       "-javaagent:" + str(agent) + "=" + str(witness_path),
                       "-Xlog:class+load=info:file=" + str(root / "loads.log"),
                       "-cp", str(classes), "Main"]
            successful = subprocess.run(command, capture_output=True, check=False, timeout=30)
            lines = witness_path.read_text().splitlines()
            callbacks = {line.split("\t")[2] for line in lines if line.startswith("CLASS\t")}
            loaded = {line.split("\t")[2] for line in lines if line.startswith("LOADED\t")}
            self.assertEqual(successful.returncode, 0,
                             successful.stderr.decode() + str(sorted(loaded - callbacks)))
            self.assertEqual(successful.stdout, b"75\n")
            records = read_witness(witness_path.read_bytes(), expected)
            self.assertEqual(len(records["definitions"]), 4)
            self.assertEqual(len(records["loaded"]), 4)
            self.assertEqual({row["name"] for row in records["helpers"]}, {
                "dyn4k/witness/NumericClassWitness",
                "dyn4k/witness/NumericClassWitness$Observer",
                "dyn4k/witness/NumericClassWitness$1"})
            witness_path.unlink()
            jdk8 = selected_test_jdk8_home()
            java8 = [str(jdk8 / "bin/java"), "-XX:+DisableAttachMechanism", "-Xshare:off",
                     "-javaagent:" + str(agent) + "=" + str(witness_path),
                     "-cp", str(classes), "Main"]
            java8_result = subprocess.run(java8, capture_output=True, check=False, timeout=30)
            lines = witness_path.read_text().splitlines()
            callbacks = {line.split("\t")[2] for line in lines if line.startswith("CLASS\t")}
            loaded = {line.split("\t")[2] for line in lines if line.startswith("LOADED\t")}
            self.assertEqual(java8_result.returncode, 0,
                             java8_result.stderr.decode() + str(sorted(loaded - callbacks)))
            self.assertEqual(java8_result.stdout, b"75\n")
            self.assertEqual(len(read_witness(witness_path.read_bytes(), expected)["loaded"]), 4)
            self.assertIn("portable.PortableMatrixTest source:",
                          (root / "loads.log").read_text())
            tracer = shutil.which("strace")
            self.assertIsNotNone(tracer)
            witness_path.unlink()
            traced = subprocess.run([tracer, "-ff", "-ttt", "-yy", "-e",
                                     "abbrev=!stat,lstat,fstat,newfstatat,statx", "-s", "131072",
                                     "-e", "trace=process,open,openat,openat2,close,read,pread64,lseek,"
                                     "stat,lstat,fstat,newfstatat,statx,write,mmap,rename,unlink,truncate",
                                     "-o", str(root / "trace"), *java8],
                                    capture_output=True, check=False, timeout=30)
            self.assertEqual(traced.returncode, 0, traced.stderr.decode())
            traces = {path.name.split(".")[-1]: path.read_bytes()
                      for path in root.glob("trace.*")}
            worker = next(tid for tid, data in traces.items()
                          if b"execve(" in data and b'"Main"' in data)
            status = agent.stat()
            identity = {"device_major": os.major(status.st_dev),
                        "device_minor": os.minor(status.st_dev),
                        "inode": status.st_ino, "size": status.st_size}
            try:
                input_proof = verify_stable_input(traces, str(agent), identity, worker,
                                                  agent.read_bytes(), (java8[0], tuple(java8)))
            except Exception as error:
                count = sum(str(agent) in line for data in traces.values()
                            for line in data.decode().splitlines())
                kinds = [(line.split(" ", 1)[-1].split("(", 1)[0],
                          "PROT_WRITE" in line, "MAP_PRIVATE" in line)
                         for data in traces.values() for line in data.decode().splitlines()
                         if str(agent) in line and line.split(" ", 1)[-1].startswith(
                             ("write", "mmap", "rename", "unlink", "truncate"))]
                stats = [line[:450] for data in traces.values()
                         for line in data.decode().splitlines()
                         if str(agent) in line and "stat" in line]
                self.fail(str(error) + f"; relevant trace records: {count}; operations: {kinds[:10]}; stats: {stats[:6]}")
            self.assertGreater(input_proof["reads"], 0)
            broken = classes / "portable" / "PortableMatrixTest.class"
            bad = broken.read_bytes()
            broken.write_bytes(b"XXXX" + bad[4:])
            witness_path.unlink()
            failed = subprocess.run(command, capture_output=True, check=False, timeout=30)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn(b"CLASS\t", witness_path.read_bytes())
            with self.assertRaises(Rejected):
                read_witness(witness_path.read_bytes(), expected)
            broken.write_bytes(bad)
            shadow = root / "source" / "dyn4k" / "witness" / "NumericClassWitness.java"
            shadow.parent.mkdir(parents=True)
            shadow.write_text("package dyn4k.witness; public final class NumericClassWitness { "
                              "public static void premain(String a, java.lang.instrument.Instrumentation i) "
                              "{ throw new IllegalStateException(\"shadow\"); } }")
            shadow_compile = subprocess.run([str(JDK / "bin/javac"), "--release", "8",
                                             "-d", str(classes), str(shadow)],
                                            capture_output=True, check=False)
            self.assertEqual(shadow_compile.returncode, 0, shadow_compile.stderr.decode())
            witness_path.unlink()
            substituted = subprocess.run(command, capture_output=True, check=False, timeout=30)
            self.assertNotEqual(substituted.returncode, 0)
            self.assertFalse(witness_path.exists())

    def test_relevant_load_after_seal_forces_nonzero_java8_exit(self):
        jdk8 = selected_test_jdk8_home()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = root / "agent.jar"
            build_agent(SOURCE.read_bytes(), JDK, agent, root / "agent-build")
            classes = root / "classes"
            classes.mkdir()
            package = root / "src/portable"
            package.mkdir(parents=True)
            for name in ("NumericProbeMatrixTest", "PortableMatrixTest", "NumericalRecorder",
                         "Late$$Lambda$Legal"):
                (package / (name + ".java")).write_text(
                    "package portable; public class " + name + " {}")
            main = root / "src/LateMain.java"
            main.write_text("""public class LateMain {
                public static void main(String[] args) throws Exception {
                    Class.forName("portable.NumericProbeMatrixTest");
                    Class.forName("portable.PortableMatrixTest");
                    Class.forName("portable.NumericalRecorder");
                    Runtime.getRuntime().addShutdownHook(new Thread(() -> {
                        try {
                            while (!new String(java.nio.file.Files.readAllBytes(
                                java.nio.file.Paths.get(args[0])), "US-ASCII").contains("END\\tOK")) {
                                Thread.sleep(5);
                            }
                            Class.forName("portable.Late$$Lambda$Legal");
                        } catch (Exception failure) { throw new RuntimeException(failure); }
                    }));
                }
            }""")
            compiled = subprocess.run([str(JDK / "bin/javac"), "--release", "8", "-d",
                                       str(classes), str(main),
                                       *map(str, sorted(package.glob("*.java")))],
                                      capture_output=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr.decode())
            witness_path = root / "witness.log"
            result = subprocess.run([str(jdk8 / "bin/java"), "-XX:+DisableAttachMechanism",
                                     "-Xshare:off", "-javaagent:" + str(agent) + "=" + str(witness_path),
                                     "-cp", str(classes), "LateMain", str(witness_path)],
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 86, result.stderr.decode())
            self.assertIn(b"END\tOK", witness_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
