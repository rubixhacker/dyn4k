import hashlib
import shutil
import subprocess
import sys
import unittest
import tempfile
import json
import io
import zipfile
import struct
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from numeric_producer_trace import verify_transport, verify_stable_input, Unbound
from receipt import Rejected


class TracePrivacyTest(unittest.TestCase):
    def test_stat_identity_without_exec_environment_expansion(self):
        from numeric_producer import trace_arguments, SYSCALLS

        tracer = shutil.which("strace")
        self.assertIsNotNone(tracer)
        with tempfile.TemporaryDirectory() as directory:
            canary = "SYNTHETIC_STAGE_B_ENVIRONMENT_CANARY_7f9d0a"
            child = [sys.executable, "-B", "-c",
                     "import os; fd = os.open('/dev/null', os.O_RDONLY); os.fstat(fd); os.close(fd)"]
            synthetic_env = {"STAGE_B_CANARY": canary}
            base = ["-ff", "-ttt", "-yy", "-s", "131072", "-e", "trace=" + SYSCALLS]
            def recorded(name, options):
                prefix = Path(directory) / name
                result = subprocess.run([tracer, *options, "-o", str(prefix), *child],
                                        env=synthetic_env, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0)
                return b"".join(path.read_bytes() for path in prefix.parent.glob(name + ".*"))

            broad = recorded("broad", [*base[:3], "-v", *base[3:]])
            self.assertIn(canary.encode(), broad)
            selective = recorded("selective", trace_arguments())
            self.assertNotIn(canary.encode(), selective)
            self.assertIn(b"execve(", selective)
            self.assertIn(b"st_dev=makedev(", selective)
            self.assertIn(b"st_ino=", selective)
            self.assertEqual(trace_arguments(),
                             ["-ff", "-ttt", "-yy", "-e",
                              "abbrev=!fstat,newfstatat,statx", "-s", "131072", "-e",
                              "trace=" + SYSCALLS])


