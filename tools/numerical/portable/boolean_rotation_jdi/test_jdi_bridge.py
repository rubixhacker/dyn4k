import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from jdi_bridge import (EvidenceRejected, parse_call_sites, verify_body_map,
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
               "40001", "org.dyn4j.geometry.Transform", "1800", "300"]


class JdiBridgeTest(unittest.TestCase):
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
        worker = archive({"trace.123": (
            'bind(9, {sa_family=AF_INET, sin_port=htons(40001), '
            'sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n'
            'listen(9, 1) = 0\n').encode()})
        helper = archive({"trace.456": (
            'execve("/tmp/dyn4k-tools/jdk21/bin/java", '
            + str(HELPER_ARGS).replace("'", '"') + ', 0x7f /* 1 var */) = 0\n'
            'connect(7, {sa_family=AF_INET, sin_port=htons(40001), '
            'sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n').encode()})
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

    def test_selected_worker_bind_requires_thread_clone_chain(self):
        helper = archive({"trace.456": (
            'execve("/tmp/dyn4k-tools/jdk21/bin/java", '
            + str(HELPER_ARGS).replace("'", '"') + ', 0x7f /* 1 var */) = 0\n'
            'connect(7, {sa_family=AF_INET, sin_port=htons(40001), '
            'sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n').encode()})
        bind = ('bind(9, {sa_family=AF_INET, sin_port=htons(40001), '
                'sin_addr=inet_addr("127.0.0.1")}, 16) = 0\n'
                'listen(9, 1) = 0\n').encode()
        thread = ('clone3({flags=CLONE_VM|CLONE_FS|CLONE_FILES|CLONE_SIGHAND|'
                  'CLONE_THREAD, exit_signal=0}, 88) = 124\n').encode()
        fork = b'clone(child_stack=NULL, flags=SIGCHLD) = 124\n'
        good = archive({"trace.123": thread, "trace.124": bind})
        self.assertEqual(verify_jdi_transport(good, helper, 40001, 123, 456,
                                              HELPER_ARGS)["worker_socket_writer"], 124)
        split = archive({"trace.123": thread + bind.split(b"listen(")[0],
                         "trace.124": b"listen(9, 1) = 0\n"})
        self.assertEqual(verify_jdi_transport(split, helper, 40001, 123, 456,
                                              HELPER_ARGS)["worker_socket_listener"], 124)
        for root in (fork, b"", thread.replace(b"CLONE_THREAD", b"CLONE_PARENT")):
            with self.assertRaises(EvidenceRejected):
                verify_jdi_transport(archive({"trace.123": root,
                                              "trace.124": bind}), helper,
                                     40001, 123, 456, HELPER_ARGS)
        with self.assertRaises(EvidenceRejected):
            verify_jdi_transport(archive({"trace.123": thread,
                                          "trace.124": bind,
                                          "trace.125": b"unrelated\n"}), helper,
                                 40001, 123, 456, HELPER_ARGS)

    def test_vm_disconnect_is_not_vm_death(self):
        source = Path(__file__).resolve().parent
        environment = os.environ.copy()
        environment.pop("OLLAMA_API_KEY", None)
        environment["JAVA_HOME"] = "/tmp/dyn4k-tools/jdk21"
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR", str(Path.home()))) as root:
            environment["TMPDIR"] = root
            build = subprocess.run(("/tmp/dyn4k-tools/jdk21/bin/javac",
                                    "--add-modules", "jdk.jdi", "-d", root,
                                    str(source / "RotationJdiProbe.java"),
                                    str(source / "EndpointControl.java")),
                                   env=environment, capture_output=True, timeout=30)
            self.assertEqual(build.returncode, 0, "JDI endpoint control did not compile")
            run = subprocess.run(("/tmp/dyn4k-tools/jdk21/bin/java", "--add-modules",
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
