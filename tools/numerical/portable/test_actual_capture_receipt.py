import copy
import io
import unittest
import zipfile
from unittest.mock import patch

from actual_arithmetic import (CaptureRejected, _ROOT, _STAGED_JAR, make_capture_receipt,
                               verify_capture_receipt)
from test_actual_arithmetic import fixture, xml_for


class CaptureReceiptTest(unittest.TestCase):
    def setUp(self):
        source = patch("actual_arithmetic._source_archive", return_value=b"source")
        source.start()
        self.addCleanup(source.stop)
        binaries = patch("actual_arithmetic._check_local_binaries")
        binaries.start()
        self.addCleanup(binaries.stop)

    def fixture(self):
        xml = xml_for(fixture())
        runtime = "/tmp/dyn4k-tools/jdk21/bin/java"
        log = (f"Starting process 'Gradle Test Executor 1'. Command: {runtime} "
               "@/tmp/gradle-worker-classpath1txt "
               "worker.org.gradle.process.internal.worker.GradleWorkerMain\n"
               "BUILD SUCCESSFUL\n").encode()
        execve = (f'123 execve("{runtime}", ["{runtime}", '
                  '"@/tmp/gradle-worker-classpath1txt", '
                  '"worker.org.gradle.process.internal.worker.GradleWorkerMain"], 0x0) = 0\n').encode()
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as classes:
            for name in ("main/portable/NumericalRecorder.class",
                         "test/portable/ProspectiveArithmeticTest.class",
                         "test/portable/PortableMatrixTest.class"):
                classes.writestr(name, b"class")
        class_root = _ROOT / "tools/numerical/portable/build/classes/kotlin/jvm"
        files = {"xml": xml, "stage_log": b"BUILD SUCCESSFUL\n",
                 "gradle_log": log, "execve_log": execve,
                 "artifact": b"artifact", "runtime": b"runtime", "source": b"source",
                 "worker_classpath": (f"-cp\n{_STAGED_JAR}:{class_root / 'main'}:"
                                      f"{class_root / 'test'}\n").encode(),
                 "portable_classes": payload.getvalue()}
        receipt = make_capture_receipt(files, "captureGeometry", "a" * 40,
                                       ["geometry-boundary-s0-o0-d0"], runtime)
        return receipt, files, runtime

    def test_sealed_capture_keeps_case_policy_unpassed(self):
        receipt, files, runtime = self.fixture()
        result = verify_capture_receipt(receipt, files, "captureGeometry", "a" * 40,
                                        ["geometry-boundary-s0-o0-d0"], runtime)
        self.assertEqual(result["status"], "VERIFIED_ARITHMETIC_BINDING")
        self.assertEqual(result["qualification"], "UNPASSED")
        self.assertEqual(result["operations_verified"], 1)

    def test_stale_bytes_source_artifact_trace_and_runtime_fail(self):
        for key in ("xml", "stage_log", "gradle_log", "execve_log",
                    "artifact", "runtime", "source", "worker_classpath",
                    "portable_classes"):
            receipt, files, runtime = self.fixture()
            files[key] += b"tamper"
            with self.subTest(key=key), self.assertRaises(CaptureRejected):
                verify_capture_receipt(receipt, files, "captureGeometry", "a" * 40,
                                       ["geometry-boundary-s0-o0-d0"], runtime)
        receipt, files, runtime = self.fixture()
        receipt["summary"]["trace_sha256"] = "0" * 64
        with self.assertRaises(CaptureRejected):
            verify_capture_receipt(receipt, files, "captureGeometry", "a" * 40,
                                   ["geometry-boundary-s0-o0-d0"], runtime)
        receipt, files, runtime = self.fixture()
        with patch("actual_arithmetic._source_archive", return_value=b"other"):
            with self.assertRaises(CaptureRejected):
                verify_capture_receipt(receipt, files, "captureGeometry", "a" * 40,
                                       ["geometry-boundary-s0-o0-d0"], runtime)

    def test_wrong_method_process_and_receipt_fields_fail(self):
        receipt, files, runtime = self.fixture()
        for field, value in (("method", "captureJoints"), ("candidate_commit", "b" * 40),
                             ("exit_code", 1), ("runtime_executable", "/other/java")):
            changed = copy.deepcopy(receipt)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(CaptureRejected):
                verify_capture_receipt(changed, files, "captureGeometry", "a" * 40,
                                       ["geometry-boundary-s0-o0-d0"], runtime)
        files["execve_log"] = files["execve_log"].replace(b" = 0", b" = -1")
        with self.assertRaises(CaptureRejected):
            verify_capture_receipt(receipt, files, "captureGeometry", "a" * 40,
                                   ["geometry-boundary-s0-o0-d0"], runtime)


if __name__ == "__main__":
    unittest.main()