class TransportTest(unittest.TestCase):
    def test_agent_input_requires_worker_read_and_stable_identity(self):
        path = "/private/agent.jar"
        trace = {"100": (
            b'1.000000 execve("/jdk/bin/java", ["java", "worker.org.gradle.process.internal.worker.GradleWorkerMain"], 0x0) = 0\n'
            b'1.100000 openat(AT_FDCWD, "/private/agent.jar", O_RDONLY) = 4</private/agent.jar>\n'
            b'1.110000 fstat(4</private/agent.jar>, {st_mode=S_IFREG|0644, st_size=3, st_dev=makedev(0, 1), st_ino=44}) = 0\n'
            b'1.120000 read(4</private/agent.jar>, "JAR", 3) = 3\n'
            b'1.130000 close(4</private/agent.jar>) = 0\n'
            b'1.200000 +++ exited with 0 +++\n')}
        identity = {"device_major": 0, "device_minor": 1, "inode": 44, "size": 3}
        self.assertEqual(verify_stable_input(trace, path, identity, "100")["reads"], 1)
        with self.assertRaises(Rejected):
            verify_stable_input({"100": trace["100"].replace(b'"JAR", 3', b'"JAR", 3')
                                 .replace(b'O_RDONLY', b'O_RDWR')}, path, identity, "100")
        with self.assertRaises(Rejected):
            verify_stable_input(trace, path, {**identity, "inode": 45}, "100")
        with self.assertRaises(Unbound):
            verify_stable_input({"100": trace["100"].replace(b'1.120000 read(4</private/agent.jar>, "JAR", 3) = 3\n', b'')},
                                path, identity, "100")

    def trace(self, read=True):
        calls = [
            '1.000000 execve("/jdk/bin/java", ["/jdk/bin/java", "@/work/args.txt", "worker.org.gradle.process.internal.worker.GradleWorkerMain"], 0x0 /* 0 vars */) = 0',
            '1.100000 openat(AT_FDCWD, "/work/args.txt", O_RDONLY) = 3</work/args.txt>',
            '1.110000 fstat(3</work/args.txt>, {st_dev=makedev(0, 1), st_ino=12, st_mode=S_IFREG|0600, st_size=7, ...}) = 0',
        ]
        if read:
            calls.append('1.120000 read(3</work/args.txt>, "-cp\\n/a\\n", 4096) = 7')
        calls += [
            '1.130000 close(3</work/args.txt>) = 0',
            '1.200000 openat(AT_FDCWD, "/work/mirror.log", O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW, 0600) = 4</work/mirror.log>',
            '1.210000 write(4</work/mirror.log>, "hello\\n", 6) = 6',
            '1.220000 close(4</work/mirror.log>) = 0',
            '2.000000 +++ exited with 0 +++',
        ]
        return {"100": ("\n".join(calls) + "\n").encode()}

    def test_response_open_without_read_cannot_bind_producer(self):
        with self.assertRaisesRegex(Unbound, "response.*read"):
            verify_transport(self.trace(False), "/work/mirror.log", b"hello\n",
                             "/work/args.txt", b"-cp\n/a\n")

    def test_malformed_trace_record_rejects(self):
        malformed = self.trace()["100"].replace(b"1.000000 execve", b"not-a-time execve")
        with self.assertRaisesRegex(Rejected, "trace timestamp") as error:
            verify_transport({"100": malformed}, "/work/mirror.log", b"hello\n",
                             "/work/args.txt", b"-cp\n/a\n")
        self.assertNotIsInstance(error.exception, Unbound)

    def test_exact_response_read_and_exclusive_output_bind_transport(self):
        proof = verify_transport(self.trace(), "/work/mirror.log", b"hello\n",
                                 "/work/args.txt", b"-cp\n/a\n")
        self.assertEqual(proof["worker_pid"], "100")
        self.assertEqual(proof["mirror_writer_tid"], "100")
        without_no_follow = self.trace()["100"].replace(b"O_EXCL|O_NOFOLLOW", b"O_EXCL")
        proof = verify_transport({"100": without_no_follow}, "/work/mirror.log", b"hello\n",
                                 "/work/args.txt", b"-cp\n/a\n")
        self.assertEqual(proof["mirror_writer_tid"], "100")

    def test_substitutions_cannot_bind_transport(self):
        mutations = {
            "read bytes": (b'"-cp\\n/a\\n", 4096', b'"-cp\\n/b\\n", 4096'),
            "response identity": (b"st_size=7", b"st_size=8"),
            "missing identity": (b"fstat(", b"ignored("),
            "unexclusive creation": (b"O_EXCL|", b""),
            "descriptor reuse": (b'1.210000 write', b'1.205000 close(4</work/mirror.log>) = 0\n1.210000 write'),
            "output bytes": (b'"hello\\n", 6', b'"jello\\n", 6'),
            "partial write": (b'"hello\\n", 6) = 6', b'"hello\\n", 6) = 5'),
            "worker exit": (b"exited with 0", b"exited with 1"),
            "missing thread": (b'1.200000 openat', b'1.190000 clone(flags=CLONE_THREAD|CLONE_FILES) = 101\n1.200000 openat'),
            "replacement": (b'1.220000 close', b'1.215000 unlink("/work/mirror.log") = 0\n1.220000 close'),
        }
        for name, (old, new) in mutations.items():
            with self.subTest(name=name), self.assertRaises(Rejected):
                verify_transport({"100": self.trace()["100"].replace(old, new)},
                                 "/work/mirror.log", b"hello\n", "/work/args.txt", b"-cp\n/a\n")

    def test_dup_and_thread_membership_preserve_destination(self):
        trace = self.trace()
        original = b'1.210000 write(4</work/mirror.log>, "hello\\n", 6) = 6\n'
        trace["100"] = trace["100"].replace(original,
            b'1.205000 dup(4</work/mirror.log>) = 5</work/mirror.log>\n'
            b'1.206000 clone(flags=CLONE_THREAD|CLONE_FILES) = 101\n')
        trace["101"] = (b'1.210000 writev(5</work/mirror.log>, [{iov_base="hello", iov_len=5}, '
                        b'{iov_base="\\n", iov_len=1}], 2) = 6\n'
                        b'1.215000 close(5</work/mirror.log>) = 0\n'
                        b'1.900000 +++ exited with 0 +++\n')
        proof = verify_transport(trace, "/work/mirror.log", b"hello\n", "/work/args.txt", b"-cp\n/a\n")
        self.assertEqual((proof["mirror_writer_tid"], proof["mirror_fd"]), ("101", "5"))
        trace["100"] = trace["100"].replace(b"CLONE_THREAD|CLONE_FILES", b"SIGCHLD")
        with self.assertRaises(Rejected):
            verify_transport(trace, "/work/mirror.log", b"hello\n", "/work/args.txt", b"-cp\n/a\n")

    def test_parent_can_create_response_before_worker_reads_it(self):
        trace = self.trace()
        trace["99"] = (b'0.100000 openat(AT_FDCWD, "/work/args.txt", O_WRONLY|O_CREAT|O_TRUNC, 0600) = 3</work/args.txt>\n'
                       b'0.200000 write(3</work/args.txt>, "-cp\\n/a\\n", 7) = 7\n'
                       b'0.300000 close(3</work/args.txt>) = 0\n'
                       b'0.900000 clone(flags=SIGCHLD) = 100\n'
                       b'2.100000 unlink("/work/args.txt") = 0\n'
                       b'2.200000 +++ exited with 0 +++\n')
        proof = verify_transport(trace, "/work/mirror.log", b"hello\n", "/work/args.txt", b"-cp\n/a\n")
        self.assertEqual(proof["parent_pids"], ["99"])

    def test_mirror_seek_cannot_bind_sequential_output_bytes(self):
        for operation in (
            b'lseek(4</work/mirror.log>, 100, SEEK_SET) = 100',
            b'lseek(4</work/mirror.log>, 100, SEEK_CUR) = 100',
            b'lseek(4</work/mirror.log>, 100, SEEK_END) = 100',
        ):
            with self.subTest(operation=operation), self.assertRaisesRegex(Rejected, "mirror seek"):
                trace = self.trace()["100"].replace(
                    b'1.210000 write', b'1.205000 ' + operation + b'\n1.210000 write')
                verify_transport({"100": trace}, "/work/mirror.log", b"hello\n",
                                 "/work/args.txt", b"-cp\n/a\n")

    def test_auxiliary_log_may_reset_empty_file_before_first_write(self):
        trace = self.trace()["100"].replace(
            b'1.210000 write',
            b'1.205000 lseek(4</work/mirror.log>, 0, SEEK_END) = 0\n'
            b'1.206000 ftruncate(4</work/mirror.log>, 0) = 0\n'
            b'1.210000 write')
        verify_transport({"100": trace}, "/work/mirror.log", b"hello\n",
                         "/work/args.txt", b"-cp\n/a\n", exclusive=False, ordered=False)
        with self.assertRaisesRegex(Rejected, "mirror seek"):
            verify_transport({"100": trace.replace(b'0, SEEK_END) = 0', b'1, SEEK_END) = 1')},
                             "/work/mirror.log", b"hello\n", "/work/args.txt", b"-cp\n/a\n",
                             exclusive=False, ordered=False)
        with self.assertRaisesRegex(Rejected, "unsupported access"):
            changed = trace.replace(b'1.220000 close',
                                    b'1.215000 ftruncate(4</work/mirror.log>, 0) = 0\n1.220000 close')
            verify_transport({"100": changed}, "/work/mirror.log", b"hello\n",
                             "/work/args.txt", b"-cp\n/a\n", exclusive=False, ordered=False)

    def test_close_range_and_untraced_writer_cannot_leave_valid_descriptor(self):
        for call in (b'1.205000 close_range(3, 10, 0) = 0\n',
                     b'1.205000 pwrite64(4</work/mirror.log>, "hello\\n", 6, 0) = 6\n'):
            with self.subTest(call=call), self.assertRaises(Rejected):
                verify_transport({"100": self.trace()["100"].replace(b'1.210000 write', call + b'1.210000 write')},
                                 "/work/mirror.log", b"hello\n", "/work/args.txt", b"-cp\n/a\n")

    def test_positioned_and_vector_reads_cover_exact_response_bytes(self):
        original = b'read(3</work/args.txt>, "-cp\\n/a\\n", 4096) = 7'
        for replacement in (
            b'pread64(3</work/args.txt>, "-cp\\n/a\\n", 4096, 0) = 7',
            b'readv(3</work/args.txt>, [{iov_base="-cp\\n", iov_len=4}, {iov_base="/a\\n", iov_len=3}], 2) = 7',
        ):
            with self.subTest(call=replacement):
                proof = verify_transport({"100": self.trace()["100"].replace(original, replacement)},
                                         "/work/mirror.log", b"hello\n", "/work/args.txt", b"-cp\n/a\n")
                self.assertEqual(proof["worker_exit"], 0)

    def test_backward_response_seek_does_not_count_repeated_bytes_twice(self):
        trace = self.trace()["100"].replace(
            b'st_size=7', b'st_size=6').replace(
            b'read(3</work/args.txt>, "-cp\\n/a\\n", 4096) = 7',
            b'read(3</work/args.txt>, "abc", 3) = 3\n'
            b'1.125000 lseek(3</work/args.txt>, -3, SEEK_CUR) = 0\n'
            b'1.126000 read(3</work/args.txt>, "abc", 3) = 3')
        with self.assertRaisesRegex(Unbound, "response.*seek|response.*incomplete"):
            verify_transport({"100": trace}, "/work/mirror.log", b"hello\n",
                             "/work/args.txt", b"abcabc")

    def test_mirror_identity_must_match_original_captured_file(self):
        from numeric_producer import captured_file_identity
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original.log"
            archived = Path(directory) / "archived.log"
            original.write_bytes(b"hello\n")
            archived.write_bytes(original.read_bytes())
            original_identity = captured_file_identity(original)
            self.assertNotEqual(original_identity["inode"], captured_file_identity(archived)["inode"])
            stat_call = ("1.215000 fstat(4</work/mirror.log>, "
                         "{st_dev=makedev(%d, %d), st_ino=%d, st_mode=S_IFREG|0600, st_size=6, ...}) = 0\n" %
                         (original_identity["device_major"], original_identity["device_minor"],
                          original_identity["inode"])).encode()
            relocated_trace = self.trace()["100"].replace(b'1.220000 close', stat_call + b'1.220000 close')
            verify_transport({"100": relocated_trace}, "/work/mirror.log", archived.read_bytes(),
                             "/work/args.txt", b"-cp\n/a\n", mirror_identity=original_identity)
        trace = self.trace()["100"].replace(
            b'1.220000 close',
            b'1.215000 fstat(4</work/mirror.log>, '
            b'{st_dev=makedev(0, 1), st_ino=13, st_mode=S_IFREG|0600, st_size=6, ...}) = 0\n'
            b'1.220000 close')
        expected = {"device_major": 0, "device_minor": 1, "inode": 13, "size": 6}
        proof = verify_transport({"100": trace}, "/work/mirror.log", b"hello\n",
                                 "/work/args.txt", b"-cp\n/a\n", mirror_identity=expected)
        self.assertEqual(proof["mirror_sha256"], hashlib.sha256(b"hello\n").hexdigest())
        hexadecimal_device = trace.replace(b"makedev(0, 1)", b"makedev(0, 0x1)")
        proof = verify_transport({"100": hexadecimal_device}, "/work/mirror.log", b"hello\n",
                                 "/work/args.txt", b"-cp\n/a\n", mirror_identity=expected)
        self.assertEqual(proof["mirror_sha256"], hashlib.sha256(b"hello\n").hexdigest())
        with self.assertRaisesRegex(Rejected, "mirror file identity differs"):
            verify_transport({"100": trace}, "/work/mirror.log", b"hello\n",
                             "/work/args.txt", b"-cp\n/a\n",
                             mirror_identity={**expected, "inode": 14})
        with self.assertRaisesRegex(Unbound, "mirror file identity unavailable"):
            verify_transport(self.trace(), "/work/mirror.log", b"hello\n",
                             "/work/args.txt", b"-cp\n/a\n", mirror_identity=expected)


