import io
import copy
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import redirect_stdout
import tempfile
import unittest
from unittest import mock
import zipfile
import zlib
from pathlib import Path

from ordinary_arithmetic_diagnostic import (
    DiagnosticRejected, check_retained, verify_events, verify_lifecycle,
    verify_resource_samples, verify_case_output, validate_request,
    verify_runtime_limits, verify_worker_classpath, _allocation_ready,
    main, verify_archive, _supervisor_phases, _replay_failure,
    _last_complete_observation, _resource_ownership, _zip_checked,
    _verify_worker_raw_subset,
    _owned_sample, _resource_evidence, _executed_role, _observer_command,
    _sample_role, _resource_execs,
    _source_archive, _verify_source_archive, JDK21, ROOT, SampleUnavailable,
)
import ordinary_arithmetic_diagnostic as diagnostic
from actual_arithmetic import CaptureRejected, verify_capture_receipt
import actual_arithmetic
from boolean_rotation_jdi import jdi_bridge
from capture_actual import child_environment


def sample_events():
    rows = []
    markers = []
    for ordinal in range(64):
        pre = ["3ff0000000000000", "8000000000000000"]
        trig = ["3fefffffffffffff", "3f70000000000000"]
        post = ["3fefffffffffffff", "3f70000000000000"]
        angle = "3f91111111111111"
        rows.append("\t".join(map(str, [ordinal, 7, 19, *pre, *trig,
            *post, angle,
            "org.dyn4j.dynamics.AbstractPhysicsBody.integratePosition$lambda$0",
            151, 41, 1000 + ordinal])) + "\n")
        markers.append({"sequence": ordinal + 1, "step": ordinal + 1,
            "body_id": "b0", "kind": "rotate", "source": "pivot",
            "pre": pre, "trig": trig, "post": post, "angle_bits": angle})
    return "".join(rows).encode(), markers


def resource_replay_fixture():
    def command_hash(argv):
        return hashlib.sha256(("\0".join(argv) + "\0").encode()).hexdigest()

    def archive(traces):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as writer:
            for pid, lines in traces.items():
                writer.writestr(f"trace.{pid}", lines.encode())
        return stream.getvalue()

    clock = 1700000000
    wrapper = str(ROOT / "gradlew")
    jdk = str(JDK21 / "bin/java")
    shell = ["sh", wrapper]
    java = [jdk, "-cp", str(Path.home() /
            ".gradle/wrapper/dists/gradle-9.5.0-bin/test/gradle-9.5.0/lib/gradle-daemon-main-9.5.0.jar"),
            "org.gradle.launcher.daemon.bootstrap.GradleDaemon", "9.5.0"]
    tracer_child = ["sleep", "1"]
    worker = [jdk, "@" + str(Path.home() / ".gradle/.tmp/gradle-worker-classpath123txt"),
              "worker.org.gradle.process.internal.worker.GradleWorkerMain",
              "'Gradle Test Executor 1'"]
    helper = [jdk, "--add-modules", "jdk.jdi", "-cp", "/tmp/helper-classes",
              "OrdinaryArithmeticProbe", "attach", "/tmp/helper-output",
              "127.0.0.1", "12345", "600"]
    observer = list(_observer_command(("/tmp/xml", "/tmp/class-log",
                                       "/tmp/arguments", "/tmp/lifecycle")))
    target_root = ["strace", "-ff"]
    helper_root = ["strace", "helper"]
    observer_root = ["strace", "observer"]
    commands = (shell, java, tracer_child, worker, helper, observer, target_root,
                helper_root, observer_root)
    files = {
        "stage-process-traces.zip": archive({
            11: (f'{clock - 2}.100000 execve("/bin/sh", {json.dumps(shell)}, 0) = 0\n'
                 f'{clock - 2}.300000 execve({json.dumps(jdk)}, '
                 f'{json.dumps(java)}, 0) = 0\n'
                 f'{clock - 2}.800000 +++ exited with 0 +++\n')}),
        "all-process-traces.zip": archive({
            101: (f'{clock}.100000 execve("/bin/sh", {json.dumps(shell)}, 0) = 0\n'
                  f'{clock}.300000 execve({json.dumps(jdk)}, '
                  f'{json.dumps(java)}, 0) = 0\n'
                  f'{clock}.500000 execve("/usr/bin/sleep", ["sleep", "1"], 0) = 0\n'
                  f'{clock}.800000 +++ exited with 0 +++\n'),
            102: (f'{clock}.120000 execve({json.dumps(jdk)}, '
                  f'{json.dumps(worker)}, 0) = 0\n'
                  f'{clock}.800000 +++ exited with 0 +++\n')}),
        "helper-traces.zip": archive({
            201: (f'{clock}.150000 execve({json.dumps(jdk)}, '
                  f'{json.dumps(helper)}, 0) = 0\n'
                  f'{clock}.800000 +++ exited with 0 +++\n')}),
        "observer-traces.zip": archive({
            301: (f'{clock}.900000 execve({json.dumps(sys.executable)}, '
                  f'{json.dumps(observer)}, 0) = 0\n'
                  f'{clock + 1}.200000 +++ exited with 0 +++\n')})}

    def root(pid):
        return {"pid": pid, "parent_pid": 1, "group_pid": pid,
                "session_pid": pid, "start_ticks": pid,
                "affinity": [12, 13]}

    def row(pid, parent, group, role, argv):
        return {"pid": pid, "parent_pid": parent, "group_pid": group,
                "session_pid": group, "start_ticks": pid,
                "affinity": [12, 13], "roles": [role], "rss_kib": 100,
                "command_sha256": command_hash(argv)}

    metadata = {"launch_roots": {"stage": root(10), "target": root(100),
                                    "helper": root(200), "observer": root(300)},
                "gradle_root_pid": 100, "helper_root_pid": 200,
                "observer_root_pid": 300, "worker_pid": 102, "helper_pid": 201,
                "command": target_root, "helper_command": helper_root,
                "observer_command": observer_root,
                "resource_commands": {command_hash(argv): argv for argv in commands},
                "supervisor_milestones_ns": {"stage_start": 1_000_000_000,
                    "stage_end": 2_000_000_000, "gradle_start": 3_000_000_000,
                    "target_exit": 6_000_000_000,
                    "observer_start": 6_500_000_000,
                    "observer_exit": 7_500_000_000}}
    leader = row(100, 1, 100, "tracer", target_root)
    child = row(101, 100, 100, "gradle", shell)
    worker_row = row(102, 100, 100, "worker", worker)
    helper_leader = row(200, 1, 200, "tracer", helper_root)
    helper_row = row(201, 200, 200, "helper", helper)
    observer_leader = row(300, 1, 300, "tracer", observer_root)
    observer_row = row(301, 300, 300, "observer", observer)
    base = clock * 1_000_000_000
    samples = [
        {"time_ns": 4_000_000_000, "wall_start_ns": base + 190_000_000,
         "wall_end_ns": base + 210_000_000, "phase": "target",
         "pids": [leader, child, worker_row, helper_leader, helper_row]},
        {"time_ns": 4_200_000_000, "wall_start_ns": base + 390_000_000,
         "wall_end_ns": base + 410_000_000, "phase": "target",
         "pids": [leader, {**child, "command_sha256": command_hash(java)},
                  worker_row, helper_leader, helper_row]},
        {"time_ns": 4_400_000_000, "wall_start_ns": base + 590_000_000,
         "wall_end_ns": base + 610_000_000, "phase": "target",
         "pids": [leader, {**child, "roles": ["other"],
                  "command_sha256": command_hash(tracer_child)}, worker_row,
                  helper_leader, helper_row]},
        {"time_ns": 7_000_000_000, "wall_start_ns": base + 990_000_000,
         "wall_end_ns": base + 1_010_000_000, "phase": "observer",
         "pids": [observer_leader, observer_row]}]
    return samples, metadata, files, {"cpu_set": [12, 13]}


