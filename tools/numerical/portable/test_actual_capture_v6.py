import json
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from actual_capture_receipt import (FILE_NAMES, FocusedRejected,
                                    _expected_classes, _helper_members, _xml_mirror,
                                    verify_boolean_startup, verify_helper_startup,
                                    load_version6_archive, verify_existing,
                                    verify_launcher_input)
from actual_trace import checked_projection, TraceRejected
from boolean_rotation_jdi import jdi_bridge
from boolean_rotation_jdi.jdi_bridge import verify_jdi_file_writes
from prospective_compare import verify_arithmetic_captures
from receipt import Rejected


class FocusedReplayTest(unittest.TestCase):
    def test_pinned_launcher_identity_and_bytes(self):
        launcher_bytes = b"bounded pinned launcher source test"
        identity = {"device_major": 0, "device_minor": 56,
                    "inode": 42, "size": len(launcher_bytes)}
        digest = hashlib.sha256(launcher_bytes).hexdigest()
        metadata = {"launcher_identity": identity,
                    "launcher_after_identity": identity,
                    "launcher_sha256": digest}
        with patch("actual_capture_receipt.captured_file_identity", return_value=identity), \
                patch.object(Path, "read_bytes", return_value=launcher_bytes), \
                patch.object(jdi_bridge, "JSPAWNHELPER_SHA256", digest):
            self.assertEqual(verify_launcher_input(metadata), digest)
            wrong_size = identity | {"size": len(launcher_bytes) + 1}
            with patch("actual_capture_receipt.captured_file_identity",
                       return_value=wrong_size), self.assertRaises(FocusedRejected):
                verify_launcher_input(metadata | {
                    "launcher_identity": wrong_size,
                    "launcher_after_identity": wrong_size})
            for changed in ({"launcher_sha256": "0" * 64},
                            {"launcher_identity": identity | {"size": identity["size"] + 1}},
                            {"launcher_after_identity": identity | {"inode": identity["inode"] + 1}}):
                with self.subTest(changed=changed), self.assertRaises(FocusedRejected):
                    verify_launcher_input(metadata | changed)

    def test_helper_output_destination_is_checked_before_byte_accounting(self):
        def packed(entries):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                for name, value in entries.items():
                    archive.writestr(name, value)
            return output.getvalue()

        root = str(Path.home() / "focused-jdi-output")
        file_path = root + "/complete.txt"
        files = {"jdi_helper_classes": packed({"RotationJdiProbe.class": b"class"}),
                 "jdi_evidence": packed({"complete.txt": b"abc"})}
        transport = {"helper_classes_path": str(Path.home() / "helper-classes"),
                     "output_path": root}
        classes, outputs = _helper_members(files, transport)
        protected = set(classes) | set(outputs)
        good = (f'1.000001 openat(AT_FDCWD, "{file_path}", '
                f'O_WRONLY|O_CREAT|O_TRUNC, 0666) = 7<{file_path}>\n'
                f'1.000002 write(7<{file_path}>, "abc", 3) = 3\n'
                f'1.000003 close(7<{file_path}>) = 0\n'
                '1.000004 +++ exited with 0 +++\n').encode()
        projected = checked_projection(packed({"trace.41": good}), protected,
                                       strict_outputs=set(outputs))
        self.assertEqual(verify_jdi_file_writes(
            projected["legacy_zip"], files["jdi_evidence"], root)["files"], 1)
        redirected = good.replace(
            f'1.000002 write(7<{file_path}>, "abc", 3) = 3'.encode(),
            (f'1.000002 dup2(8</home/other>, 7<{file_path}>) = 7</home/other>\n'
             '1.0000021 write(7</home/other>, "abc", 3) = 3').encode())
        with self.assertRaises(TraceRejected):
            checked_projection(packed({"trace.41": redirected}), protected,
                               strict_outputs=set(outputs))
        replaced = good.replace(
            b'1.000004 +++ exited with 0 +++\n',
            f'1.0000031 rename("{file_path}", "{root}/other.txt") = 0\n'
            '1.000004 +++ exited with 0 +++\n'.encode())
        with self.assertRaises(TraceRejected):
            checked_projection(packed({"trace.41": replaced}), protected,
                               strict_outputs=set(outputs))

    def test_worker_and_helper_effective_agent_inventory(self):
        home = str(Path.home())
        metadata = {"agent_path": home + "/agent.jar",
                    "witness_path": home + "/witness.log",
                    "mirror_path": home + "/mirror.log"}
        agent = "-javaagent:" + metadata["agent_path"] + "=boolean:" + metadata["witness_path"]
        jdwp = ("-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,"
                 "address=127.0.0.1:40001")
        flags = agent + " " + jdwp + " -XX:+DisableAttachMechanism -Xshare:off " + \
            "-Dportable.booleanMirror=" + metadata["mirror_path"]
        prefix = "[41][info][arguments] "
        def worker_log(options):
            return ("\n".join(prefix + row for row in (
                "VM Arguments:", "jvm_args: " + options,
                "java_command: worker.org.gradle.process.internal.worker.GradleWorkerMain 1",
                "java_class_path (initial): /home/classes",
                "Launcher Type: SUN_STANDARD")) + "\n").encode()
        selected = ("41", "/tmp/dyn4k-tools/jdk21/bin/java",
                    ("java", agent, jdwp, "GradleWorkerMain"))
        verify_boolean_startup(worker_log(flags), selected, metadata, 40001)
        for option in ("-javaagent:/home/other.jar", "-agentlib:other=1"):
            with self.subTest(option=option), self.assertRaises(FocusedRejected):
                verify_boolean_startup(worker_log(flags + " " + option), selected,
                                       metadata, 40001)
            forged = (selected[0], selected[1], selected[2][:-1] +
                      (option, selected[2][-1]))
            with self.subTest(option=option), self.assertRaises(FocusedRejected):
                verify_boolean_startup(worker_log(flags), forged, metadata, 40001)
        helper_path = home + "/helper-arguments.log"
        helper_argv = ["/tmp/dyn4k-tools/jdk21/bin/java", "--add-modules", "jdk.jdi",
                       "-Djava.io.tmpdir=" + home, "-cp", home + "/helper-classes",
                       "RotationJdiProbe", "attach", home + "/output", "127.0.0.1",
                       "40001", "org.dyn4j.geometry.Transform", "1800", "600"]
        helper_prefix = "[42][info][arguments] "
        helper_flags = helper_argv[3] + " -Xlog:arguments=info:file=" + \
            helper_path + ":pid,level,tags:filecount=0"
        def helper_log(options):
            return ("\n".join(helper_prefix + row for row in (
                "VM Arguments:", "jvm_args: " + options,
                "java_command: " + " ".join(helper_argv[6:]),
                "java_class_path (initial): " + helper_argv[5],
                "Launcher Type: SUN_STANDARD")) + "\n").encode()
        verify_helper_startup(helper_log(helper_flags), 42, helper_argv, helper_path)
        for option in ("-javaagent:/home/other.jar", "-agentlib:other=1"):
            with self.subTest(option=option), self.assertRaises(FocusedRejected):
                verify_helper_startup(helper_log(helper_flags + " " + option), 42,
                                      helper_argv, helper_path)

    def test_full_mirror_requires_order_and_final_newline(self):
        xml = (b'<testsuite><system-out>first\nsecond\n'
               b'</system-out></testsuite>')
        self.assertEqual(_xml_mirror({"xml": xml, "mirror": b"first\nsecond\n"}),
                         hashlib.sha256(b"first\nsecond\n").hexdigest())
        for changed in (b"second\nfirst\n", b"first\nsecond", b"first\nSECOND\n"):
            with self.subTest(mirror=changed), self.assertRaises(FocusedRejected):
                _xml_mirror({"xml": xml, "mirror": changed})

    def test_duplicate_compiled_provider_and_engine_shadow_fail(self):
        def packed(entries):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                for name, value in sorted(entries):
                    item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    item.compress_type = zipfile.ZIP_STORED
                    archive.writestr(item, value)
            return output.getvalue()

        artifact = packed([("org/dyn4j/geometry/Transform.class", b"engine")])
        base = [("main/portable/NumericalRecorder.class", b"recorder"),
                ("test/portable/NumericProbeMatrixTest.class", b"probe"),
                ("test/portable/PortableMatrixTest.class", b"matrix")]
        good = packed(base + [("test/portable/Fixture.class", b"fixture")])
        expected, _ = _expected_classes({"portable_classes": good,
                                         "artifact": artifact})
        self.assertEqual(expected["org/dyn4j/geometry/Transform"], b"engine")
        for duplicate in (
                [("test/portable/Fixture.class", b"fixture"),
                 ("main/portable/Fixture.class", b"shadow")],
                [("test/org/dyn4j/geometry/Transform.class", b"shadow")]):
            with self.subTest(duplicate=duplicate), self.assertRaises(FocusedRejected):
                _expected_classes({"portable_classes": packed(base + duplicate),
                                   "artifact": artifact})

    def test_public_replay_compares_exact_case_after_validated_whole_lane(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            archive = root / "capture"
            lane = root / "jvm"
            baseline = root / "baseline"
            attestation = root / "attestation.json"
            for path in (archive, lane / "cases", baseline):
                path.mkdir(parents=True)
            attestation.write_text("{}")
            case = b'{"id":"joint-Revolute-LimitsEnabled-false"}\n'
            name = "joint-Revolute-LimitsEnabled-false.jsonl"
            (archive / name).write_bytes(case)
            (lane / "cases" / name).write_bytes(case)
            (archive / "receipt.json").write_bytes(b"receipt\n")
            (lane / "receipt.json").write_text(json.dumps({
                "candidate_commit": "a" * 40,
                "artifact_sha256": {"target": "b" * 64},
                "runtime": {"executable_sha256": "c" * 64}}))
            focused = {"candidate_commit": "a" * 40,
                       "source_archive_sha256": "d" * 64,
                       "artifact_sha256": "b" * 64,
                       "runtime_sha256": "c" * 64,
                       "case_sha256": hashlib.sha256(case).hexdigest()}
            with patch("actual_capture_receipt.compare_host", return_value={
                    "status": "FAILED_PHYSICAL",
                    "candidate_source_sha256": "d" * 64}) as whole, \
                    patch("actual_capture_receipt.replay_version6",
                          return_value=focused), \
                    patch("actual_capture_receipt.comparison_coverage",
                          return_value={"frozen_case_ids": ["frozen"]}):
                result = verify_existing(archive, lane, baseline, attestation)
            self.assertEqual(result["qualification"], "UNPASSED")
            self.assertEqual(result["whole_lane_status"], "FAILED_PHYSICAL")
            self.assertIsNone(whole.call_args.kwargs["arithmetic_captures"])
            (lane / "cases" / name).write_bytes(case + b" ")
            with patch("actual_capture_receipt.compare_host", return_value={
                    "status": "FAILED_PHYSICAL",
                    "candidate_source_sha256": "d" * 64}), \
                    patch("actual_capture_receipt.replay_version6",
                          return_value=focused), \
                    patch("actual_capture_receipt.comparison_coverage",
                          return_value={"frozen_case_ids": ["frozen"]}):
                with self.assertRaises(FocusedRejected):
                    verify_existing(archive, lane, baseline, attestation)

    def test_version6_inventory_and_old_status_forgery_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            for name in FILE_NAMES.values():
                (root / name).write_bytes(b"raw")
            (root / "worker-class-load-41.log").write_bytes(b"class")
            (root / "worker-arguments-41.log").write_bytes(b"arguments")
            receipt = root / "receipt.json"
            receipt.write_text('{"schema":"portable-arithmetic-capture-receipt/5",'
                               '"status":"PASSED_FOCUSED_METHOD_EVIDENCE"}')
            with self.assertRaises(FocusedRejected):
                load_version6_archive(root)
            receipt.write_text('{"schema":"portable-arithmetic-capture-receipt/6",'
                               '"schema":"portable-arithmetic-capture-receipt/6"}')
            with self.assertRaises(FocusedRejected):
                load_version6_archive(root)
            receipt.write_text('{"schema":"portable-arithmetic-capture-receipt/6"}')
            self.assertEqual(load_version6_archive(root)[0]["schema"],
                             "portable-arithmetic-capture-receipt/6")
            (root / "extra.txt").write_bytes(b"extra")
            with self.assertRaises(FocusedRejected):
                load_version6_archive(root)
            (root / "extra.txt").unlink()
            (root / "mirror.log").unlink()
            (root / "mirror.log").symlink_to(root / "capture.xml")
            with self.assertRaises(FocusedRejected):
                load_version6_archive(root)

    def test_boolean_only_root_still_fails_global_method_inventory(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            (root / "captureRevoluteLimitsFalse").mkdir()
            with self.assertRaisesRegex(Rejected, "method inventory"):
                verify_arithmetic_captures(root, root, "a" * 40,
                                           "b" * 64, "c" * 64)

    def test_public_replay_validates_whole_lane_first_without_capture_override(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            archive = root / "capture"
            lane = root / "jvm"
            baseline = root / "baseline"
            attestation = root / "attestation.json"
            for path in (archive, lane, baseline):
                path.mkdir()
            attestation.write_text("{}")
            (lane / "receipt.json").write_text(json.dumps({
                "candidate_commit": "a" * 40, "artifact_sha256": {"target": "b" * 64},
                "runtime": {"executable_sha256": "c" * 64}}))
            order = []

            def whole(*args, **kwargs):
                order.append("whole")
                self.assertIsNone(kwargs["arithmetic_captures"])
                return {"candidate_source_sha256": "d" * 64,
                        "operation_binding": "UNPASSED_NOT_EXECUTED"}

            def focused(*args, **kwargs):
                order.append("focused")
                return {"candidate_commit": "a" * 40,
                        "source_archive_sha256": "d" * 64,
                        "artifact_sha256": "b" * 64,
                        "runtime_sha256": "c" * 64,
                        "case_sha256": "e" * 64}

            with patch("actual_capture_receipt.compare_host", side_effect=whole), \
                    patch("actual_capture_receipt.replay_version6", side_effect=focused), \
                    patch("actual_capture_receipt.comparison_coverage",
                          return_value={"frozen_case_ids": ["frozen"]}):
                with self.assertRaises(FocusedRejected):
                    verify_existing(archive, lane, baseline, attestation)
            self.assertEqual(order, ["whole", "focused"])


if __name__ == "__main__":
    unittest.main()