class OutputTest(unittest.TestCase):
    def fixture(self):
        from run import method_case_ids
        from prospective_compare import PROBE_VALUES
        cases = {}
        for case in method_case_ids("geometryCollisionBoundaryAndScale"):
            scale_index, origin_index, delta_index = (int(part[1:]) for part in case.split("-")[-3:])
            scale = (0.01, 1.0, 100.0)[scale_index]
            ox, oy = ((0.0, 0.0), (1000.0, 1000.0), (-1000.0, 1000.0),
                      (1000000.0, -1000000.0), (-1000000.0, 1000000.0))[origin_index]
            delta = (-1e-8, -1e-12, 0.0, 1e-12, 1e-8)[delta_index]
            header = {"kind": "inputs", "id": case,
                      "input": {"scale": scale, "delta": delta, "origin": [ox, oy], "signedZero": -0.0},
                      "setup": {"bodies": [
                          {"transform": {"getTranslationX": ox, "getTranslationY": oy}},
                          {"transform": {"getTranslationX": ox + scale * (1.5 + delta),
                                         "getTranslationY": oy}}]}}
            cases[case] = (json.dumps(header) + "\n" + json.dumps({"kind": "case-end", "id": case}) + "\n").encode()
        mirror = b"".join(b"NUMERICAL_JSON " + line for raw in cases.values()
                          for line in raw.splitlines(keepends=True))
        mirror += b"NUMERICAL_PROBE_JSON " + json.dumps(PROBE_VALUES).encode() + b"\n"
        mirror += b'NUMERICAL_PROVIDER_JSON {"classpath":"/bootstrap.jar","effective_classpath":"/test","providers":{}}\n'
        return cases, mirror

    def xml(self, mirror):
        suite = ET.Element("testsuite", tests="1", skipped="0", failures="0", errors="0")
        ET.SubElement(suite, "testcase", classname="portable.NumericProbeMatrixTest",
                      name="geometryCollisionBoundaryAndScale[jvm]")
        ET.SubElement(suite, "system-out").text = mirror.decode()
        return ET.tostring(suite)

    def test_synthetic_output_is_consistent_without_claiming_execution(self):
        from numeric_producer import verify_output
        cases, mirror = self.fixture()
        probe, providers = verify_output(mirror, self.xml(mirror), cases)
        self.assertEqual(probe["negativeZeroBits"], "8000000000000000")
        self.assertIs(probe["maximumFinite"], True)
        self.assertEqual(providers["classpath"], "/bootstrap.jar")

    def test_marker_and_original_stream_substitutions_reject(self):
        from numeric_producer import verify_output
        cases, mirror = self.fixture()
        changes = {
            "numeric Boolean": (b'"maximumFinite": true', b'"maximumFinite": 1'),
            "negative zero bits": (b'8000000000000000', b'0000000000000000'),
            "gap bits": (b'3d71980000000000', b'0000000000000000'),
            "original bytes": (b'"signedZero": -0.0', b'"signedZero": 0.0'),
            "missing case": (b'geometry-boundary-s0-o0-d0', b'unknown'),
            "duplicate marker": (b'NUMERICAL_PROVIDER_JSON', b'NUMERICAL_PROBE_JSON'),
        }
        for name, (old, new) in changes.items():
            with self.subTest(name=name), self.assertRaises(Rejected):
                modified = mirror.replace(old, new)
                verify_output(modified, self.xml(modified), cases)
        for old, new in ((b'tests="1"', b'tests="2"'),
                         (b'skipped="0"', b'skipped="1"'),
                         (b'geometryCollisionBoundaryAndScale[jvm]"', b'geometryCollisionBoundaryAndScale"'),
                         (b'portable.NumericProbeMatrixTest', b'portable.PortableMatrixTest')):
            with self.subTest(xml=new), self.assertRaises(Rejected):
                verify_output(mirror, self.xml(mirror).replace(old, new), cases)
        with self.assertRaisesRegex(Rejected, "mirror differ"):
            verify_output(mirror + b"unexpected\n", self.xml(mirror), cases)

    def test_mirror_requires_exactly_one_probe_and_all_original_streams(self):
        from numeric_producer import verify_output
        with self.assertRaisesRegex(Rejected, "probe marker count"):
            verify_output(b"", b'<testsuite tests="1" skipped="0" failures="0" errors="0"><testcase classname="portable.NumericProbeMatrixTest" name="geometryCollisionBoundaryAndScale[jvm]"/><system-out></system-out></testsuite>', {})