def changed_resource_image(samples, metadata, files, pid, path, argv):
    samples = copy.deepcopy(samples)
    metadata = copy.deepcopy(metadata)
    files = dict(files)
    phase = ("helper" if pid == 201 else "observer" if pid == 301 else "target")
    archive_name = {"target": "all-process-traces.zip",
                    "helper": "helper-traces.zip",
                    "observer": "observer-traces.zip"}[phase]
    index = {101: 1, 201: 0, 301: 3}[pid]
    old_digest = samples[index]["pids"][{101: 1, 201: 4, 301: 1}[pid]]["command_sha256"]
    old_argv = metadata["resource_commands"].pop(old_digest)
    new_digest = hashlib.sha256(("\0".join(argv) + "\0").encode()).hexdigest()
    metadata["resource_commands"][new_digest] = argv
    for sample in samples:
        for row in sample["pids"]:
            if row["pid"] == pid and row["command_sha256"] == old_digest:
                row["command_sha256"] = new_digest
    source = zipfile.ZipFile(io.BytesIO(files[archive_name]))
    output = io.BytesIO()
    changed = 0
    with source, zipfile.ZipFile(output, "w") as writer:
        for name in source.namelist():
            raw = source.read(name)
            if name == f"trace.{pid}":
                lines = raw.decode().splitlines(keepends=True)
                for line_index, line in enumerate(lines):
                    if " execve(" not in line or not line.endswith(" = 0\n"):
                        continue
                    if json.dumps(old_argv) not in line:
                        continue
                    prefix = line[:line.index("execve(")]
                    lines[line_index] = (prefix + "execve(" + json.dumps(path) +
                                         ", " + json.dumps(argv) + ", 0) = 0\n")
                    changed += 1
                raw = "".join(lines).encode()
            writer.writestr(name, raw)
    assert changed == 1
    files[archive_name] = output.getvalue()
    return samples, metadata, files


def wrapper_shebang_fixture():
    samples, metadata, files, allocation = resource_replay_fixture()
    wrapper = str(ROOT / "gradlew")
    raw_argv = [wrapper, "jvmTest"]
    proc_argv = ["/bin/sh", wrapper, "jvmTest"]
    old = samples[0]["pids"][1]["command_sha256"]
    metadata["resource_commands"].pop(old)
    digest = hashlib.sha256(("\0".join(proc_argv) + "\0").encode()).hexdigest()
    metadata["resource_commands"][digest] = proc_argv
    samples[0]["pids"][1]["command_sha256"] = digest
    old_root = samples[0]["pids"][0]["command_sha256"]
    metadata["resource_commands"].pop(old_root)
    metadata["command"] = ["strace", "-ff", *raw_argv]
    root_digest = hashlib.sha256(("\0".join(metadata["command"]) + "\0").encode()).hexdigest()
    metadata["resource_commands"][root_digest] = metadata["command"]
    for sample in samples[:3]:
        sample["pids"][0]["command_sha256"] = root_digest
    with zipfile.ZipFile(io.BytesIO(files["all-process-traces.zip"])) as archive:
        traces = {name: archive.read(name) for name in archive.namelist()}
    old_exec = f'execve("/bin/sh", {json.dumps(["sh", wrapper])}, 0) = 0'.encode()
    new_exec = f'execve({json.dumps(wrapper)}, {json.dumps(raw_argv)}, 0) = 0'.encode()
    assert traces["trace.101"].count(old_exec) == 1
    traces["trace.101"] = traces["trace.101"].replace(old_exec, new_exec, 1)
    files["all-process-traces.zip"] = _zip_checked(traces, "trace_zip")
    return samples, metadata, files, allocation


