import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import jdi_bridge
from jdi_bridge import (EvidenceRejected, compile_helper, parse_call_sites, verify_body_map,
                        verify_jdi_archive, verify_jdi_file_writes,
                        verify_jdi_transport)
from witness import read_probe_events


BODY = """
  private static final kotlin.Unit integratePosition$lambda$0(org.dyn4j.dynamics.AbstractPhysicsBody, double);
    Code:
       2: invokevirtual #461 // Method rotateAboutCenter:(D)V
    LineNumberTable:
      line 264: 0
"""
JOINT = """
  public boolean solvePositionConstraints(org.dyn4j.dynamics.TimeStep, org.dyn4j.dynamics.Settings);
    Code:
     247: invokeinterface #453, 3 // InterfaceMethod org/dyn4j/dynamics/PhysicsBody.rotateAboutCenter:(D)V
     261: invokeinterface #453, 3 // InterfaceMethod org/dyn4j/dynamics/PhysicsBody.rotateAboutCenter:(D)V
     550: invokeinterface #453, 3 // InterfaceMethod org/dyn4j/dynamics/PhysicsBody.rotateAboutCenter:(D)V
     588: invokeinterface #453, 3 // InterfaceMethod org/dyn4j/dynamics/PhysicsBody.rotateAboutCenter:(D)V
    LineNumberTable:
      line 250: 237
      line 251: 252
      line 267: 535
      line 269: 574
"""


def archive(rows):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as output:
        for name, payload in rows.items():
            output.writestr(name, payload)
    return data.getvalue()


TEST_HOME = str(Path.home() / "boolean-jdi-test")
HELPER_ARGS = ["/tmp/dyn4k-tools/jdk21/bin/java", "--add-modules", "jdk.jdi",
               f"-Djava.io.tmpdir={TEST_HOME}/tmp", "-cp", f"{TEST_HOME}/helper-classes",
               "RotationJdiProbe", "attach", f"{TEST_HOME}/jdi", "127.0.0.1",
               "40001", "org.dyn4j.geometry.Transform", "1800", "600"]
WORKER_EXEC = (b'execve("/tmp/dyn4k-tools/jdk21/bin/java", '
               b'["java", "GradleWorkerMain"], 0x7f) = 0\n')
THREAD_CLONE = (b'clone3({flags=CLONE_VM|CLONE_FS|CLONE_FILES|'
                b'CLONE_SIGHAND|CLONE_THREAD, exit_signal=0}, 88) = 124\n')
SOCKET_BIND = (b'bind(9, {sa_family=AF_INET, sin_port=htons(40001), '
               b'sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n')
SOCKET_LISTEN = b'listen(9, 1) = 0\n'
HELPER_SOCKET_TRACE = (
    'execve("/tmp/dyn4k-tools/jdk21/bin/java", '
    + str(HELPER_ARGS).replace("'", '"') + ', 0x7f /* 1 var */) = 0\n'
    'connect(7, {sa_family=AF_INET, sin_port=htons(40001), '
    'sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n').encode()