class StartupTest(unittest.TestCase):
    def test_witness_worker_requires_one_agent_and_guard_flags(self):
        from numeric_producer import verify_startup_log
        def raw(flags):
            rows = ("VM Arguments:", "jvm_args: " + flags,
                    "java_command: worker.org.gradle.process.internal.worker.GradleWorkerMain executor",
                    "java_class_path (initial): /bootstrap.jar", "Launcher Type: SUN_STANDARD")
            return "".join("[100][info][arguments] " + row + "\n" for row in rows).encode()
        agent = "-javaagent:/private/observer.jar=/private/witness.log"
        flags = agent + " -XX:+DisableAttachMechanism -Xshare:off -Xmx512m"
        verify_startup_log(raw(flags), "100", "/bootstrap.jar",
                           "/private/observer.jar", "/private/witness.log")
        for changed in (flags.replace("-Xshare:off", ""), flags.replace(agent, ""),
                        flags + " -agentlib:jdwp", flags + " -Xrunjdwp", flags + " " + agent,
                        flags + " --patch-module=java.base=/tmp/shadow"):
            with self.subTest(changed=changed), self.assertRaises(Rejected):
                verify_startup_log(raw(changed), "100", "/bootstrap.jar",
                                   "/private/observer.jar", "/private/witness.log")

    def test_executed_startup_log_rejects_classpath_and_agent_substitution(self):
        from numeric_producer import verify_startup_log
        def raw(classpath="/bootstrap.jar", flags="-Xmx512m"):
            records = ("VM Arguments:", "jvm_args: " + flags,
                       "java_command: worker.org.gradle.process.internal.worker.GradleWorkerMain executor",
                       "java_class_path (initial): " + classpath, "Launcher Type: SUN_STANDARD")
            return "".join("[100][info][arguments] " + row + "\n" for row in records).encode()
        verify_startup_log(raw(), "100", "/bootstrap.jar")
        for data in (raw("/other.jar"), raw(flags="-javaagent:/other.jar"),
                     raw().replace(b"[100]", b"[101]")):
            with self.assertRaises(Rejected):
                verify_startup_log(data, "100", "/bootstrap.jar")


