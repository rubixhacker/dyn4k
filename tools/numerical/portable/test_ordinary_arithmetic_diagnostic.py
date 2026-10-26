import io
import hashlib
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
import tempfile
import unittest
import zipfile
from pathlib import Path

from ordinary_arithmetic_diagnostic import (
    DiagnosticRejected, check_retained, verify_events, verify_lifecycle,
    verify_resource_samples, verify_case_output, validate_request,
    verify_runtime_limits, verify_worker_classpath, _allocation_ready,
    main, verify_archive, _supervisor_phases, _replay_failure,
    _last_complete_observation, _resource_ownership, _zip_checked,
    _verify_worker_raw_subset,
    _owned_sample, _resource_evidence,
)
from actual_arithmetic import CaptureRejected, verify_capture_receipt
import actual_arithmetic
from boolean_rotation_jdi import jdi_bridge


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


class DiagnosticContractTest(unittest.TestCase):
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
        samples = [{"time_ns": 1, "phase": "target", "pids": [
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
        def archive(*pids):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as writer:
                for pid in pids:
                    raw = (b'1.0 execve("/usr/bin/python", '
                           b'["python", "ordinary-diagnostic-observer"], 0) = 0\n'
                           b'1.1 +++ exited with 0 +++\n') if pid == 301 else (
                           b"1.0 +++ exited with 0 +++\n")
                    writer.writestr(f"trace.{pid}", raw)
            return stream.getvalue()
        files = {"all-process-traces.zip": archive(101, 102),
                 "helper-traces.zip": archive(201),
                 "observer-traces.zip": archive(301)}
        def root(pid):
            return {"pid": pid, "parent_pid": 1, "group_pid": pid,
                    "session_pid": pid, "start_ticks": pid,
                    "affinity": [12, 13]}
        metadata = {"launch_roots": {"stage": root(10), "target": root(100),
                    "helper": root(200), "observer": root(300)},
                    "gradle_root_pid": 100, "helper_root_pid": 200,
                    "observer_root_pid": 300, "worker_pid": 102, "helper_pid": 201,
                    "supervisor_milestones_ns": {"stage_start": 1,
                    "stage_end": 2, "gradle_start": 3, "target_exit": 8,
                    "observer_start": 9, "observer_exit": 10}}
        allocation = {"cpu_set": [12, 13]}
        row = {**root(102), "parent_pid": 100, "group_pid": 100,
               "session_pid": 100, "roles": ["worker"],
               "rss_kib": 1, "command_sha256": "0" * 64}
        leader = {**root(100), "roles": ["tracer"], "rss_kib": 1,
                  "command_sha256": "1" * 64}
        samples = [{"time_ns": 5, "phase": "target", "pids": [leader, row]}]
        _resource_ownership(samples, metadata, files, allocation)
        with self.assertRaisesRegex(DiagnosticRejected, "^UNAVAILABLE$"):
            _resource_evidence(samples, metadata, files, allocation)
        for changed in ({**row, "pid": 999999999},
                        {**row, "group_pid": 200},
                        {**row, "affinity": [11]},
                        {**row, "roles": ["observer"]}):
            with self.subTest(changed=changed), self.assertRaises(DiagnosticRejected):
                _resource_ownership([{"time_ns": 5, "phase": "target",
                                      "pids": [leader, changed]}], metadata, files,
                                    allocation)
        with self.assertRaises(DiagnosticRejected):
            _resource_ownership([{"time_ns": 11, "phase": "target",
                                  "pids": [leader, row]}], metadata, files, allocation)

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