class DiagnosticContractTest(unittest.TestCase):
    def test_stage_plan_builds_portable_main_and_test_classes(self):
        commands, launch = diagnostic._stage_commands()
        self.assertEqual(2, len(commands))
        self.assertIn(":dyn4k-core:publishJvmPublicationToStagingRepository",
                      commands[0])
        self.assertEqual([str(ROOT / "gradlew"), "-p", str(diagnostic.PORTABLE),
                          "jvmTestClasses"], commands[1][:4])
        self.assertIn("--offline", commands[1])
        self.assertIn("--max-workers=1", commands[1])
        self.assertEqual(["/bin/sh", "-c"], launch[:2])
        for command in commands:
            self.assertEqual(("/bin/sh", ["/bin/sh", *command]),
                             diagnostic._wrapper_proc_image(
                                 "stage", command[0], command,
                                 {"stage_commands": commands}))
        with self.assertRaisesRegex(DiagnosticRejected,
                                    "diagnostic wrapper invocation differs"):
            diagnostic._wrapper_proc_image("stage", commands[1][0],
                                            [*commands[1], "jvmTest"],
                                            {"stage_commands": commands})

    def test_core_publication_alone_cannot_prepare_portable_class_archive(self):
        core_only = [str(ROOT / "gradlew"),
            ":dyn4k-core:publishKotlinMultiplatformPublicationToStagingRepository",
            ":dyn4k-core:publishJvmPublicationToStagingRepository", "--rerun-tasks",
            "--no-daemon", "--console=plain", "--offline", "--max-workers=1",
            "-Pkotlin.compiler.execution.strategy=in-process"]
        metadata = {"stage_command": core_only,
                    "artifact_identity": "sealed", "runtime_identity": "sealed"}
        with mock.patch.object(diagnostic, "captured_file_identity",
                               return_value="sealed"):
            with self.assertRaisesRegex(DiagnosticRejected,
                                        "diagnostic staged source or runtime identity differs"):
                diagnostic._stage_identity({"stage.log": b"BUILD SUCCESSFUL\n"},
                                           metadata)

    def test_stage_replay_requires_both_executed_build_commands(self):
        commands, launch = diagnostic._stage_commands()
        metadata = {"stage_commands": commands, "stage_command": launch,
                    "artifact_identity": "sealed", "runtime_identity": "sealed"}
        files = {"stage.log": (
            b"> Task :dyn4k-core:publishJvmPublicationToStagingRepository\n"
            b"BUILD SUCCESSFUL\n> Task :jvmTestClasses\nBUILD SUCCESSFUL\n"),
            "stage-process-traces.zip": b"retained trace"}
        events = [(index, 100 + index, None,
                   f'execve({json.dumps(command[0])}, '
                   f'{json.dumps(command)}, 0) = 0')
                  for index, command in enumerate(commands)]
        with (mock.patch.object(diagnostic, "captured_file_identity",
                                return_value="sealed"),
              mock.patch.object(diagnostic, "_raw_events",
                                return_value=({}, events))):
            diagnostic._stage_identity(files, metadata)
            with mock.patch.object(diagnostic, "_raw_events",
                                   return_value=({}, events[:1])):
                with self.assertRaisesRegex(DiagnosticRejected,
                                            "diagnostic staged command execution differs"):
                    diagnostic._stage_identity(files, metadata)

    def test_root_allocation_is_separate_from_sampled_rss_limit(self):
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            path = Path(directory) / "allocation.json"
            cpu = min(os.sched_getaffinity(0))
            record = {"schema": "ordinary-arithmetic-resource-allocation/1",
                "diagnostic_runtime_allocation": "SCHEDULED",
                "available_memory_kib": 1024,
                "other_tasks_preserved": True, "cpu_set": [cpu]}
            path.write_text(json.dumps(record))
            self.assertTrue(_allocation_ready(path, require_local_cpus=True))
            path.write_text(json.dumps({**record, "cpu_set": [cpu, cpu]}))
            self.assertFalse(_allocation_ready(path, require_local_cpus=True))
            path.write_text(json.dumps({**record,
                "diagnostic_runtime_allocation": "NOT_SCHEDULED_RESOURCE"}))
            self.assertFalse(_allocation_ready(path, require_local_cpus=True))

    def test_worker_classpath_rejects_shadow_provider_and_changed_snapshot(self):
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            root = Path(directory)
            classes = root / "classes"
            main = classes / "main/portable/NumericalRecorder.class"
            test = classes / "test/portable/PortableMatrixTest.class"
            for path in (main, test):
                path.parent.mkdir(parents=True)
                path.write_bytes(path.name.encode())
            portable = io.BytesIO()
            with zipfile.ZipFile(portable, "w") as archive:
                archive.writestr("main/portable/NumericalRecorder.class",
                                main.read_bytes())
                archive.writestr("test/portable/PortableMatrixTest.class",
                                test.read_bytes())
            staged = root / "staged.jar"
            with zipfile.ZipFile(staged, "w") as archive:
                for name in actual_arithmetic._AUDITED_ENGINE_CLASSES:
                    archive.writestr(name, b"safe class")
            dependency = root / "dependency.jar"
            with zipfile.ZipFile(dependency, "w") as archive:
                archive.writestr("safe.class", b"safe class")
            response = ("-cp\n" + ":".join(map(str, (
                classes / "main", classes / "test", staged, dependency))) + "\n").encode()
            snapshot = verify_worker_classpath(
                response, portable.getvalue(), staged_jar=staged,
                class_root=classes)
            self.assertEqual(len(snapshot), 4)
            with self.assertRaises(DiagnosticRejected):
                verify_worker_classpath(response, portable.getvalue(),
                    [{**snapshot[0], "sha256": "0" * 64}, *snapshot[1:]],
                    staged_jar=staged, class_root=classes)
            with zipfile.ZipFile(dependency, "w") as archive:
                archive.writestr("org/dyn4j/geometry/Transform.class", b"shadow")
            with self.assertRaises(DiagnosticRejected):
                verify_worker_classpath(response, portable.getvalue(),
                    snapshot, staged_jar=staged, class_root=classes)

    def test_only_original_case_and_fixed_cap_can_start(self):
        validate_request("captureLongMotion", 64)
        for method, cap in (("captureLongMotion", 63),
                            ("captureLongMotion", 65), ("captureFreeMotion", 64)):
            with self.subTest(method=method, cap=cap), self.assertRaises(DiagnosticRejected):
                validate_request(method, cap)

    def test_prefix_rejects_changed_bits_order_caller_and_receiver(self):
        raw, markers = sample_events()
        self.assertEqual(verify_events(raw, markers, 151, 41)["matched_calls"], 64)
        for changed in (raw.replace(b"3fefffffffffffff", b"3feffffffffffffe", 1),
                        raw.replace(b"0\t7\t19", b"1\t7\t19", 1),
                        raw.replace(b"AbstractPhysicsBody", b"OtherPhysicsBody", 1),
                        raw.replace(b"0\t7\t19", b"0\t7\t20", 1),
                        raw.replace(b"\t151\t41\t", b"\t151\t42\t", 1),
                        b"".join(raw.splitlines(keepends=True)[:-1])):
            with self.subTest(changed=changed[:35]), self.assertRaises(DiagnosticRejected):
                verify_events(changed, markers, 151, 41)

    def test_detach_requires_complete_monotonic_sequence(self):
        stages = ("attach", "armed", "class-prepared", "first-entry", "cap-entry-reached",
                  "exits-drained", "requests-disabled", "event-set-resumed",
                  "disposed", "detach-complete")
        raw = "".join(f"{stage}\t{index + 1}\n" for index, stage in enumerate(stages)).encode()
        self.assertEqual(verify_lifecycle(raw)["detach_complete_ns"], 10)
        for changed in (raw.replace(b"disposed\t9\n", b""),
                        raw.replace(b"class-prepared\t3", b"class-prepared\t1"),
                        raw.replace(b"event-set-resumed", b"event-set-missing")):
            with self.subTest(changed=changed), self.assertRaises(DiagnosticRejected):
                verify_lifecycle(changed)

    def test_sampled_rss_deduplicates_owned_pids_and_rejects_gaps(self):
        roles = {"gradle", "worker", "helper", "tracer", "observer"}
        def row(pid, role, rss):
            return {"pid": pid, "roles": role, "rss_kib": rss,
                    "parent_pid": 1, "group_pid": pid, "session_pid": pid,
                    "start_ticks": pid,
                    "affinity": [12, 13], "command_sha256": "0" * 64}
        samples = [{"time_ns": 1, "wall_start_ns": 1,
                    "wall_end_ns": 2, "phase": "target", "pids": [
            row(11, ["gradle"], 100),
            row(12, ["worker"], 200),
            row(13, ["helper"], 300),
            row(14, ["observer"], 300),
            row(15, ["tracer"], 100)]}]
        self.assertEqual(verify_resource_samples(samples, roles)["peak_aggregate_kib"], 1000)
        duplicate = json.loads(json.dumps(samples))
        duplicate[0]["pids"].append(duplicate[0]["pids"][0])
        self.assertEqual(verify_resource_samples(duplicate, roles)["peak_aggregate_kib"], 1000)
        missing = json.loads(json.dumps(samples))
        missing[0]["pids"][1]["rss_kib"] = None
        self.assertEqual(verify_resource_samples(missing, roles)["status"], "UNAVAILABLE")
        crossing = json.loads(json.dumps(samples))
        crossing[0]["pids"][1]["rss_kib"] = 10 * 1024 * 1024 + 1
        self.assertEqual(verify_resource_samples(crossing, roles)["status"], "RSS_BOUND")

    def test_decoded_privacy_rejects_fragmented_harmless_sentinel(self):
        raw = (b'write(1, "DYN4K_CAPTURE_ENV_" "SENTINEL=portable-capture-check", 50) = 50\n')
        with self.assertRaises(DiagnosticRejected):
            check_retained(raw, "trace")
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as writer:
            writer.writestr("trace.1", raw)
        with self.assertRaises(DiagnosticRejected):
            check_retained(archive.getvalue(), "zip")
        safe = io.BytesIO()
        with zipfile.ZipFile(safe, "w") as writer:
            writer.writestr("trace.1", b"safe raw record\n")
        self.assertEqual(check_retained(safe.getvalue(), "zip"), safe.getvalue())

    def test_split_json_and_xml_sentinel_rejected_at_all_writers_and_readers(self):
        from ordinary_arithmetic_diagnostic import _read_checked, _report_bytes, _write_checked
        fragments = ["DYN4K_CAPTURE_ENV_", "SENTINEL=portable-capture-check"]
        raw = (json.dumps({"probe": fragments}) + "\n").encode()
        xml = (b'<root a="DYN4K_CAPTURE_ENV_" '
               b'b="SENTINEL=portable-capture-check"/>')
        for kind, payload in (("raw", raw), ("report", raw), ("jsonl", raw),
                              ("raw", xml)):
            with self.subTest(kind=kind, payload=payload[:5]), self.assertRaises(
                    DiagnosticRejected):
                check_retained(payload, kind)
        with self.assertRaises(DiagnosticRejected):
            _report_bytes({"probe": fragments})
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            for name, payload in (("sample.json", raw), ("sample.jsonl", raw),
                                  ("capture.xml", xml)):
                path = Path(directory) / name
                with self.subTest(name=name), self.assertRaises(DiagnosticRejected):
                    _write_checked(path, payload)
                self.assertFalse(path.exists())
                path.write_bytes(payload)
                with self.subTest(read=name), self.assertRaises(DiagnosticRejected):
                    _read_checked(path)
        for name, payload in (("nested.json", raw), ("nested.jsonl", raw),
                              ("nested.xml", xml), ("trace.1", raw)):
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as writer:
                writer.writestr(name, payload)
            with self.subTest(member=name), self.assertRaises(DiagnosticRejected):
                check_retained(archive.getvalue(), "zip")
            with self.subTest(writer=name), self.assertRaises(DiagnosticRejected):
                _zip_checked({name: payload})
        escaped = (b'{"outer":["\\u0044YN4K_CAPTURE_ENV_",'
                   b'"SENTINEL=portable-capture-check"]}')
        separated_fields = (b'{"first":"\\u0044YN4K_CAPTURE_ENV_",'
                            b'"second":"SENTINEL=portable-capture-check"}')
        entity_xml = (b'<root a="&#68;YN4K_CAPTURE_ENV_" '
                      b'b="SENTINEL=portable-capture-check"/>')
        for payload in (escaped, separated_fields, entity_xml):
            with self.subTest(decoded_fragment=payload[:20]), self.assertRaises(
                    DiagnosticRejected):
                check_retained(payload, "raw")

    def test_nested_json_privacy_rejects_escaped_sentinel_at_seams(self):
        leaked = (b'{"outer":{"nested":["\\u0044YN4K_CAPTURE_ENV_'
                  b'SENTINEL=portable-capture-check"]}}\n')
        with self.assertRaises(DiagnosticRejected):
            check_retained(leaked, "report")
        trace = (b'1.0 write(1, "\\u0044YN4K_CAPTURE_ENV_'
                 b'SENTINEL=portable-capture-check", 50) = 50\n')
        with self.assertRaises(DiagnosticRejected):
            check_retained(trace, "trace")
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            from ordinary_arithmetic_diagnostic import _write_checked, _read_checked
            path = Path(directory) / "sample.json"
            with self.assertRaises(DiagnosticRejected):
                _write_checked(path, leaked)
            path.write_bytes(leaked)
            with self.assertRaises(DiagnosticRejected):
                _read_checked(path)
            with self.assertRaises(DiagnosticRejected):
                _write_checked(Path(directory) / "sample.jsonl", leaked)
            with self.assertRaises(DiagnosticRejected):
                _write_checked(Path(directory) / "malformed.json", b'{"open":')
        zipped = io.BytesIO()
        with zipfile.ZipFile(zipped, "w") as archive:
            archive.writestr("nested.json", leaked)
        with self.assertRaises(DiagnosticRejected):
            check_retained(zipped.getvalue(), "zip")
        with self.assertRaises(DiagnosticRejected):
            _zip_checked({"nested.json": leaked})
        xml = (b"<testsuite><system-out>NUMERICAL_JSON " + leaked.strip() +
               b"</system-out></testsuite>")
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            from ordinary_arithmetic_diagnostic import _write_checked
            with self.assertRaises(DiagnosticRejected):
                _write_checked(Path(directory) / "capture.xml", xml)

    def test_declared_zip_limit_rejects_before_member_open(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as writer:
            writer.writestr("large.bin", b"x")
        raw = bytearray(archive.getvalue())
        central = raw.find(b"PK\x01\x02")
        self.assertGreaterEqual(central, 0)
        raw[central + 24:central + 28] = (129 * 1024 * 1024).to_bytes(4, "little")
        with self.assertRaisesRegex(DiagnosticRejected, "decoded bound"):
            check_retained(bytes(raw), "zip")

    def test_staged_jar_accepts_empty_directories_only(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as writer:
            writer.writestr("org/", b"")
            writer.writestr("org/dyn4j/", b"")
            writer.writestr("org/dyn4j/Example.class", b"class bytes")
        raw = archive.getvalue()
        self.assertEqual(check_retained(raw, "jar"), raw)
        with self.assertRaises(DiagnosticRejected):
            check_retained(raw, "zip")
        with self.assertRaises(DiagnosticRejected):
            check_retained(raw, "trace_zip")

        malformed = (
            (("org/", b"payload"), ("org/Example.class", b"class bytes")),
            (("org/", b""), ("org", b"file")),
            (("org", b"file"), ("org/Example.class", b"class bytes")),
            (("org/", b""), ("org/", b"")),
            (("../outside.class", b"class bytes"),),
            (("/outside.class", b"class bytes"),),
            (("org/./Example.class", b"class bytes"),),
            (("org//Example.class", b"class bytes"),),
            (("org\\Example.class", b"class bytes"),),
        )
        for entries in malformed:
            with self.subTest(entries=entries):
                archive = io.BytesIO()
                with zipfile.ZipFile(archive, "w") as writer:
                    for name, payload in entries:
                        writer.writestr(name, payload)
                with self.assertRaises(DiagnosticRejected):
                    check_retained(archive.getvalue(), "jar")

    def test_staged_jar_keeps_size_crc_and_privacy_checks(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as writer:
            writer.writestr("org/", b"")
            writer.writestr("org/Example.class", b"class bytes")
        raw = archive.getvalue()
        central = raw.find(b"PK\x01\x02")
        self.assertGreaterEqual(central, 0)
        oversized = bytearray(raw)
        oversized[central + 24:central + 28] = (129 * 1024 * 1024).to_bytes(4, "little")
        with self.assertRaises(DiagnosticRejected):
            check_retained(bytes(oversized), "jar")
        corrupt = bytearray(raw)
        second_central = corrupt.find(b"PK\x01\x02", central + 1)
        self.assertGreaterEqual(second_central, 0)
        corrupt[second_central + 16] ^= 1
        with self.assertRaises(DiagnosticRejected):
            check_retained(bytes(corrupt), "jar")
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as writer:
            writer.writestr("org/", b"")
            writer.writestr("META-INF/details.json",
                            b'{"secret":"\\u0044YN4K_CAPTURE_ENV_'
                            b'SENTINEL=portable-capture-check"}')
        with self.assertRaises(DiagnosticRejected):
            check_retained(archive.getvalue(), "jar")

    def test_staged_jar_directory_stream_matches_zero_size_and_crc(self):
        for compression, payload in (
                (zipfile.ZIP_STORED, b"hidden bytes"),
                (zipfile.ZIP_DEFLATED, b"hidden bytes"),
                (zipfile.ZIP_DEFLATED,
                 b"DYN4K_CAPTURE_ENV_SENTINEL=portable-capture-check")):
            with self.subTest(compression=compression, payload=payload):
                archive = io.BytesIO()
                with zipfile.ZipFile(archive, "w", compression=compression) as writer:
                    writer.writestr("org/", payload)
                    writer.writestr("org/Example.class", b"class bytes")
                raw = bytearray(archive.getvalue())
                local = raw.find(b"PK\x03\x04")
                central = raw.find(b"PK\x01\x02")
                raw[local + 14:local + 18] = bytes(4)
                raw[local + 22:local + 26] = bytes(4)
                raw[central + 16:central + 20] = bytes(4)
                raw[central + 24:central + 28] = bytes(4)
                forged = bytes(raw)
                with zipfile.ZipFile(io.BytesIO(forged)) as reader:
                    item = reader.infolist()[0]
                    self.assertEqual((item.file_size, item.CRC), (0, 0))
                    self.assertEqual(reader.read(item), b"")
                    start = local + 30 + int.from_bytes(raw[local + 26:local + 28], "little")
                    start += int.from_bytes(raw[local + 28:local + 30], "little")
                    if compression == zipfile.ZIP_DEFLATED:
                        self.assertEqual(zlib.decompress(
                            forged[start:start + item.compress_size], -15), payload)
                with self.assertRaises(DiagnosticRejected):
                    check_retained(forged, "jar")

    def test_staged_jar_rejects_directory_stream_and_header_faults(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as writer:
            writer.writestr("org/", b"")
        valid = archive.getvalue()
        self.assertEqual(check_retained(valid, "jar"), valid)
        local = valid.find(b"PK\x03\x04")
        central = valid.find(b"PK\x01\x02")
        data = local + 30 + len("org/")
        trailing = bytearray(valid[:data + 2] + b"junk" + valid[data + 2:])
        new_central = central + 4
        trailing[local + 18:local + 22] = (6).to_bytes(4, "little")
        trailing[new_central + 20:new_central + 24] = (6).to_bytes(4, "little")
        eocd = trailing.find(b"PK\x05\x06")
        trailing[eocd + 16:eocd + 20] = new_central.to_bytes(4, "little")
        hidden_gap = bytearray(valid[:data + 2] + b"junk" + valid[data + 2:])
        gap_eocd = hidden_gap.find(b"PK\x05\x06")
        hidden_gap[gap_eocd + 16:gap_eocd + 20] = new_central.to_bytes(4, "little")
        truncated = bytearray(valid)
        truncated[data + 1] = 1
        bad_method = bytearray(valid)
        bad_method[local + 8:local + 10] = zipfile.ZIP_STORED.to_bytes(2, "little")
        unsupported_method = bytearray(valid)
        unsupported_method[local + 8:local + 10] = (99).to_bytes(2, "little")
        unsupported_method[central + 10:central + 12] = (99).to_bytes(2, "little")
        bad_name = bytearray(valid)
        bad_name[local + 30] = ord("x")
        for raw in (trailing, hidden_gap, truncated, bad_method,
                    unsupported_method, bad_name):
            with self.subTest(raw=bytes(raw)):
                with self.assertRaises(DiagnosticRejected):
                    check_retained(bytes(raw), "jar")

    def test_equal_poll_observations_and_causal_order(self):
        names = ("stage_start", "stage_end", "gradle_start", "worker_observed",
                 "socket_ready", "attach_observed", "cap_observed", "helper_exit",
                 "target_exit", "observer_start", "observer_exit")
        moments = dict(zip(names, (1, 2, 3, 4, 4, 5, 6, 7, 8, 9, 10)))
        self.assertEqual(_supervisor_phases({"supervisor_milestones_ns": moments})[
            "socket_ready_to_attach_observed_ns"], 1)
        for left, right in (("stage_end", "gradle_start"),
                            ("helper_exit", "target_exit"),
                            ("observer_start", "observer_exit")):
            changed = {**moments, right: moments[left]}
            with self.subTest(left=left), self.assertRaises(DiagnosticRejected):
                _supervisor_phases({"supervisor_milestones_ns": changed})

    def test_typed_replay_failure_and_last_checked_row(self):
        self.assertEqual(str(_replay_failure(DiagnosticRejected("UNAVAILABLE"))),
                         "UNAVAILABLE")
        self.assertEqual(str(_replay_failure(DiagnosticRejected("changed byte"))),
                         "INDEPENDENT_REPLAY_FAILED")
        raw, _ = sample_events()
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            private = Path(directory) / "private"
            output = Path(directory) / "output"
            private.mkdir()
            output.mkdir()
            (private / "progress.tsv").write_bytes(raw.splitlines(keepends=True)[0])
            record = _last_complete_observation(private, output)
            self.assertEqual(record["ordinal"], 0)
            self.assertEqual(hashlib.sha256((output / record["file"]).read_bytes()).hexdigest(),
                             record["sha256"])
            (private / "progress.tsv").write_bytes(
                b'0\t7\t19\t\\u0044YN4K_CAPTURE_ENV_SENTINEL=portable-capture-check\n')
            self.assertIsNone(_last_complete_observation(private, output))
            later = Path(directory) / "later"
            later.mkdir()
            (private / "progress.tsv").write_bytes(
                raw.splitlines(keepends=True)[0] +
                b'1\t7\t19\t\\u0044YN4K_CAPTURE_ENV_SENTINEL=portable-capture-check\n')
            retained = _last_complete_observation(private, later)
            self.assertEqual(retained["ordinal"], 0)
            self.assertEqual((later / retained["file"]).read_bytes(),
                             raw.splitlines(keepends=True)[0])

    def test_resource_replay_binds_process_identity_role_phase_and_affinity(self):
        samples, metadata, files, allocation = resource_replay_fixture()
        _resource_ownership(samples, metadata, files, allocation)
        observed = _resource_evidence(samples, metadata, files, allocation)
        self.assertEqual(observed["observed_role_peak_kib"]["gradle"], 100)
        self.assertEqual(observed["observed_role_peak_kib"]["tracer"], 200)
        self.assertEqual(observed["observed_role_peak_kib"]["other"], 100)
        self.assertEqual(observed["sampled_aggregate_peak_kib"], 500)
        self.assertEqual(samples[2]["pids"][1]["roles"], ["other"])
        for change in ({"pid": 999999999}, {"start_ticks": 999},
                       {"parent_pid": 200}, {"group_pid": 200},
                       {"session_pid": 200}, {"affinity": [11]},
                       {"roles": ["tracer"]}):
            changed = json.loads(json.dumps(samples))
            changed[1]["pids"][1].update(change)
            with self.subTest(change=change), self.assertRaises(DiagnosticRejected):
                _resource_ownership(changed, metadata, files, allocation)
        for role in ("tracer", "worker", "helper", "observer"):
            changed = json.loads(json.dumps(samples))
            changed[1]["pids"][1]["roles"] = [role]
            with self.subTest(spoof=role), self.assertRaises(DiagnosticRejected):
                _resource_ownership(changed, metadata, files, allocation)
        for sample_index, row_index in ((0, 2), (0, 4), (3, 1)):
            changed = json.loads(json.dumps(samples))
            changed[sample_index]["pids"][row_index]["roles"] = ["tracer"]
            with self.subTest(role_pid=changed[sample_index]["pids"][row_index]["pid"]), \
                    self.assertRaises(DiagnosticRejected):
                _resource_ownership(changed, metadata, files, allocation)
        changed = json.loads(json.dumps(samples))
        changed[1]["pids"][1]["command_sha256"] = "f" * 64
        with self.assertRaises(DiagnosticRejected):
            _resource_ownership(changed, metadata, files, allocation)
        unproved = json.loads(json.dumps(samples))
        argv = ["java", "UntracedProgram"]
        digest = hashlib.sha256(("\0".join(argv) + "\0").encode()).hexdigest()
        unproved[1]["pids"][1]["command_sha256"] = digest
        metadata_with_command = {**metadata,
            "resource_commands": {**metadata["resource_commands"], digest: argv}}
        with self.assertRaisesRegex(DiagnosticRejected, "raw execution proof"):
            _resource_ownership(unproved, metadata_with_command, files, allocation)
        untraced = json.loads(json.dumps(samples))
        untraced[1]["wall_start_ns"] -= 140_000_000
        untraced[1]["wall_end_ns"] -= 140_000_000
        with self.assertRaises(DiagnosticRejected):
            _resource_ownership(untraced, metadata, files, allocation)
        with self.assertRaises(DiagnosticRejected):
            changed = json.loads(json.dumps(samples))
            changed[1]["time_ns"] = 7_600_000_000
            _resource_ownership(changed, metadata, files, allocation)

    def test_wrapper_shebang_replays_same_pid_shell_then_java(self):
        samples, metadata, files, allocation = wrapper_shebang_fixture()
        result = _resource_evidence(samples, metadata, files, allocation)
        self.assertEqual(result["sampled_aggregate_peak_kib"], 500)
        _, executions = _resource_execs(files, metadata)
        wrapper = str(ROOT / "gradlew")
        self.assertEqual(executions["target"][101][0][1], "/bin/sh")
        self.assertEqual(executions["target"][101][0][3], wrapper)
        self.assertEqual(executions["target"][101][1][1], str(JDK21 / "bin/java"))
        self.assertEqual([sample["pids"][1]["roles"] for sample in samples[:2]],
                         [["gradle"], ["gradle"]])

    def test_wrapper_shebang_rejects_changed_identity_args_and_order(self):
        samples, metadata, files, allocation = wrapper_shebang_fixture()
        wrapper = str(ROOT / "gradlew")
        original = f'execve({json.dumps(wrapper)}, {json.dumps([wrapper, "jvmTest"])}, 0) = 0'.encode()
        with zipfile.ZipFile(io.BytesIO(files["all-process-traces.zip"])) as archive:
            traces = {name: archive.read(name) for name in archive.namelist()}

        def changed_trace(old, new):
            changed = dict(files)
            rows = dict(traces)
            assert rows["trace.101"].count(old) == 1
            rows["trace.101"] = rows["trace.101"].replace(old, new, 1)
            changed["all-process-traces.zip"] = _zip_checked(rows, "trace_zip")
            return changed

        misordered = dict(files)
        rows = dict(traces)
        lines = rows["trace.101"].splitlines(keepends=True)
        first_time, first_call = lines[0].split(b" ", 1)
        second_time, second_call = lines[1].split(b" ", 1)
        lines[:2] = [first_time + b" " + second_call,
                     second_time + b" " + first_call]
        rows["trace.101"] = b"".join(lines)
        misordered["all-process-traces.zip"] = _zip_checked(rows, "trace_zip")
        for label, altered in (
            ("script", changed_trace(original, original.replace(
                json.dumps(wrapper).encode(), json.dumps(wrapper + "-copy").encode(), 1))),
            ("shell_lookalike", changed_trace(original, original.replace(
                json.dumps(wrapper).encode(), b'"/tmp/sh"', 1))),
            ("argument", changed_trace(original, original.replace(b'"jvmTest"', b'"test"'))),
            ("argv0", changed_trace(original, original.replace(
                b'["' + wrapper.encode() + b'",', b'["spoof",'))),
            ("missing", changed_trace(original, b'getpid() = 101')),
            ("missing_java", changed_trace(second_call.rstrip(b"\n"), b'getpid() = 101')),
            ("order", misordered),
        ):
            with self.subTest(label=label), self.assertRaises(DiagnosticRejected):
                _resource_ownership(samples, metadata, altered, allocation)
        wrong = copy.deepcopy(samples)
        wrong_meta = copy.deepcopy(metadata)
        wrong[0]["pids"][1]["command_sha256"] = hashlib.sha256(
            ("/bin/bash\0" + wrapper + "\0jvmTest\0").encode()).hexdigest()
        wrong_meta["resource_commands"][wrong[0]["pids"][1]["command_sha256"]] = [
            "/bin/bash", wrapper, "jvmTest"]
        with self.assertRaises(DiagnosticRejected):
            _resource_ownership(wrong, wrong_meta, files, allocation)
        wrong = copy.deepcopy(samples)
        wrong_meta = copy.deepcopy(metadata)
        wrong_argv = ["/bin/sh", wrapper, "test"]
        wrong_digest = hashlib.sha256(("\0".join(wrong_argv) + "\0").encode()).hexdigest()
        wrong[0]["pids"][1]["command_sha256"] = wrong_digest
        wrong_meta["resource_commands"][wrong_digest] = wrong_argv
        with self.assertRaises(DiagnosticRejected):
            _resource_ownership(wrong, wrong_meta, files, allocation)

    def test_wrapper_shebang_is_pinned_to_committed_source(self):
        raw = _source_archive()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            wrapper = archive.read("gradlew")
            members = {name: archive.read(name) for name in archive.namelist()}
        committed = subprocess.check_output(("git", "show", "HEAD:gradlew"), cwd=ROOT)
        self.assertEqual(wrapper, committed)
        self.assertTrue(wrapper.startswith(b"#!/bin/sh\n"))
        members["gradlew"] = b"#!/bin/bash\n" + wrapper.split(b"\n", 1)[1]
        changed = _zip_checked(members)
        commit = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=ROOT)
        with self.assertRaisesRegex(DiagnosticRejected, "wrapper shebang differs"):
            _verify_source_archive(changed, commit.decode().strip(),
                                   child_environment(focused=True))

    def test_roles_require_executed_path_and_entry_point(self):
        samples, metadata, files, allocation = resource_replay_fixture()
        jdk = str(JDK21 / "bin/java")
        daemon = metadata["resource_commands"][samples[1]["pids"][1]["command_sha256"]]
        helper = metadata["resource_commands"][samples[0]["pids"][4]["command_sha256"]]
        observer = metadata["resource_commands"][samples[3]["pids"][1]["command_sha256"]]
        _, executions = _resource_execs(files)
        self.assertEqual(executions["target"][101][1][1], jdk)
        self.assertEqual(_executed_role(jdk, daemon), "gradle")
        self.assertEqual(_executed_role(jdk, helper), "helper")
        self.assertEqual(_executed_role(sys.executable, observer), "observer")
        self.assertEqual(_executed_role(str(ROOT / "gradlew"),
                                         [str(ROOT / "gradlew"), "jvmTest"]), "gradle")
        self.assertEqual(_executed_role(jdk, [jdk, "-jar",
            str(ROOT / "gradle/wrapper/gradle-wrapper.jar"), "jvmTest"]), "gradle")
        self.assertEqual(_executed_role(jdk, [jdk,
            "@" + str(Path.home() / ".gradle/.tmp/gradle-worker-classpath123txt"),
            "worker.org.gradle.process.internal.worker.GradleWorkerMain",
            "'Gradle Test Executor 1'"]), "worker")
        bad_gradle = (
            ("/usr/bin/python3", daemon),
            ("/usr/bin/python3", [jdk, *daemon[1:]]),
            ("/tmp/gradlew-helper", [str(ROOT / "gradlew")]),
            (jdk, [jdk, "-Dtag=GradleDaemon", "NotGradle", "9.5.0"]),
            (jdk, [jdk, "NotGradle", "org.gradle.launcher.daemon.bootstrap.GradleDaemon"]),
            (jdk, [jdk, "-cp", "/tmp/GradleDaemon/lib.jar", "NotGradle"]),
            (jdk, [jdk, "com.example.GradleDaemonProbe", "9.5.0"]),
            (jdk, [jdk, "org.gradle.launcher.daemon.bootstrap.GradleDaemonProbe", "9.5.0"]),
        )
        for path, argv in bad_gradle:
            with self.subTest(path=path, argv=argv):
                self.assertIsNone(_executed_role(path, argv))
        self.assertIsNone(_executed_role(jdk, [*helper[:5],
            "com.example.NotOrdinaryArithmeticProbe", *helper[6:]]))
        self.assertIsNone(_executed_role(sys.executable, [*observer[:4],
            observer[4].replace("ordinary-diagnostic-observer",
                                "ordinary-diagnostic-observer-extra"), *observer[5:]]))

    def test_replay_rejects_genuine_execs_with_spoofed_roles(self):
        samples, metadata, files, allocation = resource_replay_fixture()
        jdk = str(JDK21 / "bin/java")
        daemon = metadata["resource_commands"][samples[1]["pids"][1]["command_sha256"]]
        helper = metadata["resource_commands"][samples[0]["pids"][4]["command_sha256"]]
        observer = metadata["resource_commands"][samples[3]["pids"][1]["command_sha256"]]
        controls = (
            (101, "/usr/bin/python3", daemon),
            (101, "/usr/bin/python3", [jdk, *daemon[1:]]),
            (101, "/tmp/gradlew-helper", [str(ROOT / "gradlew")]),
            (101, jdk, [jdk, "-Dtag=GradleDaemon", "NotGradle", "9.5.0"]),
            (101, jdk, [jdk, "NotGradle", daemon[-2]]),
            (101, jdk, [jdk, "com.example.GradleDaemonProbe", "9.5.0"]),
            (201, jdk, [*helper[:5], "com.example.NotOrdinaryArithmeticProbe",
                        *helper[6:]]),
            (301, sys.executable, [*observer[:4], observer[4].replace(
                "ordinary-diagnostic-observer", "ordinary-diagnostic-observer-extra"),
                *observer[5:]]),
        )
        for pid, path, argv in controls:
            with self.subTest(pid=pid, path=path, argv=argv):
                changed, changed_meta, changed_files = changed_resource_image(
                    samples, metadata, files, pid, path, argv)
                with self.assertRaisesRegex(
                        DiagnosticRejected, "role differs|observer resource identity"):
                    _resource_ownership(changed, changed_meta, changed_files, allocation)
        unrelated, unrelated_meta, unrelated_files = changed_resource_image(
            samples, metadata, files, 101, "/usr/bin/python3", [jdk, *daemon[1:]])
        unrelated[1]["pids"][1]["roles"] = ["other"]
        retained = _resource_evidence(unrelated, unrelated_meta, unrelated_files,
                                      allocation)
        self.assertEqual(retained["sampled_aggregate_peak_kib"], 500)
        self.assertEqual(retained["observed_role_peak_kib"]["other"], 100)
        changed = copy.deepcopy(samples)
        changed[1]["pids"][1]["roles"] = ["tracer"]
        with self.assertRaisesRegex(DiagnosticRejected, "role differs"):
            _resource_ownership(changed, metadata, files, allocation)
        _resource_ownership(samples, metadata, files, allocation)
        self.assertEqual([sample["pids"][1]["roles"] for sample in samples[:3]],
                         [["gradle"], ["gradle"], ["other"]])

    def test_live_sample_uses_executable_instead_of_spoofed_argv_zero(self):
        jdk = str(JDK21 / "bin/java")
        script = ("import subprocess,sys; p=subprocess.Popen("
                  "[sys.argv[1], '5'], executable='/usr/bin/sleep'); "
                  "print(p.pid, flush=True); p.wait()")
        leader = subprocess.Popen([sys.executable, "-B", "-c", script, jdk],
                                  stdout=subprocess.PIPE, start_new_session=True)
        try:
            child_pid = int(leader.stdout.readline())
            sample = _owned_sample({"gradle": leader.pid}, "stage")
            row = next(item for item in sample["pids"] if item["pid"] == child_pid)
            self.assertEqual(row["roles"], ["other"])
            self.assertEqual(row["command_sha256"], hashlib.sha256(
                (jdk + "\0" + "5\0").encode()).hexdigest())
        finally:
            os.killpg(leader.pid, signal.SIGTERM)
            leader.wait(timeout=5)
            leader.stdout.close()

    def test_stage_exec_requires_its_retained_process_trace(self):
        samples, metadata, files, allocation = resource_replay_fixture()
        command_hashes = metadata["resource_commands"]
        java = next(digest for digest, argv in command_hashes.items()
                    if "org.gradle.launcher.daemon.bootstrap.GradleDaemon" in argv)
        wrapper = str(ROOT / "gradlew")
        proc_argv = ["/bin/sh", wrapper, "publish"]
        proc_digest = hashlib.sha256(("\0".join(proc_argv) + "\0").encode()).hexdigest()
        stage_command = ["strace", "stage", wrapper, "publish"]
        stage_hash = hashlib.sha256(("\0".join(stage_command) + "\0").encode()).hexdigest()
        metadata = {**metadata, "stage_trace_command": stage_command,
                    "stage_command": [wrapper, "publish"],
                    "resource_commands": {digest: command_hashes[digest]
                        for digest in (java,)} | {stage_hash: stage_command,
                                               proc_digest: proc_argv}}
        root = {"pid": 10, "parent_pid": 1, "group_pid": 10,
                "session_pid": 10, "start_ticks": 10,
                "affinity": [12, 13], "roles": ["tracer"], "rss_kib": 10,
                "command_sha256": stage_hash}
        child = {**root, "pid": 11, "parent_pid": 10, "start_ticks": 11,
                 "roles": ["gradle"], "command_sha256": proc_digest}
        base = 1699999998 * 1_000_000_000
        stage_samples = [
            {"time_ns": 1_200_000_000, "wall_start_ns": base + 190_000_000,
             "wall_end_ns": base + 210_000_000, "phase": "stage",
             "pids": [root, child]},
            {"time_ns": 1_400_000_000, "wall_start_ns": base + 390_000_000,
             "wall_end_ns": base + 410_000_000, "phase": "stage",
             "pids": [root, {**child, "command_sha256": java}]}]
        changed = dict(files)
        with zipfile.ZipFile(io.BytesIO(files["stage-process-traces.zip"])) as source:
            original = source.read("trace.11")
        old_exec = f'execve("/bin/sh", {json.dumps(["sh", wrapper])}, 0) = 0'.encode()
        new_exec = f'execve({json.dumps(wrapper)}, {json.dumps([wrapper, "publish"])}, 0) = 0'.encode()
        self.assertEqual(original.count(old_exec), 1)
        changed["stage-process-traces.zip"] = _zip_checked({
            "trace.11": original.replace(old_exec, new_exec, 1)}, "trace_zip")
        _resource_ownership(stage_samples, metadata, changed, allocation)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as writer:
            writer.writestr("trace.11", b"1699999998.800000 +++ exited with 0 +++\n")
        changed["stage-process-traces.zip"] = archive.getvalue()
        with self.assertRaises(DiagnosticRejected):
            _resource_ownership(stage_samples, metadata, changed, allocation)

    def test_live_proc_sample_records_own_group_start_and_cpu_affinity(self):
        child = subprocess.Popen(["sleep", "5"], start_new_session=True)
        try:
            sample = _owned_sample({"gradle": child.pid}, "stage")
            leader = next(row for row in sample["pids"] if row["pid"] == child.pid)
            self.assertEqual(leader["roles"], ["tracer"])
            self.assertEqual(leader["group_pid"], child.pid)
            self.assertEqual(leader["session_pid"], child.pid)
            self.assertGreater(leader["start_ticks"], 0)
            self.assertEqual(set(leader["affinity"]), os.sched_getaffinity(0))
        finally:
            child.terminate()
            child.wait(timeout=5)

    def test_exited_child_is_absent_and_zombie_is_not_sampled_as_live(self):
        exited = subprocess.Popen(["true"], start_new_session=True)
        exited.wait(timeout=5)
        self.assertEqual(_owned_sample({"gradle": exited.pid}, "stage")["pids"], [])
        zombie = subprocess.Popen(["true"], start_new_session=True)
        try:
            for _ in range(100):
                if (Path(f"/proc/{zombie.pid}/stat").read_text().split(") ", 1)[1]
                        .startswith("Z ")):
                    break
                time.sleep(0.01)
            else:
                self.fail("child did not enter zombie state")
            self.assertEqual(_owned_sample({"gradle": zombie.pid}, "stage")["pids"], [])
        finally:
            zombie.wait(timeout=5)

    def test_sampler_rejects_changed_pid_identity_and_access_failure(self):
        child = subprocess.Popen(["sleep", "5"], start_new_session=True)
        original = diagnostic._proc_identity
        try:
            def changed(pid):
                identity = original(pid)
                if pid == child.pid:
                    identity["start_ticks"] += 1
                return identity
            with mock.patch.object(diagnostic, "_proc_identity", side_effect=changed):
                with self.assertRaisesRegex(DiagnosticRejected, "UNAVAILABLE") as failure:
                    _owned_sample({"gradle": child.pid}, "stage")
            self.assertEqual(failure.exception.detail["reason"], "PID_IDENTITY_CHANGED")
            real_readlink = os.readlink
            def denied(path, *args, **kwargs):
                if str(path) == f"/proc/{child.pid}/exe":
                    raise PermissionError(13, "private command output must not be copied")
                return real_readlink(path, *args, **kwargs)
            with mock.patch.object(diagnostic.os, "readlink", side_effect=denied):
                with self.assertRaisesRegex(DiagnosticRejected, "UNAVAILABLE") as failure:
                    _owned_sample({"gradle": child.pid}, "stage")
            self.assertEqual(failure.exception.detail["reason"], "EXECUTABLE_READ_FAILED")
            self.assertNotIn("private command output", str(failure.exception.detail))
        finally:
            child.terminate()
            child.wait(timeout=5)

    def test_sample_failure_report_retains_only_typed_process_evidence(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            allocation = Path(directory) / "allocation.json"
            allocation.write_text(json.dumps({
                "schema": "ordinary-arithmetic-resource-allocation/1",
                "diagnostic_runtime_allocation": "SCHEDULED",
                "available_memory_kib": 1024,
                "other_tasks_preserved": True,
                "cpu_set": [min(os.sched_getaffinity(0))]}))
            output = Path(directory) / "output"
            failure = SampleUnavailable("stage", 123, "EXECUTABLE_READ_FAILED",
                                        PermissionError(13, "private command text"))
            with mock.patch.object(diagnostic, "clean_source", side_effect=failure):
                report = diagnostic.capture(output, allocation)
            self.assertEqual(report["status"], "UNAVAILABLE")
            self.assertEqual(report["runtime"], "INCOMPLETE")
            self.assertEqual(report["failure_detail"], {
                "phase": "stage", "pid": 123,
                "reason": "EXECUTABLE_READ_FAILED", "errno": 13})
            self.assertNotIn(b"private command text",
                             (output / "diagnostic.json").read_bytes())

    def test_live_unknown_command_rss_and_stat_fail_closed(self):
        child = subprocess.Popen(["sleep", "5"], start_new_session=True)
        read_bytes = Path.read_bytes
        read_text = Path.read_text
        try:
            def missing_command(path):
                return b"" if path == Path(f"/proc/{child.pid}/cmdline") else read_bytes(path)
            with mock.patch.object(Path, "read_bytes", missing_command):
                with self.assertRaisesRegex(DiagnosticRejected, "UNAVAILABLE") as error:
                    _owned_sample({"gradle": child.pid}, "stage")
            self.assertEqual(error.exception.detail["reason"], "COMMAND_MISSING")

            for command in (b"\0", b"\0sleep\0\0"):
                def empty_first_argument(path, *args, **kwargs):
                    if path == Path(f"/proc/{child.pid}/cmdline"):
                        return command
                    return read_bytes(path, *args, **kwargs)
                with mock.patch.object(Path, "read_bytes", empty_first_argument):
                    with self.assertRaisesRegex(DiagnosticRejected, "UNAVAILABLE") as error:
                        _owned_sample({"gradle": child.pid}, "stage")
                self.assertEqual(error.exception.detail["reason"],
                                 "COMMAND_MALFORMED")

            def missing_rss(path, *args, **kwargs):
                if path == Path(f"/proc/{child.pid}/status"):
                    return "Name:\tsleep\n"
                return read_text(path, *args, **kwargs)
            with mock.patch.object(Path, "read_text", missing_rss):
                with self.assertRaisesRegex(DiagnosticRejected, "UNAVAILABLE") as error:
                    _owned_sample({"gradle": child.pid}, "stage")
            self.assertEqual(error.exception.detail["reason"], "RSS_MISSING")

            def denied_stat(path, *args, **kwargs):
                if path == Path(f"/proc/{child.pid}/stat"):
                    raise PermissionError(13, "private text")
                return read_text(path, *args, **kwargs)
            with mock.patch.object(Path, "read_text", denied_stat):
                with self.assertRaisesRegex(DiagnosticRejected, "UNAVAILABLE") as error:
                    _owned_sample({"gradle": child.pid}, "stage")
            self.assertEqual(error.exception.detail["reason"], "STAT_READ_FAILED")
            self.assertNotIn("private text", str(error.exception.detail))
        finally:
            child.terminate()
            child.wait(timeout=5)

    def test_worker_raw_subset_rejects_changed_missing_and_extra_members(self):
        parent = (b"1.0 clone(child_stack=NULL) = 11\n"
                  b"1.1 vfork() = 12\n1.2 +++ exited with 0 +++\n")
        child = b"1.0 +++ exited with 0 +++\n"
        all_raw = _zip_checked({"trace.10": parent, "trace.11": child,
                                "trace.12": child},
                               "trace_zip")
        worker = _zip_checked({"trace.10": parent, "trace.11": child,
                               "trace.12": child},
                              "trace_zip")
        _verify_worker_raw_subset(all_raw, worker, 10)
        for changed in ({"trace.10": parent},
                        {"trace.10": parent, "trace.11": child,
                         "trace.12": child.replace(b"1.0", b"1.1")},
                        {"trace.10": parent, "trace.11": child,
                         "trace.12": child, "trace.13": child}):
            with self.subTest(members=list(changed)), self.assertRaises(DiagnosticRejected):
                _verify_worker_raw_subset(all_raw,
                    _zip_checked(changed, "trace_zip"), 10)

    def test_incomplete_case_and_diagnostic_report_cannot_pass(self):
        with self.assertRaises(DiagnosticRejected):
            verify_case_output(b"<testsuite tests='1'><testcase/></testsuite>",
                               b"", 0)

    def test_capture_without_runtime_allocation_does_not_start_target(self):
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as directory:
            output = Path(directory) / "diagnostic"
            with redirect_stdout(io.StringIO()):
                result = main(["--capture", "--output", str(output)])
            self.assertEqual(result["status"], "NOT_SCHEDULED_RESOURCE")
            self.assertEqual(result["runtime"], "NOT_RUN")
            self.assertEqual({path.name for path in output.iterdir()},
                             {"diagnostic.json"})
            with self.assertRaises(CaptureRejected):
                verify_capture_receipt(result, {}, "captureLongMotion",
                    "0" * 40, ["long-free-60"],
                    "/tmp/dyn4k-tools/jdk21/bin/java")
            qualification = str(Path.cwd() / "tools/qualification")
            sys.path.insert(0, qualification)
            try:
                from independent_gates import verify_pending_prospective_bridge
            finally:
                sys.path.remove(qualification)
            raw = (output / "diagnostic.json").read_bytes()
            bridge = {"prospective_bridge": {"inventory": "diagnostic.json",
                      "inventory_sha256": hashlib.sha256(raw).hexdigest()}}
            with self.assertRaises(ValueError):
                verify_pending_prospective_bridge(
                    output, bridge, Path.cwd(), "0" * 40, "0" * 64, "0" * 64)
            with self.assertRaises(DiagnosticRejected):
                verify_archive(output)
            (output / "receipt.json").write_text("{}")
            with self.assertRaises(DiagnosticRejected):
                verify_archive(output)

    def test_time_and_byte_boundaries_reject_in_replay(self):
        moments = {"stage_start": 1, "gradle_start": 2,
                   "target_exit": 3, "observer_exit": 4}
        helper = {"attach_ns": 1, "detach_complete_ns": 2}
        self.assertEqual(verify_runtime_limits(moments, helper, 1, 1)["time"],
                         "WITHIN_RETAINED_LIMITS")
        for changed, size, observer in (
            ({**moments, "observer_exit": 1200 * 1000000000 + 2}, 1, 1),
            (moments, 1800 * 1024 * 1024, 1),
            (moments, 1, 128 * 1024 * 1024 + 1)):
            with self.subTest(changed=changed, size=size, observer=observer), \
                    self.assertRaises(DiagnosticRejected):
                verify_runtime_limits(changed, helper, size, observer)

    def test_selected_transport_must_close_after_exchange(self):
        home = str(Path.home() / "ordinary-jdi-control")
        argv = ["/tmp/dyn4k-tools/jdk21/bin/java", "--add-modules", "jdk.jdi",
                "-Djava.io.tmpdir=" + home, "-cp", home + "/classes",
                "OrdinaryArithmeticProbe", "attach", home + "/output",
                "127.0.0.1", "40001", "600"]
        worker = (
            b'1.000001 execve("/tmp/dyn4k-tools/jdk21/bin/java", '
            b'["java", "worker.org.gradle.process.internal.worker.GradleWorkerMain", '
            b'"executor"], 0x7f) = 0\n'
            b'1.0000011 socket(AF_INET, SOCK_STREAM, IPPROTO_TCP) = 9<TCP:[90]>\n'
            b'1.000002 bind(9<TCP:[90]>, {sa_family=AF_INET, '
            b'sin_port=htons(40001), sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n'
            b'1.000003 listen(9<TCP:[127.0.0.1:40001]>, 1) = 0\n'
            b'1.000005 accept(9<TCP:[127.0.0.1:40001]>, '
            b'{sa_family=AF_INET, sin_port=htons(41000), '
            b'sin_addr=inet_addr("127.0.0.1")}, [128 => 16]) '
            b'= 10<TCP:[127.0.0.1:40001->127.0.0.1:41000]>\n'
            b'1.000008 recvfrom(10<TCP:[127.0.0.1:40001->127.0.0.1:41000]>, '
            b'"JDWP-Handshake", 14, 0, NULL, NULL) = 14\n'
            b'1.000009 sendto(10<TCP:[127.0.0.1:40001->127.0.0.1:41000]>, '
            b'"JDWP-Handshake", 14, 0, NULL, 0) = 14\n'
            b'1.000012 recvfrom(10<TCP:[127.0.0.1:40001->127.0.0.1:41000]>, '
            b'"request", 7, 0, NULL, NULL) = 7\n'
            b'1.000013 sendto(10<TCP:[127.0.0.1:40001->127.0.0.1:41000]>, '
            b'"response", 8, 0, NULL, 0) = 8\n')
        helper = (
            b'1.000004 execve("/tmp/dyn4k-tools/jdk21/bin/java", ' +
            str(argv).replace("'", '"').encode() + b', 0x7f) = 0\n'
            b'1.000006 socket(AF_INET, SOCK_STREAM, IPPROTO_IP) = 7<TCP:[91]>\n'
            b'1.000007 connect(7<TCP:[91]>, {sa_family=AF_INET, '
            b'sin_port=htons(40001), sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n'
            b'1.0000071 getsockname(7<TCP:[127.0.0.1:41000->127.0.0.1:40001]>, '
            b'{sa_family=AF_INET, sin_port=htons(41000), '
            b'sin_addr=inet_addr("127.0.0.1")}, [128 => 16]) = 0\n'
            b'1.0000072 write(7<TCP:[127.0.0.1:41000->127.0.0.1:40001]>, '
            b'"JDWP-Handshake", 14) = 14\n'
            b'1.000010 read(7<TCP:[127.0.0.1:41000->127.0.0.1:40001]>, '
            b'"JDWP-Handshake", 14) = 14\n'
            b'1.000011 write(7<TCP:[127.0.0.1:41000->127.0.0.1:40001]>, '
            b'"request", 7) = 7\n'
            b'1.000014 read(7<TCP:[127.0.0.1:41000->127.0.0.1:40001]>, '
            b'"response", 8) = 8\n')
        close = (b'1.000015 close(7<TCP:[127.0.0.1:41000->127.0.0.1:40001]>) = 0\n'
                 b'1.000016 +++ exited with 0 +++\n')
        worker_close = (b'1.0000155 close(10<TCP:[127.0.0.1:40001->'
                        b'127.0.0.1:41000]>) = 0\n')
        def zipped(raw, pid):
            data = io.BytesIO()
            with zipfile.ZipFile(data, "w") as writer:
                writer.writestr("trace." + str(pid), raw)
            return data.getvalue()
        result = jdi_bridge.verify_jdi_transport_v6(
            zipped(worker + worker_close, 123), zipped(helper + close, 456),
            40001, 123, 456, argv,
            ordinary_diagnostic=True)
        self.assertEqual(result["status"], "PROVED_JDI_RAW_EXCHANGE")
        self.assertEqual(result["worker_closed_at"], "1.0000155")
        with self.assertRaises(jdi_bridge.EvidenceRejected):
            jdi_bridge.verify_jdi_transport_v6(
                zipped(worker, 123), zipped(helper + close, 456),
                40001, 123, 456, argv, ordinary_diagnostic=True)
        for changed in (helper + close.splitlines(keepends=True)[-1],
                        helper + close.replace(b"close(7<", b"close(8<"),
                        helper.replace(b"1.000014 read(",
                            b"1.0000135 close(7<TCP:[127.0.0.1:41000->"
                            b"127.0.0.1:40001]>) = 0\n1.000014 read(") +
                        b"1.000016 +++ exited with 0 +++\n"):
            with self.subTest(changed=changed[-85:]), self.assertRaises(
                    jdi_bridge.EvidenceRejected):
                jdi_bridge.verify_jdi_transport_v6(
                    zipped(worker + worker_close, 123), zipped(changed, 456),
                    40001, 123, 456, argv,
                    ordinary_diagnostic=True)


if __name__ == "__main__":
    unittest.main()