class ArchiveTest(unittest.TestCase):
    def test_sidecar_runtime_must_be_independent_and_match_full_lane(self):
        from numeric_producer import verify_sidecar_identity
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "target.jar"
            artifact.write_bytes(b"target")
            runtime = {"host": "jvm", "os": "linux", "machine": "x86_64",
                       "executable": "/jdk/bin/java", "executable_sha256": "java-hash",
                       "version": 'openjdk version "21.0.0"',
                       "dependency_sha256": hashlib.sha256(b"target").hexdigest()}
            verify_sidecar_identity(dict(runtime), runtime, artifact)
            for field in runtime:
                with self.subTest(field=field), self.assertRaisesRegex(Rejected, "sidecar runtime identity"):
                    verify_sidecar_identity({**runtime, field: "different"}, runtime, artifact)
            with self.assertRaisesRegex(Rejected, "sidecar runtime identity"):
                verify_sidecar_identity({}, runtime, artifact)

    def test_public_schema_two_cannot_pass_without_loaded_class_bytes(self):
        from numeric_producer import encoded, sha, FIXTURE, CLASS, METHOD, SCHEMA
        from prospective_compare import verify_numeric_probe
        from run import declared_cases, method_case_ids
        with tempfile.TemporaryDirectory() as directory:
            lane = Path(directory) / "jvm"
            (lane / "cases").mkdir(parents=True)
            for case in declared_cases():
                (lane / "cases" / (case["id"] + ".jsonl")).write_bytes(b"case\n")
            (lane / "receipt.json").write_bytes(b"{}")
            artifact = Path(directory) / "target.jar"
            artifact.write_bytes(b"artifact")
            runtime = {"method_executions": 15}
            proof = {"worker_pid": "100", "parent_pids": ["1"],
                     "worker_argv_sha256": "0" * 64, "worker_exit": 0,
                     "runtime_executable_sha256": "0" * 64,
                     "classpath_sha256": "0" * 64, "class_archive_sha256": "0" * 64,
                     "provider_origins": {
                         name: "file:///classes" for name in (
                             CLASS, "portable.PortableMatrixTest", "portable.NumericalRecorder",
                             "org.dyn4j.dynamics.Body", "org.dyn4j.geometry.Geometry")},
                     "mirror_writer_tid": "100", "mirror_fd": "4",
                     "mirror_destination": "/work/mirror.log", "mirror_sha256": "0" * 64,
                     "xml_sha256": "0" * 64, "gradle_log_sha256": "0" * 64,
                     "trace_manifest_sha256": "0" * 64}
            receipt = {"schema": SCHEMA, "candidate_commit": "commit", "source_sha256": "source",
                       "fixture_source_sha256": FIXTURE, "trace_sha256": "trace",
                       "primary_receipt_sha256": sha(b"{}"),
                       "geometry_case_sha256": {case: sha(b"case\n") for case in method_case_ids(METHOD)},
                       "artifact_sha256": {"target": sha(b"artifact")}, "runtime": runtime,
                       "selected_test": {"class": CLASS, "method": METHOD, "task": "jvmTest", "host": "jvm"},
                       "probe": {}, "files": {"synthetic": {"size": 1, "sha256": "0" * 64}},
                       "proof": proof}
            (lane / "numeric-probe").mkdir()
            (lane / "numeric-probe" / "synthetic").write_bytes(b"x")
            (lane / "numeric-probe-receipt.json").write_bytes(encoded(receipt))
            with self.assertRaisesRegex(Rejected, "numeric producer proof schema"):
                verify_numeric_probe(lane, "commit", "source", "trace",
                                     {"target": artifact}, runtime)
            proof["class_witness"] = {"schema": "class-witness/1",
                                      "source_sha256": "0" * 64, "agent_sha256": "0" * 64,
                                      "witness_sha256": "0" * 64,
                                      "definition_count": 3,
                                      "definition_inventory_sha256": "0" * 64,
                                      "helper_provider": "file:///private/agent.jar", "input_reads": 1,
                                      "writer_tid": "100", "writer_fd": "5",
                                      "destination": "/private/witness.log"}
            (lane / "numeric-probe-receipt.json").write_bytes(encoded(receipt))
            with patch("numeric_producer.load_raw", return_value={}), \
                    patch("numeric_producer._proof", return_value=proof), \
                    patch("numeric_producer.inventory", return_value=receipt["files"]):
                result = verify_numeric_probe(lane, "commit", "source", "trace",
                                              {"target": artifact}, runtime)
            self.assertEqual(result["status"], "PASSED_BOUND_PRODUCER")
            for changed in ({**proof, "worker_exit": "0"},
                            {**proof, "worker_exit": 1},
                            {**proof, "parent_pids": [True]},
                            {**proof, "mirror_fd": 4},
                            {**proof, "mirror_sha256": "not-a-digest"},
                            {**proof, "provider_origins": {}}):
                receipt["proof"] = changed
                (lane / "numeric-probe-receipt.json").write_bytes(encoded(receipt))
                with self.subTest(changed=changed):
                    with patch("numeric_producer.load_raw", side_effect=AssertionError("raw replay began")), \
                            patch("numeric_producer._proof", side_effect=Unbound("trace final record is truncated")):
                        with self.assertRaisesRegex(Rejected, "numeric producer proof field") as error:
                            verify_numeric_probe(lane, "commit", "source", "trace",
                                                 {"target": artifact}, runtime)
                    self.assertNotIsInstance(error.exception, Unbound)
            receipt["proof"] = proof
            (lane / "numeric-probe-receipt.json").write_bytes(encoded(receipt))
            with patch("numeric_producer.load_raw", return_value={}), \
                    patch("numeric_producer._proof", side_effect=Unbound("trace final record is truncated")), \
                    self.assertRaisesRegex(Rejected, "sealed numeric producer proof cannot be replayed") as error:
                verify_numeric_probe(lane, "commit", "source", "trace", {"target": artifact}, runtime)
            self.assertNotIsInstance(error.exception, Unbound)

    def test_strict_raw_inventory_rejects_resealed_extra_members_and_digest_changes(self):
        from numeric_producer import REQUIRED, inventory, load_raw
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = REQUIRED | {"process/trace.100", "worker-classpath.txt"}
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"raw")
            files = inventory(root)
            self.assertEqual(set(load_raw(root, files)), names)
            (root / "mirror.log").write_bytes(b"changed")
            with self.assertRaisesRegex(Rejected, "digest"):
                load_raw(root, files)
            (root / "mirror.log").write_bytes(b"raw")
            (root / "undeclared.log").write_bytes(b"extra")
            with self.assertRaisesRegex(Rejected, "member set"):
                load_raw(root, inventory(root))
            (root / "undeclared.log").unlink()
            (root / "direct-classpath.json").write_bytes(b"[]")
            with self.assertRaisesRegex(Rejected, "member set"):
                load_raw(root, inventory(root))

    def test_schema_two_identity_substitutions_reject_before_recompile(self):
        from numeric_producer import verify, encoded, sha, FIXTURE, CLASS, METHOD, SCHEMA
        from run import declared_cases, method_case_ids
        with tempfile.TemporaryDirectory() as directory:
            lane = Path(directory) / "jvm"
            (lane / "cases").mkdir(parents=True)
            for case in declared_cases():
                (lane / "cases" / (case["id"] + ".jsonl")).write_bytes(b"case\n")
            (lane / "receipt.json").write_bytes(b"{}")
            artifact = Path(directory) / "target.jar"
            artifact.write_bytes(b"artifact")
            runtime = {"method_executions": 15}
            receipt = {"schema": SCHEMA, "candidate_commit": "commit", "source_sha256": "source",
                       "fixture_source_sha256": FIXTURE, "trace_sha256": "trace",
                       "primary_receipt_sha256": sha(b"{}"),
                       "geometry_case_sha256": {case: sha(b"case\n") for case in method_case_ids(METHOD)},
                       "artifact_sha256": {"target": sha(b"artifact")}, "runtime": runtime,
                       "selected_test": {"class": CLASS, "method": METHOD, "task": "jvmTest", "host": "jvm"},
                       "probe": {}, "files": {}, "proof": {}}
            for field, changed in (("candidate_commit", "other"), ("source_sha256", "other"),
                                   ("fixture_source_sha256", "other"), ("trace_sha256", "other"),
                                   ("primary_receipt_sha256", "other"), ("artifact_sha256", {}),
                                   ("runtime", {"method_executions": 1}), ("selected_test", {}),
                                   ("geometry_case_sha256", {}), ("files", {})):
                with self.subTest(field=field), self.assertRaises(Rejected):
                    modified = {**receipt, field: changed}
                    (lane / "numeric-probe-receipt.json").write_bytes(encoded(modified))
                    verify(lane, "commit", "source", "trace", {"target": artifact}, runtime)

    def test_raw_inventory_rejects_extra_and_linked_files(self):
        from numeric_producer import inventory
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.log").write_bytes(b"one")
            first = inventory(root)
            self.assertEqual(first["one.log"]["size"], 3)
            (root / "linked.log").symlink_to(root / "one.log")
            with self.assertRaisesRegex(Rejected, "linked"):
                inventory(root)

    def test_capture_trace_budget_rejects_oversized_member_and_total(self):
        from numeric_producer import inventory, MAX_TRACE_MEMBER
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = root / "process"
            process.mkdir()
            oversized = process / "trace.1"
            with oversized.open("wb") as stream:
                stream.truncate(MAX_TRACE_MEMBER + 1)
            with self.assertRaisesRegex(Rejected, "raw evidence budget exceeded"):
                inventory(root)
            oversized.unlink()
            for index in range(1, 6):
                with (process / f"trace.{index}").open("wb") as stream:
                    stream.truncate(MAX_TRACE_MEMBER if index < 5 else 1)
            with patch("numeric_producer.digest", return_value="0" * 64):
                with self.assertRaisesRegex(Rejected, "raw evidence budget exceeded"):
                    inventory(root)

    def test_ordinary_raw_total_keeps_512_mib_limit(self):
        from numeric_producer import inventory, load_raw, MAX_TOTAL, MAX_TRACE_MEMBER
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(5):
                with (root / f"ordinary-{index}.log").open("wb") as stream:
                    stream.truncate(120 * 1024 * 1024)
            with patch("numeric_producer.digest", return_value="0" * 64), \
                    self.assertRaisesRegex(Rejected, "raw evidence budget exceeded"):
                inventory(root)
            declared = {f"ordinary-{index}.log": {"size": 120 * 1024 * 1024,
                                                   "sha256": "0" * 64} for index in range(5)}
            with patch("numeric_producer.inventory", side_effect=AssertionError("raw read began")), \
                    self.assertRaisesRegex(Rejected, "raw evidence budget exceeded"):
                load_raw(root, declared)
            for index in range(5):
                (root / f"ordinary-{index}.log").unlink()
            process = root / "process"
            process.mkdir()
            for index in range(3):
                with (process / f"trace.{index + 1}").open("wb") as stream:
                    stream.truncate(MAX_TRACE_MEMBER)
            with patch("numeric_producer.digest", return_value="0" * 64):
                self.assertGreater(sum(item["size"] for item in inventory(root).values()), MAX_TOTAL)


