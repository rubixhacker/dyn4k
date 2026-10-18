import copy
import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from capture_actual import ENVIRONMENT_SENTINEL, reject_environment_trace
from actual_arithmetic import (CaptureRejected, _AUDITED_ENGINE_CLASSES,
                               _ROOT, _STAGED_JAR, _inspect_worker_classpath,
                               make_capture_receipt,
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
        classpath = patch("actual_arithmetic._inspect_worker_classpath",
                          return_value=[{"path": str(_STAGED_JAR), "sha256": "0" * 64}])
        classpath.start()
        self.addCleanup(classpath.stop)
    def fixture(self):
        xml = xml_for(fixture())
        runtime = "/tmp/dyn4k-tools/jdk21/bin/java"
        log_pattern = Path.home() / "dyn4k-evidence/worker-class-load-%p.log"
        log_option = (f"-Xlog:class+load=info:file={log_pattern}:"
                      "pid,level,tags:filecount=0")
        log = (f"Starting process 'Gradle Test Executor 1'. Command: {runtime} "
               f"@/tmp/gradle-worker-classpath1txt {log_option} "
               "worker.org.gradle.process.internal.worker.GradleWorkerMain\n"
               "BUILD SUCCESSFUL\n").encode()
        execve = (f'122 execve("{_ROOT / "gradlew"}", ["gradlew", '
                  '"jvmTest", "--tests", '
                  '"portable.ProspectiveArithmeticTest.captureGeometry", '
                  f'"-PportableWorkerClassLoadLog={log_pattern}"], 0x0) = 0\n'
                  f'123 execve("{runtime}", ["{runtime}", '
                  '"@/tmp/gradle-worker-classpath1txt", '
                  f'"{log_option}", '
                  '"worker.org.gradle.process.internal.worker.GradleWorkerMain"], 0x0) = 0\n').encode()
        load = "".join(f"[123][info][class,load] "
                       f"{name.removesuffix('.class').replace('/', '.')} "
                       f"source: {_STAGED_JAR.as_uri()}\n"
                       for name in sorted(_AUDITED_ENGINE_CLASSES)).encode()
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
                 "worker_class_load": load,
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
                    "worker_class_load",
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

    def test_worker_load_log_rejects_substitution_and_recomputed_receipt(self):
        receipt, files, runtime = self.fixture()
        self.assertEqual(receipt["worker_pid"], "123")
        self.assertEqual(len(receipt["worker_class_load_sources"]), 4)
        original = files["worker_class_load"]
        first = sorted(_AUDITED_ENGINE_CLASSES)[0].removesuffix(".class").replace("/", ".")
        changes = {
            "wrong-pid": original.replace(b"[123]", b"[124]"),
            "missing-class": b"\n".join(original.splitlines()[1:]) + b"\n",
            "wrong-engine": original.replace(_STAGED_JAR.as_uri().encode(),
                                             b"file:/tmp/other-engine.jar", 1),
            "duplicate-class": original + original.splitlines()[0] + b"\n",
            "substituted-log": (f"[124][info][class,load] {first} "
                                f"source: {_STAGED_JAR.as_uri()}\n").encode(),
        }
        for name, changed in changes.items():
            files["worker_class_load"] = changed
            with self.subTest(name=name), self.assertRaises(CaptureRejected):
                make_capture_receipt(files, "captureGeometry", "a" * 40,
                                     ["geometry-boundary-s0-o0-d0"], runtime)
        files["worker_class_load"] = original
        files["execve_log"] = files["execve_log"].replace(b"123 execve", b"124 execve")
        with self.assertRaises(CaptureRejected):
            make_capture_receipt(files, "captureGeometry", "a" * 40,
                                 ["geometry-boundary-s0-o0-d0"], runtime)
        files["execve_log"] = files["execve_log"].replace(b"124 execve", b"123 execve")
        files["gradle_log"] = files["gradle_log"].replace(
            b"-Xlog:class+load", b"-Xlog:class+unload")
        with self.assertRaises(CaptureRejected):
            make_capture_receipt(files, "captureGeometry", "a" * 40,
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


class ClasspathProviderTest(unittest.TestCase):
    def test_prior_and_later_engine_providers_fail(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as folder:
            root = Path(folder)
            staged = root / "staged.jar"
            shadow = root / "earlier.jar"
            class_root = root / "classes"
            (class_root / "main").mkdir(parents=True)
            (class_root / "test").mkdir()
            with zipfile.ZipFile(staged, "w") as archive:
                for name in _AUDITED_ENGINE_CLASSES:
                    archive.writestr(name, b"staged")
            with zipfile.ZipFile(shadow, "w") as archive:
                archive.writestr("org/dyn4j/geometry/Transform.class", b"earlier")
            main = class_root / "main"
            test = class_root / "test"
            self.assertEqual(len(_inspect_worker_classpath(
                f"{main}:{test}:{staged}", staged, class_root)), 3)
            for classpath in (f"{shadow}:{main}:{test}:{staged}",
                              f"{main}:{test}:{staged}:{shadow}"):
                with self.subTest(classpath=classpath), self.assertRaises(CaptureRejected):
                    _inspect_worker_classpath(classpath, staged, class_root)


class EnvironmentSentinelTest(unittest.TestCase):
    def test_normal_execve_trace_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "execve.log"
            trace.write_text('123 execve("/jdk/bin/java", ["java"], 0x0) = 0\n')
            reject_environment_trace(trace)
            self.assertTrue(trace.is_file())

    def test_environment_dump_is_removed_and_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "execve.log"
            trace.write_text(f"environment includes {ENVIRONMENT_SENTINEL}\n")
            with self.assertRaises(CaptureRejected):
                reject_environment_trace(trace)
            self.assertFalse(trace.exists())

    def test_unreadable_trace_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "execve.log"
            trace.write_text("synthetic trace bytes")
            with patch.object(Path, "read_bytes", side_effect=PermissionError):
                with self.assertRaisesRegex(CaptureRejected, "process trace is unavailable"):
                    reject_environment_trace(trace)
            self.assertFalse(trace.exists())

    def test_removal_failure_has_safe_error(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "execve.log"
            trace.write_text("synthetic trace bytes")
            with patch.object(Path, "read_bytes", side_effect=PermissionError):
                with patch.object(Path, "unlink", side_effect=PermissionError):
                    with self.assertRaises(CaptureRejected) as raised:
                        reject_environment_trace(trace)
            self.assertEqual(str(raised.exception), "process trace could not be removed")
            self.assertTrue(trace.exists())

    def test_missing_trace_reports_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "execve.log"
            with self.assertRaisesRegex(CaptureRejected, "process trace is missing"):
                reject_environment_trace(trace)
            self.assertFalse(trace.exists())


if __name__ == "__main__":
    unittest.main()