class JdiBridgeTest(unittest.TestCase):
    def test_compile_helper_rejects_missing_javac_for_default_and_override(self):
        selected_jdks = (
            (None, Path("/default/jdk")),
            ("/ci/jdk", Path("/ci/jdk")),
        )
        with tempfile.TemporaryDirectory(dir=Path.home()) as temporary:
            temporary_root = Path(temporary)
            for configured_jdk, expected_jdk in selected_jdks:
                with self.subTest(configured_jdk=configured_jdk):
                    with patch.dict(os.environ):
                        os.environ.pop("DYN4K_JDI_JDK_HOME", None)
                        if configured_jdk is not None:
                            os.environ["DYN4K_JDI_JDK_HOME"] = configured_jdk
                        with patch.object(jdi_bridge, "JDK21", Path("/default/jdk")):
                            command = (str(expected_jdk / "bin/javac"), "-version")
                            with patch("jdi_bridge.subprocess.run",
                                       side_effect=FileNotFoundError("javac missing")) as run:
                                with self.assertRaises(EvidenceRejected):
                                    compile_helper(b"public class Probe {}",
                                                   temporary_root)
                            self.assertEqual(run.call_args.args[0], command)

    def test_compile_helper_rejects_unpinned_javac_versions(self):
        invalid_versions = (
            ("", "", 0),
            ("", "javac 21.0.12", 1),
            ("javac twenty-one", "", 0),
            ("javac 25.0.1", "", 0),
        )
        selected_jdks = (
            (None, Path("/default/jdk")),
            ("/ci/jdk", Path("/ci/jdk")),
        )
        with tempfile.TemporaryDirectory(dir=Path.home()) as temporary:
            temporary_root = Path(temporary)
            for configured_jdk, expected_jdk in selected_jdks:
                for stdout, stderr, returncode in invalid_versions:
                    with self.subTest(configured_jdk=configured_jdk,
                                      stdout=stdout, stderr=stderr,
                                      returncode=returncode):
                        with patch.dict(os.environ):
                            os.environ.pop("DYN4K_JDI_JDK_HOME", None)
                            if configured_jdk is not None:
                                os.environ["DYN4K_JDI_JDK_HOME"] = configured_jdk
                            with patch.object(jdi_bridge, "JDK21", Path("/default/jdk")):
                                command = (str(expected_jdk / "bin/javac"), "-version")
                                result = subprocess.CompletedProcess(
                                    command, returncode, stdout, stderr)
                                with patch("jdi_bridge.subprocess.run",
                                           return_value=result) as run:
                                    with self.assertRaises(EvidenceRejected):
                                        compile_helper(b"public class Probe {}",
                                                       temporary_root)
                                self.assertEqual(run.call_args.args[0], command)

    def test_aligned_strace_results_allow_closed_fd_reuse(self):
        output = Path(TEST_HOME) / "jdi"
        raw = archive({"first.txt": b"one\n", "second.txt": b"two\n"})
        trace = (
            f'openat(AT_FDCWD, "{output}/first.txt", O_WRONLY|O_CREAT|O_TRUNC, 0666) = 7\n'
            'write(7, "one\\n", 4)                   = 4\n'
            'close(7)                                = 0\n'
            f'openat(AT_FDCWD, "{output}/second.txt", O_WRONLY|O_CREAT|O_TRUNC, 0666) = 7\n'
            'write(7, "two\\n", 4)                   = 4\n'
            'close(7)                                = 0\n').encode()
        result = verify_jdi_file_writes(archive({"trace.456": trace}), raw, output)
        self.assertEqual(result["files"], 2)
        for changed in (trace.replace(b"close(7)                                = 0",
                                      b"close(7)                                = -1", 1),
                        trace.replace(b"write(7, \"two\\n\", 4)                   = 4",
                                      b"write(7, \"two\\n\", 4)                   = 3", 1)):
            with self.assertRaises(EvidenceRejected):
                verify_jdi_file_writes(archive({"trace.456": changed}), raw, output)

    def test_output_bytes_require_complete_kernel_file_writes(self):
        output = Path(TEST_HOME) / "jdi"
        raw = archive({"events.tsv": b"one\ntwo\n", "complete.txt": b"vm-death\n"})
        trace = (
            f'openat(AT_FDCWD, "{output}/events.tsv", O_WRONLY|O_CREAT|O_TRUNC, 0666) = 8\n'
            'write(8, "one\\ntwo\\n", 8) = 8\nclose(8) = 0\n'
            f'openat(AT_FDCWD, "{output}/complete.txt", O_WRONLY|O_CREAT|O_TRUNC, 0666) = 8\n'
            'write(8, "vm-death\\n", 9) = 9\nclose(8) = 0\n').encode()
        helper = archive({"trace.456": trace})
        result = verify_jdi_file_writes(helper, raw, output)
        self.assertEqual(result["status"], "MATCHED_JDI_FILE_WRITES_UNPASSED_LOADER")
        for changed in (
                archive({"events.tsv": b"one\nTWO\n", "complete.txt": b"vm-death\n"}),
                archive({"events.tsv": b"one\ntwo\n"}),
                archive({"events.tsv": b"one\ntwo\n", "complete.txt": b"vm-death\n",
                         "forged.txt": b"forged"})):
            with self.assertRaises(EvidenceRejected):
                verify_jdi_file_writes(helper, changed, output)
        for altered in (trace.replace(b"write(8,", b"write(9,", 1),
                        trace.replace(b") = 8", b") = 7", 1),
                        trace.replace(b"close(8) = 0", b"close(8) = -1", 1),
                        trace.replace(b"events.tsv", b"forged.tsv", 1)):
            with self.assertRaises(EvidenceRejected):
                verify_jdi_file_writes(archive({"trace.456": altered}), raw, output)

    def test_body_map_is_independent_of_marker_token(self):
        mapping = b"b0\t10\nb1\t11\nintegrated\t11\n"
        calls = [{"receiver": 11}, {"receiver": 10}, {"receiver": 11}]
        self.assertEqual(verify_body_map(mapping, calls)["status"],
                         "MATCHED_BODY_RECEIVERS_UNPASSED_LOADER")
        for altered in (mapping.replace(b"integrated\t11", b"integrated\t10"),
                        mapping.replace(b"b0\t10", b"b0\t11"),
                        mapping + b"b2\t12\n"):
            with self.assertRaises(EvidenceRejected):
                verify_body_map(altered, calls)
        with self.assertRaises(EvidenceRejected):
            verify_body_map(mapping, [calls[1], calls[0], calls[2]])

    @unittest.skipUnless(os.environ.get("DYN4K_BOOLEAN_JDI_TOY"),
                         "No retained JDK21 body-map toy supplied")
    def test_toy_archive_requires_all_jdi_bytes(self):
        root = Path(os.environ["DYN4K_BOOLEAN_JDI_TOY"])
        output = root / "toy-1"
        original = {path.name: path.read_bytes() for path in output.iterdir()
                    if path.is_file()}
        class_bytes = (root / "toy-classes/ToyBooleanJdi$Rotation.class").read_bytes()
        markers = [{key: call[key] for key in ("pre", "trig", "post", "angle_bits")}
                   for call in read_probe_events(output, 3)]
        result = verify_jdi_archive(archive(original), class_bytes,
                                    "ToyBooleanJdi$Rotation", 3, markers)
        self.assertEqual(result["status"], "MATCHED_JDI_BYTES_UNPASSED_ORIGIN")
        self.assertEqual(result["qualification"], "UNPASSED")
        self.assertIn("artifact_class_sha256", result)
        self.assertNotIn("loaded_class_sha256", result)
        for changed in ({key: value for key, value in original.items()
                         if key != "body-map.tsv"},
                        {**original, "extra.txt": b"forged"},
                        {**original, "events.tsv": original["events.tsv"].replace(
                            b"8000000000000000", b"0000000000000000", 1)},
                        {**original, "constant-pool.bin": b"forged"}):
            with self.assertRaises(EvidenceRejected):
                verify_jdi_archive(archive(changed), class_bytes,
                                   "ToyBooleanJdi$Rotation", 3, markers)

    def test_source_sites_select_captured_branch(self):
        self.assertEqual(parse_call_sites(BODY, JOINT), [2, 550, 588])
        with self.assertRaises(EvidenceRejected):
            parse_call_sites(BODY.replace("line 264", "line 263"), JOINT)
        with self.assertRaises(EvidenceRejected):
            parse_call_sites(BODY, JOINT.replace("line 269", "line 268"))

    def test_transport_needs_worker_bind_and_helper_connect(self):
        worker = archive({"trace.123": WORKER_EXEC + (
            'bind(9, {sa_family=AF_INET, sin_port=htons(40001), '
            'sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n'
            'listen(9, 1) = 0\n').encode()})
        helper = archive({"trace.456": HELPER_SOCKET_TRACE})
        result = verify_jdi_transport(worker, helper, 40001, 123, 456, HELPER_ARGS)
        self.assertEqual(result["status"], "MATCHED_JDI_SOCKET_SYSCALLS_UNPASSED_PROCESS")
        self.assertEqual(result["qualification"], "UNPASSED")
        for changed_worker, changed_helper, port in (
            (worker.replace(b"bind(", b"find("), helper, 40001),
            (worker.replace(b"listen(9", b"listen(8"), helper, 40001),
            (worker, helper.replace(b"connect(", b"bonnect("), 40001),
            (worker, helper, 40002),
        ):
            with self.assertRaises(EvidenceRejected):
                verify_jdi_transport(changed_worker, changed_helper, port, 123, 456,
                                     HELPER_ARGS)
        original_trace = zipfile.ZipFile(io.BytesIO(helper)).read("trace.456")
        for changed in (archive({"trace.456": original_trace.replace(
                            b"RotationJdiProbe", b"FakeJdiProbe")}),
                        archive({"trace.456": original_trace,
                                 "trace.999": b"forged\n"})):
            with self.assertRaises(EvidenceRejected):
                verify_jdi_transport(worker, changed, 40001, 123, 456, HELPER_ARGS)

    def test_helper_connect_requires_same_process_thread_ancestry(self):
        worker = archive({"trace.123": WORKER_EXEC + SOCKET_BIND + SOCKET_LISTEN})
        leader, connect = HELPER_SOCKET_TRACE.split(b"connect(", 1)
        connect = b"connect(" + connect
        clone = THREAD_CLONE.replace(b"124", b"457")
        helper = archive({"trace.456": leader + clone, "trace.457": connect})
        result = verify_jdi_transport(worker, helper, 40001, 123, 456, HELPER_ARGS)
        self.assertEqual(result["helper_connector"], 457)
        nested = archive({"trace.456": leader + clone,
                          "trace.457": THREAD_CLONE.replace(b"124", b"458"),
                          "trace.458": connect})
        self.assertEqual(verify_jdi_transport(
            worker, nested, 40001, 123, 456, HELPER_ARGS)["helper_connector"], 458)
        for parent, member in (
                (leader + b"clone(child_stack=NULL, flags=SIGCHLD) = 457\n", connect),
                (leader + clone.replace(b"CLONE_FILES", b"CLONE_PARENT"), connect),
                (leader, connect),
                (leader + clone, connect + b'execveat(AT_FDCWD, "/home/stewart/other", '
                 b'["other"], 0x7f, 0) = 0\n')):
            with self.assertRaises(EvidenceRejected):
                verify_jdi_transport(
                    worker, archive({"trace.456": parent, "trace.457": member}),
                    40001, 123, 456, HELPER_ARGS)

    def test_mapped_ipv4_loopback_connect_requires_exact_sockaddr(self):
        port = 37177
        args = HELPER_ARGS.copy()
        args[10] = str(port)
        leader = HELPER_SOCKET_TRACE.split(b"connect(", 1)[0].replace(
            b"40001", str(port).encode())
        clone = THREAD_CLONE.replace(b"124", b"457")
        worker = archive({"trace.123": WORKER_EXEC + SOCKET_BIND.replace(
            b"40001", str(port).encode()) + SOCKET_LISTEN})
        connect = (
            b'connect(6, {sa_family=AF_INET6, sin6_port=htons(37177), '
            b'sin6_flowinfo=htonl(0), inet_pton(AF_INET6, "::ffff:127.0.0.1", '
            b'&sin6_addr), sin6_scope_id=0}, 28) = 0\n')
        helper = archive({"trace.456": leader + clone, "trace.457": connect})
        result = verify_jdi_transport(worker, helper, port, 123, 456, args)
        self.assertEqual(result["helper_connector"], 457)
        self.assertEqual(result["qualification"], "UNPASSED")
        for old, new in (
                (b"::ffff:127.0.0.1", b"::1"),
                (b"::ffff:127.0.0.1", b"::"),
                (b"::ffff:127.0.0.1", b"::ffff:0.0.0.0"),
                (b"::ffff:127.0.0.1", b"::ffff:192.0.2.1"),
                (b"sa_family=AF_INET6", b"sa_family=AF_INET"),
                (b"inet_pton(AF_INET6", b"inet_pton(AF_INET"),
                (b"htons(37177)", b"htons(37178)"),
                (b"sin6_flowinfo=htonl(0)", b"sin6_flowinfo=htonl(1)"),
                (b"sin6_scope_id=0", b"sin6_scope_id=1"),
                (b"&sin6_addr", b"sin6_addr"),
                (b"}, 28)", b"}, 16)"),
                (b"}, 28)", b", extra=0}, 28)"),
                (b") = 0\n", b") = 0 extra\n")):
            with self.subTest(old=old, new=new):
                changed = connect.replace(old, new)
                self.assertNotEqual(changed, connect)
                with self.assertRaises(EvidenceRejected):
                    verify_jdi_transport(
                        worker, archive({"trace.456": leader + clone,
                                         "trace.457": changed}), port, 123, 456, args)
        fork = b"clone(child_stack=NULL, flags=SIGCHLD) = 457\n"
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(
                worker, archive({"trace.456": leader + fork,
                                 "trace.457": connect}), port, 123, 456, args)
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(
                worker, archive({"trace.456": leader + clone,
                                 "trace.457": connect + connect.replace(
                                     b"::ffff:127.0.0.1", b"::1")}),
                port, 123, 456, args)

    def test_selected_worker_bind_requires_thread_clone_chain(self):
        helper = archive({"trace.456": HELPER_SOCKET_TRACE})
        bind = ('bind(9, {sa_family=AF_INET, sin_port=htons(40001), '
                'sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n'
                'listen(9, 1) = 0\n').encode()
        thread = ('clone3({flags=CLONE_VM|CLONE_FS|CLONE_FILES|CLONE_SIGHAND|'
                  'CLONE_THREAD, exit_signal=0}, 88) = 124\n').encode()
        fork = b'clone(child_stack=NULL, flags=SIGCHLD) = 124\n'
        good = archive({"trace.123": WORKER_EXEC + thread, "trace.124": bind})
        result = verify_jdi_transport(good, helper, 40001, 123, 456,
                                      HELPER_ARGS)
        self.assertEqual(result["worker_socket_writer"], 124)
        self.assertEqual(result["worker_socket_listener"], 124)
        self.assertEqual(result["worker_tgid"], 123)
        split = archive({"trace.123": WORKER_EXEC + thread + bind.split(b"listen(")[0],
                         "trace.124": b"listen(9, 1) = 0\n"})
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(split, helper, 40001, 123, 456, HELPER_ARGS)
        for root in (fork, b"", thread.replace(b"CLONE_THREAD", b"CLONE_PARENT")):
            with self.assertRaises(EvidenceRejected):
                verify_jdi_transport(archive({"trace.123": WORKER_EXEC + root,
                                              "trace.124": bind}), helper,
                                     40001, 123, 456, HELPER_ARGS)
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(archive({"trace.123": WORKER_EXEC + thread,
                                          "trace.124": bind,
                                          "trace.125": b"unrelated\n"}), helper,
                                 40001, 123, 456, HELPER_ARGS)

    def test_successful_later_exec_rejects_worker_thread_attribution(self):
        helper = archive({"trace.456": HELPER_SOCKET_TRACE})
        replacement = (b'execve("/home/stewart/replacement", '
                       b'["replacement"], 0x7f) = 0\n')
        replacement_at = (b'execveat(AT_FDCWD, "/home/stewart/replacement", '
                          b'["replacement"], 0x7f, 0) = 0\n')
        for leader, member in (
                (WORKER_EXEC + THREAD_CLONE,
                 SOCKET_BIND + SOCKET_LISTEN + replacement),
                (WORKER_EXEC + THREAD_CLONE + replacement,
                 SOCKET_BIND + SOCKET_LISTEN),
                (WORKER_EXEC + THREAD_CLONE,
                 SOCKET_BIND + SOCKET_LISTEN + replacement_at)):
            worker = archive({"trace.123": leader, "trace.124": member})
            with self.assertRaises(EvidenceRejected):
                verify_jdi_transport(worker, helper, 40001, 123, 456,
                                     HELPER_ARGS)
        failed = (b'execve("/home/stewart/missing", '
                  b'["missing"], 0x7f) = -1 ENOENT (No such file or directory)\n')
        worker = archive({"trace.123": WORKER_EXEC + THREAD_CLONE,
                          "trace.124": SOCKET_BIND + failed + SOCKET_LISTEN})
        self.assertEqual(verify_jdi_transport(
            worker, helper, 40001, 123, 456, HELPER_ARGS)["worker_socket_writer"], 124)
        worker = archive({"trace.123": WORKER_EXEC + failed + THREAD_CLONE,
                          "trace.124": SOCKET_BIND + SOCKET_LISTEN})
        self.assertEqual(verify_jdi_transport(
            worker, helper, 40001, 123, 456, HELPER_ARGS)["worker_tgid"], 123)
        worker = archive({"trace.123": THREAD_CLONE + WORKER_EXEC,
                          "trace.124": SOCKET_BIND + SOCKET_LISTEN})
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(worker, helper, 40001, 123, 456, HELPER_ARGS)

    def test_helper_execveat_replacement_is_rejected(self):
        worker = archive({"trace.123": WORKER_EXEC + SOCKET_BIND + SOCKET_LISTEN})
        replacement = (b'execveat(AT_FDCWD, "/home/stewart/replacement", '
                       b'["replacement"], 0x7f, 0) = 0\n')
        helper = archive({"trace.456": HELPER_SOCKET_TRACE + replacement})
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(worker, helper, 40001, 123, 456, HELPER_ARGS)
        aligned = replacement.replace(b") = 0\n", b")              = 0\n")
        helper = archive({"trace.456": HELPER_SOCKET_TRACE + aligned})
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(worker, helper, 40001, 123, 456, HELPER_ARGS)
        helper = archive({"trace.456": HELPER_SOCKET_TRACE + b"clone(0) = 457\n",
                          "trace.457": replacement})
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(worker, helper, 40001, 123, 456, HELPER_ARGS)
        helper = archive({"trace.456": HELPER_SOCKET_TRACE +
                          b'execve("/home/stewart/replacement", '
                          b'["replacement"], 0x7f) = 0\n'})
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(worker, helper, 40001, 123, 456, HELPER_ARGS)
        failed = replacement.replace(b" = 0\n", b" = -1 ENOENT\n")
        helper = archive({"trace.456": HELPER_SOCKET_TRACE + failed})
        self.assertEqual(verify_jdi_transport(
            worker, helper, 40001, 123, 456, HELPER_ARGS)["qualification"],
            "UNPASSED")

    def test_reversed_listen_rejects_socket_attribution(self):
        helper = archive({"trace.456": HELPER_SOCKET_TRACE})
        for member in (SOCKET_LISTEN + SOCKET_BIND,
                       SOCKET_BIND + SOCKET_LISTEN + SOCKET_LISTEN):
            worker = archive({"trace.123": WORKER_EXEC + THREAD_CLONE,
                              "trace.124": member})
            with self.assertRaises(EvidenceRejected):
                verify_jdi_transport(worker, helper, 40001, 123, 456,
                                     HELPER_ARGS)

    def test_cross_thread_listen_rejects_socket_attribution(self):
        helper = archive({"trace.456": HELPER_SOCKET_TRACE})
        for leader, member in (
                (WORKER_EXEC + THREAD_CLONE + SOCKET_BIND, SOCKET_LISTEN),
                (WORKER_EXEC + THREAD_CLONE + SOCKET_LISTEN,
                 SOCKET_BIND + SOCKET_LISTEN)):
            worker = archive({"trace.123": leader, "trace.124": member})
            with self.assertRaises(EvidenceRejected):
                verify_jdi_transport(worker, helper, 40001, 123, 456,
                                     HELPER_ARGS)

    def test_vm_disconnect_is_not_vm_death(self):
        source = Path(__file__).resolve().parent
        configured_home = os.environ.get("DYN4K_JDI_JDK_HOME")
        if configured_home:
            java_home = Path(configured_home).expanduser().resolve()
            java = java_home / "bin" / "java"
            javac = java_home / "bin" / "javac"
            if not java.is_file() or not javac.is_file() or not os.access(java, os.X_OK) or \
                    not os.access(javac, os.X_OK):
                self.fail("DYN4K_JDI_JDK_HOME must contain executable Java 21 tools")
        else:
            java_name = shutil.which("java")
            javac_name = shutil.which("javac")
            if java_name is None or javac_name is None:
                self.skipTest(
                    "JDK 21 is unavailable; set DYN4K_JDI_JDK_HOME or provide java and javac"
                )
            java = Path(java_name).resolve()
            javac = Path(javac_name).resolve()
            if java.parent != javac.parent:
                self.skipTest("system java and javac do not share a toolchain")
            java_home = java.parent.parent

        for executable in (java, javac):
            version = subprocess.run((str(executable), "-version"), capture_output=True,
                                     text=True, timeout=10)
            self.assertEqual(version.returncode, 0, "Java tool version check failed")
            output = version.stdout + version.stderr
            token = next((part.strip('"') for part in output.split()
                          if part.strip('"')[:1].isdigit()), None)
            is_java_21 = token is not None and token.split(".", 1)[0].split("-", 1)[0] == "21"
            if not is_java_21:
                if configured_home:
                    self.fail("DYN4K_JDI_JDK_HOME does not point to Java 21")
                self.skipTest("system Java toolchain is not version 21")

        environment = os.environ.copy()
        environment.pop("OLLAMA_API_KEY", None)
        environment["JAVA_HOME"] = str(java_home)
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR", str(Path.home()))) as root:
            environment["TMPDIR"] = root
            build = subprocess.run((str(javac),
                                    "--add-modules", "jdk.jdi", "-d", root,
                                    str(source / "RotationJdiProbe.java"),
                                    str(source / "EndpointControl.java")),
                                   env=environment, capture_output=True, timeout=30)
            self.assertEqual(build.returncode, 0, "JDI endpoint control did not compile")
            run = subprocess.run((str(java), "--add-modules",
                                  "jdk.jdi", "-Djava.io.tmpdir=" + root, "-cp", root,
                                  "EndpointControl"), env=environment,
                                 capture_output=True, timeout=15)
            self.assertEqual(run.returncode, 0, "JDI endpoint control failed")

    @unittest.skipUnless(os.environ.get("DYN4K_JDI_RETAINED_JAR"),
                         "No retained source-compatible JAR supplied")
    def test_retained_jar_disassembly(self):
        from jdi_bridge import derive_call_sites
        raw = Path(os.environ["DYN4K_JDI_RETAINED_JAR"]).read_bytes()
        self.assertEqual(derive_call_sites(raw), [2, 550, 588])


if __name__ == "__main__":
    unittest.main()