class CompiledPayloadTest(unittest.TestCase):
    def compiled(self, calls=1):
        def utf(value):
            data = value.encode()
            return b"\x01" + struct.pack(">H", len(data)) + data
        pool = [utf("portable/NumericProbeMatrixTest"), b"\x07\x00\x01",
                utf("geometryCollisionBoundaryAndScale"), utf("()V"), utf("Code"),
                utf("portable/PortableMatrixTest"), b"\x07\x00\x06",
                b"\x0c\x00\x03\x00\x04", b"\x0a\x00\x07\x00\x08"]
        code = b"\x01\xb6\x00\x09" * calls + b"\xb1"
        body = struct.pack(">HHI", 1, 1, len(code)) + code + b"\x00\x00\x00\x00"
        method = struct.pack(">HHHHHI", 1, 3, 4, 1, 5, len(body)) + body
        return (bytes.fromhex("cafebabe00000034") + struct.pack(">H", len(pool) + 1) +
                b"".join(pool) + struct.pack(">HHHHHH", 1, 2, 0, 0, 0, 1) + method + b"\x00\x00")

    def test_compiled_map_rejects_missing_duplicate_and_noncanonical_members(self):
        from numeric_producer import class_map
        names = ["main/portable/NumericalRecorder.class", "test/portable/NumericProbeMatrixTest.class",
                 "test/portable/PortableMatrixTest.class"]
        def archive(entries):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as output:
                for name in entries:
                    output.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), self.compiled())
            return stream.getvalue()
        self.assertEqual(set(class_map(archive(names))), set(names))
        for invalid in (names[:-1], list(reversed(names)), names + ["test/../escape.class"]):
            with self.subTest(names=invalid), self.assertRaises(Rejected):
                class_map(archive(invalid))

    def test_direct_call_edge_requires_exactly_one_original_fixture_call(self):
        from numeric_producer import verify_call_edge
        self.assertEqual(verify_call_edge(self.compiled()), 1)
        for calls in (0, 2):
            with self.subTest(calls=calls), self.assertRaisesRegex(Rejected, "direct call count"):
                verify_call_edge(self.compiled(calls))
        with self.assertRaises(Exception):
            verify_call_edge(self.compiled()[:-10])


if __name__ == "__main__":
    unittest.main()
